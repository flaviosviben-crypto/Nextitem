"""Data quality engine and the HTTP surface."""
from __future__ import annotations

import io
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
    assert listing["facets"]["segments"]

    cid = listing["customers"][0]["customer_id"]
    detail = client.get(f"/api/customers/{cid}").json()
    assert detail["profile"]["customer_id"] == cid
    assert isinstance(detail["recommendations"], list)
    assert isinstance(detail["timeline"], list)


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


def test_opportunities_and_pipeline(client):
    opps = client.get("/api/opportunities").json()
    assert opps["total"] > 0

    pipeline = client.get("/api/pipeline").json()
    assert pipeline["statuses"][0] == "New"
    if pipeline["rows"]:
        row_id = pipeline["rows"][0]["id"]
        updated = client.patch(f"/api/pipeline/{row_id}",
                               json={"status": "Contacted", "note": "Called"}).json()
        assert updated["status"] == "Contacted"
        assert updated["note"] == "Called"

        bad = client.patch(f"/api/pipeline/{row_id}", json={"status": "Nonsense"})
        assert bad.status_code == 400


def test_briefing_is_actionable(client):
    body = client.get("/api/briefing").json()
    assert body["loaded"] is True
    assert "headline" in body
    assert isinstance(body["priorities"], list)
    for row in body["contact_today"]:
        assert row["reason"], "every suggested contact must carry a reason"


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
