"""Build minimal, privacy-safe context payloads for the LLM.

Two rules govern everything here:

1. **The LLM never computes.** It receives *results* — numbers already produced
   by the deterministic analytics layer — and turns them into language. It is
   never asked to add, average or rank.
2. **Minimise personal data.** Under ``REVENUEOS_MINIMISE_PII`` (on by default)
   emails, phone numbers and exact addresses are stripped before anything
   leaves the process. Customers are identified by internal ID plus a display
   name, because a boutique owner needs to recognise who to call — that is the
   product's purpose — but nothing more than that is ever sent.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..config import settings

# Fields that must never reach the model when PII minimisation is on.
PII_FIELDS = {"email", "phone", "notes", "birth_date", "address", "full_name",
              "first_name", "last_name"}


def scrub(record: dict[str, Any], keep_name: bool = True) -> dict[str, Any]:
    """Drop direct identifiers from a record before it is sent to the model."""
    if not settings.minimise_pii:
        return record
    out = {}
    for key, value in record.items():
        camel = key[0].lower() + key[1:] if key else key
        if camel in PII_FIELDS or key in PII_FIELDS:
            continue
        out[key] = value
    if keep_name and "name" not in out:
        for candidate in ("displayName", "customerName"):
            if candidate in record:
                out["name"] = record[candidate]
                break
    return out


def _num(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(number) or np.isinf(number):
        return None
    return round(number, digits)


def customer_brief(row: pd.Series, include_affinities: bool = True) -> dict[str, Any]:
    """A compact, PII-minimised view of one customer."""
    brief: dict[str, Any] = {
        "id": str(row.get("customer_id")),
        "name": row.get("display_name"),
        "segment": row.get("segment"),
        "segmentReason": row.get("segment_reason"),
        "lifetimeSpend": _num(row.get("total_spend"), 0),
        "orders": _num(row.get("order_count"), 0),
        "avgBasket": _num(row.get("avg_order_value"), 0),
        "daysSinceLastPurchase": _num(row.get("recency_days"), 0),
        "expectedCycleDays": _num(row.get("expected_cycle_days"), 0),
        "daysOverdue": _num(row.get("days_overdue"), 0),
        "churnRisk": _num(row.get("churn_risk"), 3),
        "customerScore": _num(row.get("customer_score"), 1),
        "predicted12mValue": _num(row.get("predicted_12m_value"), 0),
        "dataConfidence": row.get("data_confidence"),
        "city": row.get("city"),
        "store": row.get("store"),
    }
    if include_affinities:
        for key, source in (("topCategories", "category_affinity"),
                            ("topBrands", "brand_affinity"),
                            ("topColours", "color_affinity"),
                            ("sizes", "size_affinity")):
            value = row.get(source)
            if isinstance(value, list) and value:
                brief[key] = [
                    {"value": item.get("value"), "share": _num(item.get("share"), 3)}
                    for item in value[:3] if isinstance(item, dict)
                ]
        band_low, band_high = row.get("price_band_low"), row.get("price_band_high")
        if band_low is not None and not pd.isna(band_low):
            brief["typicalPriceRange"] = [_num(band_low, 0), _num(band_high, 0)]
        discount = _num(row.get("discount_rate"), 3)
        if discount is not None:
            brief["shareOfPurchasesDiscounted"] = discount

    return {k: v for k, v in brief.items() if v is not None}


def product_brief(row: pd.Series) -> dict[str, Any]:
    brief = {
        "id": str(row.get("product_id")),
        "name": row.get("product_name"),
        "brand": row.get("brand"),
        "category": row.get("category"),
        "colour": row.get("color"),
        "size": row.get("size"),
        "price": _num(row.get("price"), 0),
        "stock": _num(row.get("stock"), 0),
        "daysInStock": _num(row.get("days_in_stock"), 0),
        "unitsSold": _num(row.get("units_sold"), 0),
        "sellThrough": _num(row.get("sell_through"), 3),
        "status": row.get("status"),
        "riskScore": _num(row.get("risk_score"), 0),
        "stockValue": _num(row.get("retail_value"), 0),
        "marginPct": _num(row.get("margin_pct"), 0),
    }
    return {k: v for k, v in brief.items() if v is not None}


def workspace_overview(workspace) -> dict[str, Any]:
    """The always-on context header: what this boutique's data actually is."""
    workspace.recompute()
    metrics = workspace.customer_metrics
    products = workspace.inventory_metrics
    quality = workspace.quality or {}

    overview: dict[str, Any] = {
        "boutique": workspace.name,
        "currency": settings.currency,
        "dataHealthScore": quality.get("score"),
        "counts": {
            "customers": int(len(metrics)) if metrics is not None else 0,
            "products": int(len(products)) if products is not None else 0,
            "transactions": int(len(workspace.transactions))
            if workspace.transactions is not None else 0,
        },
        "capabilitiesUnavailable": [
            c["label"] for c in quality.get("capabilities", [])
            if c.get("status") == "unavailable"
        ],
    }

    if metrics is not None and not metrics.empty:
        spend = metrics["total_spend"].dropna()
        overview["customerBase"] = {
            "totalLifetimeSpend": _num(spend.sum(), 0) if not spend.empty else None,
            "medianLifetimeSpend": _num(spend.median(), 0) if not spend.empty else None,
            "segments": metrics["segment"].value_counts().to_dict()
            if "segment" in metrics else {},
        }
    if products is not None and not products.empty:
        overview["inventory"] = {
            "skus": int(len(products)),
            "statusCounts": products["status"].value_counts().to_dict()
            if "status" in products else {},
            "stockValue": _num(products["retail_value"].dropna().sum(), 0)
            if "retail_value" in products else None,
        }
    return overview


def truncate_rows(rows: list[dict[str, Any]], limit: int = 25) -> dict[str, Any]:
    """Cap how much data is sent, and say so explicitly rather than silently."""
    if len(rows) <= limit:
        return {"rows": rows, "returned": len(rows), "total": len(rows)}
    return {
        "rows": rows[:limit],
        "returned": limit,
        "total": len(rows),
        "note": f"Only the top {limit} of {len(rows)} rows are shown.",
    }
