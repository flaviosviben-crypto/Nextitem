"""Did RevenueOS make the boutique money? Measured from what advisors did.

Every figure here comes from the action log — opportunities generated, customers
actually contacted, conversions recorded — not from a model. Where a model is
involved the label says so.

The attribution is deliberately layered, because the honest answer has layers:

    Contacted revenue     purchases by customers an advisor contacted.
                          Observed, but not proof of cause.
    Influenced revenue    the part of that spend that followed the contact
                          within a plausible window. Still observed.
    Estimated incremental the share we are willing to claim RevenueOS caused,
                          after discounting what would likely have happened
                          anyway. Modelled — and the only number that is.

Without a holdout group, incremental revenue is an estimate and is always
presented as one.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .opportunities import CLOSED_STATES, INCREMENTALITY, OPEN_STATES

# A purchase this long after a contact is plausibly connected to it. Beyond the
# window we stop claiming any relationship at all.
ATTRIBUTION_WINDOW_DAYS = 30

CONTACTED_STATES = {"Contacted", "Converted"}


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "")).date()
        except ValueError:
            return None
    return None


def report(pipeline: list[dict[str, Any]], transactions: list[dict[str, Any]],
           as_of: date | None = None, window_days: int = 30) -> dict[str, Any]:
    """Performance over the trailing window, from advisor actions and real sales."""
    as_of = as_of or date.today()
    since = as_of - timedelta(days=window_days)

    recent = [r for r in pipeline if (_as_date(r.get("created_at")) or as_of) >= since]
    contacted = [r for r in recent if r.get("status") in CONTACTED_STATES]
    converted = [r for r in recent if r.get("status") == "Converted"]
    ignored = [r for r in recent if r.get("status") == "Ignored"]

    contacted_ids = {r["customer_id"] for r in contacted}
    conversion_rate = (len(converted) / len(contacted)) if contacted else None

    # --- observed revenue from contacted customers ---
    contacted_revenue = 0.0
    influenced_revenue = 0.0
    contact_dates = _contact_dates(contacted)
    for t in transactions:
        if t.get("customer_id") not in contacted_ids:
            continue
        tx_date = _as_date(t.get("date"))
        if not tx_date or tx_date < since:
            continue
        amount = float(t.get("line_total") or 0)
        contacted_revenue += amount
        contacted_on = contact_dates.get(t["customer_id"])
        if contacted_on and 0 <= (tx_date - contacted_on).days <= ATTRIBUTION_WINDOW_DAYS:
            influenced_revenue += amount

    # --- the modelled share we claim as caused ---
    incremental = 0.0
    for row in converted:
        share = INCREMENTALITY.get(row.get("trigger", ""), 0.5)
        # Prefer real observed spend for this customer; fall back to the estimate
        # that was on the card when the advisor acted.
        booked = row.get("realised_value") or row.get("basket_value") or row.get("influenced_value")
        if booked:
            incremental += float(booked) * share

    return {
        "window_days": window_days,
        "as_of": as_of.isoformat(),
        "opportunities_generated": len(recent),
        "customers_contacted": len(contacted_ids),
        "conversions": len(converted),
        "ignored": len(ignored),
        "open": sum(1 for r in recent if r.get("status") in OPEN_STATES),
        "untouched": sum(1 for r in recent
                         if r.get("status") not in OPEN_STATES | CLOSED_STATES),
        "conversion_rate": round(conversion_rate, 3) if conversion_rate is not None else None,

        "contacted_revenue": round(contacted_revenue, 2),
        "contacted_revenue_basis": (
            "All spend by contacted customers in this window. Observed, but not "
            "evidence that the contact caused it."),
        "influenced_revenue": round(influenced_revenue, 2),
        "influenced_revenue_basis": (
            f"Spend within {ATTRIBUTION_WINDOW_DAYS} days after a recorded contact. "
            "Observed and time-linked, still not proof of cause."),
        "estimated_incremental_revenue": round(incremental, 2),
        "incremental_revenue_basis": (
            "Converted opportunities, discounted by how likely that purchase was to "
            "happen anyway. Modelled, not measured — a holdout group is the only "
            "way to measure this properly."),
        "measurement_caveat": (
            "RevenueOS has no control group yet, so incremental revenue is an "
            "estimate. Contacted and influenced revenue are counted from real sales."),
        "by_trigger": _by_trigger(recent),
    }


def _contact_dates(rows: list[dict[str, Any]]) -> dict[str, date]:
    """Earliest recorded contact per customer, so attribution starts there."""
    out: dict[str, date] = {}
    for row in rows:
        when = _as_date(row.get("updated_at")) or _as_date(row.get("created_at"))
        if not when:
            continue
        cid = row["customer_id"]
        if cid not in out or when < out[cid]:
            out[cid] = when
    return out


def _by_trigger(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Which reasons for contact are actually working."""
    buckets: dict[str, dict[str, int]] = {}
    for row in rows:
        kind = row.get("trigger") or "unknown"
        b = buckets.setdefault(kind, {"generated": 0, "contacted": 0, "converted": 0})
        b["generated"] += 1
        if row.get("status") in CONTACTED_STATES:
            b["contacted"] += 1
        if row.get("status") == "Converted":
            b["converted"] += 1

    out = []
    for kind, b in buckets.items():
        rate = (b["converted"] / b["contacted"]) if b["contacted"] else None
        out.append({
            "trigger": kind, **b,
            "conversion_rate": round(rate, 3) if rate is not None else None,
        })
    out.sort(key=lambda r: -r["generated"])
    return out
