"""Workspace state: the single place raw tables become computed intelligence.

A *workspace* holds the three canonical tables plus every derived artefact. The
expensive pipeline (metrics → RFM → inventory → matching context →
opportunities) runs once per data change and is then cached, so page loads are
reads rather than recomputations.

Persistence is SQLite + Parquet-in-blob today; the access is confined to this
module so a swap to Postgres/Supabase touches nothing else.
"""

from __future__ import annotations

import io
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .analytics.customer_scoring import build_customer_metrics
from .analytics.inventory import build_inventory_metrics
from .analytics.matching import MatchingContext, build_context
from .analytics.opportunities import generate_opportunities, opportunity_totals
from .analytics.rfm import compute_rfm
from .config import settings
from .data.validation import analyse_quality

TABLES = ("customers", "transactions", "inventory")

_lock = threading.RLock()


@dataclass
class ImportRecord:
    entity: str
    filename: str
    rows: int
    columns: int
    confidence: float
    imported_at: float
    parse: dict[str, Any] = field(default_factory=dict)
    clean: dict[str, Any] = field(default_factory=dict)
    mapping: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "filename": self.filename,
            "rows": self.rows,
            "columns": self.columns,
            "confidence": round(self.confidence, 4),
            "importedAt": self.imported_at,
            "parse": self.parse,
            "clean": self.clean,
            "mapping": self.mapping,
        }


@dataclass
class Workspace:
    id: str
    name: str
    source: str = "empty"          # empty | demo | upload
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    customers: pd.DataFrame | None = None
    transactions: pd.DataFrame | None = None
    inventory: pd.DataFrame | None = None

    imports: list[ImportRecord] = field(default_factory=list)

    # derived
    customer_metrics: pd.DataFrame | None = None
    inventory_metrics: pd.DataFrame | None = None
    matching_context: MatchingContext | None = None
    opportunities: list[dict[str, Any]] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)
    pipeline_ms: float | None = None
    _dirty: bool = True

    # user-owned state that survives recomputation
    pipeline_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    campaigns: list[dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    def set_table(self, entity: str, frame: pd.DataFrame) -> None:
        setattr(self, entity, frame)
        self._dirty = True
        self.updated_at = time.time()

    def has_data(self) -> bool:
        return any(
            getattr(self, table) is not None and not getattr(self, table).empty
            for table in TABLES
        )

    def tables(self) -> dict[str, pd.DataFrame | None]:
        return {t: getattr(self, t) for t in TABLES}

    # ------------------------------------------------------------------ #
    def recompute(self, force: bool = False) -> None:
        """Run the full analytics pipeline. Idempotent and cached."""
        with _lock:
            if not self._dirty and not force:
                return
            started = time.perf_counter()

            self.quality = analyse_quality(self.tables())

            if self.customers is None and (self.transactions is None or self.transactions.empty):
                self.customer_metrics = None
                self.inventory_metrics = None
                self.matching_context = None
                self.opportunities = []
                self._dirty = False
                return

            metrics = build_customer_metrics(
                self.customers if self.customers is not None else pd.DataFrame(),
                self.transactions,
            )
            if not metrics.empty:
                metrics = compute_rfm(metrics)
            self.customer_metrics = metrics

            self.inventory_metrics = (
                build_inventory_metrics(self.inventory, self.transactions)
                if self.inventory is not None and not self.inventory.empty else None
            )

            if self.inventory_metrics is not None and not self.inventory_metrics.empty:
                self.matching_context = build_context(
                    self.inventory_metrics,
                    self.customer_metrics if self.customer_metrics is not None else pd.DataFrame(),
                )
            else:
                self.matching_context = None

            if (self.matching_context is not None and self.customer_metrics is not None
                    and not self.customer_metrics.empty):
                self.opportunities = generate_opportunities(
                    self.customer_metrics, self.inventory_metrics,
                    self.matching_context, self.transactions,
                )
            elif self.customer_metrics is not None and not self.customer_metrics.empty:
                self.opportunities = generate_opportunities(
                    self.customer_metrics, pd.DataFrame(),
                    build_context(pd.DataFrame(), self.customer_metrics),
                    self.transactions,
                )
            else:
                self.opportunities = []

            # re-attach any pipeline status the user has set
            for opp in self.opportunities:
                state = self.pipeline_status.get(opp["id"])
                if state:
                    opp["status"] = state.get("status", "new")
                    opp["statusNote"] = state.get("note")
                    opp["statusUpdatedAt"] = state.get("updatedAt")
                else:
                    opp["status"] = "new"

            self.pipeline_ms = round((time.perf_counter() - started) * 1000, 1)
            self._dirty = False

    def opportunity_summary(self) -> dict[str, Any]:
        return opportunity_totals(self.opportunities)

    def stats(self) -> dict[str, Any]:
        self.recompute()
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "hasData": self.has_data(),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "counts": {
                "customers": int(len(self.customers)) if self.customers is not None else 0,
                "transactions": int(len(self.transactions)) if self.transactions is not None else 0,
                "products": int(len(self.inventory)) if self.inventory is not None else 0,
                "opportunities": len(self.opportunities),
            },
            "dataHealth": self.quality.get("score"),
            "dataGrade": self.quality.get("grade"),
            "pipelineMs": self.pipeline_ms,
            "imports": [i.to_dict() for i in self.imports],
        }

    def reset(self) -> None:
        with _lock:
            for table in TABLES:
                setattr(self, table, None)
            self.imports = []
            self.customer_metrics = None
            self.inventory_metrics = None
            self.matching_context = None
            self.opportunities = []
            self.quality = {}
            self.pipeline_status = {}
            self.campaigns = []
            self.source = "empty"
            self._dirty = True
            self.updated_at = time.time()


# --------------------------------------------------------------------------- #
# registry + persistence
# --------------------------------------------------------------------------- #
class WorkspaceStore:
    """In-memory registry with SQLite durability across restarts."""

    def __init__(self, db_path=None) -> None:
        self.db_path = str(db_path or settings.db_path)
        self._workspaces: dict[str, Workspace] = {}
        self._default_id: str | None = None
        self._init_db()
        self._load_all()

    # -- sqlite -------------------------------------------------------- #
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    imports TEXT,
                    pipeline_status TEXT,
                    campaigns TEXT
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS workspace_tables (
                    workspace_id TEXT NOT NULL,
                    entity TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    PRIMARY KEY (workspace_id, entity)
                )"""
            )

    def _load_all(self) -> None:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT id, name, source, created_at, updated_at, imports, "
                    "pipeline_status, campaigns FROM workspaces ORDER BY created_at"
                ).fetchall()
        except sqlite3.Error:
            return

        for row in rows:
            workspace = Workspace(
                id=row[0], name=row[1], source=row[2],
                created_at=row[3], updated_at=row[4],
            )
            workspace.imports = [
                ImportRecord(**{
                    "entity": r["entity"], "filename": r["filename"], "rows": r["rows"],
                    "columns": r["columns"], "confidence": r["confidence"],
                    "imported_at": r.get("importedAt", time.time()),
                    "parse": r.get("parse", {}), "clean": r.get("clean", {}),
                    "mapping": r.get("mapping", {}),
                })
                for r in json.loads(row[5] or "[]")
            ]
            workspace.pipeline_status = json.loads(row[6] or "{}")
            workspace.campaigns = json.loads(row[7] or "[]")

            with self._connect() as conn:
                for entity, payload in conn.execute(
                    "SELECT entity, payload FROM workspace_tables WHERE workspace_id = ?",
                    (workspace.id,),
                ):
                    try:
                        setattr(workspace, entity, pd.read_parquet(io.BytesIO(payload)))
                    except Exception:
                        continue

            self._workspaces[workspace.id] = workspace
            if self._default_id is None:
                self._default_id = workspace.id

    def persist(self, workspace: Workspace) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO workspaces (id, name, source, created_at, updated_at,
                        imports, pipeline_status, campaigns)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name, source=excluded.source,
                        updated_at=excluded.updated_at, imports=excluded.imports,
                        pipeline_status=excluded.pipeline_status,
                        campaigns=excluded.campaigns""",
                    (workspace.id, workspace.name, workspace.source, workspace.created_at,
                     workspace.updated_at, json.dumps([i.to_dict() for i in workspace.imports]),
                     json.dumps(workspace.pipeline_status), json.dumps(workspace.campaigns)),
                )
                for entity in TABLES:
                    frame = getattr(workspace, entity)
                    if frame is None or frame.empty:
                        conn.execute(
                            "DELETE FROM workspace_tables WHERE workspace_id = ? AND entity = ?",
                            (workspace.id, entity),
                        )
                        continue
                    buffer = io.BytesIO()
                    _parquet_safe(frame).to_parquet(buffer, index=False)
                    conn.execute(
                        """INSERT INTO workspace_tables (workspace_id, entity, payload)
                           VALUES (?, ?, ?)
                           ON CONFLICT(workspace_id, entity) DO UPDATE SET payload=excluded.payload""",
                        (workspace.id, entity, buffer.getvalue()),
                    )
        except Exception:
            # Persistence is a convenience: never take the API down for it.
            pass

    # -- registry ------------------------------------------------------ #
    def default(self) -> Workspace:
        with _lock:
            if self._default_id and self._default_id in self._workspaces:
                return self._workspaces[self._default_id]
            workspace = self.create("My Boutique")
            self._default_id = workspace.id
            return workspace

    def create(self, name: str) -> Workspace:
        workspace = Workspace(id=uuid.uuid4().hex[:12], name=name)
        with _lock:
            self._workspaces[workspace.id] = workspace
            if self._default_id is None:
                self._default_id = workspace.id
        self.persist(workspace)
        return workspace

    def get(self, workspace_id: str | None = None) -> Workspace:
        if not workspace_id:
            return self.default()
        with _lock:
            if workspace_id in self._workspaces:
                return self._workspaces[workspace_id]
        raise KeyError(f"Workspace '{workspace_id}' not found")

    def list(self) -> list[Workspace]:
        with _lock:
            return list(self._workspaces.values())

    def delete_data(self, workspace_id: str | None = None) -> Workspace:
        workspace = self.get(workspace_id)
        workspace.reset()
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM workspace_tables WHERE workspace_id = ?",
                             (workspace.id,))
        except sqlite3.Error:
            pass
        self.persist(workspace)
        return workspace


def _parquet_safe(frame: pd.DataFrame) -> pd.DataFrame:
    """List/dict columns survive a JSON round-trip better than pyarrow guessing."""
    out = frame.copy()
    for column in out.columns:
        sample = out[column].dropna()
        if not sample.empty and isinstance(sample.iloc[0], (list, dict)):
            out[column] = out[column].map(lambda v: json.dumps(v) if isinstance(v, (list, dict)) else v)
    return out


store = WorkspaceStore()
