"""The data quality engine, and the promise that it never invents numbers."""

from __future__ import annotations

import pandas as pd
import pytest

from app.data.validation import analyse_quality, assess_capabilities


def customers(**overrides) -> pd.DataFrame:
    base = {
        "customer_id": ["C1", "C2", "C3"],
        "display_name": ["Rossi", "Bianchi", "Conti"],
        "email": ["a@x.it", "b@x.it", "c@x.it"],
        "total_spend": [1000.0, 2000.0, 500.0],
        "order_count": [3.0, 5.0, 1.0],
        "last_purchase_date": pd.to_datetime(["2026-05-01", "2026-04-01", "2026-01-01"]),
        "city": ["Milano", "Roma", "Milano"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def codes(report) -> set[str]:
    return {issue["code"] for issue in report["issues"]}


class TestHealthScore:
    def test_complete_data_scores_well(self, tables):
        report = analyse_quality(tables)
        assert 60 <= report["score"] <= 100
        assert report["grade"] in {"Excellent", "Good", "Workable"}

    def test_missing_tables_lower_the_score(self, tables):
        full = analyse_quality(tables)["score"]
        partial = analyse_quality({"customers": tables["customers"],
                                   "transactions": None, "inventory": None})["score"]
        assert partial < full

    def test_the_summary_names_what_is_missing(self):
        report = analyse_quality({"customers": customers(),
                                  "transactions": None, "inventory": None})
        assert report["summary"]
        assert "switched off" in report["summary"] or "supports" in report["summary"]

    def test_score_drivers_are_shown(self, tables):
        drivers = analyse_quality(tables)["scoreDrivers"]
        assert len(drivers) >= 4
        for driver in drivers:
            assert driver["label"] and driver["value"] is not None
            assert driver["impact"] <= driver["max"]


class TestIssueDetection:
    def test_invalid_emails_are_found(self):
        report = analyse_quality({
            "customers": customers(email=["ok@x.it", "not-an-email", "also bad"]),
            "transactions": None, "inventory": None,
        })
        assert "invalid_emails" in codes(report)

    def test_duplicate_customers_are_found_by_email(self):
        report = analyse_quality({
            "customers": customers(email=["same@x.it", "same@x.it", "c@x.it"]),
            "transactions": None, "inventory": None,
        })
        assert "duplicate_customers" in codes(report)

    def test_future_dates_are_flagged(self):
        report = analyse_quality({
            "customers": customers(
                last_purchase_date=pd.to_datetime(["2099-01-01", "2026-04-01", "2026-01-01"])
            ),
            "transactions": None, "inventory": None,
        })
        assert "future_dates" in codes(report)

    def test_inconsistent_labels_are_grouped(self):
        report = analyse_quality({
            "customers": customers(city=["Milano", "milano", "MILANO"]),
            "transactions": None, "inventory": None,
        })
        assert "inconsistent_city" in codes(report)

    def test_orphan_transactions_are_reported(self):
        transactions = pd.DataFrame({
            "customer_id": ["C1", None, None],
            "date": pd.to_datetime(["2026-01-01"] * 3),
            "net_amount": [100.0, 200.0, 300.0],
            "product_id": ["P1", "P2", "P3"],
        })
        report = analyse_quality({"customers": customers(),
                                  "transactions": transactions, "inventory": None})
        assert "orphan_transactions" in codes(report)

    def test_missing_amounts_are_reported(self):
        transactions = pd.DataFrame({
            "customer_id": ["C1", "C2"],
            "date": pd.to_datetime(["2026-01-01", "2026-02-01"]),
            "net_amount": [100.0, None],
            "product_id": ["P1", "P2"],
        })
        report = analyse_quality({"customers": customers(),
                                  "transactions": transactions, "inventory": None})
        assert "missing_amounts" in codes(report)

    def test_missing_tables_are_critical(self):
        report = analyse_quality({"customers": None, "transactions": None, "inventory": None})
        assert "no_customers" in codes(report)
        assert "no_inventory" in codes(report)
        assert any(issue["severity"] == "critical" for issue in report["issues"])

    def test_issues_are_ordered_by_severity(self):
        report = analyse_quality({"customers": None, "transactions": None, "inventory": None})
        severities = [issue["severity"] for issue in report["issues"]]
        order = {"critical": 0, "warning": 1, "info": 2}
        assert severities == sorted(severities, key=lambda s: order[s])

    def test_every_issue_explains_itself(self, tables):
        for issue in analyse_quality(tables)["issues"]:
            assert issue["title"] and issue["detail"]
            assert issue["severity"] in {"critical", "warning", "info"}


class TestCapabilities:
    def test_full_data_powers_everything(self, tables):
        capabilities = assess_capabilities(tables)
        assert all(c["status"] != "unavailable" for c in capabilities)

    def test_capabilities_switch_off_without_their_inputs(self):
        capabilities = assess_capabilities(
            {"customers": customers(), "transactions": None, "inventory": None}
        )
        by_key = {c["key"]: c for c in capabilities}
        assert by_key["product_matching"]["status"] == "unavailable"
        assert by_key["trends"]["status"] == "unavailable"
        # ...while the ones that only need customers still work
        assert by_key["customer_prioritisation"]["status"] != "unavailable"

    def test_unavailable_capabilities_say_what_is_missing(self):
        capabilities = assess_capabilities(
            {"customers": customers(), "transactions": None, "inventory": None}
        )
        for capability in capabilities:
            if capability["status"] == "unavailable":
                assert capability["missing"], f"{capability['key']} did not say why"
                assert capability["why"], "a capability must explain its commercial purpose"

    def test_margin_needs_cost_data(self):
        inventory = pd.DataFrame({
            "product_id": ["P1"], "product_name": ["Coat"], "price": [800.0],
            "stock": [3.0], "category": ["Coats"], "cost": [None],
        })
        capabilities = {c["key"]: c for c in assess_capabilities(
            {"customers": customers(), "transactions": None, "inventory": inventory}
        )}
        assert capabilities["margin"]["status"] == "unavailable"


class TestCompleteness:
    def test_absent_tables_report_none_not_zero(self):
        report = analyse_quality({"customers": customers(),
                                  "transactions": None, "inventory": None})
        assert report["completeness"]["transactions"]["present"] is False
        assert report["completeness"]["transactions"]["score"] is None
        assert report["completeness"]["customers"]["score"] is not None
