"""Campaign builder: pick an audience from computed signals, then draft outreach."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..analytics import matching
from ..workspace import workspace

router = APIRouter(tags=["campaigns"])

TEMPLATES: dict[str, dict[str, Any]] = {
    "vip_private_sale": {
        "name": "VIP Private Sale",
        "goal": "Give your best customers first access before anything goes public.",
        "criteria": "Top-tier customers by value and frequency, with consent on file",
    },
    "new_collection": {
        "name": "New Collection Preview",
        "goal": "Put the newest arrivals in front of the customers most likely to buy them.",
        "criteria": "Strong affinity matches against products that arrived in the last 60 days",
    },
    "reactivate_lapsed": {
        "name": "Reactivate Lapsed Customers",
        "goal": "Bring back valuable customers who have gone quiet.",
        "criteria": "At Risk or Sleeping customers with meaningful spending history",
    },
    "slow_movers": {
        "name": "Move Slow Stock",
        "goal": "Sell ageing stock at full price through personal outreach, not markdown.",
        "criteria": "Customers whose affinity matches products classed At Risk or Dead Stock",
    },
}


class CampaignRequest(BaseModel):
    template: str
    limit: int = 40
    contactable_only: bool = True


@router.get("/campaigns/templates")
def templates() -> dict[str, Any]:
    return {"templates": [{"id": k, **v} for k, v in TEMPLATES.items()]}


@router.post("/campaigns/build")
def build(payload: CampaignRequest) -> dict[str, Any]:
    if payload.template not in TEMPLATES:
        raise HTTPException(404, "Unknown campaign template.")
    if not workspace.is_loaded:
        raise HTTPException(400, "Load a dataset first.")

    template = TEMPLATES[payload.template]
    audience, products = _audience_for(payload.template, payload.limit, payload.contactable_only)
    if not audience:
        return {**template, "id": payload.template, "audience": [], "products": [],
                "estimated_value": 0,
                "note": "No customers currently match this campaign's criteria."}

    estimated = 0.0
    for row in audience:
        estimated += row.get("expected_value") or 0

    campaign = {
        "id": payload.template,
        **template,
        "audience_size": len(audience),
        "audience": audience,
        "products": products,
        "estimated_value": round(estimated, 2),
        "contactable": sum(1 for a in audience if a.get("contactable")),
    }
    # Imported here, not at module scope: this pulls in the Anthropic SDK,
    # which is the single largest cost of starting the API and is needed only
    # when an AI surface is actually called. Paying it on every boot delays
    # the port opening, which is what a platform waits for.
    from ..ai import analyst as analyst_ai

    copy = analyst_ai.campaign_copy(campaign)
    campaign.update({"rationale": copy.get("rationale"), "message": copy.get("message"),
                     "engine": copy.get("engine")})
    return campaign


def _audience_for(template: str, limit: int, contactable_only: bool):
    profiles = workspace.profiles
    if contactable_only:
        profiles = [p for p in profiles if p.get("contactable")]

    products: list[dict[str, Any]] = []
    if template == "vip_private_sale":
        pool = [p for p in profiles if p.get("value_tier") in {"VIP", "Promising"}]
        pool.sort(key=lambda p: -(p.get("total_spend") or 0))
    elif template == "new_collection":
        products = [p for p in workspace.products
                    if (p.get("days_in_stock") or 999) <= 60 and (p.get("stock") or 0) > 0]
        products.sort(key=lambda p: -(p.get("price") or 0))
        pool = profiles
    elif template == "reactivate_lapsed":
        pool = [p for p in profiles if p.get("lifecycle") in {"At Risk", "Lost"}
                and (p.get("total_spend") or 0) > 0]
        pool.sort(key=lambda p: -(p.get("total_spend") or 0))
    else:  # slow_movers
        products = [p for p in workspace.products
                    if p.get("risk_class") in {"At Risk", "Dead Stock"} and (p.get("stock") or 0) > 0]
        products.sort(key=lambda p: -(p.get("stock_value") or 0))
        pool = profiles

    candidate_products = products or workspace.products
    audience = []
    for p in pool[:limit * 3]:
        best = (matching.best_products_for_customer(
            p, candidate_products, limit=1,
            min_score=0.45 if template in {"new_collection", "slow_movers"} else 0.3)
            if workspace.product_matching_available else [])
        if template in {"new_collection", "slow_movers"} and not best:
            continue
        audience.append({
            "customer_id": p["customer_id"],
            "name": p["name"],
            "value_tier": p.get("value_tier"),
            "lifecycle": p.get("lifecycle"),
            "top_category": p.get("top_category"),
            "total_spend": p.get("total_spend"),
            "contactable": p.get("contactable", False),
            "product": ({"sku": best[0]["sku"], "name": best[0]["product_name"],
                         "match_pct": best[0]["match_pct"], "price": best[0]["price"],
                         "why": best[0]["why"]} if best else None),
            "expected_value": matching.expected_value(best[0], p) if best else None,
        })
        if len(audience) >= limit:
            break

    product_payload = [{"sku": p["sku"], "name": p["product_name"], "price": p.get("price"),
                        "category": p.get("category"), "brand": p.get("brand"),
                        "stock": p.get("stock")} for p in products[:8]]
    return audience, product_payload
