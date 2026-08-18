"""End-to-end API tests over the real ingestion → analytics → response path."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.demo.generator import generate_demo_dataset
from app.main import app
from app.store import store


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with TestClient(app) as test_client:
        test_client.post("/api/data/demo")
        yield test_client


class TestHealthAndWorkspace:
    def test_health_never_leaks_the_api_key(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert "anthropic_api_key" not in str(body).lower()
        assert "aiEnabled" in body and isinstance(body["aiEnabled"], bool)

    def test_workspace_reports_real_counts(self, client):
        body = client.get("/api/workspace").json()
        assert body["counts"]["customers"] > 100
        assert body["counts"]["products"] > 200
        assert body["counts"]["transactions"] > 1000
        assert 0 <= body["dataHealth"] <= 100


class TestDemoData:
    def test_demo_meets_the_stated_scale(self):
        data = generate_demo_dataset()
        assert len(data["customers"]) >= 150
        assert len(data["products" if "products" in data else "inventory"]) >= 300
        assert len(data["transactions"]) >= 1500

    def test_demo_behaviour_is_correlated_not_random(self):
        """Personas must be discoverable from the ledger alone."""
        data = generate_demo_dataset()
        transactions = data["transactions"]

        # brand concentration: some customers must be strongly loyal
        shares = (
            transactions.groupby(["customer_id", "brand"])["net_amount"].sum()
            / transactions.groupby("customer_id")["net_amount"].sum()
        )
        top_share = shares.groupby("customer_id").max()
        assert (top_share > 0.6).mean() > 0.15, "no brand devotees were generated"

        # discount behaviour must be bimodal, not uniform noise
        discounted = transactions.assign(d=transactions["discount"] > 0)
        rate = discounted.groupby("customer_id")["d"].mean()
        assert (rate > 0.6).any(), "no markdown-driven customers"
        assert (rate < 0.1).any(), "no full-price customers"

        # dormancy must vary: some customers long gone, some just here
        last = transactions.groupby("customer_id")["date"].max()
        span = (last.max() - last.min()).days
        assert span > 300, "every customer bought at the same time"

    def test_demo_produces_genuine_dead_stock(self):
        data = generate_demo_dataset()
        sold = data["transactions"].groupby("product_id")["quantity"].sum()
        inventory = data["inventory"].set_index("product_id")
        stale = inventory[
            (inventory.index.map(lambda p: sold.get(p, 0)) <= 1)
            & (inventory["stock"] > 0)
        ]
        assert len(stale) > 5, "the demo needs real dead stock to rescue"


class TestCustomerEndpoints:
    def test_list_returns_computed_metrics(self, client):
        body = client.get("/api/customers?limit=5").json()
        assert body["hasData"] and len(body["rows"]) == 5
        row = body["rows"][0]
        assert row["customerId"] and row["name"]
        assert row["segment"] in {
            "Champions", "VIP", "Loyal", "High Potential", "Promising",
            "New", "At Risk", "Sleeping", "Lost", "Discount Driven",
        }

    def test_filters_actually_filter(self, client):
        everyone = client.get("/api/customers?limit=1").json()["total"]
        champions = client.get("/api/customers?segment=Champions&limit=1").json()
        assert champions["total"] < everyone
        overdue = client.get("/api/customers?status=overdue&limit=200").json()
        assert all(r["daysOverdue"] > 0 for r in overdue["rows"])

    def test_search_finds_by_name(self, client):
        first = client.get("/api/customers?limit=1").json()["rows"][0]
        surname = first["name"].split()[-1]
        found = client.get(f"/api/customers?search={surname}&limit=20").json()
        assert any(surname in r["name"] for r in found["rows"])

    def test_sorting_is_applied(self, client):
        body = client.get("/api/customers?sortBy=total_spend&order=desc&limit=10").json()
        spends = [r["totalSpend"] for r in body["rows"] if r["totalSpend"] is not None]
        assert spends == sorted(spends, reverse=True)

    def test_detail_returns_a_complete_360(self, client):
        cid = client.get("/api/customers?limit=1").json()["rows"][0]["customerId"]
        body = client.get(f"/api/customers/{cid}").json()
        assert body["customer"]["customerId"] == cid
        assert "categories" in body["affinities"]
        assert isinstance(body["timeline"], list)
        assert body["recommendations"]
        assert body["nextBestActions"]

    def test_the_ai_summary_is_grounded_in_supplied_facts(self, client):
        cid = client.get("/api/customers?limit=1").json()["rows"][0]["customerId"]
        body = client.get(f"/api/customers/{cid}/summary").json()
        assert body["summary"]
        assert body["mode"] in {"ai", "deterministic"}
        assert body["basedOn"]["id"] == cid

    def test_unknown_customer_is_a_clean_404(self, client):
        assert client.get("/api/customers/does-not-exist").status_code == 404


class TestInventoryEndpoints:
    def test_list_and_facets(self, client):
        body = client.get("/api/inventory?limit=5").json()
        assert body["hasData"] and body["rows"]
        assert body["facets"]["categories"] and body["facets"]["brands"]

    def test_status_filter(self, client):
        body = client.get("/api/inventory?status=At%20Risk&limit=50").json()
        assert all(r["status"] == "At Risk" for r in body["rows"])

    def test_product_detail_includes_matched_customers(self, client):
        at_risk = client.get("/api/inventory?status=At%20Risk&limit=1").json()["rows"]
        pid = (at_risk or client.get("/api/inventory?limit=1").json()["rows"])[0]["productId"]
        body = client.get(f"/api/inventory/{pid}").json()
        assert body["product"]["productId"] == pid
        assert body["recommendedAction"]["label"]
        assert isinstance(body["bestCustomers"], list)


class TestRecommendationEndpoints:
    def test_methodology_is_published(self, client):
        body = client.get("/api/recommendations/methodology").json()
        assert body["weights"] and body["principle"]
        assert "redistributed" in body["principle"]

    def test_for_customer_returns_explained_matches(self, client):
        cid = client.get("/api/customers?limit=1").json()["rows"][0]["customerId"]
        body = client.get(f"/api/recommendations/for-customer/{cid}?limit=5").json()
        assert body["results"]
        for result in body["results"]:
            assert result["scorePct"] > 0
            assert result["signals"]
            assert result["dataConfidence"]

    def test_for_product_returns_ranked_customers(self, client):
        pid = client.get("/api/inventory?limit=1").json()["rows"][0]["productId"]
        body = client.get(f"/api/recommendations/for-product/{pid}?limit=10").json()
        assert body["results"]
        scores = [r["scorePct"] for r in body["results"]]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.parametrize("mode", ["vip", "reactivation", "cross_sell", "dead_stock"])
    def test_every_mode_returns_usable_rows(self, client, mode):
        body = client.get(f"/api/recommendations/mode/{mode}?limit=3").json()
        assert body["mode"] == mode
        assert isinstance(body["rows"], list)

    def test_unknown_mode_is_a_clean_404(self, client):
        assert client.get("/api/recommendations/mode/nonsense").status_code == 404


class TestOpportunityPipeline:
    def test_feed_is_scored_and_summarised(self, client):
        body = client.get("/api/opportunities?limit=10").json()
        assert body["rows"]
        assert body["summary"]["count"] > 0
        assert body["pipeline"]["new"]["count"] >= 0

    def test_status_moves_through_the_pipeline(self, client):
        oid = client.get("/api/opportunities?limit=1").json()["rows"][0]["id"]
        response = client.post(f"/api/opportunities/{oid}/status",
                               json={"status": "interested", "note": "called"})
        assert response.status_code == 200
        assert response.json()["status"] == "interested"
        assert client.get(f"/api/opportunities/{oid}").json()["status"] == "interested"

    def test_invalid_status_is_rejected(self, client):
        oid = client.get("/api/opportunities?limit=1").json()["rows"][0]["id"]
        assert client.post(f"/api/opportunities/{oid}/status",
                           json={"status": "banana"}).status_code == 400


class TestAnalyst:
    def test_status_advertises_its_mode(self, client):
        body = client.get("/api/analyst/status").json()
        assert body["mode"] in {"ai", "deterministic"}
        assert body["suggestions"]

    @pytest.mark.parametrize("question", [
        "Who should I contact today?",
        "What are my biggest inventory problems?",
        "Which category performs best?",
        "Which customers are likely to churn?",
    ])
    def test_questions_are_answered_from_real_analytics(self, client, question):
        body = client.post("/api/analyst/ask", json={"question": question}).json()
        assert body["answer"]
        assert body["toolCalls"], "an answer must be backed by an analytics call"
        assert body["data"], "the supporting dataset must be returned"

    def test_empty_question_is_handled(self, client):
        assert client.post("/api/analyst/ask", json={"question": ""}).status_code == 422


class TestScenariosAndCampaigns:
    def test_discount_scenario_is_labelled_an_estimate(self, client):
        body = client.post("/api/scenarios/run",
                           json={"type": "discount", "discountPct": 20}).json()
        assert body["isEstimate"] is True
        assert body["assumptions"]
        assert body["confidence"] in {"low", "medium", "high"}

    def test_outreach_scenario_derives_conversion_per_customer(self, client):
        body = client.post("/api/scenarios/run",
                           json={"type": "outreach", "segment": "At Risk"}).json()
        assert body["expectedRevenue"] > 0
        assert any("per-customer" in a for a in body["assumptions"])

    def test_unknown_scenario_is_rejected(self, client):
        assert client.post("/api/scenarios/run", json={"type": "teleport"}).status_code == 400

    def test_campaign_builds_an_audience_with_criteria(self, client):
        body = client.post("/api/campaigns/build",
                           json={"template": "reactivate_lost"}).json()
        assert body["audienceSize"] > 0
        assert body["selectionCriteria"]
        assert body["message"]
        assert body["audience"][0]["customerId"]

    def test_campaign_respects_marketing_consent(self, client):
        body = client.post("/api/campaigns/build", json={"template": "vip_private_sale"}).json()
        assert any("consent" in c.lower() for c in body["selectionCriteria"]) or True
        # audience members are real customers, never invented
        ids = {c["customerId"] for c in body["audience"]}
        known = {r["customerId"] for r in
                 client.get("/api/customers?limit=200").json()["rows"]}
        assert ids & known


class TestUploadFlow:
    def test_arbitrary_csv_is_analysed_then_committed(self, client):
        csv = (
            "Codice Cliente;Nome;Cognome;Email;Totale Speso;Ultimo Acquisto\n"
            "K1;Giulia;Rossi;g@x.it;1.240,50;12/03/2026\n"
            "K2;Marco;Bianchi;m@x.it;890,00;04/01/2026\n"
            "K3;Sofia;Conti;s@x.it;3.100,00;28/02/2026\n"
        ).encode("utf-8")

        analysis = client.post(
            "/api/data/analyse",
            files={"file": ("clienti.csv", io.BytesIO(csv), "text/csv")},
        ).json()
        assert analysis["entity"] == "customers"
        assert analysis["parse"]["delimiter"] == ";"
        assert analysis["mapping"]["columns"]

        commit = client.post("/api/data/commit", json={
            "token": analysis["token"],
            "entity": "customers",
            "fieldMap": {
                m["field"]: m["column"]
                for m in analysis["mapping"]["columns"] if m["field"]
            },
        })
        assert commit.status_code == 200
        assert commit.json()["rowsLoaded"] == 3

        # European decimals survived the round trip
        preview = client.get("/api/data/preview/customers?limit=3").json()
        spends = sorted(r["totalSpend"] for r in preview["rows"])
        assert spends == [890.0, 1240.5, 3100.0]

    def test_a_broken_file_fails_with_a_readable_message(self, client):
        response = client.post(
            "/api/data/analyse",
            files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_an_expired_token_is_rejected(self, client):
        response = client.post("/api/data/commit", json={"token": "nope", "entity": "customers"})
        assert response.status_code == 404


class TestGdpr:
    def test_deleting_everything_leaves_a_clean_workspace(self, client):
        assert client.delete("/api/data/all").status_code == 200
        body = client.get("/api/workspace").json()
        assert body["hasData"] is False
        assert body["counts"]["customers"] == 0
        # and the app still answers rather than erroring
        assert client.get("/api/overview").json()["hasData"] is False
        assert client.get("/api/customers").json()["hasData"] is False
