"""Automatic schema detection: arbitrary headers → the RevenueOS data model.

The mapper combines three independent evidence sources, because header text
alone is unreliable ("Totale" could be spend, quantity or a line total):

1. **Lexical** – normalised exact-alias hits, token overlap, and a fuzzy
   (SequenceMatcher) similarity on the header string.
2. **Value archetype** – what the cells actually look like: do they parse as
   dates, as money, as emails, how unique are they, what is their magnitude.
3. **Structural** – uniqueness for IDs, cardinality for categories, and the
   position of the column in the file.

The three are blended into a 0..1 confidence, then a greedy one-to-one
assignment resolves competition between columns. Anything below
``REVIEW_THRESHOLD`` is surfaced to the user for manual confirmation instead of
being silently guessed.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field as dc_field
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from .ingestion import parse_number
from .schema import ENTITIES, Entity, Field, Kind
from .parsing import date_parse_ratio

AUTO_THRESHOLD = 0.72       # mapped automatically
REVIEW_THRESHOLD = 0.45     # mapped, but flagged for review
# below REVIEW_THRESHOLD → left unmapped

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[+()\d][\d\s().\-/]{5,}$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

_STOPWORDS = {"the", "of", "di", "del", "della", "il", "la", "le", "lo", "de", "der",
              "das", "des", "and", "e", "et", "y", "a", "al", "in", "per", "n", "nr"}


def normalise(text: Any) -> str:
    """Lowercase, strip accents, collapse punctuation to single spaces."""
    if text is None:
        return ""
    raw = str(text)
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.lower()
    raw = _NON_ALNUM.sub(" ", raw)
    return " ".join(raw.split())


def tokenise(text: Any) -> list[str]:
    return [t for t in normalise(text).split() if t and t not in _STOPWORDS]


# --------------------------------------------------------------------------- #
# value profiling
# --------------------------------------------------------------------------- #
@dataclass
class ColumnProfile:
    name: str
    position: int
    non_null: int
    total: int
    unique: int
    numeric_ratio: float
    date_ratio: float
    email_ratio: float
    phone_ratio: float
    int_ratio: float
    median: float | None
    max_value: float | None
    min_value: float | None
    avg_length: float
    samples: list[str] = dc_field(default_factory=list)

    @property
    def fill_rate(self) -> float:
        return self.non_null / self.total if self.total else 0.0

    @property
    def uniqueness(self) -> float:
        return self.unique / self.non_null if self.non_null else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fillRate": round(self.fill_rate, 4),
            "uniqueValues": self.unique,
            "numericRatio": round(self.numeric_ratio, 3),
            "dateRatio": round(self.date_ratio, 3),
            "samples": self.samples,
        }


def profile_column(series: pd.Series, name: str, position: int, sample_size: int = 300) -> ColumnProfile:
    total = len(series)
    clean = series.dropna()
    clean = clean[clean.astype(str).str.strip() != ""]
    non_null = len(clean)
    if non_null == 0:
        return ColumnProfile(name, position, 0, total, 0, 0.0, 0.0, 0.0, 0.0, 0.0,
                             None, None, None, 0.0, [])

    sample = clean.sample(min(sample_size, non_null), random_state=11) if non_null > sample_size else clean
    text_sample = sample.astype(str).str.strip()

    numbers = [parse_number(v) for v in text_sample]
    parsed = [n for n in numbers if n is not None]
    numeric_ratio = len(parsed) / len(text_sample)
    int_ratio = (sum(1 for n in parsed if float(n).is_integer()) / len(parsed)) if parsed else 0.0

    email_ratio = float(text_sample.map(lambda v: bool(EMAIL_RE.match(v))).mean())
    phone_ratio = float(text_sample.map(lambda v: bool(PHONE_RE.match(v))).mean())
    # a column that is mostly numbers is not a date column unless it parses as one
    date_ratio = date_parse_ratio(text_sample)

    series_numeric = pd.Series(parsed, dtype="float64") if parsed else pd.Series(dtype="float64")
    return ColumnProfile(
        name=name,
        position=position,
        non_null=non_null,
        total=total,
        unique=int(clean.astype(str).str.strip().nunique()),
        numeric_ratio=numeric_ratio,
        date_ratio=date_ratio,
        email_ratio=email_ratio,
        phone_ratio=phone_ratio,
        int_ratio=int_ratio,
        median=float(series_numeric.median()) if not series_numeric.empty else None,
        max_value=float(series_numeric.max()) if not series_numeric.empty else None,
        min_value=float(series_numeric.min()) if not series_numeric.empty else None,
        avg_length=float(text_sample.str.len().mean()),
        samples=[str(v) for v in text_sample.head(4).tolist()],
    )


def profile_frame(frame: pd.DataFrame) -> dict[str, ColumnProfile]:
    return {
        col: profile_column(frame[col], col, idx)
        for idx, col in enumerate(frame.columns)
    }


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #
def lexical_score(header: str, field: Field) -> float:
    """0..1 similarity between a raw header and a canonical field."""
    norm_header = normalise(header)
    if not norm_header:
        return 0.0
    header_tokens = set(tokenise(header))

    best = 0.0
    for alias in (field.name, *field.aliases):
        norm_alias = normalise(alias)
        if not norm_alias:
            continue
        if norm_header == norm_alias:
            return 1.0
        alias_tokens = set(tokenise(alias))
        if alias_tokens and alias_tokens == header_tokens:
            best = max(best, 0.97)
            continue
        # containment: "data ultimo acquisto" contains "ultimo acquisto"
        if alias_tokens and alias_tokens.issubset(header_tokens):
            coverage = len(alias_tokens) / max(len(header_tokens), 1)
            best = max(best, 0.80 + 0.14 * coverage)
        elif header_tokens and header_tokens.issubset(alias_tokens):
            coverage = len(header_tokens) / max(len(alias_tokens), 1)
            best = max(best, 0.70 + 0.18 * coverage)
        ratio = SequenceMatcher(None, norm_header, norm_alias).ratio()
        if ratio > 0.86:
            best = max(best, ratio * 0.92)

    # token-level evidence from the field's keyword list
    if field.tokens and header_tokens:
        field_tokens = set()
        for tok in field.tokens:
            field_tokens.update(tokenise(tok))
        hits = header_tokens & field_tokens
        if hits:
            # partial credit; several matching tokens is stronger evidence
            token_score = 0.40 + 0.16 * min(len(hits), 3)
            token_score *= len(hits) / len(header_tokens) * 0.5 + 0.5
            best = max(best, min(token_score, 0.78))
        else:
            # prefix/substring hints ("qta" vs "quantita", "categ" vs "category")
            for htok in header_tokens:
                for ftok in field_tokens:
                    if len(htok) >= 3 and len(ftok) >= 3 and (
                        htok.startswith(ftok[:4]) or ftok.startswith(htok[:4])
                    ):
                        best = max(best, 0.52)
    return round(min(best, 1.0), 4)


def _kind_score(profile: ColumnProfile, field: Field) -> float:
    """How well the actual cell values fit the field's archetype (0..1)."""
    if profile.non_null == 0:
        return 0.0
    kind = field.kind

    if kind is Kind.EMAIL:
        return profile.email_ratio
    if kind is Kind.PHONE:
        return max(profile.phone_ratio, 0.0)
    if kind is Kind.DATE:
        return profile.date_ratio
    if kind in {Kind.CURRENCY, Kind.NUMBER, Kind.INTEGER, Kind.PERCENT}:
        if profile.numeric_ratio < 0.55:
            return 0.05
        score = 0.55 + 0.45 * profile.numeric_ratio
        if kind is Kind.INTEGER:
            score *= 0.55 + 0.45 * profile.int_ratio
        if kind is Kind.PERCENT and profile.max_value is not None and profile.max_value <= 100:
            score = min(1.0, score + 0.08)
        if kind is Kind.CURRENCY and profile.median is not None and profile.median < 1:
            score *= 0.7
        return min(score, 1.0)
    if kind is Kind.ID:
        # IDs are highly unique and rarely long free text
        if profile.date_ratio > 0.8 or profile.email_ratio > 0.5:
            return 0.05
        uniq = profile.uniqueness
        length_ok = 1.0 if profile.avg_length <= 40 else 0.4
        return min(1.0, (0.35 + 0.65 * uniq) * length_ok)
    if kind is Kind.CATEGORY:
        if profile.email_ratio > 0.5 or profile.date_ratio > 0.8:
            return 0.05
        # "Every value is distinct" only means something once there are enough
        # rows for repetition to be possible. On a 3-row sample every column
        # looks unique, which must not veto a genuine category column.
        if profile.non_null < 12:
            return 0.45 if profile.numeric_ratio > 0.9 else 0.7
        uniq = profile.uniqueness
        # categories repeat: low uniqueness is *good*
        base = 1.0 if uniq <= 0.25 else max(0.15, 1.0 - (uniq - 0.25) * 1.15)
        if profile.numeric_ratio > 0.9:
            base *= 0.45
        return base
    if kind is Kind.LIST:
        if profile.numeric_ratio > 0.8:
            return 0.2
        return 0.65 if profile.avg_length >= 3 else 0.3
    # TEXT
    if profile.numeric_ratio > 0.9 or profile.date_ratio > 0.8:
        return 0.15
    return 0.7


@dataclass
class Candidate:
    field: str
    label: str
    confidence: float
    lexical: float
    value_fit: float
    rationale: str


def _rationale(header: str, field: Field, lexical: float, value_fit: float,
               profile: ColumnProfile) -> str:
    bits: list[str] = []
    if lexical >= 0.97:
        bits.append(f"header matches a known name for {field.label}")
    elif lexical >= 0.7:
        bits.append(f"header is close to {field.label}")
    elif lexical >= 0.4:
        bits.append(f"header shares keywords with {field.label}")
    else:
        bits.append("header gives little signal")

    if field.kind is Kind.DATE and profile.date_ratio > 0.6:
        bits.append(f"{profile.date_ratio:.0%} of values parse as dates")
    elif field.kind is Kind.EMAIL and profile.email_ratio > 0.5:
        bits.append(f"{profile.email_ratio:.0%} of values are valid emails")
    elif field.is_numeric and profile.numeric_ratio > 0.6:
        median = profile.median
        detail = f"median {median:,.0f}" if median is not None else "numeric"
        bits.append(f"values are numeric ({detail})")
    elif field.kind is Kind.ID and profile.uniqueness > 0.8:
        bits.append(f"{profile.uniqueness:.0%} unique values")
    elif field.kind is Kind.CATEGORY and profile.unique <= 60:
        bits.append(f"only {profile.unique} distinct values")
    elif value_fit < 0.3:
        bits.append("cell contents do not look like this field")
    return "; ".join(bits)


def score_column(header: str, profile: ColumnProfile, entity: Entity,
                 top_n: int = 4) -> list[Candidate]:
    """Rank every canonical field of `entity` against one raw column."""
    scored: list[Candidate] = []
    for field in entity.fields:
        lex = lexical_score(header, field)
        val = _kind_score(profile, field)
        if lex < 0.20 and val < 0.85:
            continue
        # Lexical evidence dominates but a hard type mismatch vetoes it.
        confidence = 0.68 * lex + 0.32 * val
        if val < 0.2:
            confidence *= 0.35
        elif val < 0.45:
            confidence *= 0.72
        if lex < 0.25:
            confidence *= 0.45
        if profile.fill_rate < 0.05:
            confidence *= 0.5

        # Some value types identify themselves. A column of valid email
        # addresses is the email column whatever its header says, so strong
        # value evidence sets a floor the lexical penalty cannot drag under.
        if field.kind in {Kind.EMAIL, Kind.PHONE, Kind.DATE} and val >= 0.85:
            confidence = max(confidence, 0.55 * val)

        confidence = max(0.0, min(1.0, confidence))
        if confidence <= 0.02:
            continue
        scored.append(Candidate(
            field=field.name,
            label=field.label,
            confidence=round(confidence, 4),
            lexical=round(lex, 4),
            value_fit=round(val, 4),
            rationale=_rationale(header, field, lex, val, profile),
        ))
    scored.sort(key=lambda c: c.confidence, reverse=True)
    return scored[:top_n]


# --------------------------------------------------------------------------- #
# assignment
# --------------------------------------------------------------------------- #
@dataclass
class ColumnMapping:
    column: str
    field: str | None
    label: str | None
    confidence: float
    status: str            # "auto" | "review" | "unmapped"
    rationale: str
    alternatives: list[Candidate]
    profile: ColumnProfile

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "field": self.field,
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "status": self.status,
            "rationale": self.rationale,
            "samples": self.profile.samples,
            "fillRate": round(self.profile.fill_rate, 4),
            "alternatives": [
                {"field": c.field, "label": c.label, "confidence": round(c.confidence, 4),
                 "rationale": c.rationale}
                for c in self.alternatives
            ],
        }


@dataclass
class MappingResult:
    entity: str
    mappings: list[ColumnMapping]
    missing_required: list[str]
    overall_confidence: float

    def as_field_map(self) -> dict[str, str]:
        """canonical field → source column (only confident-enough mappings)."""
        out: dict[str, str] = {}
        for m in self.mappings:
            if m.field and m.status in {"auto", "review"} and m.field not in out:
                out[m.field] = m.column
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "overallConfidence": round(self.overall_confidence, 4),
            "missingRequired": self.missing_required,
            "columns": [m.to_dict() for m in self.mappings],
        }


def map_columns(frame: pd.DataFrame, entity_name: str,
                profiles: dict[str, ColumnProfile] | None = None) -> MappingResult:
    """Greedy one-to-one assignment of raw columns to canonical fields."""
    ent = ENTITIES[entity_name]
    profiles = profiles or profile_frame(frame)

    all_candidates: list[tuple[float, str, Candidate]] = []
    per_column: dict[str, list[Candidate]] = {}
    for col in frame.columns:
        cands = score_column(col, profiles[col], ent)
        per_column[col] = cands
        for cand in cands:
            all_candidates.append((cand.confidence, col, cand))

    all_candidates.sort(key=lambda item: item[0], reverse=True)

    taken_fields: set[str] = set()
    taken_columns: set[str] = set()
    assignment: dict[str, Candidate] = {}
    for confidence, col, cand in all_candidates:
        if confidence < REVIEW_THRESHOLD:
            continue
        if col in taken_columns or cand.field in taken_fields:
            continue
        assignment[col] = cand
        taken_columns.add(col)
        taken_fields.add(cand.field)

    mappings: list[ColumnMapping] = []
    for col in frame.columns:
        cand = assignment.get(col)
        alternatives = [c for c in per_column[col] if not cand or c.field != cand.field][:3]
        if cand is None:
            best = per_column[col][0] if per_column[col] else None
            mappings.append(ColumnMapping(
                column=col, field=None, label=None, confidence=0.0, status="unmapped",
                rationale=(
                    f"Best guess was {best.label} ({best.confidence:.0%}) — below the "
                    "confidence bar, so it is left for you to confirm."
                    if best else "No canonical field resembles this column."
                ),
                alternatives=per_column[col][:3], profile=profiles[col],
            ))
            continue
        status = "auto" if cand.confidence >= AUTO_THRESHOLD else "review"
        mappings.append(ColumnMapping(
            column=col, field=cand.field, label=cand.label, confidence=cand.confidence,
            status=status, rationale=cand.rationale, alternatives=alternatives,
            profile=profiles[col],
        ))

    mapped_fields = {m.field for m in mappings if m.field}
    missing_required = [f.name for f in ent.required_fields() if f.name not in mapped_fields]

    confident = [m.confidence for m in mappings if m.field]
    overall = sum(confident) / len(confident) if confident else 0.0
    return MappingResult(entity_name, mappings, missing_required, overall)


# --------------------------------------------------------------------------- #
# entity detection
# --------------------------------------------------------------------------- #
def detect_entity(frame: pd.DataFrame,
                  profiles: dict[str, ColumnProfile] | None = None) -> tuple[str, float, dict[str, float]]:
    """Guess whether a file is customers / transactions / inventory.

    Score = quality of the best mapping for that entity, weighted by how many
    of its *required* fields were found, plus a bonus for signature tokens in
    the filename-independent header set.
    """
    profiles = profiles or profile_frame(frame)
    header_tokens: set[str] = set()
    for col in frame.columns:
        header_tokens.update(tokenise(col))

    scores: dict[str, float] = {}
    for name, ent in ENTITIES.items():
        result = map_columns(frame, name, profiles)
        mapped = [m for m in result.mappings if m.field]
        if not mapped:
            scores[name] = 0.0
            continue
        coverage = len(mapped) / max(len(frame.columns), 1)
        quality = sum(m.confidence for m in mapped) / len(mapped)
        required_hit = 1.0 - (len(result.missing_required) /
                              max(len(ent.required_fields()), 1))
        signature = 0.06 * len(header_tokens & set(ent.signature_tokens))
        scores[name] = round(
            0.34 * coverage + 0.30 * quality + 0.36 * required_hit + min(signature, 0.12), 4
        )

    best = max(scores, key=lambda k: scores[k])
    ordered = sorted(scores.values(), reverse=True)
    margin = ordered[0] - (ordered[1] if len(ordered) > 1 else 0.0)
    confidence = round(min(1.0, scores[best] * (0.72 + min(margin, 0.28))), 4)
    return best, confidence, scores
