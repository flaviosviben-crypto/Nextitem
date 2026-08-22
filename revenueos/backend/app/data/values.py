"""Value-level parsing primitives.

Every parser returns ``None`` rather than a fabricated default, so downstream
code can honestly distinguish "zero" from "we don't know". That distinction is
the difference between "€0 spend" and "spend not provided".
"""
from __future__ import annotations

import re
from datetime import date, datetime

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_PHONE_RE = re.compile(r"^[+()\d][\d\s\-.()/]{5,}$")
_CURRENCY_RE = re.compile(r"[€£$¥ \s]")

TRUE_TOKENS = {"true", "1", "yes", "y", "si", "sì", "oui", "ja", "vero", "x", "opt in", "optin",
               "granted", "consentito", "accettato", "attivo", "on", "s"}
FALSE_TOKENS = {"false", "0", "no", "n", "non", "nein", "falso", "opt out", "optout", "denied",
                "negato", "rifiutato", "inattivo", "off"}

_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%m/%d/%Y", "%m-%d-%Y",
    "%d/%m/%y", "%d-%m-%y", "%m/%d/%y",
    "%Y%m%d",
    "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y",
)


def parse_number(value: object) -> float | None:
    """Parse a number written in any common European or Anglo convention.

    Handles: "1.234,56", "1,234.56", "€ 1 234,56", "(250)" negatives, "12%".
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip()
    if not s:
        return None

    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = _CURRENCY_RE.sub("", s)
    percent = s.endswith("%")
    s = s.rstrip("%").replace("'", "")
    if not s or not re.search(r"\d", s):
        return None
    if not re.fullmatch(r"[-+]?[\d.,]+", s):
        return None

    last_comma, last_dot = s.rfind(","), s.rfind(".")
    if last_comma >= 0 and last_dot >= 0:
        # Whichever appears last is the decimal separator.
        if last_comma > last_dot:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif last_comma >= 0:
        decimals = len(s) - last_comma - 1
        # "1,50" is decimal; "1,500" is ambiguous but thousands is far more common
        # in exports that also use dots elsewhere, so treat 3 digits as thousands.
        s = s.replace(",", ".") if 0 < decimals <= 2 else s.replace(",", "")
    elif last_dot >= 0:
        decimals = len(s) - last_dot - 1
        if decimals == 3 and re.fullmatch(r"[-+]?\d{1,3}(\.\d{3})+", s):
            s = s.replace(".", "")

    try:
        num = float(s)
    except ValueError:
        return None
    if negative:
        num = -num
    return num / 100 if percent else num


def parse_money(value: object) -> float | None:
    return parse_number(value)


def parse_rate(value: object) -> float | None:
    """Parse a rate that may be expressed as 0.15 or as 15 (meaning 15%)."""
    num = parse_number(value)
    if num is None:
        return None
    if isinstance(value, str) and value.strip().endswith("%"):
        return num
    return num / 100 if abs(num) > 1 else num


def parse_date(value: object) -> date | None:
    """Parse a date, preferring day-first (European) when ambiguous."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s or not re.search(r"\d", s):
        return None
    s = s.replace("T", " ").split(" ")[0].split("+")[0]
    if len(s) < 6:
        return None

    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(s, fmt).date()
        except ValueError:
            continue
        if 1900 <= parsed.year <= 2100:
            return parsed

    m = re.match(r"^(\d{1,4})[-/.](\d{1,2})[-/.](\d{1,4})$", s)
    if m:
        a, b, c = (int(x) for x in m.groups())
        if a > 31:                       # year first
            y, mo, d = a, b, c
        elif c > 31:                     # year last
            y = c
            if a > 12:                   # day must be first
                d, mo = a, b
            elif b > 12:                 # month can't be second -> US order
                mo, d = a, b
            else:
                d, mo = a, b             # ambiguous: European day-first
        else:
            return None
        if y < 100:
            y += 2000 if y < 70 else 1900
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def parse_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if not s:
        return None
    if s in TRUE_TOKENS:
        return True
    if s in FALSE_TOKENS:
        return False
    return None


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    s = re.sub(r"\s+", " ", str(value)).strip()
    return s or None


def clean_label(value: object) -> str | None:
    """Normalise a categorical label: trimmed, title-ish, consistent casing."""
    s = clean_text(value)
    if s is None:
        return None
    if s.lower() in {"n/a", "na", "null", "none", "-", "--", "?", "nd", "n.d."}:
        return None
    # Leave brand acronyms alone ("A.P.C.", "MSGM"); only fix shouty/flat casing.
    letters = [c for c in s if c.isalpha()]
    is_acronym = "." in s or (len(letters) <= 4 and s.isupper())
    if not is_acronym and (s.isupper() or s.islower()):
        s = " ".join(w.capitalize() if len(w) > 2 else w.upper() for w in s.split())
    return s


def is_emailish(value: str) -> bool:
    return bool(_EMAIL_RE.match(str(value).strip()))


def is_phoneish(value: str) -> bool:
    s = str(value).strip()
    return bool(_PHONE_RE.match(s)) and sum(c.isdigit() for c in s) >= 6


def is_boolish(value: str) -> bool:
    return parse_bool(value) is not None


def normalize_size(value: object) -> str | None:
    """Normalise clothing/shoe sizes so 's', 'S ', 'small' all collapse."""
    s = clean_text(value)
    if s is None:
        return None
    key = s.strip().lower().replace(".", "")
    aliases = {
        "xs": "XS", "extra small": "XS", "x small": "XS",
        "s": "S", "small": "S", "piccola": "S",
        "m": "M", "medium": "M", "media": "M",
        "l": "L", "large": "L", "grande": "L",
        "xl": "XL", "extra large": "XL", "x large": "XL",
        "xxl": "XXL", "2xl": "XXL", "xxxl": "XXXL", "3xl": "XXXL",
        "u": "One Size", "os": "One Size", "one size": "One Size",
        "tu": "One Size", "unica": "One Size", "taglia unica": "One Size",
    }
    if key in aliases:
        return aliases[key]
    if re.fullmatch(r"\d{1,2}([.,]5)?", key):
        return key.replace(",", ".")
    return s.upper() if len(s) <= 4 else s


def normalize_color(value: object) -> str | None:
    """Collapse colour spellings across languages to a single label."""
    s = clean_text(value)
    if s is None:
        return None
    key = s.strip().lower()
    aliases = {
        "nero": "Black", "black": "Black", "noir": "Black", "negro": "Black", "schwarz": "Black",
        "bianco": "White", "white": "White", "blanc": "White", "blanco": "White", "weiss": "White",
        "beige": "Beige", "cammello": "Camel", "camel": "Camel", "sabbia": "Sand", "sand": "Sand",
        "grigio": "Grey", "grey": "Grey", "gray": "Grey", "gris": "Grey", "grau": "Grey",
        "blu": "Blue", "blue": "Blue", "bleu": "Blue", "azul": "Blue", "navy": "Navy",
        "rosso": "Red", "red": "Red", "rouge": "Red", "rojo": "Red",
        "verde": "Green", "green": "Green", "vert": "Green",
        "marrone": "Brown", "brown": "Brown", "marron": "Brown", "cuoio": "Tan", "tan": "Tan",
        "rosa": "Pink", "pink": "Pink", "cipria": "Powder Pink",
        "panna": "Cream", "cream": "Cream", "avorio": "Ivory", "ivory": "Ivory",
        "ecru": "Ecru", "tortora": "Taupe", "taupe": "Taupe",
    }
    return aliases.get(key, clean_label(s))
