"""Robust CSV ingestion.

Handles the messy reality of boutique POS/e-commerce exports:
  * unknown encodings (UTF-8/UTF-16/latin-1/cp1252, BOMs)
  * unknown delimiters (, ; tab |)
  * European decimals ("1.234,56") and currency symbols
  * preamble junk rows before the real header
  * headerless files
  * ragged rows, duplicated header names, fully-empty columns

Nothing here raises on "bad" data: we degrade, we never crash.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any

CANDIDATE_DELIMITERS = [",", ";", "\t", "|"]
ENCODINGS = ["utf-8-sig", "utf-8", "utf-16", "cp1252", "latin-1"]

_NUM_RE = re.compile(r"^[\s€£$]*[-+(]?\s*\d[\d\s.,']*\)?\s*%?[\s€£$]*$")


@dataclass
class ParsedTable:
    """A parsed CSV: header names plus row dicts, and how we got there."""

    headers: list[str]
    rows: list[dict[str, str]]
    delimiter: str
    encoding: str
    had_header: bool
    skipped_preamble: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "headers": self.headers,
            "row_count": self.row_count,
            "delimiter": "TAB" if self.delimiter == "\t" else self.delimiter,
            "encoding": self.encoding,
            "had_header": self.had_header,
            "skipped_preamble": self.skipped_preamble,
            "issues": self.issues,
            "sample_rows": self.rows[:5],
        }


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """Decode bytes to text, returning (text, encoding_used)."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            pass
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        # Reject decodings that produced a suspicious number of replacement chars
        if text.count("�") / max(1, len(text)) > 0.001:
            continue
        return text, enc
    return raw.decode("utf-8", errors="replace"), "utf-8 (lossy)"


def sniff_delimiter(text: str) -> str:
    """Pick the delimiter that yields the most consistent, widest table."""
    sample = text[:200_000]
    best, best_score = ",", float("-inf")
    for delim in CANDIDATE_DELIMITERS:
        try:
            rows = [r for r in csv.reader(io.StringIO(sample), delimiter=delim)][:80]
        except csv.Error:
            continue
        rows = [r for r in rows if any(c.strip() for c in r)]
        if len(rows) < 2:
            continue
        widths = [len(r) for r in rows]
        mode_width = max(set(widths), key=widths.count)
        if mode_width <= 1:
            continue
        consistency = widths.count(mode_width) / len(widths)
        drift = sum(abs(w - mode_width) for w in widths) / len(widths)
        score = mode_width * 2 + consistency * 20 - drift * 2
        if score > best_score:
            best, best_score = delim, score
    return best


def _is_numeric_token(value: str) -> bool:
    v = value.strip()
    return bool(v) and bool(_NUM_RE.match(v))


def _looks_like_header(row: list[str], following: list[list[str]]) -> bool:
    """A header row is mostly text while the data below is more numeric/dated."""
    cells = [c.strip() for c in row if c.strip()]
    if not cells:
        return False
    if not following:
        return True
    alpha_share = sum(bool(re.search(r"[A-Za-zÀ-ÿ]", c)) for c in cells) / len(cells)
    if alpha_share < 0.5:
        return False
    header_numeric = sum(_is_numeric_token(c) for c in cells) / len(cells)
    body_numeric = 0.0
    counted = 0
    for r in following[:20]:
        vals = [c.strip() for c in r if c.strip()]
        if not vals:
            continue
        body_numeric += sum(_is_numeric_token(c) for c in vals) / len(vals)
        counted += 1
    body_numeric = body_numeric / counted if counted else 0.0
    # Header should be less numeric than the body, or barely numeric at all.
    return header_numeric < body_numeric or header_numeric < 0.25


def _dedupe_headers(raw: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for i, name in enumerate(raw):
        base = (name or "").strip() or f"Column {i + 1}"
        seen[base] = seen.get(base, 0) + 1
        out.append(base if seen[base] == 1 else f"{base} ({seen[base]})")
    return out


def parse_csv(raw: bytes | str, filename: str = "") -> ParsedTable:
    """Parse arbitrary CSV bytes into a ParsedTable. Never raises on content."""
    issues: list[str] = []
    if isinstance(raw, bytes):
        text, encoding = decode_bytes(raw)
    else:
        text, encoding = raw, "utf-8"
    text = text.lstrip("﻿")

    if not text.strip():
        return ParsedTable([], [], ",", encoding, True, issues=["File is empty."])

    delimiter = sniff_delimiter(text)
    try:
        grid = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter)]
    except csv.Error as exc:  # pragma: no cover - csv rarely raises here
        return ParsedTable([], [], delimiter, encoding, True, issues=[f"Unreadable CSV: {exc}"])

    grid = [r for r in grid if any(c.strip() for c in r)]
    if not grid:
        return ParsedTable([], [], delimiter, encoding, True, issues=["No non-empty rows."])

    # Skip preamble junk: rows narrower than the table's dominant width.
    widths = [len(r) for r in grid[:100]]
    mode_width = max(set(widths), key=widths.count)
    skipped = 0
    while len(grid) > 1 and len(grid[0]) < mode_width and skipped < 10:
        grid.pop(0)
        skipped += 1
    if skipped:
        issues.append(f"Skipped {skipped} preamble row(s) above the header.")

    had_header = _looks_like_header(grid[0], grid[1:])
    width = max(len(r) for r in grid[: min(len(grid), 200)])
    if had_header:
        header_cells = [grid[0][i] if i < len(grid[0]) else "" for i in range(width)]
        headers = _dedupe_headers(header_cells)
        body = grid[1:]
    else:
        headers = [f"Column {i + 1}" for i in range(width)]
        body = grid
        issues.append("No header row detected — columns are positional.")

    rows: list[dict[str, str]] = []
    ragged = 0
    for r in body:
        if len(r) != width:
            ragged += 1
        rows.append({headers[i]: (r[i].strip() if i < len(r) else "") for i in range(width)})
    if ragged:
        issues.append(f"{ragged} row(s) had a different column count and were padded/truncated.")

    # Drop columns that are entirely empty — they only add mapping noise.
    empty_cols = [h for h in headers if not any(row.get(h) for row in rows)]
    if empty_cols and len(empty_cols) < len(headers):
        headers = [h for h in headers if h not in empty_cols]
        rows = [{h: row[h] for h in headers} for row in rows]
        issues.append(f"Ignored {len(empty_cols)} completely empty column(s).")

    if not rows:
        issues.append("Header found but no data rows.")

    return ParsedTable(
        headers=headers,
        rows=rows,
        delimiter=delimiter,
        encoding=encoding,
        had_header=had_header,
        skipped_preamble=skipped,
        issues=issues,
    )
