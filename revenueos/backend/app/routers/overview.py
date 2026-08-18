"""The Overview page: daily briefing, KPIs, priorities and trend charts."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter

from ..ai.analyst import narrate
from ..ai.prompts import briefing_system
from ..analytics.forecasting import (
    concentration,
    customer_value_distribution,
    dimension_performance,
    revenue_timeseries,
)
from ..analytics.inventory import inventory_overview
from ..analytics.rfm import segment_summary
from ..config import settings
from ..serialisation import clean_value
from ..routers.opportunities import compact
from ..store import store

router = APIRouter(prefix="/api/overview", tags=["overview"])


@router.get("")
def overview() -> dict[str, Any]:
    workspace = store.default()
    workspace.recompute()

    if not workspace.has_data():
        return {"hasData": False, "workspace": workspace.stats()}

    metrics = workspace.customer_metrics
    products = workspace.inventory_metrics
    opportunity_summary = workspace.opportunity_summary()

    kpis = _kpis(workspace, metrics, products, opportunity_summary)
    priorities = _priorities(workspace)

    return {
        "hasData": True,
        "workspace": workspace.stats(),
        "kpis": kpis,
        "priorities": priorities,
        "opportunities": [compact(o, customers=4, products=2) for o in workspace.opportunities[:8]],
        "opportunitySummary": opportunity_summary,
        "revenueTrend": revenue_timeseries(workspace.transactions, "W", 9),
        "segments": segment_summary(metrics) if metrics is not None else [],
        "valueDistribution": customer_value_distribution(metrics) if metrics is not None else [],
        "concentration": concentration(metrics) if metrics is not None else {"available": False},
        "categoryPerformance": dimension_performance(workspace.transactions, "category", 8),
        "inventory": inventory_overview(products) if products is not None else None,
        "dataHealth": {
            "score": workspace.quality.get("score"),
            "grade": workspace.quality.get("grade"),
            "summary": workspace.quality.get("summary"),
        },
    }


@router.get("/briefing")
def briefing() -> dict[str, Any]:
    """The 'here is what needs your attention today' paragraph."""
    workspace = store.default()
    workspace.recompute()
    if not workspace.has_data():
        return {"briefing": "Load your data to get your first briefing.",
                "mode": "deterministic", "hasData": False}

    metrics = workspace.customer_metrics
    products = workspace.inventory_metrics
    summary = workspace.opportunity_summary()
    top = workspace.opportunities[:4]

    payload = {
        "opportunityCount": summary.get("count"),
        "expectedRevenue": summary.get("expectedValue"),
        "topOpportunities": [
            {"title": o["title"], "why": o["explanation"][:220],
             "action": o["action"], "estimatedValue": o["estimatedValue"],
             "score": o["score"]}
            for o in top
        ],
        "customersOverdue": int(
            (metrics["days_overdue"].fillna(-1) > 0).sum()
        ) if metrics is not None and "days_overdue" in metrics else None,
        "stockAtRisk": _at_risk_value(products),
        "dataHealth": workspace.quality.get("score"),
    }

    fallback = _composed_briefing(payload)
    text, mode = narrate(briefing_system(settings.currency), payload, fallback)
    return {"briefing": text, "mode": mode, "hasData": True, "basedOn": payload}


# --------------------------------------------------------------------------- #
def _at_risk_value(products: pd.DataFrame | None) -> float | None:
    if products is None or products.empty or "status" not in products.columns:
        return None
    at_risk = products[products["status"].isin(["At Risk", "Dead Stock"])]
    if at_risk.empty or "retail_value" not in at_risk.columns:
        return None
    value = at_risk["retail_value"].dropna().sum()
    return round(float(value), 2) if value else None


def _kpis(workspace, metrics, products, summary) -> list[dict[str, Any]]:
    """Four headline numbers. Each carries its own explanation and provenance."""
    kpis: list[dict[str, Any]] = []

    kpis.append({
        "key": "revenueOpportunity",
        "label": "Revenue opportunity",
        "value": summary.get("expectedValue"),
        "format": "currency",
        "detail": (
            f"Probability-weighted across {summary.get('count', 0)} detected opportunities"
            if summary.get("expectedValue") is not None else "Not enough information"
        ),
        "href": "/opportunities",
    })

    overdue = None
    overdue_value = None
    if metrics is not None and "days_overdue" in metrics.columns:
        late = metrics[metrics["days_overdue"].fillna(-1) > 0]
        overdue = int(len(late))
        baskets = late["avg_order_value"].dropna()
        overdue_value = round(float(baskets.sum()), 2) if not baskets.empty else None
    kpis.append({
        "key": "customersToContact",
        "label": "Customers to contact",
        "value": overdue,
        "format": "number",
        "detail": (
            f"Past their own repurchase window · {_money(overdue_value)} of typical baskets"
            if overdue_value else "Past their own repurchase window"
        ) if overdue is not None else "Needs purchase dates",
        "href": "/customers?status=overdue",
    })

    at_risk_count = None
    at_risk_value = _at_risk_value(products)
    if products is not None and "status" in products.columns:
        at_risk_count = int(products["status"].isin(["At Risk", "Dead Stock"]).sum())
    kpis.append({
        "key": "inventoryAtRisk",
        "label": "Inventory at risk",
        "value": at_risk_value,
        "format": "currency",
        "detail": (f"{at_risk_count} SKUs ageing or not moving"
                   if at_risk_count is not None else "Needs stock data"),
        "href": "/inventory?status=At%20Risk",
    })

    match_avg = None
    strong = None
    if workspace.opportunities:
        scores = [o["matchPct"] for o in workspace.opportunities if o.get("matchPct")]
        if scores:
            match_avg = round(float(np.mean(scores)), 1)
            strong = sum(1 for s in scores if s >= 70)
    kpis.append({
        "key": "matchQuality",
        "label": "Average match score",
        "value": match_avg,
        "format": "percent0to100",
        "detail": (f"{strong} matches above 70%" if strong is not None
                   else "Needs customer and product data"),
        "href": "/recommendations",
    })
    return kpis


def _priorities(workspace) -> list[dict[str, Any]]:
    """Today's three-to-four actions, each linking to where the work happens."""
    out: list[dict[str, Any]] = []
    opportunities = [o for o in workspace.opportunities if o.get("status", "new") == "new"]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for opp in opportunities:
        grouped.setdefault(opp["kind"], []).append(opp)

    order = ["overdue_vip", "new_arrival_match", "dead_stock_rescue", "reactivation",
             "brand_restock", "high_potential", "private_sale"]
    for kind in order:
        bucket = grouped.get(kind)
        if not bucket:
            continue
        value = sum(o.get("estimatedValue") or 0 for o in bucket)
        customers = {c for o in bucket for c in o.get("customerIds", [])}
        products = {p for o in bucket for p in o.get("productIds", [])}

        titles = {
            "overdue_vip": f"Contact {len(customers)} overdue high-value customers",
            "new_arrival_match": f"Push {len(products)} new arrivals to matched clients",
            "dead_stock_rescue": f"Rescue {len(products)} products before markdown",
            "reactivation": f"Reactivate {len(customers)} lapsed customers",
            "brand_restock": "Preview new brand arrivals to loyal buyers",
            "high_potential": f"Grow {len(customers)} high-potential customers",
            "private_sale": "Build a private sale audience",
        }
        hrefs = {
            "overdue_vip": "/opportunities?kind=overdue_vip",
            "new_arrival_match": "/opportunities?kind=new_arrival_match",
            "dead_stock_rescue": "/inventory?status=At%20Risk",
            "reactivation": "/opportunities?kind=reactivation",
            "brand_restock": "/opportunities?kind=brand_restock",
            "high_potential": "/opportunities?kind=high_potential",
            "private_sale": "/campaigns",
        }
        out.append({
            "kind": kind,
            "title": titles.get(kind, bucket[0]["title"]),
            "detail": bucket[0]["explanation"][:180],
            "estimatedValue": round(value, 2) if value else None,
            "opportunityCount": len(bucket),
            "customerCount": len(customers),
            "productCount": len(products),
            "topScore": round(max(o["score"] for o in bucket), 1),
            "href": hrefs.get(kind, "/opportunities"),
            "cta": "View customers" if customers and not products else "View details",
        })
        if len(out) >= 4:
            break
    return out


def _money(value: Any) -> str:
    try:
        return f"€{float(value):,.0f}"
    except (TypeError, ValueError):
        return "not enough information"


def _composed_briefing(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    if payload.get("expectedRevenue"):
        parts.append(
            f"There is {_money(payload['expectedRevenue'])} of probability-weighted revenue "
            f"across {payload.get('opportunityCount', 0)} detected opportunities."
        )
    if payload.get("customersOverdue"):
        parts.append(
            f"{payload['customersOverdue']} customers are past their own repurchase window."
        )
    if payload.get("stockAtRisk"):
        parts.append(f"{_money(payload['stockAtRisk'])} of stock is ageing or not moving.")
    top = payload.get("topOpportunities") or []
    if top:
        parts.append(f"Start with: {top[0]['action']}.")
    return " ".join(parts) or "No pressing actions were detected in the current data."
