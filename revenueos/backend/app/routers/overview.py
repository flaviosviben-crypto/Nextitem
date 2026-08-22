"""The Overview: what needs attention today, in one screen.

Deliberately thin. Overview's job is to point at Today's Opportunities, not to
compete with it — an advisor who lingers here is not selling.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..analytics import performance as perf
from ..analytics.opportunities import counts, todays_list
from ..workspace import workspace

router = APIRouter(tags=["overview"])


@router.get("/overview")
def overview() -> dict[str, Any]:
    if not workspace.is_loaded:
        return {"loaded": False}

    summary = workspace.summary
    today = todays_list(workspace.opportunities)
    opp_counts = counts(workspace.opportunities, workspace.pipeline, daily_cap=workspace.daily_cap,
                       product_matching_available=workspace.product_matching_available)
    report = workspace.performance or perf.report(workspace.pipeline,
                                                  workspace.transactions_raw,
                                                  as_of=workspace.as_of)

    return {
        "loaded": True,
        # The one snapshot date every screen's relative dates and lifecycle
        # calculations are computed against — shown in the shell so "1 day"
        # reads correctly against the calendar date it is relative to.
        "as_of": workspace.as_of.isoformat(),
        "today": {
            "opportunities": len(today),
            # Same numbers the Opportunities screen and Performance report use;
            # they all read one stamp rather than each deciding for themselves.
            **opp_counts,
            # Stated plainly so a short list reads as an honest day, not a fault.
            "note": ("Nothing meets the bar today — the data is current, there is "
                     "simply nobody worth interrupting."
                     if not today else
                     f"{len(today)} customers are worth a conversation today."),
            "relationship": (
                f"{len(today)} prioritized for today · "
                f"{opp_counts['detected']} "
                f"{'opportunity' if opp_counts['detected'] == 1 else 'opportunities'} detected"),
            "influenced_value": round(sum(o.get("influenced_value") or 0 for o in today), 2),
            "value_basis": ("Each customer's estimated purchase value — their own order "
                            "history, the recommended piece's price, or a blend of both, "
                            "depending on what is known — weighted by a modelled response "
                            "rate. Not a forecast."),
            "top": [{
                "id": o["id"],
                "customer_id": o["customer_id"],
                "customer_name": o["customer_name"],
                "value_tier": o.get("value_tier"),
                "lifecycle": o.get("lifecycle"),
                "headline": o["headline"],
                "why_now": o["why_now"],
                "product": (o.get("product") or {}).get("name"),
                "match_pct": (o.get("product") or {}).get("match_pct"),
                "channel": (o["eligibility"].get("preferred_channel") or {}).get("label"),
            } for o in today[:5]],
        },
        "this_month": {
            "customers_contacted": report.get("customers_contacted"),
            "conversions": report.get("conversions"),
            "conversion_rate": report.get("conversion_rate"),
            "influenced_revenue": report.get("influenced_revenue"),
            "estimated_incremental_revenue": report.get("estimated_incremental_revenue"),
        },
        "base": {
            "customers": summary.get("counts", {}).get("customers"),
            "value": summary.get("segments", {}).get("value", []),
            "lifecycle": summary.get("segments", {}).get("lifecycle", []),
        },
        "data_health": summary.get("data_health"),
        "compliance": summary.get("compliance", {}),
        "counts": summary.get("counts", {}),
    }
