"""Value-level parsers shared by mapping, cleaning and analytics.

Dates are the single most fragile part of boutique exports: the same file can
mix ``12/03/2026`` (day-first), ``2026-03-12`` and ``12-Mar-26``. We detect the
dominant convention per *column* rather than per row, which avoids the classic
silent bug where 03/04 and 04/03 are read with different meanings.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Iterable

import numpy as np
import pandas as pd

_ISO_RE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")
_DMY_RE = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})")
_MONTH_NAME_RE = re.compile(r"[A-Za-z]{3,}")

_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%m/%d/%Y", "%m-%d-%Y",
    "%d/%m/%y", "%m/%d/%y", "%y-%m-%d",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y %H:%M", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d, %Y",
)


def _clean_date_text(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if text.lower() in {"", "nan", "none", "null", "n/a", "-", "0000-00-00"}:
        return ""
    return text


def parse_date(value: Any, dayfirst: bool = True) -> date | None:
    """Parse a single value into a date, or return None. Never raises."""
    text = _clean_date_text(value)
    if not text:
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.date()
    if isinstance(value, date):
        return value

    # Excel serial numbers (common in .xls exports)
    if text.replace(".", "").isdigit() and len(text.split(".")[0]) == 5:
        try:
            serial = float(text)
            if 20000 < serial < 60000:
                return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=serial)).date()
        except ValueError:
            pass

    normalised = text.replace("T", " ")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(normalised[: len(fmt) + 6].strip(), fmt).date()
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(text, dayfirst=dayfirst, errors="coerce")
    except Exception:
        return None
    if parsed is pd.NaT or pd.isna(parsed):
        return None
    return parsed.date()


def detect_dayfirst(values: Iterable[Any]) -> bool:
    """True when the column is day-first (European), decided by evidence.

    A value like 25/03 proves day-first; 03/25 proves month-first. We count
    both kinds of proof and fall back to European convention on a tie, since
    the product targets EU boutiques.
    """
    day_proof = month_proof = 0
    for raw in values:
        text = _clean_date_text(raw)
        if not text:
            continue
        match = _DMY_RE.match(text)
        if not match:
            continue
        first, second = int(match.group(1)), int(match.group(2))
        if first > 12 and second <= 12:
            day_proof += 1
        elif second > 12 and first <= 12:
            month_proof += 1
    if month_proof > day_proof:
        return False
    return True


def date_parse_ratio(values: pd.Series, sample: int = 200) -> float:
    """Share of non-empty values that parse as a plausible date."""
    clean = values.dropna().astype(str).str.strip()
    clean = clean[clean != ""]
    if clean.empty:
        return 0.0
    if len(clean) > sample:
        clean = clean.sample(sample, random_state=13)
    # Pure integers like 42 or 1200 must not count as dates.
    looks_datey = clean.map(
        lambda v: bool(_ISO_RE.match(v) or _DMY_RE.match(v) or _MONTH_NAME_RE.search(v))
    )
    if looks_datey.mean() < 0.5:
        return 0.0
    dayfirst = detect_dayfirst(clean)
    parsed = clean.map(lambda v: parse_date(v, dayfirst))
    ok = parsed.map(lambda d: d is not None and 1950 <= d.year <= 2100)
    return float(ok.mean())


def to_date_series(series: pd.Series) -> pd.Series:
    """Convert a whole column to datetime64, using one convention throughout."""
    clean = series.astype(object)
    dayfirst = detect_dayfirst(clean.dropna().head(400))
    parsed = clean.map(lambda v: parse_date(v, dayfirst))
    out = pd.to_datetime(pd.Series(parsed, index=series.index), errors="coerce")
    # reject implausible dates rather than propagating garbage
    valid = out.notna() & (out.dt.year >= 1950) & (out.dt.year <= 2100)
    return out.where(valid)


# --------------------------------------------------------------------------- #
# fashion-specific value normalisation
# --------------------------------------------------------------------------- #
_SIZE_ALIASES = {
    "xxs": "XXS", "xs": "XS", "s": "S", "small": "S", "m": "M", "medium": "M",
    "l": "L", "large": "L", "xl": "XL", "xxl": "XXL", "xxxl": "XXXL",
    "2xl": "XXL", "3xl": "XXXL", "u": "ONE SIZE", "tu": "ONE SIZE",
    "one size": "ONE SIZE", "taglia unica": "ONE SIZE", "unica": "ONE SIZE",
    "os": "ONE SIZE",
}

# Italian/EU numeric clothing sizes mapped to letter equivalents so that a
# customer who buys "42" and a product in "M" can still be matched.
_NUMERIC_SIZE_TO_LETTER = {
    34: "XXS", 36: "XS", 38: "S", 40: "S", 42: "M", 44: "M",
    46: "L", 48: "L", 50: "XL", 52: "XL", 54: "XXL", 56: "XXL",
}

_LETTER_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL"]

_COLOR_ALIASES = {
    "nero": "black", "noir": "black", "schwarz": "black", "negro": "black",
    "bianco": "white", "blanc": "white", "weiss": "white", "blanco": "white",
    "beige": "beige", "cammello": "camel", "camel": "camel", "sabbia": "sand",
    "sand": "sand", "crema": "cream", "cream": "cream", "avorio": "ivory",
    "ivory": "ivory", "ecru": "ecru", "panna": "cream",
    "grigio": "grey", "gris": "grey", "gray": "grey", "grey": "grey", "grau": "grey",
    "blu": "blue", "bleu": "blue", "azzurro": "blue", "navy": "navy", "blau": "blue",
    "rosso": "red", "rouge": "red", "rot": "red", "rojo": "red",
    "verde": "green", "vert": "green", "gruen": "green",
    "marrone": "brown", "marron": "brown", "braun": "brown", "cognac": "brown",
    "moka": "brown", "testa di moro": "brown", "chocolate": "brown",
    "rosa": "pink", "pink": "pink", "cipria": "pink", "powder": "pink",
    "giallo": "yellow", "jaune": "yellow", "senape": "mustard", "mustard": "mustard",
    "viola": "purple", "lilla": "purple", "violet": "purple",
    "arancio": "orange", "arancione": "orange", "orange": "orange",
    "oro": "gold", "gold": "gold", "argento": "silver", "silver": "silver",
    "fantasia": "print", "stampa": "print", "print": "print", "multicolor": "multicolour",
    "multicolore": "multicolour",
}

# Neutral palette is a real commercial signal in luxury retail.
NEUTRAL_COLORS = {"black", "white", "beige", "camel", "sand", "cream", "ivory",
                  "ecru", "grey", "navy", "brown"}


def normalise_size(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text in {"nan", "none", "-"}:
        return None
    text = text.replace("taglia", "").replace("size", "").strip()
    text = text.replace("it ", "").replace("eu ", "").strip()
    if text in _SIZE_ALIASES:
        return _SIZE_ALIASES[text]
    digits = re.sub(r"[^\d.]", "", text)
    if digits:
        try:
            number = float(digits)
        except ValueError:
            return text.upper()[:12]
        if number.is_integer():
            return str(int(number))
        return str(number)
    return text.upper()[:12]


def size_to_letter(value: Any) -> str | None:
    """Map any size representation to a comparable letter bucket."""
    size = normalise_size(value)
    if size is None:
        return None
    if size in _LETTER_ORDER or size == "ONE SIZE":
        return size
    try:
        number = int(float(size))
    except (ValueError, TypeError):
        return None
    if number in _NUMERIC_SIZE_TO_LETTER:
        return _NUMERIC_SIZE_TO_LETTER[number]
    # shoe sizes (35-47) have no letter equivalent — keep them numeric
    return None


def size_distance(a: Any, b: Any) -> float | None:
    """0 = identical, 1 = far apart. None when not comparable."""
    sa, sb = normalise_size(a), normalise_size(b)
    if sa is None or sb is None:
        return None
    if sa == sb:
        return 0.0
    if "ONE SIZE" in (sa, sb):
        return 0.15
    la, lb = size_to_letter(sa), size_to_letter(sb)
    if la and lb and la in _LETTER_ORDER and lb in _LETTER_ORDER:
        steps = abs(_LETTER_ORDER.index(la) - _LETTER_ORDER.index(lb))
        return min(1.0, steps / 3.0)
    # numeric (shoes) comparison
    try:
        na, nb = float(sa), float(sb)
    except (ValueError, TypeError):
        return 1.0
    return min(1.0, abs(na - nb) / 4.0)


def normalise_color(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text in {"nan", "none", "-"}:
        return None
    text = re.sub(r"[^a-zà-ÿ ]", " ", text)
    text = " ".join(text.split())
    if not text:
        return None
    if text in _COLOR_ALIASES:
        return _COLOR_ALIASES[text]
    for token in text.split():
        if token in _COLOR_ALIASES:
            return _COLOR_ALIASES[token]
    return text[:20]


def is_neutral_color(value: Any) -> bool:
    colour = normalise_color(value)
    return colour in NEUTRAL_COLORS if colour else False


def normalise_label(value: Any) -> str | None:
    """Title-case a category/brand while keeping known acronyms intact."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "-"}:
        return None
    text = " ".join(text.split())
    if text.isupper() and len(text) <= 4:
        return text
    return text.title() if text.islower() or text.isupper() else text


def normalise_gender(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text[0] in {"f", "d", "w", "m"}:
        if text.startswith(("f", "d", "w")) and not text.startswith("man"):
            # femmina / donna / woman / female
            if text.startswith(("fem", "don", "wom", "f", "d", "w")):
                return "women"
        if text.startswith(("m", "u")) and not text.startswith("miss"):
            return "men"
    if any(k in text for k in ("uomo", "man", "male", "herr", "homme")):
        return "men"
    if any(k in text for k in ("donna", "woman", "women", "female", "damen", "femme")):
        return "women"
    if any(k in text for k in ("unisex", "kids", "child", "bambino", "junior")):
        return "unisex" if "unisex" in text else "kids"
    return None


def split_list(value: Any) -> list[str]:
    """Split a multi-value cell ("Coats; Knitwear, Bags") into clean tokens."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = [str(v) for v in value]
    else:
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            return []
        items = re.split(r"[;,|/]+", text)
    out: list[str] = []
    for item in items:
        cleaned = normalise_label(item)
        if cleaned:
            out.append(cleaned)
    return out


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(number) or np.isinf(number):
        return None
    return number
