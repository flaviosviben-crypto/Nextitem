"""AI Analyst, daily briefing and executive insights."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..ai import analyst as analyst_ai
from ..ai.client import status as ai_status
from ..analytics import matching
from ..workspace import workspace

router = APIRouter(tags=["analyst"])


class Turn(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = []


@router.get("/ai/status")
def status() -> dict[str, Any]:
    return ai_status()


@router.post("/ai/ask")
def ask(payload: AskRequest) -> dict[str, Any]:
    history = [{"role": t.role, "content": t.content} for t in payload.history]
    return analyst_ai.ask(payload.question.strip(), history)


@router.get("/ai/brief")
def brief() -> dict[str, Any]:
    return analyst_ai.executive_brief()


@router.get("/briefing")
def daily_briefing() -> dict[str, Any]:
    """The homepage: what needs attention today, all computed."""
    if not workspace.is_loaded:
        return {"loaded": False}

    summary = workspace.summary
    opps = workspace.opportunities

    priorities = []
    for opp in opps[:4]:
        customers = [e for e in opp.get("entities", []) if e.get("type") == "customer"]
        priorities.append({
            "id": opp["id"],
            "type": opp["type"],
            "title": opp["title"],
            "detail": opp["explanation"],
            "impact": opp["impact"],
            "expected_value": opp.get("expected_value"),
            "action": opp["action"],
            "score": opp["score"],
            "customer_count": len(customers),
            "customer_ids": opp.get("customer_ids", [])[:12],
            "product_skus": opp.get("product_skus", [])[:12],
        })

    overdue = sorted(
        [p for p in workspace.profiles
         if (p.get("overdue_ratio") or 0) > 1.2 and (p.get("value_percentile") or 0) >= 0.5],
        key=lambda p: -((p.get("total_spend") or 0) * (p.get("overdue_ratio") or 1)))[:8]

    contact_list = []
    for p in overdue:
        best = matching.best_products_for_customer(p, workspace.products, limit=1)
        contact_list.append({
            "customer_id": p["customer_id"],
            "name": p["name"],
            "segment": p.get("segment"),
            "reason": (f"{p['overdue_ratio']:.1f}× past their {p['cadence_days']:.0f}-day cycle"
                       if p.get("cadence_days") and p.get("overdue_ratio")
                       else f"{p.get('recency_days')} days since last purchase"),
            "value": p.get("potential_annual_value") or p.get("avg_order_value"),
            "contactable": p.get("marketing_consent") is True,
            "product": ({"sku": best[0]["sku"], "name": best[0]["product_name"],
                         "match_pct": best[0]["match_pct"]} if best else None),
        })

    inv = summary.get("inventory", {})
    return {
        "loaded": True,
        "headline": {
            "revenue_opportunity": summary.get("revenue_opportunity"),
            "customers_to_contact": summary.get("customers_to_contact"),
            "products_at_risk": inv.get("at_risk_products"),
            "at_risk_value": inv.get("at_risk_value"),
            "high_confidence_matches": summary.get("high_confidence_matches"),
            "data_health": summary.get("data_health"),
        },
        "priorities": priorities,
        "contact_today": contact_list,
        "counts": summary.get("counts", {}),
    }
