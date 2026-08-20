"""Approve, then say something: the outreach workflow end to end.

The product claim this file defends is that approving a recommendation produces
something the advisor can use, that it works with no AI key configured, and that
"contacted" only ever means a human said so.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.analytics import outreach
from app.main import app
from app.workspace import workspace


@pytest.fixture
def client():
    """A freshly seeded, undecided queue per test — these tests consume it."""
    workspace.load_demo()
    with TestClient(app) as c:
        yield c


def _first(client) -> dict:
    return client.get("/api/opportunities").json()["opportunities"][0]


def _profile_with(**overrides) -> dict:
    base = {
        "customer_id": "C1", "name": "Pietro Fontana", "store": "Milano Brera",
        "email": "p@example.com", "phone": "+39 320 1112223",
        "category_affinity": {"Leather Goods": 0.86},
        "brand_affinity": {"Sessùn": 0.2},
        "size_affinity_by_family": {"Ready-to-Wear": {"S": 1.0}},
    }
    return {**base, **overrides}


def _opp(**overrides) -> dict:
    base = {
        "id": "opp::C1::due", "customer_id": "C1", "customer_name": "Pietro Fontana",
        "trigger": "due", "why_now": "Last bought 37 days ago against a 26-day cycle.",
        "action": "Email about the Mini Crossbody.",
        "product": {"name": "Mini Crossbody", "brand": "Sessùn", "category": "Leather Goods",
                    "price": 1100.0, "stock": 4.0, "availability": "4 in stock",
                    "why": ["Leather Goods is 86% of their spend"], "caveats": []},
        "eligibility": {"channels": [{"key": "email", "label": "Email", "verb": "Email"}],
                        "preferred_channel": {"key": "email"}, "blocked": [], "status": "Actionable"},
        "influenced_value": 442.0,
    }
    return {**base, **overrides}


# ------------------------------------------------------- deterministic draft --

def test_a_draft_is_generated_without_an_ai_key():
    """The template is the product, not a degraded mode."""
    draft = outreach.build(_opp(), _profile_with(), "email")
    assert draft["engine"] == "template"
    assert draft["kind"] == "message"
    assert draft["body"]
    assert "Pietro" in draft["body"]
    assert "Mini Crossbody" in draft["body"]


def test_the_draft_invents_nothing():
    """No discount, no exclusivity, no event, no urgency the stock cannot carry."""
    draft = outreach.build(_opp(), _profile_with(), "whatsapp")
    lowered = draft["body"].lower()
    for invented in ("discount", "sale", "% off", "exclusive", "event", "private view",
                     "limited", "last chance", "hurry", "only for you"):
        assert invented not in lowered, invented
    # Nor the internal reasoning: the customer is not told they are "due".
    for internal in ("cycle", "overdue", "segment", "vip", "score"):
        assert internal not in lowered, internal


def test_stock_is_only_claimed_when_stock_exists():
    out_of_stock = _opp(product={**_opp()["product"], "stock": 0.0})
    assert "boutique" not in outreach.build(out_of_stock, _profile_with(), "whatsapp")["body"]

    last_one = _opp(product={**_opp()["product"], "stock": 1.0})
    assert "one left" in outreach.build(last_one, _profile_with(), "whatsapp")["body"]


def test_size_is_only_mentioned_when_it_is_unambiguous():
    """A guessed size in a boutique message is an error a client remembers."""
    rtw = _opp(product={**_opp()["product"], "category": "Ready-to-Wear"})
    assert "usual S" in outreach.build(rtw, _profile_with(), "whatsapp")["body"]
    # "One Size" says nothing about the customer, so it is not said.
    assert "your usual" not in outreach.build(_opp(), _profile_with(), "whatsapp")["body"]
    # Split evidence is not evidence.
    split = _profile_with(size_affinity_by_family={"Ready-to-Wear": {"S": 0.5, "M": 0.5}})
    assert "your usual" not in outreach.build(rtw, split, "whatsapp")["body"]


# ---------------------------------------------------------- per-channel shape --

def test_each_channel_produces_the_right_shape():
    email = outreach.build(_opp(), _profile_with(), "email")
    assert email["kind"] == "message" and email["subject"]
    assert email["deep_link"].startswith("mailto:")

    whatsapp = outreach.build(_opp(), _profile_with(), "whatsapp")
    assert whatsapp["kind"] == "message" and whatsapp["subject"] is None
    assert whatsapp["deep_link"].startswith("https://wa.me/393201112223?text=")

    # A call read from a script sounds exactly like a call read from a script.
    phone = outreach.build(_opp(), _profile_with(), "phone")
    assert phone["kind"] == "brief"
    assert phone["body"] is None
    assert 2 <= len(phone["talking_points"]) <= 5
    assert phone["deep_link"] == "tel:393201112223"

    in_store = outreach.build(_opp(), _profile_with(), "in_store")
    assert in_store["kind"] == "brief" and in_store["deep_link"] is None


def test_missing_contact_details_leave_nothing_to_open():
    """Never offer an action that cannot work."""
    no_email = outreach.build(_opp(), _profile_with(email=None), "email")
    assert no_email["contact_available"] is False
    assert no_email["deep_link"] is None
    # The draft still exists — the advisor may have the address elsewhere.
    assert no_email["body"]

    no_phone = outreach.build(_opp(), _profile_with(phone=None), "whatsapp")
    assert no_phone["contact_available"] is False and no_phone["deep_link"] is None


def test_a_channel_without_consent_is_marked_as_such():
    draft = outreach.build(_opp(), _profile_with(), "whatsapp")
    assert draft["channel_permitted"] is False
    assert outreach.build(_opp(), _profile_with(), "email")["channel_permitted"] is True


# -------------------------------------------------------------- the workflow --

def test_approve_persists_and_the_card_leaves_the_inbox(client):
    opp = _first(client)
    before = client.get("/api/opportunities").json()

    assert client.patch(f"/api/actions/{opp['id']}", json={"status": "Approved"}).status_code == 200

    after = client.get("/api/opportunities").json()
    assert after["shown"] == before["shown"] - 1
    assert opp["id"] not in {o["id"] for o in after["opportunities"]}
    # It left the queue, not the day.
    assert after["prioritized_today"] == before["prioritized_today"]
    assert after["decisions_made"] == before["decisions_made"] + 1


def test_an_approved_recommendation_is_ready_to_contact_in_action_center(client):
    opp = _first(client)
    client.patch(f"/api/actions/{opp['id']}", json={"status": "Approved"})

    centre = client.get("/api/actions").json()
    row = next(r for r in centre["rows"] if r["id"] == opp["id"])
    assert row["status"] == "Approved"
    assert centre["counts"]["Approved"] == 1
    assert row.get("contacted_at") is None


def test_the_endpoint_returns_a_usable_draft(client):
    opp = _first(client)
    draft = client.get(f"/api/outreach/{opp['id']}").json()
    assert draft["kind"] in {"message", "brief"}
    assert draft["engine"] == "template"  # no ANTHROPIC_API_KEY under test
    assert draft["channel"] in {c["key"] for c in draft["channels"]}
    assert draft["customer_name"] == opp["customer_name"]
    if draft["kind"] == "message":
        assert draft["body"]
    else:
        assert draft["talking_points"]


def test_asking_for_another_permitted_channel_switches_the_draft(client):
    opp = _first(client)
    first = client.get(f"/api/outreach/{opp['id']}").json()
    other = next((c["key"] for c in first["channels"] if c["key"] != first["channel"]), None)
    if other is None:
        pytest.skip("this customer consented to only one channel")
    switched = client.get(f"/api/outreach/{opp['id']}?channel={other}").json()
    assert switched["channel"] == other


def test_reading_a_draft_does_not_record_a_contact(client):
    """Copying text and opening WhatsApp both happen before the conversation."""
    opp = _first(client)
    client.patch(f"/api/actions/{opp['id']}", json={"status": "Approved"})
    client.get(f"/api/outreach/{opp['id']}")
    client.get(f"/api/outreach/{opp['id']}?channel=email")

    row = next(r for r in client.get("/api/actions").json()["rows"] if r["id"] == opp["id"])
    assert row["status"] == "Approved"
    assert client.get("/api/performance").json()["customers_contacted"] == 0


def test_marking_contacted_persists_channel_time_and_wording(client):
    opp = _first(client)
    client.patch(f"/api/actions/{opp['id']}", json={"status": "Approved"})

    saved = client.post(f"/api/outreach/{opp['id']}/contacted",
                        json={"channel": "email", "message": "Hi Pietro — edited by hand."})
    assert saved.status_code == 200
    body = saved.json()
    assert body["status"] == "Contacted"
    assert body["contact_channel"] == "email"
    assert body["contacted_at"]
    # The wording actually used, not the wording suggested.
    assert body["outreach_message"] == "Hi Pietro — edited by hand."

    audit = client.get("/api/audit").json()["entries"]
    assert any(e["action_id"] == opp["id"] and e["status"] == "Contacted" for e in audit)


def test_performance_counts_the_contact(client):
    opp = _first(client)
    client.patch(f"/api/actions/{opp['id']}", json={"status": "Approved"})
    assert client.get("/api/performance").json()["customers_contacted"] == 0

    client.post(f"/api/outreach/{opp['id']}/contacted", json={"channel": "email"})
    report = client.get("/api/performance").json()
    assert report["customers_contacted"] == 1
    assert report["awaiting_decision"] == report["prioritized_today"] - 1


def test_the_workflow_survives_a_refresh(client):
    opp = _first(client)
    client.patch(f"/api/actions/{opp['id']}", json={"status": "Approved"})
    client.post(f"/api/outreach/{opp['id']}/contacted",
                json={"channel": "email", "message": "Sent this."})

    # Re-reading is what a browser refresh does.
    assert opp["id"] not in {o["id"] for o in client.get("/api/opportunities").json()["opportunities"]}
    again = client.get(f"/api/outreach/{opp['id']}").json()
    assert again["status"] == "Contacted"
    assert again["contacted_at"]
    assert again["sent_message"] == "Sent this."


def test_a_failed_call_does_not_advance_the_workflow(client):
    """A 404 or a 409 must leave the pipeline exactly where it was."""
    assert client.post("/api/outreach/opp::nobody::due/contacted",
                       json={"channel": "email"}).status_code == 404
    assert client.get("/api/outreach/opp::nobody::due").status_code == 404

    opp = _first(client)
    client.patch(f"/api/actions/{opp['id']}", json={"status": "Ignored"})
    refused = client.post(f"/api/outreach/{opp['id']}/contacted", json={"channel": "email"})
    assert refused.status_code == 409

    row = next(r for r in client.get("/api/actions").json()["rows"] if r["id"] == opp["id"])
    assert row["status"] == "Ignored"
    assert row.get("contacted_at") is None
