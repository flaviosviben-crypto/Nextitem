"""Scenario Lab: modelled what-if projections, always labelled as estimates."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..analytics import forecasting
from ..workspace import workspace

router = APIRouter(tags=["scenarios"])


class DiscountScenario(BaseModel):
    skus: list[str] = []
    risk_class: str | None = None
    discount_pct: float = 15.0
    elasticity: float = 1.8


class OutreachScenario(BaseModel):
    customer_ids: list[str] = []
    segment: str | None = None
    conversion_rate: float = 0.12


class CategoryScenario(BaseModel):
    category: str
    attention_lift: float = 0.25


@router.post("/scenarios/discount")
def discount(payload: DiscountScenario) -> dict[str, Any]:
    skus = payload.skus
    if not skus and payload.risk_class:
        skus = [p["sku"] for p in workspace.products
                if p.get("risk_class") == payload.risk_class and (p.get("stock") or 0) > 0]
    if not skus:
        raise HTTPException(400, "Select products or a risk class to model.")
    result = forecasting.simulate_discount(workspace.products, skus,
                                           payload.discount_pct, payload.elasticity)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/scenarios/outreach")
def outreach(payload: OutreachScenario) -> dict[str, Any]:
    ids = payload.customer_ids
    if not ids and payload.segment:
        ids = [p["customer_id"] for p in workspace.profiles if p.get("segment") == payload.segment]
    if not ids:
        raise HTTPException(400, "Select customers or a segment to model.")
    result = forecasting.simulate_outreach(workspace.profiles, ids, payload.conversion_rate)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/scenarios/category")
def category(payload: CategoryScenario) -> dict[str, Any]:
    result = forecasting.simulate_category_focus(
        workspace.transactions_raw, workspace.products, payload.category, payload.attention_lift)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.get("/scenarios/options")
def options() -> dict[str, Any]:
    return {
        "segments": sorted({p.get("segment") for p in workspace.profiles if p.get("segment")}),
        "categories": sorted({p.get("category") for p in workspace.products if p.get("category")}),
        "risk_classes": sorted({p.get("risk_class") for p in workspace.products
                                if p.get("risk_class")}),
    }
