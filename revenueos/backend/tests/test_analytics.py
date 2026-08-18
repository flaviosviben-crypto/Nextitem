"""Customer metrics, RFM segmentation, inventory ageing and opportunity scoring."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analytics.customer_scoring import build_customer_metrics
from app.analytics.inventory import build_inventory_metrics, inventory_overview
from app.analytics.matching import build_context
from app.analytics.opportunities import generate_opportunities, opportunity_totals
from app.analytics.rfm import SEGMENTS, compute_rfm, segment_summary


def make_transactions(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"customer_id": cid, "date": pd.Timestamp(date), "net_amount": amount,
             "quantity": 1.0, "product_id": f"P{i}", "category": "Coats",
             "brand": "Max Mara", "color": "Black", "size": "M",
             "transaction_id": f"T{i}"}
            for i, (cid, date, amount) in enumerate(rows)
        ]
    )


class TestCustomerMetrics:
    def test_metrics_are_derived_from_the_transaction_ledger(self):
        customers = pd.DataFrame({"customer_id": ["C1"], "display_name": ["Rossi"]})
        transactions = make_transactions([
            ("C1", "2026-01-10", 500.0),
            ("C1", "2026-03-10", 700.0),
            ("C1", "2026-05-10", 300.0),
        ])
        metrics = build_customer_metrics(customers, transactions,
                                         as_of=pd.Timestamp("2026-06-10"))
        row = metrics.iloc[0]
        assert row["total_spend"] == pytest.approx(1500.0)
        assert row["order_count"] == 3
        assert row["avg_order_value"] == pytest.approx(500.0)
        assert row["recency_days"] == 31
        assert row["median_gap_days"] == pytest.approx(59.5, abs=1.5)

    def test_transaction_history_overrides_stale_crm_totals(self):
        customers = pd.DataFrame({
            "customer_id": ["C1"], "display_name": ["Rossi"],
            "total_spend": [99.0], "order_count": [1.0],
        })
        transactions = make_transactions([("C1", "2026-01-10", 500.0),
                                          ("C1", "2026-03-10", 700.0)])
        metrics = build_customer_metrics(customers, transactions)
        assert metrics.iloc[0]["total_spend"] == pytest.approx(1200.0)

    def test_crm_values_are_used_when_there_is_no_ledger(self):
        customers = pd.DataFrame({
            "customer_id": ["C1"], "display_name": ["Rossi"],
            "total_spend": [2400.0], "order_count": [4.0],
            "last_purchase_date": [pd.Timestamp("2026-04-01")],
        })
        metrics = build_customer_metrics(customers, None, as_of=pd.Timestamp("2026-06-01"))
        row = metrics.iloc[0]
        assert row["total_spend"] == 2400.0
        assert row["avg_order_value"] == pytest.approx(600.0)
        assert row["recency_days"] == 61

    def test_uncomputable_metrics_stay_null_rather_than_zero(self):
        customers = pd.DataFrame({"customer_id": ["C1"], "display_name": ["Rossi"]})
        metrics = build_customer_metrics(customers, None)
        row = metrics.iloc[0]
        for column in ("total_spend", "avg_order_value", "recency_days",
                       "churn_risk", "predicted_12m_value"):
            assert pd.isna(row[column]), f"{column} was faked as {row[column]}"

    def test_affinities_reflect_actual_spend_shares(self):
        customers = pd.DataFrame({"customer_id": ["C1"], "display_name": ["Rossi"]})
        transactions = make_transactions([("C1", "2026-01-10", 800.0),
                                          ("C1", "2026-02-10", 200.0)])
        transactions.loc[1, "category"] = "Bags"
        metrics = build_customer_metrics(customers, transactions)
        affinity = {a["value"]: a["share"] for a in metrics.iloc[0]["category_affinity"]}
        assert affinity["Coats"] == pytest.approx(0.8)
        assert affinity["Bags"] == pytest.approx(0.2)

    def test_customers_present_only_in_transactions_still_get_a_profile(self):
        customers = pd.DataFrame({"customer_id": ["C1"], "display_name": ["Rossi"]})
        transactions = make_transactions([("C1", "2026-01-10", 100.0),
                                          ("C9", "2026-02-10", 900.0)])
        metrics = build_customer_metrics(customers, transactions)
        assert set(metrics["customer_id"]) == {"C1", "C9"}

    def test_overdue_is_measured_against_the_customers_own_rhythm(self):
        customers = pd.DataFrame({"customer_id": ["C1"], "display_name": ["Rossi"]})
        # buys every ~30 days, last purchase 90 days ago
        transactions = make_transactions([
            ("C1", "2026-01-01", 100.0), ("C1", "2026-01-31", 100.0),
            ("C1", "2026-03-02", 100.0),
        ])
        metrics = build_customer_metrics(customers, transactions,
                                         as_of=pd.Timestamp("2026-05-31"))
        row = metrics.iloc[0]
        assert row["expected_cycle_days"] < 45
        assert row["days_overdue"] > 40
        assert row["churn_risk"] > 0.5


class TestRFM:
    def test_segments_come_from_the_defined_vocabulary(self, metrics):
        assert set(metrics["segment"].dropna()) <= set(SEGMENTS)

    def test_segmentation_adapts_to_the_datasets_own_distribution(self):
        """The same relative behaviour must segment the same way at any price level."""
        def build(scale: float) -> pd.DataFrame:
            rows = []
            for i in range(40):
                rows.append({
                    "customer_id": f"C{i}",
                    "display_name": f"P{i}",
                    "total_spend": (i + 1) * 100 * scale,
                    "order_count": float(1 + i // 4),
                    "recency_days": float(400 - i * 9),
                    "tenure_days": 700.0,
                    "median_gap_days": 60.0,
                    "cycles_overdue": (400 - i * 9) / 60 - 1,
                })
            return compute_rfm(pd.DataFrame(rows))

        cheap = build(1.0)["segment"].tolist()
        expensive = build(50.0)["segment"].tolist()
        assert cheap == expensive, "segments must be relative, not absolute thresholds"

    def test_a_high_value_recent_frequent_buyer_is_a_champion(self, metrics):
        best = metrics.sort_values("customer_score", ascending=False).iloc[0]
        assert best["segment"] in {"Champions", "VIP"}

    def test_markdown_buyers_are_identified_behaviourally(self, metrics):
        driven = metrics[metrics["segment"] == "Discount Driven"]
        if not driven.empty:
            assert (driven["discount_rate"].dropna() >= 0.5).all()

    def test_small_datasets_still_produce_spread(self):
        rows = [
            {"customer_id": f"C{i}", "display_name": f"P{i}",
             "total_spend": float(100 * (i + 1)), "order_count": float(i + 1),
             "recency_days": float(300 - i * 30), "tenure_days": 500.0}
            for i in range(8)
        ]
        result = compute_rfm(pd.DataFrame(rows))
        assert result["segment"].nunique() >= 2

    def test_segment_summary_reports_revenue_share(self, metrics):
        summary = segment_summary(metrics)
        assert summary
        shares = [s["shareOfRevenue"] for s in summary if s["shareOfRevenue"] is not None]
        assert sum(shares) == pytest.approx(1.0, abs=0.02)


class TestInventoryAgeing:
    def _catalogue(self, **overrides) -> pd.DataFrame:
        base = {
            "product_id": ["P1", "P2", "P3"],
            "product_name": ["New Coat", "Old Coat", "Steady Knit"],
            "price": [800.0, 800.0, 300.0],
            "cost": [400.0, 400.0, 150.0],
            "stock": [4.0, 4.0, 4.0],
            "category": ["Coats", "Coats", "Knitwear"],
            "arrival_date": [
                pd.Timestamp("2026-05-20"),   # 21 days old
                pd.Timestamp("2025-04-10"),   # 14 months old
                pd.Timestamp("2026-01-10"),
            ],
        }
        base.update(overrides)
        return pd.DataFrame(base)

    def test_days_in_stock_is_computed_from_arrival(self):
        products = build_inventory_metrics(self._catalogue(), None,
                                           as_of=pd.Timestamp("2026-06-10"))
        assert products.iloc[0]["days_in_stock"] == 21
        assert products.iloc[1]["days_in_stock"] > 400

    def test_a_new_arrival_that_has_not_sold_is_not_at_risk(self):
        """Stock that has had no time to sell must not be flagged for not selling."""
        transactions = pd.DataFrame({
            "product_id": ["P3"], "date": [pd.Timestamp("2026-06-01")],
            "net_amount": [300.0], "quantity": [2.0],
        })
        products = build_inventory_metrics(self._catalogue(), transactions,
                                           as_of=pd.Timestamp("2026-06-10"))
        new_arrival = products[products["product_id"] == "P1"].iloc[0]
        assert new_arrival["status"] in {"Healthy", "Hot"}
        assert new_arrival["risk_score"] < 45

    def test_old_unsold_stock_is_flagged(self):
        products = build_inventory_metrics(self._catalogue(), None,
                                           as_of=pd.Timestamp("2026-06-10"))
        old = products[products["product_id"] == "P2"].iloc[0]
        assert old["status"] in {"At Risk", "Dead Stock", "Slow Moving"}
        assert old["risk_score"] > 45

    def test_risk_drivers_explain_the_score(self):
        products = build_inventory_metrics(self._catalogue(), None,
                                           as_of=pd.Timestamp("2026-06-10"))
        drivers = products[products["product_id"] == "P2"].iloc[0]["risk_drivers"]
        assert drivers
        for driver in drivers:
            assert driver["name"] and driver["detail"]
            assert driver["points"] >= 0

    def test_the_recommended_action_is_not_a_reflex_markdown(self):
        products = build_inventory_metrics(self._catalogue(), None,
                                           as_of=pd.Timestamp("2026-06-10"))
        at_risk = products[products["status"].isin(["At Risk", "Dead Stock", "Slow Moving"])]
        for _, row in at_risk.iterrows():
            action = row["recommended_action"]
            assert action["action"] in {"clienteling", "targeted_outreach", "rescue", "clear"}
            # discounting is only ever the fallback, never the first suggestion
            if action["action"] == "rescue":
                assert "before discounting" in action["detail"].lower() or \
                       "try the top customer matches" in action["detail"].lower()

    def test_out_of_stock_products_are_not_reported_as_at_risk(self):
        products = build_inventory_metrics(self._catalogue(stock=[0.0, 0.0, 0.0]), None)
        assert products["status"].isin(["Healthy", "Hot"]).all()
        assert products["risk_score"].isna().all()

    def test_stock_value_is_null_when_price_is_unknown(self):
        products = build_inventory_metrics(
            self._catalogue(price=[np.nan, 800.0, 300.0]), None
        )
        assert pd.isna(products.iloc[0]["retail_value"])
        assert products.iloc[0]["retail_value"] != 0

    def test_overview_reports_unknowns_as_none(self):
        catalogue = self._catalogue()
        catalogue["cost"] = np.nan
        overview = inventory_overview(build_inventory_metrics(catalogue, None))
        assert overview["skus"] == 3
        assert overview["inventoryValue"] is None
        assert overview["retailValue"] is not None

    def test_sell_through_uses_units_received_not_units_on_hand(self):
        transactions = pd.DataFrame({
            "product_id": ["P1"] * 6, "date": [pd.Timestamp("2026-06-01")] * 6,
            "net_amount": [800.0] * 6, "quantity": [1.0] * 6,
        })
        products = build_inventory_metrics(self._catalogue(), transactions,
                                           as_of=pd.Timestamp("2026-06-10"))
        # 6 sold of 10 received (6 sold + 4 on hand)
        assert products.iloc[0]["sell_through"] == pytest.approx(0.6)


class TestOpportunityScoring:
    def test_opportunities_are_ranked_and_bounded(self, metrics, products, ctx, tables):
        opportunities = generate_opportunities(metrics, products, ctx, tables["transactions"])
        assert opportunities
        scores = [o["score"] for o in opportunities]
        assert scores == sorted(scores, reverse=True)
        assert all(0 <= score <= 100 for score in scores)

    def test_every_opportunity_carries_its_reasoning(self, metrics, products, ctx, tables):
        for opportunity in generate_opportunities(metrics, products, ctx,
                                                  tables["transactions"])[:12]:
            assert opportunity["title"]
            assert len(opportunity["explanation"]) > 30
            assert opportunity["action"]
            assert 0 < opportunity["probability"] <= 1
            assert 0 <= opportunity["confidence"] <= 1
            assert opportunity["evidence"]
            assert opportunity["customerIds"] or opportunity["productIds"]

    def test_score_rises_with_each_component(self):
        from app.analytics.opportunities import _score

        base = _score(0.2, 500, 0.5, 0.6, 500)
        assert _score(0.4, 500, 0.5, 0.6, 500) > base      # probability
        assert _score(0.2, 2000, 0.5, 0.6, 500) > base     # value
        assert _score(0.2, 500, 0.9, 0.6, 500) > base      # urgency
        assert _score(0.2, 500, 0.5, 0.95, 500) > base     # confidence

    def test_unknown_value_does_not_zero_the_score(self):
        from app.analytics.opportunities import _score

        assert _score(0.3, None, 0.5, 0.6, 500) > 0

    def test_scoring_is_relative_to_the_datasets_own_basket_size(self):
        from app.analytics.opportunities import _score

        # a €400 opportunity in a €500-basket store scores like a €4,000 one
        # in a €5,000-basket store
        small = _score(0.3, 400, 0.5, 0.7, 500)
        large = _score(0.3, 4000, 0.5, 0.7, 5000)
        assert abs(small - large) < 8

    def test_totals_are_probability_weighted(self, metrics, products, ctx, tables):
        opportunities = generate_opportunities(metrics, products, ctx, tables["transactions"])
        totals = opportunity_totals(opportunities)
        assert totals["count"] == len(opportunities)
        assert totals["expectedValue"] < totals["totalValue"]

    def test_dead_stock_rescue_prefers_clienteling_over_markdown(self, metrics, products,
                                                                 ctx, tables):
        opportunities = generate_opportunities(metrics, products, ctx, tables["transactions"])
        rescues = [o for o in opportunities if o["kind"] == "dead_stock_rescue"]
        assert rescues, "the demo data should contain rescuable stock"
        with_matches = [o for o in rescues if o["customers"]]
        assert with_matches
        assert any("before applying any discount" in o["action"] for o in with_matches)

    def test_no_opportunities_without_customers(self):
        assert generate_opportunities(pd.DataFrame(), pd.DataFrame(), None, None) == []
