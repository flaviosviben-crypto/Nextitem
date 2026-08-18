"""The AI Analyst endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..ai import client
from ..ai.analyst import ask
from ..config import public_config
from ..store import store

router = APIRouter(prefix="/api/analyst", tags=["analyst"])

SUGGESTIONS = [
    "Who should I contact today?",
    "Which VIPs have not bought recently?",
    "What are my biggest inventory problems?",
    "Which category performs best?",
    "Who should I invite to a private sale?",
    "What should I push this weekend?",
    "Which customers are likely to churn?",
    "What should I do to make €5,000 extra this week?",
]


class Turn(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list)


@router.get("/status")
def status() -> dict[str, Any]:
    workspace = store.default()
    workspace.recompute()
    return {
        **public_config(),
        "hasData": workspace.has_data(),
        "suggestions": SUGGESTIONS,
        "mode": "ai" if client.is_available() else "deterministic",
        "notice": None if client.is_available() else (
            "ANTHROPIC_API_KEY is not set. The analyst still answers from your data "
            "using the same analytics, presented as computed tables rather than prose."
        ),
    }


@router.post("/ask")
def ask_question(request: AskRequest) -> dict[str, Any]:
    workspace = store.default()
    answer = ask(
        workspace,
        request.question,
        [{"role": t.role, "content": t.content} for t in request.history],
    )
    return answer.to_dict()
