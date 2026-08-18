"""Customer × product matching with dynamic weight redistribution.

The rule that governs this whole module:

    **Missing information is not a negative signal.**

A signal that cannot be computed (no colour data, no size history, no cost) is
*dropped from the calculation and its weight is redistributed* across the
signals that can be computed. The resulting score therefore always means "how
good a fit is this, given what we actually know", and a boutique that never
exports colours does not see every recommendation collapse to 0%.

Because a score built on two signals is less trustworthy than one built on
eight, the strength of the evidence is reported *separately* as
``dataConfidence`` — the product never disguises thin evidence as precision.

Both directions run on the same maths: the signal functions take numpy arrays
and broadcast, so "rank products for one customer" and "rank customers for one
product" share a single implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd

from ..data.parsing import NEUTRAL_COLORS, normalise_color, size_distance

# Base weights. They are *relative* — only the ones that survive availability
# filtering matter, and they are renormalised for every single pair.
BASE_WEIGHTS: dict[str, float] = {
    "category": 0.22,
    "brand": 0.14,
    "price": 0.15,
    "size": 0.13,
    "color": 0.09,
    "pattern": 0.10,
    "gender": 0.05,
    "season": 0.04,
    "inventory": 0.05,
    "novelty": 0.03,
}

SIGNAL_LABELS = {
    "category": "Category preference",
    "brand": "Brand affinity",
    "price": "Price affinity",
    "size": "Size compatibility",
    "color": "Colour preference",
    "pattern": "Purchase pattern",
    "gender": "Gender fit",
    "season": "Seasonal relevance",
    "inventory": "Inventory priority",
    "novelty": "Newness",
}

# Neutral prior used to damp scores when very little is known. It is the
# empirical "any given piece could suit any given customer" baseline, not zero.
NEUTRAL_PRIOR = 0.42

# Categories that customers naturally buy again vs. buy once.
REPEATABLE_HINTS = ("knit", "maglier", "shirt", "camic", "t-shirt", "top", "trouser",
                    "pantalon", "denim", "jean", "accessor", "scarf", "sciarp", "belt",
                    "cintur", "jewel", "bijoux", "sock", "underwear", "beauty")
CONSIDERED_HINTS = ("coat", "cappott", "outerwear", "jacket", "giacc", "bag", "bors",
                    "shoe", "scarp", "boot", "stivale", "dress", "abito", "suit")

# Simple cross-sell adjacencies used when a customer has no history in the
# product's own category. Deliberately shallow and explainable.
COMPLEMENTS: dict[str, tuple[str, ...]] = {
    "coats": ("knitwear", "scarves", "dresses", "trousers"),
    "outerwear": ("knitwear", "scarves", "dresses", "trousers"),
    "knitwear": ("trousers", "coats", "skirts", "shirts"),
    "dresses": ("shoes", "bags", "jewellery", "coats"),
    "shoes": ("bags", "trousers", "dresses"),
    "bags": ("shoes", "accessories", "jewellery"),
    "trousers": ("knitwear", "shirts", "shoes"),
    "shirts": ("trousers", "knitwear", "skirts"),
    "skirts": ("knitwear", "shirts", "shoes"),
    "accessories": ("bags", "knitwear"),
    "jewellery": ("dresses", "bags"),
    "scarves": ("coats", "knitwear"),
}


# --------------------------------------------------------------------------- #
# context objects
# --------------------------------------------------------------------------- #
@dataclass
class MatchingContext:
    """Everything shared across all pairs, computed once per dataset."""
    products: pd.DataFrame
    customers: pd.DataFrame
    current_month: int
    product_appeal: np.ndarray | None = None      # 0..1 general desirability
    has_category: bool = False
    has_brand: bool = False
    has_color: bool = False
    has_size: bool = False
    has_price: bool = False
    has_gender: bool = False
    has_season: bool = False
    has_risk: bool = False
    has_margin: bool = False
    has_arrival: bool = False
    category_norm: pd.Series | None = None
    brand_norm: pd.Series | None = None
    color_norm: pd.Series | None = None
    notes: list[str] = field(default_factory=list)
    # Signal keys the catalogue cannot support at all (no colour column, etc.)
    absent_signals: list[str] = field(default_factory=list)
    # Profiles are expensive to rebuild and never change within a pipeline run,
    # so the reverse direction (customers for a product) builds them once.
    _profiles: dict[str, "CustomerProfile"] = field(default_factory=dict)

    def profiles_for(self, customers: pd.DataFrame) -> list["CustomerProfile"]:
        out: list[CustomerProfile] = []
        for _, row in customers.iterrows():
            key = str(row.get("customer_id"))
            profile = self._profiles.get(key)
            if profile is None:
                profile = build_profile(row)
                self._profiles[key] = profile
            out.append(profile)
        return out


def _norm_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    text = str(value).strip().lower()
    return text or None


def build_context(products: pd.DataFrame, customers: pd.DataFrame,
                  as_of: pd.Timestamp | None = None) -> MatchingContext:
    as_of = as_of or pd.Timestamp.now()
    products = products.copy()

    def present(column: str) -> bool:
        return column in products.columns and products[column].notna().any()

    ctx = MatchingContext(
        products=products,
        customers=customers,
        current_month=int(as_of.month),
        has_category=present("category"),
        has_brand=present("brand"),
        has_color=present("color"),
        has_size=present("size"),
        has_price=present("price"),
        has_gender=present("gender"),
        has_season=present("season"),
        has_risk="risk_score" in products.columns and products["risk_score"].notna().any(),
        has_margin="margin_pct" in products.columns and products["margin_pct"].notna().any(),
        has_arrival="arrival_date" in products.columns and products["arrival_date"].notna().any(),
    )
    if ctx.has_category:
        ctx.category_norm = products["category"].map(_norm_text)
    if ctx.has_brand:
        ctx.brand_norm = products["brand"].map(_norm_text)
    if ctx.has_color:
        ctx.color_norm = products["color"].map(lambda v: normalise_color(v))

    ctx.product_appeal = _product_appeal(products)
    # Attach the prior to the frame so any subset (or a single row) carries it.
    ctx.products = products.assign(_appeal=ctx.product_appeal)

    # Signals the catalogue cannot support at all. These never enter the
    # calculation, so they would otherwise be invisible; they are recorded here
    # and reported on every result alongside the per-pair gaps.
    for key, label, ok in (("category", "category", ctx.has_category),
                           ("brand", "brand", ctx.has_brand),
                           ("color", "colour", ctx.has_color),
                           ("size", "size", ctx.has_size),
                           ("price", "price", ctx.has_price)):
        if not ok:
            ctx.absent_signals.append(key)
            ctx.notes.append(
                f"No {label} data in the catalogue — that signal's weight was "
                "redistributed across the others."
            )
    return ctx


def _product_appeal(products: pd.DataFrame) -> np.ndarray:
    """A product's general desirability, used as the prior for thin profiles."""
    n = len(products)
    parts: list[np.ndarray] = []
    weights: list[float] = []

    if "sell_through" in products.columns and products["sell_through"].notna().any():
        st = products["sell_through"].astype("float64")
        parts.append(np.clip(st.fillna(st.median()).to_numpy(), 0, 1))
        weights.append(0.5)
    if "units_sold" in products.columns and products["units_sold"].notna().any():
        rank = products["units_sold"].rank(pct=True)
        parts.append(rank.fillna(0.5).to_numpy())
        weights.append(0.3)
    if "risk_score" in products.columns and products["risk_score"].notna().any():
        risk = products["risk_score"].astype("float64") / 100
        parts.append(np.clip(1 - risk.fillna(0.5).to_numpy(), 0, 1))
        weights.append(0.2)

    if not parts:
        return np.full(n, NEUTRAL_PRIOR)
    stacked = np.vstack(parts)
    weight_array = np.array(weights).reshape(-1, 1)
    appeal = (stacked * weight_array).sum(axis=0) / weight_array.sum()
    # keep the prior in a sane band: never 0, never overconfident
    return np.clip(0.30 + 0.30 * appeal, 0.25, 0.65)


# --------------------------------------------------------------------------- #
# customer-side profile
# --------------------------------------------------------------------------- #
@dataclass
class CustomerProfile:
    customer_id: str
    name: str
    categories: dict[str, float]
    brands: dict[str, float]
    colors: dict[str, float]
    sizes: dict[str, float]
    price_low: float | None
    price_high: float | None
    price_mid: float | None
    avg_order_value: float | None
    discount_rate: float | None
    neutral_share: float | None
    purchased_ids: set[str]
    gender: str | None
    recency_days: float | None
    seasonal_months: dict[int, float]
    top_category: str | None
    top_brand: str | None
    evidence_lines: int
    segment: str | None = None
    total_spend: float | None = None
    customer_score: float | None = None


# Bayesian smoothing strength: how many "virtual" observations of the base rate
# are blended into every affinity share. One purchase must not read as a 100%
# preference, so shares are pulled towards the base rate until evidence exists.
SHARE_PRIOR_STRENGTH = 3.0


def _shrink_shares(shares: dict[str, float], evidence: float) -> dict[str, float]:
    """Pull affinity shares towards the uniform base rate on thin evidence."""
    if not shares:
        return shares
    base = 1.0 / max(len(shares), 1)
    n = max(float(evidence), 0.0)
    weight = n / (n + SHARE_PRIOR_STRENGTH)
    return {k: v * weight + base * (1 - weight) for k, v in shares.items()}


def _shares_to_dict(value: Any) -> dict[str, float]:
    if not isinstance(value, list):
        return {}
    out: dict[str, float] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        key = _norm_text(item.get("value"))
        share = item.get("share")
        if key is None or share is None:
            continue
        try:
            out[key] = float(share)
        except (TypeError, ValueError):
            continue
    return out


def _scalar(row: pd.Series, key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(number) or np.isinf(number):
        return None
    return number


def build_profile(row: pd.Series) -> CustomerProfile:
    colors = _shares_to_dict(row.get("color_affinity"))
    normalised_colors: dict[str, float] = {}
    for key, share in colors.items():
        clean = normalise_color(key)
        if clean:
            normalised_colors[clean] = normalised_colors.get(clean, 0.0) + share

    seasonality = row.get("seasonality")
    months: dict[int, float] = {}
    if isinstance(seasonality, list):
        for item in seasonality:
            if isinstance(item, dict) and item.get("month") is not None:
                try:
                    months[int(item["month"])] = float(item.get("share", 0.0))
                except (TypeError, ValueError):
                    continue

    purchased = row.get("purchased_product_ids")
    purchased_ids = {str(p) for p in purchased} if isinstance(purchased, list) else set()

    categories = _shares_to_dict(row.get("category_affinity"))
    brands = _shares_to_dict(row.get("brand_affinity"))

    # CRM-declared preferences count as (weaker) evidence when there is no history
    if not categories:
        declared = row.get("preferred_categories")
        if isinstance(declared, list) and declared:
            weight = round(1 / len(declared), 4)
            categories = {_norm_text(c): weight for c in declared if _norm_text(c)}
    if not brands:
        declared = row.get("preferred_brands")
        if isinstance(declared, list) and declared:
            weight = round(1 / len(declared), 4)
            brands = {_norm_text(b): weight for b in declared if _norm_text(b)}

    sizes = _shares_to_dict(row.get("size_affinity"))
    if not sizes:
        declared = row.get("sizes")
        if isinstance(declared, list) and declared:
            weight = round(1 / len(declared), 4)
            sizes = {_norm_text(s): weight for s in declared if _norm_text(s)}

    if not normalised_colors:
        declared = row.get("colors")
        if isinstance(declared, list) and declared:
            weight = round(1 / len(declared), 4)
            for c in declared:
                clean = normalise_color(c)
                if clean:
                    normalised_colors[clean] = normalised_colors.get(clean, 0.0) + weight

    gender = row.get("gender")
    gender = str(gender).strip().lower() if isinstance(gender, str) and gender.strip() else None

    price_mid = _scalar(row, "price_band_mid")
    aov = _scalar(row, "avg_order_value")
    if price_mid is None and aov is not None:
        price_mid = aov

    lines = _scalar(row, "tx_lines") or 0.0
    categories = _shrink_shares(categories, lines)
    brands = _shrink_shares(brands, lines)
    normalised_colors = _shrink_shares(normalised_colors, lines)

    return CustomerProfile(
        customer_id=str(row.get("customer_id")),
        name=str(row.get("display_name") or row.get("customer_id")),
        categories=categories,
        brands=brands,
        colors=normalised_colors,
        sizes=sizes,
        price_low=_scalar(row, "price_band_low"),
        price_high=_scalar(row, "price_band_high"),
        price_mid=price_mid,
        avg_order_value=aov,
        discount_rate=_scalar(row, "discount_rate"),
        neutral_share=_scalar(row, "neutral_color_share"),
        purchased_ids=purchased_ids,
        gender=gender,
        recency_days=_scalar(row, "recency_days"),
        seasonal_months=months,
        top_category=max(categories, key=categories.get) if categories else None,
        top_brand=max(brands, key=brands.get) if brands else None,
        evidence_lines=int(lines),
        segment=row.get("segment") if isinstance(row.get("segment"), str) else None,
        total_spend=_scalar(row, "total_spend"),
        customer_score=_scalar(row, "customer_score"),
    )


# --------------------------------------------------------------------------- #
# signal computation (vectorised, broadcasts in both directions)
# --------------------------------------------------------------------------- #
def _category_signal(share: np.ndarray, known: np.ndarray, complement: np.ndarray,
                     breadth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (value, available).

    A category the customer buys often scores high. A category they have never
    bought is *neutral-positive* (0.40) rather than a rejection — trying a new
    category is a legitimate commercial move — and lifts to 0.55 when it is a
    natural complement to what they do buy.
    """
    value = np.where(
        known,
        # 0.55 floor + share-driven lift, saturating so a 90% share is not 3x a 30% share
        np.clip(0.55 + 0.45 * np.sqrt(np.clip(share, 0, 1) / np.maximum(breadth, 0.15)), 0, 1),
        np.where(complement > 0, 0.55, 0.40),
    )
    return value, np.ones_like(value, dtype=bool)


def _brand_signal(share: np.ndarray, known: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    value = np.where(known, np.clip(0.60 + 0.40 * np.sqrt(np.clip(share, 0, 1)), 0, 1), 0.42)
    return value, np.ones_like(value, dtype=bool)


def _price_signal(price: np.ndarray, low: float | None, high: float | None,
                  mid: float | None) -> tuple[np.ndarray, np.ndarray]:
    """Gaussian-ish fit around the customer's observed price band."""
    available = np.isfinite(price)
    if mid is None or not np.isfinite(mid) or mid <= 0:
        return np.full(price.shape, np.nan), np.zeros(price.shape, dtype=bool)

    lo = low if low is not None and np.isfinite(low) and low > 0 else mid * 0.6
    hi = high if high is not None and np.isfinite(high) and high > lo else mid * 1.6
    width = max(hi - lo, mid * 0.25, 1.0)

    with np.errstate(invalid="ignore"):
        inside = (price >= lo) & (price <= hi)
        # distance outside the band, in band-widths
        distance = np.where(price < lo, (lo - price) / width,
                            np.where(price > hi, (price - hi) / width, 0.0))
        value = np.where(inside, 0.92, np.clip(0.92 * np.exp(-1.15 * distance), 0.05, 0.92))
        # a slightly-above-band piece is an upsell, not a failure: soften it
        value = np.where((price > hi) & (distance <= 0.5), np.maximum(value, 0.60), value)
    value = np.where(available, value, np.nan)
    return value, available


def _size_signal(distance: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    available = np.isfinite(distance)
    value = np.where(available, np.clip(1.0 - 0.85 * distance, 0.05, 1.0), np.nan)
    return value, available


def _color_signal(share: np.ndarray, known: np.ndarray, is_neutral: np.ndarray,
                  has_color: np.ndarray, neutral_share: float | None
                  ) -> tuple[np.ndarray, np.ndarray]:
    value = np.full(share.shape, np.nan)
    available = has_color.copy()

    exact = np.clip(0.62 + 0.38 * np.sqrt(np.clip(share, 0, 1)), 0, 1)
    value = np.where(known, exact, value)

    unknown = has_color & ~known
    if neutral_share is not None and np.isfinite(neutral_share):
        # customers who buy neutrals still respond to other neutrals
        neutral_value = np.where(is_neutral, 0.35 + 0.5 * neutral_share,
                                 0.35 + 0.45 * (1 - neutral_share))
        value = np.where(unknown, np.clip(neutral_value, 0.15, 0.85), value)
    else:
        value = np.where(unknown, 0.42, value)
    available = available & np.isfinite(value)
    return value, available


def _pattern_signal(repeatable: np.ndarray, known_category: np.ndarray,
                    already_bought: np.ndarray, recency_days: float | None,
                    evidence_lines: int) -> tuple[np.ndarray, np.ndarray]:
    """Does buying this now fit how this customer actually shops?"""
    if evidence_lines <= 0:
        return np.full(repeatable.shape, np.nan), np.zeros(repeatable.shape, dtype=bool)

    value = np.full(repeatable.shape, 0.5)
    # buying more of a repeatable category is natural; a considered purchase
    # they made recently in the same category is less likely to repeat soon
    value = np.where(known_category & repeatable, 0.78, value)
    value = np.where(known_category & ~repeatable, 0.55, value)
    value = np.where(~known_category, 0.45, value)
    # exact same product already owned
    value = np.where(already_bought & repeatable, 0.50, value)
    value = np.where(already_bought & ~repeatable, 0.08, value)

    if recency_days is not None and np.isfinite(recency_days):
        # in-window customers are readier to buy than long-lapsed ones
        readiness = float(np.clip(1.15 - recency_days / 400, 0.6, 1.15))
        value = np.clip(value * readiness, 0.05, 1.0)
    return value, np.ones_like(value, dtype=bool)


def _gender_signal(product_gender: np.ndarray, customer_gender: str | None
                   ) -> tuple[np.ndarray, np.ndarray]:
    if customer_gender is None:
        return np.full(product_gender.shape, np.nan), np.zeros(product_gender.shape, dtype=bool)
    available = product_gender != ""
    match = product_gender == customer_gender
    unisex = np.isin(product_gender, ["unisex", "u"])
    value = np.where(match, 1.0, np.where(unisex, 0.85, 0.12))
    value = np.where(available, value, np.nan)
    return value, available


def _season_signal(product_month_fit: np.ndarray, has_season: np.ndarray
                   ) -> tuple[np.ndarray, np.ndarray]:
    value = np.where(has_season, product_month_fit, np.nan)
    return value, has_season & np.isfinite(value)


def _inventory_signal(risk: np.ndarray, margin: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    parts, weights = [], []
    if np.isfinite(risk).any():
        parts.append(np.where(np.isfinite(risk), np.clip(risk / 100, 0, 1), 0.5))
        weights.append(0.65)
    if np.isfinite(margin).any():
        parts.append(np.where(np.isfinite(margin), np.clip(margin / 100, 0, 1), 0.5))
        weights.append(0.35)
    if not parts:
        return np.full(risk.shape, np.nan), np.zeros(risk.shape, dtype=bool)
    stacked = np.vstack(parts)
    weight_array = np.array(weights).reshape(-1, 1)
    value = (stacked * weight_array).sum(axis=0) / weight_array.sum()
    available = np.isfinite(risk) | np.isfinite(margin)
    return np.where(available, value, np.nan), available


def _novelty_signal(days_in_stock: np.ndarray, already_bought: np.ndarray
                    ) -> tuple[np.ndarray, np.ndarray]:
    available = np.isfinite(days_in_stock)
    value = np.where(available, np.clip(1.0 - days_in_stock / 180, 0.1, 1.0), np.nan)
    value = np.where(already_bought, np.minimum(value, 0.2), value)
    return value, available


# --------------------------------------------------------------------------- #
# helpers used to project one side onto the other
# --------------------------------------------------------------------------- #
def _is_repeatable(categories: Iterable[Any]) -> np.ndarray:
    out = []
    for value in categories:
        text = _norm_text(value) or ""
        if any(hint in text for hint in REPEATABLE_HINTS):
            out.append(True)
        elif any(hint in text for hint in CONSIDERED_HINTS):
            out.append(False)
        else:
            out.append(True)  # default: assume it can be bought again
    return np.array(out, dtype=bool)


def _season_month_fit(products: pd.DataFrame, month: int) -> np.ndarray:
    """How relevant a product's season is *right now* (northern hemisphere)."""
    if "season" not in products.columns:
        return np.full(len(products), np.nan)
    fw_months = {9, 10, 11, 12, 1, 2}
    values = []
    for raw in products["season"]:
        text = _norm_text(raw)
        if text is None:
            values.append(np.nan)
            continue
        is_fw = any(k in text for k in ("fw", "aw", "autumn", "winter", "inverno", "autunno"))
        is_ss = any(k in text for k in ("ss", "spring", "summer", "estate", "primavera"))
        if not is_fw and not is_ss:
            values.append(np.nan)
            continue
        in_fw_window = month in fw_months
        if (is_fw and in_fw_window) or (is_ss and not in_fw_window):
            values.append(0.95)
        else:
            # shoulder months are less punishing than deep out-of-season
            values.append(0.30 if month in {3, 8, 9} else 0.18)
    return np.array(values, dtype="float64")


def _numeric(frame: pd.DataFrame, column: str) -> np.ndarray:
    if column not in frame.columns:
        return np.full(len(frame), np.nan)
    return pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype="float64")


# --------------------------------------------------------------------------- #
# scoring core
# --------------------------------------------------------------------------- #
def _combine(signals: dict[str, tuple[np.ndarray, np.ndarray]], size: int
             ) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    """Weighted mean over available signals, with weights renormalised per pair."""
    total_weight = np.zeros(size)
    weighted_sum = np.zeros(size)
    contributions: dict[str, np.ndarray] = {}

    for name, (value, available) in signals.items():
        weight = BASE_WEIGHTS[name]
        mask = available & np.isfinite(value)
        safe_value = np.where(mask, value, 0.0)
        total_weight += np.where(mask, weight, 0.0)
        weighted_sum += safe_value * np.where(mask, weight, 0.0)
        contributions[name] = np.where(mask, safe_value * weight, np.nan)

    with np.errstate(invalid="ignore", divide="ignore"):
        raw = np.where(total_weight > 0, weighted_sum / total_weight, np.nan)
    coverage = total_weight / sum(BASE_WEIGHTS.values())
    return raw, coverage, contributions


def _shrink(raw: np.ndarray, coverage: np.ndarray, prior: np.ndarray,
            evidence: float = 1.0) -> np.ndarray:
    """Pull thin-evidence scores towards the prior instead of overstating them.

    Two things temper a score: how many signals were computable (``coverage``)
    and how many purchases back the customer profile (``evidence``). A perfect
    match computed from a single receipt is still a guess.
    """
    strength = float(np.clip(evidence / 6.0, 0.0, 1.0))
    lam = 0.42 + 0.34 * np.clip(coverage, 0, 1) + 0.22 * strength
    blended = np.where(np.isfinite(raw), lam * raw + (1 - lam) * prior, prior)
    return np.clip(blended, 0.03, 0.99)


def _confidence_label(coverage: float, evidence_lines: int) -> str:
    if coverage >= 0.75 and evidence_lines >= 4:
        return "high"
    if coverage >= 0.55 and evidence_lines >= 2:
        return "medium"
    if coverage >= 0.35:
        return "low"
    return "very low"


# --------------------------------------------------------------------------- #
# public API — products for a customer
# --------------------------------------------------------------------------- #
def score_products_for_customer(
    profile: CustomerProfile,
    ctx: MatchingContext,
    limit: int = 20,
    only_in_stock: bool = True,
    exclude_purchased: bool = True,
    product_filter: pd.Series | None = None,
) -> list[dict[str, Any]]:
    products = ctx.products
    if products is None or products.empty:
        return []

    mask = pd.Series(True, index=products.index)
    if only_in_stock and "stock" in products.columns:
        stock = pd.to_numeric(products["stock"], errors="coerce")
        # unknown stock is kept — absence of data must not hide the catalogue
        mask &= (stock.isna()) | (stock > 0)
    if product_filter is not None:
        mask &= product_filter.reindex(products.index).fillna(False)

    candidates = products[mask]
    if exclude_purchased and profile.purchased_ids and not candidates.empty:
        repeatable = _is_repeatable(
            candidates["category"] if "category" in candidates.columns
            else pd.Series([None] * len(candidates), index=candidates.index)
        )
        owned = np.isin(candidates["product_id"].astype(str).to_numpy(),
                        list(profile.purchased_ids))
        # A client can rebuy a knit but not the same coat: drop owned one-off
        # pieces entirely, keep repeatable ones (the pattern signal ranks them down).
        candidates = candidates[~(owned & ~repeatable)]
    if candidates.empty:
        return []

    scored = _score_pairs(profile, candidates, ctx)
    order = np.argsort(-scored["score"])[: max(limit, 0)]
    results = []
    for pos in order:
        row = candidates.iloc[pos]
        results.append(_result_payload(profile, row, scored, pos, ctx))
    return results


def score_customers_for_product(
    product: pd.Series,
    customers: pd.DataFrame,
    ctx: MatchingContext,
    limit: int = 20,
    min_score: float = 0.0,
) -> list[dict[str, Any]]:
    """Rank customers for one product — the "who should I call about this" view.

    Vectorised across customers: the product's attributes are scalars, so each
    customer-side signal is one numpy array and the whole base is scored in a
    single pass rather than one DataFrame operation per person.
    """
    if customers is None or customers.empty:
        return []

    profiles = ctx.profiles_for(customers)
    n = len(profiles)

    category = _norm_text(product.get("category"))
    brand = _norm_text(product.get("brand"))
    colour = normalise_color(product.get("color"))
    size = product.get("size")
    price = _to_float(product.get("price"))
    gender = _norm_text(product.get("gender")) or ""
    product_id = str(product.get("product_id"))
    risk = _to_float(product.get("risk_score"))
    margin = _to_float(product.get("margin_pct"))
    days_in_stock = _to_float(product.get("days_in_stock"))
    season_fit = float(_season_month_fit(product.to_frame().T, ctx.current_month)[0])
    repeatable = bool(_is_repeatable([category])[0])

    cat_share = np.array([p.categories.get(category, 0.0) if category else 0.0 for p in profiles])
    cat_known = np.array([bool(category and category in p.categories) for p in profiles])
    complement = np.array([
        1.0 if category and any(
            comp in p.categories for comp in COMPLEMENTS.get(category, ())
        ) else 0.0
        for p in profiles
    ])
    breadth = np.array([
        max(1.0 / max(len(p.categories), 1), 0.15) if p.categories else 0.34 for p in profiles
    ])
    brand_share = np.array([p.brands.get(brand, 0.0) if brand else 0.0 for p in profiles])
    brand_known = np.array([bool(brand and brand in p.brands) for p in profiles])
    color_share = np.array([p.colors.get(colour, 0.0) if colour else 0.0 for p in profiles])
    color_known = np.array([bool(colour and colour in p.colors) for p in profiles])
    color_present = np.full(n, colour is not None)
    is_neutral = np.full(n, bool(colour in NEUTRAL_COLORS) if colour else False)

    size_dist = np.full(n, np.nan)
    if ctx.has_size and size is not None:
        for i, profile in enumerate(profiles):
            if not profile.sizes:
                continue
            best = sorted(profile.sizes.items(), key=lambda kv: kv[1], reverse=True)[:3]
            candidates = [d for d in (size_distance(owned, size) for owned, _ in best)
                          if d is not None]
            if candidates:
                size_dist[i] = min(candidates)

    already_bought = np.array([product_id in p.purchased_ids for p in profiles])
    price_array = np.full(n, price if price is not None else np.nan)
    gender_array = np.full(n, gender, dtype=object)
    risk_array = np.full(n, risk if risk is not None else np.nan)
    margin_array = np.full(n, margin if margin is not None else np.nan)
    days_array = np.full(n, days_in_stock if days_in_stock is not None else np.nan)

    signals: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if ctx.has_category:
        signals["category"] = _category_signal(cat_share, cat_known, complement, breadth)
    if ctx.has_brand:
        signals["brand"] = _brand_signal(brand_share, brand_known)

    # Price fit depends on each customer's own band, so it is computed per row.
    price_values, price_available = np.full(n, np.nan), np.zeros(n, dtype=bool)
    for i, profile in enumerate(profiles):
        value, available = _price_signal(
            price_array[i: i + 1], profile.price_low, profile.price_high, profile.price_mid
        )
        price_values[i], price_available[i] = value[0], available[0]
    signals["price"] = (price_values, price_available)
    signals["size"] = _size_signal(size_dist)
    if ctx.has_color:
        neutral_shares = np.array([
            p.neutral_share if p.neutral_share is not None else np.nan for p in profiles
        ])
        colour_values, colour_available = np.full(n, np.nan), np.zeros(n, dtype=bool)
        for i, profile in enumerate(profiles):
            value, available = _color_signal(
                color_share[i: i + 1], color_known[i: i + 1], is_neutral[i: i + 1],
                color_present[i: i + 1], profile.neutral_share,
            )
            colour_values[i], colour_available[i] = value[0], available[0]
        signals["color"] = (colour_values, colour_available)
        _ = neutral_shares

    pattern_values, pattern_available = np.full(n, np.nan), np.zeros(n, dtype=bool)
    for i, profile in enumerate(profiles):
        value, available = _pattern_signal(
            np.array([repeatable]), cat_known[i: i + 1], already_bought[i: i + 1],
            profile.recency_days, profile.evidence_lines,
        )
        pattern_values[i], pattern_available[i] = value[0], available[0]
    signals["pattern"] = (pattern_values, pattern_available)

    gender_values, gender_available = np.full(n, np.nan), np.zeros(n, dtype=bool)
    for i, profile in enumerate(profiles):
        value, available = _gender_signal(gender_array[i: i + 1], profile.gender)
        gender_values[i], gender_available[i] = value[0], available[0]
    signals["gender"] = (gender_values, gender_available)

    season_array = np.full(n, season_fit)
    signals["season"] = _season_signal(season_array, np.isfinite(season_array))
    signals["inventory"] = _inventory_signal(risk_array, margin_array)
    signals["novelty"] = _novelty_signal(days_array, already_bought)

    raw, coverage, contributions = _combine(signals, n)
    appeal = _to_float(product.get("_appeal"))
    prior = np.full(n, appeal if appeal is not None else NEUTRAL_PRIOR)
    evidence = np.array([float(p.evidence_lines) for p in profiles])
    strength = np.clip(evidence / 6.0, 0.0, 1.0)
    lam = 0.42 + 0.34 * np.clip(coverage, 0, 1) + 0.22 * strength
    score = np.clip(
        np.where(np.isfinite(raw), lam * raw + (1 - lam) * prior, prior), 0.03, 0.99
    )

    scored = {
        "score": score, "raw": raw, "coverage": coverage,
        "contributions": contributions,
        "signals": {k: v[0] for k, v in signals.items()},
        "available": {k: v[1] for k, v in signals.items()},
        "cat_share": cat_share, "cat_known": cat_known,
        "brand_share": brand_share, "brand_known": brand_known,
        "color_known": color_known, "already_bought": already_bought,
        "size_distance": size_dist, "price": price_array,
    }

    order = np.argsort(-score)
    rows: list[dict[str, Any]] = []
    for pos in order:
        if float(score[pos]) < min_score:
            break
        profile = profiles[pos]
        payload = _result_payload(profile, product, scored, int(pos), ctx)
        payload["customerId"] = profile.customer_id
        payload["customerName"] = profile.name
        payload["segment"] = profile.segment
        payload["totalSpend"] = profile.total_spend
        payload["customerScore"] = profile.customer_score
        rows.append(payload)
        if len(rows) >= limit:
            break
    return rows


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(number) or np.isinf(number)) else number


def _score_pairs(profile: CustomerProfile, products: pd.DataFrame,
                 ctx: MatchingContext) -> dict[str, Any]:
    """Core scoring for one customer against N products."""
    n = len(products)
    index = products.index

    # ---- project customer affinities onto the product rows ---- #
    if ctx.has_category and "category" in products.columns:
        cats = products["category"].map(_norm_text)
        cat_share = np.array([profile.categories.get(c, 0.0) if c else 0.0 for c in cats])
        cat_known = np.array([bool(c and c in profile.categories) for c in cats])
        complement = np.array([
            1.0 if c and any(
                comp in owned for owned in profile.categories
                for comp in COMPLEMENTS.get(c, ())
            ) else 0.0
            for c in cats
        ])
    else:
        cats = pd.Series([None] * n, index=index)
        cat_share = np.zeros(n)
        cat_known = np.zeros(n, dtype=bool)
        complement = np.zeros(n)

    breadth = 1.0 / max(len(profile.categories), 1) if profile.categories else 0.34
    breadth_array = np.full(n, max(breadth, 0.15))

    if ctx.has_brand and "brand" in products.columns:
        brands = products["brand"].map(_norm_text)
        brand_share = np.array([profile.brands.get(b, 0.0) if b else 0.0 for b in brands])
        brand_known = np.array([bool(b and b in profile.brands) for b in brands])
    else:
        brand_share = np.zeros(n)
        brand_known = np.zeros(n, dtype=bool)

    if ctx.has_color and "color" in products.columns:
        colours = products["color"].map(lambda v: normalise_color(v))
        color_share = np.array([profile.colors.get(c, 0.0) if c else 0.0 for c in colours])
        color_known = np.array([bool(c and c in profile.colors) for c in colours])
        color_present = np.array([c is not None for c in colours])
        is_neutral = np.array([bool(c in NEUTRAL_COLORS) if c else False for c in colours])
    else:
        colours = pd.Series([None] * n, index=index)
        color_share = np.zeros(n)
        color_known = np.zeros(n, dtype=bool)
        color_present = np.zeros(n, dtype=bool)
        is_neutral = np.zeros(n, dtype=bool)

    if ctx.has_size and "size" in products.columns and profile.sizes:
        best_sizes = sorted(profile.sizes.items(), key=lambda kv: kv[1], reverse=True)[:3]
        distances = []
        for value in products["size"]:
            candidate = [
                d for d in (size_distance(owned, value) for owned, _ in best_sizes)
                if d is not None
            ]
            distances.append(min(candidate) if candidate else np.nan)
        size_dist = np.array(distances, dtype="float64")
    else:
        size_dist = np.full(n, np.nan)

    price = _numeric(products, "price")
    product_gender = np.array([
        (_norm_text(v) or "") for v in products.get("gender", pd.Series([None] * n, index=index))
    ])
    season_fit = _season_month_fit(products, ctx.current_month)
    risk = _numeric(products, "risk_score")
    margin = _numeric(products, "margin_pct")
    days_in_stock = _numeric(products, "days_in_stock")

    product_ids = products["product_id"].astype(str).to_numpy()
    already_bought = np.isin(product_ids, list(profile.purchased_ids)) if profile.purchased_ids \
        else np.zeros(n, dtype=bool)
    repeatable = _is_repeatable(cats)

    signals: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if ctx.has_category:
        signals["category"] = _category_signal(cat_share, cat_known, complement, breadth_array)
    if ctx.has_brand:
        signals["brand"] = _brand_signal(brand_share, brand_known)
    signals["price"] = _price_signal(price, profile.price_low, profile.price_high, profile.price_mid)
    signals["size"] = _size_signal(size_dist)
    if ctx.has_color:
        signals["color"] = _color_signal(color_share, color_known, is_neutral, color_present,
                                         profile.neutral_share)
    signals["pattern"] = _pattern_signal(repeatable, cat_known, already_bought,
                                         profile.recency_days, profile.evidence_lines)
    signals["gender"] = _gender_signal(product_gender, profile.gender)
    signals["season"] = _season_signal(season_fit, np.isfinite(season_fit))
    signals["inventory"] = _inventory_signal(risk, margin)
    signals["novelty"] = _novelty_signal(days_in_stock, already_bought)

    raw, coverage, contributions = _combine(signals, n)
    if "_appeal" in products.columns:
        prior = pd.to_numeric(products["_appeal"], errors="coerce").fillna(NEUTRAL_PRIOR).to_numpy()
    else:
        prior = np.full(n, NEUTRAL_PRIOR)
    score = _shrink(raw, coverage, prior, evidence=profile.evidence_lines)

    return {
        "score": score,
        "raw": raw,
        "coverage": coverage,
        "contributions": contributions,
        "signals": {k: v[0] for k, v in signals.items()},
        "available": {k: v[1] for k, v in signals.items()},
        "categories": cats,
        "colours": colours,
        "size_distance": size_dist,
        "cat_share": cat_share,
        "cat_known": cat_known,
        "brand_share": brand_share,
        "brand_known": brand_known,
        "color_known": color_known,
        "already_bought": already_bought,
        "price": price,
    }


def _result_payload(profile: CustomerProfile, row: pd.Series, scored: dict[str, Any],
                    pos: int, ctx: MatchingContext) -> dict[str, Any]:
    score = float(scored["score"][pos])
    coverage = float(scored["coverage"][pos])

    total_contribution = float(np.nansum([
        scored["contributions"][name][pos] for name in scored["contributions"]
    ]))
    explanation: list[dict[str, Any]] = []
    for name, values in scored["contributions"].items():
        contribution = values[pos]
        if not np.isfinite(contribution):
            continue
        signal_value = float(scored["signals"][name][pos])
        impact = float(contribution / total_contribution * score) if total_contribution > 0 else 0.0
        explanation.append({
            "name": SIGNAL_LABELS[name],
            "key": name,
            "value": round(signal_value, 4),
            "impact": round(impact, 4),
            "direction": "positive" if signal_value >= 0.55 else
                         ("neutral" if signal_value >= 0.42 else "negative"),
            "reason": _reason_for(name, pos, profile, row, scored),
        })
    explanation.sort(key=lambda item: item["impact"], reverse=True)

    missing = [
        SIGNAL_LABELS[name] for name, available in scored["available"].items()
        if not bool(available[pos])
    ]
    # Catalogue-wide gaps never reach the signal loop, so add them explicitly.
    missing += [
        SIGNAL_LABELS[key] for key in ctx.absent_signals
        if SIGNAL_LABELS[key] not in missing
    ]

    return {
        "productId": str(row.get("product_id")),
        "productName": row.get("product_name"),
        "brand": row.get("brand"),
        "category": row.get("category"),
        "color": row.get("color"),
        "size": row.get("size"),
        "price": _clean_number(row.get("price")),
        "stock": _clean_number(row.get("stock")),
        "status": row.get("status"),
        "riskScore": _clean_number(row.get("risk_score")),
        "daysInStock": _clean_number(row.get("days_in_stock")),
        "score": round(score, 4),
        "scorePct": int(round(score * 100)),
        "dataConfidence": _confidence_label(coverage, profile.evidence_lines),
        "signalCoverage": round(coverage, 3),
        "signals": explanation,
        "missingSignals": missing,
        "headline": _headline(explanation, score),
    }


def _reason_for(name: str, pos: int, profile: CustomerProfile, row: pd.Series,
                scored: dict[str, Any]) -> str:
    if name == "category":
        category = row.get("category")
        if bool(scored["cat_known"][pos]):
            share = float(scored["cat_share"][pos])
            return f"{share:.0%} of their spend is in {category}"
        if profile.top_category:
            return (f"New category for them — natural next to {profile.top_category.title()}"
                    if row.get("category") else "New category for this customer")
        return "No category history yet, treated neutrally"
    if name == "brand":
        brand = row.get("brand")
        if bool(scored["brand_known"][pos]):
            share = float(scored["brand_share"][pos])
            return f"Has bought {brand} before ({share:.0%} of spend)"
        return f"{brand} is new to them" if brand else "No brand history"
    if name == "price":
        price = scored["price"][pos]
        if profile.price_low is not None and profile.price_high is not None:
            band = f"€{profile.price_low:,.0f}–€{profile.price_high:,.0f}"
            if np.isfinite(price) and profile.price_low <= price <= profile.price_high:
                return f"€{price:,.0f} sits inside their usual {band} range"
            if np.isfinite(price) and price > profile.price_high:
                return f"€{price:,.0f} is above their usual {band} range"
            return f"€{price:,.0f} is below their usual {band} range"
        if profile.avg_order_value:
            return f"Compared with their €{profile.avg_order_value:,.0f} average basket"
        return "Limited price history"
    if name == "size":
        distance = scored["size_distance"][pos]
        size = row.get("size")
        if np.isfinite(distance) and distance == 0:
            return f"Size {size} matches what they buy"
        if np.isfinite(distance) and distance <= 0.4:
            return f"Size {size} is adjacent to their usual size"
        return f"Size {size} differs from their usual size"
    if name == "color":
        colour = row.get("color")
        if bool(scored["color_known"][pos]):
            return f"{str(colour).title()} is among the colours they buy"
        if profile.neutral_share is not None and profile.neutral_share >= 0.6:
            return f"They favour neutrals ({profile.neutral_share:.0%} of purchases)"
        return f"{str(colour).title()} is outside their usual palette" if colour else "No colour data"
    if name == "pattern":
        if bool(scored["already_bought"][pos]):
            return "They already own this exact product"
        if profile.recency_days is not None:
            return f"Last purchase {int(profile.recency_days)} days ago"
        return "Based on how they typically shop"
    if name == "gender":
        return f"Catalogue line matches their profile ({row.get('gender')})"
    if name == "season":
        fit = float(scored["signals"]["season"][pos]) if "season" in scored["signals"] else 0.5
        season = row.get("season")
        if fit >= 0.7:
            return f"{season} is in season right now"
        return f"{season} is outside the current selling window"
    if name == "inventory":
        risk = row.get("risk_score")
        if risk is not None and not pd.isna(risk) and float(risk) >= 55:
            return f"Stock priority: risk score {float(risk):.0f}/100"
        margin = row.get("margin_pct")
        if margin is not None and not pd.isna(margin):
            return f"Margin {float(margin):.0f}%"
        return "Normal stock priority"
    if name == "novelty":
        days = row.get("days_in_stock")
        if days is not None and not pd.isna(days) and float(days) <= 45:
            return f"New arrival — {int(float(days))} days in store"
        return "Not a new arrival"
    return ""


# Only fit signals can constitute an objection. "Margin 47%" or "not a new
# arrival" are operational facts, not reasons a customer would say no.
_OBJECTION_KEYS = {"category", "brand", "price", "size", "color", "pattern", "gender"}


def _headline(explanation: list[dict[str, Any]], score: float) -> str:
    positives = [s for s in explanation if s["direction"] == "positive"][:2]
    negative = next(
        (s for s in explanation
         if s["direction"] == "negative" and s["key"] in _OBJECTION_KEYS and s["value"] < 0.40),
        None,
    )
    if positives:
        text = " and ".join(s["reason"].lower() for s in positives)
        headline = f"{int(round(score * 100))}% match — {text}"
    else:
        headline = f"{int(round(score * 100))}% match on the signals available"
    if negative:
        headline += f", though {negative['reason'].lower()}"
    return headline[:220]


def _clean_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(number) or np.isinf(number):
        return None
    return round(number, 2)
