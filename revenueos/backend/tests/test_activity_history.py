"""Store filtering on Action Center, and a customer's activity history.

The history is a plain read of ``workspace.audit_log`` (see
``app/analytics/activity.py``): every event is written once, when it happens,
and never recomputed from the pipeline's current state. These tests defend
that a recompute cannot duplicate or rewrite what already happened, and that a
no-op decision cannot pad the timeline with a copy of the last event.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.workspace import workspace


@pytest.fixture
def client():
    workspace.load_demo()
    with TestClient(app) as c:
        yield c


def _first_action(client) -> dict:
    return client.get("/api/actions").json()["rows"][0]


def _activity(client, customer_id: str) -> list[dict]:
    return client.get(f"/api/customers/{customer_id}").json()["activity"]


# --------------------------------------------------------------- store filter --

def test_action_center_reports_real_stores_only():
    """The facet is read off actual rows, never invented."""
    workspace.load_demo()
    with TestClient(app) as client:
        body = client.get("/api/actions").json()
        assert body["stores"]
        real_stores = {r.get("store") for r in workspace.pipeline if r.get("store")}
        assert set(body["stores"]) == real_stores
        # Every row genuinely carries the store the customer's own data has.
        by_id = {p["customer_id"]: p.get("store") for p in workspace.profiles}
        for row in workspace.pipeline:
            assert row.get("store") == by_id.get(row["customer_id"])


def test_filtering_by_store_narrows_every_row_to_that_store(client):
    all_rows = client.get("/api/actions").json()["rows"]
    stores = sorted({r["store"] for r in all_rows if r.get("store")})
    assert stores, "demo data should carry a store on every row"
    target = stores[0]

    filtered = client.get("/api/actions", params={"store": target}).json()
    assert filtered["rows"], "the chosen store should have at least one row"
    assert all(r.get("store") == target for r in filtered["rows"])
    assert filtered["store"] == target
    # Narrower or equal — never more rows than the unfiltered screen.
    assert filtered["total"] <= client.get("/api/actions").json()["total"]


def test_an_unknown_store_returns_nothing_not_an_error(client):
    body = client.get("/api/actions", params={"store": "Nowhereville"}).json()
    assert body["rows"] == []
    assert body["total"] == 0


def test_store_filter_composes_with_status_and_scope(client):
    stores = client.get("/api/actions").json()["stores"]
    target = stores[0]
    combined = client.get(
        "/api/actions", params={"store": target, "scope": "today", "status": "New"}).json()
    assert all(r.get("store") == target and r.get("status") == "New" for r in combined["rows"])


# ---------------------------------------------------------- activity history --

def test_a_new_opportunity_is_recorded_as_recommended(client):
    row = _first_action(client)
    events = _activity(client, row["customer_id"])
    assert events, "every opportunity should leave a Recommended event"
    recommended = [e for e in events if e["opportunity_id"] == row["id"]]
    assert len(recommended) == 1
    event = recommended[0]
    assert event["status"] == "Recommended"
    assert event["label"] == "Recommended"
    assert event["at"]
    # Real relationships, not invented — present because the demo data has them.
    assert event["store"] == row.get("store")


def test_a_decision_appends_an_event_in_the_advisors_words(client):
    row = _first_action(client)
    client.patch(f"/api/actions/{row['id']}", json={"status": "Approved"})

    events = _activity(client, row["customer_id"])
    approved = [e for e in events if e["opportunity_id"] == row["id"] and e["status"] == "Approved"]
    assert len(approved) == 1
    # Same word Action Center's own status control uses for "Approved".
    assert approved[0]["label"] == "Ready to contact"
    assert approved[0]["advisor"] == row.get("advisor")
    assert approved[0]["store"] == row.get("store")


def test_ignored_is_shown_as_set_aside(client):
    row = _first_action(client)
    client.patch(f"/api/actions/{row['id']}", json={"status": "Ignored", "reason": "low_relevance"})

    events = _activity(client, row["customer_id"])
    ignored = next(e for e in events if e["opportunity_id"] == row["id"] and e["status"] == "Ignored")
    assert ignored["label"] == "Set aside"
    assert "Low relevance" in (ignored["note"] or "")


def test_the_full_lifecycle_reads_back_in_order(client):
    """Recommended, then every decision the advisor made, newest first."""
    row = _first_action(client)
    for status in ("Approved", "Scheduled", "Contacted", "Converted"):
        assert client.patch(f"/api/actions/{row['id']}", json={"status": status}).status_code == 200

    events = [e for e in _activity(client, row["customer_id"]) if e["opportunity_id"] == row["id"]]
    labels = [e["label"] for e in events]
    # Newest first: Converted was last, Recommended was first.
    assert labels == ["Converted", "Contacted", "Scheduled", "Ready to contact", "Recommended"]


# ------------------------------------------------------------- data integrity --

def test_repeating_the_same_decision_does_not_duplicate_the_event(client):
    """A resubmitted, unchanged PATCH must not pad the timeline."""
    row = _first_action(client)
    client.patch(f"/api/actions/{row['id']}", json={"status": "Approved"})
    client.patch(f"/api/actions/{row['id']}", json={"status": "Approved"})
    client.patch(f"/api/actions/{row['id']}", json={"status": "Approved"})

    events = [e for e in _activity(client, row["customer_id"])
              if e["opportunity_id"] == row["id"] and e["status"] == "Approved"]
    assert len(events) == 1


def test_a_genuinely_new_note_or_value_still_gets_recorded(client):
    """Not every repeat is a no-op: a new realised value on an already-Converted
    row is real information and must be written down."""
    row = _first_action(client)
    client.patch(f"/api/actions/{row['id']}", json={"status": "Converted", "realised_value": 500})
    client.patch(f"/api/actions/{row['id']}", json={"status": "Converted", "realised_value": 650})

    events = [e for e in _activity(client, row["customer_id"])
              if e["opportunity_id"] == row["id"] and e["status"] == "Converted"]
    assert len(events) == 2


def test_recompute_does_not_duplicate_recommended_events(client):
    """Opportunities are rebuilt on every import; the history is not."""
    row = _first_action(client)
    before = len(_activity(client, row["customer_id"]))

    workspace.recompute()
    workspace.recompute()

    after = _activity(client, row["customer_id"])
    assert len(after) == before
    recommended = [e for e in after if e["opportunity_id"] == row["id"] and e["status"] == "Recommended"]
    assert len(recommended) == 1


def test_recompute_does_not_rewrite_a_historical_store_or_advisor(client):
    """A later correction to a customer's store must not repaint history."""
    row = _first_action(client)
    original_store = row.get("store")
    assert original_store

    events_before = _activity(client, row["customer_id"])
    recommended_before = next(e for e in events_before
                              if e["opportunity_id"] == row["id"] and e["status"] == "Recommended")
    assert recommended_before["store"] == original_store

    # Simulate a correction to the customer's own record, as a re-import would.
    for rec in workspace.customers_raw:
        if rec["customer_id"] == row["customer_id"]:
            rec["store"] = "Corrected Store"
    workspace.recompute()

    # The live row now reflects the correction...
    updated_row = next(r for r in workspace.pipeline if r["id"] == row["id"])
    assert updated_row["store"] == "Corrected Store"

    # ...but the event already logged still says what was true when it happened.
    events_after = _activity(client, row["customer_id"])
    recommended_after = next(e for e in events_after
                             if e["opportunity_id"] == row["id"] and e["status"] == "Recommended")
    assert recommended_after["store"] == original_store
    assert recommended_after["at"] == recommended_before["at"]


def test_timestamps_are_consistent_across_event_kinds(client):
    row = _first_action(client)
    client.patch(f"/api/actions/{row['id']}", json={"status": "Approved"})

    events = [e for e in _activity(client, row["customer_id"]) if e["opportunity_id"] == row["id"]]
    assert len(events) == 2
    for event in events:
        # Every event uses the same isoformat(timespec="seconds") shape — parses
        # cleanly and round-trips, never a bare date mixed in with a datetime.
        parsed = datetime.fromisoformat(event["at"])
        assert parsed.isoformat(timespec="seconds") == event["at"]


def test_history_survives_a_recompute_even_if_the_opportunity_fades(client):
    """An opportunity that no longer clears the bar still keeps its record."""
    row = _first_action(client)
    client.patch(f"/api/actions/{row['id']}", json={"status": "Ignored", "reason": "low_relevance"})
    before = _activity(client, row["customer_id"])
    assert any(e["opportunity_id"] == row["id"] for e in before)

    # Remove every trace of the opportunity from the live pipeline, as a
    # recompute that no longer detects it would.
    workspace.pipeline = [r for r in workspace.pipeline if r["id"] != row["id"]]

    after = _activity(client, row["customer_id"])
    assert any(e["opportunity_id"] == row["id"] for e in after)
    assert after == before
