"""The analytics surface Claude is allowed to call.

Claude never computes a number here. Every tool runs the same deterministic code
that powers the dashboard and returns already-computed results; Claude's job is
to choose the right query, read the result, and explain it.

Privacy: tools return internal customer IDs and display names only. Email,
phone and address never enter a prompt (see ``context_builder.minimise``).
"""
from __future__ import annotations

import json
from typing import Any

from anthropic import beta_tool

from ..analytics import matching
from ..workspace import workspace


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _no_data() -> str:
    return _json({"error": "No dataset is loaded. Ask the user to import data or load the demo boutique."})


def _slim_customer(p: dict[str, Any]) -> dict[str, Any]:
    """A customer as the model should see them: metrics, no contact details."""
    return {
        "customer_id": p["customer_id"],
        "name": p["name"],
        "value_tier": p.get("value_tier"),
        "lifecycle": p.get("lifecycle"),
        "customer_score": p.get("customer_score"),
        "total_spend": p.get("total_spend"),
        "orders": p.get("order_count"),
        "avg_order_value": p.get("avg_order_value"),
        "last_purchase": p.get("last_purchase"),
        "days_since_purchase": p.get("recency_days"),
        "typical_cycle_days": p.get("cycle_days"),
        "cycle_confidence": p.get("cycle_confidence"),
        "cycle_position": p.get("cycle_position"),
        "top_category": p.get("top_category"),
        "top_brand": p.get("top_brand"),
        "price_band": [p.get("price_low"), p.get("price_high")],
        "store": p.get("store"),
        "contactable": p.get("contactable", False),
        "data_confidence": p.get("data_confidence"),
    }


def _slim_product(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "sku": p["sku"],
        "name": p.get("product_name"),
        "category": p.get("category"),
        "brand": p.get("brand"),
        "price": p.get("price"),
        "stock": p.get("stock"),
        "stock_value": p.get("stock_value"),
        "days_in_stock": p.get("days_in_stock"),
        "units_sold": p.get("units_sold"),
        "sell_through": p.get("sell_through"),
        "risk_class": p.get("risk_class"),
        "risk_score": p.get("risk_score"),
        "risk_reason": p.get("risk_reason"),
        "recommended_action": p.get("recommended_action"),
    }


def _find_customer(reference: str) -> dict[str, Any] | None:
    ref = (reference or "").strip().lower()
    if not ref:
        return None
    for p in workspace.profiles:
        if p["customer_id"].lower() == ref:
            return p
    exact = [p for p in workspace.profiles if p["name"].lower() == ref]
    if exact:
        return exact[0]
    partial = [p for p in workspace.profiles if ref in p["name"].lower()]
    if len(partial) == 1:
        return partial[0]
    if partial:
        return max(partial, key=lambda p: p.get("total_spend") or 0)
    return None


# ------------------------------------------------------------------- tools ---

@beta_tool
def get_business_overview() -> str:
    """Headline state of the boutique: customer base, inventory, revenue opportunity, data health.

    Use this first for broad questions like "how is the business doing" or
    "what should I focus on".
    """
    if not workspace.is_loaded:
        return _no_data()
    return _json(workspace.summary)


@beta_tool
def list_customers(
    segment: str = "",
    sort_by: str = "customer_score",
    limit: int = 10,
    overdue_only: bool = False,
    contactable_only: bool = False,
) -> str:
    """List customers ranked by a metric, optionally filtered.

    Args:
        segment: Restrict by value tier ("VIP", "Promising", "Standard") or by lifecycle
            stage ("Active", "Due", "At Risk", "Lost"). Empty means all.
        sort_by: One of "customer_score", "total_spend", "cycle_position", "recency_days",
            "potential_annual_value", "avg_order_value".
        limit: How many customers to return (max 40).
        overdue_only: Only customers at or past their repurchase point.
        contactable_only: Only customers with a permitted contact channel.
    """
    if not workspace.is_loaded:
        return _no_data()
    rows = workspace.profiles
    if segment:
        needle = segment.strip().lower()
        rows = [p for p in rows if needle in {(p.get("value_tier") or "").lower(),
                                              (p.get("lifecycle") or "").lower()}]
    if overdue_only:
        rows = [p for p in rows if p.get("lifecycle") in {"Due", "At Risk", "Lost"}]
    if contactable_only:
        rows = [p for p in rows if p.get("contactable")]

    key = sort_by if sort_by in {
        "customer_score", "total_spend", "cycle_position", "recency_days",
        "potential_annual_value", "avg_order_value"} else "customer_score"
    rows = sorted(rows, key=lambda p: (p.get(key) is not None, p.get(key) or 0), reverse=True)
    return _json({
        "sorted_by": key,
        "matched": len(rows),
        "customers": [_slim_customer(p) for p in rows[:max(1, min(limit, 40))]],
    })


@beta_tool
def get_customer(reference: str) -> str:
    """Full profile for one customer, including affinities and recent purchases.

    Args:
        reference: Customer ID or name (partial names are matched).
    """
    if not workspace.is_loaded:
        return _no_data()
    p = _find_customer(reference)
    if not p:
        return _json({"error": f"No customer matches '{reference}'."})

    txs = workspace.customer_transactions(p["customer_id"])[:12]
    return _json({
        "customer": _slim_customer(p),
        "category_affinity": p.get("category_affinity"),
        "brand_affinity": p.get("brand_affinity"),
        "color_affinity": p.get("color_affinity"),
        "size_affinity": p.get("size_affinity"),
        "spend_growth": p.get("spend_growth"),
        "segment_play": p.get("segment_play"),
        "recent_purchases": [{
            "date": str(t.get("date")),
            "product": t.get("product"),
            "category": t.get("category"),
            "brand": t.get("brand"),
            "amount": t.get("line_total"),
        } for t in txs],
    })


@beta_tool
def recommend_products_for_customer(reference: str, limit: int = 5) -> str:
    """Rank in-stock products for one customer, with the reasons behind each match.

    Args:
        reference: Customer ID or name.
        limit: How many products to return (max 10).
    """
    if not workspace.is_loaded:
        return _no_data()
    p = _find_customer(reference)
    if not p:
        return _json({"error": f"No customer matches '{reference}'."})
    matches = matching.best_products_for_customer(p, workspace.products,
                                                  limit=max(1, min(limit, 10)))
    if not matches:
        return _json({"customer": p["name"],
                      "matches": [],
                      "note": "No product clears the confidence threshold for this customer."})
    return _json({
        "customer": p["name"],
        "matches": [{
            "sku": m["sku"], "product": m["product_name"], "price": m["price"],
            "match_pct": m["match_pct"], "data_confidence": m["data_confidence"],
            "why": m["why"], "caveats": m["caveats"],
            "expected_value": matching.expected_value(m, p),
        } for m in matches],
    })


@beta_tool
def find_customers_for_product(sku: str, limit: int = 10, contactable_only: bool = False) -> str:
    """Rank the customers most likely to buy a given product. Ideal for new arrivals.

    Args:
        sku: The product SKU (exact) or part of the product name.
        limit: How many customers to return (max 25).
        contactable_only: Only include customers with marketing consent.
    """
    if not workspace.is_loaded:
        return _no_data()
    product = workspace.product(sku)
    if not product:
        needle = sku.strip().lower()
        hits = [p for p in workspace.products if needle in (p.get("product_name") or "").lower()]
        if not hits:
            return _json({"error": f"No product matches '{sku}'."})
        product = hits[0]

    matches = matching.best_customers_for_product(
        product, workspace.profiles, limit=max(1, min(limit, 25)),
        consented_only=contactable_only)
    return _json({
        "product": _slim_product(product),
        "matches": [{
            "customer_id": m["customer_id"], "name": m["customer_name"],
            "match_pct": m["match_pct"], "data_confidence": m["data_confidence"],
            "why": m["why"],
        } for m in matches],
    })


@beta_tool
def list_opportunities(opportunity_type: str = "", limit: int = 8) -> str:
    """The customers RevenueOS says are worth a conversation, and why.

    Args:
        opportunity_type: Filter by trigger — "due", "at_risk", "win_back",
            "new_arrival", "cross_sell", "restock_affinity". Empty means all.
        limit: How many to return (max 20).
    """
    if not workspace.is_loaded:
        return _no_data()
    rows = workspace.opportunities
    if opportunity_type:
        rows = [o for o in rows if o["trigger"] == opportunity_type.strip().lower()]
    return _json([{
        "id": o["id"], "trigger": o["trigger"], "customer_id": o["customer_id"],
        "value_tier": o.get("value_tier"), "lifecycle": o.get("lifecycle"),
        "headline": o["headline"], "why_now": o["why_now"],
        "product": (o.get("product") or {}).get("name"),
        "match_pct": (o.get("product") or {}).get("match_pct"),
        # The actual multiplicands behind influenced_value_eur. match_pct is a
        # different number (raw product-match score) and must not be read as
        # the probability used here — expose the real ones so the math can be
        # explained correctly instead of reconstructed from adjacent fields.
        "basket_value_eur": o.get("basket_value"),
        "probability": o.get("probability"),
        "influenced_value_eur": o.get("influenced_value"),
        "incremental_value_eur": o.get("incremental_value"),
        "value_basis": o.get("value_basis"),
        "priority": o["priority"], "action": o["action"],
        "contactable": o["contactable"],
    } for o in rows[:max(1, min(limit, 20))]])


@beta_tool
def list_products(risk_class: str = "", category: str = "", sort_by: str = "risk_score",
                  limit: int = 10) -> str:
    """List catalogue products with their inventory performance.

    Args:
        risk_class: Filter by "Hot", "Healthy", "Slow Moving", "At Risk" or "Dead Stock".
        category: Filter by product category.
        sort_by: "risk_score", "stock_value", "days_in_stock", "units_sold" or "sell_through".
        limit: How many products to return (max 30).
    """
    if not workspace.is_loaded:
        return _no_data()
    rows = workspace.products
    if risk_class:
        rows = [p for p in rows if (p.get("risk_class") or "").lower() == risk_class.strip().lower()]
    if category:
        needle = category.strip().lower()
        rows = [p for p in rows if needle in (p.get("category") or "").lower()]
    key = sort_by if sort_by in {"risk_score", "stock_value", "days_in_stock",
                                 "units_sold", "sell_through"} else "risk_score"
    rows = sorted(rows, key=lambda p: (p.get(key) is not None, p.get(key) or 0), reverse=True)
    return _json({"sorted_by": key, "matched": len(rows),
                  "products": [_slim_product(p) for p in rows[:max(1, min(limit, 30))]]})


@beta_tool
def get_inventory_overview() -> str:
    """Inventory totals: value, ageing, sell-through, and the split by risk class."""
    if not workspace.is_loaded:
        return _no_data()
    return _json(workspace.summary.get("inventory", {}))


@beta_tool
def get_segment_breakdown() -> str:
    """Customer counts and value by RFM segment (VIP, At Risk, Sleeping, ...)."""
    if not workspace.is_loaded:
        return _no_data()
    return _json(workspace.summary.get("segments", []))


@beta_tool
def get_revenue_trend(months: int = 12) -> str:
    """Monthly revenue, order count and unique customers over recent months.

    Args:
        months: How many months back to report (max 36).
    """
    if not workspace.is_loaded:
        return _no_data()
    from ..analytics.forecasting import monthly_trend
    return _json(monthly_trend(workspace.transactions_raw, months=max(1, min(months, 36))))


@beta_tool
def get_data_health() -> str:
    """What the uploaded data supports, what is missing, and the data health score.

    Use this when the user asks why a number is unavailable or how to improve results.
    """
    if not workspace.is_loaded:
        return _no_data()
    return _json(workspace.quality)


@beta_tool
def get_category_performance(limit: int = 10) -> str:
    """Revenue, units and customer count per category, with stock held against each.

    Args:
        limit: How many categories to return (max 20).
    """
    if not workspace.is_loaded:
        return _no_data()
    from ..analytics.forecasting import category_performance
    return _json(category_performance(workspace.transactions_raw, workspace.products,
                                      limit=max(1, min(limit, 20))))


ANALYST_TOOLS = [
    get_business_overview,
    list_customers,
    get_customer,
    recommend_products_for_customer,
    find_customers_for_product,
    list_opportunities,
    list_products,
    get_inventory_overview,
    get_segment_breakdown,
    get_revenue_trend,
    get_data_health,
    get_category_performance,
]
