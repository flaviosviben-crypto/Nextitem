"""Why an advisor said no, captured and kept.

A rejection is the only decision that carries information the engine cannot
derive for itself. These tests defend the two properties that make it worth
anything later: the reason is required, and it is structured.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.analytics.opportunities import DECLINE_REASONS
from app.main import app
from app.workspace import workspace


@pytest.fixture
def client():
    workspace.load_demo()
    with TestClient(app) as c:
        yield c


def _first(client) -> dict:
    return client.get("/api/opportunities").json()["opportunities"][0]


def _row(client, row_id: str) -> dict:
    return next(r for r in client.get("/api/actions").json()["rows"] if r["id"] == row_id)


def test_setting_aside_without_a_reason_is_refused(client):
    """And refused before anything is written — a half-saved decision would
    take the card out of the inbox and lose the reason with it."""
    opp = _first(client)
    refused = client.patch(f"/api/actions/{opp['id']}", json={"status": "Ignored"})
    assert refused.status_code == 400
    assert "reason" in refused.json()["detail"].lower()

    assert _row(client, opp["id"])["status"] == "New"
    assert opp["id"] in {o["id"] for o in client.get("/api/opportunities").json()["opportunities"]}


def test_an_unknown_reason_is_refused(client):
    opp = _first(client)
    refused = client.patch(f"/api/actions/{opp['id']}",
                           json={"status": "Ignored", "reason": "just_because"})
    assert refused.status_code == 400
    assert _row(client, opp["id"])["status"] == "New"


@pytest.mark.parametrize("code", list(DECLINE_REASONS))
def test_every_structured_reason_saves(client, code):
    opp = _first(client)
    saved = client.patch(f"/api/actions/{opp['id']}", json={"status": "Ignored", "reason": code})
    assert saved.status_code == 200

    body = saved.json()
    assert body["status"] == "Ignored"
    # The code is the record; the label is for reading.
    assert body["decline_reason"] == code
    assert body["decline_reason_label"] == DECLINE_REASONS[code]


def test_other_carries_an_optional_note(client):
    opp = _first(client)
    with_note = client.patch(
        f"/api/actions/{opp['id']}",
        json={"status": "Ignored", "reason": "other", "reason_note": "She moved to Paris."},
    ).json()
    assert with_note["decline_reason"] == "other"
    assert with_note["decline_note"] == "She moved to Paris."

    # The note is genuinely optional.
    other = client.get("/api/opportunities").json()["opportunities"][0]
    assert client.patch(f"/api/actions/{other['id']}",
                        json={"status": "Ignored", "reason": "other"}).json()["decline_note"] is None


def test_the_reason_reaches_action_center_and_the_audit_log(client):
    opp = _first(client)
    client.patch(f"/api/actions/{opp['id']}",
                 json={"status": "Ignored", "reason": "wrong_product"})

    row = _row(client, opp["id"])
    assert row["status"] == "Ignored"
    assert row["decline_reason_label"] == "Wrong product"

    entry = next(e for e in client.get("/api/audit").json()["entries"]
                 if e["action_id"] == opp["id"])
    assert entry["status"] == "Ignored"
    assert "Wrong product" in entry["note"]


def test_reasons_are_counted_for_later_analysis(client):
    """Structured from the start so it can be aggregated. Nothing consumes it
    yet — this task collects the feedback, it does not learn from it."""
    feed = client.get("/api/opportunities").json()["opportunities"]
    client.patch(f"/api/actions/{feed[0]['id']}",
                 json={"status": "Ignored", "reason": "wrong_product"})
    client.patch(f"/api/actions/{feed[1]['id']}",
                 json={"status": "Ignored", "reason": "wrong_product"})
    client.patch(f"/api/actions/{feed[2]['id']}",
                 json={"status": "Ignored", "reason": "low_relevance"})

    centre = client.get("/api/actions").json()
    assert centre["decline_reasons"]["wrong_product"] == 2
    assert centre["decline_reasons"]["low_relevance"] == 1
    assert centre["decline_reasons"]["contacted_recently"] == 0
    assert centre["decline_reason_labels"] == DECLINE_REASONS


def test_a_saved_decision_removes_the_card_and_survives_a_refresh(client):
    opp = _first(client)
    before = client.get("/api/opportunities").json()

    client.patch(f"/api/actions/{opp['id']}",
                 json={"status": "Ignored", "reason": "contacted_recently"})

    after = client.get("/api/opportunities").json()
    assert opp["id"] not in {o["id"] for o in after["opportunities"]}
    assert after["awaiting_decision"] == before["awaiting_decision"] - 1
    # The day still recommended it; only the queue shrank.
    assert after["prioritized_today"] == before["prioritized_today"]
    assert after["decisions_made"] == before["decisions_made"] + 1

    # Re-reading is what a browser refresh does.
    assert opp["id"] not in {o["id"] for o in client.get("/api/opportunities").json()["opportunities"]}
    assert _row(client, opp["id"])["decline_reason"] == "contacted_recently"


def test_changing_your_mind_clears_the_reason(client):
    """A row that is now Approved must not still say "wrong product"."""
    opp = _first(client)
    client.patch(f"/api/actions/{opp['id']}", json={"status": "Ignored", "reason": "wrong_product"})
    reopened = client.patch(f"/api/actions/{opp['id']}", json={"status": "Approved"}).json()
    assert reopened["status"] == "Approved"
    assert reopened.get("decline_reason") is None
    assert reopened.get("decline_reason_label") is None


def test_approve_and_schedule_still_need_no_reason(client):
    feed = client.get("/api/opportunities").json()["opportunities"]
    assert client.patch(f"/api/actions/{feed[0]['id']}",
                        json={"status": "Approved"}).status_code == 200
    assert client.patch(f"/api/actions/{feed[1]['id']}",
                        json={"status": "Scheduled"}).status_code == 200


def test_a_recompute_does_not_erase_the_reason(client):
    """Opportunities are rebuilt on every import; the advisor's record is not."""
    opp = _first(client)
    client.patch(f"/api/actions/{opp['id']}", json={"status": "Ignored", "reason": "low_relevance"})

    workspace.recompute()

    row = next(r for r in workspace.pipeline if r["id"] == opp["id"])
    assert row["status"] == "Ignored"
    assert row["decline_reason"] == "low_relevance"
    assert row["decline_reason_label"] == "Low relevance"
