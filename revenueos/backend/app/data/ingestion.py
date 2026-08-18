"""Raw file ingestion: bytes in, a clean DataFrame plus a parse report out.

This layer makes zero assumptions about *meaning*. It only solves the mechanical
problems that break real boutique exports:

* unknown encodings (UTF-8 with BOM, cp1252 from Excel Windows, latin-1)
* unknown delimiters (``,``  ``;``  ``\\t``  ``|``)
* preamble junk rows above the real header
* European number formats (``1.234,56`` and ``1 234,56``)
* currency symbols and thousands separators glued to numbers
* fully empty columns / rows, duplicated header names
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
DELIMITERS = (",", ";", "\t", "|")

CURRENCY_CHARS = "€$£¥₤ "
_NUMERIC_CLEAN_RE = re.compile(r"[^\d,.\-+eE]")
_MULTISPACE_RE = re.compile(r"\s+")


class IngestionError(ValueError):
    """Raised when a file cannot be parsed into any usable table at all."""


@dataclass
class ParseReport:
    filename: str
    encoding: str
    delimiter: str
    header_row: int
    rows: int
    columns: int
    dropped_empty_columns: list[str] = field(default_factory=list)
    dropped_empty_rows: int = 0
    renamed_duplicates: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "encoding": self.encoding,
            "delimiter": {"\t": "tab"}.get(self.delimiter, self.delimiter),
            "headerRow": self.header_row,
            "rows": self.rows,
            "columns": self.columns,
            "droppedEmptyColumns": self.dropped_empty_columns,
            "droppedEmptyRows": self.dropped_empty_rows,
            "renamedDuplicates": self.renamed_duplicates,
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------- #
# encoding / delimiter detection
# --------------------------------------------------------------------------- #
def decode_bytes(raw: bytes) -> tuple[str, str]:
    """Return ``(text, encoding_used)``, never raising on bad bytes."""
    if not raw:
        raise IngestionError("The file is empty.")
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8 (lossy)"


def detect_delimiter(text: str) -> str:
    """Pick the delimiter that yields the most consistent column count.

    ``csv.Sniffer`` is tried first but it is unreliable on short/ragged files,
    so we always validate its answer with the consistency heuristic.
    """
    sample_lines = [ln for ln in text.splitlines()[:60] if ln.strip()]
    if not sample_lines:
        raise IngestionError("The file contains no readable rows.")

    best: tuple[float, int, str] = (-1.0, 0, ",")
    for delim in DELIMITERS:
        counts = [len(next(csv.reader([ln], delimiter=delim))) for ln in sample_lines]
        counts = [c for c in counts if c > 0]
        if not counts:
            continue
        modal = max(set(counts), key=counts.count)
        if modal < 2:
            continue
        consistency = counts.count(modal) / len(counts)
        # score: prefer consistent parses, break ties on richer column counts
        score = consistency * 100 + min(modal, 40)
        if score > best[0]:
            best = (score, modal, delim)

    if best[1] < 2:
        # single-column file – still usable, default to comma
        return ","
    return best[2]


def _looks_like_header(cells: list[str]) -> bool:
    """A header row is mostly non-empty, mostly non-numeric, mostly short text."""
    values = [c.strip() for c in cells]
    filled = [v for v in values if v]
    if len(filled) < max(2, len(values) * 0.5):
        return False
    numeric = sum(1 for v in filled if _is_number_like(v))
    if numeric > len(filled) * 0.4:
        return False
    long_cells = sum(1 for v in filled if len(v) > 60)
    return long_cells <= len(filled) * 0.25


def detect_header_row(text: str, delimiter: str, max_scan: int = 12) -> int:
    """Skip preamble junk ("Export of 12/03/2026", blank lines, titles)."""
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows: list[list[str]] = []
    for i, row in enumerate(reader):
        if i >= max_scan:
            break
        rows.append(row)
    if not rows:
        return 0
    widths = [len([c for c in r if c.strip()]) for r in rows]
    target = max(widths) if widths else 0
    for idx, row in enumerate(rows):
        if widths[idx] >= max(2, target * 0.6) and _looks_like_header(row):
            return idx
    return 0


# --------------------------------------------------------------------------- #
# numeric coercion
# --------------------------------------------------------------------------- #
def _is_number_like(value: str) -> bool:
    return parse_number(value) is not None


def parse_number(value: Any) -> float | None:
    """Parse a number written in *any* common European or US convention.

    ``1.234,56`` → 1234.56   ``1,234.56`` → 1234.56   ``€ 1 234,56`` → 1234.56
    ``45%`` → 45.0           ``(120)`` → -120.0      ``-`` / ``n/a`` → None
    """
    if value is None:
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
            return None
        return float(value)

    text = str(value).strip()
    if not text:
        return None
    if text.lower() in {"-", "--", "n/a", "na", "null", "none", "nan", "#n/a", ""}:
        return None

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    text = text.replace("%", "")
    text = "".join(ch for ch in text if ch not in CURRENCY_CHARS)
    text = text.replace(" ", "").replace("'", "")
    text = _NUMERIC_CLEAN_RE.sub("", text)
    if not text or text in {"-", "+", ".", ","}:
        return None

    has_comma, has_dot = "," in text, "." in text
    if has_comma and has_dot:
        # the *rightmost* separator is the decimal one
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        # comma is decimal unless it is used as a thousands separator (1,234,567)
        parts = text.split(",")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3
                              and not text.startswith("0,")):
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    elif has_dot:
        parts = text.split(".")
        if len(parts) > 2:  # 1.234.567
            text = text.replace(".", "")
        elif len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3:
            # ambiguous 1.234 -> treat as thousands only when no decimals elsewhere
            text = text.replace(".", "")

    try:
        number = float(text)
    except ValueError:
        return None
    if np.isnan(number) or np.isinf(number):
        return None
    return -number if negative else number


def to_numeric_series(series: pd.Series) -> pd.Series:
    """Vectorised-ish numeric coercion that tolerates mixed junk."""
    if pd.api.types.is_numeric_dtype(series):
        return series.astype("float64")
    return series.map(parse_number).astype("float64")


def numeric_ratio(series: pd.Series, sample: int = 400) -> float:
    """Share of non-empty values that parse as numbers (0..1)."""
    values = series.dropna().astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return 0.0
    if len(values) > sample:
        values = values.sample(sample, random_state=7)
    parsed = values.map(parse_number)
    return float(parsed.notna().mean())


# --------------------------------------------------------------------------- #
# main entrypoint
# --------------------------------------------------------------------------- #
def _clean_header(name: Any, index: int) -> str:
    text = "" if name is None else str(name)
    text = text.replace("﻿", "").strip()
    text = _MULTISPACE_RE.sub(" ", text)
    if not text or text.lower().startswith("unnamed:"):
        return f"column_{index + 1}"
    return text


def read_table(raw: bytes, filename: str = "upload.csv") -> tuple[pd.DataFrame, ParseReport]:
    """Parse an uploaded CSV/TSV/TXT (or Excel) file into a DataFrame."""
    if not raw:
        raise IngestionError("The file is empty.")

    lower = filename.lower()
    if lower.endswith((".xlsx", ".xls")):
        return _read_excel(raw, filename)

    text, encoding = decode_bytes(raw)
    if not text.strip():
        raise IngestionError("The file contains no data.")

    delimiter = detect_delimiter(text)
    header_row = detect_header_row(text, delimiter)

    try:
        frame = pd.read_csv(
            io.StringIO(text),
            sep=delimiter,
            skiprows=header_row,
            dtype=str,
            keep_default_na=False,
            na_values=["", "NULL", "null", "N/A", "n/a", "NaN", "#N/A", "-"],
            engine="python",
            on_bad_lines="skip",
            skip_blank_lines=True,
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise IngestionError(f"Could not parse the file: {exc}") from exc

    report = ParseReport(
        filename=filename,
        encoding=encoding,
        delimiter=delimiter,
        header_row=header_row,
        rows=0,
        columns=0,
    )
    if header_row > 0:
        report.warnings.append(
            f"Skipped {header_row} preamble row(s) before the header line."
        )
    return _finalise(frame, report)


def _read_excel(raw: bytes, filename: str) -> tuple[pd.DataFrame, ParseReport]:
    try:
        frame = pd.read_excel(io.BytesIO(raw), dtype=str)
    except Exception as exc:
        raise IngestionError(
            "Excel files need the optional 'openpyxl' dependency, or export the "
            f"sheet as CSV first ({exc})."
        ) from exc
    report = ParseReport(
        filename=filename, encoding="binary", delimiter="xlsx",
        header_row=0, rows=0, columns=0,
    )
    return _finalise(frame, report)


def _finalise(frame: pd.DataFrame, report: ParseReport) -> tuple[pd.DataFrame, ParseReport]:
    # 1. normalise header names, de-duplicate
    seen: dict[str, int] = {}
    new_columns: list[str] = []
    for idx, col in enumerate(frame.columns):
        name = _clean_header(col, idx)
        if name in seen:
            seen[name] += 1
            renamed = f"{name} ({seen[name]})"
            report.renamed_duplicates[name] = renamed
            name = renamed
        else:
            seen[name] = 1
        new_columns.append(name)
    frame.columns = new_columns

    # 2. trim whitespace on every cell
    for col in frame.columns:
        if frame[col].dtype == object:
            frame[col] = frame[col].astype(str).str.strip()
            frame[col] = frame[col].replace(
                {"nan": None, "NaN": None, "None": None, "": None, "NULL": None}
            )

    # 3. drop fully-empty columns and rows
    empty_cols = [c for c in frame.columns if frame[c].isna().all()]
    if empty_cols:
        frame = frame.drop(columns=empty_cols)
        report.dropped_empty_columns = empty_cols

    before = len(frame)
    frame = frame.dropna(how="all")
    report.dropped_empty_rows = before - len(frame)

    frame = frame.reset_index(drop=True)
    report.rows = len(frame)
    report.columns = len(frame.columns)

    if report.columns == 0:
        raise IngestionError("No usable columns were found in this file.")
    if report.rows == 0:
        report.warnings.append("The file has headers but no data rows.")
    return frame, report
