"""The opportunity feed and the sales pipeline built on top of it."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..analytics.opportunities import KIND_META
from ..store import store


def compact(opportunity: dict[str, Any], customers: int = 5, products: int = 3,
            signals: int = 2) -> dict[str, Any]:
    """Trim an opportunity for list views.

    A full opportunity carries every matched customer with every signal that
    produced their score. That is what the detail view needs and what a list of
    sixty would drown in, so lists get the head of each collection and the count.
    """
    out = dict(opportunity)
    for key, keep in (("customers", customers), ("products", products)):
        rows = opportunity.get(key) or []
        out[key] = [
            {**{k: v for k, v in row.items() if k != "signals"},
             "signals": (row.get("signals") or [])[:signals]}
            if isinstance(row, dict) else row
            for row in rows[:keep]
        ]
        out[f"{key}Total"] = len(rows)
    return out

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

STATUSES = ("new", "contacted", "interested", "won", "lost")


@router.get("")
def list_opportunities(kind: str | None = None, status: str | None = None,
                       minScore: float | None = None, limit: int = 60) -> dict[str, Any]:
    workspace = store.default()
    workspace.recompute()
    rows = list(workspace.opportunities)

    if kind:
        rows = [o for o in rows if o["kind"] == kind]
    if status:
        rows = [o for o in rows if o.get("status", "new") == status]
    if minScore is not None:
        rows = [o for o in rows if o["score"] >= minScore]

    return {
        "hasData": workspace.has_data(),
        "rows": [compact(o) for o in rows[:limit]],
        "total": len(rows),
        "summary": workspace.opportunity_summary(),
        "kinds": KIND_META,
        "statuses": list(STATUSES),
        "pipeline": _pipeline_counts(workspace),
    }


class StatusUpdate(BaseModel):
    status: str
    note: str | None = None


@router.post("/{opportunity_id}/status")
def set_status(opportunity_id: str, update: StatusUpdate) -> dict[str, Any]:
    if update.status not in STATUSES:
        raise HTTPException(400, f"Status must be one of {list(STATUSES)}.")
    workspace = store.default()
    workspace.recompute()

    known = {o["id"] for o in workspace.opportunities}
    if opportunity_id not in known:
        raise HTTPException(404, "That opportunity no longer exists in the current data.")

    workspace.pipeline_status[opportunity_id] = {
        "status": update.status,
        "note": update.note,
        "updatedAt": time.time(),
    }
    for opp in workspace.opportunities:
        if opp["id"] == opportunity_id:
            opp["status"] = update.status
            opp["statusNote"] = update.note
            opp["statusUpdatedAt"] = workspace.pipeline_status[opportunity_id]["updatedAt"]
            break
    store.persist(workspace)
    return {"id": opportunity_id, "status": update.status,
            "pipeline": _pipeline_counts(workspace)}


@router.get("/{opportunity_id}")
def get_opportunity(opportunity_id: str) -> dict[str, Any]:
    workspace = store.default()
    workspace.recompute()
    for opp in workspace.opportunities:
        if opp["id"] == opportunity_id:
            return opp
    raise HTTPException(404, "Opportunity not found.")


def _pipeline_counts(workspace) -> dict[str, dict[str, Any]]:
    counts = {s: {"count": 0, "value": 0.0} for s in STATUSES}
    for opp in workspace.opportunities:
        status = opp.get("status", "new")
        entry = counts.setdefault(status, {"count": 0, "value": 0.0})
        entry["count"] += 1
        entry["value"] += opp.get("estimatedValue") or 0.0
    for entry in counts.values():
        entry["value"] = round(entry["value"], 2)
    return counts
