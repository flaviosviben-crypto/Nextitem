"""RevenueOS API.

FastAPI application wiring. Every route reads from the workspace's cached
analytics; the expensive pipeline runs once per data change, not per request.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import public_config, settings
from .data.ingestion import IngestionError
from .routers import (
    analyst,
    campaigns,
    customers,
    data,
    insights,
    inventory,
    opportunities,
    overview,
    recommendations,
    scenarios,
    search,
)
from .store import store

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("revenueos")

app = FastAPI(
    title="RevenueOS API",
    version="1.0.0",
    description=(
        "AI Revenue Intelligence for independent fashion boutiques. "
        "Deterministic analytics; Claude is the reasoning and narration layer."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    overview.router, data.router, customers.router, inventory.router,
    recommendations.router, opportunities.router, analyst.router,
    campaigns.router, scenarios.router, insights.router, search.router,
):
    app.include_router(router)


@app.middleware("http")
async def timing(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
    return response


@app.exception_handler(IngestionError)
async def ingestion_error_handler(request: Request, exc: IngestionError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    """Never leak a stack trace to the browser; never take the app down."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong processing that request. "
                           "Your data has not been changed."},
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    workspace = store.default()
    return {
        "status": "ok",
        "version": app.version,
        **public_config(),
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "source": workspace.source,
            "hasData": workspace.has_data(),
        },
    }


@app.get("/api/workspace")
def workspace_info() -> dict[str, Any]:
    workspace = store.default()
    return {**workspace.stats(), "config": public_config()}
