"""The in-process workspace: holds a boutique's data and its computed analytics.

One pipeline run happens on import; every endpoint then reads cached results.
Recomputing on each request would be wasteful and would make the dashboard feel
slow on a 100k-row dataset.

Persistence is a single JSON snapshot on disk (SQLite/Postgres is the obvious
next step — see README). State is deliberately isolated behind this class so
swapping the store does not touch the analytics or the API.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .analytics import (
    compliance,
    customer_scoring,
    inventory as inventory_analytics,
    opportunities as opp_engine,
    performance,
    segmentation,
)
from .data import cleaning, ingestion, mapping as mapping_mod, validation
from .data.schema import Kind
from .demo import generator

DATA_DIR = Path(__file__).resolve().parent.parent / "storage"
SNAPSHOT = DATA_DIR / "workspace.json"


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Not serialisable: {type(obj)}")


@dataclass
class ImportRecord:
    kind: str
    filename: str
    rows: int
    mapped_fields: int
    at: str
    delimiter: str
    encoding: str
    issues: list[str] = field(default_factory=list)


class Workspace:
    """Everything RevenueOS knows about one boutique."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.reset()

    # ------------------------------------------------------------- lifecycle --
    def reset(self) -> None:
        with self._lock:
            self.customers_raw: list[dict[str, Any]] = []
            self.transactions_raw: list[dict[str, Any]] = []
            self.inventory_raw: list[dict[str, Any]] = []
            self.mappings: dict[str, list[dict[str, Any]]] = {}
            self.imports: list[ImportRecord] = []
            self.source: str = "empty"
            self.pending: dict[str, Any] | None = None
            self.profiles: list[dict[str, Any]] = []
            self.products: list[dict[str, Any]] = []
            self.opportunities: list[dict[str, Any]] = []
            self.pipeline: list[dict[str, Any]] = []
            self.quality: dict[str, Any] | None = None
            self.summary: dict[str, Any] = {}
            self.performance: dict[str, Any] = {}
            # Every advisor decision is written down. Outreach without an audit
            # trail is not something a luxury house will put its name to.
            self.audit_log: list[dict[str, Any]] = []
            # Lifecycle boundaries are a setting, not a law of retail: a jeweller
            # and a denim store do not share a definition of "overdue".
            self.lifecycle_thresholds: dict[str, float] = dict(
                segmentation.LIFECYCLE_THRESHOLDS)
            self.computed_at: str | None = None

    @property
    def is_loaded(self) -> bool:
        return bool(self.profiles or self.products)

    # ---------------------------------------------------------------- import --
    def stage_file(self, kind: Kind, filename: str, raw: bytes) -> dict[str, Any]:
        """Parse and auto-map a file, but do not commit it yet."""
        parsed = ingestion.parse_csv(raw, filename)
        if not parsed.rows:
            return {
                "ok": False,
                "kind": kind,
                "error": "; ".join(parsed.issues) or "No data rows found in this file.",
                "parse": parsed.to_dict(),
            }
        detected = mapping_mod.detect_mapping(kind, parsed.headers, parsed.rows)
        with self._lock:
            self.pending = {
                "kind": kind,
                "filename": filename,
                "parsed": parsed,
                "mappings": detected,
            }
        return {
            "ok": True,
            "kind": kind,
            "filename": filename,
            "parse": parsed.to_dict(),
            "mappings": [m.to_dict() for m in detected],
            "ready": self._mapping_is_sufficient(kind, detected),
            "required": _REQUIRED[kind],
        }

    def update_pending_mapping(self, overrides: dict[str, str | None]) -> dict[str, Any]:
        with self._lock:
            if not self.pending:
                return {"ok": False, "error": "No file is waiting to be mapped."}
            self.pending["mappings"] = mapping_mod.apply_overrides(self.pending["mappings"], overrides)
            kind = self.pending["kind"]
            return {
                "ok": True,
                "kind": kind,
                "mappings": [m.to_dict() for m in self.pending["mappings"]],
                "ready": self._mapping_is_sufficient(kind, self.pending["mappings"]),
                "required": _REQUIRED[kind],
            }

    def commit_pending(self) -> dict[str, Any]:
        with self._lock:
            if not self.pending:
                return {"ok": False, "error": "No file is waiting to be imported."}
            kind: Kind = self.pending["kind"]
            parsed = self.pending["parsed"]
            maps = self.pending["mappings"]
            missing = self._missing_required(kind, maps)
            if missing:
                return {"ok": False, "error": "Map these fields first: " + ", ".join(missing),
                        "missing": missing}

            field_map = mapping_mod.mapping_to_dict(maps)
            records = cleaning.BUILDERS[kind](parsed.rows, field_map)
            if not records:
                return {"ok": False,
                        "error": "No usable rows after mapping. Check the mapped columns."}

            setattr(self, f"{kind}_raw", records)
            self.mappings[kind] = [m.to_dict() for m in maps]
            self.imports.insert(0, ImportRecord(
                kind=kind, filename=self.pending["filename"], rows=len(records),
                mapped_fields=len(field_map),
                at=datetime.utcnow().isoformat(timespec="seconds"),
                delimiter="TAB" if parsed.delimiter == "\t" else parsed.delimiter,
                encoding=parsed.encoding, issues=parsed.issues,
            ))
            self.imports = self.imports[:20]
            self.source = "uploaded"
            self.pending = None

        self.recompute()
        return {"ok": True, "kind": kind, "rows": len(getattr(self, f"{kind}_raw")),
                "summary": self.summary, "quality": self.quality}

    def _missing_required(self, kind: Kind, maps) -> list[str]:
        present = {m.field for m in maps if m.field}
        return [f for f in _REQUIRED[kind] if f not in present]

    def _mapping_is_sufficient(self, kind: Kind, maps) -> bool:
        return not self._missing_required(kind, maps)

    # ------------------------------------------------------------------ demo --
    def load_demo(self, seed: int = 7) -> dict[str, Any]:
        """Load the demo boutique *through the real import path*.

        Demo records are rendered to strings and re-parsed exactly like an
        uploaded CSV, so the demo exercises ingestion, mapping and cleaning
        rather than bypassing them.
        """
        data = generator.generate(seed=seed)
        with self._lock:
            self.reset()
            for kind in ("customers", "transactions", "inventory"):
                rows = generator.to_csv_rows(data[kind])
                headers = list(rows[0].keys())
                detected = mapping_mod.detect_mapping(kind, headers, rows)
                field_map = mapping_mod.mapping_to_dict(detected)
                records = cleaning.BUILDERS[kind](rows, field_map)
                setattr(self, f"{kind}_raw", records)
                self.mappings[kind] = [m.to_dict() for m in detected]
                self.imports.insert(0, ImportRecord(
                    kind=kind, filename=f"demo_{kind}.csv", rows=len(records),
                    mapped_fields=len(field_map),
                    at=datetime.utcnow().isoformat(timespec="seconds"),
                    delimiter=",", encoding="utf-8", issues=[],
                ))
            self.source = "demo"
        self.recompute()
        return {"ok": True, "summary": self.summary, "quality": self.quality}

    # --------------------------------------------------------------- compute --
    def recompute(self) -> None:
        with self._lock:
            customers = self.customers_raw
            transactions = self.transactions_raw
            inventory = self.inventory_raw

            profiles = customer_scoring.build_profiles(customers, transactions)
            # Value and lifecycle are resolved separately, then eligibility, so the
            # opportunity engine never has to guess at any of the three.
            profiles = segmentation.classify(profiles, self.lifecycle_thresholds)
            profiles = compliance.apply(profiles)
            products = inventory_analytics.build_product_stats(inventory, transactions)
            quality = validation.analyse(customers, transactions, inventory)
            opps = opp_engine.detect(profiles, products, transactions)
            # Today's workload is decided once, here, and stamped onto every
            # detected opportunity. Screens read that stamp; none of them gets to
            # decide separately what "today" means.
            today = opp_engine.prioritize(opps)
            opp_counts = opp_engine.counts(opps)

            base = customer_scoring.summarize_base(profiles)
            inv = inventory_analytics.inventory_summary(products)
            actionable = [o for o in opps if o["contactable"]]
            # The headline is what today's list is realistically worth — the sum
            # of influenced value across the opportunities actually recommended,
            # not across everything detected.
            revenue_opportunity = sum(o.get("influenced_value") or 0 for o in today)

            self.profiles = profiles
            self.products = products
            self.opportunities = opps
            self.quality = quality.to_dict()
            self.pipeline = _merge_pipeline(self.pipeline, opp_engine.pipeline_defaults(opps))
            self.performance = performance.report(self.pipeline, transactions)
            self.summary = {
                "source": self.source,
                "customers": base,
                "inventory": inv,
                "segments": segmentation.summarize(profiles),
                "compliance": compliance.summarize(profiles),
                "revenue_opportunity": round(revenue_opportunity, 2),
                # One vocabulary, used everywhere: detected is the universe the
                # engine found, prioritized is what it recommends working today.
                "opportunities": opp_counts,
                "actionable_opportunities": len(actionable),
                "suppressed_opportunities": len(opps) - len(actionable),
                "high_confidence_matches": sum(
                    1 for o in opps if ((o.get("product") or {}).get("match_pct") or 0) >= 75),
                "customers_to_contact": len({o["customer_id"] for o in today}),
                "data_health": quality.score,
                "counts": {
                    "customers": len(profiles),
                    "transactions": len(transactions),
                    "products": len(products),
                },
            }
            self.computed_at = datetime.utcnow().isoformat(timespec="seconds")
        self.save()

    def refresh_performance(self) -> None:
        """Recompute the performance report after an advisor acts.

        Cheap enough to run on every decision, and it means the Performance page
        never lags behind what the advisor just did.
        """
        with self._lock:
            self.performance = performance.report(self.pipeline, self.transactions_raw)

    def audit(self, row_id: str, status: str, note: str | None = None,
              actor: str = "advisor") -> None:
        with self._lock:
            self.audit_log.insert(0, {
                "at": datetime.utcnow().isoformat(timespec="seconds"),
                "action_id": row_id,
                "status": status,
                "note": note,
                "actor": actor,
            })
            self.audit_log = self.audit_log[:2000]

    # ------------------------------------------------------------- accessors --
    def profile(self, customer_id: str) -> dict[str, Any] | None:
        return next((p for p in self.profiles if p["customer_id"] == customer_id), None)

    def product(self, sku: str) -> dict[str, Any] | None:
        return next((p for p in self.products if str(p["sku"]) == str(sku)), None)

    def customer_transactions(self, customer_id: str) -> list[dict[str, Any]]:
        rows = [t for t in self.transactions_raw if t["customer_id"] == customer_id]
        return sorted(rows, key=lambda t: t.get("date") or date.min, reverse=True)

    # ----------------------------------------------------------- persistence --
    def save(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "source": self.source,
                "customers_raw": self.customers_raw,
                "transactions_raw": self.transactions_raw,
                "inventory_raw": self.inventory_raw,
                "mappings": self.mappings,
                "imports": [i.__dict__ for i in self.imports],
                "pipeline": self.pipeline,
                "lifecycle_thresholds": self.lifecycle_thresholds,
                "audit_log": self.audit_log,
            }
            SNAPSHOT.write_text(json.dumps(payload, default=_json_default))
        except OSError:
            pass  # persistence is best-effort; the app still works in memory

    def load(self) -> bool:
        if not SNAPSHOT.exists():
            return False
        try:
            payload = json.loads(SNAPSHOT.read_text())
        except (OSError, json.JSONDecodeError):
            return False

        from .data.values import parse_date

        def revive(records: list[dict[str, Any]], date_fields: tuple[str, ...]) -> list[dict[str, Any]]:
            for r in records:
                for f in date_fields:
                    if r.get(f):
                        r[f] = parse_date(r[f])
            return records

        with self._lock:
            self.reset()
            self.customers_raw = revive(payload.get("customers_raw", []),
                                        ("last_purchase_date", "first_purchase_date", "birth_date"))
            self.transactions_raw = revive(payload.get("transactions_raw", []), ("date",))
            self.inventory_raw = revive(payload.get("inventory_raw", []), ("arrival_date",))
            self.mappings = payload.get("mappings", {})
            self.imports = [ImportRecord(**i) for i in payload.get("imports", [])]
            self.pipeline = payload.get("pipeline", [])
            self.lifecycle_thresholds = {**segmentation.LIFECYCLE_THRESHOLDS,
                                         **payload.get("lifecycle_thresholds", {})}
            self.audit_log = payload.get("audit_log", [])
            self.source = payload.get("source", "restored")
        if self.customers_raw or self.transactions_raw or self.inventory_raw:
            self.recompute()
            return True
        return False

    def clear(self) -> None:
        """GDPR: forget everything, on disk as well as in memory."""
        with self._lock:
            self.reset()
        try:
            SNAPSHOT.unlink(missing_ok=True)
        except OSError:
            pass


_REQUIRED: dict[str, list[str]] = {
    "customers": ["customer_id"],
    "transactions": ["customer_id", "line_total"],
    "inventory": ["sku"],
}


def _merge_pipeline(existing: list[dict[str, Any]], fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep advisor decisions when opportunities are recomputed."""
    status_by_id = {row["id"]: row for row in existing}
    merged = []
    for row in fresh:
        prior = status_by_id.get(row["id"])
        if prior:
            row["status"] = prior.get("status", "New")
            row["note"] = prior.get("note")
            row["updated_at"] = prior.get("updated_at")
        merged.append(row)
    # Preserve rows the advisor has acted on even if the opportunity faded.
    fresh_ids = {r["id"] for r in fresh}
    for row in existing:
        if row["id"] not in fresh_ids and row.get("status") not in (None, "New"):
            merged.append(row)
    return merged


workspace = Workspace()
