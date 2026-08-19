"""Matching engine — above all, the missing-data behaviour.

The bug this suite exists to prevent: a recommendation scoring 0% simply because
optional fields (colour, size, brand, stock) were absent from the export.
"""
from __future__ import annotations

from app.analytics import matching

FULL_CUSTOMER = {
    "customer_id": "C1",
    "name": "Giulia Rossi",
    "category_affinity": {"Leather Goods": 0.7, "Accessories": 0.3},
    "brand_affinity": {"Totême": 0.6, "Marni": 0.4},
    "color_affinity": {"Black": 0.6, "Camel": 0.4},
    "size_affinity": {"One Size": 1.0},
    "price_low": 400, "price_median": 800, "price_high": 1400,
    "purchased_skus": ["OLD-1"],
    "order_count": 6, "cadence_days": 90, "overdue_ratio": 1.1,
    "transaction_count": 9, "marketing_consent": True,
}

FULL_PRODUCT = {
    "sku": "LG-001", "product_name": "Structured Tote", "category": "Leather Goods",
    "brand": "Totême", "price": 890, "stock": 3, "color": "Black", "size": "One Size",
    "risk_class": "Healthy",
}


def _bare(source: dict, keep: set[str]) -> dict:
    return {k: v for k, v in source.items() if k in keep}


def test_full_signal_match_scores_high():
    m = matching.score_pair(FULL_CUSTOMER, FULL_PRODUCT)
    assert m is not None
    assert m["match_pct"] >= 80
    assert m["data_confidence"] == "High"
    assert m["why"]


def test_missing_optional_fields_do_not_zero_the_score():
    """The core regression: strip colour, size and brand from both sides."""
    customer = dict(FULL_CUSTOMER)
    customer.pop("color_affinity")
    customer.pop("size_affinity")
    customer.pop("brand_affinity")
    product = dict(FULL_PRODUCT)
    product.pop("color")
    product.pop("size")
    product.pop("brand")

    m = matching.score_pair(customer, product)
    assert m is not None
    assert m["match_pct"] > 0, "missing optional data must never produce a 0% match"
    assert m["match_pct"] >= 70, "category and price alone should still match strongly"
    assert "Colour fit" in m["missing_signals"]
    assert "Brand fit" in m["missing_signals"]


def test_weights_are_renormalised_over_applicable_signals():
    m = matching.score_pair(FULL_CUSTOMER, FULL_PRODUCT)
    live = [s for s in m["signals"] if s["applicable"]]
    assert abs(sum(s["weight"] for s in live) - 1.0) < 1e-3

    sparse_product = {"sku": "X", "product_name": "Thing", "category": "Leather Goods",
                      "price": 850, "stock": 2}
    m2 = matching.score_pair(FULL_CUSTOMER, sparse_product)
    live2 = [s for s in m2["signals"] if s["applicable"]]
    assert abs(sum(s["weight"] for s in live2) - 1.0) < 1e-3
    assert len(live2) < len(live)


def test_sparse_data_lowers_confidence_not_the_score():
    rich = matching.score_pair(FULL_CUSTOMER, FULL_PRODUCT)

    thin_customer = _bare(FULL_CUSTOMER, {"customer_id", "name", "category_affinity",
                                          "price_median", "price_low", "price_high"})
    thin_customer["transaction_count"] = 1
    thin_product = _bare(FULL_PRODUCT, {"sku", "product_name", "category", "price", "stock"})

    thin = matching.score_pair(thin_customer, thin_product)
    assert thin["match_pct"] >= 70
    assert thin["data_confidence"] in {"Low", "Medium"}
    assert thin["coverage"] < rich["coverage"]


def test_out_of_stock_is_gated_not_scored_zero():
    product = dict(FULL_PRODUCT, stock=0)
    assert matching.score_pair(FULL_CUSTOMER, product, require_stock=True) is None
    # Without the stock requirement it is scored normally again.
    assert matching.score_pair(FULL_CUSTOMER, product, require_stock=False) is not None


def test_unknown_stock_is_not_treated_as_out_of_stock():
    product = dict(FULL_PRODUCT)
    product.pop("stock")
    m = matching.score_pair(FULL_CUSTOMER, product, require_stock=True)
    assert m is not None, "unknown stock must not be read as zero stock"
    assert m["match_pct"] > 0


def test_unrelated_category_scores_low_but_is_not_none():
    product = dict(FULL_PRODUCT, category="Beauty", sku="B-1", product_name="Perfume")
    m = matching.score_pair(FULL_CUSTOMER, product)
    assert m is not None
    assert m["match_pct"] < 60


def test_customer_without_any_signal_returns_none():
    empty = {"customer_id": "E", "name": "Empty", "transaction_count": 0}
    assert matching.score_pair(empty, FULL_PRODUCT) is None


def test_already_purchased_sku_is_penalised():
    customer = dict(FULL_CUSTOMER, purchased_skus=["LG-001"])
    owned = matching.score_pair(customer, FULL_PRODUCT)
    fresh = matching.score_pair(FULL_CUSTOMER, FULL_PRODUCT)
    assert owned["match_pct"] < fresh["match_pct"]


def test_recommendations_differ_between_customers():
    shoes_lover = dict(FULL_CUSTOMER, customer_id="C2",
                       category_affinity={"Shoes": 1.0}, brand_affinity={"Autry": 1.0})
    catalogue = [
        FULL_PRODUCT,
        {"sku": "SH-1", "product_name": "Leather Loafer", "category": "Shoes",
         "brand": "Autry", "price": 620, "stock": 4, "color": "Black", "size": "38"},
    ]
    a = matching.best_products_for_customer(FULL_CUSTOMER, catalogue, limit=1)
    b = matching.best_products_for_customer(shoes_lover, catalogue, limit=1)
    assert a[0]["sku"] != b[0]["sku"], "different customers must get different recommendations"


def test_signals_are_machine_readable_and_explain_the_score():
    m = matching.score_pair(FULL_CUSTOMER, FULL_PRODUCT)
    category = next(s for s in m["signals"] if s["name"] == "category")
    assert 0 <= category["score"] <= 1
    assert category["reason"]
    total = sum(s["impact"] for s in m["signals"] if s["applicable"])
    assert abs(total - m["score"]) < 1e-3, "impacts must sum to the reported score"


def test_gender_mismatch_is_excluded():
    product = dict(FULL_PRODUCT, gender="Uomo")
    customer = dict(FULL_CUSTOMER, gender="Donna")
    assert matching.score_pair(customer, product) is None


def test_expected_value_respects_consent():
    m = matching.score_pair(FULL_CUSTOMER, FULL_PRODUCT)
    consented = matching.expected_value(m, FULL_CUSTOMER)
    unknown = matching.expected_value(m, dict(FULL_CUSTOMER, marketing_consent=None))
    assert consented > unknown
