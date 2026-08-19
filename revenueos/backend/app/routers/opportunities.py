"""Opportunity feed and the sales pipeline."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..workspace import workspace

router = APIRouter(tags=["opportunities"])

STATUSES = ["New", "Contacted", "Interested", "Won", "Lost"]


class PipelineUpdate(BaseModel):
    status: str
    note: str | None = None


@router.get("/opportunities")
def list_opportunities(type: str = "", limit: int = 30) -> dict[str, Any]:
    rows = workspace.opportunities
    if type:
        rows = [o for o in rows if o["type"] == type]
    return {
        "total": len(rows),
        "total_impact": round(sum(o.get("impact") or 0 for o in rows), 2),
        "opportunities": rows[:limit],
        "types": sorted({o["type"] for o in workspace.opportunities}),
    }


@router.get("/opportunities/{opportunity_id}")
def opportunity_detail(opportunity_id: str) -> dict[str, Any]:
    found = next((o for o in workspace.opportunities if o["id"] == opportunity_id), None)
    if not found:
        raise HTTPException(404, "Opportunity not found.")
    return found


@router.get("/pipeline")
def pipeline(status: str = "") -> dict[str, Any]:
    rows = workspace.pipeline
    if status:
        rows = [r for r in rows if r.get("status") == status]
    counts = {s: sum(1 for r in workspace.pipeline if r.get("status") == s) for s in STATUSES}
    won = [r for r in workspace.pipeline if r.get("status") == "Won"]
    return {
        "rows": rows[:400],
        "counts": counts,
        "total": len(rows),
        "won_value": round(sum(r.get("value") or 0 for r in won), 2),
        "open_value": round(sum(r.get("value") or 0 for r in workspace.pipeline
                                if r.get("status") in {"New", "Contacted", "Interested"}), 2),
        "statuses": STATUSES,
    }


@router.patch("/pipeline/{row_id:path}")
def update_pipeline(row_id: str, payload: PipelineUpdate) -> dict[str, Any]:
    if payload.status not in STATUSES:
        raise HTTPException(400, f"Status must be one of {', '.join(STATUSES)}.")
    row = next((r for r in workspace.pipeline if r["id"] == row_id), None)
    if not row:
        raise HTTPException(404, "Pipeline item not found.")
    row["status"] = payload.status
    if payload.note is not None:
        row["note"] = payload.note
    row["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    workspace.save()
    return row
