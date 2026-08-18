"""Campaign builder: audience → estimated value → products → draft outreach."""

from __future__ import annotations

import time
import uuid
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..ai.analyst import narrate
from ..ai.prompts import campaign_system
from ..analytics.forecasting import simulate_outreach
from ..analytics.matching import build_profile, score_products_for_customer
from ..config import settings
from ..serialisation import clean_value
from ..store import store

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

TEMPLATES = [
    {
        "key": "vip_private_sale",
        "name": "VIP private sale",
        "description": "A closed-door event for your highest-value clients.",
        "audience": {"segments": ["Champions", "VIP", "Loyal"]},
        "tone": "An exclusive preview before anyone else sees it.",
    },
    {
        "key": "new_collection",
        "name": "New collection preview",
        "description": "Announce new arrivals to the clients whose taste matches them.",
        "audience": {"segments": ["Champions", "VIP", "Loyal", "High Potential", "Promising"],
                     "maxDaysOverdue": 60},
        "tone": "A personal heads-up about pieces chosen with them in mind.",
    },
    {
        "key": "reactivate_lost",
        "name": "Reactivate lapsed customers",
        "description": "Bring back customers who have drifted past their window.",
        "audience": {"segments": ["At Risk", "Sleeping", "Lost"], "overdueOnly": True},
        "tone": "A warm reconnection, not a discount blast.",
    },
    {
        "key": "slow_movers",
        "name": "Move slow stock at full price",
        "description": "Target the clients most likely to buy what is sitting still.",
        "audience": {"segments": None},
        "productStatus": ["Slow Moving", "At Risk", "Dead Stock"],
        "tone": "A styling suggestion built around specific pieces.",
    },
    {
        "key": "markdown_event",
        "name": "Markdown event",
        "description": "For the customers who genuinely buy on promotion.",
        "audience": {"segments": ["Discount Driven"]},
        "tone": "A straightforward sale announcement.",
    },
]


class BuildRequest(BaseModel):
    template: str | None = None
    name: str | None = None
    segments: list[str] | None = None
    overdueOnly: bool = False
    minSpend: float | None = None
    productStatus: list[str] | None = None
    category: str | None = None
    brand: str | None = None
    maxAudience: int = Field(default=200, ge=1, le=2000)
    language: str = "English"


@router.get("/templates")
def list_templates() -> dict[str, Any]:
    return {"templates": TEMPLATES}


@router.get("")
def list_campaigns() -> dict[str, Any]:
    workspace = store.default()
    return {"campaigns": workspace.campaigns}


@router.post("/build")
def build_campaign(request: BuildRequest) -> dict[str, Any]:
    """Assemble a campaign: who, what, how much it is worth, and a draft message."""
    workspace = store.default()
    workspace.recompute()
    metrics = workspace.customer_metrics
    if metrics is None or metrics.empty:
        raise HTTPException(400, "No customer data is loaded.")

    template = next((t for t in TEMPLATES if t["key"] == request.template), None)
    segments = request.segments
    if segments is None and template:
        segments = template["audience"].get("segments")
    product_status = request.productStatus or (template or {}).get("productStatus")

    audience = metrics
    criteria: list[str] = []
    if segments:
        audience = audience[audience["segment"].isin(segments)]
        criteria.append(f"Segments: {', '.join(segments)}")
    if request.overdueOnly or (template and template["audience"].get("overdueOnly")):
        audience = audience[audience["days_overdue"].fillna(-1) > 0]
        criteria.append("Past their normal repurchase window")
    if request.minSpend is not None:
        audience = audience[audience["total_spend"].fillna(0) >= request.minSpend]
        criteria.append(f"Lifetime spend at least €{request.minSpend:,.0f}")
    if "consent" in audience.columns and audience["consent"].notna().any():
        before = len(audience)
        consented = audience[
            ~audience["consent"].astype(str).str.strip().str.lower().isin(
                {"no", "false", "0", "n", "opt out", "opted out"}
            )
        ]
        if len(consented) < before:
            criteria.append(
                f"{before - len(consented)} customer(s) without marketing consent excluded"
            )
        audience = consented

    if audience.empty:
        raise HTTPException(400, "No customers matched those criteria.")

    audience = audience.sort_values("customer_score", ascending=False).head(request.maxAudience)

    products = _select_products(workspace, product_status, request.category, request.brand)
    recommendations = _per_customer_products(workspace, audience, products)

    projection = simulate_outreach(audience)
    payload = {
        "campaign": request.name or (template["name"] if template else "Custom campaign"),
        "tone": (template or {}).get("tone", "Personal and specific."),
        "language": request.language,
        "audienceSize": int(len(audience)),
        "selectionCriteria": criteria,
        "topSegments": audience["segment"].value_counts().head(4).to_dict()
        if "segment" in audience else {},
        "featuredProducts": [
            {"name": p["name"], "brand": p["brand"], "category": p["category"],
             "price": p["price"]}
            for p in products[:4]
        ],
        "estimatedRevenue": projection.get("expectedRevenue"),
        "avgBasket": projection.get("avgBasket"),
    }
    message, mode = narrate(
        campaign_system(settings.currency), payload, _composed_message(payload)
    )

    campaign = {
        "id": f"cmp_{uuid.uuid4().hex[:10]}",
        "name": payload["campaign"],
        "template": request.template,
        "createdAt": time.time(),
        "audienceSize": int(len(audience)),
        "selectionCriteria": criteria,
        "projection": projection,
        "message": message,
        "messageMode": mode,
        "language": request.language,
        "products": products[:12],
        "audience": [
            {
                "customerId": str(row["customer_id"]),
                "name": row.get("display_name"),
                "segment": row.get("segment"),
                "totalSpend": clean_value(row.get("total_spend")),
                "avgOrderValue": clean_value(row.get("avg_order_value")),
                "daysOverdue": clean_value(row.get("days_overdue")),
                "hasEmail": bool(row.get("email")),
                "hasPhone": bool(row.get("phone")),
                "recommended": recommendations.get(str(row["customer_id"]), []),
            }
            for _, row in audience.head(60).iterrows()
        ],
    }
    workspace.campaigns = [c for c in workspace.campaigns if c["id"] != campaign["id"]]
    workspace.campaigns.insert(0, {k: v for k, v in campaign.items() if k != "audience"})
    workspace.campaigns = workspace.campaigns[:20]
    store.persist(workspace)

    return campaign


@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: str) -> dict[str, Any]:
    workspace = store.default()
    workspace.campaigns = [c for c in workspace.campaigns if c["id"] != campaign_id]
    store.persist(workspace)
    return {"deleted": campaign_id}


# --------------------------------------------------------------------------- #
def _select_products(workspace, statuses, category, brand) -> list[dict[str, Any]]:
    products = workspace.inventory_metrics
    if products is None or products.empty:
        return []
    frame = products[products["stock"].fillna(1) > 0]
    if statuses:
        frame = frame[frame["status"].isin(statuses)]
    if category:
        frame = frame[frame["category"].astype(str) == category]
    if brand:
        frame = frame[frame["brand"].astype(str) == brand]
    if frame.empty:
        return []
    frame = frame.sort_values("retail_value", ascending=False).head(12)
    return [
        {
            "productId": str(row["product_id"]),
            "name": row.get("product_name"),
            "brand": row.get("brand"),
            "category": row.get("category"),
            "price": clean_value(row.get("price")),
            "stock": clean_value(row.get("stock")),
            "status": row.get("status"),
        }
        for _, row in frame.iterrows()
    ]


def _per_customer_products(workspace, audience, products) -> dict[str, list[dict[str, Any]]]:
    ctx = workspace.matching_context
    if ctx is None:
        return {}
    allowed = {p["productId"] for p in products} if products else None
    out: dict[str, list[dict[str, Any]]] = {}
    for _, row in audience.head(60).iterrows():
        product_filter = None
        if allowed:
            product_filter = ctx.products["product_id"].astype(str).isin(allowed)
        matches = score_products_for_customer(
            build_profile(row), ctx, limit=2, product_filter=product_filter
        )
        out[str(row["customer_id"])] = [
            {"productId": m["productId"], "name": m["productName"],
             "matchPct": m["scorePct"], "price": m["price"]}
            for m in matches
        ]
    return out


def _composed_message(payload: dict[str, Any]) -> str:
    products = payload.get("featuredProducts") or []
    piece = products[0]["name"] if products else "a few pieces"
    return (
        f"Hello [Name],\n\n"
        f"We have set aside {piece} that we think suits you, based on what you have "
        "chosen with us before.\n\n"
        "If you would like to see it, reply here and we will hold it for you or arrange "
        "a time that works.\n\n"
        "Warm regards,\nThe team"
    )
