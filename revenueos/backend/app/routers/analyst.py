"""AI Analyst and executive insights.

Not part of the V1 navigation, but kept mounted: the analytics tool-runner is
real intelligence and stays available by API for pilots that ask for it.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..ai.client import status as ai_status

router = APIRouter(tags=["analyst"])


class Turn(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = []


@router.get("/ai/status")
def status() -> dict[str, Any]:
    return ai_status()


@router.post("/ai/ask")
def ask(payload: AskRequest) -> dict[str, Any]:
    history = [{"role": t.role, "content": t.content} for t in payload.history]
    # Imported here, not at module scope: this pulls in the Anthropic SDK,
    # which is the single largest cost of starting the API and is needed only
    # when an AI surface is actually called. Paying it on every boot delays
    # the port opening, which is what a platform waits for.
    from ..ai import analyst as analyst_ai

    return analyst_ai.ask(payload.question.strip(), history)


@router.get("/ai/brief")
def brief() -> dict[str, Any]:
    from ..ai import analyst as analyst_ai

    return analyst_ai.executive_brief()
