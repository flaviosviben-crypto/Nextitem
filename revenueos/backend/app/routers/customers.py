"""Customer list, Customer 360, and the AI profile summary."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..ai.analyst import narrate
from ..ai.context_builder import customer_brief
from ..ai.prompts import customer_summary_system
from ..analytics.matching import build_profile, score_products_for_customer
from ..analytics.rfm import SEGMENT_META, segment_summary
from ..config import settings
from ..serialisation import clean_value, frame_to_records, row_to_dict
from ..store import store

router = APIRouter(prefix="/api/customers", tags=["customers"])

LIST_FIELDS = [
    "customer_id", "display_name", "segment", "segment_reason", "total_spend",
    "order_count", "avg_order_value", "last_purchase_date", "recency_days",
    "expected_cycle_days", "days_overdue", "churn_risk", "customer_score",
    "engagement_score", "predicted_12m_value", "data_confidence", "city",
    "country", "store", "email", "phone", "consent", "purchase_velocity",
]


def _metrics() -> pd.DataFrame:
    workspace = store.default()
    workspace.recompute()
    metrics = workspace.customer_metrics
    if metrics is None or metrics.empty:
        return pd.DataFrame()
    return metrics


@router.get("")
def list_customers(
    search: str | None = None,
    segment: str | None = None,
    city: str | None = None,
    status: str | None = Query(None, description="overdue | active | never"),
    minSpend: float | None = None,
    maxSpend: float | None = None,
    sortBy: str = "customer_score",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    metrics = _metrics()
    if metrics.empty:
        return {"rows": [], "total": 0, "facets": {}, "hasData": False}

    frame = metrics
    if search:
        needle = search.strip().lower()
        mask = frame["display_name"].astype(str).str.lower().str.contains(needle, na=False)
        mask |= frame["customer_id"].astype(str).str.lower().str.contains(needle, na=False)
        for column in ("city", "email"):
            if column in frame.columns:
                mask |= frame[column].astype(str).str.lower().str.contains(needle, na=False)
        frame = frame[mask]
    if segment:
        frame = frame[frame["segment"].astype(str) == segment]
    if city and "city" in frame.columns:
        frame = frame[frame["city"].astype(str) == city]
    if status == "overdue":
        frame = frame[frame["days_overdue"].notna() & (frame["days_overdue"] > 0)]
    elif status == "active":
        frame = frame[frame["days_overdue"].notna() & (frame["days_overdue"] <= 0)]
    elif status == "never":
        frame = frame[frame["recency_days"].isna()]
    if minSpend is not None:
        frame = frame[frame["total_spend"].fillna(-1) >= minSpend]
    if maxSpend is not None:
        frame = frame[frame["total_spend"].fillna(np.inf) <= maxSpend]

    total = int(len(frame))
    sort_column = sortBy if sortBy in frame.columns else "customer_score"
    frame = frame.sort_values(
        sort_column, ascending=(order == "asc"), na_position="last"
    )
    page = frame.iloc[offset: offset + max(1, min(limit, 200))]

    return {
        "hasData": True,
        "rows": frame_to_records(page, LIST_FIELDS),
        "total": total,
        "offset": offset,
        "limit": limit,
        "facets": {
            "segments": sorted(metrics["segment"].dropna().unique().tolist())
            if "segment" in metrics else [],
            "cities": sorted(metrics["city"].dropna().unique().tolist())[:100]
            if "city" in metrics else [],
        },
    }


@router.get("/segments")
def customer_segments() -> dict[str, Any]:
    metrics = _metrics()
    if metrics.empty:
        return {"segments": [], "total": 0}
    return {
        "segments": segment_summary(metrics),
        "total": int(len(metrics)),
        "meta": SEGMENT_META,
    }


@router.get("/{customer_id}")
def customer_detail(customer_id: str, recommendations: int = 6) -> dict[str, Any]:
    """Everything the Customer 360 page shows, computed from real history."""
    workspace = store.default()
    workspace.recompute()
    metrics = _metrics()
    if metrics.empty:
        raise HTTPException(404, "No customer data is loaded.")

    match = metrics[metrics["customer_id"].astype(str) == str(customer_id)]
    if match.empty:
        raise HTTPException(404, f"Customer '{customer_id}' not found.")
    row = match.iloc[0]

    profile = row_to_dict(row)
    profile.pop("purchasedProductIds", None)

    timeline = _timeline(workspace, customer_id)
    matches: list[dict[str, Any]] = []
    if workspace.matching_context is not None:
        matches = score_products_for_customer(
            build_profile(row), workspace.matching_context,
            limit=max(1, min(recommendations, 20)),
        )

    return {
        "customer": profile,
        "affinities": {
            "categories": clean_value(row.get("category_affinity")) or [],
            "brands": clean_value(row.get("brand_affinity")) or [],
            "colors": clean_value(row.get("color_affinity")) or [],
            "sizes": clean_value(row.get("size_affinity")) or [],
            "seasonality": clean_value(row.get("seasonality")) or [],
            "priceBand": {
                "low": clean_value(row.get("price_band_low")),
                "high": clean_value(row.get("price_band_high")),
                "mid": clean_value(row.get("price_band_mid")),
            },
        },
        "timeline": timeline,
        "recommendations": matches,
        "nextBestActions": _next_best_actions(row, matches),
        "segmentMeta": SEGMENT_META.get(str(row.get("segment")), {}),
    }


@router.get("/{customer_id}/summary")
def customer_summary(customer_id: str) -> dict[str, Any]:
    """The AI profile paragraph — narrated from computed facts, never invented."""
    metrics = _metrics()
    if metrics.empty:
        raise HTTPException(404, "No customer data is loaded.")
    match = metrics[metrics["customer_id"].astype(str) == str(customer_id)]
    if match.empty:
        raise HTTPException(404, f"Customer '{customer_id}' not found.")
    row = match.iloc[0]

    payload = customer_brief(row)
    text, mode = narrate(
        customer_summary_system(settings.currency),
        payload,
        fallback=_composed_summary(row),
    )
    return {"summary": text, "mode": mode, "basedOn": payload}


# --------------------------------------------------------------------------- #
def _timeline(workspace, customer_id: str) -> list[dict[str, Any]]:
    transactions = workspace.transactions
    if transactions is None or transactions.empty or "customer_id" not in transactions:
        return []
    rows = transactions[transactions["customer_id"].astype(str) == str(customer_id)]
    if rows.empty:
        return []
    if "date" in rows.columns:
        rows = rows.sort_values("date", ascending=False)

    grouped: dict[str, dict[str, Any]] = {}
    for _, line in rows.iterrows():
        date = line.get("date")
        key = (
            str(line.get("transaction_id"))
            if line.get("transaction_id") is not None and not pd.isna(line.get("transaction_id"))
            else (date.strftime("%Y-%m-%d") if pd.notna(date) else "undated")
        )
        entry = grouped.setdefault(key, {
            "id": key,
            "date": date.strftime("%Y-%m-%d") if pd.notna(date) else None,
            "total": 0.0,
            "hasTotal": False,
            "items": [],
            "store": clean_value(line.get("store")),
        })
        amount = line.get("net_amount")
        if amount is not None and not pd.isna(amount):
            entry["total"] += float(amount)
            entry["hasTotal"] = True
        entry["items"].append({
            "productId": clean_value(line.get("product_id")),
            "name": clean_value(line.get("product_name")),
            "category": clean_value(line.get("category")),
            "brand": clean_value(line.get("brand")),
            "color": clean_value(line.get("color")),
            "size": clean_value(line.get("size")),
            "quantity": clean_value(line.get("quantity")),
            "amount": clean_value(amount),
            "discount": clean_value(line.get("discount")),
        })

    out = []
    for entry in grouped.values():
        entry["total"] = round(entry["total"], 2) if entry.pop("hasTotal") else None
        out.append(entry)
    out.sort(key=lambda e: e["date"] or "", reverse=True)
    return out[:60]


def _next_best_actions(row: pd.Series, matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Concrete actions derived from this customer's own metrics."""
    actions: list[dict[str, Any]] = []
    overdue = row.get("days_overdue")
    segment = row.get("segment")
    discount_rate = row.get("discount_rate")
    name = row.get("display_name") or "this customer"
    first = name.split()[0] if isinstance(name, str) else "this customer"

    if overdue is not None and not pd.isna(overdue) and float(overdue) > 0:
        cycle = row.get("expected_cycle_days")
        actions.append({
            "priority": "high",
            "label": "Contact this week",
            "detail": (
                f"{int(float(overdue))} days past their usual "
                f"{int(float(cycle))}-day rhythm."
                if cycle is not None and not pd.isna(cycle)
                else f"{int(float(overdue))} days past their usual rhythm."
            ),
            "kind": "contact",
        })
    elif overdue is not None and not pd.isna(overdue):
        due = row.get("next_purchase_due")
        actions.append({
            "priority": "low",
            "label": "In their normal window",
            "detail": (
                f"Next purchase expected around {pd.Timestamp(due).strftime('%d %b %Y')}."
                if due is not None and not pd.isna(due) else "No outreach needed yet."
            ),
            "kind": "monitor",
        })

    if matches:
        top = matches[0]
        actions.append({
            "priority": "high",
            "label": f"Recommend {top['productName']}",
            "detail": top["headline"],
            "kind": "recommend",
            "productId": top["productId"],
        })
        brands = row.get("brand_affinity")
        if isinstance(brands, list) and brands:
            brand = brands[0].get("value")
            actions.append({
                "priority": "medium",
                "label": f"Invite to the next {brand} preview",
                "detail": f"{brands[0].get('share', 0):.0%} of their spend goes to {brand}.",
                "kind": "invite",
            })

    if discount_rate is not None and not pd.isna(discount_rate):
        rate = float(discount_rate)
        if rate <= 0.15:
            actions.append({
                "priority": "medium",
                "label": "Do not discount",
                "detail": f"Only {rate:.0%} of their purchases were on markdown — "
                          "price is not their objection.",
                "kind": "pricing",
            })
        elif rate >= 0.55:
            actions.append({
                "priority": "medium",
                "label": "Save for the private sale",
                "detail": f"{rate:.0%} of their purchases were discounted. "
                          "They respond to events, not full-price outreach.",
                "kind": "pricing",
            })

    if segment in {"High Potential", "Promising"}:
        actions.append({
            "priority": "medium",
            "label": "Book a styling appointment",
            "detail": f"{first} is trending above average for their tenure — "
                      "personal attention now compounds.",
            "kind": "appointment",
        })
    return actions[:5]


def _composed_summary(row: pd.Series) -> str:
    """Deterministic profile sentence, assembled only from present values."""
    name = row.get("display_name") or "This customer"
    first = str(name).split()[0]
    parts: list[str] = []

    segment = row.get("segment")
    spend = row.get("total_spend")
    orders = row.get("order_count")
    opening = f"{first} is a {str(segment).lower()} customer" if segment else f"{first}"
    if spend is not None and not pd.isna(spend) and orders is not None and not pd.isna(orders):
        opening += f" with €{float(spend):,.0f} of lifetime spend across {int(orders)} orders"
    parts.append(opening + ".")

    cycle = row.get("expected_cycle_days")
    overdue = row.get("days_overdue")
    if cycle is not None and not pd.isna(cycle):
        weeks = float(cycle) / 7
        sentence = f"They typically shop every {weeks:.0f} weeks"
        if overdue is not None and not pd.isna(overdue) and float(overdue) > 0:
            sentence += f" and are currently {int(float(overdue))} days overdue"
        parts.append(sentence + ".")

    categories = row.get("category_affinity")
    brands = row.get("brand_affinity")
    if isinstance(categories, list) and categories:
        top = categories[0]
        sentence = f"Their spend concentrates in {top['value']} ({top['share']:.0%})"
        if isinstance(brands, list) and brands:
            sentence += f", mostly {brands[0]['value']}"
        parts.append(sentence + ".")

    low, high = row.get("price_band_low"), row.get("price_band_high")
    if low is not None and not pd.isna(low) and high is not None and not pd.isna(high):
        parts.append(f"They usually buy in the €{float(low):,.0f}–€{float(high):,.0f} range.")

    discount = row.get("discount_rate")
    if discount is not None and not pd.isna(discount):
        rate = float(discount)
        parts.append(
            "They rarely buy on markdown." if rate <= 0.2
            else f"{rate:.0%} of their purchases were discounted."
        )
    return " ".join(parts)
