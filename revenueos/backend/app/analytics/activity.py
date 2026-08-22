"""One customer's activity history: what RevenueOS and the advisor did, in order.

Every entry here is read straight from ``workspace.audit_log`` — a persisted
event written once, at the moment it happened. Nothing is recomputed or
re-derived from the current pipeline, so a later recompute, a corrected store
assignment, or an opportunity fading off today's list can never rewrite what
this screen already showed.
"""
from __future__ import annotations

from typing import Any

# The stored pipeline status, said the way an advisor would — the same words
# Action Center's own status dropdown uses (see frontend/app/actions/page.tsx
# STATUS_LABEL). "Recommended" is not a pipeline status; it is the one event
# every opportunity starts with, logged the moment it is first detected.
EVENT_LABELS: dict[str, str] = {
    "Recommended": "Recommended",
    "Approved": "Ready to contact",
    "Scheduled": "Scheduled",
    "Contacted": "Contacted",
    "Converted": "Converted",
    "Ignored": "Set aside",
}


def customer_activity(customer_id: str, audit_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every persisted event for one customer, newest first.

    ``audit_log`` is already newest-first (entries are inserted at the head),
    so filtering preserves that order without a re-sort.
    """
    return [{
        "id": f"{e.get('action_id')}::{e.get('at')}::{e.get('status')}",
        "opportunity_id": e.get("action_id"),
        "status": e.get("status"),
        "label": EVENT_LABELS.get(e.get("status"), e.get("status")),
        "at": e.get("at"),
        "advisor": e.get("advisor"),
        "store": e.get("store"),
        "note": e.get("note"),
    } for e in audit_log if e.get("customer_id") == customer_id]
