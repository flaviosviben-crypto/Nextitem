"""The recommendation engine's public surface: all five modes."""

from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..analytics.matching import (
    BASE_WEIGHTS,
    SIGNAL_LABELS,
    build_profile,
    score_customers_for_product,
    score_products_for_customer,
)
from ..serialisation import clean_value
from ..store import store

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])

MODES = {
    "for_customer": "Best products for a customer",
    "for_product": "Best customers for a product",
    "cross_sell": "Cross-sell into a new category",
    "reactivation": "Win back inactive customers",
    "vip": "VIP priority recommendations",
    "dead_stock": "Dead stock rescue",
}


def _context():
    workspace = store.default()
    workspace.recompute()
    if workspace.matching_context is None or workspace.customer_metrics is None \
            or workspace.customer_metrics.empty:
        raise HTTPException(
            400,
            "Recommendations need both a customer list and an inventory catalogue. "
            "Upload the missing file, or load the demo boutique.",
        )
    return workspace


@router.get("/methodology")
def methodology() -> dict[str, Any]:
    """How the match score is built — shown in the UI so the score is auditable."""
    workspace = store.default()
    workspace.recompute()
    ctx = workspace.matching_context
    return {
        "weights": [
            {"key": key, "label": SIGNAL_LABELS[key], "weight": weight}
            for key, weight in sorted(BASE_WEIGHTS.items(), key=lambda kv: -kv[1])
        ],
        "principle": (
            "Weights are relative. Any signal that cannot be computed for a given "
            "customer-product pair is removed and its weight is redistributed across "
            "the remaining signals, so missing information never counts as a negative. "
            "The resulting score is reported alongside a separate data confidence "
            "describing how much evidence it rests on."
        ),
        "unavailableSignals": ctx.notes if ctx else [],
        "confidenceLevels": {
            "high": "8+ signals available and 4+ purchases of history.",
            "medium": "Most signals available, at least 2 purchases.",
            "low": "A minority of signals, or a single purchase.",
            "very low": "Almost no usable signal — treat as a suggestion, not a prediction.",
        },
    }


@router.get("/for-customer/{customer_id}")
def for_customer(customer_id: str, limit: int = 12,
                 category: str | None = None,
                 inStockOnly: bool = True) -> dict[str, Any]:
    workspace = _context()
    metrics = workspace.customer_metrics
    match = metrics[metrics["customer_id"].astype(str) == str(customer_id)]
    if match.empty:
        raise HTTPException(404, f"Customer '{customer_id}' not found.")
    row = match.iloc[0]

    products = workspace.matching_context.products
    product_filter = None
    if category:
        product_filter = products["category"].astype(str) == category

    results = score_products_for_customer(
        build_profile(row), workspace.matching_context,
        limit=max(1, min(limit, 60)), only_in_stock=inStockOnly,
        product_filter=product_filter,
    )
    return {
        "mode": "for_customer",
        "customer": {
            "customerId": str(row["customer_id"]),
            "name": row.get("display_name"),
            "segment": row.get("segment"),
            "totalSpend": clean_value(row.get("total_spend")),
            "dataConfidence": row.get("data_confidence"),
        },
        "results": results,
    }


@router.get("/for-product/{product_id}")
def for_product(product_id: str, limit: int = 20,
                segment: str | None = None,
                minScore: float = 0.4) -> dict[str, Any]:
    workspace = _context()
    products = workspace.inventory_metrics
    match = products[products["product_id"].astype(str) == str(product_id)]
    if match.empty:
        raise HTTPException(404, f"Product '{product_id}' not found.")
    product = match.iloc[0]

    customers = workspace.customer_metrics
    if segment:
        customers = customers[customers["segment"].astype(str) == segment]

    results = score_customers_for_product(
        product, customers, workspace.matching_context,
        limit=max(1, min(limit, 100)), min_score=minScore,
    )
    return {
        "mode": "for_product",
        "product": {
            "productId": str(product["product_id"]),
            "name": product.get("product_name"),
            "brand": product.get("brand"),
            "category": product.get("category"),
            "price": clean_value(product.get("price")),
            "stock": clean_value(product.get("stock")),
            "status": product.get("status"),
            "riskScore": clean_value(product.get("risk_score")),
        },
        "results": results,
    }


@router.get("/mode/{mode}")
def by_mode(mode: str, limit: int = 12,
            perCustomer: int = Query(3, ge=1, le=6)) -> dict[str, Any]:
    """Batch modes: cross-sell, reactivation, VIP, dead stock rescue."""
    if mode not in MODES:
        raise HTTPException(404, f"Unknown mode '{mode}'. Options: {list(MODES)}")
    workspace = _context()
    metrics = workspace.customer_metrics
    ctx = workspace.matching_context
    products = workspace.inventory_metrics

    if mode == "dead_stock":
        stuck = products[
            products["status"].isin(["At Risk", "Dead Stock"])
            & (products["stock"].fillna(0) > 0)
        ].sort_values("retail_value", ascending=False).head(max(1, min(limit, 30)))
        rows = []
        for _, product in stuck.iterrows():
            matches = score_customers_for_product(product, metrics, ctx, limit=6, min_score=0.45)
            rows.append({
                "product": {
                    "productId": str(product["product_id"]),
                    "name": product.get("product_name"),
                    "brand": product.get("brand"),
                    "category": product.get("category"),
                    "price": clean_value(product.get("price")),
                    "stock": clean_value(product.get("stock")),
                    "retailValue": clean_value(product.get("retail_value")),
                    "daysInStock": clean_value(product.get("days_in_stock")),
                    "riskScore": clean_value(product.get("risk_score")),
                    "status": product.get("status"),
                },
                "customers": matches,
            })
        return {"mode": mode, "label": MODES[mode], "rows": rows}

    pool = metrics
    if mode == "vip":
        pool = pool[pool["segment"].isin(["Champions", "VIP", "Loyal"])]
        pool = pool.sort_values("customer_score", ascending=False)
    elif mode == "reactivation":
        pool = pool[pool["segment"].isin(["At Risk", "Sleeping", "Lost"])]
        pool = pool.sort_values("total_spend", ascending=False)
    elif mode == "cross_sell":
        pool = pool[pool["order_count"].fillna(0) >= 2]
        pool = pool.sort_values("customer_score", ascending=False)
    else:
        pool = pool.sort_values("customer_score", ascending=False)

    rows = []
    for _, row in pool.head(max(1, min(limit, 40))).iterrows():
        profile = build_profile(row)
        product_filter = None
        if mode == "cross_sell" and profile.categories:
            owned = set(profile.categories)
            categories = ctx.products["category"].astype(str).str.lower()
            product_filter = ~categories.isin(owned)
        matches = score_products_for_customer(
            profile, ctx, limit=perCustomer, product_filter=product_filter,
        )
        if not matches:
            continue
        rows.append({
            "customer": {
                "customerId": profile.customer_id,
                "name": profile.name,
                "segment": row.get("segment"),
                "totalSpend": clean_value(row.get("total_spend")),
                "daysOverdue": clean_value(row.get("days_overdue")),
                "avgOrderValue": clean_value(row.get("avg_order_value")),
                "dataConfidence": row.get("data_confidence"),
            },
            "products": matches,
        })
    return {"mode": mode, "label": MODES[mode], "rows": rows}
