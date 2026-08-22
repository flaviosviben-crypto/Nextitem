"""Data import, mapping, health and GDPR controls."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..data.schema import SCHEMAS, schema_payload
from ..workspace import workspace

router = APIRouter(tags=["data"])

MAX_UPLOAD_BYTES = 80 * 1024 * 1024


class MappingUpdate(BaseModel):
    overrides: dict[str, str | None]


class DemoRequest(BaseModel):
    seed: int = 7


@router.get("/summary")
def summary() -> dict[str, Any]:
    if not workspace.is_loaded:
        return {"loaded": False, "source": workspace.source}
    return {"loaded": True, "computed_at": workspace.computed_at, **workspace.summary}


@router.get("/data/schema/{kind}")
def schema(kind: str) -> dict[str, Any]:
    if kind not in SCHEMAS:
        raise HTTPException(404, f"Unknown data kind '{kind}'.")
    return {"kind": kind, "fields": schema_payload(kind)}


@router.post("/data/upload")
async def upload(kind: str = Form(...), file: UploadFile = File(...)) -> dict[str, Any]:
    """Parse and auto-map a CSV. Nothing is committed until /data/confirm."""
    if kind not in SCHEMAS:
        raise HTTPException(400, f"Unknown data kind '{kind}'. Use customers, transactions or inventory.")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "The uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than the 80 MB import limit.")
    result = workspace.stage_file(kind, file.filename or "upload.csv", raw)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Could not read this file."))
    return result


@router.post("/data/mapping")
def update_mapping(payload: MappingUpdate) -> dict[str, Any]:
    result = workspace.update_pending_mapping(payload.overrides)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "No pending import."))
    return result


@router.post("/data/confirm")
def confirm() -> dict[str, Any]:
    result = workspace.commit_pending()
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Import failed."))
    return result


@router.post("/data/demo")
def load_demo(payload: DemoRequest | None = None) -> dict[str, Any]:
    return workspace.load_demo(seed=(payload.seed if payload else 7))


@router.get("/data/quality")
def quality() -> dict[str, Any]:
    if not workspace.is_loaded:
        raise HTTPException(404, "No dataset loaded.")
    return workspace.quality or {}


@router.get("/data/imports")
def imports() -> dict[str, Any]:
    return {
        "source": workspace.source,
        "imports": [i.__dict__ for i in workspace.imports],
        "mappings": workspace.mappings,
        "counts": {
            "customers": len(workspace.customers_raw),
            "transactions": len(workspace.transactions_raw),
            "inventory": len(workspace.inventory_raw),
        },
    }


@router.delete("/data")
def clear() -> dict[str, Any]:
    """Delete everything — in memory and on disk. GDPR right to erasure."""
    workspace.clear()
    return {"ok": True, "message": "All imported data has been deleted from this workspace."}
