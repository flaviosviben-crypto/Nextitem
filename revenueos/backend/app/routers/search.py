"""Global search — the data source behind the ⌘K command palette."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..serialisation import clean_value
from ..store import store

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(q: str = "", limit: int = 8) -> dict[str, Any]:
    workspace = store.default()
    workspace.recompute()
    needle = (q or "").strip().lower()
    if not needle:
        return {"customers": [], "products": [], "query": q}

    customers: list[dict[str, Any]] = []
    metrics = workspace.customer_metrics
    if metrics is not None and not metrics.empty:
        mask = metrics["display_name"].astype(str).str.lower().str.contains(needle, na=False)
        mask |= metrics["customer_id"].astype(str).str.lower().str.contains(needle, na=False)
        if "city" in metrics.columns:
            mask |= metrics["city"].astype(str).str.lower().str.contains(needle, na=False)
        hits = metrics[mask].sort_values("customer_score", ascending=False).head(limit)
        customers = [
            {
                "customerId": str(row["customer_id"]),
                "name": row.get("display_name"),
                "segment": row.get("segment"),
                "totalSpend": clean_value(row.get("total_spend")),
                "city": row.get("city"),
            }
            for _, row in hits.iterrows()
        ]

    products: list[dict[str, Any]] = []
    catalogue = workspace.inventory_metrics
    if catalogue is not None and not catalogue.empty:
        mask = catalogue["product_name"].astype(str).str.lower().str.contains(needle, na=False)
        for column in ("brand", "category", "sku", "product_id"):
            if column in catalogue.columns:
                mask |= catalogue[column].astype(str).str.lower().str.contains(needle, na=False)
        hits = catalogue[mask].sort_values("retail_value", ascending=False).head(limit)
        products = [
            {
                "productId": str(row["product_id"]),
                "name": row.get("product_name"),
                "brand": row.get("brand"),
                "category": row.get("category"),
                "price": clean_value(row.get("price")),
                "stock": clean_value(row.get("stock")),
                "status": row.get("status"),
            }
            for _, row in hits.iterrows()
        ]

    return {"query": q, "customers": customers, "products": products}
