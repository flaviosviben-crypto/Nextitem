"""Customer list and Customer Detail.

Customer Detail exists to answer one question in under ten seconds: *why is
RevenueOS telling me to contact this person?* Every field on it is either that
answer or the evidence behind it.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..analytics import matching, segmentation
from ..workspace import workspace

router = APIRouter(tags=["customers"])

SORTABLE = {"customer_score", "total_spend", "avg_order_value", "recency_days",
            "cycle_position", "potential_annual_value", "order_count", "name"}


@router.get("/customers")
def list_customers(
    q: str = "",
    value_tier: str = "",
    lifecycle: str = "",
    store: str = "",
    sort: str = "customer_score",
    direction: str = "desc",
    contactable_only: bool = False,
    limit: int = Query(50, le=500),
    offset: int = 0,
) -> dict[str, Any]:
    rows = workspace.profiles
    if q:
        needle = q.lower()
        rows = [p for p in rows if needle in p["name"].lower()
                or needle in p["customer_id"].lower()]
    # Value and lifecycle filter independently, because they are independent
    # questions: "show me my VIPs" and "show me who is drifting" are not the same.
    if value_tier:
        rows = [p for p in rows if p.get("value_tier") == value_tier]
    if lifecycle:
        rows = [p for p in rows if p.get("lifecycle") == lifecycle]
    if store:
        rows = [p for p in rows if (p.get("store") or "") == store]
    if contactable_only:
        rows = [p for p in rows if p.get("contactable")]

    key = sort if sort in SORTABLE else "customer_score"
    reverse = direction != "asc"
    if key == "name":
        rows = sorted(rows, key=lambda p: p["name"].lower(), reverse=reverse)
    else:
        rows = sorted(rows, key=lambda p: (p.get(key) is not None, p.get(key) or 0),
                      reverse=reverse)

    page = rows[offset:offset + limit]
    top_products = {}
    for p in page:
        best = matching.best_products_for_customer(p, workspace.products, limit=1)
        top_products[p["customer_id"]] = ({
            "sku": best[0]["sku"], "name": best[0]["product_name"],
            "match_pct": best[0]["match_pct"], "price": best[0]["price"],
        } if best else None)

    return {
        "total": len(rows),
        "offset": offset,
        "limit": limit,
        "customers": [{
            "customer_id": p["customer_id"], "name": p["name"],
            "value_tier": p.get("value_tier"), "lifecycle": p.get("lifecycle"),
            "segment": p.get("segment"),
            "value_tone": p.get("value_tone"), "lifecycle_tone": p.get("lifecycle_tone"),
            "customer_score": p.get("customer_score"),
            "total_spend": p.get("total_spend"), "order_count": p.get("order_count"),
            "avg_order_value": p.get("avg_order_value"), "last_purchase": p.get("last_purchase"),
            "recency_days": p.get("recency_days"), "cycle_days": p.get("cycle_days"),
            "cycle_position": p.get("cycle_position"),
            "cycle_confidence": p.get("cycle_confidence"),
            "store": p.get("store"), "top_category": p.get("top_category"),
            "contactable": p.get("contactable", False),
            "suppression_reason": p.get("suppression_reason"),
            "data_confidence": p.get("data_confidence"),
            "crm_record": p.get("crm_record", True),
            "potential_annual_value": p.get("potential_annual_value"),
            "recommended_product": top_products[p["customer_id"]],
        } for p in page],
        "facets": {
            "value_tiers": [t for t in segmentation.VALUE_TIERS
                            if any(p.get("value_tier") == t for p in workspace.profiles)],
            "lifecycles": [s for s in segmentation.LIFECYCLE_STAGES
                           if any(p.get("lifecycle") == s for p in workspace.profiles)],
            "stores": sorted({p.get("store") for p in workspace.profiles if p.get("store")}),
        },
    }


@router.get("/customers/{customer_id}")
def customer_detail(customer_id: str) -> dict[str, Any]:
    profile = workspace.profile(customer_id)
    if not profile:
        raise HTTPException(404, "Customer not found.")

    matches = matching.best_products_for_customer(profile, workspace.products, limit=6)
    transactions = workspace.customer_transactions(customer_id)
    opps = [o for o in workspace.opportunities if o["customer_id"] == customer_id]

    return {
        "profile": profile,
        # The answer, stated first and in the same words as the opportunity card,
        # so the advisor never has to reconcile two versions of the reason.
        "why_contact": ({
            "headline": opps[0]["headline"],
            "why_now": opps[0]["why_now"],
            "evidence": opps[0]["evidence"],
            "action": opps[0]["action"],
            "product": opps[0].get("product"),
            "contactable": opps[0]["contactable"],
        } if opps else {
            "headline": "No reason to contact them today",
            "why_now": profile.get("lifecycle_basis"),
            "evidence": None,
            "action": "Nothing to do — they are within their normal buying rhythm.",
            "product": None,
            "contactable": profile.get("contactable", False),
        }),
        "value": {
            "tier": profile.get("value_tier"),
            "basis": profile.get("value_basis"),
            "signals": profile.get("value_signals", []),
            "percentile": profile.get("value_percentile"),
        },
        "lifecycle": {
            "stage": profile.get("lifecycle"),
            "basis": profile.get("lifecycle_basis"),
            "confidence": profile.get("lifecycle_confidence"),
            "cycle_days": profile.get("cycle_days"),
            "cycle_basis": profile.get("cycle_basis"),
            "cycle_confidence": profile.get("cycle_confidence"),
            "cycle_position": profile.get("cycle_position"),
        },
        "eligibility": profile.get("eligibility"),
        "recommendations": [{
            **m, "expected_value": matching.expected_value(m, profile),
        } for m in matches],
        "timeline": [{
            "date": str(t.get("date")) if t.get("date") else None,
            "transaction_id": t.get("transaction_id"),
            "product": t.get("product"),
            "sku": t.get("sku"),
            "category": t.get("category"),
            "brand": t.get("brand"),
            "color": t.get("color"),
            "size": t.get("size"),
            "quantity": t.get("quantity"),
            "amount": t.get("line_total"),
            "discount": t.get("discount"),
            "store": t.get("store"),
        } for t in transactions[:80]],
    }


@router.get("/customers/{customer_id}/narrative")
def customer_narrative(customer_id: str) -> dict[str, Any]:
    # Imported here, not at module scope: this pulls in the Anthropic SDK,
    # which is the single largest cost of starting the API and is needed only
    # when an AI surface is actually called. Paying it on every boot delays
    # the port opening, which is what a platform waits for.
    from ..ai import analyst

    result = analyst.customer_narrative(customer_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/segments")
def segments() -> dict[str, Any]:
    """Value and lifecycle, reported as the two separate dimensions they are."""
    return workspace.summary.get("segments", {"value": [], "lifecycle": [], "matrix": []})
