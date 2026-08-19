"""Adaptive RFM segmentation.

Fixed thresholds ("VIP = spent over €5,000") break the moment you change
boutique. Instead we score each customer's Recency, Frequency and Monetary
value as a quintile *within this dataset*, then apply readable segment rules on
top. A boutique with a €300 average basket and one with a €3,000 average basket
both get a sensible spread.

Recency is measured against each customer's own cadence when we know it, so a
client who always buys twice a year is not flagged "at risk" in month three.
"""
from __future__ import annotations

from typing import Any

SEGMENTS = [
    "VIP", "Champions", "Loyal", "High Potential", "New", "Promising",
    "At Risk", "Sleeping", "Lost", "Discount Driven", "Unclassified",
]

SEGMENT_META: dict[str, dict[str, str]] = {
    "VIP": {"tone": "positive", "play": "Protect: personal contact, previews, first access."},
    "Champions": {"tone": "positive", "play": "Reward: early access and personal invitations."},
    "Loyal": {"tone": "positive", "play": "Grow basket: cross-sell adjacent categories."},
    "High Potential": {"tone": "positive", "play": "Accelerate: personal styling and new arrivals."},
    "New": {"tone": "neutral", "play": "Onboard: a second purchase within the first 90 days."},
    "Promising": {"tone": "neutral", "play": "Nurture: targeted arrivals in their category."},
    "At Risk": {"tone": "warning", "play": "Recover now: personal outreach before they lapse."},
    "Sleeping": {"tone": "warning", "play": "Reactivate: a strong, relevant reason to return."},
    "Lost": {"tone": "negative", "play": "Low priority: include only in broad campaigns."},
    "Discount Driven": {"tone": "neutral", "play": "Sale-cycle only: avoid full-price outreach."},
    "Unclassified": {"tone": "neutral", "play": "Not enough history to segment reliably."},
}


def _quintile_bounds(values: list[float]) -> list[float]:
    """Cut points at the 20/40/60/80th percentiles of the observed values."""
    ordered = sorted(values)
    if not ordered:
        return []
    return [ordered[min(len(ordered) - 1, int(len(ordered) * q))] for q in (0.2, 0.4, 0.6, 0.8)]


def _score_against(bounds: list[float], value: float, ascending: bool = True) -> int:
    """1..5 where 5 is best. ``ascending`` means bigger value is better."""
    if not bounds:
        return 3
    rank = 1
    for bound in bounds:
        if value > bound:
            rank += 1
    rank = min(5, rank)
    return rank if ascending else 6 - rank


def assign_segments(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach r/f/m scores and a segment label to each profile, in place."""
    scored = [p for p in profiles if p.get("total_spend") is not None or p.get("recency_days") is not None]

    monetary_vals = [p["total_spend"] for p in scored if p.get("total_spend") is not None]
    freq_vals = [p["frequency_per_year"] for p in scored if p.get("frequency_per_year") is not None]
    # Recency is normalised by cadence where possible so cycles differ per customer.
    recency_vals = [_relative_recency(p) for p in scored if _relative_recency(p) is not None]

    m_bounds = _quintile_bounds(monetary_vals)
    f_bounds = _quintile_bounds(freq_vals)
    r_bounds = _quintile_bounds(recency_vals)

    for p in profiles:
        m = _score_against(m_bounds, p["total_spend"], True) if p.get("total_spend") is not None else None
        f = _score_against(f_bounds, p["frequency_per_year"], True) if p.get("frequency_per_year") is not None else None
        rel = _relative_recency(p)
        # Lower relative recency is better, hence ascending=False.
        r = _score_against(r_bounds, rel, False) if rel is not None else None

        p["rfm"] = {"recency": r, "frequency": f, "monetary": m}
        p["rfm_code"] = "".join(str(x) if x else "-" for x in (r, f, m))
        p["segment"] = _segment_for(p, r, f, m)
        p["segment_play"] = SEGMENT_META[p["segment"]]["play"]
        p["segment_tone"] = SEGMENT_META[p["segment"]]["tone"]
    return profiles


def _relative_recency(p: dict[str, Any]) -> float | None:
    """Days since last purchase, expressed in units of that customer's cadence."""
    recency = p.get("recency_days")
    if recency is None:
        return None
    cadence = p.get("cadence_days")
    if cadence and cadence > 0:
        return recency / cadence
    return recency / 120.0  # no cadence known: compare on a common 4-month yardstick


def _segment_for(p: dict[str, Any], r: int | None, f: int | None, m: int | None) -> str:
    if r is None and m is None:
        return "Unclassified"

    orders = p.get("order_count") or 0
    tenure = p.get("tenure_days")
    overdue = p.get("overdue_ratio")
    discount_share = p.get("discount_share")
    value_pct = p.get("value_percentile")

    # Heavy discount buyers are a commercially distinct group regardless of value.
    if discount_share is not None and discount_share >= 0.7 and orders >= 3:
        return "Discount Driven"

    # Genuinely new: short tenure, few orders.
    if tenure is not None and tenure <= 120 and orders <= 2 and (r or 3) >= 3:
        return "New" if orders <= 1 else "Promising"

    top_value = (value_pct is not None and value_pct >= 0.9) or (m == 5)
    good_value = (m or 0) >= 4
    active = (r or 0) >= 4
    lapsing = overdue is not None and overdue >= 1.5
    long_gone = overdue is not None and overdue >= 3

    if top_value and active and (f or 0) >= 4:
        return "VIP"
    if top_value and long_gone:
        return "Lost" if (r or 3) <= 1 else "At Risk"
    if good_value and active and (f or 0) >= 3:
        return "Champions"
    if (f or 0) >= 4 and active:
        return "Loyal"
    if good_value and lapsing:
        return "At Risk"
    if (m or 0) >= 3 and (f or 0) <= 2 and active:
        return "High Potential"
    if long_gone:
        return "Lost"
    if lapsing:
        return "Sleeping"
    if active:
        return "Promising"
    return "Sleeping" if (r or 3) >= 2 else "Lost"


def segment_summary(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-segment counts and value, ordered by commercial importance."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for p in profiles:
        buckets.setdefault(p.get("segment", "Unclassified"), []).append(p)

    out = []
    for name in SEGMENTS:
        members = buckets.get(name)
        if not members:
            continue
        spends = [m["total_spend"] for m in members if m.get("total_spend") is not None]
        potential = [m["potential_annual_value"] for m in members if m.get("potential_annual_value")]
        out.append({
            "segment": name,
            "customers": len(members),
            "share": round(len(members) / max(1, len(profiles)), 3),
            "total_value": round(sum(spends), 2) if spends else None,
            "avg_value": round(sum(spends) / len(spends), 2) if spends else None,
            "annual_potential": round(sum(potential), 2) if potential else None,
            "tone": SEGMENT_META[name]["tone"],
            "play": SEGMENT_META[name]["play"],
        })
    return out
