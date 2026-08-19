"""Today's Opportunities and the Action Center that follows them."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..analytics.opportunities import ACTION_STATES, CLOSED_STATES, OPEN_STATES, daily
from ..workspace import workspace

router = APIRouter(tags=["opportunities"])

# "New" is the state an opportunity arrives in, before an advisor has decided.
PIPELINE_STATES = ["New", *ACTION_STATES]


class ActionUpdate(BaseModel):
    status: str
    note: str | None = None
    realised_value: float | None = None


@router.get("/opportunities")
def todays_opportunities(trigger: str = "", include_suppressed: bool = False,
                         limit: int = 20) -> dict[str, Any]:
    """The advisor's list for today.

    Never padded to a quota: the response reports how many cleared the bar so the
    UI can say "7 today" without implying something is missing.
    """
    everything = workspace.opportunities
    shortlist = daily(everything, max_cards=limit)
    if trigger:
        shortlist = [o for o in shortlist if o["trigger"] == trigger]

    suppressed = [o for o in everything if not o["contactable"]]

    return {
        "opportunities": shortlist,
        "shown": len(shortlist),
        "total_detected": len(everything),
        "suppressed": suppressed[:50] if include_suppressed else [],
        "suppressed_count": len(suppressed),
        "influenced_value": round(sum(o.get("influenced_value") or 0 for o in shortlist), 2),
        "incremental_value": round(sum(o.get("incremental_value") or 0 for o in shortlist), 2),
        "triggers": sorted({o["trigger"] for o in everything}),
    }


@router.get("/opportunities/{opportunity_id:path}")
def opportunity_detail(opportunity_id: str) -> dict[str, Any]:
    found = next((o for o in workspace.opportunities if o["id"] == opportunity_id), None)
    if not found:
        raise HTTPException(404, "Opportunity not found.")
    return found


@router.get("/actions")
def action_center(status: str = "") -> dict[str, Any]:
    """Everything an advisor has decided on, and everything still waiting."""
    rows = workspace.pipeline
    if status:
        rows = [r for r in rows if r.get("status") == status]

    counts = {s: sum(1 for r in workspace.pipeline if r.get("status") == s)
              for s in PIPELINE_STATES}
    converted = [r for r in workspace.pipeline if r.get("status") == "Converted"]

    return {
        "rows": rows[:400],
        "counts": counts,
        "total": len(rows),
        "statuses": PIPELINE_STATES,
        "open": sum(1 for r in workspace.pipeline if r.get("status") in OPEN_STATES),
        "closed": sum(1 for r in workspace.pipeline if r.get("status") in CLOSED_STATES),
        "converted_value": round(
            sum(r.get("realised_value") or r.get("influenced_value") or 0
                for r in converted), 2),
        "converted_value_basis": (
            "Recorded sale value where the advisor entered one, otherwise the "
            "estimate that was on the card."),
    }


@router.patch("/actions/{row_id:path}")
def update_action(row_id: str, payload: ActionUpdate) -> dict[str, Any]:
    if payload.status not in PIPELINE_STATES:
        raise HTTPException(400, f"Status must be one of {', '.join(PIPELINE_STATES)}.")
    row = next((r for r in workspace.pipeline if r["id"] == row_id), None)
    if not row:
        raise HTTPException(404, "Action not found.")

    # Approving an outreach is a human decision, and it is recorded as one: no
    # message reaches a customer without a name and a timestamp against it.
    row["status"] = payload.status
    if payload.note is not None:
        row["note"] = payload.note
    if payload.realised_value is not None:
        row["realised_value"] = payload.realised_value
    row["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    workspace.audit(row_id, payload.status, payload.note)
    workspace.refresh_performance()
    workspace.save()
    return row


@router.get("/audit")
def audit_log(limit: int = 200) -> dict[str, Any]:
    """Who approved what, and when. Boring by design, and non-negotiable."""
    return {"entries": workspace.audit_log[:limit], "total": len(workspace.audit_log)}
