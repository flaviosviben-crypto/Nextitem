"""Schema detection: map arbitrary CSV headers onto the RevenueOS schema.

Three independent signals are combined, so a column can be recognised by its
name, by what its values look like, or by both:

  1. lexical  — normalised header vs. multilingual alias list (exact, token, fuzzy)
  2. semantic — a profile of the actual values (emails? dates? money? ids?)
  3. arbitration — each canonical field is claimed by at most one column,
     highest-scoring column wins, losers fall back to their next best guess.

Every mapping carries a confidence in [0, 1] plus a human-readable rationale,
so the UI can show "Ultimo Acquisto → Last Purchase Date → 94%" and let the
user override anything below the confident threshold.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable

from .schema import SCHEMAS, FieldSpec, Kind
from .values import (
    is_boolish,
    is_emailish,
    is_phoneish,
    parse_date,
    parse_number,
)

CONFIDENT = 0.72   # at or above: auto-applied silently
REVIEW = 0.45      # between REVIEW and CONFIDENT: applied but flagged for review


def normalize(text: str) -> str:
    """Lowercase, strip accents, collapse everything non-alphanumeric to spaces."""
    text = unicodedata.normalize("NFD", str(text or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact(text: str) -> str:
    return normalize(text).replace(" ", "")


@dataclass
class ColumnProfile:
    """What the values in a column actually look like."""

    header: str
    filled: int
    total: int
    fill_rate: float
    unique_ratio: float
    numeric_share: float
    date_share: float
    email_share: float
    phone_share: float
    bool_share: float
    median: float | None
    p90: float | None
    max_len: int
    avg_len: float
    distinct: int
    has_currency_symbol: bool
    has_percent: bool
    looks_integer: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def profile_column(header: str, values: Iterable[str], sample: int = 400) -> ColumnProfile:
    raw = [str(v).strip() for v in list(values)[:sample]]
    total = len(raw)
    filled = [v for v in raw if v]
    n = len(filled)
    if n == 0:
        return ColumnProfile(header, 0, total, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                             None, None, 0, 0.0, 0, False, False, False)

    numbers = [parse_number(v) for v in filled]
    nums = [x for x in numbers if x is not None]
    dates = sum(1 for v in filled if parse_date(v) is not None)
    emails = sum(1 for v in filled if is_emailish(v))
    phones = sum(1 for v in filled if is_phoneish(v))
    bools = sum(1 for v in filled if is_boolish(v))
    ordered = sorted(nums)
    median = ordered[len(ordered) // 2] if ordered else None
    p90 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.9))] if ordered else None
    distinct = len(set(filled))

    return ColumnProfile(
        header=header,
        filled=n,
        total=total,
        fill_rate=n / max(1, total),
        unique_ratio=distinct / n,
        numeric_share=len(nums) / n,
        date_share=dates / n,
        email_share=emails / n,
        phone_share=phones / n,
        bool_share=bools / n,
        median=median,
        p90=p90,
        max_len=max(len(v) for v in filled),
        avg_len=sum(len(v) for v in filled) / n,
        distinct=distinct,
        has_currency_symbol=any(re.search(r"[€£$]", v) for v in filled),
        has_percent=sum(v.endswith("%") for v in filled) / n > 0.5,
        looks_integer=bool(nums) and all(float(x).is_integer() for x in nums),
    )


def _lexical_score(header: str, spec: FieldSpec) -> tuple[float, str]:
    """Score header text against a field's aliases. Returns (score, reason)."""
    norm = normalize(header)
    comp = _compact(header)
    if not norm:
        return 0.0, ""

    candidates = {normalize(a) for a in spec.aliases} | {normalize(spec.name), normalize(spec.label)}
    candidates.discard("")

    for cand in candidates:
        if norm == cand or comp == cand.replace(" ", ""):
            return 0.97, f"Header matches the known name “{cand}”"

    best, best_reason = 0.0, ""
    header_tokens = set(norm.split())
    for cand in candidates:
        cand_tokens = set(cand.split())
        ccomp = cand.replace(" ", "")

        # Whole-alias containment ("data ultimo acquisto" inside "crm data ultimo acquisto")
        if len(ccomp) >= 4 and (ccomp in comp or comp in ccomp):
            shorter, longer = sorted((len(ccomp), len(comp)))
            score = 0.80 + 0.12 * (shorter / max(1, longer))
            if score > best:
                best, best_reason = score, f"Header contains “{cand}”"
            continue

        # Token overlap (word order independent)
        if cand_tokens and header_tokens:
            overlap = len(cand_tokens & header_tokens)
            if overlap:
                cover = overlap / len(cand_tokens)
                precision = overlap / len(header_tokens)
                score = 0.55 + 0.30 * cover + 0.10 * precision
                if cover == 1.0 and precision >= 0.5:
                    score = max(score, 0.86)
                if score > best:
                    best, best_reason = score, f"Header words overlap “{cand}”"

        # Character similarity, for typos and truncations
        ratio = SequenceMatcher(None, comp, ccomp).ratio()
        if ratio > 0.86:
            score = 0.50 + 0.35 * ratio
            if score > best:
                best, best_reason = score, f"Header closely resembles “{cand}”"

    return min(best, 0.94), best_reason


def _semantic_score(spec: FieldSpec, p: ColumnProfile) -> tuple[float, str]:
    """Score a column's *values* against what this field should contain.

    Returns (score in [-1, 1], reason). Negative means the values contradict
    the field, which lets us veto a tempting but wrong header match.
    """
    t = spec.value_type
    if p.filled == 0:
        return 0.0, ""

    if t == "email":
        if p.email_share > 0.7:
            return 0.95, "Values are email addresses"
        return (-0.6, "Values are not email addresses") if p.email_share < 0.05 else (0.0, "")

    if t == "phone":
        if p.phone_share > 0.6:
            return 0.85, "Values look like phone numbers"
        return (-0.3, "Values do not look like phone numbers") if p.phone_share < 0.05 else (0.0, "")

    if t == "date":
        if p.date_share > 0.8:
            return 0.92, "Values parse as dates"
        if p.date_share > 0.4:
            return 0.55, "Most values parse as dates"
        return -0.7, "Values are not dates"

    if t == "bool":
        if p.bool_share > 0.8:
            return 0.9, "Values are yes/no flags"
        if p.distinct <= 3 and p.numeric_share > 0.8 and (p.p90 or 0) <= 1:
            return 0.6, "Values are a 0/1 flag"
        return -0.4, "Values are not a yes/no flag"

    if t == "money":
        if p.numeric_share < 0.7:
            return -0.8, "Values are not numeric"
        score, why = 0.45, "Values are numeric"
        if p.has_currency_symbol:
            score, why = 0.9, "Values carry a currency symbol"
        elif not p.looks_integer:
            score, why = 0.68, "Values are decimal amounts"
        if (p.median or 0) >= 20:
            score = min(1.0, score + 0.12)
        if p.has_percent:
            score -= 0.5
            why = "Values look like percentages, not amounts"
        return score, why

    if t == "number":
        if p.numeric_share < 0.7:
            return -0.8, "Values are not numeric"
        return 0.55, "Values are numeric"

    if t == "id":
        if p.unique_ratio > 0.85 and p.avg_len <= 40:
            return 0.7, "Values are near-unique identifiers"
        if p.unique_ratio > 0.25:
            return 0.35, "Values repeat across rows like a foreign key"
        return -0.2, "Values are too repetitive to be an identifier"

    if t == "category":
        if p.distinct <= max(60, p.filled * 0.35) and p.avg_len <= 40:
            return 0.6, "Values form a small set of repeated labels"
        if p.unique_ratio > 0.9:
            return -0.35, "Values are unique per row, not categories"
        return 0.1, ""

    # text
    if p.avg_len >= 2:
        return 0.35, "Values are free text"
    return 0.0, ""


@dataclass
class ColumnMapping:
    header: str
    field: str | None
    label: str | None
    confidence: float
    reason: str
    status: str            # "confident" | "review" | "unmapped"
    alternatives: list[dict[str, Any]]
    profile: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_mapping(kind: Kind, headers: list[str], rows: list[dict[str, str]]) -> list[ColumnMapping]:
    """Map every header to at most one canonical field, with confidence."""
    specs = SCHEMAS[kind]
    profiles = {h: profile_column(h, [r.get(h, "") for r in rows]) for h in headers}

    # Score every (header, field) pair.
    grid: dict[str, list[tuple[float, str, str]]] = {}
    for h in headers:
        p = profiles[h]
        scored: list[tuple[float, str, str]] = []
        for spec in specs:
            lex, lex_reason = _lexical_score(h, spec)
            sem, sem_reason = _semantic_score(spec, p)
            if lex <= 0 and sem <= 0.5:
                continue
            if lex <= 0:
                # Values alone are rarely enough to claim a named field.
                continue
            # Lexical leads; semantics confirm or veto.
            score = lex * (0.72 + 0.28 * max(0.0, min(1.0, (sem + 1) / 2)))
            if sem < 0:
                score += sem * 0.45          # active contradiction pulls it down hard
            if p.fill_rate < 0.15:
                score *= 0.75                 # mostly-empty columns are weak evidence
            reason = " · ".join(x for x in (lex_reason, sem_reason) if x)
            scored.append((max(0.0, min(1.0, score)), spec.name, reason))
        scored.sort(key=lambda x: -x[0])
        grid[h] = scored

    # Arbitrate: a canonical field may only be claimed once.
    claimed: dict[str, tuple[str, float, str]] = {}   # field -> (header, score, reason)
    pending = {h: list(grid[h]) for h in headers}
    for _ in range(len(headers) * len(specs) + 10):
        progressed = False
        for h in headers:
            if any(c[0] == h for c in claimed.values()):
                continue
            while pending[h]:
                score, field_name, reason = pending[h][0]
                if score <= 0:
                    pending[h].clear()
                    break
                holder = claimed.get(field_name)
                if holder is None:
                    claimed[field_name] = (h, score, reason)
                    progressed = True
                    break
                if score > holder[1]:
                    claimed[field_name] = (h, score, reason)
                    # Previous holder must look for its next-best field.
                    pending[holder[0]].pop(0)
                    progressed = True
                    break
                pending[h].pop(0)
            else:
                continue
        if not progressed:
            break

    assigned = {header: (fname, score, reason) for fname, (header, score, reason) in claimed.items()}
    label_of = {s.name: s.label for s in specs}

    out: list[ColumnMapping] = []
    for h in headers:
        alt = [
            {"field": f, "label": label_of.get(f, f), "confidence": round(s, 3)}
            for s, f, _ in grid[h][:4]
        ]
        if h in assigned:
            fname, score, reason = assigned[h]
            status = "confident" if score >= CONFIDENT else ("review" if score >= REVIEW else "unmapped")
            if status == "unmapped":
                out.append(ColumnMapping(h, None, None, round(score, 3),
                                         "Too uncertain to map automatically", "unmapped",
                                         alt, profiles[h].to_dict()))
            else:
                out.append(ColumnMapping(h, fname, label_of.get(fname, fname), round(score, 3),
                                         reason or "Matched by header name", status, alt,
                                         profiles[h].to_dict()))
        else:
            out.append(ColumnMapping(h, None, None, 0.0, "No matching RevenueOS field",
                                     "unmapped", alt, profiles[h].to_dict()))
    return out


def mapping_to_dict(mappings: list[ColumnMapping]) -> dict[str, str]:
    """Collapse mappings into {canonical_field: source_header} for the loaders."""
    return {m.field: m.header for m in mappings if m.field}


def apply_overrides(mappings: list[ColumnMapping], overrides: dict[str, str | None]) -> list[ColumnMapping]:
    """Apply user corrections: {header: field or None}. Keeps fields unique."""
    result = {m.header: m for m in mappings}
    for header, field_name in overrides.items():
        if header not in result:
            continue
        if field_name:
            for other in result.values():
                if other.header != header and other.field == field_name:
                    other.field, other.label, other.status = None, None, "unmapped"
                    other.reason = "Replaced by a manual mapping"
            spec_label = field_name
            for specs in SCHEMAS.values():
                for s in specs:
                    if s.name == field_name:
                        spec_label = s.label
            result[header].field = field_name
            result[header].label = spec_label
            result[header].confidence = 1.0
            result[header].status = "confident"
            result[header].reason = "Set manually"
        else:
            result[header].field = None
            result[header].label = None
            result[header].confidence = 0.0
            result[header].status = "unmapped"
            result[header].reason = "Ignored manually"
    return list(result.values())
