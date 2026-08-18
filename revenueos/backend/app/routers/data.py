"""Data ingestion, mapping preview, demo loading, data health, GDPR deletion."""

from __future__ import annotations

import time
import uuid
from typing import Any

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..data.cleaning import apply_mapping
from ..data.ingestion import IngestionError, read_table
from ..data.mapping import detect_entity, map_columns, profile_frame
from ..data.schema import ENTITIES, schema_catalogue
from ..demo.generator import generate_demo_dataset
from ..store import ImportRecord, store

router = APIRouter(prefix="/api/data", tags=["data"])

MAX_UPLOAD_BYTES = 60 * 1024 * 1024

# Uploads awaiting confirmation of their column mapping.
_pending: dict[str, dict[str, Any]] = {}
_PENDING_TTL_SECONDS = 3600


def _prune_pending() -> None:
    cutoff = time.time() - _PENDING_TTL_SECONDS
    for key in [k for k, v in _pending.items() if v["createdAt"] < cutoff]:
        _pending.pop(key, None)


@router.get("/schema")
def get_schema() -> dict[str, Any]:
    """What RevenueOS understands — drives the manual mapping UI."""
    return {"entities": schema_catalogue()}


@router.post("/analyse")
async def analyse_upload(
    file: UploadFile = File(...),
    entity: str | None = Form(None),
) -> dict[str, Any]:
    """Parse a file, detect its entity and propose a column mapping.

    Nothing is committed here: the response is a preview the user confirms or
    corrects, which is what keeps low-confidence guesses out of the analytics.
    """
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    try:
        frame, parse_report = read_table(raw, file.filename or "upload.csv")
    except IngestionError as exc:
        raise HTTPException(400, str(exc)) from exc

    profiles = profile_frame(frame)
    if entity and entity in ENTITIES:
        detected, detection_confidence = entity, 1.0
        scores = {entity: 1.0}
    else:
        detected, detection_confidence, scores = detect_entity(frame, profiles)

    mapping = map_columns(frame, detected, profiles)

    _prune_pending()
    token = uuid.uuid4().hex[:16]
    _pending[token] = {
        "frame": frame,
        "entity": detected,
        "parse": parse_report.to_dict(),
        "filename": file.filename or "upload.csv",
        "createdAt": time.time(),
    }

    return {
        "token": token,
        "entity": detected,
        "entityLabel": ENTITIES[detected].label,
        "entityConfidence": round(detection_confidence, 4),
        "entityScores": {k: round(v, 4) for k, v in scores.items()},
        "parse": parse_report.to_dict(),
        "mapping": mapping.to_dict(),
        "preview": _preview(frame),
        "needsReview": [m.column for m in mapping.mappings if m.status != "auto"],
    }


class CommitRequest(BaseModel):
    token: str
    entity: str | None = None
    # canonical field -> source column, as confirmed/corrected by the user
    fieldMap: dict[str, str] | None = None


@router.post("/commit")
def commit_upload(request: CommitRequest) -> dict[str, Any]:
    """Apply a confirmed mapping and load the table into the workspace."""
    _prune_pending()
    pending = _pending.get(request.token)
    if not pending:
        raise HTTPException(
            404, "This upload has expired. Please select the file again.")

    frame: pd.DataFrame = pending["frame"]
    entity = request.entity or pending["entity"]
    if entity not in ENTITIES:
        raise HTTPException(400, f"Unknown data type '{entity}'.")

    if request.fieldMap is not None:
        field_map = {k: v for k, v in request.fieldMap.items() if v}
    else:
        field_map = map_columns(frame, entity).as_field_map()

    unknown = [c for c in field_map.values() if c not in frame.columns]
    if unknown:
        raise HTTPException(400, f"These columns are not in the file: {', '.join(unknown)}")

    clean, clean_report = apply_mapping(frame, entity, field_map)
    if clean.empty:
        raise HTTPException(
            400,
            "After applying the mapping no usable rows remained. Check that the key "
            "column (ID) is mapped correctly.",
        )

    workspace = store.default()
    workspace.set_table(entity, clean)
    if workspace.source != "upload":
        workspace.source = "upload"
    workspace.imports = [i for i in workspace.imports if i.entity != entity]
    workspace.imports.append(ImportRecord(
        entity=entity,
        filename=pending["filename"],
        rows=len(clean),
        columns=len(field_map),
        confidence=map_columns(frame, entity).overall_confidence,
        imported_at=time.time(),
        parse=pending["parse"],
        clean=clean_report.to_dict(),
        mapping={"fieldMap": field_map},
    ))
    _pending.pop(request.token, None)

    workspace.recompute(force=True)
    store.persist(workspace)

    return {
        "entity": entity,
        "rowsLoaded": len(clean),
        "clean": clean_report.to_dict(),
        "workspace": workspace.stats(),
        "dataHealth": workspace.quality,
    }


@router.post("/demo")
def load_demo() -> dict[str, Any]:
    """Load the demo boutique **through the real import pipeline**.

    The generated frames are mapped and cleaned exactly like an uploaded file, so
    the demo exercises the same code path a customer's data would.
    """
    workspace = store.default()
    workspace.reset()

    generated = generate_demo_dataset()
    for entity, frame in generated.items():
        mapping = map_columns(frame, entity)
        clean, clean_report = apply_mapping(frame, entity, mapping.as_field_map())
        workspace.set_table(entity, clean)
        workspace.imports.append(ImportRecord(
            entity=entity,
            filename=f"demo_{entity}.csv",
            rows=len(clean),
            columns=len(mapping.as_field_map()),
            confidence=mapping.overall_confidence,
            imported_at=time.time(),
            parse={"filename": f"demo_{entity}.csv", "rows": len(frame),
                   "columns": len(frame.columns), "encoding": "utf-8", "delimiter": ","},
            clean=clean_report.to_dict(),
            mapping={"fieldMap": mapping.as_field_map()},
        ))

    workspace.name = "Atelier Nova · Milano"
    workspace.source = "demo"
    workspace.recompute(force=True)
    store.persist(workspace)

    return {
        "workspace": workspace.stats(),
        "dataHealth": workspace.quality,
        "opportunities": len(workspace.opportunities),
    }


@router.get("/health")
def data_health() -> dict[str, Any]:
    workspace = store.default()
    workspace.recompute()
    if not workspace.has_data():
        return {"hasData": False, "score": None,
                "summary": "No data loaded yet."}
    return {"hasData": True, **workspace.quality,
            "imports": [i.to_dict() for i in workspace.imports]}


@router.get("/preview/{entity}")
def preview_entity(entity: str, limit: int = 25) -> dict[str, Any]:
    """A look at the cleaned, canonical table — what the engine actually reads."""
    if entity not in ENTITIES:
        raise HTTPException(404, f"Unknown data type '{entity}'.")
    workspace = store.default()
    frame = getattr(workspace, entity)
    if frame is None or frame.empty:
        return {"entity": entity, "rows": [], "columns": [], "total": 0}
    from ..serialisation import frame_to_records
    subset = frame.head(max(1, min(limit, 200)))
    return {
        "entity": entity,
        "label": ENTITIES[entity].label,
        "total": int(len(frame)),
        "columns": [c for c in frame.columns],
        "rows": frame_to_records(subset),
    }


@router.delete("/all")
def delete_all_data() -> dict[str, Any]:
    """GDPR: erase every table and derived artefact for this workspace."""
    workspace = store.delete_data()
    _pending.clear()
    return {"deleted": True, "workspace": workspace.stats()}


@router.delete("/{entity}")
def delete_entity(entity: str) -> dict[str, Any]:
    if entity not in ENTITIES:
        raise HTTPException(404, f"Unknown data type '{entity}'.")
    workspace = store.default()
    workspace.set_table(entity, None)
    workspace.imports = [i for i in workspace.imports if i.entity != entity]
    workspace.recompute(force=True)
    store.persist(workspace)
    return {"deleted": entity, "workspace": workspace.stats()}


def _preview(frame: pd.DataFrame, rows: int = 6) -> dict[str, Any]:
    head = frame.head(rows)
    return {
        "columns": list(frame.columns),
        "rows": [
            [None if pd.isna(v) else str(v) for v in record]
            for record in head.itertuples(index=False, name=None)
        ],
        "totalRows": int(len(frame)),
    }
