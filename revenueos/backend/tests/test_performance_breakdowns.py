"""Advisor/team, channel and reason breakdowns on the Performance page.

RevenueOS has no per-advisor login, so "advisor" here is sourced from the
POS's own Sales Advisor field on transactions — who has actually sold to a
customer, not who performed a given contact. These tests defend that the
breakdowns are built from real, sourced data, never invented, and that
filtering the page never lets the same purchase get double-counted across
more than one row of a table.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.analytics import performance as perf

AS_OF = date(2026, 8, 17)


def _row(rid, cid, status="New", prioritized=True, trigger="due",
         created_days_ago=5, updated_days_ago=None, channel=None):
    created = AS_OF - timedelta(days=created_days_ago)
    row = {
        "id": rid, "customer_id": cid, "status": status,
        "prioritized_today": prioritized,
        "first_prioritized_at": created.isoformat() if prioritized else None,
        "trigger": trigger, "created_at": created.isoformat(),
        "updated_at": (AS_OF - timedelta(days=updated_days_ago)).isoformat()
                      if updated_days_ago is not None else None,
        "influenced_value": 200.0, "basket_value": 200.0,
    }
    if channel:
        row["contact_channel"] = channel
    return row


def _tx(cid, days_ago, amount, advisor=None, order=None):
    return {
        "customer_id": cid, "transaction_id": order or f"O-{cid}-{days_ago}",
        "date": AS_OF - timedelta(days=days_ago), "line_total": amount,
        "advisor": advisor,
    }


# --------------------------------------------------------- advisor sourcing --

def test_advisor_is_derived_from_transaction_history_not_invented():
    """The mode of a real POS field, never a fabricated identity."""
    txs = [_tx("C1", 40, 500, advisor="ADV-1"), _tx("C1", 10, 300, advisor="ADV-1"),
           _tx("C2", 40, 400, advisor="ADV-2")]
    advisor_of = perf._customer_advisor_map(txs)
    assert advisor_of == {"C1": "ADV-1", "C2": "ADV-2"}
    # No transaction names an advisor for C3: absent, never guessed.
    assert "C3" not in advisor_of


def test_a_split_history_goes_to_whoever_sold_the_most():
    txs = [_tx("C1", 40, 500, advisor="ADV-1"), _tx("C1", 30, 500, advisor="ADV-1"),
           _tx("C1", 10, 500, advisor="ADV-2")]
    assert perf._customer_advisor_map(txs)["C1"] == "ADV-1"


# --------------------------------------------------------- team performance --

def test_by_advisor_breaks_down_recommendations_contacts_and_revenue():
    pipeline = [
        _row("opp::C1::due", "C1", status="Converted", updated_days_ago=20),
        _row("opp::C2::due", "C2", status="Contacted", updated_days_ago=15),
        _row("opp::C3::due", "C3", status="New"),
    ]
    txs = [
        _tx("C1", 40, 500, advisor="ADV-1"),   # before the contact: not "after contact"
        _tx("C1", 10, 300, advisor="ADV-1"),   # 10 days after a 20-day-old contact: counted
        _tx("C2", 5, 250, advisor="ADV-2"),    # 10 days after a 15-day-old contact: counted
        _tx("C3", 5, 999, advisor="ADV-1"),    # C3 was never contacted: irrelevant to revenue
    ]
    profiles = [{"customer_id": "C1", "store": "Milan"}, {"customer_id": "C2", "store": "Milan"},
                {"customer_id": "C3", "store": "Rome"}]
    report = perf.report(pipeline, txs, as_of=AS_OF, window_days=30, profiles=profiles)

    by_advisor = {r["advisor"]: r for r in report["by_advisor"]}
    assert by_advisor["ADV-1"]["recommended"] == 2       # C1 and C3
    assert by_advisor["ADV-1"]["decisions_made"] == 1    # only C1 has been decided
    assert by_advisor["ADV-1"]["contacted"] == 1          # C1 only; C3 is still New
    assert by_advisor["ADV-1"]["converted"] == 1
    assert by_advisor["ADV-1"]["conversion_rate"] == 1.0
    assert by_advisor["ADV-1"]["revenue_after_contact"] == 300.0

    assert by_advisor["ADV-2"]["recommended"] == 1
    assert by_advisor["ADV-2"]["contacted"] == 1
    assert by_advisor["ADV-2"]["converted"] == 0
    assert by_advisor["ADV-2"]["conversion_rate"] == 0.0
    assert by_advisor["ADV-2"]["revenue_after_contact"] == 250.0

    assert report["unattributed_recommendations_advisor"] == 0
    assert report["advisor_data_available"] is True


def test_by_store_uses_the_same_field_the_customers_page_filters_by():
    pipeline = [
        _row("opp::C1::due", "C1", status="Converted", updated_days_ago=20),
        _row("opp::C2::due", "C2", status="Contacted", updated_days_ago=15),
        _row("opp::C3::due", "C3", status="New"),
    ]
    txs = [_tx("C1", 10, 300, advisor="ADV-1"), _tx("C2", 5, 250, advisor="ADV-2")]
    profiles = [{"customer_id": "C1", "store": "Milan"}, {"customer_id": "C2", "store": "Milan"},
                {"customer_id": "C3", "store": "Rome"}]
    report = perf.report(pipeline, txs, as_of=AS_OF, window_days=30, profiles=profiles)

    by_store = {r["store"]: r for r in report["by_store"]}
    assert by_store["Milan"]["recommended"] == 2
    assert by_store["Milan"]["contacted"] == 2
    assert by_store["Milan"]["converted"] == 1
    assert by_store["Milan"]["revenue_after_contact"] == 550.0   # C1's 300 + C2's 250, not double-counted
    assert by_store["Rome"]["recommended"] == 1
    assert by_store["Rome"]["contacted"] == 0
    assert by_store["Rome"]["conversion_rate"] is None


def test_customers_without_a_known_advisor_are_named_not_dropped_silently():
    pipeline = [_row("opp::C1::due", "C1", status="New")]
    report = perf.report(pipeline, [], as_of=AS_OF, window_days=30)
    assert report["by_advisor"] == []
    assert report["unattributed_recommendations_advisor"] == 1
    assert report["advisor_data_available"] is False
    assert report["by_store"] == []
    assert report["store_data_available"] is False


# ---------------------------------------------------------------- filtering --

def test_advisor_filter_narrows_the_whole_report_not_just_the_table():
    pipeline = [
        _row("opp::C1::due", "C1", status="Converted", updated_days_ago=10),
        _row("opp::C2::due", "C2", status="Contacted", updated_days_ago=10),
    ]
    txs = [_tx("C1", 2, 500, advisor="ADV-1"), _tx("C2", 2, 300, advisor="ADV-2")]
    profiles = [{"customer_id": "C1", "store": "Milan"}, {"customer_id": "C2", "store": "Rome"}]

    full = perf.report(pipeline, txs, as_of=AS_OF, window_days=30, profiles=profiles)
    assert full["opportunities_detected"] == 2

    filtered = perf.report(pipeline, txs, as_of=AS_OF, window_days=30, profiles=profiles,
                           advisor="ADV-1")
    assert filtered["opportunities_detected"] == 1
    assert filtered["conversions"] == 1
    assert filtered["influenced_revenue"] == 500.0
    assert filtered["filters"]["advisor"] == "ADV-1"
    # The dropdown itself must not shrink to only what the filter left behind.
    assert filtered["filters"]["advisors"] == ["ADV-1", "ADV-2"]

    by_store_filter = perf.report(pipeline, txs, as_of=AS_OF, window_days=30, profiles=profiles,
                                  store="Rome")
    assert by_store_filter["opportunities_detected"] == 1
    assert by_store_filter["conversions"] == 0


# ------------------------------------------------------- channel performance --

def test_by_channel_only_counts_recorded_channels_and_names_the_rest():
    pipeline = [
        _row("opp::C1::due", "C1", status="Contacted", updated_days_ago=5, channel="email"),
        _row("opp::C2::due", "C2", status="Converted", updated_days_ago=5, channel="whatsapp"),
        # Contacted via a direct Action Center status change, bypassing the
        # outreach flow that stamps a channel — a real gap, not a bug to hide.
        _row("opp::C3::due", "C3", status="Contacted", updated_days_ago=5),
    ]
    report = perf.report(pipeline, [], as_of=AS_OF, window_days=30)

    by_channel = {r["channel"]: r for r in report["by_channel"]}
    # All five channels are always present, even unused ones.
    assert set(by_channel) == {"phone", "whatsapp", "email", "sms", "in_store"}
    assert by_channel["email"]["contacted"] == 1
    assert by_channel["email"]["converted"] == 0
    assert by_channel["whatsapp"]["contacted"] == 1
    assert by_channel["whatsapp"]["converted"] == 1
    assert by_channel["whatsapp"]["conversion_rate"] == 1.0
    assert by_channel["phone"]["contacted"] == 0
    assert by_channel["phone"]["conversion_rate"] is None

    # The bypassed contact is counted, but as a named gap, not folded into a channel.
    assert report["unspecified_channel_contacts"] == 1
    assert sum(c["contacted"] for c in report["by_channel"]) == 2


# -------------------------------------------------------- reason/template ---

def test_by_trigger_reports_revenue_and_the_template_limit_is_named():
    pipeline = [_row("opp::C1::due", "C1", status="Converted", trigger="due", updated_days_ago=10)]
    txs = [_tx("C1", 2, 400, advisor="ADV-1")]
    report = perf.report(pipeline, txs, as_of=AS_OF, window_days=30)

    row = next(r for r in report["by_trigger"] if r["trigger"] == "due")
    assert row["revenue_after_contact"] == 400.0

    assert report["template_attribution_supported"] is False
    assert "template" in report["template_attribution_note"].lower()
    assert "reason" in report["template_attribution_note"].lower()


def test_decisions_made_partitions_prioritized_today_with_awaiting_decision():
    pipeline = [
        _row("opp::C1::due", "C1", status="Contacted", updated_days_ago=1),
        _row("opp::C2::due", "C2", status="New"),
    ]
    report = perf.report(pipeline, [], as_of=AS_OF, window_days=30)
    assert report["decisions_made"] == 1
    assert report["awaiting_decision"] == 1
    assert report["decisions_made"] + report["awaiting_decision"] == report["prioritized_today"]
