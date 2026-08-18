"""The analytics functions Claude is allowed to call, and their execution.

This is the boundary that makes the AI Analyst trustworthy: Claude can *choose*
which analysis to run and *interpret* what comes back, but every number in an
answer originates from one of these deterministic functions running over the
boutique's real tables. There is no path by which the model can invent a
customer, a product, or a figure and have it presented as data.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..analytics.forecasting import (
    dimension_performance,
    revenue_timeseries,
    simulate_discount,
    simulate_outreach,
)
from ..analytics.inventory import dimension_mix, inventory_overview
from ..analytics.matching import build_profile, score_customers_for_product, score_products_for_customer
from ..analytics.rfm import segment_summary
from .context_builder import customer_brief, product_brief, truncate_rows

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "find_customers",
        "description": (
            "Search and rank customers by computed metrics. Use for questions like "
            "'who should I contact today', 'which VIPs have not bought recently', "
            "'who is at risk of churning', 'who are my best customers'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "segment": {"type": "string",
                            "description": "Restrict to one segment, e.g. 'Champions', 'At Risk', 'Sleeping'."},
                "overdueOnly": {"type": "boolean",
                                "description": "Only customers past their normal repurchase window."},
                "minSpend": {"type": "number"},
                "sortBy": {"type": "string",
                           "enum": ["customer_score", "total_spend", "days_overdue",
                                    "churn_risk", "predicted_12m_value", "recency_days"],
                           "description": "Ranking metric, highest first."},
                "search": {"type": "string", "description": "Name or city substring."},
                "limit": {"type": "integer", "description": "Max rows (default 15)."},
            },
        },
    },
    {
        "name": "recommend_products_for_customer",
        "description": (
            "Rank catalogue products for one named customer, with the signal-level "
            "reasons for each match. Use for 'what should I recommend to X'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customerId": {"type": "string"},
                "customerName": {"type": "string",
                                 "description": "Used when the ID is unknown; matched case-insensitively."},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "recommend_customers_for_product",
        "description": (
            "Rank customers for one product — 'who would buy this jacket', "
            "'who should I call about the new arrivals'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "productId": {"type": "string"},
                "productName": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "find_products",
        "description": (
            "Search and rank inventory. Use for 'what stock is at risk', "
            "'what are my biggest inventory problems', 'what should I push', "
            "'what arrived recently'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string",
                           "enum": ["Hot", "Healthy", "Slow Moving", "At Risk", "Dead Stock"]},
                "category": {"type": "string"},
                "brand": {"type": "string"},
                "maxDaysInStock": {"type": "number"},
                "minDaysInStock": {"type": "number"},
                "inStockOnly": {"type": "boolean"},
                "sortBy": {"type": "string",
                           "enum": ["risk_score", "retail_value", "days_in_stock",
                                    "sell_through", "units_sold", "price"]},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "get_opportunities",
        "description": (
            "The ranked commercial opportunities already discovered by the engine, "
            "with estimated value, probability and the customers/products involved."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string",
                         "description": "Filter by kind, e.g. overdue_vip, dead_stock_rescue, "
                                        "new_arrival_match, reactivation, brand_restock."},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "get_performance",
        "description": (
            "Revenue trend over time and performance broken down by category, brand, "
            "colour or size. Use for 'which category performs best', 'why did sales fall'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string",
                              "enum": ["category", "brand", "color", "size", "store", "channel"]},
                "includeTrend": {"type": "boolean"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "get_segments",
        "description": "Customer base broken into segments with size, revenue share and averages.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_inventory_summary",
        "description": (
            "Portfolio-level stock KPIs plus the mix by category, brand, size and colour."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mixBy": {"type": "string", "enum": ["category", "brand", "size", "color"]},
            },
        },
    },
    {
        "name": "simulate",
        "description": (
            "Project the effect of an action: a discount on selected products, or "
            "contacting a group of customers. Results are estimates with stated assumptions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["discount", "outreach"]},
                "discountPct": {"type": "number"},
                "productIds": {"type": "array", "items": {"type": "string"}},
                "segment": {"type": "string"},
                "customerIds": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["type"],
        },
    },
]


class ToolError(ValueError):
    pass


def run_tool(workspace, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Execute one analytics tool against the workspace. Never raises to caller."""
    try:
        handler = _HANDLERS.get(name)
        if handler is None:
            return {"error": f"Unknown tool '{name}'."}
        workspace.recompute()
        return handler(workspace, payload or {})
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": f"{name} failed: {exc}"}


# --------------------------------------------------------------------------- #
def _metrics(workspace) -> pd.DataFrame:
    metrics = workspace.customer_metrics
    if metrics is None or metrics.empty:
        raise ToolError("No customer data has been loaded yet.")
    return metrics


def _products(workspace) -> pd.DataFrame:
    products = workspace.inventory_metrics
    if products is None or products.empty:
        raise ToolError("No inventory has been loaded yet.")
    return products


def _find_customers(workspace, payload) -> dict[str, Any]:
    metrics = _metrics(workspace)
    frame = metrics

    segment = payload.get("segment")
    if segment and "segment" in frame.columns:
        frame = frame[frame["segment"].astype(str).str.lower() == str(segment).lower()]
    if payload.get("overdueOnly") and "days_overdue" in frame.columns:
        frame = frame[frame["days_overdue"].notna() & (frame["days_overdue"] > 0)]
    if payload.get("minSpend") is not None and "total_spend" in frame.columns:
        frame = frame[frame["total_spend"].fillna(0) >= float(payload["minSpend"])]
    search = payload.get("search")
    if search:
        needle = str(search).lower()
        mask = frame["display_name"].astype(str).str.lower().str.contains(needle, na=False)
        if "city" in frame.columns:
            mask |= frame["city"].astype(str).str.lower().str.contains(needle, na=False)
        frame = frame[mask]

    sort_by = payload.get("sortBy") or "customer_score"
    if sort_by in frame.columns:
        ascending = sort_by == "recency_days"
        frame = frame.sort_values(sort_by, ascending=ascending, na_position="last")

    limit = int(payload.get("limit") or 15)
    rows = [customer_brief(row) for _, row in frame.head(limit).iterrows()]
    result = truncate_rows(rows, limit)
    result["matchedCustomers"] = int(len(frame))
    result["filtersApplied"] = {k: v for k, v in payload.items() if v is not None}
    return result


def _recommend_products_for_customer(workspace, payload) -> dict[str, Any]:
    metrics = _metrics(workspace)
    ctx = workspace.matching_context
    if ctx is None:
        raise ToolError("No inventory is loaded, so products cannot be recommended.")

    row = _resolve_customer(metrics, payload)
    profile = build_profile(row)
    limit = int(payload.get("limit") or 6)
    matches = score_products_for_customer(profile, ctx, limit=limit)
    return {
        "customer": customer_brief(row),
        "recommendations": [
            {
                "productId": m["productId"], "product": m["productName"],
                "brand": m["brand"], "category": m["category"], "price": m["price"],
                "size": m["size"], "colour": m["color"], "stock": m["stock"],
                "matchPct": m["scorePct"], "dataConfidence": m["dataConfidence"],
                "why": [
                    {"signal": s["name"], "reason": s["reason"], "direction": s["direction"]}
                    for s in m["signals"][:4]
                ],
            }
            for m in matches
        ],
    }


def _recommend_customers_for_product(workspace, payload) -> dict[str, Any]:
    metrics = _metrics(workspace)
    products = _products(workspace)
    ctx = workspace.matching_context
    row = _resolve_product(products, payload)
    limit = int(payload.get("limit") or 10)
    matches = score_customers_for_product(row, metrics, ctx, limit=limit, min_score=0.4)
    return {
        "product": product_brief(row),
        "matches": [
            {
                "customerId": m["customerId"], "customer": m["customerName"],
                "segment": m.get("segment"), "lifetimeSpend": m.get("totalSpend"),
                "matchPct": m["scorePct"], "dataConfidence": m["dataConfidence"],
                "why": [
                    {"signal": s["name"], "reason": s["reason"], "direction": s["direction"]}
                    for s in m["signals"][:3]
                ],
            }
            for m in matches
        ],
    }


def _find_products(workspace, payload) -> dict[str, Any]:
    products = _products(workspace)
    frame = products

    for key, column in (("status", "status"), ("category", "category"), ("brand", "brand")):
        value = payload.get(key)
        if value and column in frame.columns:
            frame = frame[frame[column].astype(str).str.lower() == str(value).lower()]
    if payload.get("maxDaysInStock") is not None:
        frame = frame[frame["days_in_stock"].notna()
                      & (frame["days_in_stock"] <= float(payload["maxDaysInStock"]))]
    if payload.get("minDaysInStock") is not None:
        frame = frame[frame["days_in_stock"].notna()
                      & (frame["days_in_stock"] >= float(payload["minDaysInStock"]))]
    if payload.get("inStockOnly", True):
        frame = frame[frame["stock"].fillna(1) > 0]

    sort_by = payload.get("sortBy") or "risk_score"
    if sort_by in frame.columns:
        frame = frame.sort_values(sort_by, ascending=False, na_position="last")

    limit = int(payload.get("limit") or 15)
    rows = []
    for _, row in frame.head(limit).iterrows():
        brief = product_brief(row)
        action = row.get("recommended_action")
        if isinstance(action, dict):
            brief["recommendedAction"] = action.get("label")
            brief["actionDetail"] = action.get("detail")
        drivers = row.get("risk_drivers")
        if isinstance(drivers, list) and drivers:
            brief["riskDrivers"] = [
                {"driver": d.get("name"), "detail": d.get("detail")} for d in drivers[:3]
            ]
        rows.append(brief)
    result = truncate_rows(rows, limit)
    result["matchedProducts"] = int(len(frame))
    return result


def _get_opportunities(workspace, payload) -> dict[str, Any]:
    opportunities = workspace.opportunities or []
    kind = payload.get("kind")
    if kind:
        opportunities = [o for o in opportunities if o["kind"] == kind]
    limit = int(payload.get("limit") or 10)
    rows = [
        {
            "id": o["id"], "kind": o["kindLabel"], "title": o["title"],
            "why": o["explanation"], "action": o["action"],
            "estimatedValue": o["estimatedValue"], "probability": o["probability"],
            "score": o["score"], "matchPct": o.get("matchPct"),
            "customers": [
                {"id": c.get("customerId"), "name": c.get("name" ) or c.get("customerName"),
                 "matchPct": c.get("scorePct")}
                for c in (o.get("customers") or [])[:6]
            ],
            "products": [
                {"id": p.get("productId"), "name": p.get("name") or p.get("productName"),
                 "price": p.get("price")}
                for p in (o.get("products") or [])[:4]
            ],
        }
        for o in opportunities[:limit]
    ]
    summary = workspace.opportunity_summary()
    return {"opportunities": rows, "totals": summary}


def _get_performance(workspace, payload) -> dict[str, Any]:
    transactions = workspace.transactions
    out: dict[str, Any] = {}
    if payload.get("includeTrend", True):
        trend = revenue_timeseries(transactions, freq="W", months=9)
        if trend.get("available"):
            out["trend"] = {
                "last30Days": trend["last30Days"],
                "previous30Days": trend["previous30Days"],
                "changeVsPrevious": trend["change"],
                "weeklyPoints": trend["points"][-14:],
            }
        else:
            out["trend"] = {"available": False, "reason": trend.get("reason")}

    dimension = payload.get("dimension") or "category"
    limit = int(payload.get("limit") or 10)
    rows = dimension_performance(transactions, dimension, limit)
    out["breakdown"] = {"dimension": dimension, "rows": rows}
    if not rows:
        out["breakdown"]["note"] = (
            f"No '{dimension}' information is present in the transaction data."
        )
    return out


def _get_segments(workspace, payload) -> dict[str, Any]:
    metrics = _metrics(workspace)
    return {"segments": segment_summary(metrics), "totalCustomers": int(len(metrics))}


def _get_inventory_summary(workspace, payload) -> dict[str, Any]:
    products = _products(workspace)
    mix_by = payload.get("mixBy") or "category"
    return {
        "overview": inventory_overview(products),
        "mix": {"dimension": mix_by, "rows": dimension_mix(products, mix_by)},
    }


def _simulate(workspace, payload) -> dict[str, Any]:
    kind = payload.get("type")
    if kind == "discount":
        return simulate_discount(
            _products(workspace),
            float(payload.get("discountPct") or 15),
            payload.get("productIds"),
        )
    if kind == "outreach":
        return simulate_outreach(
            _metrics(workspace),
            payload.get("customerIds"),
            payload.get("segment"),
        )
    return {"error": "Unknown simulation type. Use 'discount' or 'outreach'."}


# --------------------------------------------------------------------------- #
def _resolve_customer(metrics: pd.DataFrame, payload: dict[str, Any]) -> pd.Series:
    customer_id = payload.get("customerId")
    if customer_id:
        match = metrics[metrics["customer_id"].astype(str) == str(customer_id)]
        if not match.empty:
            return match.iloc[0]
    name = payload.get("customerName") or customer_id
    if name:
        needle = str(name).strip().lower()
        match = metrics[metrics["display_name"].astype(str).str.lower() == needle]
        if match.empty:
            match = metrics[
                metrics["display_name"].astype(str).str.lower().str.contains(needle, na=False)
            ]
        if not match.empty:
            return match.iloc[0]
    raise ToolError(
        f"No customer matching '{payload.get('customerName') or customer_id}' exists in this data."
    )


def _resolve_product(products: pd.DataFrame, payload: dict[str, Any]) -> pd.Series:
    product_id = payload.get("productId")
    if product_id:
        match = products[products["product_id"].astype(str) == str(product_id)]
        if not match.empty:
            return match.iloc[0]
    name = payload.get("productName") or product_id
    if name:
        needle = str(name).strip().lower()
        match = products[
            products["product_name"].astype(str).str.lower().str.contains(needle, na=False)
        ]
        if match.empty and "sku" in products.columns:
            match = products[products["sku"].astype(str).str.lower() == needle]
        if not match.empty:
            return match.iloc[0]
    raise ToolError(
        f"No product matching '{payload.get('productName') or product_id}' exists in this catalogue."
    )


_HANDLERS = {
    "find_customers": _find_customers,
    "recommend_products_for_customer": _recommend_products_for_customer,
    "recommend_customers_for_product": _recommend_customers_for_product,
    "find_products": _find_products,
    "get_opportunities": _get_opportunities,
    "get_performance": _get_performance,
    "get_segments": _get_segments,
    "get_inventory_summary": _get_inventory_summary,
    "simulate": _simulate,
}
