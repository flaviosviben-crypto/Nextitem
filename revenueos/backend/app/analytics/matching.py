"""Customer × product matching.

The rule that fixes the old engine's "0% match" bug:

    A signal we cannot measure is *excluded from the average*, not scored zero.

Each signal declares whether it is applicable for this (customer, product) pair.
Only applicable signals contribute, and their weights are renormalised to sum to
1. So a boutique with no colour data does not get systematically depressed
scores — it gets the same scale with fewer inputs, and a lower *data confidence*,
which is reported separately from the match score.

Hard gates (out of stock, wrong gender) exclude a product from consideration
entirely rather than silently dragging its score down.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from . import taxonomy

# Nominal weights. These are renormalised across whichever signals apply.
BASE_WEIGHTS: dict[str, float] = {
    "category": 0.25,
    "brand": 0.15,
    "price": 0.15,
    "size": 0.15,
    "color": 0.10,
    "pattern": 0.10,
    "inventory_priority": 0.05,
    "novelty": 0.05,
}

# A match built on almost nothing should not look authoritative.
_CONFIDENCE_BANDS = ((0.75, "High"), (0.45, "Medium"))

# Signals that describe the customer's relationship to the product. At least one
# must be measurable or there is no customer-specific match to report.
_CUSTOMER_SIGNALS = {"category", "brand", "price", "size", "color", "pattern"}


@dataclass
class Signal:
    name: str
    label: str
    applicable: bool
    score: float          # 0..1, only meaningful when applicable
    reason: str
    weight: float = 0.0   # filled in after renormalisation
    impact: float = 0.0   # weight * score, i.e. contribution to the final number

    def to_dict(self) -> dict[str, Any]:
        # Four decimals so the displayed breakdown reconciles with the displayed
        # score — a signal table that does not add up destroys trust.
        return {
            "name": self.name,
            "label": self.label,
            "score": round(self.score, 4),
            "weight": round(self.weight, 4),
            "impact": round(self.impact, 4),
            "reason": self.reason,
            "applicable": self.applicable,
        }


def _na(name: str, label: str, reason: str) -> Signal:
    return Signal(name, label, False, 0.0, reason)


# ---------------------------------------------------------------- signals ----

def _category_signal(cust: dict, prod: dict) -> Signal:
    affinity: dict[str, float] = cust.get("category_affinity") or {}
    prod_cat = prod.get("category")
    if not prod_cat:
        return _na("category", "Category fit", "Product has no category recorded")
    if not affinity:
        return _na("category", "Category fit", "No category history for this customer")

    best_score, best_label, best_share = 0.0, None, 0.0
    for label, share in affinity.items():
        compat = taxonomy.compatibility(label, prod_cat)
        if compat <= 0:
            continue
        # A strong preference in a related family beats a weak one in the same.
        value = compat * (0.55 + 0.45 * min(1.0, share / 0.5))
        if value > best_score:
            best_score, best_label, best_share = value, label, share

    if best_label is None:
        top = next(iter(affinity))
        return Signal("category", "Category fit", True, 0.05,
                      f"{taxonomy.describe(prod_cat)} is unrelated to their usual {top}")

    if taxonomy.compatibility(best_label, prod_cat) >= 0.9:
        reason = (f"{best_label} is {best_share:.0%} of their spend"
                  if best_share >= 0.15 else f"They have bought {best_label} before")
    else:
        reason = f"Complements the {best_label} they already buy"
    return Signal("category", "Category fit", True, min(1.0, best_score), reason)


def _brand_signal(cust: dict, prod: dict) -> Signal:
    affinity: dict[str, float] = cust.get("brand_affinity") or {}
    brand = prod.get("brand")
    if not brand:
        return _na("brand", "Brand fit", "Product has no brand recorded")
    if not affinity:
        return _na("brand", "Brand fit", "No brand history for this customer")

    key = str(brand).strip().lower()
    for label, share in affinity.items():
        if str(label).strip().lower() == key:
            score = min(1.0, 0.62 + 0.38 * min(1.0, share / 0.4))
            return Signal("brand", "Brand fit", True, score,
                          f"{brand} is {share:.0%} of their spend")
    top = next(iter(affinity))
    return Signal("brand", "Brand fit", True, 0.32,
                  f"New brand for them — they usually buy {top}")


def _price_signal(cust: dict, prod: dict) -> Signal:
    price = prod.get("price")
    if not price or price <= 0:
        return _na("price", "Price fit", "Product has no price recorded")
    low, high = cust.get("price_low"), cust.get("price_high")
    median = cust.get("price_median")
    if median is None:
        return _na("price", "Price fit", "No spending history to compare against")

    money = f"€{price:,.0f}"
    band = f"€{low:,.0f}–€{high:,.0f}" if low and high else None
    if low and high and low <= price <= high:
        return Signal("price", "Price fit", True, 0.95, f"{money} sits inside their usual {band}")

    ratio = price / median if median else 1.0
    if ratio > 1:
        # Stretching upward is a real opportunity, but a 3× jump is a stretch.
        score = max(0.15, 1.0 - (ratio - 1) * 0.55)
        direction = f"{money} is above their typical {band or f'€{median:,.0f}'}"
        if ratio <= 1.35:
            direction += " — a natural step up"
    else:
        score = max(0.25, 1.0 - (1 - ratio) * 0.7)
        direction = f"{money} is below their typical {band or f'€{median:,.0f}'}"
    return Signal("price", "Price fit", True, min(1.0, score), direction)


def _size_signal(cust: dict, prod: dict) -> Signal:
    prod_size = prod.get("size")
    if not prod_size:
        return _na("size", "Size availability", "Product has no size recorded")

    # Compare like with like: a customer's knitwear size says nothing about shoes.
    family = taxonomy.family_of(prod.get("category"))
    by_family: dict[str, dict[str, float]] = cust.get("size_affinity_by_family") or {}
    sizes = by_family.get(family) if family else None
    scope = family
    if not sizes:
        if by_family:
            return _na("size", "Size availability",
                       f"No {family or 'matching'} size history for this customer")
        sizes = cust.get("size_affinity") or {}
        scope = None
    if not sizes:
        return _na("size", "Size availability", "No size history for this customer")

    key = str(prod_size).strip().upper()
    known = {str(s).strip().upper(): share for s, share in sizes.items()}
    where = f" in {scope.lower()}" if scope else ""
    if key in known:
        return Signal("size", "Size availability", True, 1.0,
                      f"Usually buys size {prod_size}{where}")
    if key == "ONE SIZE":
        return Signal("size", "Size availability", True, 0.85, "One size — fits regardless")
    return Signal("size", "Size availability", True, 0.12,
                  f"Available in {prod_size}, but they buy {', '.join(list(known)[:2])}{where}")


def _color_signal(cust: dict, prod: dict) -> Signal:
    color = prod.get("color")
    affinity: dict[str, float] = cust.get("color_affinity") or {}
    if not color:
        return _na("color", "Colour fit", "Product has no colour recorded")
    if not affinity:
        return _na("color", "Colour fit", "No colour history for this customer")
    key = str(color).strip().lower()
    for label, share in affinity.items():
        if str(label).strip().lower() == key:
            return Signal("color", "Colour fit", True, min(1.0, 0.7 + share),
                          f"{color} is a colour they repeatedly choose")
    top = next(iter(affinity))
    return Signal("color", "Colour fit", True, 0.4, f"They lean towards {top}")


def _pattern_signal(cust: dict, prod: dict) -> Signal:
    """Do this customer's buying habits suggest they are due for this kind of item?"""
    orders = cust.get("order_count") or 0
    if orders < 2:
        return _na("pattern", "Buying pattern", "Not enough purchase history")

    overdue = cust.get("overdue_ratio")
    cadence = cust.get("cadence_days")
    if overdue is None or cadence is None:
        return _na("pattern", "Buying pattern", "No repurchase cadence established")

    if 0.75 <= overdue <= 1.6:
        return Signal("pattern", "Buying pattern", True, 0.95,
                      f"They buy about every {cadence:.0f} days and are due now")
    if overdue < 0.75:
        return Signal("pattern", "Buying pattern", True, 0.45,
                      f"Bought recently — next purchase typically in {cadence:.0f} days")
    return Signal("pattern", "Buying pattern", True, 0.7,
                  f"{overdue:.1f}× past their usual {cadence:.0f}-day cycle — overdue")


def _inventory_signal(cust: dict, prod: dict) -> Signal:
    risk = prod.get("risk_class")
    if not risk or risk == "Unknown":
        return _na("inventory_priority", "Inventory priority", "No stock performance data")
    scores = {"Dead Stock": 1.0, "At Risk": 0.85, "Slow Moving": 0.65, "Healthy": 0.4, "Hot": 0.25}
    reasons = {
        "Dead Stock": "Clearing this frees capital — high priority to move",
        "At Risk": "Ageing stock the boutique should push now",
        "Slow Moving": "Could use a nudge",
        "Healthy": "Selling normally",
        "Hot": "Already selling well without help",
    }
    return Signal("inventory_priority", "Inventory priority", True,
                  scores.get(risk, 0.4), reasons.get(risk, "Selling normally"))


def _novelty_signal(cust: dict, prod: dict) -> Signal:
    purchased = set(cust.get("purchased_skus") or [])
    if not purchased:
        return _na("novelty", "Newness", "No SKU-level purchase history")
    if str(prod.get("sku")) in purchased:
        return Signal("novelty", "Newness", True, 0.1, "They already own this exact item")
    return Signal("novelty", "Newness", True, 1.0, "New piece for this customer")


SIGNAL_BUILDERS: dict[str, Callable[[dict, dict], Signal]] = {
    "category": _category_signal,
    "brand": _brand_signal,
    "price": _price_signal,
    "size": _size_signal,
    "color": _color_signal,
    "pattern": _pattern_signal,
    "inventory_priority": _inventory_signal,
    "novelty": _novelty_signal,
}


# ------------------------------------------------------------------ gates ----

def _gate(cust: dict, prod: dict, require_stock: bool) -> str | None:
    """Return a reason to exclude this product entirely, or ``None`` to keep it."""
    stock = prod.get("stock")
    if require_stock and stock is not None and stock <= 0:
        return "Out of stock"

    pg, cg = prod.get("gender"), cust.get("gender")
    if pg and cg:
        p, c = str(pg).strip().lower()[:1], str(cg).strip().lower()[:1]
        unisex = str(pg).strip().lower() in {"unisex", "u", "all", "uni"}
        if not unisex and p in {"m", "u", "d", "f", "w"} and c in {"m", "u", "d", "f", "w"}:
            male = {"m", "u"}          # 'u' = uomo (IT)
            female = {"f", "w", "d"}   # 'd' = donna (IT)
            if (p in male and c in female) or (p in female and c in male):
                return "Different gender line"
    return None


# ------------------------------------------------------------------ score ----

def score_pair(
    customer: dict[str, Any],
    product: dict[str, Any],
    require_stock: bool = True,
) -> dict[str, Any] | None:
    """Score one customer × product pair. ``None`` means the product is gated out."""
    blocked = _gate(customer, product, require_stock)
    if blocked:
        return None

    signals = [SIGNAL_BUILDERS[name](customer, product) for name in BASE_WEIGHTS]
    applicable = [s for s in signals if s.applicable]
    if not applicable:
        return None  # nothing at all to go on: do not invent a number

    # A match must say something about *this customer*. Inventory priority and
    # newness describe the product alone, so on their own they are not a match.
    if not any(s.name in _CUSTOMER_SIGNALS for s in applicable):
        return None

    # --- the fix: renormalise weights over applicable signals only ---
    live_weight = sum(BASE_WEIGHTS[s.name] for s in applicable)
    for s in applicable:
        s.weight = BASE_WEIGHTS[s.name] / live_weight
        s.impact = s.weight * s.score

    raw = sum(s.impact for s in applicable)

    # Category coherence gate. Price, stock and timing must never carry a product
    # from an unrelated category to the top — the boutique would immediately see
    # the recommendation as nonsense. Weak category fit caps the whole match.
    category_signal = next((s for s in applicable if s.name == "category"), None)
    if category_signal is not None and category_signal.score < 0.3:
        ceiling = 0.25 + category_signal.score
        if raw > ceiling:
            raw = ceiling
            for s in applicable:
                s.impact = s.weight * s.score * (ceiling / max(1e-9, sum(
                    x.weight * x.score for x in applicable)))

    # Data confidence reflects how much of the nominal model we could actually run.
    coverage = live_weight / sum(BASE_WEIGHTS.values())
    history = customer.get("transaction_count") or 0
    depth = min(1.0, history / 6.0)
    confidence_value = 0.65 * coverage + 0.35 * depth
    confidence = "Low"
    for threshold, label in _CONFIDENCE_BANDS:
        if confidence_value >= threshold:
            confidence = label
            break

    ranked = sorted(applicable, key=lambda s: -s.impact)
    positives = [s for s in ranked if s.score >= 0.6][:4]
    negatives = [s for s in ranked if s.score < 0.35][:2]

    return {
        "sku": product.get("sku"),
        "product_name": product.get("product_name"),
        "category": product.get("category"),
        "brand": product.get("brand"),
        "price": product.get("price"),
        "stock": product.get("stock"),
        "risk_class": product.get("risk_class"),
        "customer_id": customer.get("customer_id"),
        "customer_name": customer.get("name"),
        "score": round(raw, 4),
        "match_pct": int(round(raw * 100)),
        "data_confidence": confidence,
        "coverage": round(coverage, 3),
        "signals": [s.to_dict() for s in signals],
        "why": [s.reason for s in positives],
        "caveats": [s.reason for s in negatives],
        "missing_signals": [s.label for s in signals if not s.applicable],
    }


def best_products_for_customer(
    customer: dict[str, Any],
    products: list[dict[str, Any]],
    limit: int = 8,
    require_stock: bool = True,
    min_score: float = 0.35,
) -> list[dict[str, Any]]:
    scored = [score_pair(customer, p, require_stock) for p in products]
    live = [m for m in scored if m and m["score"] >= min_score]
    live.sort(key=lambda m: (-m["score"], -(m.get("price") or 0)))

    # An advisor wants options, not the same piece three times. Keep the best of
    # each product name first, then backfill if that leaves the list short.
    seen: set[str] = set()
    distinct: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    for match in live:
        key = str(match.get("product_name") or match["sku"]).strip().lower()
        if key in seen:
            duplicates.append(match)
        else:
            seen.add(key)
            distinct.append(match)
    return (distinct + duplicates)[:limit]


def best_customers_for_product(
    product: dict[str, Any],
    customers: list[dict[str, Any]],
    limit: int = 10,
    require_stock: bool = False,
    consented_only: bool = False,
    min_score: float = 0.4,
) -> list[dict[str, Any]]:
    # Eligibility is resolved once, by the compliance layer; matching just honours it.
    pool = [c for c in customers if not consented_only or c.get("contactable")]
    scored = [score_pair(c, product, require_stock) for c in pool]
    live = [m for m in scored if m and m["score"] >= min_score]
    live.sort(key=lambda m: -m["score"])
    return live[:limit]


def expected_value(match: dict[str, Any], customer: dict[str, Any]) -> float | None:
    """Expected revenue if we act on this match: price × conversion likelihood."""
    price = match.get("price")
    if not price:
        price = customer.get("avg_order_value")
    if not price:
        return None
    # Match score maps to a deliberately conservative conversion band (4%–32%).
    probability = 0.04 + 0.28 * min(1.0, match["score"])
    if not customer.get("contactable"):
        probability *= 0.6      # no permitted channel: only a shop-floor encounter
    return round(price * probability, 2)
