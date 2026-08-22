"""Today's Opportunities and the Action Center that follows them."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..analytics.opportunities import (
    ACTION_STATES, CLOSED_STATES, DECLINE_REASONS, OPEN_STATES, awaiting_decision, counts,
    todays_list,
)
from ..workspace import workspace

router = APIRouter(tags=["opportunities"])

# "New" is the state an opportunity arrives in, before an advisor has decided.
PIPELINE_STATES = ["New", *ACTION_STATES]

# Only these trigger kinds ever write a product-match percentage into the
# free-text "why now" reason. Kept narrow and explicit rather than
# pattern-matching the string, so the scrub below cannot misfire on prose it
# was never meant to touch.
_MATCH_DEPENDENT_TRIGGERS = {"new_arrival", "restock_affinity"}


def _scrub_unsupported_match(row: dict[str, Any]) -> dict[str, Any]:
    """Strip a match claim the current dataset no longer supports.

    An opportunity an advisor already acted on survives a recompute even after
    the opportunity itself fades (``_merge_pipeline`` preserves decided rows) —
    including one made back when the dataset still had transaction history.
    The advisor's decision and the product name stay, as the honest record of
    what happened; a precise match percentage this dataset can no longer
    compute must not keep showing as if it were still current.
    """
    if row.get("match_pct") is None and row.get("trigger") not in _MATCH_DEPENDENT_TRIGGERS:
        return row
    out = {**row, "match_pct": None}
    if row.get("trigger") in _MATCH_DEPENDENT_TRIGGERS:
        out["reason"] = ("Product matching is no longer supported by the current "
                         "dataset — this reason was generated before the data changed.")
    return out


class ActionUpdate(BaseModel):
    status: str
    note: str | None = None
    realised_value: float | None = None
    # Why the advisor set this aside. Required for Ignored: "no" without a
    # reason tells the boutique nothing about where the engine is wrong.
    reason: str | None = None
    reason_note: str | None = None


@router.get("/opportunities")
def todays_opportunities(trigger: str = "", include_suppressed: bool = False,
                         scope: str = "today") -> dict[str, Any]:
    """Today's recommended workload, drawn from everything detected.

    ``scope`` reads a set that was already decided in the pipeline; it never
    re-runs the prioritisation. A limit parameter used to live here, which meant
    a client could ask this endpoint for a different "today" than the one the
    Overview reported — two screens, two answers, same question.
    """
    everything = workspace.opportunities
    today = todays_list(everything)
    # The default scope is a decision inbox, not an archive: a recommendation
    # leaves it once an advisor has ruled on it, and stays gone across a refresh
    # because the decision lives in the pipeline, not in the browser. It has not
    # left the day — prioritized_today below still counts it.
    inbox = awaiting_decision(everything, workspace.pipeline)
    rows = {"detected": everything, "recommended": today}.get(scope, inbox)
    if trigger:
        rows = [o for o in rows if o["trigger"] == trigger]

    suppressed = [o for o in everything if not o["contactable"]]

    return {
        "opportunities": rows,
        "scope": scope,
        "shown": len(rows),
        # The relationship the whole product hangs on, in every response.
        **counts(everything, workspace.pipeline, daily_cap=workspace.daily_cap,
                product_matching_available=workspace.product_matching_available),
        "suppressed": suppressed[:50] if include_suppressed else [],
        "suppressed_count": len(suppressed),
        "influenced_value": round(sum(o.get("influenced_value") or 0 for o in inbox), 2),
        "incremental_value": round(sum(o.get("incremental_value") or 0 for o in inbox), 2),
        "triggers": sorted({o["trigger"] for o in everything}),
        # Same snapshot date as Overview, Action Center and Customers — never
        # this request's wall-clock time.
        "as_of": workspace.as_of.isoformat(),
    }


class SettingsUpdate(BaseModel):
    daily_cap: int | None = None


@router.get("/opportunities/settings")
def get_settings() -> dict[str, Any]:
    """Today's workload size — a store's own capacity, not a law of the engine."""
    return {"daily_cap": workspace.daily_cap}


@router.patch("/opportunities/settings")
def update_settings(payload: SettingsUpdate) -> dict[str, Any]:
    if payload.daily_cap is not None:
        if not (1 <= payload.daily_cap <= 200):
            raise HTTPException(400, "daily_cap must be between 1 and 200.")
        workspace.daily_cap = payload.daily_cap
        workspace.recompute()
    return {"daily_cap": workspace.daily_cap}


@router.get("/opportunities/{opportunity_id:path}")
def opportunity_detail(opportunity_id: str) -> dict[str, Any]:
    found = next((o for o in workspace.opportunities if o["id"] == opportunity_id), None)
    if not found:
        raise HTTPException(404, "Opportunity not found.")
    return found


@router.get("/actions")
def action_center(status: str = "", scope: str = "all") -> dict[str, Any]:
    """Everything an advisor has decided on, and everything still waiting."""
    # Scope first, then status. The status tiles count within the chosen scope,
    # or the screen would show "Awaiting decision 102" directly beside a chip
    # reading "Today's list · 20" and contradict itself.
    scoped = ([r for r in workspace.pipeline if r.get("prioritized_today")]
              if scope == "today" else workspace.pipeline)
    rows = [r for r in scoped if r.get("status") == status] if status else scoped

    by_status = {s: sum(1 for r in scoped if r.get("status") == s)
                 for s in PIPELINE_STATES}
    converted = [r for r in scoped if r.get("status") == "Converted"]

    # "New" spanning every detected opportunity implied hundreds of items were
    # waiting on the advisor today. Split it: what RevenueOS recommends working
    # now, and what it merely found and is holding.
    #
    # Today's list counts what was *prioritised*, whatever the advisor has since
    # done with it. Counting only undecided rows would shrink the number each
    # time someone approved one, so this screen would drift out of step with the
    # Overview over the course of a morning. Progress through the list is what
    # the status tiles are for.
    on_todays_list = sum(1 for r in workspace.pipeline if r.get("prioritized_today"))
    awaiting = sum(1 for r in workspace.pipeline
                   if r.get("status") == "New" and r.get("prioritized_today"))

    served_rows = rows[:400]
    if not workspace.product_matching_available:
        served_rows = [_scrub_unsupported_match(r) for r in served_rows]

    return {
        "rows": served_rows,
        "counts": by_status,
        "product_matching_available": workspace.product_matching_available,
        "todays_list": on_todays_list,
        "awaiting_decision": awaiting,
        "detected_not_prioritized": len(workspace.pipeline) - on_todays_list,
        "detected": len(workspace.pipeline),
        "total": len(rows),
        "statuses": PIPELINE_STATES,
        "scope": scope,
        "open": sum(1 for r in scoped if r.get("status") in OPEN_STATES),
        "closed": sum(1 for r in scoped if r.get("status") in CLOSED_STATES),
        "converted_value": round(
            sum(r.get("realised_value") or r.get("influenced_value") or 0
                for r in converted), 2),
        # Structured for aggregation from the start: this is the boutique's own
        # record of where its recommendations miss. Nothing consumes it yet.
        "decline_reasons": {
            code: sum(1 for r in scoped if r.get("decline_reason") == code)
            for code in DECLINE_REASONS
        },
        "decline_reason_labels": DECLINE_REASONS,
        "converted_value_basis": (
            "Recorded sale value where the advisor entered one, otherwise the "
            "estimate that was on the card."),
        # Same snapshot date as Overview, Opportunities and Customers.
        "as_of": workspace.as_of.isoformat(),
    }


@router.patch("/actions/{row_id:path}")
def update_action(row_id: str, payload: ActionUpdate) -> dict[str, Any]:
    if payload.status not in PIPELINE_STATES:
        raise HTTPException(400, f"Status must be one of {', '.join(PIPELINE_STATES)}.")
    # Setting something aside is the one decision that carries information the
    # engine cannot derive for itself, so it is the one decision that must say
    # why. Rejected before anything is written: a half-saved decision would
    # leave the card gone from the inbox and the reason lost.
    if payload.status == "Ignored":
        if not payload.reason:
            raise HTTPException(
                400, f"A reason is required: {', '.join(DECLINE_REASONS)}.")
        if payload.reason not in DECLINE_REASONS:
            raise HTTPException(400, f"Unknown reason '{payload.reason}'.")
    row = next((r for r in workspace.pipeline if r["id"] == row_id), None)
    if not row:
        raise HTTPException(404, "Action not found.")

    # Approving an outreach is a human decision, and it is recorded as one: no
    # message reaches a customer without a name and a timestamp against it.
    row["status"] = payload.status
    if payload.status == "Ignored":
        row["decline_reason"] = payload.reason
        row["decline_reason_label"] = DECLINE_REASONS[payload.reason]
        # Free text is optional and only meaningful against "Other"; it is kept
        # separate from `note` so the advisor's own notes are not overwritten.
        row["decline_note"] = (payload.reason_note or "").strip()[:500] or None
    else:
        # Changing your mind clears the reason — a row that is now Approved
        # must not still carry "wrong product" as its explanation.
        row.pop("decline_reason", None)
        row.pop("decline_reason_label", None)
        row.pop("decline_note", None)
    if payload.note is not None:
        row["note"] = payload.note
    if payload.realised_value is not None:
        row["realised_value"] = payload.realised_value
    row["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    audit_note = payload.note
    if payload.status == "Ignored":
        audit_note = " · ".join(
            p for p in (DECLINE_REASONS[payload.reason], payload.reason_note, payload.note) if p)
    workspace.audit(row_id, payload.status, audit_note)
    workspace.refresh_performance()
    workspace.save()
    return row


@router.get("/audit")
def audit_log(limit: int = 200) -> dict[str, Any]:
    """Who approved what, and when. Boring by design, and non-negotiable."""
    return {"entries": workspace.audit_log[:limit], "total": len(workspace.audit_log)}
