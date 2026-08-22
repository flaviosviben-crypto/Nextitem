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

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from . import reference_date
from .opportunities import CLOSED_STATES, INCREMENTALITY, OPEN_STATES

# A purchase this long after a contact is plausibly connected to it. Beyond the
# window we stop claiming any relationship at all.
ATTRIBUTION_WINDOW_DAYS = 30

CONTACTED_STATES = {"Contacted", "Converted"}

# The channels a contact can actually be recorded on (mirrors
# ``compliance.CHANNELS``, kept as a plain map here so this module never has
# to import compliance just to label a breakdown table).
CHANNEL_LABELS: dict[str, str] = {
    "phone": "Phone", "whatsapp": "WhatsApp", "email": "Email",
    "sms": "SMS", "in_store": "In store",
}


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
           as_of: date | None = None, window_days: int = 30,
           profiles: list[dict[str, Any]] | None = None,
           advisor: str | None = None, store: str | None = None) -> dict[str, Any]:
    """Performance over the trailing window, from advisor actions and real sales.

    ``advisor`` and ``store`` narrow the whole report to one team member or
    location before anything else is computed, so every figure below — the
    funnel, the revenue lines, every breakdown table — describes that scope
    consistently instead of mixing a filtered headline with unfiltered detail.

    Advisor and store are both read from the customer, not the recommendation:
    RevenueOS has no per-advisor login, so there is no record of who performed
    a given outreach. ``advisor`` here is who has actually sold to that
    customer the most in transaction records — a real, sourced fact, just not
    the same claim as "who made this contact".
    """
    as_of = as_of or reference_date.resolve_as_of(transactions)
    since = as_of - timedelta(days=window_days)

    # Built from the full dataset handed in, before any filter narrows it —
    # both so the filter itself has something to test customers against, and
    # so the "which advisors/stores exist" lists a UI would show do not shrink
    # to whatever is left after the filter is applied.
    advisor_of = _customer_advisor_map(transactions)
    store_of = {p["customer_id"]: p.get("store") for p in (profiles or []) if p.get("store")}

    if advisor:
        pipeline = [r for r in pipeline if advisor_of.get(r.get("customer_id")) == advisor]
        transactions = [t for t in transactions if advisor_of.get(t.get("customer_id")) == advisor]
    if store:
        pipeline = [r for r in pipeline if store_of.get(r.get("customer_id")) == store]
        transactions = [t for t in transactions if store_of.get(t.get("customer_id")) == store]

    recent = [r for r in pipeline if (_as_date(r.get("created_at")) or as_of) >= since]
    contacted = [r for r in recent if r.get("status") in CONTACTED_STATES]
    converted = [r for r in recent if r.get("status") == "Converted"]
    ignored = [r for r in recent if r.get("status") == "Ignored"]
    decided = OPEN_STATES | CLOSED_STATES

    contacted_ids = {r["customer_id"] for r in contacted}
    conversion_rate = (len(converted) / len(contacted)) if contacted else None
    # Recommended rows this window has ruled on, one way or another — same
    # "decided" set opportunities.OPEN_STATES | CLOSED_STATES already uses, so
    # this line and ``awaiting_decision`` below always partition prioritized_today.
    decisions_made = sum(1 for r in recent
                         if _was_prioritized(r) and r.get("status") not in (None, "New"))

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

    # --- sales the advisor recorded against a converted opportunity ---
    # These are observed too, just through a different channel: an advisor typing
    # in what the customer bought. They often precede the POS export, which is
    # why a boutique can show recorded sales while influenced revenue is still nil.
    recorded_sales = sum(float(r["realised_value"]) for r in converted
                         if r.get("realised_value"))
    recorded_count = sum(1 for r in converted if r.get("realised_value"))

    # --- the modelled share we claim as caused ---
    incremental = 0.0
    estimated_rows = 0
    for row in converted:
        share = INCREMENTALITY.get(row.get("trigger", ""), 0.5)
        booked = row.get("realised_value")
        if not booked:
            # No recorded sale value: fall back to what was on the card, and count
            # the row so the basis can say how much of this is estimate on estimate.
            booked = row.get("basket_value") or row.get("influenced_value")
            estimated_rows += 1
        if booked:
            incremental += float(booked) * share

    by_advisor, unattributed_advisor = _by_advisor(recent, transactions, since, advisor_of)
    by_store, unattributed_store = _by_store(recent, transactions, since, store_of)
    by_channel, unspecified_channel_contacts = _by_channel(recent, transactions, since)

    return {
        "window_days": window_days,
        "as_of": as_of.isoformat(),
        # Detected is the universe the engine found; prioritised is what it
        # recommended working. Conflating them was the ambiguity this fixes.
        "opportunities_detected": len(recent),
        # A historical fact — was this ever prioritized — not "is it in today's
        # live list right now".
        "prioritized_today": sum(1 for r in recent if _was_prioritized(r)),
        "customers_contacted": len(contacted_ids),
        "conversions": len(converted),
        "ignored": len(ignored),
        "open": sum(1 for r in recent if r.get("status") in OPEN_STATES),
        # "Untouched" spans every detected opportunity, including the ones the
        # engine never put in front of anyone. Reported as a single number it
        # read as a backlog of work owed by the advisor. Split it: what is
        # genuinely waiting on a decision today, and what was merely detected
        # and held back. The old total stays for callers that want the sum.
        "untouched": sum(1 for r in recent if r.get("status") not in decided),
        "awaiting_decision": sum(1 for r in recent
                                 if r.get("status") not in decided
                                 and _was_prioritized(r)),
        "detected_not_recommended": sum(1 for r in recent
                                        if r.get("status") not in decided
                                        and not _was_prioritized(r)),
        "conversion_rate": round(conversion_rate, 3) if conversion_rate is not None else None,
        # The same sum Today's Opportunities and the Overview show, so a
        # workspace with nothing measured yet can still say what is on the table.
        # No new estimate: it adds up the value each row had when it was
        # generated, so a later recompute cannot quietly rewrite the total.
        "prioritized_expected_value": round(
            sum(float(r.get("influenced_value_generated") or r.get("influenced_value") or 0)
                for r in recent if _was_prioritized(r)), 2),

        "contacted_revenue": round(contacted_revenue, 2),
        "contacted_revenue_basis": (
            "All spend by contacted customers in this window. Observed, but not "
            "evidence that the contact caused it."),
        "influenced_revenue": round(influenced_revenue, 2),
        "influenced_revenue_basis": (
            f"Spend within {ATTRIBUTION_WINDOW_DAYS} days after a recorded contact. "
            "Observed and time-linked, still not proof of cause."),
        "recorded_sales": round(recorded_sales, 2),
        "recorded_sales_count": recorded_count,
        "recorded_sales_basis": (
            f"Sale values advisors entered against {recorded_count} converted "
            f"{'opportunity' if recorded_count == 1 else 'opportunities'}. Observed, and "
            "often ahead of the till export — which is why this can exceed the "
            "revenue matched from transactions."),
        "estimated_incremental_revenue": round(incremental, 2),
        "incremental_revenue_basis": (
            "Converted opportunities, discounted by how likely that purchase was to "
            "happen anyway. Modelled, not measured — a holdout group is the only "
            "way to measure this properly."
            + (f" {estimated_rows} of {len(converted)} had no sale value entered, so "
               "the card's estimate was used for those."
               if estimated_rows else "")),
        "measurement_caveat": (
            "RevenueOS has no control group yet, so incremental revenue is an "
            "estimate. Contacted revenue, revenue after contact and recorded sales "
            "are all counted from real observations."),
        # Ruled on vs. still in the inbox always add up to prioritized_today,
        # the same partition the funnel below already shows.
        "decisions_made": decisions_made,

        # ----- Section 3: message/outreach effectiveness, by reason -----
        # RevenueOS records the trigger a recommendation was generated for; it
        # does not record which specific wording or template variant an
        # advisor actually sent, so that is the finest grain honestly
        # available. Section, not screen: this stays reason-level everywhere.
        "by_trigger": _by_trigger(recent, transactions, since),
        "template_attribution_supported": False,
        "template_attribution_note": (
            "RevenueOS does not track which message wording or template was sent — "
            "only the reason a recommendation was generated for. The table below is "
            "reason-level effectiveness, not template-level."),

        # ----- Section 1: advisor / team performance -----
        "by_advisor": by_advisor,
        "advisor_data_available": bool(advisor_of),
        "unattributed_recommendations_advisor": unattributed_advisor,
        "advisor_attribution_basis": (
            "Advisor is whoever has sold the most to that customer in transaction "
            "records. RevenueOS has no per-advisor login yet, so it cannot say who "
            "personally made a given contact — this names who has served the "
            "customer historically, not who sent this outreach."),

        "by_store": by_store,
        "store_data_available": bool(store_of),
        "unattributed_recommendations_store": unattributed_store,
        "store_attribution_basis": (
            "Store is the customer's own preferred store field, or failing that the "
            "store most of their purchases were made in — the same definition the "
            "Customers page filters by."),

        # ----- Section 2: channel performance -----
        "by_channel": by_channel,
        "unspecified_channel_contacts": unspecified_channel_contacts,
        "channel_basis": (
            "Counted only from contacts recorded through the outreach flow, which "
            "stamps the channel actually used. A contact marked done without going "
            "through it (a direct status change) cannot be attributed to a channel."),

        # Present on every request so a filtered page can still populate its
        # own dropdowns without a second call — built from the full dataset,
        # never from whatever the current advisor/store filter left behind.
        "filters": {
            "advisor": advisor or None,
            "store": store or None,
            "advisors": sorted(set(advisor_of.values())),
            "stores": sorted(set(v for v in store_of.values() if v)),
        },
    }


def _was_prioritized(row: dict[str, Any]) -> bool:
    """Historical fact: did this ever make a day's prioritized list.

    Prefers the frozen ``first_prioritized_at`` timestamp; falls back to the
    live ``prioritized_today`` flag for rows recorded before that field
    existed, so old reports do not lose these rows outright.
    """
    return bool(row.get("first_prioritized_at") or row.get("prioritized_today"))


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


def _customer_advisor_map(transactions: list[dict[str, Any]]) -> dict[str, str]:
    """Which advisor has sold each customer the most, from transaction records.

    RevenueOS has no per-advisor login, so there is nothing that names who
    performed a given outreach — this reads the POS's own "Sales Advisor"
    field instead, which is a real fact about who has served this customer,
    just not the same claim. A customer with no advisor on any transaction
    line simply has no entry here — never a guess.
    """
    per_customer: dict[str, Counter] = {}
    for t in transactions:
        advisor, cid = t.get("advisor"), t.get("customer_id")
        if not advisor or not cid:
            continue
        per_customer.setdefault(cid, Counter())[advisor] += 1
    return {cid: counter.most_common(1)[0][0] for cid, counter in per_customer.items()}


def _revenue_after_contact(customer_ids: set[str], contact_dates: dict[str, date],
                           transactions: list[dict[str, Any]], since: date) -> float:
    """Spend within the attribution window of a recorded contact, for one group.

    Reads real transactions rather than summing any row's stored estimate, so
    a customer with more than one historical recommendation in the group never
    has their purchases counted twice within it.
    """
    total = 0.0
    for t in transactions:
        cid = t.get("customer_id")
        if cid not in customer_ids:
            continue
        tx_date = _as_date(t.get("date"))
        if not tx_date or tx_date < since:
            continue
        contacted_on = contact_dates.get(cid)
        if contacted_on and 0 <= (tx_date - contacted_on).days <= ATTRIBUTION_WINDOW_DAYS:
            total += float(t.get("line_total") or 0)
    return total


def _cohort_metrics(rows: list[dict[str, Any]], transactions: list[dict[str, Any]],
                    since: date, key_fn, cohort: str) -> dict[Any, dict[str, Any]]:
    """Shared aggregation behind every breakdown table on this page.

    ``cohort="recommended"`` starts from every row this key was ever
    recommended for in the window — the same population ``_by_trigger``
    already used, extended to advisor and store. ``cohort="contacted"`` starts
    from rows that were actually contacted, for the channel table, which has
    no "recommended" concept of its own (a channel is only known once a
    contact happens).

    Every group's revenue is summed from that group's own contacted customers
    against real transactions, exactly like the page total — never by
    re-summing a row's stored estimate, which would let one customer's
    repeated recommendations inflate more than one group's revenue at once.
    """
    buckets: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        if cohort == "recommended" and not _was_prioritized(row):
            continue
        if cohort == "contacted" and row.get("status") not in CONTACTED_STATES:
            continue
        buckets.setdefault(key_fn(row), []).append(row)

    out: dict[Any, dict[str, Any]] = {}
    for key, group_rows in buckets.items():
        contacted = [r for r in group_rows if r.get("status") in CONTACTED_STATES]
        converted = [r for r in group_rows if r.get("status") == "Converted"]
        contacted_ids = {r["customer_id"] for r in contacted}
        contact_dates = _contact_dates(contacted)
        revenue_after_contact = _revenue_after_contact(contacted_ids, contact_dates,
                                                        transactions, since)

        incremental = 0.0
        for row in converted:
            share = INCREMENTALITY.get(row.get("trigger", ""), 0.5)
            booked = row.get("realised_value") or row.get("basket_value") or row.get("influenced_value")
            if booked:
                incremental += float(booked) * share

        rate = (len(converted) / len(contacted)) if contacted else None
        entry: dict[str, Any] = {
            "contacted": len(contacted),
            "converted": len(converted),
            "conversion_rate": round(rate, 3) if rate is not None else None,
            "revenue_after_contact": round(revenue_after_contact, 2),
            "estimated_incremental_revenue": round(incremental, 2),
        }
        if cohort == "recommended":
            entry["recommended"] = len(group_rows)
            entry["decisions_made"] = sum(1 for r in group_rows
                                          if r.get("status") not in (None, "New"))
        out[key] = entry
    return out


def _by_trigger(rows: list[dict[str, Any]], transactions: list[dict[str, Any]],
                since: date) -> list[dict[str, Any]]:
    """Which reasons for contact are actually working.

    Counted from ``recommended``, not every detected opportunity: a card an
    advisor never saw could not have been contacted or converted, so counting
    it here would understate how well a reason performs once it actually
    reaches someone. Recommended -> contacted -> converted is one coherent
    cohort, not three different populations sharing a table.

    This is reason-level, not template-level — RevenueOS does not record which
    specific wording an advisor sent, only the trigger a card was made for.
    """
    grouped = _cohort_metrics(rows, transactions, since,
                              lambda r: r.get("trigger") or "unknown", "recommended")
    out = [{
        "trigger": kind,
        "recommended": g["recommended"],
        "contacted": g["contacted"],
        "converted": g["converted"],
        "conversion_rate": g["conversion_rate"],
        "revenue_after_contact": g["revenue_after_contact"],
    } for kind, g in grouped.items()]
    out.sort(key=lambda r: -r["recommended"])
    return out


def _by_advisor(rows: list[dict[str, Any]], transactions: list[dict[str, Any]], since: date,
                advisor_of: dict[str, str]) -> tuple[list[dict[str, Any]], int]:
    """Recommendations, decisions, contacts and revenue, broken down by advisor.

    Returns the breakdown plus how many recommended rows could not be matched
    to any advisor (no transaction on file names one) — reported so the table
    never silently under-counts against the page total.
    """
    grouped = _cohort_metrics(rows, transactions, since,
                              lambda r: advisor_of.get(r.get("customer_id")), "recommended")
    unattributed = grouped.pop(None, None)
    out = [{"advisor": key, **g} for key, g in grouped.items()]
    out.sort(key=lambda r: -r["recommended"])
    return out, (unattributed["recommended"] if unattributed else 0)


def _by_store(rows: list[dict[str, Any]], transactions: list[dict[str, Any]], since: date,
             store_of: dict[str, str]) -> tuple[list[dict[str, Any]], int]:
    """The same breakdown as ``_by_advisor``, by store instead."""
    grouped = _cohort_metrics(rows, transactions, since,
                              lambda r: store_of.get(r.get("customer_id")), "recommended")
    unattributed = grouped.pop(None, None)
    out = [{"store": key, **g} for key, g in grouped.items()]
    out.sort(key=lambda r: -r["recommended"])
    return out, (unattributed["recommended"] if unattributed else 0)


def _by_channel(rows: list[dict[str, Any]], transactions: list[dict[str, Any]],
                since: date) -> tuple[list[dict[str, Any]], int]:
    """Contacted, converted, conversion rate and revenue, by channel actually used.

    Every one of the five channels a contact can be recorded on is always
    returned, zeroed if unused, so the table reads as a complete answer rather
    than a list that grows as data arrives. Contacts recorded without a
    channel (a status changed directly in the Action Center, bypassing the
    outreach flow) are counted and returned separately rather than guessed at.
    """
    grouped = _cohort_metrics(rows, transactions, since,
                              lambda r: r.get("contact_channel"), "contacted")
    unspecified = grouped.pop(None, None)
    out = []
    for key in ("phone", "whatsapp", "email", "sms", "in_store"):
        g = grouped.get(key) or {"contacted": 0, "converted": 0, "conversion_rate": None,
                                 "revenue_after_contact": 0.0}
        out.append({
            "channel": key,
            "channel_label": CHANNEL_LABELS[key],
            "contacted": g["contacted"],
            "converted": g["converted"],
            "conversion_rate": g["conversion_rate"],
            "revenue_after_contact": g["revenue_after_contact"],
        })
    return out, (unspecified["contacted"] if unspecified else 0)
