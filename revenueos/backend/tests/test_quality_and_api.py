"""Data quality engine and the HTTP surface."""
from __future__ import annotations

import io
import pathlib
import threading
import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.data import validation
from app.main import app
from app.workspace import workspace

TODAY = date(2026, 8, 17)


@pytest.fixture(scope="module")
def client():
    workspace.load_demo()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def inbox():
    """A client with a freshly seeded, undecided queue.

    Function-scoped on purpose: the startup tests call workspace.reset(), and
    the decision tests below consume the queue, so anything sharing the
    module-scoped fixture would depend on the order tests happen to run in.
    """
    workspace.load_demo()
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ quality --

def test_missing_consent_is_flagged_as_critical():
    report = validation.analyse(
        [{"customer_id": "C1", "name": "A", "email": "a@example.com"}], [], [])
    titles = [f.title for f in report.findings]
    assert "No marketing consent column" in titles
    consent = next(c for c in report.capabilities if c.name == "Compliant outreach")
    assert consent.available is False
    assert consent.unlock


def test_invalid_emails_and_duplicates_are_counted():
    customers = [
        {"customer_id": "C1", "name": "A", "email": "not-an-email", "marketing_consent": True},
        {"customer_id": "C1", "name": "A dup", "email": "a@example.com", "marketing_consent": True},
    ]
    report = validation.analyse(customers, [], [])
    titles = [f.title for f in report.findings]
    assert "Duplicate customer records" in titles
    assert "Invalid email addresses" in titles


def test_health_score_reflects_completeness():
    rich_customers = [{"customer_id": f"C{i}", "name": f"N{i}", "marketing_consent": True,
                       "email": f"c{i}@example.com"} for i in range(10)]
    rich_tx = [{"customer_id": f"C{i}", "transaction_id": f"O{i}", "date": TODAY - timedelta(days=i),
                "line_total": 500.0, "category": "Shoes", "sku": "S1", "quantity": 1}
               for i in range(10)]
    rich_inv = [{"sku": "S1", "product_name": "Loafer", "category": "Shoes", "price": 500.0,
                 "stock": 3, "arrival_date": TODAY - timedelta(days=60)}]

    rich = validation.analyse(rich_customers, rich_tx, rich_inv)
    poor = validation.analyse([{"customer_id": "C1", "name": "A"}], [], [])
    assert rich.score > poor.score
    assert rich.summary and poor.summary


def test_capabilities_explain_what_is_unlocked():
    report = validation.analyse([{"customer_id": "C1", "name": "A"}], [], [])
    blocked = [c for c in report.capabilities if not c.available]
    assert blocked
    assert all(c.reason for c in blocked)


# ---------------------------------------------------------------------- API --

def test_health_endpoint(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["loaded"] is True
    assert "ai" in body


def test_summary_has_computed_headline(client):
    body = client.get("/api/summary").json()
    assert body["loaded"] is True
    assert body["counts"]["customers"] > 0
    assert body["revenue_opportunity"] >= 0
    assert 0 <= body["data_health"] <= 100


def test_customer_list_and_detail(client):
    listing = client.get("/api/customers?limit=5").json()
    assert listing["total"] > 0
    assert len(listing["customers"]) == 5
    assert listing["facets"]["value_tiers"]
    assert listing["facets"]["lifecycles"]

    cid = listing["customers"][0]["customer_id"]
    detail = client.get(f"/api/customers/{cid}").json()
    assert detail["profile"]["customer_id"] == cid
    assert isinstance(detail["recommendations"], list)
    assert isinstance(detail["timeline"], list)
    # Customer Detail must answer "why am I being told to contact them?" outright.
    assert detail["why_contact"]["headline"]
    assert detail["value"]["basis"], "the value tier must state its evidence"
    assert detail["lifecycle"]["basis"], "the lifecycle stage must state its evidence"


def test_recommendations_are_explained(client):
    listing = client.get("/api/customers?limit=3&sort=total_spend").json()
    cid = listing["customers"][0]["customer_id"]
    detail = client.get(f"/api/customers/{cid}").json()
    recs = detail["recommendations"]
    assert recs, "a high-value customer should attract at least one recommendation"
    top = recs[0]
    assert top["match_pct"] > 0
    assert top["why"], "every match must carry its reasons"
    assert any(s["applicable"] for s in top["signals"])


def test_customer_404(client):
    assert client.get("/api/customers/NOPE-123").status_code == 404


def test_product_endpoints(client):
    listing = client.get("/api/products?limit=5").json()
    assert listing["total"] > 0
    sku = listing["products"][0]["sku"]

    detail = client.get(f"/api/products/{sku}").json()
    assert detail["product"]["sku"] == sku
    assert "best_customers" in detail

    overview = client.get("/api/inventory/overview").json()
    assert overview["summary"]["skus"] > 0
    assert overview["ageing"]


def test_todays_opportunities_answer_the_five_questions(client):
    body = client.get("/api/opportunities").json()
    assert body["shown"] > 0
    assert body["shown"] <= 20, "the daily list has a ceiling an advisor can work through"
    for o in body["opportunities"]:
        assert o["customer_name"]                      # who
        assert o["why_now"]                            # why now
        assert o["action"]                             # how to act
        assert o["contactable"] is True, "the daily list only contains reachable customers"
        if o["product"]:
            assert o["product"]["why"], "why this product must be explained"


def test_action_center_records_every_decision(client):
    actions = client.get("/api/actions").json()
    assert actions["statuses"] == ["New", "Approved", "Scheduled", "Contacted",
                                   "Converted", "Ignored"]
    row_id = actions["rows"][0]["id"]
    updated = client.patch(f"/api/actions/{row_id}",
                           json={"status": "Contacted", "note": "Called"}).json()
    assert updated["status"] == "Contacted"
    assert updated["note"] == "Called"

    audit = client.get("/api/audit").json()
    assert any(e["action_id"] == row_id and e["status"] == "Contacted"
               for e in audit["entries"]), "every decision must reach the audit log"

    bad = client.patch(f"/api/actions/{row_id}", json={"status": "Nonsense"})
    assert bad.status_code == 400


def test_overview_points_at_todays_work(client):
    body = client.get("/api/overview").json()
    assert body["loaded"] is True
    assert body["today"]["note"], "the day must be described in words, not just a count"
    assert body["today"]["opportunities"] == len(body["today"]["top"]) or body["today"]["top"]
    for row in body["today"]["top"]:
        assert row["why_now"], "every suggested contact must carry a reason"


def test_performance_separates_observed_from_estimated(client):
    body = client.get("/api/performance").json()
    assert body["contacted_revenue"] >= body["influenced_revenue"]
    assert "modelled, not measured" in body["incremental_revenue_basis"].lower()
    assert body["attribution_note"]


def test_a_recorded_sale_is_never_presented_as_incremental(client):
    """We may claim only part of a sale as caused by RevenueOS, never all of it."""
    actions = client.get("/api/actions").json()
    row = actions["rows"][0]
    client.patch(f"/api/actions/{row['id']}",
                 json={"status": "Converted", "realised_value": 1000})

    body = client.get("/api/performance").json()
    assert body["recorded_sales"] >= 1000
    assert body["recorded_sales_count"] >= 1
    assert body["estimated_incremental_revenue"] < body["recorded_sales"], \
        "incremental revenue must be a discounted share of what was actually sold"
    # The advisor-entered figure is observed, and says why it can outrun the till.
    assert "observed" in body["recorded_sales_basis"].lower()


def test_upload_maps_and_imports_a_real_csv(client):
    csv = (
        "Codice Cliente;Nome Cliente;Ultimo Acquisto;Spesa Totale;N Ordini;Consenso Marketing\n"
        "K1;Giulia Rossi;12/05/2026;1.234,56;7;Si\n"
        "K2;Marco Bianchi;03/01/2026;980,00;3;No\n"
    )
    upload = client.post(
        "/api/data/upload",
        data={"kind": "customers"},
        files={"file": ("clienti.csv", io.BytesIO(csv.encode()), "text/csv")},
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["parse"]["delimiter"] == ";"
    mapped = {m["field"] for m in body["mappings"] if m["field"]}
    assert "customer_id" in mapped and "total_spend" in mapped
    assert body["ready"] is True

    confirmed = client.post("/api/data/confirm").json()
    assert confirmed["ok"] is True
    assert confirmed["rows"] == 2

    # Restore the demo dataset for any later test in this module.
    client.post("/api/data/demo", json={"seed": 7})


def test_upload_rejects_empty_file(client):
    resp = client.post(
        "/api/data/upload",
        data={"kind": "customers"},
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert resp.status_code == 400


def test_scenarios_are_labelled_estimates(client):
    options = client.get("/api/scenarios/options").json()
    if options["risk_classes"]:
        result = client.post("/api/scenarios/discount",
                             json={"risk_class": options["risk_classes"][0],
                                   "discount_pct": 15}).json()
        assert result["estimate"] is True
        assert result["assumptions"]

    if options["segments"]:
        result = client.post("/api/scenarios/outreach",
                             json={"segment": options["segments"][0]}).json()
        assert result["estimate"] is True
        assert "blocked_by_consent" in result


def test_campaign_builder_returns_an_audience(client):
    templates = client.get("/api/campaigns/templates").json()["templates"]
    assert templates
    built = client.post("/api/campaigns/build",
                        json={"template": "vip_private_sale", "limit": 10}).json()
    assert built["id"] == "vip_private_sale"
    assert "audience" in built


def test_ai_endpoint_degrades_without_a_key(client):
    body = client.post("/api/ai/ask", json={"question": "Who should I contact today?"}).json()
    assert body["answer"] or body.get("rows") is not None
    assert body["engine"] in {"claude", "computed"}


def test_all_four_screens_report_the_same_two_numbers(client):
    """Overview, Opportunities, Action Center and Performance must reconcile.

    The ambiguity this guards against is a real one the product shipped with:
    two screens quoting a large number and two quoting a small one, with nothing
    explaining the relationship. They now read one stamp decided in the pipeline.
    """
    overview = client.get("/api/overview").json()["today"]
    feed = client.get("/api/opportunities").json()
    actions = client.get("/api/actions").json()
    perf = client.get("/api/performance").json()

    detected = {overview["detected"], feed["detected"], actions["detected"],
                perf["opportunities_detected"]}
    assert len(detected) == 1, f"detected disagrees across screens: {detected}"

    prioritized = {overview["prioritized_today"], feed["prioritized_today"],
                   actions["todays_list"], perf["prioritized_today"]}
    assert len(prioritized) == 1, f"today disagrees across screens: {prioritized}"

    assert prioritized.pop() <= detected.pop(), "today is drawn from what was detected"


def test_the_opportunities_feed_cannot_be_asked_for_a_different_today(client):
    """A per-request limit once let a client redefine 'today' for one screen."""
    a = client.get("/api/opportunities").json()
    b = client.get("/api/opportunities?limit=3").json()
    assert a["shown"] == b["shown"], "an unknown parameter must not resize today's list"

    every = client.get("/api/opportunities?scope=detected").json()
    assert every["shown"] == every["detected"]
    assert every["prioritized_today"] == a["prioritized_today"]


def test_deciding_on_an_action_does_not_change_the_detected_count(client):
    """Workflow state and detection are different axes; moving one must not move the other."""
    before = client.get("/api/actions").json()
    row = next(r for r in before["rows"] if r["status"] == "New")

    client.patch(f"/api/actions/{row['id']}", json={"status": "Approved"})
    after = client.get("/api/actions").json()

    assert after["detected"] == before["detected"]
    assert after["counts"]["Approved"] == before["counts"]["Approved"] + 1
    # Today's list is what RevenueOS prioritised, not what is left to do. If it
    # shrank on every approval this screen would drift away from the Overview
    # over the course of a morning; progress belongs in the status tiles.
    assert after["todays_list"] == before["todays_list"]
    assert after["awaiting_decision"] == before["awaiting_decision"] - 1


def test_health_answers_before_the_data_is_ready(monkeypatch):
    """The server must listen immediately, whatever the data load is doing.

    Uvicorn serves nothing — not even this endpoint — until the startup event
    returns, so loading data inline lets a slow instance fail its platform
    health check and be marked a failed deploy.
    """
    from fastapi.testclient import TestClient
    from app import main
    from app.workspace import workspace

    started = threading.Event()
    release = threading.Event()

    def slow_seed(*_a, **_k):
        started.set()
        release.wait(timeout=5)

    monkeypatch.setattr(workspace, "load", lambda: False)
    monkeypatch.setattr(workspace, "load_demo", slow_seed)
    monkeypatch.setenv("SEED_DEMO_ON_EMPTY", "true")
    monkeypatch.setattr(main, "STARTUP_ERROR", None)
    workspace.reset()

    with TestClient(main.app) as client:
        assert started.wait(timeout=5), "the load should begin off the startup path"
        body = client.get("/api/health").json()   # answers while the load runs
        assert body["loading"] is True
        assert body["status"] == "loading"
        release.set()


def test_health_never_fails_even_if_a_subsystem_does(monkeypatch):
    """A platform decides deploy success from this endpoint, so it cannot raise."""
    from fastapi.testclient import TestClient
    from app import main
    import app.ai.client as ai_client

    monkeypatch.setattr(ai_client, "is_available",
                        lambda: (_ for _ in ()).throw(RuntimeError("sdk broken")))
    with TestClient(main.app) as client:
        res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["ai"]["available"] is False


def test_a_failed_data_load_leaves_the_api_running(monkeypatch):
    """Startup work must never be able to take the service down.

    An exception in the startup event aborts uvicorn entirely: no routes, no
    health check, and the platform answers every request with a bare 502 that
    says nothing. Verified by simulating a failing seed and checking the API
    still serves and names the cause.
    """
    from fastapi.testclient import TestClient
    from app import main
    from app.workspace import workspace

    monkeypatch.setattr(workspace, "load", lambda: False)
    monkeypatch.setattr(workspace, "load_demo", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("seed exploded")))
    monkeypatch.setenv("SEED_DEMO_ON_EMPTY", "true")
    monkeypatch.setattr(main, "STARTUP_ERROR", None)
    workspace.reset()

    with TestClient(main.app) as client:
        body = client.get("/api/health").json()

    assert body["status"] == "degraded", "a broken load must be visible, not fatal"
    assert "seed exploded" in body["startup_error"]
    assert body["loaded"] is False


def test_importing_the_app_does_not_load_the_anthropic_sdk():
    """Boot cost decides whether a deploy survives its platform's port scan.

    The SDK was the single largest import in the tree, pulled in eagerly by
    three routers for a feature that is optional and not in the navigation. A
    platform waits a fixed window for the port to open; spending it importing a
    client nobody has asked for is how a working service is marked failed.
    """
    import subprocess
    import sys

    probe = subprocess.run(
        [sys.executable, "-c",
         "import sys, app.main; sys.exit(1 if 'anthropic' in sys.modules else 0)"],
        cwd=str(pathlib.Path(__file__).resolve().parent.parent),
        capture_output=True,
    )
    assert probe.returncode == 0, (
        "anthropic is imported at boot again — check for a module-level "
        "`from ..ai import analyst` in a router"
    )


def test_startup_returns_immediately_however_slow_the_data_is(monkeypatch):
    """The startup event must not hold the port closed.

    Uvicorn binds only after this event returns, and a platform that scans for
    an open port gives up long before a throttled instance finishes rebuilding
    the analytics pipeline. Loading belongs behind the running server.
    """
    from fastapi.testclient import TestClient
    from app import main
    from app.workspace import workspace

    release = threading.Event()
    monkeypatch.setattr(workspace, "load", lambda: False)
    monkeypatch.setattr(workspace, "load_demo",
                        lambda *a, **k: release.wait(timeout=10))
    monkeypatch.setenv("SEED_DEMO_ON_EMPTY", "true")
    monkeypatch.setattr(main, "STARTUP_ERROR", None)
    workspace.reset()

    began = time.monotonic()
    with TestClient(main.app) as client:          # __enter__ runs the startup event
        elapsed = time.monotonic() - began
        assert elapsed < 1.0, f"startup blocked for {elapsed:.1f}s with a slow load"
        assert client.get("/api/health").json()["status"] == "loading"
        release.set()


def test_a_decision_removes_the_recommendation_from_the_inbox(inbox):
    """Today's Opportunities is a queue of undecided work, not an archive."""
    before = inbox.get("/api/opportunities").json()
    assert before["awaiting_decision"] == before["shown"]
    target = before["opportunities"][0]["id"]

    inbox.patch(f"/api/actions/{target}", json={"status": "Approved"})
    after = inbox.get("/api/opportunities").json()

    assert target not in [o["id"] for o in after["opportunities"]]
    assert after["shown"] == before["shown"] - 1
    assert after["awaiting_decision"] == before["awaiting_decision"] - 1
    assert after["decisions_made"] == before["decisions_made"] + 1


def test_deciding_never_shrinks_what_was_recommended_today(inbox):
    """The queue empties; the day does not. Performance still counts all of it."""
    before = inbox.get("/api/opportunities").json()
    recommended = before["prioritized_today"]

    for row in before["opportunities"][:2]:
        inbox.patch(f"/api/actions/{row['id']}", json={"status": "Scheduled"})

    after = inbox.get("/api/opportunities").json()
    assert after["prioritized_today"] == recommended
    assert inbox.get("/api/performance").json()["prioritized_today"] == recommended
    assert inbox.get("/api/actions").json()["todays_list"] == recommended
    # The three always reconcile: decided + waiting == recommended.
    assert after["awaiting_decision"] + after["decisions_made"] == recommended


def test_every_decision_type_clears_the_card(inbox):
    """Approve, Schedule and Not now all take a recommendation out of the queue."""
    for status in ("Approved", "Scheduled", "Ignored"):
        feed = inbox.get("/api/opportunities").json()
        target = feed["opportunities"][0]["id"]
        # Setting aside additionally requires a reason; see test_decline_reasons.
        payload = {"status": status}
        if status == "Ignored":
            payload["reason"] = "low_relevance"
        inbox.patch(f"/api/actions/{target}", json=payload)
        after = inbox.get("/api/opportunities").json()
        assert target not in [o["id"] for o in after["opportunities"]], status
        assert any(r["id"] == target and r["status"] == status
                   for r in inbox.get("/api/actions").json()["rows"]), status


def test_a_decided_recommendation_does_not_come_back_on_refresh(inbox):
    """The decision lives in the pipeline, not in the browser."""
    target = inbox.get("/api/opportunities").json()["opportunities"][0]["id"]
    inbox.patch(f"/api/actions/{target}",
                json={"status": "Ignored", "reason": "contacted_recently"})

    for _ in range(3):   # a refresh is just another GET
        feed = inbox.get("/api/opportunities").json()
        assert target not in [o["id"] for o in feed["opportunities"]]

    # Still reachable where the audit lives, and in the full detected scope.
    assert target in [o["id"] for o in
                      inbox.get("/api/opportunities?scope=detected").json()["opportunities"]]


def test_a_rejected_decision_leaves_the_queue_untouched(inbox):
    """A failed write must not remove anything — the UI mirrors this."""
    before = inbox.get("/api/opportunities").json()
    target = before["opportunities"][0]["id"]

    bad = inbox.patch(f"/api/actions/{target}", json={"status": "Nonsense"})
    assert bad.status_code == 400

    after = inbox.get("/api/opportunities").json()
    assert target in [o["id"] for o in after["opportunities"]]
    assert after["awaiting_decision"] == before["awaiting_decision"]
