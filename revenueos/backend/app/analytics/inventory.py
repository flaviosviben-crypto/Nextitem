"""Inventory intelligence: ageing, sell-through, risk and the action to take.

The commercial opinion baked in here: **a markdown is the last resort, not the
first**. When a product is at risk the recommended action is first to find the
customers who would buy it at full price; discounting is only suggested when
the clientèle signal is weak or the stock is genuinely terminal.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

STATUSES = ("Hot", "Healthy", "Slow Moving", "At Risk", "Dead Stock")

STATUS_META = {
    "Hot": {"tone": "positive", "meaning": "Selling faster than the rest of your catalogue."},
    "Healthy": {"tone": "neutral", "meaning": "Moving at a normal pace for its age."},
    "Slow Moving": {"tone": "watch", "meaning": "Behind the pace expected for how long it has been in stock."},
    "At Risk": {"tone": "warning", "meaning": "Capital is starting to sit still — act before markdown season."},
    "Dead Stock": {"tone": "negative", "meaning": "No meaningful movement; the money is stuck."},
}


def build_inventory_metrics(
    inventory: pd.DataFrame,
    transactions: pd.DataFrame | None = None,
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """One row per product with ageing, velocity, risk and a recommended action."""
    if inventory is None or inventory.empty:
        return pd.DataFrame()

    as_of = as_of or pd.Timestamp.now().normalize()
    frame = inventory.copy()
    frame["product_id"] = frame["product_id"].astype(str)

    sales = _sales_by_product(transactions, as_of)
    if not sales.empty:
        frame = frame.merge(sales, on="product_id", how="left")
    for column in ("units_sold", "units_sold_90d", "revenue", "last_sold_date",
                   "first_sold_date", "orders", "avg_selling_price", "avg_discount_pct"):
        if column not in frame.columns:
            frame[column] = np.nan

    frame["units_sold"] = frame["units_sold"].fillna(0.0) if not sales.empty else np.nan
    frame["units_sold_90d"] = frame["units_sold_90d"].fillna(0.0) if not sales.empty else np.nan
    frame["revenue"] = frame["revenue"].fillna(0.0) if not sales.empty else np.nan

    frame = _ageing(frame, as_of)
    frame = _value_and_margin(frame)
    frame = _sell_through(frame)
    frame = _risk(frame)
    return frame


# --------------------------------------------------------------------------- #
def _sales_by_product(transactions: pd.DataFrame | None, as_of: pd.Timestamp) -> pd.DataFrame:
    if transactions is None or transactions.empty or "product_id" not in transactions.columns:
        return pd.DataFrame()
    tx = transactions[transactions["product_id"].notna()].copy()
    if tx.empty:
        return pd.DataFrame()
    tx["product_id"] = tx["product_id"].astype(str)
    qty = tx["quantity"].fillna(1) if "quantity" in tx.columns else pd.Series(1.0, index=tx.index)
    tx["_qty"] = qty
    has_date = "date" in tx.columns and tx["date"].notna().any()
    has_amount = "net_amount" in tx.columns and tx["net_amount"].notna().any()

    records = []
    cutoff = as_of - pd.Timedelta(days=90)
    for pid, group in tx.groupby("product_id", sort=False):
        record: dict[str, Any] = {
            "product_id": pid,
            "units_sold": float(group["_qty"].sum()),
            "orders": int(len(group)),
        }
        if has_amount:
            record["revenue"] = float(group["net_amount"].sum(skipna=True))
            units = float(group["_qty"].sum())
            if units > 0:
                record["avg_selling_price"] = round(record["revenue"] / units, 2)
        if has_date:
            dates = group["date"].dropna()
            if not dates.empty:
                record["last_sold_date"] = dates.max()
                record["first_sold_date"] = dates.min()
                recent = group[group["date"] >= cutoff]
                record["units_sold_90d"] = float(recent["_qty"].sum()) if not recent.empty else 0.0
        if "discount" in group.columns and group["discount"].notna().any():
            positive = group["discount"].dropna()
            positive = positive[positive > 0]
            if not positive.empty:
                mean = float(positive.mean())
                record["avg_discount_pct"] = mean if mean > 1 else mean * 100
        records.append(record)
    return pd.DataFrame(records)


def _ageing(frame: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    frame = frame.copy()
    arrival = pd.to_datetime(frame.get("arrival_date"), errors="coerce") \
        if "arrival_date" in frame.columns else pd.Series(pd.NaT, index=frame.index)
    frame["arrival_date"] = arrival

    days = (as_of - arrival).dt.days.astype("float64")
    frame["days_in_stock"] = days
    frame["days_in_stock_estimated"] = False

    # Fall back to first-sold date when arrival is unknown; flag the estimate so
    # the UI can say "estimated" rather than presenting a guess as a fact.
    missing = frame["days_in_stock"].isna()
    if missing.any() and "first_sold_date" in frame.columns:
        first_sold = pd.to_datetime(frame["first_sold_date"], errors="coerce")
        estimate = (as_of - first_sold).dt.days.astype("float64")
        frame.loc[missing & estimate.notna(), "days_in_stock"] = estimate[missing & estimate.notna()]
        frame.loc[missing & estimate.notna(), "days_in_stock_estimated"] = True

    frame["days_since_last_sale"] = np.nan
    if "last_sold_date" in frame.columns:
        last_sold = pd.to_datetime(frame["last_sold_date"], errors="coerce")
        frame["days_since_last_sale"] = (as_of - last_sold).dt.days.astype("float64")

    def bucket(value) -> str | None:
        if value is None or pd.isna(value):
            return None
        days = float(value)
        if days <= 30:
            return "0-30 days"
        if days <= 60:
            return "31-60 days"
        if days <= 90:
            return "61-90 days"
        if days <= 180:
            return "91-180 days"
        if days <= 365:
            return "181-365 days"
        return "365+ days"

    frame["age_bucket"] = frame["days_in_stock"].map(bucket)
    return frame


def _value_and_margin(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    stock = frame["stock"] if "stock" in frame.columns else pd.Series(np.nan, index=frame.index)
    price = frame["price"] if "price" in frame.columns else pd.Series(np.nan, index=frame.index)
    cost = frame["cost"] if "cost" in frame.columns else pd.Series(np.nan, index=frame.index)

    frame["retail_value"] = (stock * price).where(stock.notna() & price.notna())
    frame["cost_value"] = (stock * cost).where(stock.notna() & cost.notna())

    unit_margin = (price - cost).where(price.notna() & cost.notna())
    frame["unit_margin"] = unit_margin
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = (unit_margin / price.replace(0, np.nan)) * 100
    if "margin" in frame.columns and frame["margin"].notna().any():
        frame["margin_pct"] = frame["margin"].where(frame["margin"].notna(), pct)
    else:
        frame["margin_pct"] = pct
    frame["margin_value"] = (unit_margin * stock).where(unit_margin.notna() & stock.notna())

    if "original_price" in frame.columns:
        original = frame["original_price"]
        with np.errstate(divide="ignore", invalid="ignore"):
            frame["markdown_pct"] = (
                (original - price) / original.replace(0, np.nan) * 100
            ).where(original.notna() & price.notna() & (original > 0))
    else:
        frame["markdown_pct"] = np.nan
    return frame


def _sell_through(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    sold = frame.get("units_sold")
    stock = frame.get("stock")
    if sold is None or sold.isna().all():
        frame["sell_through"] = np.nan
        frame["weekly_velocity"] = np.nan
        frame["weeks_of_cover"] = np.nan
        return frame

    received = sold.fillna(0) + stock.fillna(0)
    frame["sell_through"] = (sold / received.replace(0, np.nan)).where(
        sold.notna() & stock.notna() & (received > 0)
    )

    days = frame.get("days_in_stock")
    weeks = (days / 7).where(days.notna() & (days > 7))
    frame["weekly_velocity"] = (sold / weeks).where(weeks.notna())
    frame["weeks_of_cover"] = (stock / frame["weekly_velocity"].replace(0, np.nan)).where(
        frame["weekly_velocity"].notna() & (frame["weekly_velocity"] > 0) & stock.notna()
    )
    return frame


def _risk(frame: pd.DataFrame) -> pd.DataFrame:
    """Risk score 0-100 with an explicit, human-readable driver list.

    Each driver contributes points only when its input exists; the final score is
    rescaled by the weight actually available, so a catalogue without arrival
    dates still produces a meaningful ranking instead of collapsing to zero.
    """
    frame = frame.copy()
    n = len(frame)

    age = frame["days_in_stock"]
    age_rank = age.rank(pct=True) if age.notna().any() else pd.Series(np.nan, index=frame.index)
    velocity = frame["weekly_velocity"]
    velocity_rank = velocity.rank(pct=True) if velocity.notna().any() else pd.Series(np.nan, index=frame.index)
    sell_through = frame["sell_through"]
    value = frame["retail_value"]
    value_rank = value.rank(pct=True) if value.notna().any() else pd.Series(np.nan, index=frame.index)
    last_sale = frame["days_since_last_sale"]
    stock = frame["stock"]

    scores: list[float | None] = []
    statuses: list[str] = []
    driver_lists: list[list[dict[str, Any]]] = []

    for idx in frame.index:
        drivers: list[dict[str, Any]] = []
        weighted = 0.0
        available = 0.0

        # A piece that arrived last week has not had time to sell. Movement
        # signals are therefore weighted by how mature the stock is, so new
        # arrivals are never flagged as "at risk" simply for being new.
        age_days = age.loc[idx]
        maturity = (
            float(np.clip((float(age_days) - 21) / 60, 0.0, 1.0))
            if pd.notna(age_days) else 1.0
        )

        def add(name: str, weight: float, severity: float, detail: str) -> None:
            nonlocal weighted, available
            if weight <= 0.01:
                return
            severity = float(np.clip(severity, 0.0, 1.0))
            weighted += weight * severity
            available += weight
            drivers.append({
                "name": name,
                "weight": weight,
                "severity": round(severity, 3),
                "points": round(weight * severity * 100, 1),
                "detail": detail,
            })

        age_value = age_days
        if pd.notna(age_value):
            severity = float(np.clip((float(age_value) - 45) / 240, 0, 1))
            add("Stock age", 0.30, severity,
                f"{int(age_value)} days in stock"
                + (" (estimated)" if bool(frame.loc[idx, "days_in_stock_estimated"]) else ""))

        vel_value = velocity.loc[idx]
        if pd.notna(vel_value) and velocity_rank.notna().any():
            rank = float(velocity_rank.loc[idx])
            add("Sales velocity", 0.26 * maturity, 1 - rank,
                f"{float(vel_value):.2f} units/week — slower than {1 - rank:.0%} of the catalogue"
                if rank < 0.5 else f"{float(vel_value):.2f} units/week")
        elif pd.notna(frame.loc[idx, "units_sold"]):
            units = float(frame.loc[idx, "units_sold"])
            add("Sales velocity", 0.26 * maturity,
                1.0 if units == 0 else float(np.clip(1 - units / 6, 0, 1)),
                "never sold" if units == 0 else f"only {units:.0f} unit(s) sold")

        st_value = sell_through.loc[idx]
        if pd.notna(st_value):
            add("Sell-through", 0.18 * maturity, 1 - float(np.clip(st_value, 0, 1)),
                f"{float(st_value):.0%} of received units sold")

        last_value = last_sale.loc[idx]
        if pd.notna(last_value):
            add("Time since last sale", 0.14 * maturity,
                float(np.clip((float(last_value) - 30) / 180, 0, 1)),
                f"last sold {int(last_value)} days ago")
        elif pd.notna(frame.loc[idx, "units_sold"]) and float(frame.loc[idx, "units_sold"]) == 0:
            add("Time since last sale", 0.14 * maturity, 1.0, "no recorded sale ever")

        val_value = value.loc[idx]
        if pd.notna(val_value) and value_rank.notna().any():
            add("Capital exposure", 0.12, float(value_rank.loc[idx]),
                f"€{float(val_value):,.0f} of stock value tied up")

        stock_value = stock.loc[idx]
        if pd.notna(stock_value) and float(stock_value) <= 0:
            # Out of stock: not a risk, it is simply not actionable.
            st_now = sell_through.loc[idx]
            sold_out_well = pd.notna(st_now) and float(st_now) >= 0.8
            scores.append(None)
            statuses.append("Hot" if sold_out_well else "Healthy")
            driver_lists.append([{
                "name": "Out of stock", "weight": 1.0, "severity": 0.0, "points": 0.0,
                "detail": ("Sold through and no units left — consider a re-order."
                           if sold_out_well else "No units on hand — nothing at risk."),
            }])
            continue

        if available < 0.2:
            scores.append(None)
            statuses.append("Healthy")
            driver_lists.append(drivers)
            continue

        score = round(100 * weighted / available, 1)
        scores.append(score)
        driver_lists.append(sorted(drivers, key=lambda d: d["points"], reverse=True))
        statuses.append(_status_for(score, frame.loc[idx]))

    frame["risk_score"] = scores
    frame["risk_drivers"] = driver_lists
    frame["status"] = statuses
    frame["recommended_action"] = [
        _action_for(frame.loc[idx]) for idx in frame.index
    ]
    _ = n
    return frame


def _status_for(score: float, row: pd.Series) -> str:
    velocity = row.get("weekly_velocity")
    sell_through = row.get("sell_through")
    if score >= 78:
        return "Dead Stock"
    if score >= 60:
        return "At Risk"
    if score >= 42:
        return "Slow Moving"
    if (velocity is not None and not pd.isna(velocity) and float(velocity) >= 1.0) or \
       (sell_through is not None and not pd.isna(sell_through) and float(sell_through) >= 0.6):
        return "Hot"
    return "Healthy"


def _action_for(row: pd.Series) -> dict[str, Any]:
    """Recommend the *next* commercial move, discount last."""
    status = row.get("status")
    stock = row.get("stock")
    value = row.get("retail_value")
    markdown = row.get("markdown_pct")
    days = row.get("days_in_stock")

    if stock is not None and not pd.isna(stock) and float(stock) <= 0:
        return {"action": "none", "label": "Out of stock",
                "detail": "Nothing on hand. Consider a re-order if it sells well."}

    if status == "Hot":
        if stock is not None and not pd.isna(stock) and float(stock) <= 0:
            return {"action": "reorder", "label": "Re-order — it sold out",
                    "detail": "This sold through completely. Check availability with the supplier."}
        return {"action": "reorder", "label": "Protect availability",
                "detail": "Selling well — check re-order or size replenishment before it runs out."}
    if status == "Healthy":
        return {"action": "monitor", "label": "No action needed",
                "detail": "Moving at a normal pace."}

    value_text = f"€{float(value):,.0f}" if value is not None and not pd.isna(value) else "this stock"
    if status == "Slow Moving":
        return {"action": "clienteling", "label": "Put it in front of the right clients",
                "detail": f"{value_text} is drifting. Match it to customers with matching affinity "
                          "before considering any price action."}
    if status == "At Risk":
        return {"action": "targeted_outreach", "label": "Targeted outreach now",
                "detail": f"{value_text} at risk. Build a short contact list from the best "
                          "customer matches and offer a personal styling appointment."}

    # Dead stock
    already_marked = markdown is not None and not pd.isna(markdown) and float(markdown) >= 20
    if already_marked:
        return {"action": "clear", "label": "Clear through an event",
                "detail": f"Already marked down {float(markdown):.0f}% and still not moving after "
                          f"{int(days) if days is not None and not pd.isna(days) else '—'} days. "
                          "Move it into a private sale or bundle it."}
    return {"action": "rescue", "label": "Rescue before discounting",
            "detail": f"{value_text} is stuck. Try the top customer matches first; only discount "
                      "if that list is short or does not convert."}


def inventory_overview(frame: pd.DataFrame) -> dict[str, Any]:
    """Portfolio-level KPIs. Unknown values are reported as None, never 0."""
    if frame is None or frame.empty:
        return {"skus": 0, "unitsInStock": None, "inventoryValue": None}

    def total(column: str) -> float | None:
        if column not in frame.columns:
            return None
        values = frame[column].dropna()
        return round(float(values.sum()), 2) if not values.empty else None

    def mean(column: str) -> float | None:
        if column not in frame.columns:
            return None
        values = frame[column].dropna()
        return round(float(values.mean()), 3) if not values.empty else None

    status_counts = (
        frame["status"].value_counts().to_dict() if "status" in frame.columns else {}
    )
    at_risk = frame[frame["status"].isin(["At Risk", "Dead Stock"])] if "status" in frame.columns else frame.iloc[0:0]
    at_risk_value = at_risk["retail_value"].dropna().sum() if "retail_value" in at_risk.columns else None

    return {
        "skus": int(len(frame)),
        "unitsInStock": total("stock"),
        "inventoryValue": total("cost_value") or None,
        "retailValue": total("retail_value"),
        "estimatedMargin": total("margin_value"),
        "avgMarginPct": mean("margin_pct"),
        "avgSellThrough": mean("sell_through"),
        "avgDaysInStock": mean("days_in_stock"),
        "statusCounts": {k: int(v) for k, v in status_counts.items()},
        "atRiskSkus": int(len(at_risk)),
        "atRiskValue": round(float(at_risk_value), 2) if at_risk_value else None,
        "ageBuckets": (
            frame["age_bucket"].value_counts().to_dict() if "age_bucket" in frame.columns else {}
        ),
    }


def dimension_mix(frame: pd.DataFrame, column: str, limit: int = 10) -> list[dict[str, Any]]:
    """Stock concentration by category / brand / size / colour."""
    if frame is None or frame.empty or column not in frame.columns:
        return []
    subset = frame[frame[column].notna()]
    if subset.empty:
        return []
    grouped = subset.groupby(subset[column].astype(str))
    rows = []
    for name, group in grouped:
        units = group["stock"].dropna().sum() if "stock" in group.columns else None
        value = group["retail_value"].dropna().sum() if "retail_value" in group.columns else None
        sell_through = group["sell_through"].dropna()
        risk = group["risk_score"].dropna()
        rows.append({
            "value": name,
            "skus": int(len(group)),
            "units": round(float(units), 1) if units is not None and units == units else None,
            "retailValue": round(float(value), 2) if value is not None and value == value else None,
            "avgSellThrough": round(float(sell_through.mean()), 4) if not sell_through.empty else None,
            "avgRisk": round(float(risk.mean()), 1) if not risk.empty else None,
        })
    key = "retailValue" if any(r["retailValue"] for r in rows) else "skus"
    rows.sort(key=lambda r: (r[key] or 0), reverse=True)
    total = sum((r[key] or 0) for r in rows)
    for row in rows:
        row["share"] = round((row[key] or 0) / total, 4) if total else None
    return rows[:limit]
