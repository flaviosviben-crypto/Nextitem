"""Data quality engine.

Produces a 0-100 Data Health Score plus concrete, plain-language findings and a
capability map: what RevenueOS can do with *this* dataset, and what extra column
would unlock the next capability. No finding is invented — every one counts real
rows.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .values import is_emailish

Severity = str  # "critical" | "warning" | "info"


@dataclass
class Finding:
    severity: Severity
    title: str
    detail: str
    affected: int = 0
    fixable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "affected": self.affected,
            "fixable": self.fixable,
        }


@dataclass
class Capability:
    name: str
    available: bool
    reason: str
    unlock: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "available": self.available, "reason": self.reason, "unlock": self.unlock}


@dataclass
class QualityReport:
    score: int
    grade: str
    findings: list[Finding] = field(default_factory=list)
    capabilities: list[Capability] = field(default_factory=list)
    completeness: dict[str, dict[str, Any]] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "grade": self.grade,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
            "capabilities": [c.to_dict() for c in self.capabilities],
            "completeness": self.completeness,
        }


def _fill_rate(records: list[dict[str, Any]], field_name: str) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r.get(field_name) is not None) / len(records)


def _completeness_block(records: list[dict[str, Any]], fields: list[str]) -> dict[str, Any]:
    return {
        "rows": len(records),
        "fields": {f: round(_fill_rate(records, f), 3) for f in fields if any(f in r for r in records)},
    }


def analyse(
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
) -> QualityReport:
    findings: list[Finding] = []
    penalties = 0.0

    # ---------- customers ----------
    if customers:
        ids = [c["customer_id"] for c in customers]
        dupes = [cid for cid, n in Counter(ids).items() if n > 1]
        if dupes:
            affected = sum(n for cid, n in Counter(ids).items() if n > 1)
            findings.append(Finding("warning", "Duplicate customer records",
                                    f"{len(dupes)} customer IDs appear more than once "
                                    f"({affected} rows). Metrics for these customers are merged.",
                                    affected, True))
            penalties += min(8, len(dupes) / max(1, len(customers)) * 40)

        emails = [c.get("email") for c in customers if c.get("email")]
        bad_emails = [e for e in emails if not is_emailish(str(e))]
        if bad_emails:
            findings.append(Finding("warning", "Invalid email addresses",
                                    f"{len(bad_emails)} of {len(emails)} email values are not "
                                    "valid addresses and cannot be used for outreach.",
                                    len(bad_emails), True))
            penalties += min(5, len(bad_emails) / max(1, len(emails)) * 15)

        no_name = sum(1 for c in customers if not c.get("name") or c["name"] == c["customer_id"])
        if no_name > len(customers) * 0.3:
            findings.append(Finding("info", "Customers without a readable name",
                                    f"{no_name} customers are identified only by ID. Outreach "
                                    "suggestions will be less personal.", no_name))
            penalties += 3

        consent_known = sum(1 for c in customers if c.get("marketing_consent") is not None)
        if consent_known == 0:
            findings.append(Finding("critical", "No marketing consent column",
                                    "Consent is unknown for every customer. Outreach actions stay "
                                    "in preview mode until consent is confirmed.", len(customers)))
            penalties += 10
        elif consent_known < len(customers):
            findings.append(Finding("warning", "Partial marketing consent data",
                                    f"{len(customers) - consent_known} customers have no consent "
                                    "value; they are treated as not contactable.",
                                    len(customers) - consent_known))
            penalties += 3
    else:
        findings.append(Finding("info", "No customer file imported",
                                "Customer profiles are derived from transactions only."))

    # ---------- transactions ----------
    if transactions:
        dated = [t for t in transactions if t.get("date")]
        if not dated:
            findings.append(Finding("critical", "No usable transaction dates",
                                    "Without dates there is no recency, cadence or trend analysis.",
                                    len(transactions)))
            penalties += 20
        elif len(dated) < len(transactions):
            missing = len(transactions) - len(dated)
            findings.append(Finding("warning", "Transactions with unreadable dates",
                                    f"{missing} lines have no valid date and are excluded from "
                                    "time-based analysis.", missing))
            penalties += min(6, missing / len(transactions) * 20)

        future = [t for t in dated if t["date"] > date.today()]
        if future:
            findings.append(Finding("warning", "Transactions dated in the future",
                                    f"{len(future)} lines are dated after today. They are kept but "
                                    "may distort recency.", len(future)))
            penalties += 2

        zero_value = sum(1 for t in transactions if not t.get("line_total"))
        if zero_value > len(transactions) * 0.15:
            findings.append(Finding("warning", "Many zero-value lines",
                                    f"{zero_value} lines have no revenue. Check whether returns or "
                                    "gifts are mixed into the export.", zero_value))
            penalties += 4

        cat_known = sum(1 for t in transactions if t.get("category"))
        if cat_known == 0:
            findings.append(Finding("critical", "No product category in transactions",
                                    "Category affinity is the strongest matching signal; without it "
                                    "recommendations rely on price and brand only.", len(transactions)))
            penalties += 12
        elif cat_known < len(transactions) * 0.6:
            findings.append(Finding("warning", "Sparse category data",
                                    f"Only {cat_known / len(transactions):.0%} of lines carry a "
                                    "category. Matching confidence will be lower.",
                                    len(transactions) - cat_known))
            penalties += 5

        cats = Counter(str(t["category"]).strip().lower() for t in transactions if t.get("category"))
        near_dupes = _near_duplicate_labels(list(cats))
        if near_dupes:
            findings.append(Finding("info", "Inconsistent category naming",
                                    "These look like the same category written differently: "
                                    + "; ".join(" / ".join(g) for g in near_dupes[:5]),
                                    sum(len(g) for g in near_dupes), True))
            penalties += 2
    else:
        findings.append(Finding("warning", "No transaction file imported",
                                "Customer metrics fall back to summary columns; product-level "
                                "matching and sell-through cannot be computed."))
        penalties += 12

    # ---------- inventory ----------
    if inventory:
        skus = [p["sku"] for p in inventory]
        dupe_skus = [s for s, n in Counter(skus).items() if n > 1]
        if dupe_skus:
            findings.append(Finding("info", "Duplicate SKUs merged",
                                    f"{len(dupe_skus)} SKUs appeared on multiple rows; their stock "
                                    "was summed.", len(dupe_skus), True))

        no_price = sum(1 for p in inventory if p.get("price") is None)
        if no_price:
            findings.append(Finding("warning" if no_price > len(inventory) * 0.2 else "info",
                                    "Products without a price",
                                    f"{no_price} products have no price. Inventory value and "
                                    "price-fit scoring skip them.", no_price))
            penalties += min(6, no_price / len(inventory) * 15)

        no_stock = sum(1 for p in inventory if p.get("stock") is None)
        if no_stock == len(inventory):
            findings.append(Finding("critical", "No stock quantities",
                                    "Availability is unknown, so recommendations cannot be filtered "
                                    "to sellable items.", no_stock))
            penalties += 10
        elif no_stock:
            findings.append(Finding("info", "Products with unknown stock",
                                    f"{no_stock} products show stock as unknown rather than zero.",
                                    no_stock))

        no_cat = sum(1 for p in inventory if not p.get("category"))
        if no_cat > len(inventory) * 0.3:
            findings.append(Finding("warning", "Products without a category",
                                    f"{no_cat} products are uncategorised and will rarely be matched.",
                                    no_cat))
            penalties += 5

        negative = sum(1 for p in inventory if (p.get("stock") or 0) < 0 or (p.get("price") or 0) < 0)
        if negative:
            findings.append(Finding("warning", "Suspicious negative values",
                                    f"{negative} products have a negative price or stock.", negative))
            penalties += 3
    else:
        findings.append(Finding("warning", "No inventory file imported",
                                "Product recommendations need a catalogue; only category-level "
                                "guidance is possible."))
        penalties += 12

    # ---------- link quality ----------
    if customers and transactions:
        cust_ids = {c["customer_id"] for c in customers}
        orphan = {t["customer_id"] for t in transactions} - cust_ids
        if orphan:
            findings.append(Finding("warning", "Transactions without a matching customer",
                                    f"{len(orphan)} customer IDs appear in transactions but not in "
                                    "the customer file. They are still analysed as customers.",
                                    len(orphan)))
            penalties += min(6, len(orphan) / max(1, len(cust_ids)) * 20)
    if transactions and inventory:
        tx_skus = {t["sku"] for t in transactions if t.get("sku")}
        inv_skus = {p["sku"] for p in inventory}
        if tx_skus:
            overlap = len(tx_skus & inv_skus) / len(tx_skus)
            if overlap < 0.3:
                findings.append(Finding("warning", "Sales and catalogue barely share SKUs",
                                        f"Only {overlap:.0%} of sold SKUs exist in the catalogue. "
                                        "SKU-level matching falls back to category matching.",
                                        len(tx_skus - inv_skus)))
                penalties += 6

    score = int(max(0, min(100, round(100 - penalties))))
    grade = ("Excellent" if score >= 85 else "Good" if score >= 70
             else "Workable" if score >= 50 else "Limited")

    caps = _capabilities(customers, transactions, inventory)
    report = QualityReport(
        score=score,
        grade=grade,
        findings=sorted(findings, key=lambda f: {"critical": 0, "warning": 1, "info": 2}[f.severity]),
        capabilities=caps,
        completeness={
            "customers": _completeness_block(customers, [
                "customer_id", "name", "email", "marketing_consent", "total_spend",
                "num_purchases", "last_purchase_date", "preferred_category", "store", "size"]),
            "transactions": _completeness_block(transactions, [
                "customer_id", "date", "line_total", "sku", "category", "brand", "color", "size"]),
            "inventory": _completeness_block(inventory, [
                "sku", "product_name", "category", "brand", "price", "cost", "stock",
                "color", "size", "arrival_date"]),
        },
    )
    report.summary = _summarise(report, customers, transactions, inventory)
    return report


def _near_duplicate_labels(labels: list[str]) -> list[list[str]]:
    """Group labels that differ only by spacing, punctuation or plural 's'."""
    groups: dict[str, list[str]] = {}
    for label in labels:
        key = "".join(ch for ch in label.lower() if ch.isalnum()).rstrip("s")
        groups.setdefault(key, []).append(label)
    return [g for g in groups.values() if len(g) > 1]


def _capabilities(customers, transactions, inventory) -> list[Capability]:
    has_tx = bool(transactions)
    has_dates = any(t.get("date") for t in transactions)
    has_cat = any(t.get("category") for t in transactions) or any(p.get("category") for p in inventory)
    has_inv = bool(inventory)
    has_stock = any(p.get("stock") is not None for p in inventory)
    has_price = any(p.get("price") is not None for p in inventory)
    has_consent = any(c.get("marketing_consent") is not None for c in customers)
    has_spend = any(c.get("total_spend") is not None for c in customers) or has_tx

    return [
        Capability("Customer value ranking", has_spend,
                   "Spend data is available." if has_spend else "No spend or transaction data.",
                   "" if has_spend else "Add a lifetime spend column or a transactions export."),
        Capability("Recency & churn risk", has_dates or any(c.get("last_purchase_date") for c in customers),
                   "Purchase dates are available." if has_dates else "Dates come from customer summary only."
                   if any(c.get("last_purchase_date") for c in customers) else "No purchase dates found.",
                   "" if has_dates else "Add transaction dates for accurate repurchase cadence."),
        Capability("RFM segmentation", has_tx and has_dates,
                   "Recency, frequency and monetary value can all be computed."
                   if has_tx and has_dates else "Needs dated transaction history.",
                   "" if has_tx and has_dates else "Import a transactions file with dates and amounts."),
        Capability("Product matching", has_inv and has_cat,
                   "Catalogue and category signals are present."
                   if has_inv and has_cat else "Needs a catalogue with categories.",
                   "" if has_inv and has_cat else "Import products with a category column."),
        Capability("Stock-aware recommendations", has_inv and has_stock,
                   "Stock levels are known." if has_stock else "Stock is unknown, availability is unverified.",
                   "" if has_stock else "Add a stock/giacenza column to your product export."),
        Capability("Margin & inventory value", has_price,
                   "Prices are available." if has_price else "No product prices.",
                   "" if has_price else "Add price (and cost, for margin) to the product export."),
        Capability("Compliant outreach", has_consent,
                   "Consent status is recorded." if has_consent else "No consent column: outreach stays preview-only.",
                   "" if has_consent else "Add a marketing consent column to enable approvals."),
        Capability("Sell-through & dead stock", has_tx and has_inv,
                   "Sales and catalogue can be joined." if has_tx and has_inv
                   else "Needs both transactions and inventory.",
                   "" if has_tx and has_inv else "Import both transactions and products."),
    ]


def _summarise(report: QualityReport, customers, transactions, inventory) -> str:
    parts = [
        f"Data Health {report.score}/100 ({report.grade}). "
        f"{len(customers):,} customers, {len(transactions):,} transaction lines, "
        f"{len(inventory):,} products."
    ]
    ready = [c.name for c in report.capabilities if c.available]
    blocked = [c for c in report.capabilities if not c.available]
    if ready:
        parts.append("Ready for: " + ", ".join(ready[:4]).lower() + ".")
    if blocked:
        first = blocked[0]
        parts.append(f"{first.name} is limited — {first.unlock or first.reason}")
    return " ".join(parts)
