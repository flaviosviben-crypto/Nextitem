"""Customer metrics, RFM, inventory ageing and opportunity scoring."""
from __future__ import annotations

from datetime import date, timedelta

from app.analytics import customer_scoring, inventory, opportunities, rfm

TODAY = date(2026, 8, 17)


def _tx(cid, days_ago, amount, category="Leather Goods", sku="A1", order=None, brand="Totême"):
    return {
        "customer_id": cid,
        "transaction_id": order or f"O-{cid}-{days_ago}",
        "date": TODAY - timedelta(days=days_ago),
        "line_total": amount, "unit_price": amount, "quantity": 1,
        "category": category, "brand": brand, "sku": sku, "color": "Black", "size": "M",
    }


def test_metrics_from_transactions():
    txs = [_tx("C1", 300, 500), _tx("C1", 200, 700), _tx("C1", 100, 900)]
    profiles = customer_scoring.build_profiles([{"customer_id": "C1", "name": "Anna"}], txs, TODAY)
    p = profiles[0]
    assert p["total_spend"] == 2100
    assert p["order_count"] == 3
    assert p["avg_order_value"] == 700
    assert p["recency_days"] == 100
    assert p["cadence_days"] == 100
    assert p["spend_source"] == "transactions"
    assert p["top_category"] == "Leather Goods"


def test_basket_lines_group_into_one_order():
    txs = [_tx("C1", 100, 300, order="O1"), _tx("C1", 100, 200, order="O1", sku="A2")]
    p = customer_scoring.build_profiles([{"customer_id": "C1", "name": "A"}], txs, TODAY)[0]
    assert p["order_count"] == 1
    assert p["avg_order_value"] == 500


def test_falls_back_to_crm_summary_without_transactions():
    customers = [{
        "customer_id": "C1", "name": "Anna", "total_spend": 3000,
        "num_purchases": 4, "last_purchase_date": TODAY - timedelta(days=40),
        "first_purchase_date": TODAY - timedelta(days=400),
    }]
    p = customer_scoring.build_profiles(customers, [], TODAY)[0]
    assert p["total_spend"] == 3000
    assert p["avg_order_value"] == 750
    assert p["spend_source"] == "crm summary"
    assert p["recency_days"] == 40


def test_unknown_metrics_are_none_never_zero():
    p = customer_scoring.build_profiles([{"customer_id": "C1", "name": "Anna"}], [], TODAY)[0]
    assert p["total_spend"] is None
    assert p["avg_order_value"] is None
    assert p["cadence_days"] is None
    assert p["data_confidence"] == "Low"


def test_customer_only_in_transactions_is_still_profiled():
    profiles = customer_scoring.build_profiles([], [_tx("GHOST", 30, 400)], TODAY)
    assert [p["customer_id"] for p in profiles] == ["GHOST"]


def test_segments_adapt_to_the_dataset():
    customers, txs = [], []
    for i in range(30):
        cid = f"C{i}"
        customers.append({"customer_id": cid, "name": f"Cust {i}", "marketing_consent": True})
        # Spread of value and recency so quintiles have something to bite on.
        for n in range(1 + i % 6):
            txs.append(_tx(cid, 30 + i * 12 + n * 45, 100 + i * 60, order=f"{cid}-{n}"))
    profiles = customer_scoring.build_profiles(customers, txs, TODAY)
    profiles = rfm.assign_segments(profiles)

    labels = {p["segment"] for p in profiles}
    assert len(labels) >= 3, "a varied dataset must produce a spread of segments"
    assert labels <= set(rfm.SEGMENTS)
    for p in profiles:
        assert p["segment_play"]


def test_recency_is_relative_to_each_customers_cadence():
    """A twice-a-year buyer at 100 days is fine; a monthly buyer at 100 days is not."""
    customers = [{"customer_id": "SLOW", "name": "Slow"}, {"customer_id": "FAST", "name": "Fast"}]
    txs = [
        _tx("SLOW", 500, 900, order="s1"), _tx("SLOW", 320, 900, order="s2"),
        _tx("SLOW", 100, 900, order="s3"),
        _tx("FAST", 190, 900, order="f1"), _tx("FAST", 160, 900, order="f2"),
        _tx("FAST", 130, 900, order="f3"),
    ]
    profiles = customer_scoring.build_profiles(customers, txs, TODAY)
    by_id = {p["customer_id"]: p for p in profiles}
    assert by_id["SLOW"]["overdue_ratio"] < by_id["FAST"]["overdue_ratio"]


def test_inventory_ageing_and_risk():
    products = [
        {"sku": "OLD", "product_name": "Old Coat", "category": "Ready-to-Wear", "price": 800,
         "cost": 320, "stock": 6, "arrival_date": TODAY - timedelta(days=500)},
        {"sku": "NEW", "product_name": "New Coat", "category": "Ready-to-Wear", "price": 800,
         "cost": 320, "stock": 4, "arrival_date": TODAY - timedelta(days=20)},
    ]
    txs = [_tx("C1", 10, 800, sku="NEW"), _tx("C2", 5, 800, sku="NEW", order="O2")]
    stats = inventory.build_product_stats(products, txs, TODAY)
    by_sku = {p["sku"]: p for p in stats}

    assert by_sku["OLD"]["days_in_stock"] == 500
    assert by_sku["OLD"]["units_sold"] == 0
    assert by_sku["OLD"]["risk_score"] > by_sku["NEW"]["risk_score"]
    assert by_sku["OLD"]["risk_class"] in {"At Risk", "Dead Stock"}
    assert by_sku["OLD"]["risk_drivers"], "risk must be explainable"
    assert "discount" not in by_sku["OLD"]["recommended_action"].split(".")[0].lower()
    assert by_sku["OLD"]["stock_value"] == 4800
    assert by_sku["OLD"]["margin_rate"] == 0.6


def test_inventory_without_signals_is_unknown_not_risky():
    stats = inventory.build_product_stats(
        [{"sku": "X", "product_name": "Mystery", "category": "Shoes"}], [], TODAY)
    p = stats[0]
    assert p["risk_score"] is None
    assert p["risk_class"] == "Unknown"
    assert "Not enough information" in p["risk_reason"]


def test_sell_through_needs_both_halves():
    stats = inventory.build_product_stats(
        [{"sku": "X", "product_name": "P", "category": "Shoes", "price": 100}], [], TODAY)
    assert stats[0]["sell_through"] is None


def test_opportunities_are_ranked_and_explainable():
    customers, txs = [], []
    for i in range(24):
        cid = f"C{i}"
        customers.append({"customer_id": cid, "name": f"Cust {i}", "marketing_consent": True})
        for n in range(4):
            txs.append(_tx(cid, 400 - n * 90 + i, 600 + i * 40, order=f"{cid}-{n}"))
    profiles = rfm.assign_segments(customer_scoring.build_profiles(customers, txs, TODAY))
    products = inventory.build_product_stats([
        {"sku": "A1", "product_name": "Tote", "category": "Leather Goods", "brand": "Totême",
         "price": 890, "cost": 340, "stock": 5, "arrival_date": TODAY - timedelta(days=400)},
        {"sku": "A2", "product_name": "New Tote", "category": "Leather Goods", "brand": "Totême",
         "price": 950, "cost": 360, "stock": 4, "arrival_date": TODAY - timedelta(days=15)},
    ], txs, TODAY)

    found = opportunities.detect(profiles, products, txs, TODAY)
    assert found
    assert all(0 <= o["score"] <= 100 for o in found)
    assert found == sorted(found, key=lambda o: -o["score"])
    for o in found:
        assert o["title"] and o["explanation"] and o["action"]
        assert o["impact_basis"], "every money figure must state its basis"
        assert o["expected_value"] is not None


def test_expected_value_is_below_headline_impact():
    """Headline impact is the best case; expected value must be discounted."""
    customers = [{"customer_id": f"C{i}", "name": f"C{i}", "marketing_consent": True}
                 for i in range(20)]
    txs = [_tx(f"C{i}", 300 - n * 80, 700, order=f"C{i}-{n}")
           for i in range(20) for n in range(3)]
    profiles = rfm.assign_segments(customer_scoring.build_profiles(customers, txs, TODAY))
    found = opportunities.detect(profiles, [], txs, TODAY)
    for o in found:
        if o.get("impact"):
            assert o["expected_value"] <= o["impact"]


def test_portfolio_summary_handles_empty_dataset():
    summary = customer_scoring.summarize_base([])
    assert summary["customers"] == 0
    assert summary["total_spend"] is None
