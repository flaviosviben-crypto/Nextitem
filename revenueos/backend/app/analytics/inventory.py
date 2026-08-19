"""Inventory intelligence: ageing, sell-through, risk and recommended action.

The risk score is deliberately explainable — every point is attributable to a
named driver, and the recommended action never jumps straight to "discount".
Targeted clienteling is tried first, because a boutique's margin is the product.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date
from typing import Any

CLASSES = ["Hot", "Healthy", "Slow Moving", "At Risk", "Dead Stock", "Unknown"]


def build_product_stats(
    inventory: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Join catalogue with sales history and score each product."""
    if as_of is None:
        # Stock can arrive after the last recorded sale, so the reference date is
        # the latest thing we know about — otherwise ageing goes negative.
        known = [t["date"] for t in transactions if t.get("date")]
        known += [p["arrival_date"] for p in inventory if p.get("arrival_date")]
        as_of = max(known) if known else date.today()

    sales_by_sku: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in transactions:
        if t.get("sku"):
            sales_by_sku[str(t["sku"])].append(t)

    # Fallback join on product name when SKUs don't line up between systems.
    sales_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in transactions:
        name = (t.get("product") or "").strip().lower()
        if name:
            sales_by_name[name].append(t)

    products = [
        _product_one(p, sales_by_sku, sales_by_name, as_of)
        for p in inventory
    ]
    _attach_relative_risk(products)
    return products


def _product_one(p, sales_by_sku, sales_by_name, as_of) -> dict[str, Any]:
    sku = str(p["sku"])
    sales = sales_by_sku.get(sku) or sales_by_name.get((p.get("product_name") or "").strip().lower(), [])
    dated = sorted([t for t in sales if t.get("date")], key=lambda t: t["date"])

    units_sold = sum(int(t.get("quantity") or 1) for t in sales)
    revenue = sum(t["line_total"] for t in sales)
    last_sold = dated[-1]["date"] if dated else None
    days_since_sale = (as_of - last_sold).days if last_sold else None

    stock = p.get("stock")
    price = p.get("price")
    cost = p.get("cost")
    arrival = p.get("arrival_date")
    days_in_stock = max(0, (as_of - arrival).days) if arrival else None

    # Sell-through only means something when we know both halves.
    if stock is not None and units_sold is not None and (stock + units_sold) > 0:
        sell_through = units_sold / (stock + units_sold)
    else:
        sell_through = None

    velocity = None  # units per 30 days since arrival
    if units_sold and days_in_stock and days_in_stock > 14:
        velocity = units_sold / (days_in_stock / 30.0)

    weeks_of_cover = None
    if velocity and velocity > 0 and stock:
        weeks_of_cover = round(stock / (velocity / 4.33), 1)

    stock_value = stock * price if (stock is not None and price is not None) else None
    margin_rate = p.get("margin")
    if margin_rate is None and price and cost is not None and price > 0:
        margin_rate = (price - cost) / price
    margin_value = stock_value * margin_rate if (stock_value is not None and margin_rate is not None) else None

    return {
        "sku": sku,
        "product_name": p.get("product_name") or sku,
        "category": p.get("category"),
        "subcategory": p.get("subcategory"),
        "brand": p.get("brand"),
        "gender": p.get("gender"),
        "color": p.get("color"),
        "size": p.get("size"),
        "season": p.get("season"),
        "collection": p.get("collection"),
        "supplier": p.get("supplier"),
        "store": p.get("store"),
        "price": price,
        "original_price": p.get("original_price"),
        "cost": cost,
        "margin_rate": round(margin_rate, 3) if margin_rate is not None else None,
        "margin_value": round(margin_value, 2) if margin_value is not None else None,
        "stock": stock,
        "stock_value": round(stock_value, 2) if stock_value is not None else None,
        "arrival_date": arrival.isoformat() if arrival else None,
        "days_in_stock": days_in_stock,
        "units_sold": units_sold,
        "revenue": round(revenue, 2) if revenue else 0.0,
        "buyers": len({t["customer_id"] for t in sales}),
        "last_sold": last_sold.isoformat() if last_sold else None,
        "days_since_sale": days_since_sale,
        "sell_through": round(sell_through, 3) if sell_through is not None else None,
        "velocity_per_month": round(velocity, 2) if velocity is not None else None,
        "weeks_of_cover": weeks_of_cover,
        "as_of": as_of.isoformat(),
    }


def _attach_relative_risk(products: list[dict[str, Any]]) -> None:
    """Risk scored against this catalogue's own ageing and velocity distribution."""
    ages = sorted(p["days_in_stock"] for p in products if p.get("days_in_stock") is not None)
    median_age = statistics.median(ages) if ages else None
    velocities = [p["velocity_per_month"] for p in products if p.get("velocity_per_month")]
    median_velocity = statistics.median(velocities) if velocities else None
    values = [p["stock_value"] for p in products if p.get("stock_value")]
    high_value = statistics.quantiles(values, n=4)[2] if len(values) >= 4 else (max(values) if values else None)

    for p in products:
        drivers: list[dict[str, Any]] = []
        risk = 0.0
        known_signals = 0

        age = p.get("days_in_stock")
        if age is not None:
            known_signals += 1
            if age > 365:
                pts, why = 34, f"In stock {age} days — over a year old"
            elif age > 180:
                pts, why = 26, f"In stock {age} days — past two seasons"
            elif age > 120:
                pts, why = 18, f"In stock {age} days"
            elif age > 90:
                pts, why = 10, f"In stock {age} days"
            else:
                pts, why = 0, f"Recent arrival ({age} days)"
            if median_age and age > median_age * 1.6 and pts:
                pts += 4
                why += " — well above your catalogue average"
            risk += pts
            if pts:
                drivers.append({"driver": "Stock age", "points": pts, "detail": why})

        sold = p.get("units_sold") or 0
        stock = p.get("stock")
        if sold == 0 and (age or 0) > 60:
            risk += 26
            drivers.append({"driver": "No sales", "points": 26,
                            "detail": f"No units sold in {age} days on the floor"})
            known_signals += 1
        elif p.get("velocity_per_month") is not None:
            known_signals += 1
            v = p["velocity_per_month"]
            if median_velocity and v < median_velocity * 0.4:
                risk += 16
                drivers.append({"driver": "Slow velocity", "points": 16,
                                "detail": f"Selling {v:.1f}/month vs catalogue median {median_velocity:.1f}"})
            elif median_velocity and v > median_velocity * 1.5:
                risk -= 12
                drivers.append({"driver": "Strong velocity", "points": -12,
                                "detail": f"Selling {v:.1f}/month, well above median"})

        st = p.get("sell_through")
        if st is not None:
            known_signals += 1
            if st < 0.15 and (age or 0) > 90:
                risk += 14
                drivers.append({"driver": "Low sell-through", "points": 14,
                                "detail": f"Only {st:.0%} of the buy has sold"})
            elif st > 0.7:
                risk -= 10
                drivers.append({"driver": "High sell-through", "points": -10,
                                "detail": f"{st:.0%} sold through"})

        cover = p.get("weeks_of_cover")
        if cover is not None and cover > 52:
            risk += 10
            drivers.append({"driver": "Excess cover", "points": 10,
                            "detail": f"{cover:.0f} weeks of stock at the current rate"})

        value = p.get("stock_value")
        if value and high_value and value >= high_value:
            risk += 8
            drivers.append({"driver": "Capital at stake", "points": 8,
                            "detail": f"€{value:,.0f} of stock value concentrated here"})

        if stock == 0:
            risk = min(risk, 20)
            drivers.append({"driver": "Sold out", "points": 0, "detail": "No units on hand"})

        if known_signals == 0:
            p["risk_score"] = None
            p["risk_class"] = "Unknown"
            p["risk_drivers"] = []
            p["risk_reason"] = "Not enough information — add arrival dates, stock or sales history."
            p["recommended_action"] = "Import stock and sales history to assess this product."
            continue

        score = int(max(0, min(100, round(risk))))
        p["risk_score"] = score
        p["risk_drivers"] = sorted(drivers, key=lambda d: -abs(d["points"]))
        p["risk_class"] = _classify(p, score)
        p["risk_reason"] = _risk_reason(p, score)
        p["recommended_action"] = _action_for(p)


def _classify(p: dict[str, Any], score: int) -> str:
    if p.get("stock") == 0:
        return "Healthy"
    velocity = p.get("velocity_per_month")
    if score >= 70:
        return "Dead Stock"
    if score >= 50:
        return "At Risk"
    if score >= 30:
        return "Slow Moving"
    if velocity is not None and velocity >= 2:
        return "Hot"
    return "Healthy"


def _risk_reason(p: dict[str, Any], score: int) -> str:
    top = [d["detail"] for d in p.get("risk_drivers", []) if d["points"] > 0][:3]
    if not top:
        return "Performing in line with the rest of the catalogue."
    return "; ".join(top) + "."


def _action_for(p: dict[str, Any]) -> str:
    cls = p.get("risk_class")
    cat = p.get("category") or "this category"
    value = p.get("stock_value")
    money = f"€{value:,.0f} " if value else ""

    if cls == "Dead Stock":
        return (f"Target customers with {cat.lower()} affinity personally before any markdown — "
                f"{money}is tied up here. Consider a private-sale invitation if outreach fails.")
    if cls == "At Risk":
        return (f"Push to matched clients this week: personal outreach to {cat.lower()} buyers "
                "protects full margin. Review again in 14 days.")
    if cls == "Slow Moving":
        return f"Feature in styling suggestions and pair with a fast-moving {cat.lower()} piece."
    if cls == "Hot":
        cover = p.get("weeks_of_cover")
        if cover is not None and cover < 4:
            return f"Selling fast with only {cover:.0f} weeks of cover — reorder or reserve for VIPs."
        return "Performing well — keep visible and use it as the anchor in outreach."
    if p.get("stock") == 0:
        return "Out of stock — reorder if demand continues."
    return "No action needed this week."


def inventory_summary(products: list[dict[str, Any]]) -> dict[str, Any]:
    stocked = [p for p in products if p.get("stock") is not None]
    valued = [p for p in products if p.get("stock_value") is not None]
    with_st = [p for p in products if p.get("sell_through") is not None]
    ages = [p["days_in_stock"] for p in products if p.get("days_in_stock") is not None]

    by_class: dict[str, dict[str, Any]] = {}
    for c in CLASSES:
        members = [p for p in products if p.get("risk_class") == c]
        if not members:
            continue
        vals = [p["stock_value"] for p in members if p.get("stock_value") is not None]
        by_class[c] = {
            "products": len(members),
            "units": sum(p["stock"] for p in members if p.get("stock") is not None),
            "value": round(sum(vals), 2) if vals else None,
        }

    at_risk = [p for p in products if p.get("risk_class") in {"At Risk", "Dead Stock"}]
    at_risk_value = [p["stock_value"] for p in at_risk if p.get("stock_value") is not None]

    return {
        "skus": len(products),
        "units": sum(p["stock"] for p in stocked) if stocked else None,
        "stock_value": round(sum(p["stock_value"] for p in valued), 2) if valued else None,
        "retail_value": round(sum(p["stock_value"] for p in valued), 2) if valued else None,
        "margin_value": round(sum(p["margin_value"] for p in products if p.get("margin_value")), 2)
        if any(p.get("margin_value") for p in products) else None,
        "avg_sell_through": round(statistics.mean(p["sell_through"] for p in with_st), 3) if with_st else None,
        "median_days_in_stock": round(statistics.median(ages)) if ages else None,
        "at_risk_products": len(at_risk),
        "at_risk_value": round(sum(at_risk_value), 2) if at_risk_value else None,
        "out_of_stock": sum(1 for p in stocked if p["stock"] == 0),
        "by_class": by_class,
        "by_category": _mix(products, "category"),
        "by_brand": _mix(products, "brand"),
    }


def _mix(products: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, float]] = defaultdict(lambda: {"products": 0, "units": 0.0, "value": 0.0, "revenue": 0.0})
    for p in products:
        label = p.get(key)
        if not label:
            continue
        b = buckets[str(label)]
        b["products"] += 1
        b["units"] += p.get("stock") or 0
        b["value"] += p.get("stock_value") or 0
        b["revenue"] += p.get("revenue") or 0
    rows = [{"label": k, **{kk: round(vv, 2) for kk, vv in v.items()}} for k, v in buckets.items()]
    return sorted(rows, key=lambda r: -r["value"])[:12]
