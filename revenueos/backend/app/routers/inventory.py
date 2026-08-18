"""Inventory list, product detail, and stock intelligence."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..analytics.forecasting import dimension_performance
from ..analytics.inventory import STATUS_META, dimension_mix, inventory_overview
from ..analytics.matching import score_customers_for_product
from ..serialisation import clean_value, frame_to_records, row_to_dict
from ..store import store

router = APIRouter(prefix="/api/inventory", tags=["inventory"])

LIST_FIELDS = [
    "product_id", "sku", "product_name", "brand", "category", "subcategory",
    "color", "size", "season", "price", "original_price", "cost", "stock",
    "retail_value", "margin_pct", "days_in_stock", "days_in_stock_estimated",
    "age_bucket", "units_sold", "units_sold_90d", "sell_through",
    "weekly_velocity", "risk_score", "status", "recommended_action",
    "arrival_date", "gender",
]


def _products() -> pd.DataFrame:
    workspace = store.default()
    workspace.recompute()
    products = workspace.inventory_metrics
    return products if products is not None else pd.DataFrame()


@router.get("")
def list_products(
    search: str | None = None,
    status: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    minPrice: float | None = None,
    maxPrice: float | None = None,
    minRisk: float | None = None,
    inStockOnly: bool = False,
    sortBy: str = "risk_score",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    products = _products()
    if products.empty:
        return {"rows": [], "total": 0, "facets": {}, "hasData": False}

    frame = products
    if search:
        needle = search.strip().lower()
        mask = frame["product_name"].astype(str).str.lower().str.contains(needle, na=False)
        for column in ("sku", "brand", "category", "product_id"):
            if column in frame.columns:
                mask |= frame[column].astype(str).str.lower().str.contains(needle, na=False)
        frame = frame[mask]
    if status:
        frame = frame[frame["status"].astype(str) == status]
    if category:
        frame = frame[frame["category"].astype(str) == category]
    if brand:
        frame = frame[frame["brand"].astype(str) == brand]
    if minPrice is not None:
        frame = frame[frame["price"].fillna(-1) >= minPrice]
    if maxPrice is not None:
        frame = frame[frame["price"].fillna(np.inf) <= maxPrice]
    if minRisk is not None:
        frame = frame[frame["risk_score"].fillna(-1) >= minRisk]
    if inStockOnly:
        frame = frame[frame["stock"].fillna(0) > 0]

    total = int(len(frame))
    sort_column = sortBy if sortBy in frame.columns else "risk_score"
    frame = frame.sort_values(sort_column, ascending=(order == "asc"), na_position="last")
    page = frame.iloc[offset: offset + max(1, min(limit, 200))]

    return {
        "hasData": True,
        "rows": frame_to_records(page, LIST_FIELDS),
        "total": total,
        "offset": offset,
        "limit": limit,
        "facets": {
            "statuses": [s for s in ("Hot", "Healthy", "Slow Moving", "At Risk", "Dead Stock")
                         if s in set(products["status"].dropna())],
            "categories": sorted(products["category"].dropna().unique().tolist())[:100]
            if "category" in products else [],
            "brands": sorted(products["brand"].dropna().unique().tolist())[:150]
            if "brand" in products else [],
            "priceRange": [
                clean_value(products["price"].min()), clean_value(products["price"].max())
            ] if "price" in products else [None, None],
        },
    }


@router.get("/overview")
def overview(mixBy: str = Query("category")) -> dict[str, Any]:
    workspace = store.default()
    workspace.recompute()
    products = _products()
    if products.empty:
        return {"hasData": False}
    return {
        "hasData": True,
        "kpis": inventory_overview(products),
        "statusMeta": STATUS_META,
        "mix": {
            "dimension": mixBy,
            "rows": dimension_mix(products, mixBy),
        },
        "categoryMix": dimension_mix(products, "category"),
        "brandMix": dimension_mix(products, "brand", limit=8),
        "sizeMix": dimension_mix(products, "size", limit=12),
        "colorMix": dimension_mix(products, "color", limit=12),
        "categoryPerformance": dimension_performance(workspace.transactions, "category"),
    }


@router.get("/{product_id}")
def product_detail(product_id: str, customers: int = 10) -> dict[str, Any]:
    workspace = store.default()
    workspace.recompute()
    products = _products()
    if products.empty:
        raise HTTPException(404, "No inventory is loaded.")
    match = products[products["product_id"].astype(str) == str(product_id)]
    if match.empty:
        raise HTTPException(404, f"Product '{product_id}' not found.")
    row = match.iloc[0]

    best_customers: list[dict[str, Any]] = []
    if workspace.customer_metrics is not None and not workspace.customer_metrics.empty \
            and workspace.matching_context is not None:
        best_customers = score_customers_for_product(
            row, workspace.customer_metrics, workspace.matching_context,
            limit=max(1, min(customers, 40)), min_score=0.35,
        )

    return {
        "product": row_to_dict(row),
        "riskDrivers": clean_value(row.get("risk_drivers")) or [],
        "recommendedAction": clean_value(row.get("recommended_action")) or {},
        "statusMeta": STATUS_META.get(str(row.get("status")), {}),
        "bestCustomers": best_customers,
        "salesHistory": _sales_history(workspace, product_id),
    }


def _sales_history(workspace, product_id: str) -> list[dict[str, Any]]:
    transactions = workspace.transactions
    if transactions is None or transactions.empty or "product_id" not in transactions:
        return []
    rows = transactions[transactions["product_id"].astype(str) == str(product_id)]
    if rows.empty or "date" not in rows.columns:
        return []
    rows = rows[rows["date"].notna()].sort_values("date")
    by_month = rows.set_index("date").resample("MS").agg(
        units=("quantity", "sum"), revenue=("net_amount", "sum")
    ).reset_index()
    return [
        {
            "month": r["date"].strftime("%Y-%m"),
            "units": clean_value(r["units"]),
            "revenue": clean_value(r["revenue"]),
        }
        for _, r in by_month.iterrows()
    ]
