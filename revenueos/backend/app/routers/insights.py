"""Executive insights: the AI-written weekly business review."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter

from ..ai.analyst import narrate
from ..ai.prompts import insights_system
from ..analytics.forecasting import concentration, dimension_performance, revenue_timeseries
from ..analytics.inventory import inventory_overview
from ..analytics.rfm import segment_summary
from ..config import settings
from ..store import store

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("")
def weekly_review() -> dict[str, Any]:
    workspace = store.default()
    workspace.recompute()
    if not workspace.has_data():
        return {"hasData": False}

    metrics = workspace.customer_metrics
    products = workspace.inventory_metrics
    trend = revenue_timeseries(workspace.transactions, "W", 6)
    categories = dimension_performance(workspace.transactions, "category", 8)
    brands = dimension_performance(workspace.transactions, "brand", 6)
    summary = workspace.opportunity_summary()

    facts = _facts(workspace, metrics, products, trend, categories, brands, summary)
    text, mode = narrate(insights_system(settings.currency), facts, _composed(facts))

    return {
        "hasData": True,
        "review": text,
        "mode": mode,
        "facts": facts,
        "trend": trend,
        "categories": categories,
        "brands": brands,
        "segments": segment_summary(metrics) if metrics is not None else [],
        "concentration": concentration(metrics) if metrics is not None else {"available": False},
        "inventory": inventory_overview(products) if products is not None else None,
    }


def _facts(workspace, metrics, products, trend, categories, brands, summary) -> dict[str, Any]:
    facts: dict[str, Any] = {"opportunities": summary}

    if trend.get("available"):
        facts["revenue"] = {
            "last30Days": trend["last30Days"],
            "previous30Days": trend["previous30Days"],
            "changePct": trend["change"],
        }
    else:
        facts["revenue"] = {"available": False, "reason": trend.get("reason")}

    if categories:
        facts["topCategories"] = [
            {"category": c["value"], "revenue": c["revenue"], "share": c["share"],
             "growth90d": c.get("growth")}
            for c in categories[:5]
        ]
        growing = [c for c in categories if c.get("growth") is not None]
        if growing:
            best = max(growing, key=lambda c: c["growth"])
            worst = min(growing, key=lambda c: c["growth"])
            facts["fastestGrowingCategory"] = {"category": best["value"], "growth": best["growth"]}
            facts["decliningCategory"] = {"category": worst["value"], "growth": worst["growth"]}
    if brands:
        facts["topBrands"] = [
            {"brand": b["value"], "revenue": b["revenue"], "growth90d": b.get("growth")}
            for b in brands[:4]
        ]

    if metrics is not None and not metrics.empty:
        overdue = metrics[metrics["days_overdue"].fillna(-1) > 0] \
            if "days_overdue" in metrics else metrics.iloc[0:0]
        high_value_overdue = overdue[overdue["customer_score"].fillna(0) >= 65] \
            if "customer_score" in overdue else overdue
        facts["customers"] = {
            "total": int(len(metrics)),
            "overdue": int(len(overdue)),
            "highValueOverdue": int(len(high_value_overdue)),
            "highValueOverdueValue": _sum(high_value_overdue, "avg_order_value"),
            "segments": metrics["segment"].value_counts().to_dict()
            if "segment" in metrics else {},
            "newLast90Days": int(
                (metrics["tenure_days"].fillna(9999) <= 90).sum()
            ) if "tenure_days" in metrics else None,
        }

    if products is not None and not products.empty:
        overview = inventory_overview(products)
        facts["inventory"] = {
            "skus": overview["skus"],
            "stockValue": overview.get("retailValue"),
            "atRiskValue": overview.get("atRiskValue"),
            "atRiskSkus": overview.get("atRiskSkus"),
            "avgSellThrough": overview.get("avgSellThrough"),
            "avgDaysInStock": overview.get("avgDaysInStock"),
            "statusCounts": overview.get("statusCounts"),
        }
        if "age_bucket" in products.columns:
            aged = products[products["days_in_stock"].fillna(0) > 120]
            facts["inventory"]["over120DaysValue"] = _sum(aged, "retail_value")
    return facts


def _sum(frame: pd.DataFrame, column: str) -> float | None:
    if frame is None or frame.empty or column not in frame.columns:
        return None
    values = frame[column].dropna()
    return round(float(values.sum()), 2) if not values.empty else None


def _money(value: Any) -> str:
    try:
        return f"€{float(value):,.0f}"
    except (TypeError, ValueError):
        return "not enough information"


def _composed(facts: dict[str, Any]) -> str:
    """Deterministic review built only from present figures."""
    wins, risks, opportunities, actions = [], [], [], []

    revenue = facts.get("revenue") or {}
    if revenue.get("changePct") is not None:
        change = revenue["changePct"]
        line = (f"Revenue over the last 30 days was {_money(revenue['last30Days'])}, "
                f"{'up' if change >= 0 else 'down'} {abs(change):.1%} on the prior 30 days.")
        (wins if change >= 0 else risks).append(line)

    best = facts.get("fastestGrowingCategory")
    if best and best.get("growth") is not None:
        wins.append(f"{best['category']} grew {best['growth']:+.1%} over the last 90 days.")
    worst = facts.get("decliningCategory")
    if worst and worst.get("growth") is not None and worst["growth"] < 0:
        risks.append(f"{worst['category']} fell {worst['growth']:+.1%} over the last 90 days.")

    customers = facts.get("customers") or {}
    if customers.get("highValueOverdue"):
        risks.append(
            f"{customers['highValueOverdue']} high-value customers are past their normal "
            f"repurchase window, representing {_money(customers.get('highValueOverdueValue'))} "
            "of typical baskets."
        )
        actions.append(
            f"Personally contact the {customers['highValueOverdue']} overdue high-value "
            "customers this week."
        )

    inventory = facts.get("inventory") or {}
    if inventory.get("atRiskValue"):
        risks.append(
            f"{_money(inventory['atRiskValue'])} of stock across {inventory.get('atRiskSkus')} "
            "SKUs is ageing or not moving."
        )
        actions.append(
            "Match at-risk stock to customers with the right affinity before considering markdown."
        )
    if inventory.get("over120DaysValue"):
        risks.append(f"{_money(inventory['over120DaysValue'])} has been in stock over 120 days.")

    opps = facts.get("opportunities") or {}
    if opps.get("expectedValue"):
        opportunities.append(
            f"{_money(opps['expectedValue'])} of probability-weighted revenue sits across "
            f"{opps.get('count')} detected opportunities."
        )
    for entry in list((opps.get("byKind") or {}).values())[:3]:
        opportunities.append(
            f"{entry['label']}: {entry['count']} opportunities worth {_money(entry['value'])}."
        )
    if customers.get("newLast90Days"):
        opportunities.append(
            f"{customers['newLast90Days']} customers made a first purchase in the last 90 days — "
            "converting them to a second purchase is the highest-leverage move."
        )
        actions.append("Follow up with recent first-time buyers before their window closes.")

    def section(title: str, items: list[str]) -> str:
        body = "\n".join(f"- {i}" for i in items) if items else "- Nothing material this period."
        return f"## {title}\n{body}"

    return "\n\n".join([
        section("Wins", wins),
        section("Risks", risks),
        section("Opportunities", opportunities),
        section("Recommended actions", actions),
    ])
