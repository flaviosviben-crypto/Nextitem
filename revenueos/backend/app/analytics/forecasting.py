"""Trends, category performance and what-if scenarios.

Scenario outputs are explicitly modelled estimates, never presented as fact —
every result carries its assumptions so the boutique can judge them.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date
from typing import Any


def monthly_trend(transactions: list[dict[str, Any]], months: int = 12) -> list[dict[str, Any]]:
    dated = [t for t in transactions if t.get("date")]
    if not dated:
        return []
    anchor = max(t["date"] for t in dated)

    buckets: dict[str, dict[str, Any]] = {}
    year, month = anchor.year, anchor.month
    keys = []
    for _ in range(months):
        key = f"{year:04d}-{month:02d}"
        keys.append(key)
        buckets[key] = {"month": key, "revenue": 0.0, "orders": set(), "customers": set(), "units": 0}
        month -= 1
        if month == 0:
            month, year = 12, year - 1

    for t in dated:
        key = f"{t['date'].year:04d}-{t['date'].month:02d}"
        if key in buckets:
            b = buckets[key]
            b["revenue"] += t["line_total"]
            b["orders"].add(t["transaction_id"])
            b["customers"].add(t["customer_id"])
            b["units"] += int(t.get("quantity") or 1)

    out = []
    for key in reversed(keys):
        b = buckets[key]
        orders = len(b["orders"])
        out.append({
            "month": key,
            "revenue": round(b["revenue"], 2),
            "orders": orders,
            "customers": len(b["customers"]),
            "units": b["units"],
            "avg_order_value": round(b["revenue"] / orders, 2) if orders else None,
        })
    return out


def category_performance(transactions: list[dict[str, Any]], products: list[dict[str, Any]],
                         limit: int = 10) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"revenue": 0.0, "units": 0, "customers": set(), "orders": set()})
    for t in transactions:
        cat = t.get("category")
        if not cat:
            continue
        s = stats[str(cat)]
        s["revenue"] += t["line_total"]
        s["units"] += int(t.get("quantity") or 1)
        s["customers"].add(t["customer_id"])
        s["orders"].add(t["transaction_id"])

    stock_by_cat: dict[str, dict[str, float]] = defaultdict(lambda: {"value": 0.0, "units": 0.0, "skus": 0})
    for p in products:
        cat = p.get("category")
        if not cat:
            continue
        s = stock_by_cat[str(cat)]
        s["value"] += p.get("stock_value") or 0
        s["units"] += p.get("stock") or 0
        s["skus"] += 1

    rows = []
    for cat, s in stats.items():
        stock = stock_by_cat.get(cat, {"value": 0.0, "units": 0.0, "skus": 0})
        rows.append({
            "category": cat,
            "revenue": round(s["revenue"], 2),
            "units_sold": s["units"],
            "customers": len(s["customers"]),
            "orders": len(s["orders"]),
            "avg_line_value": round(s["revenue"] / max(1, s["units"]), 2),
            "stock_value": round(stock["value"], 2),
            "stock_units": int(stock["units"]),
            "skus": int(stock["skus"]),
        })
    # Categories held in stock but never sold are a finding in their own right.
    for cat, stock in stock_by_cat.items():
        if cat not in stats:
            rows.append({
                "category": cat, "revenue": 0.0, "units_sold": 0, "customers": 0, "orders": 0,
                "avg_line_value": None, "stock_value": round(stock["value"], 2),
                "stock_units": int(stock["units"]), "skus": int(stock["skus"]),
                "note": "Stock held but no recorded sales",
            })
    return sorted(rows, key=lambda r: -r["revenue"])[:limit]


def brand_performance(transactions: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"revenue": 0.0, "units": 0, "customers": set()})
    for t in transactions:
        brand = t.get("brand")
        if not brand:
            continue
        s = stats[str(brand)]
        s["revenue"] += t["line_total"]
        s["units"] += int(t.get("quantity") or 1)
        s["customers"].add(t["customer_id"])
    rows = [{"brand": b, "revenue": round(s["revenue"], 2), "units_sold": s["units"],
             "customers": len(s["customers"])} for b, s in stats.items()]
    return sorted(rows, key=lambda r: -r["revenue"])[:limit]


def inventory_ageing(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets = [("0–30 days", 0, 30), ("31–90 days", 31, 90), ("91–180 days", 91, 180),
               ("181–365 days", 181, 365), ("Over a year", 366, 10_000)]
    out = []
    for label, lo, hi in buckets:
        members = [p for p in products
                   if p.get("days_in_stock") is not None and lo <= p["days_in_stock"] <= hi]
        values = [p["stock_value"] for p in members if p.get("stock_value") is not None]
        out.append({
            "bucket": label,
            "products": len(members),
            "units": sum(p["stock"] for p in members if p.get("stock") is not None),
            "value": round(sum(values), 2) if values else 0.0,
        })
    return out


# ------------------------------------------------------------------ what-if --

def simulate_discount(products: list[dict[str, Any]], skus: list[str], discount_pct: float,
                      uplift_elasticity: float = 1.8) -> dict[str, Any]:
    """Estimate the effect of discounting a set of products.

    Elasticity is an assumption, not a measurement: a 1.8 elasticity means a 10%
    price cut is modelled to lift unit demand by 18%. It is stated in the output.
    """
    chosen = [p for p in products if str(p["sku"]) in {str(s) for s in skus}]
    if not chosen:
        return {"error": "No matching products."}

    rate = max(0.0, min(0.9, discount_pct / 100 if discount_pct > 1 else discount_pct))
    baseline_units = sum(p.get("velocity_per_month") or 0 for p in chosen)
    uplift = rate * uplift_elasticity
    projected_units = baseline_units * (1 + uplift)

    revenue_before = sum((p.get("velocity_per_month") or 0) * (p.get("price") or 0) for p in chosen)
    revenue_after = sum((p.get("velocity_per_month") or 0) * (1 + uplift) * (p.get("price") or 0) * (1 - rate)
                        for p in chosen)
    margin_before = sum((p.get("velocity_per_month") or 0) * ((p.get("price") or 0) - (p.get("cost") or 0))
                        for p in chosen)
    margin_after = sum((p.get("velocity_per_month") or 0) * (1 + uplift)
                       * ((p.get("price") or 0) * (1 - rate) - (p.get("cost") or 0))
                       for p in chosen)
    stock_units = sum(p.get("stock") or 0 for p in chosen)

    return {
        "scenario": f"{rate:.0%} discount on {len(chosen)} products",
        "products": len(chosen),
        "monthly_units_before": round(baseline_units, 1),
        "monthly_units_after": round(projected_units, 1),
        "monthly_revenue_before": round(revenue_before, 2),
        "monthly_revenue_after": round(revenue_after, 2),
        "revenue_delta": round(revenue_after - revenue_before, 2),
        "monthly_margin_before": round(margin_before, 2),
        "monthly_margin_after": round(margin_after, 2),
        "margin_delta": round(margin_after - margin_before, 2),
        "stock_units_affected": stock_units,
        "weeks_to_clear_after": round(stock_units / (projected_units / 4.33), 1)
        if projected_units > 0 else None,
        "assumptions": [
            f"Demand elasticity of {uplift_elasticity} — a {rate:.0%} cut lifts units {uplift:.0%}",
            "Current velocity is projected forward unchanged apart from the discount effect",
            "No cannibalisation of full-price sales is modelled",
        ],
        "estimate": True,
    }


def simulate_outreach(profiles: list[dict[str, Any]], customer_ids: list[str],
                      conversion_rate: float = 0.12) -> dict[str, Any]:
    """Estimate the effect of contacting a specific group of customers."""
    ids = {str(c) for c in customer_ids}
    chosen = [p for p in profiles if p["customer_id"] in ids]
    if not chosen:
        return {"error": "No matching customers."}

    reachable = [p for p in chosen if p.get("marketing_consent") is True]
    baskets = [p.get("avg_order_value") for p in chosen if p.get("avg_order_value")]
    avg_basket = statistics.mean(baskets) if baskets else None
    rate = max(0.01, min(0.6, conversion_rate))
    expected_orders = len(reachable) * rate

    return {
        "scenario": f"Contact {len(chosen)} customers",
        "customers_selected": len(chosen),
        "contactable": len(reachable),
        "blocked_by_consent": len(chosen) - len(reachable),
        "assumed_conversion": rate,
        "expected_orders": round(expected_orders, 1),
        "avg_basket": round(avg_basket, 2) if avg_basket else None,
        "expected_revenue": round(expected_orders * avg_basket, 2) if avg_basket else None,
        "assumptions": [
            f"{rate:.0%} of contactable customers convert",
            "Each conversion is worth that customer group's average basket",
            "Customers without recorded consent are excluded from the forecast",
        ],
        "estimate": True,
    }


def simulate_category_focus(transactions: list[dict[str, Any]], products: list[dict[str, Any]],
                            category: str, attention_lift: float = 0.25) -> dict[str, Any]:
    """Estimate the effect of prioritising one category for a week."""
    rows = [t for t in transactions if str(t.get("category") or "").lower() == category.lower()]
    if not rows:
        return {"error": f"No sales history for {category}."}
    dated = [t for t in rows if t.get("date")]
    if not dated:
        return {"error": f"No dated sales for {category}."}

    anchor = max(t["date"] for t in dated)
    last_90 = [t for t in dated if (anchor - t["date"]).days <= 90]
    weekly = sum(t["line_total"] for t in last_90) / 13 if last_90 else 0
    stock = [p for p in products if str(p.get("category") or "").lower() == category.lower()]
    stock_value = sum(p.get("stock_value") or 0 for p in stock)

    return {
        "scenario": f"Focus one week on {category}",
        "category": category,
        "baseline_weekly_revenue": round(weekly, 2),
        "projected_weekly_revenue": round(weekly * (1 + attention_lift), 2),
        "revenue_delta": round(weekly * attention_lift, 2),
        "stock_available": round(stock_value, 2),
        "products_in_stock": len([p for p in stock if (p.get("stock") or 0) > 0]),
        "assumptions": [
            f"Focused merchandising and outreach lifts the category {attention_lift:.0%}",
            "Baseline is the trailing 13-week average for this category",
            "Assumes sufficient stock cover for the uplift",
        ],
        "estimate": True,
    }
