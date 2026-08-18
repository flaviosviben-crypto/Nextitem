"""Trends, performance breakdowns and what-if scenario modelling.

Everything returned from here is an *estimate produced by an explicit model*,
and every scenario result carries the assumptions that produced it so the UI can
label it as a projection rather than a fact.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# trends
# --------------------------------------------------------------------------- #
def revenue_timeseries(transactions: pd.DataFrame | None, freq: str = "W",
                       months: int = 12) -> dict[str, Any]:
    """Revenue over time plus a like-for-like comparison with the prior period."""
    if (transactions is None or transactions.empty
            or "date" not in transactions.columns
            or "net_amount" not in transactions.columns):
        return {"points": [], "available": False,
                "reason": "Transaction dates and amounts are required for revenue trends."}

    tx = transactions[transactions["date"].notna() & transactions["net_amount"].notna()].copy()
    if tx.empty:
        return {"points": [], "available": False,
                "reason": "No transactions carry both a date and an amount."}

    end = tx["date"].max()
    start = end - pd.DateOffset(months=months)
    window = tx[tx["date"] >= start]

    grouped = window.set_index("date").resample(freq).agg(
        revenue=("net_amount", "sum"),
        orders=("net_amount", "count"),
    ).reset_index()
    grouped["customers"] = (
        window.set_index("date").resample(freq)["customer_id"].nunique().values
        if "customer_id" in window.columns else np.nan
    )

    # The final bucket is almost always a partial week and would render as a
    # cliff on the chart, reading as a collapse in sales that has not happened.
    if len(grouped) > 1:
        last_start = grouped.iloc[-1]["date"]
        period_end = last_start + pd.tseries.frequencies.to_offset(freq)
        if end < period_end - pd.Timedelta(days=1):
            grouped = grouped.iloc[:-1]

    points = [
        {
            "date": row["date"].strftime("%Y-%m-%d"),
            "revenue": round(float(row["revenue"]), 2),
            "orders": int(row["orders"]),
            "customers": int(row["customers"]) if not pd.isna(row.get("customers")) else None,
            "avgBasket": round(float(row["revenue"]) / row["orders"], 2) if row["orders"] else None,
        }
        for _, row in grouped.iterrows()
    ]

    period = pd.Timedelta(days=30)
    current = float(tx[tx["date"] > end - period]["net_amount"].sum())
    previous = float(tx[(tx["date"] <= end - period) & (tx["date"] > end - 2 * period)]["net_amount"].sum())
    change = ((current - previous) / previous) if previous > 0 else None

    return {
        "points": points,
        "available": True,
        "last30Days": round(current, 2),
        "previous30Days": round(previous, 2),
        "change": round(change, 4) if change is not None else None,
        "windowEnd": end.strftime("%Y-%m-%d"),
    }


def dimension_performance(transactions: pd.DataFrame | None, column: str,
                          limit: int = 10) -> list[dict[str, Any]]:
    """Revenue, units and growth by category / brand / colour / size."""
    if (transactions is None or transactions.empty or column not in transactions.columns
            or "net_amount" not in transactions.columns):
        return []
    tx = transactions[transactions[column].notna() & transactions["net_amount"].notna()].copy()
    if tx.empty:
        return []

    has_dates = "date" in tx.columns and tx["date"].notna().any()
    if has_dates:
        end = tx["date"].max()
        recent_mask = tx["date"] > end - pd.Timedelta(days=90)
        prior_mask = (tx["date"] <= end - pd.Timedelta(days=90)) & (tx["date"] > end - pd.Timedelta(days=180))

    qty = tx["quantity"].fillna(1) if "quantity" in tx.columns else pd.Series(1.0, index=tx.index)
    tx["_qty"] = qty

    rows: list[dict[str, Any]] = []
    total_revenue = float(tx["net_amount"].sum())
    for value, group in tx.groupby(tx[column].astype(str)):
        revenue = float(group["net_amount"].sum())
        entry: dict[str, Any] = {
            "value": value,
            "revenue": round(revenue, 2),
            "share": round(revenue / total_revenue, 4) if total_revenue else None,
            "units": round(float(group["_qty"].sum()), 1),
            "orders": int(len(group)),
            "avgPrice": round(revenue / float(group["_qty"].sum()), 2)
            if float(group["_qty"].sum()) > 0 else None,
            "customers": int(group["customer_id"].nunique()) if "customer_id" in group else None,
        }
        if has_dates:
            recent = float(group.loc[group.index.intersection(tx[recent_mask].index), "net_amount"].sum())
            prior = float(group.loc[group.index.intersection(tx[prior_mask].index), "net_amount"].sum())
            entry["recent90d"] = round(recent, 2)
            entry["growth"] = round((recent - prior) / prior, 4) if prior > 0 else None
        rows.append(entry)

    rows.sort(key=lambda r: r["revenue"], reverse=True)
    return rows[:limit]


def customer_value_distribution(customers: pd.DataFrame, buckets: int = 8) -> list[dict[str, Any]]:
    """Histogram of lifetime value, on a log-ish scale that suits retail spend."""
    if customers is None or customers.empty or "total_spend" not in customers.columns:
        return []
    spend = customers["total_spend"].dropna()
    spend = spend[spend > 0]
    if spend.empty:
        return []
    if spend.nunique() < 3:
        return [{"label": f"€{float(spend.iloc[0]):,.0f}", "customers": int(len(spend)),
                 "revenue": round(float(spend.sum()), 2)}]

    edges = np.unique(np.quantile(spend, np.linspace(0, 1, buckets + 1)))
    out: list[dict[str, Any]] = []
    for i in range(len(edges) - 1):
        low, high = edges[i], edges[i + 1]
        mask = (spend >= low) & (spend <= high if i == len(edges) - 2 else spend < high)
        subset = spend[mask]
        if subset.empty:
            continue
        out.append({
            "label": f"€{low:,.0f}–€{high:,.0f}",
            "low": round(float(low), 2),
            "high": round(float(high), 2),
            "customers": int(len(subset)),
            "revenue": round(float(subset.sum()), 2),
        })
    return out


def concentration(customers: pd.DataFrame) -> dict[str, Any]:
    """What share of revenue comes from the top 10% / 20% of customers."""
    if customers is None or customers.empty or "total_spend" not in customers.columns:
        return {"available": False}
    spend = customers["total_spend"].dropna().sort_values(ascending=False)
    spend = spend[spend > 0]
    if spend.empty:
        return {"available": False}
    total = float(spend.sum())
    out: dict[str, Any] = {"available": True, "totalRevenue": round(total, 2)}
    for pct in (0.1, 0.2, 0.5):
        take = max(1, int(round(len(spend) * pct)))
        out[f"top{int(pct * 100)}Share"] = round(float(spend.head(take).sum()) / total, 4)
    return out


# --------------------------------------------------------------------------- #
# scenario lab
# --------------------------------------------------------------------------- #
def simulate_discount(products: pd.DataFrame, discount_pct: float,
                      product_ids: list[str] | None = None,
                      elasticity: float = 1.6) -> dict[str, Any]:
    """Estimate the effect of a markdown on units, revenue and margin.

    Model: constant price-elasticity of demand applied to the product's own
    observed weekly velocity over a 30-day horizon. Elasticity is an assumption,
    stated in the output — it is not derived from the boutique's data unless
    enough discounting history exists to estimate it.
    """
    if products is None or products.empty:
        return {"available": False, "reason": "No inventory loaded."}

    frame = products.copy()
    if product_ids:
        frame = frame[frame["product_id"].astype(str).isin([str(p) for p in product_ids])]
    if frame.empty:
        return {"available": False, "reason": "No products matched the selection."}

    frame = frame[frame["stock"].fillna(0) > 0]
    if frame.empty:
        return {"available": False, "reason": "The selected products have no stock on hand."}

    discount = float(np.clip(discount_pct, 0, 90)) / 100
    velocity = frame.get("weekly_velocity")
    if velocity is None or velocity.isna().all():
        baseline_units = frame["stock"].fillna(0) * 0.08   # conservative default
        velocity_known = False
    else:
        baseline_units = (velocity.fillna(velocity.median()) * 4.3).clip(lower=0)
        velocity_known = True

    uplift = (1 - discount) ** (-elasticity)
    projected_units = np.minimum(baseline_units * uplift, frame["stock"].fillna(baseline_units))
    incremental_units = projected_units - np.minimum(baseline_units, frame["stock"].fillna(baseline_units))

    price = frame["price"].fillna(frame["price"].median() if frame["price"].notna().any() else 0)
    new_price = price * (1 - discount)
    cost = frame["cost"] if "cost" in frame.columns else pd.Series(np.nan, index=frame.index)

    base_revenue = float((np.minimum(baseline_units, frame["stock"].fillna(baseline_units)) * price).sum())
    new_revenue = float((projected_units * new_price).sum())

    has_cost = cost.notna().any()
    if has_cost:
        filled_cost = cost.fillna(cost.median())
        base_margin = float((np.minimum(baseline_units, frame["stock"].fillna(baseline_units))
                             * (price - filled_cost)).sum())
        new_margin = float((projected_units * (new_price - filled_cost)).sum())
    else:
        base_margin = new_margin = None

    return {
        "available": True,
        "scenario": f"{discount_pct:.0f}% discount on {len(frame)} product(s)",
        "horizonDays": 30,
        "products": int(len(frame)),
        "baselineUnits": round(float(np.minimum(baseline_units, frame['stock'].fillna(baseline_units)).sum()), 1),
        "projectedUnits": round(float(projected_units.sum()), 1),
        "incrementalUnits": round(float(incremental_units.sum()), 1),
        "baselineRevenue": round(base_revenue, 2),
        "projectedRevenue": round(new_revenue, 2),
        "revenueDelta": round(new_revenue - base_revenue, 2),
        "baselineMargin": round(base_margin, 2) if base_margin is not None else None,
        "projectedMargin": round(new_margin, 2) if new_margin is not None else None,
        "marginDelta": round(new_margin - base_margin, 2) if base_margin is not None else None,
        "stockReduction": round(float(projected_units.sum()), 1),
        "assumptions": [
            f"Price elasticity of demand assumed at {elasticity}. A 10% cut therefore lifts "
            f"unit demand by roughly {((1/0.9) ** elasticity - 1) * 100:.0f}%.",
            "Baseline demand is each product's own observed weekly velocity over 30 days."
            if velocity_known else
            "No sales velocity available — baseline assumed at 8% of stock per month.",
            "Sales are capped at units on hand.",
            "Margin is computed only where cost data exists." if has_cost
            else "No cost data — margin impact cannot be estimated.",
        ],
        "confidence": "medium" if velocity_known else "low",
    }


def simulate_outreach(customers: pd.DataFrame, customer_ids: list[str] | None = None,
                      segment: str | None = None, contact_rate: float = 1.0,
                      conversion_rate: float | None = None) -> dict[str, Any]:
    """Estimate the revenue from contacting a group of customers.

    Conversion is derived from each customer's own overdue position when
    available (the same curve the opportunity engine uses), not a flat guess.
    """
    if customers is None or customers.empty:
        return {"available": False, "reason": "No customers loaded."}

    pool = customers
    if customer_ids:
        pool = pool[pool["customer_id"].astype(str).isin([str(c) for c in customer_ids])]
    elif segment:
        pool = pool[pool["segment"] == segment]
    if pool.empty:
        return {"available": False, "reason": "No customers matched the selection."}

    baskets = (pd.to_numeric(pool["avg_order_value"], errors="coerce")
               if "avg_order_value" in pool.columns else pd.Series(dtype=float))
    median_basket = float(baskets.dropna().median()) if baskets.notna().any() else None
    if median_basket is None:
        return {"available": False,
                "reason": "No basket values available — revenue impact cannot be estimated."}

    filled_baskets = baskets.fillna(median_basket)

    if conversion_rate is not None:
        probabilities = pd.Series(float(conversion_rate), index=pool.index)
        conversion_source = f"fixed {conversion_rate:.0%} assumption"
    elif "cycles_overdue" in pool.columns and pool["cycles_overdue"].notna().any():
        # `cycles_overdue` can arrive as object dtype from row-wise derivation;
        # numpy ufuncs need a real float array.
        cycles = pd.to_numeric(pool["cycles_overdue"], errors="coerce").fillna(0.3).clip(lower=-0.5)
        probabilities = (0.42 * np.exp(-0.55 * np.clip(cycles - 0.2, 0, None))).clip(0.05, 0.45)
        conversion_source = "per-customer, from how far past their repurchase window they are"
    else:
        probabilities = pd.Series(0.15, index=pool.index)
        conversion_source = "flat 15% fallback (no purchase-cycle data)"

    contacted = int(round(len(pool) * float(np.clip(contact_rate, 0, 1))))
    scale = contacted / len(pool) if len(pool) else 0
    expected_orders = float((probabilities * scale).sum())
    expected_revenue = float((probabilities * filled_baskets * scale).sum())

    return {
        "available": True,
        "scenario": f"Contact {contacted} customer(s)"
                    + (f" in {segment}" if segment else ""),
        "audience": int(len(pool)),
        "contacted": contacted,
        "expectedOrders": round(expected_orders, 1),
        "expectedRevenue": round(expected_revenue, 2),
        "avgBasket": round(float(filled_baskets.mean()), 2),
        "avgConversion": round(float(probabilities.mean()), 4),
        "assumptions": [
            f"Conversion estimated {conversion_source}.",
            f"Average basket of €{float(filled_baskets.mean()):,.0f} per converting customer.",
            "Assumes one purchase per converting customer within the outreach window.",
        ],
        "confidence": "medium" if conversion_rate is None else "low",
    }


def simulate_category_focus(transactions: pd.DataFrame | None, products: pd.DataFrame,
                            category: str, uplift_pct: float = 20.0) -> dict[str, Any]:
    """Estimate the effect of concentrating attention on one category."""
    if products is None or products.empty:
        return {"available": False, "reason": "No inventory loaded."}
    subset = products[products["category"].astype(str).str.lower() == category.strip().lower()] \
        if "category" in products.columns else products.iloc[0:0]
    if subset.empty:
        return {"available": False, "reason": f"No products found in '{category}'."}

    baseline_revenue = None
    if (transactions is not None and not transactions.empty
            and "category" in transactions.columns and "net_amount" in transactions.columns
            and "date" in transactions.columns):
        tx = transactions[transactions["category"].astype(str).str.lower() == category.strip().lower()]
        tx = tx[tx["date"].notna()]
        if not tx.empty:
            end = tx["date"].max()
            recent = tx[tx["date"] > end - pd.Timedelta(days=30)]
            baseline_revenue = float(recent["net_amount"].sum(skipna=True))

    if baseline_revenue is None:
        velocity = subset.get("weekly_velocity")
        price = subset.get("price")
        if velocity is not None and velocity.notna().any() and price is not None:
            baseline_revenue = float((velocity.fillna(0) * 4.3 * price.fillna(0)).sum())

    if not baseline_revenue:
        return {"available": False,
                "reason": f"Not enough sales history for '{category}' to project an uplift."}

    uplift = baseline_revenue * (uplift_pct / 100)
    stock_value = float(subset["retail_value"].dropna().sum()) if "retail_value" in subset else None
    return {
        "available": True,
        "scenario": f"Focus next 30 days on {category}",
        "category": category,
        "skus": int(len(subset)),
        "baselineRevenue": round(baseline_revenue, 2),
        "projectedRevenue": round(baseline_revenue + uplift, 2),
        "revenueDelta": round(uplift, 2),
        "stockValue": round(stock_value, 2) if stock_value else None,
        "assumptions": [
            f"A focused push is assumed to lift {category} revenue by {uplift_pct:.0f}% "
            "over 30 days.",
            "Baseline is the last 30 days of actual sales in this category."
            if transactions is not None else
            "Baseline is derived from current stock velocity.",
        ],
        "confidence": "low",
    }
