"""Customer metrics computed from real transactions, with CRM fallbacks.

Two paths run through this module:

* **Transaction-derived** (preferred): every metric is recomputed from the sales
  ledger, which also yields affinities, timelines and a personal repurchase
  rhythm.
* **CRM-summary fallback**: when no transaction history exists we use whatever
  the CRM export carried (total spend, order count, last purchase). Metrics
  that cannot be derived stay ``None`` — they are never faked as ``0``.

Every returned record carries a ``dataConfidence`` describing how much of the
profile is evidence versus inference, which the UI shows next to any score.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..data.parsing import is_neutral_color

# Weights of the composite customer score. They are redistributed across the
# components that are actually computable for each customer.
SCORE_WEIGHTS = {
    "monetary": 0.34,
    "frequency": 0.22,
    "recency": 0.22,
    "trajectory": 0.12,
    "breadth": 0.10,
}


def _norm_rank(series: pd.Series, ascending: bool = True) -> pd.Series:
    """Percentile rank in 0..1, NaN-safe. Used to keep scores dataset-relative."""
    valid = series.dropna()
    if valid.empty:
        return pd.Series(np.nan, index=series.index)
    if valid.nunique() == 1:
        return pd.Series(0.5, index=series.index).where(series.notna())
    return series.rank(pct=True, ascending=ascending).where(series.notna())


def _top_shares(values: pd.Series, weights: pd.Series | None = None,
                limit: int = 5) -> list[dict[str, Any]]:
    """Weighted share of a categorical dimension, e.g. category → 42% of spend."""
    mask = values.notna() & (values.astype(str).str.strip() != "")
    if not mask.any():
        return []
    vals = values[mask].astype(str)
    if weights is not None:
        w = weights[mask].fillna(0.0)
        if w.sum() <= 0:
            w = pd.Series(1.0, index=vals.index)
    else:
        w = pd.Series(1.0, index=vals.index)
    grouped = w.groupby(vals).sum().sort_values(ascending=False)
    total = grouped.sum()
    if total <= 0:
        return []
    return [
        {"value": str(name), "share": round(float(amount / total), 4),
         "weight": round(float(amount), 2)}
        for name, amount in grouped.head(limit).items()
    ]


def _percentile_band(values: pd.Series) -> tuple[float, float] | None:
    clean = values.dropna()
    clean = clean[clean > 0]
    if len(clean) == 0:
        return None
    if len(clean) == 1:
        only = float(clean.iloc[0])
        return (round(only * 0.75, 2), round(only * 1.3, 2))
    low = float(clean.quantile(0.15))
    high = float(clean.quantile(0.85))
    if high <= low:
        high = low * 1.25 + 1
    return (round(low, 2), round(high, 2))


def build_customer_metrics(
    customers: pd.DataFrame,
    transactions: pd.DataFrame | None,
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Return one row per customer with every derivable behavioural metric."""
    as_of = as_of or pd.Timestamp.now().normalize()

    base = customers.copy() if customers is not None else pd.DataFrame()
    if base.empty and (transactions is None or transactions.empty):
        return pd.DataFrame()

    has_tx = (
        transactions is not None
        and not transactions.empty
        and "customer_id" in transactions.columns
        and transactions["customer_id"].notna().any()
    )

    if base.empty and has_tx:
        ids = transactions["customer_id"].dropna().astype(str).unique()
        base = pd.DataFrame({"customer_id": ids})
        base["display_name"] = [f"Customer {i}" for i in ids]
    else:
        base = base.copy()
        base["customer_id"] = base["customer_id"].astype(str)
        if has_tx:
            # customers that appear only in transactions still deserve a profile
            known = set(base["customer_id"])
            extra = [
                cid for cid in transactions["customer_id"].dropna().astype(str).unique()
                if cid not in known
            ]
            if extra:
                addition = pd.DataFrame({"customer_id": extra})
                addition["display_name"] = [f"Customer {i}" for i in extra]
                for col in base.columns:
                    if col not in addition.columns:
                        addition[col] = None
                base = pd.concat([base, addition[base.columns]], ignore_index=True)

    base = base.reset_index(drop=True)
    base["customer_id"] = base["customer_id"].astype(str)

    derived = (
        _from_transactions(base["customer_id"], transactions, as_of)
        if has_tx else pd.DataFrame(index=base.index)
    )

    metrics = base.merge(derived, on="customer_id", how="left") if not derived.empty else base
    metrics = _merge_crm_fallbacks(metrics, as_of)
    metrics = _derive_scores(metrics, as_of, has_tx)
    return metrics


# --------------------------------------------------------------------------- #
# transaction-derived metrics
# --------------------------------------------------------------------------- #
def _from_transactions(customer_ids: pd.Series, transactions: pd.DataFrame,
                       as_of: pd.Timestamp) -> pd.DataFrame:
    tx = transactions.copy()
    tx = tx[tx["customer_id"].notna()]
    tx["customer_id"] = tx["customer_id"].astype(str)
    if tx.empty:
        return pd.DataFrame()

    has_date = "date" in tx.columns and tx["date"].notna().any()
    has_amount = "net_amount" in tx.columns and tx["net_amount"].notna().any()

    records: list[dict[str, Any]] = []
    for cid, group in tx.groupby("customer_id", sort=False):
        record: dict[str, Any] = {"customer_id": cid, "tx_lines": int(len(group))}

        # ---- orders ---- #
        if "transaction_id" in group.columns and group["transaction_id"].notna().any():
            order_keys = group["transaction_id"].dropna().astype(str)
            record["order_count"] = int(order_keys.nunique())
        elif has_date:
            record["order_count"] = int(group["date"].dropna().dt.date.nunique() or len(group))
        else:
            record["order_count"] = int(len(group))

        # ---- money ---- #
        if has_amount:
            amounts = group["net_amount"].dropna()
            if not amounts.empty:
                record["total_spend"] = float(amounts.sum())
                record["units"] = float(group["quantity"].fillna(1).sum()) if "quantity" in group else float(len(group))
                if record["order_count"]:
                    record["avg_order_value"] = float(record["total_spend"] / record["order_count"])
                record["max_line_value"] = float(amounts.max())
                band = _percentile_band(_line_unit_prices(group))
                if band:
                    record["price_band_low"], record["price_band_high"] = band
                    record["price_band_mid"] = round((band[0] + band[1]) / 2, 2)

        # ---- timing ---- #
        if has_date:
            dates = group["date"].dropna().sort_values()
            if not dates.empty:
                record["last_purchase_date"] = dates.max()
                record["first_purchase_date"] = dates.min()
                record["recency_days"] = float((as_of - dates.max()).days)
                record["tenure_days"] = float((as_of - dates.min()).days)
                order_days = pd.Series(sorted(set(dates.dt.normalize())))
                if len(order_days) >= 2:
                    gaps = order_days.diff().dropna().dt.days
                    gaps = gaps[gaps > 0]
                    if not gaps.empty:
                        record["avg_gap_days"] = float(gaps.mean())
                        record["median_gap_days"] = float(gaps.median())
                        record["gap_std_days"] = float(gaps.std(ddof=0)) if len(gaps) > 1 else 0.0
                        record["purchase_regularity"] = _regularity(gaps)
                # spend trajectory: last 180 days vs the 180 before that
                if has_amount:
                    record.update(_trajectory(group, as_of))
                    record["seasonality"] = _seasonality(group)

        # ---- affinities ---- #
        weights = group["net_amount"] if has_amount else None
        for column, key in (("category", "category_affinity"),
                            ("brand", "brand_affinity"),
                            ("color", "color_affinity"),
                            ("size", "size_affinity")):
            if column in group.columns:
                shares = _top_shares(group[column], weights)
                if shares:
                    record[key] = shares

        if "product_id" in group.columns:
            record["purchased_product_ids"] = [
                str(v) for v in group["product_id"].dropna().astype(str).unique()
            ]

        # ---- discount behaviour ---- #
        if "discount" in group.columns and group["discount"].notna().any():
            discounts = group["discount"].fillna(0)
            discounted_lines = (discounts > 0).mean()
            record["discount_rate"] = float(discounted_lines)
            positive = discounts[discounts > 0]
            if not positive.empty:
                # normalise: a value >1 is an absolute amount, <=1 a fraction
                as_pct = positive.where(positive <= 100, other=np.nan)
                if as_pct.notna().any():
                    mean_pct = float(as_pct.mean())
                    record["avg_discount_pct"] = mean_pct if mean_pct > 1 else mean_pct * 100
        elif has_amount and "unit_price" in group.columns and group["unit_price"].notna().any():
            paid = group["net_amount"]
            listed = group["unit_price"] * group["quantity"].fillna(1)
            comparable = listed.notna() & paid.notna() & (listed > 0)
            if comparable.any():
                ratio = (paid[comparable] / listed[comparable]).clip(0, 2)
                record["discount_rate"] = float((ratio < 0.97).mean())
                below = ratio[ratio < 0.97]
                if not below.empty:
                    record["avg_discount_pct"] = float((1 - below.mean()) * 100)

        if "color" in group.columns and group["color"].notna().any():
            colours = group["color"].dropna()
            if len(colours):
                record["neutral_color_share"] = float(
                    colours.map(is_neutral_color).mean()
                )

        if "store" in group.columns and group["store"].notna().any():
            top = _top_shares(group["store"], weights, limit=1)
            if top:
                record["primary_store"] = top[0]["value"]

        records.append(record)

    frame = pd.DataFrame(records)
    return frame


def _line_unit_prices(group: pd.DataFrame) -> pd.Series:
    """Per-unit price actually paid, used for the customer's price band."""
    if "net_amount" not in group.columns:
        return pd.Series(dtype="float64")
    amount = group["net_amount"]
    qty = group["quantity"].fillna(1) if "quantity" in group.columns else pd.Series(1.0, index=group.index)
    qty = qty.replace(0, np.nan)
    return (amount / qty).replace([np.inf, -np.inf], np.nan)


def _regularity(gaps: pd.Series) -> float:
    """0..1 — how predictable the customer's rhythm is (1 = clockwork)."""
    mean = float(gaps.mean())
    if mean <= 0:
        return 0.0
    cv = float(gaps.std(ddof=0)) / mean if len(gaps) > 1 else 0.0
    return round(float(max(0.0, min(1.0, 1 - cv))), 4)


def _trajectory(group: pd.DataFrame, as_of: pd.Timestamp) -> dict[str, Any]:
    dates, amounts = group["date"], group["net_amount"]
    window = pd.Timedelta(days=180)
    recent_mask = dates >= (as_of - window)
    prior_mask = (dates < (as_of - window)) & (dates >= (as_of - 2 * window))
    recent = float(amounts[recent_mask].sum(skipna=True))
    prior = float(amounts[prior_mask].sum(skipna=True))
    out: dict[str, Any] = {"spend_recent_180d": recent, "spend_prior_180d": prior}
    if prior > 0:
        out["spend_trend"] = round((recent - prior) / prior, 4)
    elif recent > 0:
        out["spend_trend"] = 1.0
    return out


def _seasonality(group: pd.DataFrame) -> list[dict[str, Any]]:
    dates = group["date"].dropna()
    if dates.empty:
        return []
    amounts = group.loc[dates.index, "net_amount"].fillna(0)
    by_month = amounts.groupby(dates.dt.month).sum()
    total = by_month.sum()
    if total <= 0:
        return []
    return [
        {"month": int(m), "share": round(float(v / total), 4)}
        for m, v in by_month.sort_values(ascending=False).head(3).items()
    ]


# --------------------------------------------------------------------------- #
# CRM fallbacks and composite scores
# --------------------------------------------------------------------------- #
def _coalesce(frame: pd.DataFrame, target: str, fallback: str) -> None:
    """Fill a derived column from a CRM column, without overwriting evidence."""
    if fallback not in frame.columns:
        return
    if target not in frame.columns:
        frame[target] = frame[fallback]
        return
    frame[target] = frame[target].where(frame[target].notna(), frame[fallback])


def _merge_crm_fallbacks(frame: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    frame = frame.copy()

    # rename incoming CRM columns so the derived ones win where they exist
    for derived, crm in (("total_spend", "total_spend"),
                         ("order_count", "order_count"),
                         ("avg_order_value", "avg_order_value"),
                         ("last_purchase_date", "last_purchase_date"),
                         ("first_purchase_date", "first_purchase_date")):
        crm_col = f"{crm}_crm"
        if crm in frame.columns and f"{derived}_x" in frame.columns:
            pass
        if f"{derived}_x" in frame.columns and f"{derived}_y" in frame.columns:
            frame[derived] = frame[f"{derived}_y"].where(
                frame[f"{derived}_y"].notna(), frame[f"{derived}_x"]
            )
            frame = frame.drop(columns=[f"{derived}_x", f"{derived}_y"])
        _ = crm_col

    if "total_spend" not in frame.columns:
        frame["total_spend"] = np.nan
    if "order_count" not in frame.columns:
        frame["order_count"] = np.nan

    if "avg_order_value" not in frame.columns:
        frame["avg_order_value"] = np.nan
    computable = frame["avg_order_value"].isna() & frame["total_spend"].notna() & \
        frame["order_count"].notna() & (frame["order_count"] > 0)
    frame.loc[computable, "avg_order_value"] = (
        frame.loc[computable, "total_spend"] / frame.loc[computable, "order_count"]
    )

    if "last_purchase_date" in frame.columns:
        last = pd.to_datetime(frame["last_purchase_date"], errors="coerce")
        frame["last_purchase_date"] = last
        if "recency_days" not in frame.columns:
            frame["recency_days"] = np.nan
        need = frame["recency_days"].isna() & last.notna()
        frame.loc[need, "recency_days"] = (as_of - last[need]).dt.days.astype(float)
    if "first_purchase_date" in frame.columns:
        first = pd.to_datetime(frame["first_purchase_date"], errors="coerce")
        frame["first_purchase_date"] = first
        if "tenure_days" not in frame.columns:
            frame["tenure_days"] = np.nan
        need = frame["tenure_days"].isna() & first.notna()
        frame.loc[need, "tenure_days"] = (as_of - first[need]).dt.days.astype(float)

    for column in ("recency_days", "tenure_days", "avg_gap_days", "median_gap_days",
                   "discount_rate", "spend_trend", "purchase_regularity",
                   "neutral_color_share", "units", "tx_lines"):
        if column not in frame.columns:
            frame[column] = np.nan

    # CRM-provided discount sensitivity, normalised to 0..1
    if "discount_sensitivity" in frame.columns:
        sens = pd.to_numeric(frame["discount_sensitivity"], errors="coerce")
        sens = sens.where(sens.notna())
        sens = sens / 100 if sens.dropna().gt(1).any() else sens
        frame["discount_rate"] = frame["discount_rate"].where(frame["discount_rate"].notna(), sens)

    return frame


def _expected_cycle(frame: pd.DataFrame) -> pd.Series:
    """Each customer's expected days between purchases.

    Personal rhythm when we have at least two orders; otherwise the base median,
    which keeps "overdue" meaningful for one-time buyers without pretending we
    know their habit.
    """
    personal = frame.get("median_gap_days")
    if personal is None:
        personal = pd.Series(np.nan, index=frame.index)
    base_candidates = personal.dropna()
    base = float(base_candidates.median()) if not base_candidates.empty else np.nan
    if np.isnan(base):
        recency = frame.get("recency_days")
        if recency is not None and recency.notna().any():
            base = float(recency.dropna().median())
    if np.isnan(base) or base <= 0:
        base = 120.0
    blended = personal.copy()
    # shrink extreme personal estimates towards the base (small-sample robustness)
    orders = frame.get("order_count")
    if orders is not None:
        weight = (orders.fillna(1).clip(lower=1) - 1) / (orders.fillna(1).clip(lower=1) + 1)
        blended = personal * weight + base * (1 - weight)
        blended = blended.where(personal.notna(), base)
    else:
        blended = blended.fillna(base)
    return blended.clip(lower=7, upper=900)


def _derive_scores(frame: pd.DataFrame, as_of: pd.Timestamp, has_tx: bool) -> pd.DataFrame:
    frame = frame.copy()
    frame["expected_cycle_days"] = _expected_cycle(frame)

    recency = frame["recency_days"]
    frame["cycles_overdue"] = (
        (recency - frame["expected_cycle_days"]) / frame["expected_cycle_days"]
    ).where(recency.notna())
    frame["days_overdue"] = (recency - frame["expected_cycle_days"]).where(recency.notna())
    frame["next_purchase_due"] = frame.apply(
        lambda r: (r["last_purchase_date"] + pd.Timedelta(days=float(r["expected_cycle_days"])))
        if pd.notna(r.get("last_purchase_date")) and pd.notna(r.get("expected_cycle_days"))
        else pd.NaT,
        axis=1,
    )

    # churn risk: a logistic-shaped function of how far past the cycle they are
    def churn(row) -> float | None:
        overdue = row.get("cycles_overdue")
        if overdue is None or pd.isna(overdue):
            return None
        risk = 1 / (1 + np.exp(-2.2 * (float(overdue) - 0.35)))
        regularity = row.get("purchase_regularity")
        if regularity is not None and not pd.isna(regularity):
            # a highly regular customer being late is a stronger signal
            risk = risk * (0.75 + 0.35 * float(regularity))
        return round(float(min(max(risk, 0.0), 0.99)), 4)

    frame["churn_risk"] = frame.apply(churn, axis=1)

    # purchase velocity: orders per year over their observed tenure
    tenure = frame["tenure_days"]
    orders = frame["order_count"]
    velocity = (orders / (tenure / 365.25)).where(
        tenure.notna() & (tenure > 30) & orders.notna()
    )
    frame["purchase_velocity"] = velocity.replace([np.inf, -np.inf], np.nan)

    # ---- composite customer score (0-100), weights redistributed ---- #
    components = {
        "monetary": _norm_rank(frame["total_spend"]),
        "frequency": _norm_rank(frame["order_count"]),
        "recency": 1 - _norm_rank(frame["recency_days"]),
        "trajectory": _norm_rank(frame["spend_trend"]) if "spend_trend" in frame else pd.Series(np.nan, index=frame.index),
        "breadth": _norm_rank(frame["units"]) if "units" in frame else pd.Series(np.nan, index=frame.index),
    }
    weight_frame = pd.DataFrame({
        key: pd.Series(SCORE_WEIGHTS[key], index=frame.index).where(series.notna())
        for key, series in components.items()
    })
    value_frame = pd.DataFrame(components)
    total_weight = weight_frame.sum(axis=1, skipna=True)
    weighted = (value_frame * weight_frame).sum(axis=1, skipna=True)
    score = (weighted / total_weight.replace(0, np.nan)) * 100
    frame["customer_score"] = score.round(1)

    # how much of the score rests on evidence rather than absence
    frame["score_coverage"] = (total_weight / sum(SCORE_WEIGHTS.values())).round(3)
    frame["data_confidence"] = frame.apply(
        lambda r: _confidence_label(r, has_tx), axis=1
    )

    # predicted 12-month value: velocity × AOV, damped by churn risk
    def predicted(row) -> float | None:
        aov = row.get("avg_order_value")
        vel = row.get("purchase_velocity")
        if aov is None or pd.isna(aov):
            return None
        if vel is None or pd.isna(vel):
            spend = row.get("total_spend")
            tenure_days = row.get("tenure_days")
            if spend is None or pd.isna(spend) or tenure_days is None or pd.isna(tenure_days) or tenure_days < 60:
                return None
            annualised = float(spend) / (float(tenure_days) / 365.25)
        else:
            annualised = float(vel) * float(aov)
        risk = row.get("churn_risk")
        damp = 1 - 0.55 * float(risk) if risk is not None and not pd.isna(risk) else 0.85
        return round(max(0.0, annualised * damp), 2)

    frame["predicted_12m_value"] = frame.apply(predicted, axis=1)

    # engagement 0-100 blends recency-vs-cycle with regularity and trend
    def engagement(row) -> float | None:
        parts, weights = [], []
        overdue = row.get("cycles_overdue")
        if overdue is not None and not pd.isna(overdue):
            parts.append(float(np.clip(1 - (float(overdue) + 0.2) / 2.2, 0, 1)))
            weights.append(0.5)
        regularity = row.get("purchase_regularity")
        if regularity is not None and not pd.isna(regularity):
            parts.append(float(regularity))
            weights.append(0.2)
        trend = row.get("spend_trend")
        if trend is not None and not pd.isna(trend):
            parts.append(float(np.clip((float(trend) + 1) / 2, 0, 1)))
            weights.append(0.3)
        if not parts:
            return None
        return round(float(np.average(parts, weights=weights) * 100), 1)

    frame["engagement_score"] = frame.apply(engagement, axis=1)
    return frame


def _confidence_label(row: pd.Series, has_tx: bool) -> str:
    coverage = row.get("score_coverage")
    coverage = float(coverage) if coverage is not None and not pd.isna(coverage) else 0.0
    lines = row.get("tx_lines")
    lines = float(lines) if lines is not None and not pd.isna(lines) else 0.0
    if has_tx and lines >= 4 and coverage >= 0.8:
        return "high"
    if (has_tx and lines >= 2) or coverage >= 0.7:
        return "medium"
    if coverage >= 0.4:
        return "low"
    return "very low"


def customer_affinity_profile(row: pd.Series) -> dict[str, Any]:
    """Extract the affinity structure used by the matching engine."""
    def listed(key: str) -> list[dict[str, Any]]:
        value = row.get(key)
        if isinstance(value, list):
            return value
        return []

    return {
        "categories": listed("category_affinity"),
        "brands": listed("brand_affinity"),
        "colors": listed("color_affinity"),
        "sizes": listed("size_affinity"),
        "priceBand": (
            {"low": row.get("price_band_low"), "high": row.get("price_band_high"),
             "mid": row.get("price_band_mid")}
            if row.get("price_band_low") is not None and not pd.isna(row.get("price_band_low"))
            else None
        ),
        "avgOrderValue": _clean(row.get("avg_order_value")),
        "discountRate": _clean(row.get("discount_rate")),
        "neutralColorShare": _clean(row.get("neutral_color_share")),
        "purchasedProductIds": row.get("purchased_product_ids") if isinstance(
            row.get("purchased_product_ids"), list) else [],
        "seasonality": row.get("seasonality") if isinstance(row.get("seasonality"), list) else [],
    }


def _clean(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(number) or np.isinf(number):
        return None
    return number
