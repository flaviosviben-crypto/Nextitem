"""RevenueOS API."""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import analyst, campaigns, customers, data, opportunities, products, scenarios
from .workspace import workspace

app = FastAPI(
    title="RevenueOS API",
    description="AI revenue intelligence for fashion boutiques.",
    version="1.0.0",
)

origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (data.router, customers.router, products.router, opportunities.router,
               analyst.router, campaigns.router, scenarios.router):
    app.include_router(router, prefix="/api")


@app.on_event("startup")
def _startup() -> None:
    """Restore the last workspace so a restart does not lose the boutique's data."""
    if not workspace.is_loaded:
        workspace.load()


@app.get("/api/health")
def health() -> dict[str, object]:
    from .ai.client import status as ai_status
    return {
        "status": "ok",
        "loaded": workspace.is_loaded,
        "source": workspace.source,
        "computed_at": workspace.computed_at,
        "ai": ai_status(),
    }
