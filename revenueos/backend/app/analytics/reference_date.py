"""The one "today" every analytics module agrees on.

Each stage of the pipeline used to derive its own reference date independently
— mostly the same value, since they all look at transaction dates, but
``compliance.py`` and ``performance.py`` fell back straight to the real
wall-clock date when nothing else told them otherwise. On a demo dataset whose
newest transaction is days behind the real calendar, that meant outreach
frequency caps and recency math were quietly working from two different
"todays" in the same request. Computing it once here and threading it through
removes that seam.
"""
from __future__ import annotations

from datetime import date
from typing import Any


def resolve_as_of(
    transactions: list[dict[str, Any]],
    customers: list[dict[str, Any]] | None = None,
    inventory: list[dict[str, Any]] | None = None,
) -> date:
    """The latest date anything in the dataset tells us about.

    Transaction dates first — they are the most reliable signal of "when did
    this boutique last do something". Customer last-purchase and inventory
    arrival dates fill in when a boutique has summary data but no line-level
    transactions. Real wall-clock "today" is the last resort, used only when
    the dataset has no dates at all.
    """
    known = [t["date"] for t in transactions if t.get("date")]
    if customers:
        known += [c["last_purchase_date"] for c in customers if c.get("last_purchase_date")]
    if inventory:
        known += [p["arrival_date"] for p in inventory if p.get("arrival_date")]
    return max(known) if known else date.today()
