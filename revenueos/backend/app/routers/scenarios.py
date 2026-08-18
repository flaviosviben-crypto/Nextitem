"""Scenario Lab: modelled projections, always labelled as estimates."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..ai.analyst import narrate
from ..ai.prompts import scenario_system
from ..analytics.forecasting import (
    simulate_category_focus,
    simulate_discount,
    simulate_outreach,
)
from ..config import settings
from ..store import store

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

PRESETS = [
    {"key": "discount", "name": "Apply a discount",
     "question": "What happens if I discount these products by 15%?",
     "inputs": ["discountPct", "status", "category"]},
    {"key": "outreach", "name": "Contact a group",
     "question": "What if I contact my top 30 dormant customers?",
     "inputs": ["segment", "contactRate"]},
    {"key": "category_focus", "name": "Focus on a category",
     "question": "What if I focus next week on outerwear?",
     "inputs": ["category", "upliftPct"]},
]


class ScenarioRequest(BaseModel):
    type: str
    discountPct: float | None = Field(default=15, ge=0, le=90)
    status: str | None = None
    category: str | None = None
    productIds: list[str] | None = None
    segment: str | None = None
    customerIds: list[str] | None = None
    contactRate: float = Field(default=1.0, ge=0.05, le=1.0)
    upliftPct: float = Field(default=20, ge=0, le=200)
    explain: bool = True


@router.get("/presets")
def presets() -> dict[str, Any]:
    workspace = store.default()
    workspace.recompute()
    products = workspace.inventory_metrics
    metrics = workspace.customer_metrics
    return {
        "presets": PRESETS,
        "categories": sorted(products["category"].dropna().unique().tolist())
        if products is not None and "category" in products else [],
        "statuses": ["Hot", "Healthy", "Slow Moving", "At Risk", "Dead Stock"],
        "segments": sorted(metrics["segment"].dropna().unique().tolist())
        if metrics is not None and "segment" in metrics else [],
    }


@router.post("/run")
def run_scenario(request: ScenarioRequest) -> dict[str, Any]:
    workspace = store.default()
    workspace.recompute()
    if not workspace.has_data():
        raise HTTPException(400, "No data is loaded.")

    products = workspace.inventory_metrics
    metrics = workspace.customer_metrics

    if request.type == "discount":
        if products is None or products.empty:
            raise HTTPException(400, "No inventory is loaded.")
        product_ids = request.productIds
        if not product_ids:
            frame = products
            if request.status:
                frame = frame[frame["status"].astype(str) == request.status]
            if request.category:
                frame = frame[frame["category"].astype(str) == request.category]
            product_ids = frame["product_id"].astype(str).tolist()
        result = simulate_discount(products, request.discountPct or 15, product_ids)

    elif request.type == "outreach":
        if metrics is None or metrics.empty:
            raise HTTPException(400, "No customer data is loaded.")
        result = simulate_outreach(
            metrics, request.customerIds, request.segment, request.contactRate
        )

    elif request.type == "category_focus":
        if not request.category:
            raise HTTPException(400, "A category is required for this scenario.")
        result = simulate_category_focus(
            workspace.transactions, products, request.category, request.upliftPct
        )
    else:
        raise HTTPException(400, f"Unknown scenario type '{request.type}'.")

    if not result.get("available"):
        return {"available": False, "reason": result.get("reason"), "type": request.type}

    explanation, mode = ("", "deterministic")
    if request.explain:
        explanation, mode = narrate(
            scenario_system(settings.currency), result, _composed(result)
        )

    return {
        **result,
        "type": request.type,
        "explanation": explanation,
        "explanationMode": mode,
        "isEstimate": True,
    }


def _composed(result: dict[str, Any]) -> str:
    parts = ["These figures are a projection from a stated model, not a measured outcome."]
    if result.get("revenueDelta") is not None:
        delta = result["revenueDelta"]
        parts.append(
            f"The model projects a revenue change of €{delta:,.0f} over "
            f"{result.get('horizonDays', 30)} days."
        )
        if result.get("marginDelta") is not None:
            parts.append(f"Estimated margin impact: €{result['marginDelta']:,.0f}.")
    elif result.get("expectedRevenue") is not None:
        parts.append(
            f"Contacting {result.get('contacted')} customers is projected to produce "
            f"{result.get('expectedOrders', 0):.0f} orders worth "
            f"€{result['expectedRevenue']:,.0f}."
        )
    parts.append("Assumptions: " + " ".join(result.get("assumptions", [])))
    return " ".join(parts)
