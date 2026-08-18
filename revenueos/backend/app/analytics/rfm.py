"""Adaptive RFM scoring and segmentation.

Fixed thresholds ("VIP = spent more than €5,000") break the moment the product
meets a different boutique. RevenueOS instead derives every cut point from the
dataset's own distribution:

* scores are quantile ranks (quintiles when there is enough data, fewer bins
  when there is not, so a 30-customer boutique still gets meaningful spread);
* the recency axis is measured in *repurchase cycles*, i.e. relative to each
  customer's own rhythm where known, and to the base median otherwise.

Segments are then assigned by rules over those relative scores, which keeps the
labels meaningful for a €200-average streetwear store and a €4,000-average
luxury boutique alike.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

SEGMENTS = (
    "Champions",
    "VIP",
    "Loyal",
    "High Potential",
    "Promising",
    "New",
    "At Risk",
    "Sleeping",
    "Lost",
    "Discount Driven",
)

SEGMENT_META: dict[str, dict[str, str]] = {
    "Champions": {
        "tone": "positive",
        "description": "Buy often, spend the most, and bought recently. Your core revenue.",
        "play": "Protect the relationship: early access, personal invitations, no discounting.",
    },
    "VIP": {
        "tone": "positive",
        "description": "Highest lifetime value, still active. Fewer visits than Champions but bigger baskets.",
        "play": "Private appointments and first look at new arrivals in their preferred brands.",
    },
    "Loyal": {
        "tone": "positive",
        "description": "Consistent, reliable repeat customers at a moderate value level.",
        "play": "Grow basket size with cross-category suggestions.",
    },
    "High Potential": {
        "tone": "opportunity",
        "description": "Spending well above average for how long they have been customers.",
        "play": "Invest attention now — these are your next VIPs.",
    },
    "Promising": {
        "tone": "opportunity",
        "description": "Recent buyers with a good first basket, not yet a habit.",
        "play": "Convert to a second purchase within their normal window.",
    },
    "New": {
        "tone": "neutral",
        "description": "Bought for the first time recently. Behaviour not yet established.",
        "play": "Welcome follow-up and a styling suggestion to build the habit.",
    },
    "At Risk": {
        "tone": "warning",
        "description": "Valuable customers who are now past their usual repurchase window.",
        "play": "Personal outreach with a specific product, not a generic promo.",
    },
    "Sleeping": {
        "tone": "warning",
        "description": "Have not bought for a long time relative to the base, but were engaged.",
        "play": "Reactivation with a strong reason to return.",
    },
    "Lost": {
        "tone": "negative",
        "description": "Long inactive with low historical value. Low expected return on effort.",
        "play": "Include in broad campaigns only; do not spend one-to-one time.",
    },
    "Discount Driven": {
        "tone": "neutral",
        "description": "Buy repeatedly, but almost always on markdown.",
        "play": "Target with end-of-season and private sale events, never full price.",
    },
}


@dataclass
class RFMConfig:
    bins: int
    recency_days_median: float | None
    monetary_median: float | None
    frequency_median: float | None


def _quantile_score(series: pd.Series, bins: int, ascending: bool = True) -> pd.Series:
    """Rank a metric into 1..bins. Higher is always better after inversion."""
    valid = series.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=series.index)
    if valid.nunique() == 1:
        return pd.Series(np.nan, index=series.index).fillna(
            float((bins + 1) / 2)
        ).where(series.notna())

    ranked = series.rank(method="average", pct=True, ascending=ascending)
    scores = np.ceil(ranked * bins)
    scores = scores.clip(lower=1, upper=bins)
    return scores.where(series.notna())


def _choose_bins(n: int) -> int:
    if n >= 250:
        return 5
    if n >= 80:
        return 4
    if n >= 25:
        return 3
    return 2


def compute_rfm(metrics: pd.DataFrame, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """Attach R/F/M scores and a segment to a customer-metrics frame.

    Expected (all optional except ``customer_id``):
    ``recency_days``, ``order_count``, ``total_spend``, ``expected_cycle_days``,
    ``discount_rate``, ``tenure_days``.
    """
    if metrics.empty:
        return metrics.assign(
            r_score=pd.Series(dtype=float), f_score=pd.Series(dtype=float),
            m_score=pd.Series(dtype=float), rfm_score=pd.Series(dtype=float),
            segment=pd.Series(dtype=object), segment_reason=pd.Series(dtype=object),
        )

    frame = metrics.copy()
    n = len(frame)
    bins = _choose_bins(n)

    # Recency is ranked on *cycles overdue* when we know each customer's own
    # rhythm: 120 days is alarming for someone who buys monthly and completely
    # normal for someone who buys twice a year. Raw days are the fallback.
    recency = frame.get("recency_days")
    cycles = frame.get("cycles_overdue")
    if cycles is not None and cycles.notna().mean() >= 0.6:
        recency_axis = cycles
    else:
        recency_axis = recency
    frequency = frame.get("order_count")
    monetary = frame.get("total_spend")

    # Recency: fewer days / fewer cycles overdue = better, so rank and invert.
    frame["r_score"] = (
        _quantile_score(recency_axis, bins, ascending=False)
        if recency_axis is not None else np.nan
    )
    frame["f_score"] = (
        _quantile_score(frequency, bins, ascending=True) if frequency is not None else np.nan
    )
    frame["m_score"] = (
        _quantile_score(monetary, bins, ascending=True) if monetary is not None else np.nan
    )

    # Normalise each axis to 0..1 so a 3-bin dataset is comparable to a 5-bin one.
    for axis in ("r", "f", "m"):
        col = f"{axis}_score"
        frame[f"{axis}_norm"] = (frame[col] - 1) / max(bins - 1, 1)

    available = [f"{a}_norm" for a in ("r", "f", "m") if frame[f"{a}_norm"].notna().any()]
    if available:
        frame["rfm_score"] = frame[available].mean(axis=1, skipna=True)
    else:
        frame["rfm_score"] = np.nan

    segments, reasons = _assign_segments(frame, bins)
    frame["segment"] = segments
    frame["segment_reason"] = reasons
    return frame


def _assign_segments(frame: pd.DataFrame, bins: int) -> tuple[list[str], list[str]]:
    """Rule set over *relative* scores, plus behavioural overrides."""
    r = frame.get("r_norm")
    f = frame.get("f_norm")
    m = frame.get("m_norm")
    tenure = frame.get("tenure_days")
    orders = frame.get("order_count")
    discount = frame.get("discount_rate")
    overdue = frame.get("cycles_overdue")

    segments: list[str] = []
    reasons: list[str] = []

    for idx in frame.index:
        rv = _val(r, idx)
        fv = _val(f, idx)
        mv = _val(m, idx)
        tenure_days = _val(tenure, idx)
        order_count = _val(orders, idx)
        discount_rate = _val(discount, idx)
        cycles_overdue = _val(overdue, idx)

        value = _mean_available(mv, fv)
        engagement = rv

        # --- behavioural overrides first --- #
        if (discount_rate is not None and discount_rate >= 0.55
                and order_count is not None and order_count >= 3):
            segments.append("Discount Driven")
            reasons.append(
                f"{discount_rate:.0%} of purchases were discounted across "
                f"{int(order_count)} orders"
            )
            continue

        if (order_count is not None and order_count <= 1
                and tenure_days is not None and tenure_days <= 120):
            segments.append("New")
            reasons.append(
                f"First purchase {int(tenure_days)} days ago, no repeat yet"
            )
            continue

        if engagement is None and value is None:
            segments.append("New")
            reasons.append("Not enough history to place this customer yet")
            continue

        # --- main grid --- #
        high_value = value is not None and value >= 0.7
        mid_value = value is not None and 0.4 <= value < 0.7
        recent = engagement is not None and engagement >= 0.6
        stale = engagement is not None and engagement <= 0.25
        drifting = engagement is not None and 0.25 < engagement < 0.6

        if high_value and recent:
            if fv is not None and fv >= 0.8:
                segments.append("Champions")
                reasons.append("Top-tier spend and frequency, bought recently")
            else:
                segments.append("VIP")
                reasons.append("Top-tier lifetime value and still active")
        elif high_value and drifting:
            segments.append("At Risk")
            reasons.append(
                f"High value but {int(cycles_overdue * 100)}% past their usual window"
                if cycles_overdue is not None
                else "High value but slowing down"
            )
        elif high_value and stale:
            segments.append("Sleeping")
            reasons.append("Was a high-value customer, now long inactive")
        elif mid_value and recent:
            if (tenure_days is not None and tenure_days <= 365
                    and mv is not None and mv >= 0.55):
                segments.append("High Potential")
                reasons.append("Spending above average for a relatively new customer")
            else:
                segments.append("Loyal")
                reasons.append("Steady repeat customer at a solid value level")
        elif mid_value and drifting:
            segments.append("At Risk")
            reasons.append("Established customer drifting past their normal rhythm")
        elif mid_value and stale:
            segments.append("Sleeping")
            reasons.append("No activity for a long stretch relative to your base")
        elif recent:
            if order_count is not None and order_count >= 2:
                segments.append("Promising")
                reasons.append("Recent repeat buyer, value still building")
            else:
                segments.append("New")
                reasons.append("Recent first purchase")
        elif drifting:
            segments.append("Sleeping")
            reasons.append("Low value and no recent activity")
        else:
            segments.append("Lost")
            reasons.append("Long inactive with low historical value")

    return segments, reasons


def _val(series: pd.Series | None, idx) -> float | None:
    if series is None:
        return None
    try:
        value = series.loc[idx]
    except (KeyError, TypeError):
        return None
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean_available(*values: float | None) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def segment_summary(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Aggregate per-segment stats for the UI, ordered by revenue contribution."""
    if frame.empty or "segment" not in frame.columns:
        return []
    rows: list[dict[str, Any]] = []
    total_spend = frame["total_spend"].sum(skipna=True) if "total_spend" in frame else 0.0
    for name, group in frame.groupby("segment"):
        spend = float(group["total_spend"].sum(skipna=True)) if "total_spend" in group else None
        meta = SEGMENT_META.get(str(name), {})
        rows.append({
            "segment": str(name),
            "customers": int(len(group)),
            "totalSpend": round(spend, 2) if spend is not None else None,
            "shareOfRevenue": round(spend / total_spend, 4) if spend and total_spend else None,
            "avgSpend": _safe_mean(group, "total_spend"),
            "avgOrders": _safe_mean(group, "order_count"),
            "avgRecencyDays": _safe_mean(group, "recency_days"),
            "tone": meta.get("tone", "neutral"),
            "description": meta.get("description", ""),
            "play": meta.get("play", ""),
        })
    rows.sort(key=lambda r: (r["totalSpend"] or 0), reverse=True)
    return rows


def _safe_mean(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns:
        return None
    values = frame[column].dropna()
    if values.empty:
        return None
    return round(float(values.mean()), 2)
