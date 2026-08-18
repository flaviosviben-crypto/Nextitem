"""The matching engine's contract.

The headline test in this file is
``test_score_survives_when_every_optional_field_is_missing``: it is the
regression test for the defect that made the previous version useless, where a
product match collapsed to 0% because optional catalogue fields were absent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analytics.matching import (
    BASE_WEIGHTS,
    build_context,
    build_profile,
    score_customers_for_product,
    score_products_for_customer,
)


def make_customer(**overrides) -> pd.Series:
    base = {
        "customer_id": "C1",
        "display_name": "Giulia Rossi",
        "segment": "Champions",
        "total_spend": 8400.0,
        "avg_order_value": 700.0,
        "order_count": 12.0,
        "recency_days": 20.0,
        "tx_lines": 18,
        "customer_score": 82.0,
        "category_affinity": [
            {"value": "Coats", "share": 0.45},
            {"value": "Knitwear", "share": 0.30},
        ],
        "brand_affinity": [{"value": "Max Mara", "share": 0.55}],
        "color_affinity": [{"value": "black", "share": 0.5}, {"value": "camel", "share": 0.3}],
        "size_affinity": [{"value": "M", "share": 0.8}],
        "price_band_low": 400.0,
        "price_band_high": 1200.0,
        "price_band_mid": 700.0,
        "discount_rate": 0.1,
        "neutral_color_share": 0.8,
        "purchased_product_ids": ["P900"],
        "seasonality": [],
        "gender": "women",
    }
    base.update(overrides)
    return pd.Series(base)


def make_catalogue(**overrides) -> pd.DataFrame:
    base = {
        "product_id": ["P1", "P2", "P3"],
        "product_name": ["Wool Coat", "Cashmere Knit", "Leather Bag"],
        "category": ["Coats", "Knitwear", "Bags"],
        "brand": ["Max Mara", "Loro Piana", "Totême"],
        "color": ["Black", "Camel", "Red"],
        "size": ["M", "L", "Unica"],
        "price": [890.0, 420.0, 1500.0],
        "stock": [3.0, 5.0, 1.0],
        "risk_score": [40.0, 65.0, 20.0],
        "margin_pct": [55.0, 48.0, 60.0],
        "days_in_stock": [30.0, 150.0, 12.0],
        "status": ["Healthy", "At Risk", "Healthy"],
        "sell_through": [0.5, 0.2, 0.7],
        "units_sold": [4.0, 1.0, 6.0],
        "season": ["FW26", "FW26", "SS26"],
        "gender": ["women", "women", "women"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def score_for(customer: pd.Series, catalogue: pd.DataFrame):
    ctx = build_context(catalogue, pd.DataFrame([customer]))
    return score_products_for_customer(build_profile(customer), ctx, limit=10)


class TestNoFakeZeros:
    """Missing information must never be read as a negative signal."""

    def test_score_survives_when_every_optional_field_is_missing(self):
        # The catalogue has only what is strictly required: an id, a name and
        # stock. This is the exact shape that produced 0% matches before.
        bare = pd.DataFrame({
            "product_id": ["P1", "P2"],
            "product_name": ["Item A", "Item B"],
            "stock": [2.0, 4.0],
        })
        results = score_for(make_customer(), bare)

        assert results, "a bare catalogue must still produce recommendations"
        for result in results:
            assert result["scorePct"] > 0, "a missing field is not a zero score"
            assert result["scorePct"] >= 20, f"score collapsed to {result['scorePct']}%"
            # ...but the product must be honest about how little it knows
            assert result["dataConfidence"] in {"low", "very low"}
            assert result["missingSignals"]

    @pytest.mark.parametrize("dropped", ["color", "size", "brand", "category", "price"])
    def test_dropping_any_single_dimension_keeps_scores_meaningful(self, dropped):
        catalogue = make_catalogue()
        catalogue[dropped] = None
        results = score_for(make_customer(), catalogue)

        assert results
        assert all(r["scorePct"] >= 25 for r in results)
        # the dropped signal is reported as unused, not scored as a failure
        assert any(r["missingSignals"] for r in results) or dropped in {"category", "brand"}

    def test_a_customer_with_no_history_still_gets_ranked_products(self):
        blank = make_customer(
            category_affinity=None, brand_affinity=None, color_affinity=None,
            size_affinity=None, price_band_low=None, price_band_high=None,
            price_band_mid=None, avg_order_value=None, discount_rate=None,
            neutral_color_share=None, purchased_product_ids=None, tx_lines=0,
            recency_days=None,
        )
        results = score_for(blank, make_catalogue())
        assert results
        assert all(r["scorePct"] > 0 for r in results)
        assert all(r["dataConfidence"] in {"low", "very low"} for r in results)

    def test_weights_are_redistributed_not_zeroed(self):
        """A two-signal match and an eight-signal match are on the same scale."""
        rich = score_for(make_customer(), make_catalogue())
        bare_catalogue = make_catalogue()
        for column in ("color", "size", "brand", "season", "gender"):
            bare_catalogue[column] = None
        sparse = score_for(make_customer(), bare_catalogue)

        # Both produce usable scores in the same range; the difference shows up
        # in confidence, not in a collapsed score.
        assert max(r["scorePct"] for r in rich) > 50
        assert max(r["scorePct"] for r in sparse) > 50
        assert sparse[0]["signalCoverage"] < rich[0]["signalCoverage"]


class TestScoreQuality:
    def test_a_matching_product_outranks_an_unrelated_one(self):
        results = score_for(make_customer(), make_catalogue())
        by_id = {r["productId"]: r for r in results}
        # P1: their top category, top brand, favourite colour, exact size, in band
        # P3: unbought category, wrong brand, unworn colour, above their band
        assert by_id["P1"]["scorePct"] > by_id["P3"]["scorePct"]

    def test_price_far_above_the_band_is_penalised(self):
        catalogue = make_catalogue(price=[890.0, 420.0, 9000.0])
        results = {r["productId"]: r for r in score_for(make_customer(), catalogue)}
        price_signal = next(
            s for s in results["P3"]["signals"] if s["key"] == "price"
        )
        assert price_signal["direction"] == "negative"

    def test_scores_differ_between_customers(self):
        """Two different people must not receive the same ranking."""
        coats = make_customer(
            customer_id="C1",
            category_affinity=[{"value": "Coats", "share": 0.9}],
            brand_affinity=[{"value": "Max Mara", "share": 0.9}],
        )
        bags = make_customer(
            customer_id="C2",
            category_affinity=[{"value": "Bags", "share": 0.9}],
            brand_affinity=[{"value": "Totême", "share": 0.9}],
            price_band_low=900.0, price_band_high=2000.0, price_band_mid=1400.0,
        )
        catalogue = make_catalogue()
        top_coats = score_for(coats, catalogue)[0]["productId"]
        top_bags = score_for(bags, catalogue)[0]["productId"]
        assert top_coats != top_bags

    def test_thin_evidence_is_not_presented_as_certainty(self):
        """One purchase must not read as a 100% category preference."""
        one_purchase = make_customer(
            tx_lines=1, order_count=1.0,
            category_affinity=[{"value": "Coats", "share": 1.0}],
            brand_affinity=[{"value": "Max Mara", "share": 1.0}],
        )
        many = make_customer(tx_lines=30, order_count=15.0)
        thin_top = score_for(one_purchase, make_catalogue())[0]
        rich_top = score_for(many, make_catalogue())[0]

        assert thin_top["dataConfidence"] in {"low", "very low"}
        assert rich_top["dataConfidence"] == "high"
        assert thin_top["scorePct"] < 95


class TestExplainability:
    def test_every_result_carries_machine_readable_signals(self):
        result = score_for(make_customer(), make_catalogue())[0]
        assert result["signals"]
        for signal in result["signals"]:
            assert set(signal) >= {"name", "key", "value", "impact", "direction", "reason"}
            assert 0 <= signal["value"] <= 1
            assert signal["impact"] >= 0
            assert signal["direction"] in {"positive", "neutral", "negative"}
            assert signal["reason"], "every signal must explain itself in words"

    def test_signal_impacts_sum_to_approximately_the_score(self):
        result = score_for(make_customer(), make_catalogue())[0]
        total = sum(signal["impact"] for signal in result["signals"])
        assert total == pytest.approx(result["score"], abs=0.02)

    def test_headline_reads_as_a_sentence_a_shopkeeper_would_say(self):
        result = score_for(make_customer(), make_catalogue())[0]
        assert "%" in result["headline"]
        assert len(result["headline"]) > 25

    def test_score_and_confidence_are_reported_separately(self):
        result = score_for(make_customer(), make_catalogue())[0]
        assert isinstance(result["scorePct"], int)
        assert result["dataConfidence"] in {"high", "medium", "low", "very low"}
        assert 0 <= result["signalCoverage"] <= 1


class TestFiltering:
    def test_out_of_stock_products_are_excluded_by_default(self):
        catalogue = make_catalogue(stock=[0.0, 5.0, 0.0])
        results = score_for(make_customer(), catalogue)
        assert {r["productId"] for r in results} == {"P2"}

    def test_unknown_stock_is_not_treated_as_zero_stock(self):
        catalogue = make_catalogue(stock=[np.nan, 5.0, 1.0])
        results = score_for(make_customer(), catalogue)
        assert "P1" in {r["productId"] for r in results}

    def test_a_one_off_product_already_owned_is_not_recommended_again(self):
        catalogue = make_catalogue(
            product_id=["P900", "P2", "P3"], category=["Coats", "Knitwear", "Bags"]
        )
        results = score_for(make_customer(purchased_product_ids=["P900"]), catalogue)
        assert "P900" not in {r["productId"] for r in results}


class TestReverseDirection:
    def test_ranking_customers_for_a_product_uses_the_same_scale(self):
        catalogue = make_catalogue()
        customers = pd.DataFrame([
            make_customer(customer_id="C1"),
            make_customer(customer_id="C2", display_name="Marco Bianchi",
                          category_affinity=[{"value": "Bags", "share": 0.9}]),
        ])
        ctx = build_context(catalogue, customers)
        results = score_customers_for_product(catalogue.iloc[0], customers, ctx, limit=5)

        assert len(results) == 2
        assert results[0]["scorePct"] >= results[1]["scorePct"]
        for result in results:
            assert result["customerId"]
            assert result["customerName"]
            assert result["scorePct"] > 0
            assert result["signals"]

    def test_both_directions_agree_on_the_same_pair(self):
        catalogue = make_catalogue()
        customer = make_customer()
        customers = pd.DataFrame([customer])
        ctx = build_context(catalogue, customers)

        forward = {
            r["productId"]: r["scorePct"]
            for r in score_products_for_customer(build_profile(customer), ctx, limit=10)
        }
        reverse = score_customers_for_product(catalogue.iloc[0], customers, ctx, limit=5)
        assert abs(forward["P1"] - reverse[0]["scorePct"]) <= 1


class TestWeights:
    def test_weights_are_a_sane_distribution(self):
        assert BASE_WEIGHTS["category"] == max(BASE_WEIGHTS.values())
        assert sum(BASE_WEIGHTS.values()) == pytest.approx(1.0, abs=0.02)
        assert all(weight > 0 for weight in BASE_WEIGHTS.values())


class TestOnRealDemoData:
    def test_every_customer_receives_varied_recommendations(self, metrics, ctx):
        tops = []
        for _, row in metrics.head(30).iterrows():
            results = score_products_for_customer(build_profile(row), ctx, limit=1)
            assert results, f"{row['display_name']} received no recommendations"
            assert results[0]["scorePct"] > 0
            tops.append(results[0]["productId"])
        # a recommender that returns the same product to everyone is useless
        assert len(set(tops)) >= len(tops) * 0.4

    def test_no_recommendation_anywhere_scores_zero(self, metrics, ctx):
        for _, row in metrics.head(15).iterrows():
            for result in score_products_for_customer(build_profile(row), ctx, limit=40):
                assert result["scorePct"] > 0
