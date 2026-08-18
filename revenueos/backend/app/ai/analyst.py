"""The AI Analyst: question in, grounded answer plus supporting data out.

    USER QUESTION
        ↓  intent detection (Claude's tool choice, or a deterministic router)
    ANALYTICS TOOLS  ← the only source of numbers
        ↓  result dataset
    LLM INTERPRETATION  (narration only)
        ↓
    ANSWER + the table it was derived from

The deterministic router is not a degraded imitation of the AI path — it runs the
*same* analytics tools. Without an API key the product still answers questions
correctly; it simply presents the results with composed sentences instead of
generated prose, and says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from . import client
from .context_builder import workspace_overview
from .prompts import analyst_system
from .tools import TOOL_SPECS, run_tool

MAX_TOOL_ROUNDS = 4


@dataclass
class AnalystAnswer:
    answer: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    data: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "ai"                  # "ai" | "deterministic"
    notice: str | None = None
    usage: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "toolCalls": self.tool_calls,
            "data": self.data,
            "mode": self.mode,
            "notice": self.notice,
            "usage": self.usage,
        }


def ask(workspace, question: str,
        history: list[dict[str, str]] | None = None) -> AnalystAnswer:
    """Answer a question about the workspace's data."""
    question = (question or "").strip()
    if not question:
        return AnalystAnswer(answer="Ask me something about your customers, stock or sales.",
                             mode="deterministic")

    workspace.recompute()
    if not workspace.has_data():
        return AnalystAnswer(
            answer=("There is no data loaded yet. Load the demo boutique or upload your "
                    "customer, sales and stock exports, and I can answer this."),
            mode="deterministic",
        )

    if not client.is_available():
        return _deterministic_answer(workspace, question)

    try:
        return _ai_answer(workspace, question, history or [])
    except client.AIUnavailable as exc:
        fallback = _deterministic_answer(workspace, question)
        fallback.notice = (
            f"Narrative AI is unavailable ({exc}). The figures below are still computed "
            "from your data."
        )
        return fallback


# --------------------------------------------------------------------------- #
def _ai_answer(workspace, question: str, history: list[dict[str, str]]) -> AnalystAnswer:
    system = analyst_system(workspace_overview(workspace), settings.currency)

    messages: list[dict[str, Any]] = []
    for turn in history[-6:]:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    executed: list[dict[str, Any]] = []
    datasets: list[dict[str, Any]] = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.complete(system=system, messages=messages, tools=TOOL_SPECS)

        if not response.tool_calls:
            return AnalystAnswer(
                answer=response.text or "I could not produce an answer for that.",
                tool_calls=executed, data=datasets, mode="ai", usage=response.usage,
            )

        assistant_content: list[dict[str, Any]] = []
        if response.text:
            assistant_content.append({"type": "text", "text": response.text})
        for call in response.tool_calls:
            assistant_content.append({
                "type": "tool_use", "id": call["id"],
                "name": call["name"], "input": call["input"],
            })
        messages.append({"role": "assistant", "content": assistant_content})

        results: list[dict[str, Any]] = []
        for call in response.tool_calls:
            result = run_tool(workspace, call["name"], call["input"])
            executed.append({"tool": call["name"], "input": call["input"]})
            datasets.append({"tool": call["name"], "result": result})
            results.append({
                "type": "tool_result", "tool_use_id": call["id"],
                "content": _serialise(result),
            })
        messages.append({"role": "user", "content": results})

    # Ran out of rounds: ask for a final answer with no further tools.
    final = client.complete(system=system, messages=messages, tools=None)
    return AnalystAnswer(
        answer=final.text or "I gathered the data but could not summarise it.",
        tool_calls=executed, data=datasets, mode="ai", usage=final.usage,
    )


def _serialise(result: dict[str, Any]) -> str:
    import json
    return json.dumps(result, default=str)[:60000]


# --------------------------------------------------------------------------- #
# deterministic path
# --------------------------------------------------------------------------- #
_INTENTS: list[tuple[str, tuple[str, ...]]] = [
    ("contact_today", ("contact today", "who should i contact", "who to call", "chi contattare",
                       "who should i call", "priorit")),
    ("churn", ("churn", "at risk", "losing", "lapse", "abbandon", "rischio")),
    ("vip_inactive", ("vip", "champion", "best customer", "top customer", "migliori clienti")),
    ("inventory_problem", ("inventory problem", "dead stock", "stuck", "slow moving",
                           "at risk stock", "giacenz", "magazzino", "invenduto")),
    ("push_products", ("push", "promote", "what should i sell", "spingere", "weekend")),
    ("private_sale", ("private sale", "invite", "vendita privata", "evento")),
    ("customer_products", ("recommend to", "what should i recommend", "cosa consigliare",
                           "suggest for")),
    ("product_customers", ("who would buy", "who should i call about", "chi comprerebbe",
                           "best customers for")),
    ("category_performance", ("category", "categoria", "best performing", "brand performance",
                              "which brand", "performs best")),
    ("sales_trend", ("sales fall", "sales drop", "revenue trend", "why did sales",
                     "andamento", "vendite")),
    ("segments", ("segment", "segmenti", "breakdown of customers")),
]


def _detect_intent(question: str) -> str:
    text = question.lower()
    for intent, keys in _INTENTS:
        if any(key in text for key in keys):
            return intent
    if "reactivat" in text or "dormant" in text or "sleeping" in text:
        return "churn"
    if "stock" in text or "product" in text:
        return "inventory_problem"
    return "opportunities"


def _deterministic_answer(workspace, question: str) -> AnalystAnswer:
    intent = _detect_intent(question)
    notice = (
        "Answered from computed analytics. Set ANTHROPIC_API_KEY to get conversational "
        "answers over the same figures."
    )

    plan: list[tuple[str, dict[str, Any]]] = {
        "contact_today": [("get_opportunities", {"limit": 6})],
        "churn": [("find_customers", {"overdueOnly": True, "sortBy": "churn_risk", "limit": 12})],
        "vip_inactive": [("find_customers", {"segment": "VIP", "sortBy": "days_overdue", "limit": 10}),
                         ("find_customers", {"segment": "Champions", "sortBy": "days_overdue", "limit": 10})],
        "inventory_problem": [("find_products", {"status": "Dead Stock", "sortBy": "retail_value", "limit": 10}),
                              ("get_inventory_summary", {})],
        "push_products": [("find_products", {"sortBy": "risk_score", "limit": 10})],
        "private_sale": [("get_opportunities", {"kind": "private_sale", "limit": 3}),
                         ("find_customers", {"segment": "Discount Driven", "limit": 15})],
        "category_performance": [("get_performance", {"dimension": "category"})],
        "sales_trend": [("get_performance", {"dimension": "category", "includeTrend": True})],
        "segments": [("get_segments", {})],
        "customer_products": [("find_customers", {"sortBy": "customer_score", "limit": 5})],
        "product_customers": [("find_products", {"maxDaysInStock": 45, "limit": 5})],
        "opportunities": [("get_opportunities", {"limit": 6})],
    }.get(intent, [("get_opportunities", {"limit": 6})])

    datasets: list[dict[str, Any]] = []
    executed: list[dict[str, Any]] = []
    for name, payload in plan:
        result = run_tool(workspace, name, payload)
        executed.append({"tool": name, "input": payload})
        datasets.append({"tool": name, "result": result})

    return AnalystAnswer(
        answer=_compose(intent, datasets),
        tool_calls=executed, data=datasets, mode="deterministic", notice=notice,
    )


def _money(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "not enough information"
    return f"€{number:,.0f}"


def _compose(intent: str, datasets: list[dict[str, Any]]) -> str:
    """Compose a factual answer from tool output. Every claim is a returned value."""
    first = datasets[0]["result"] if datasets else {}

    if intent in {"contact_today", "opportunities", "private_sale"}:
        opportunities = first.get("opportunities") or []
        if not opportunities:
            return "No opportunities were detected in the current data."
        totals = first.get("totals") or {}
        lines = [
            f"**{len(opportunities)} priorities** out of {totals.get('count', len(opportunities))} "
            f"detected opportunities, worth {_money(totals.get('expectedValue'))} in "
            "probability-weighted revenue.",
            "",
            "| Priority | Why | Suggested action | Est. value | Score |",
            "| --- | --- | --- | --- | --- |",
        ]
        for opp in opportunities[:6]:
            lines.append(
                f"| {opp['title']} | {opp['why'][:110]} | {opp['action'][:70]} | "
                f"{_money(opp['estimatedValue'])} | {opp['score']:.0f}/100 |"
            )
        return "\n".join(lines)

    if intent in {"churn", "vip_inactive", "customer_products"}:
        rows = first.get("rows") or []
        if not rows:
            return "No customers matched that criteria in the current data."
        lines = [
            f"**{first.get('matchedCustomers', len(rows))} customers** match. The most urgent:",
            "",
            "| Customer | Segment | Lifetime spend | Days overdue | Churn risk |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in rows[:12]:
            overdue = row.get("daysOverdue")
            churn = row.get("churnRisk")
            lines.append(
                f"| {row.get('name')} | {row.get('segment', '—')} | "
                f"{_money(row.get('lifetimeSpend'))} | "
                f"{int(overdue) if overdue is not None else 'not enough information'} | "
                f"{f'{churn:.0%}' if churn is not None else 'not enough information'} |"
            )
        return "\n".join(lines)

    if intent in {"inventory_problem", "push_products", "product_customers"}:
        rows = first.get("rows") or []
        if not rows:
            return "No products matched that criteria in the current data."
        total_value = sum(r.get("stockValue") or 0 for r in rows)
        lines = [
            f"**{first.get('matchedProducts', len(rows))} products** match, "
            f"{_money(total_value)} of stock value in the rows below.",
            "",
            "| Product | Status | Days in stock | Stock value | Recommended action |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in rows[:10]:
            days = row.get("daysInStock")
            lines.append(
                f"| {row.get('name')} | {row.get('status', '—')} | "
                f"{int(days) if days is not None else 'not enough information'} | "
                f"{_money(row.get('stockValue'))} | {row.get('recommendedAction', '—')} |"
            )
        return "\n".join(lines)

    if intent in {"category_performance", "sales_trend"}:
        breakdown = first.get("breakdown") or {}
        rows = breakdown.get("rows") or []
        trend = first.get("trend") or {}
        lines: list[str] = []
        if trend.get("last30Days") is not None:
            change = trend.get("changeVsPrevious")
            direction = "up" if (change or 0) > 0 else "down"
            lines.append(
                f"Last 30 days: **{_money(trend['last30Days'])}**"
                + (f", {direction} {abs(change):.1%} versus the previous 30 days."
                   if change is not None else ".")
            )
            lines.append("")
        if not rows:
            lines.append(breakdown.get("note") or "No breakdown data available.")
            return "\n".join(lines)
        lines += [
            f"By {breakdown.get('dimension', 'category')}:",
            "",
            "| Segment | Revenue | Share | Units | 90-day growth |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in rows[:8]:
            growth = row.get("growth")
            lines.append(
                f"| {row['value']} | {_money(row['revenue'])} | "
                f"{row['share']:.1%} | {row['units']:.0f} | "
                f"{f'{growth:+.1%}' if growth is not None else 'not enough information'} |"
            )
        return "\n".join(lines)

    if intent == "segments":
        segments = first.get("segments") or []
        if not segments:
            return "Segments could not be computed from the current data."
        lines = ["| Segment | Customers | Revenue | Share | What to do |",
                 "| --- | --- | --- | --- | --- |"]
        for seg in segments:
            share = seg.get("shareOfRevenue")
            lines.append(
                f"| {seg['segment']} | {seg['customers']} | {_money(seg.get('totalSpend'))} | "
                f"{f'{share:.1%}' if share is not None else '—'} | {seg.get('play', '')[:70]} |"
            )
        return "\n".join(lines)

    return "I ran the analysis but could not shape an answer for that question."


# --------------------------------------------------------------------------- #
def narrate(system: str, payload: dict[str, Any], fallback: str) -> tuple[str, str]:
    """One-shot narration helper for summaries, briefings and insights.

    Returns ``(text, mode)``. When AI is unavailable the caller's deterministic
    ``fallback`` is used, which is composed from the same computed figures.
    """
    if not client.is_available():
        return fallback, "deterministic"
    import json
    try:
        response = client.complete(
            system=system,
            messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
            max_tokens=900,
            temperature=0.3,
        )
        return (response.text or fallback), ("ai" if response.text else "deterministic")
    except client.AIUnavailable:
        return fallback, "deterministic"


def strip_markdown(text: str) -> str:
    return re.sub(r"[*_`#]", "", text or "").strip()
