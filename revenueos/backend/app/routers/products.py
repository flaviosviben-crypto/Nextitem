"""Inventory list, product detail, and best-customers-for-product."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..analytics import forecasting, matching
from ..workspace import workspace

router = APIRouter(tags=["inventory"])

SORTABLE = {"risk_score", "stock_value", "days_in_stock", "units_sold", "sell_through",
            "price", "stock", "revenue"}


@router.get("/products")
def list_products(
    q: str = "",
    category: str = "",
    brand: str = "",
    risk_class: str = "",
    in_stock_only: bool = False,
    sort: str = "risk_score",
    direction: str = "desc",
    limit: int = Query(60, le=500),
    offset: int = 0,
) -> dict[str, Any]:
    rows = workspace.products
    if q:
        needle = q.lower()
        rows = [p for p in rows if needle in (p.get("product_name") or "").lower()
                or needle in str(p.get("sku", "")).lower()
                or needle in (p.get("category") or "").lower()
                or needle in (p.get("brand") or "").lower()]
    if category:
        rows = [p for p in rows if (p.get("category") or "") == category]
    if brand:
        rows = [p for p in rows if (p.get("brand") or "") == brand]
    if risk_class:
        rows = [p for p in rows if (p.get("risk_class") or "") == risk_class]
    if in_stock_only:
        rows = [p for p in rows if (p.get("stock") or 0) > 0]

    key = sort if sort in SORTABLE else "risk_score"
    reverse = direction != "asc"
    rows = sorted(rows, key=lambda p: (p.get(key) is not None, p.get(key) or 0), reverse=reverse)

    return {
        "total": len(rows),
        "offset": offset,
        "limit": limit,
        "products": rows[offset:offset + limit],
        "facets": {
            "categories": sorted({p.get("category") for p in workspace.products if p.get("category")}),
            "brands": sorted({p.get("brand") for p in workspace.products if p.get("brand")}),
            "risk_classes": sorted({p.get("risk_class") for p in workspace.products
                                    if p.get("risk_class")}),
        },
    }


@router.get("/inventory/overview")
def overview() -> dict[str, Any]:
    if not workspace.is_loaded:
        raise HTTPException(404, "No dataset loaded.")
    return {
        "summary": workspace.summary.get("inventory", {}),
        "ageing": forecasting.inventory_ageing(workspace.products),
        "categories": forecasting.category_performance(workspace.transactions_raw,
                                                       workspace.products, limit=10),
        "brands": forecasting.brand_performance(workspace.transactions_raw, limit=10),
    }


@router.get("/products/{sku}")
def product_detail(sku: str) -> dict[str, Any]:
    product = workspace.product(sku)
    if not product:
        raise HTTPException(404, "Product not found.")

    buyers = matching.best_customers_for_product(product, workspace.profiles, limit=12)
    sales = [t for t in workspace.transactions_raw if str(t.get("sku")) == str(sku)]
    sales.sort(key=lambda t: t.get("date") or "", reverse=True)

    return {
        "product": product,
        "best_customers": buyers,
        "recent_sales": [{
            "date": str(t.get("date")) if t.get("date") else None,
            "customer_id": t.get("customer_id"),
            "amount": t.get("line_total"),
            "quantity": t.get("quantity"),
            "store": t.get("store"),
        } for t in sales[:20]],
        "sales_count": len(sales),
    }


@router.get("/products/{sku}/customers")
def customers_for_product(sku: str, limit: int = Query(15, le=100),
                          contactable_only: bool = False) -> dict[str, Any]:
    product = workspace.product(sku)
    if not product:
        raise HTTPException(404, "Product not found.")
    matches = matching.best_customers_for_product(
        product, workspace.profiles, limit=limit, consented_only=contactable_only)
    return {"product": product, "matches": matches}


@router.get("/trend")
def trend(months: int = Query(12, le=36)) -> dict[str, Any]:
    return {"monthly": forecasting.monthly_trend(workspace.transactions_raw, months=months)}
