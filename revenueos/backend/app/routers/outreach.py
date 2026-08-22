"""From an approved recommendation to something the advisor can actually send.

Approving used to change a status and stop. The advisor was then on their own
for the part that earns the money — working out what to say. This router closes
that gap: it hands back a draft built from the boutique's own data, and it
records a contact only when a human says one happened.

Nothing here sends anything. RevenueOS has no mail or messaging integration, so
it does not claim one: the advisor copies the text or opens it in their own
client, and marks the outreach done afterwards. Inferring "contacted" from a
copy or a link click would put an unverified event into the numbers Performance
reports as observed.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..analytics import outreach as drafting
from ..workspace import workspace

router = APIRouter(tags=["outreach"])

# Approved means decided but not yet acted on. The advisor sees "Ready to
# contact"; the stored value stays "Approved" so every existing pipeline row,
# audit entry and performance calculation keeps its meaning.
READY_STATE = "Approved"


class ContactRecord(BaseModel):
    channel: str
    message: str | None = None
    note: str | None = None


def _opportunity(opportunity_id: str) -> dict[str, Any]:
    found = next((o for o in workspace.opportunities if o["id"] == opportunity_id), None)
    if not found:
        raise HTTPException(404, "Opportunity not found.")
    return found


def _row(row_id: str) -> dict[str, Any]:
    found = next((r for r in workspace.pipeline if r["id"] == row_id), None)
    if not found:
        raise HTTPException(404, "Action not found.")
    return found


@router.get("/outreach/{opportunity_id:path}")
def outreach_draft(opportunity_id: str, channel: str = "") -> dict[str, Any]:
    """The draft for one recommendation, on the channel the advisor may use.

    Defaults to the preferred permitted channel, which is the one the compliance
    check already chose — so the draft an advisor sees is one they are allowed
    to send.
    """
    opp = _opportunity(opportunity_id)
    eligibility = opp.get("eligibility") or {}
    permitted = eligibility.get("channels", [])
    preferred = (eligibility.get("preferred_channel") or {}).get("key")
    chosen = channel or preferred or (permitted[0]["key"] if permitted else "in_store")

    profile = workspace.profile(opp["customer_id"]) or {}
    draft = drafting.build(opp, profile, chosen)

    # Tone only, and only when a key is configured. The deterministic draft is
    # already sendable, so an AI failure costs nothing.
    if draft["kind"] == "message":
        from ..ai import analyst

        draft = analyst.polish_outreach(draft, {
            "first_name": drafting.first_name(opp.get("customer_name")),
            "facts_used": draft.get("facts_used", []),
            "product": opp.get("product"),
            "store": profile.get("store"),
        })
        # The link carries the text, so it has to follow the text it was built
        # for — otherwise a polished draft opens WhatsApp with the old wording.
        draft["deep_link"] = drafting.deep_link(
            chosen, drafting.contact_detail(profile, chosen),
            draft.get("subject"), draft.get("body") or "")

    row = next((r for r in workspace.pipeline if r["id"] == opportunity_id), None)
    return {
        **draft,
        "channels": permitted,
        "blocked": eligibility.get("blocked", []),
        "eligibility_status": eligibility.get("status"),
        "eligibility_reason": eligibility.get("reason"),
        "status": (row or {}).get("status", "New"),
        "contacted_at": (row or {}).get("contacted_at"),
        # What was actually sent last time, if the advisor recorded one.
        "sent_message": (row or {}).get("outreach_message"),
        "action": opp.get("action"),
        "why_now": opp.get("why_now"),
        "influenced_value": opp.get("influenced_value"),
    }


@router.post("/outreach/{row_id:path}/contacted")
def mark_contacted(row_id: str, payload: ContactRecord) -> dict[str, Any]:
    """Record that a human contacted this customer, on this channel, just now.

    Only an explicit advisor action reaches here. Copying the text or opening a
    deep link does not, because neither is evidence the customer heard anything.
    """
    row = _row(row_id)
    if row.get("status") in {"Converted", "Ignored"}:
        raise HTTPException(409, f"This recommendation was already {row['status'].lower()}.")

    row["status"] = "Contacted"
    row["contact_channel"] = payload.channel
    row["contacted_at"] = datetime.utcnow().isoformat(timespec="seconds")
    row["updated_at"] = row["contacted_at"]
    if payload.note is not None:
        row["note"] = payload.note
    # The wording the advisor actually used, kept against the recommendation it
    # came from. One string on a row the snapshot already persists — no new
    # table, and it is what a later activity history will be built from.
    if payload.message:
        row["outreach_message"] = payload.message[:4000]

    workspace.audit(row_id, "Contacted",
                    payload.note or f"Contacted via {payload.channel}",
                    customer_id=row.get("customer_id"), store=row.get("store"),
                    advisor=row.get("advisor"))
    workspace.refresh_performance()
    workspace.save()
    return row
