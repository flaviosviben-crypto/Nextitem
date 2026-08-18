"""Data Quality Engine: what is in the data, what is missing, what it unlocks.

Two outputs matter to the user:

* a **Data Health Score** (0-100) they can act on, and
* a **capability map** that says, in business language, which parts of
  RevenueOS are fully powered, partially powered, or switched off — and what
  they would have to provide to switch them on.

Nothing here reports a metric as ``0`` when the truth is "unknown".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .cleaning import deduplicate_customers
from .mapping import EMAIL_RE
from .parsing import normalise_label

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass
class Issue:
    code: str
    severity: str          # critical | warning | info
    title: str
    detail: str
    entity: str
    count: int | None = None
    share: float | None = None
    examples: list[str] = field(default_factory=list)
    fix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "entity": self.entity,
            "count": self.count,
            "share": round(self.share, 4) if self.share is not None else None,
            "examples": self.examples[:6],
            "fix": self.fix,
        }


# --------------------------------------------------------------------------- #
# capability model
# --------------------------------------------------------------------------- #
CAPABILITIES: list[dict[str, Any]] = [
    {
        "key": "customer_prioritisation",
        "label": "Customer prioritisation",
        "why": "Rank who to contact today by value and urgency.",
        "requires": [("customers", "customer_id")],
        "boosts": [("transactions", "date"), ("transactions", "net_amount"),
                   ("customers", "last_purchase_date")],
    },
    {
        "key": "rfm",
        "label": "RFM segmentation",
        "why": "Split your base into VIPs, at-risk, sleeping and new customers.",
        "requires": [("customers", "customer_id")],
        "boosts": [("transactions", "date"), ("transactions", "net_amount"),
                   ("customers", "total_spend"), ("customers", "order_count")],
    },
    {
        "key": "product_matching",
        "label": "Customer × product matching",
        "why": "Recommend the right piece to the right client, with reasons.",
        "requires": [("inventory", "product_id"), ("customers", "customer_id")],
        "boosts": [("transactions", "product_id"), ("inventory", "category"),
                   ("inventory", "brand"), ("inventory", "price"),
                   ("inventory", "color"), ("inventory", "size")],
    },
    {
        "key": "inventory_risk",
        "label": "Inventory risk & dead stock",
        "why": "Spot capital stuck on the shelf before it becomes a markdown.",
        "requires": [("inventory", "product_id"), ("inventory", "stock")],
        "boosts": [("inventory", "arrival_date"), ("inventory", "price"),
                   ("inventory", "cost"), ("transactions", "product_id")],
    },
    {
        "key": "margin",
        "label": "Margin intelligence",
        "why": "Prioritise actions by profit, not just revenue.",
        "requires": [("inventory", "cost")],
        "boosts": [("inventory", "price"), ("transactions", "discount")],
    },
    {
        "key": "trends",
        "label": "Revenue trends & seasonality",
        "why": "See what is accelerating and what is fading.",
        "requires": [("transactions", "date"), ("transactions", "net_amount")],
        "boosts": [("transactions", "category"), ("transactions", "brand")],
    },
    {
        "key": "outreach",
        "label": "Outreach & campaigns",
        "why": "Turn a target list into an actual contact list.",
        "requires": [("customers", "customer_id")],
        "boosts": [("customers", "email"), ("customers", "phone"), ("customers", "consent")],
    },
]


def _column_available(frame: pd.DataFrame | None, column: str) -> float:
    """Fill rate of a canonical column, or 0.0 when the table is absent."""
    if frame is None or frame.empty or column not in frame.columns:
        return 0.0
    series = frame[column]
    if series.dtype == object:
        filled = series.map(lambda v: v is not None and v == v and str(v).strip() != "" and v != [])
        return float(filled.mean())
    return float(series.notna().mean())


def assess_capabilities(tables: dict[str, pd.DataFrame | None]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cap in CAPABILITIES:
        required = [(e, c, _column_available(tables.get(e), c)) for e, c in cap["requires"]]
        boosts = [(e, c, _column_available(tables.get(e), c)) for e, c in cap["boosts"]]

        required_ok = all(rate >= 0.3 for _, _, rate in required)
        boost_rate = float(np.mean([r for _, _, r in boosts])) if boosts else 1.0

        if not required_ok:
            status, strength = "unavailable", 0.0
        elif boost_rate >= 0.75:
            status, strength = "full", round(0.75 + 0.25 * boost_rate, 3)
        elif boost_rate >= 0.3:
            status, strength = "partial", round(0.4 + 0.45 * boost_rate, 3)
        else:
            status, strength = "limited", round(0.2 + 0.4 * boost_rate, 3)

        missing = [
            f"{e}.{c}" for e, c, rate in required + boosts if rate < 0.3
        ]
        out.append({
            "key": cap["key"],
            "label": cap["label"],
            "why": cap["why"],
            "status": status,
            "strength": strength,
            "missing": missing,
        })
    return out


# --------------------------------------------------------------------------- #
# issue detection
# --------------------------------------------------------------------------- #
def _string_values(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype=object)
    series = frame[column].dropna()
    return series[series.astype(str).str.strip() != ""]


def _inconsistent_labels(frame: pd.DataFrame, column: str, entity: str,
                         label: str) -> Issue | None:
    """Find labels that collapse to the same normalised token (Coats / coats / COATS)."""
    values = _string_values(frame, column)
    if values.empty:
        return None
    buckets: dict[str, set[str]] = {}
    for raw in values.astype(str):
        key = " ".join(raw.lower().split())
        buckets.setdefault(key, set()).add(raw.strip())
    clashes = {k: v for k, v in buckets.items() if len(v) > 1}
    if not clashes:
        return None
    examples = [" / ".join(sorted(v)) for v in list(clashes.values())[:6]]
    return Issue(
        code=f"inconsistent_{column}",
        severity="warning",
        title=f"Inconsistent {label.lower()} spellings",
        detail=(
            f"{len(clashes)} {label.lower()} value(s) appear with different capitalisation "
            "or spacing. RevenueOS groups them together, but your source system may not."
        ),
        entity=entity,
        count=len(clashes),
        examples=examples,
        fix=f"Standardise {label.lower()} naming in your POS export.",
    )


def analyse_quality(tables: dict[str, pd.DataFrame | None]) -> dict[str, Any]:
    """Full data-quality pass across the three canonical tables."""
    customers = tables.get("customers")
    transactions = tables.get("transactions")
    inventory = tables.get("inventory")
    issues: list[Issue] = []

    # ---------------- customers ---------------- #
    if customers is not None and not customers.empty:
        emails = _string_values(customers, "email")
        if not emails.empty:
            invalid = emails[~emails.astype(str).map(lambda v: bool(EMAIL_RE.match(v)))]
            if len(invalid):
                issues.append(Issue(
                    code="invalid_emails", severity="warning",
                    title="Invalid email addresses",
                    detail=f"{len(invalid)} of {len(emails)} email values are not valid addresses.",
                    entity="customers", count=len(invalid),
                    share=len(invalid) / len(emails),
                    examples=[str(v) for v in invalid.head(5)],
                    fix="Correct or clear these addresses before running email campaigns.",
                ))
        else:
            issues.append(Issue(
                code="no_emails", severity="info", title="No email addresses",
                detail="Email campaigns and digital outreach lists cannot be produced.",
                entity="customers",
                fix="Add an email column to unlock campaign exports.",
            ))

        _, duplicate_groups = deduplicate_customers(customers)
        if duplicate_groups:
            affected = sum(len(g["customerIds"]) for g in duplicate_groups)
            issues.append(Issue(
                code="duplicate_customers", severity="warning",
                title="Possible duplicate customers",
                detail=(
                    f"{len(duplicate_groups)} group(s) covering {affected} records look like the "
                    "same person recorded twice. Their spend is currently counted separately."
                ),
                entity="customers", count=len(duplicate_groups),
                examples=[f"{g['key']} ({', '.join(g['names'][:2])})" for g in duplicate_groups[:5]],
                fix="Merge these records in your POS to get accurate lifetime value.",
            ))

        if "last_purchase_date" in customers:
            dates = customers["last_purchase_date"].dropna()
            if not dates.empty:
                future = dates[dates > pd.Timestamp.now() + pd.Timedelta(days=1)]
                if len(future):
                    issues.append(Issue(
                        code="future_dates", severity="warning",
                        title="Purchase dates in the future",
                        detail=f"{len(future)} customer(s) have a last-purchase date in the future.",
                        entity="customers", count=len(future),
                        fix="Usually a date-format mix-up (MM/DD vs DD/MM) in the export.",
                    ))

        for column, label in (("city", "City"), ("store", "Store")):
            issue = _inconsistent_labels(customers, column, "customers", label)
            if issue:
                issues.append(issue)

        if "total_spend" in customers:
            spend = customers["total_spend"].dropna()
            if not spend.empty:
                negative = spend[spend < 0]
                if len(negative):
                    issues.append(Issue(
                        code="negative_spend", severity="warning",
                        title="Negative lifetime spend",
                        detail=f"{len(negative)} customer(s) have negative total spend.",
                        entity="customers", count=len(negative),
                        fix="Check whether refunds are being exported as separate rows.",
                    ))
                if len(spend) > 20:
                    threshold = spend.quantile(0.99) * 25
                    outliers = spend[spend > max(threshold, spend.median() * 200)]
                    if len(outliers):
                        issues.append(Issue(
                            code="spend_outliers", severity="info",
                            title="Suspicious spend values",
                            detail=(
                                f"{len(outliers)} value(s) are orders of magnitude above the rest — "
                                "often a currency in cents mixed with a currency in units."
                            ),
                            entity="customers", count=len(outliers),
                            examples=[f"{v:,.0f}" for v in outliers.head(4)],
                            fix="Confirm all amounts use the same currency and unit.",
                        ))
    else:
        issues.append(Issue(
            code="no_customers", severity="critical", title="No customer table",
            detail="Without customers there is nobody to recommend to.",
            entity="customers", fix="Upload your CRM / customer export.",
        ))

    # ---------------- transactions ---------------- #
    if transactions is not None and not transactions.empty:
        if "customer_id" in transactions:
            orphan = transactions["customer_id"].isna().sum()
            if orphan:
                issues.append(Issue(
                    code="orphan_transactions", severity="warning",
                    title="Transactions without a customer",
                    detail=(
                        f"{int(orphan)} line(s) ({orphan / len(transactions):.0%}) are anonymous. "
                        "They count towards product performance but not towards any profile."
                    ),
                    entity="transactions", count=int(orphan),
                    share=float(orphan / len(transactions)),
                    fix="Ask staff to associate sales with a customer card at the till.",
                ))
            if customers is not None and not customers.empty:
                known = set(customers["customer_id"].dropna().astype(str))
                referenced = set(transactions["customer_id"].dropna().astype(str))
                unknown = referenced - known
                if unknown:
                    issues.append(Issue(
                        code="unknown_customer_refs", severity="warning",
                        title="Transactions referencing unknown customers",
                        detail=(
                            f"{len(unknown)} customer ID(s) appear in transactions but not in the "
                            "customer file. RevenueOS creates lightweight profiles for them."
                        ),
                        entity="transactions", count=len(unknown),
                        examples=sorted(unknown)[:5],
                        fix="Export both files from the same date range.",
                    ))

        if "date" in transactions:
            missing_dates = int(transactions["date"].isna().sum())
            if missing_dates:
                issues.append(Issue(
                    code="missing_dates", severity="warning",
                    title="Transactions without a valid date",
                    detail=f"{missing_dates} line(s) have no parseable date and are excluded from trends.",
                    entity="transactions", count=missing_dates,
                    share=missing_dates / len(transactions),
                    fix="Check for empty or malformed date cells.",
                ))

        if "net_amount" in transactions:
            missing_amount = int(transactions["net_amount"].isna().sum())
            if missing_amount:
                issues.append(Issue(
                    code="missing_amounts", severity="warning",
                    title="Transactions without an amount",
                    detail=f"{missing_amount} line(s) carry no monetary value.",
                    entity="transactions", count=missing_amount,
                    share=missing_amount / len(transactions),
                ))

        if inventory is not None and not inventory.empty and "product_id" in transactions:
            known_products = set(inventory["product_id"].dropna().astype(str))
            referenced = set(transactions["product_id"].dropna().astype(str))
            missing_products = referenced - known_products
            if missing_products and referenced:
                issues.append(Issue(
                    code="unknown_product_refs", severity="info",
                    title="Sold products missing from the catalogue",
                    detail=(
                        f"{len(missing_products)} product ID(s) were sold but are not in the "
                        "inventory file (usually already sold out and archived)."
                    ),
                    entity="transactions", count=len(missing_products),
                    examples=sorted(missing_products)[:5],
                ))

        for column, label in (("category", "Category"), ("brand", "Brand")):
            issue = _inconsistent_labels(transactions, column, "transactions", label)
            if issue:
                issues.append(issue)
    else:
        issues.append(Issue(
            code="no_transactions", severity="warning", title="No transaction history",
            detail=(
                "Customer profiles fall back to summary CRM fields. Purchase timelines, "
                "true affinities and sell-through cannot be computed."
            ),
            entity="transactions",
            fix="Upload a sales export with one row per sold line.",
        ))

    # ---------------- inventory ---------------- #
    if inventory is not None and not inventory.empty:
        if "sku" in inventory:
            skus = _string_values(inventory, "sku")
            if not skus.empty:
                duplicated = skus[skus.duplicated(keep=False)]
                if len(duplicated):
                    issues.append(Issue(
                        code="duplicate_skus", severity="warning",
                        title="Duplicate SKUs",
                        detail=f"{duplicated.nunique()} SKU(s) appear on more than one product row.",
                        entity="inventory", count=int(duplicated.nunique()),
                        examples=[str(v) for v in duplicated.unique()[:5]],
                        fix="Usually size/colour variants sharing a style code — safe, but "
                            "check it is intentional.",
                    ))
        if "price" in inventory:
            prices = inventory["price"].dropna()
            if not prices.empty:
                zero = prices[prices <= 0]
                if len(zero):
                    issues.append(Issue(
                        code="zero_price", severity="warning",
                        title="Products priced at zero",
                        detail=f"{len(zero)} product(s) have a price of 0 or less.",
                        entity="inventory", count=len(zero),
                        fix="These are excluded from value calculations.",
                    ))
            missing_price = int(inventory["price"].isna().sum())
            if missing_price:
                issues.append(Issue(
                    code="missing_price", severity="warning",
                    title="Products without a price",
                    detail=(
                        f"{missing_price} product(s) have no price. Inventory value and price "
                        "matching skip them rather than counting them as €0."
                    ),
                    entity="inventory", count=missing_price,
                    share=missing_price / len(inventory),
                ))
        if "arrival_date" not in inventory or inventory["arrival_date"].isna().all():
            issues.append(Issue(
                code="no_arrival_date", severity="info",
                title="No stock arrival dates",
                detail=(
                    "Stock ageing and dead-stock risk are estimated from sales activity only, "
                    "which is less precise."
                ),
                entity="inventory",
                fix="Add the date each product entered stock to sharpen ageing analysis.",
            ))
        if "cost" not in inventory or inventory["cost"].isna().all():
            issues.append(Issue(
                code="no_cost", severity="info", title="No cost data",
                detail="Margin cannot be computed, so actions are ranked by revenue only.",
                entity="inventory",
                fix="Add a cost column to rank actions by profit.",
            ))
        for column, label in (("category", "Category"), ("brand", "Brand"),
                              ("size", "Size"), ("color", "Colour")):
            issue = _inconsistent_labels(inventory, column, "inventory", label)
            if issue:
                issues.append(issue)
    else:
        issues.append(Issue(
            code="no_inventory", severity="critical", title="No inventory table",
            detail="Product recommendations require a catalogue of what you can actually sell.",
            entity="inventory", fix="Upload your stock / catalogue export.",
        ))

    completeness = _completeness(tables)
    capabilities = assess_capabilities(tables)
    score, grade, drivers = _health_score(tables, issues, completeness, capabilities)

    issues.sort(key=lambda i: (SEVERITY_ORDER.get(i.severity, 3), -(i.count or 0)))
    return {
        "score": score,
        "grade": grade,
        "scoreDrivers": drivers,
        "completeness": completeness,
        "capabilities": capabilities,
        "issues": [i.to_dict() for i in issues],
        "summary": _summary_sentence(score, capabilities, issues),
    }


def _completeness(tables: dict[str, pd.DataFrame | None]) -> dict[str, Any]:
    """Per-table fill rates for the fields that actually drive analytics."""
    weighted = {
        "customers": [
            ("customer_id", 1.0), ("display_name", 0.8), ("email", 0.6), ("phone", 0.4),
            ("city", 0.3), ("total_spend", 0.7), ("order_count", 0.6),
            ("last_purchase_date", 0.9), ("first_purchase_date", 0.4), ("consent", 0.3),
        ],
        "transactions": [
            ("customer_id", 1.0), ("date", 1.0), ("net_amount", 1.0), ("product_id", 0.9),
            ("quantity", 0.4), ("category", 0.7), ("brand", 0.5), ("discount", 0.4),
        ],
        "inventory": [
            ("product_id", 1.0), ("product_name", 0.7), ("price", 0.9), ("stock", 1.0),
            ("category", 0.9), ("brand", 0.7), ("color", 0.5), ("size", 0.5),
            ("cost", 0.6), ("arrival_date", 0.6), ("season", 0.3),
        ],
    }
    out: dict[str, Any] = {}
    for entity, specs in weighted.items():
        frame = tables.get(entity)
        if frame is None or frame.empty:
            out[entity] = {"present": False, "score": None, "rows": 0, "fields": []}
            continue
        fields = []
        total_weight = numerator = 0.0
        for column, weight in specs:
            rate = _column_available(frame, column)
            fields.append({"field": column, "fillRate": round(rate, 4), "weight": weight})
            total_weight += weight
            numerator += weight * rate
        out[entity] = {
            "present": True,
            "rows": int(len(frame)),
            "score": round(100 * numerator / total_weight, 1) if total_weight else None,
            "fields": fields,
        }
    return out


def _health_score(tables, issues, completeness, capabilities) -> tuple[int, str, list[dict]]:
    drivers: list[dict[str, Any]] = []

    present = [e for e in ("customers", "transactions", "inventory")
               if tables.get(e) is not None and not (tables[e] is None or tables[e].empty)]
    coverage = len(present) / 3
    drivers.append({
        "label": "Tables provided",
        "value": f"{len(present)}/3",
        "impact": round(coverage * 30, 1),
        "max": 30,
    })

    fill_scores = [c["score"] for c in completeness.values() if c.get("score") is not None]
    fill = (sum(fill_scores) / len(fill_scores) / 100) if fill_scores else 0.0
    drivers.append({
        "label": "Field completeness",
        "value": f"{fill:.0%}",
        "impact": round(fill * 35, 1),
        "max": 35,
    })

    strength_map = {"full": 1.0, "partial": 0.6, "limited": 0.3, "unavailable": 0.0}
    cap = (sum(strength_map[c["status"]] for c in capabilities) / len(capabilities)) if capabilities else 0.0
    drivers.append({
        "label": "Capabilities powered",
        "value": f"{sum(1 for c in capabilities if c['status'] == 'full')}/{len(capabilities)} full",
        "impact": round(cap * 25, 1),
        "max": 25,
    })

    penalty = 0.0
    for issue in issues:
        if issue.severity == "critical":
            penalty += 6
        elif issue.severity == "warning":
            penalty += 2.5 * (issue.share if issue.share else 0.5)
        else:
            penalty += 0.4
    penalty = min(penalty, 20)
    drivers.append({
        "label": "Consistency (fewer issues is better)",
        "value": f"{len(issues)} issue(s)",
        "impact": round(10 - penalty / 2, 1),
        "max": 10,
    })

    raw = coverage * 30 + fill * 35 + cap * 25 + max(0.0, 10 - penalty / 2)
    score = int(round(max(0, min(100, raw))))
    grade = ("Excellent" if score >= 85 else "Good" if score >= 70
             else "Workable" if score >= 50 else "Limited")
    return score, grade, drivers


def _summary_sentence(score: int, capabilities, issues) -> str:
    full = [c["label"] for c in capabilities if c["status"] == "full"]
    off = [c for c in capabilities if c["status"] == "unavailable"]
    parts: list[str] = []
    if full:
        listed = ", ".join(full[:3]).lower()
        parts.append(f"Your data fully powers {listed}.")
    else:
        parts.append("Your data supports basic prioritisation only.")
    if off:
        missing = sorted({m for c in off for m in c["missing"]})
        pretty = ", ".join(m.replace("_", " ").replace(".", " ") for m in missing[:3])
        parts.append(
            f"{off[0]['label']} is switched off — it needs {pretty}."
        )
    critical = [i for i in issues if i.severity == "critical"]
    if critical:
        parts.append(f"Resolve first: {critical[0].title.lower()}.")
    parts.append(f"Overall data health is {score}/100.")
    return " ".join(parts)
