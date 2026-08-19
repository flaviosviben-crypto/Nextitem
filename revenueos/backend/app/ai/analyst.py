"""The AI Analyst: Claude reasoning over deterministic RevenueOS analytics.

Flow for a question:

    user question
      -> Claude selects RevenueOS analytics tools
      -> tools run real, deterministic computations
      -> Claude reads the results and explains them
      -> answer, with the tool calls exposed for transparency

Claude never performs a calculation that the analytics layer can do. When no API
key is configured, every entry point degrades to a computed summary that is
clearly labelled, so the product never fabricates reasoning.
"""
from __future__ import annotations

import json
from typing import Any

from ..analytics import matching, opportunities as opp_engine
from ..workspace import workspace
from . import context_builder, prompts
from .client import MAX_TOKENS, MODEL, get_client, is_available
from .tools import ANALYST_TOOLS

# Guardrail: a runaway loop would burn tokens without helping the boutique.
MAX_TURNS = 8


def _text_of(message: Any) -> str:
    return "".join(b.text for b in message.content if getattr(b, "type", None) == "text").strip()


def _call(system: str, user: str, max_tokens: int = 1400) -> str | None:
    """One-shot completion. Returns ``None`` when the model is unavailable."""
    client = get_client()
    if client is None:
        return None
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": user}],
        )
    except Exception:
        return None
    if getattr(response, "stop_reason", None) == "refusal":
        return None
    return _text_of(response) or None


# ------------------------------------------------------------ conversation ---

def ask(question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Answer a question about the loaded dataset."""
    if not workspace.is_loaded:
        return {
            "answer": "No data is loaded yet. Import your customer, transaction and product "
                      "exports, or load the demo boutique, and I can answer from your own numbers.",
            "engine": "computed",
            "tool_calls": [],
        }

    client = get_client()
    if client is None:
        return _fallback_answer(question)

    messages: list[dict[str, Any]] = []
    for turn in (history or [])[-6:]:
        role = "assistant" if turn.get("role") == "assistant" else "user"
        content = (turn.get("content") or "").strip()
        if content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    tool_calls: list[dict[str, Any]] = []
    try:
        runner = client.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=prompts.ANALYST_SYSTEM,
            thinking={"type": "adaptive"},
            tools=ANALYST_TOOLS,
            messages=messages,
        )
        final = None
        for turn_index, message in enumerate(runner):
            final = message
            for block in message.content:
                if getattr(block, "type", None) == "tool_use":
                    tool_calls.append({"tool": block.name, "input": block.input})
            if turn_index + 1 >= MAX_TURNS:
                break
    except Exception as exc:  # network, auth, rate limit — degrade, never 500
        fallback = _fallback_answer(question)
        fallback["note"] = f"Live analyst unavailable ({type(exc).__name__}); showing computed data."
        return fallback

    if final is None:
        return _fallback_answer(question)
    if getattr(final, "stop_reason", None) == "refusal":
        return {"answer": "I can't answer that one. Try asking about your customers, "
                          "inventory or revenue opportunities.",
                "engine": "claude", "tool_calls": tool_calls}

    answer = _text_of(final)
    return {
        "answer": answer or "I could not find an answer in the current dataset.",
        "engine": "claude",
        "tool_calls": tool_calls,
        "data_used": [c["tool"] for c in tool_calls],
    }


def _fallback_answer(question: str) -> dict[str, Any]:
    """Rule-routed answer over real analytics, for when the API key is absent.

    This is intentionally not dressed up as conversation: it returns the actual
    computed rows and says where they came from.
    """
    q = question.lower()
    summary = workspace.summary

    def rows_payload(title: str, rows: list[dict[str, Any]], note: str) -> dict[str, Any]:
        return {"answer": note, "engine": "computed", "title": title, "rows": rows,
                "tool_calls": [], "note": "Conversational answers need ANTHROPIC_API_KEY; "
                                          "these figures are computed directly from your data."}

    if any(k in q for k in ("contact", "contattare", "reach out", "call", "who should")):
        # Answer from the same engine the advisor sees, so the analyst and the
        # opportunity list can never give two different answers to one question.
        rows = opp_engine.daily(workspace.opportunities)[:8]
        return rows_payload(
            "Customers to contact today",
            [{"name": o["customer_name"], "segment": o.get("segment"),
              "reason": o["why_now"], "product": (o.get("product") or {}).get("name"),
              "value": o.get("influenced_value"), "contactable": o["contactable"]}
             for o in rows],
            f"{len(rows)} customers are worth a conversation today.")

    if any(k in q for k in ("stock", "inventory", "dead", "giacenza", "magazzino")):
        rows = [p for p in workspace.products if p.get("risk_class") in {"Dead Stock", "At Risk"}]
        rows.sort(key=lambda p: -(p.get("stock_value") or 0))
        inv = summary.get("inventory", {})
        return rows_payload(
            "Inventory at risk",
            [{"product": p["product_name"], "category": p.get("category"),
              "value": p.get("stock_value"), "days": p.get("days_in_stock"),
              "reason": p.get("risk_reason")} for p in rows[:8]],
            f"{inv.get('at_risk_products', 0)} products are at risk, holding "
            f"€{inv.get('at_risk_value') or 0:,.0f} of stock value.")

    if any(k in q for k in ("opportunit", "revenue", "fatturato", "make more", "grow")):
        return rows_payload(
            "Ranked opportunities",
            [{"customer": o["customer_name"], "reason": o["why_now"],
              "value": o.get("influenced_value"), "action": o["action"]}
             for o in opp_engine.daily(workspace.opportunities)[:6]],
            f"{len(workspace.opportunities)} opportunities detected, worth an estimated "
            f"€{summary.get('revenue_opportunity', 0):,.0f} if acted on.")

    if any(k in q for k in ("vip", "best customer", "top customer", "migliori")):
        rows = sorted(workspace.profiles, key=lambda p: -(p.get("total_spend") or 0))[:8]
        return rows_payload(
            "Highest-value customers",
            [{"name": p["name"], "value_tier": p.get("value_tier"),
              "lifecycle": p.get("lifecycle"), "spend": p.get("total_spend"),
              "last_purchase": p.get("last_purchase")} for p in rows],
            "Your highest-value customers by recorded spend.")

    counts = summary.get("counts", {})
    return rows_payload(
        "Dataset overview",
        [{"metric": "Customers", "value": counts.get("customers")},
         {"metric": "Transactions", "value": counts.get("transactions")},
         {"metric": "Products", "value": counts.get("products")},
         {"metric": "Revenue opportunity", "value": summary.get("revenue_opportunity")},
         {"metric": "Data health", "value": summary.get("data_health")}],
        "Here is the current state of your workspace. Ask about customers to contact, "
        "inventory risk, or revenue opportunities.")


# ------------------------------------------------------------- narrative AI ---

def customer_narrative(customer_id: str) -> dict[str, Any]:
    """Summary + next best actions for one customer."""
    profile = workspace.profile(customer_id)
    if not profile:
        return {"error": "Unknown customer."}

    matches = matching.best_products_for_customer(profile, workspace.products, limit=4)
    recent = workspace.customer_transactions(customer_id)

    computed_summary = context_builder.describe_customer(profile, matches)
    computed_actions = context_builder.describe_actions(profile, matches)

    if not is_available():
        return {"summary": computed_summary, "actions": computed_actions, "engine": "computed"}

    context = context_builder.customer_context(profile, matches, recent)
    payload = json.dumps(context, ensure_ascii=False, default=str)

    summary = _call(prompts.CUSTOMER_SUMMARY_SYSTEM,
                    f"Customer data:\n{payload}\n\nWrite the profile.", max_tokens=500)
    actions_text = _call(
        prompts.NEXT_ACTIONS_SYSTEM,
        f"Customer data:\n{payload}\n\nList the next best actions, one per line, no numbering.",
        max_tokens=500)

    actions = computed_actions
    if actions_text:
        parsed = [line.strip(" -•*\t") for line in actions_text.splitlines() if line.strip()]
        if parsed:
            actions = parsed[:4]

    return {
        "summary": summary or computed_summary,
        "actions": actions,
        "engine": "claude" if summary else "computed",
        "computed_summary": computed_summary,
    }


def executive_brief() -> dict[str, Any]:
    """The weekly business briefing."""
    if not workspace.is_loaded:
        return {"brief": "No data loaded yet.", "engine": "computed"}

    from ..analytics.forecasting import monthly_trend

    trend = monthly_trend(workspace.transactions_raw, months=6)
    computed = context_builder.describe_week(
        workspace.summary, trend, workspace.opportunities, workspace.quality or {})

    if not is_available():
        return {"brief": computed, "engine": "computed", "trend": trend}

    payload = json.dumps({
        "summary": workspace.summary,
        "monthly_trend": trend,
        "top_opportunities": [{
            "customer_id": o["customer_id"], "trigger": o["trigger"],
            "headline": o["headline"], "why_now": o["why_now"],
            "influenced_value": o.get("influenced_value"),
            "action": o["action"], "priority": o["priority"],
        } for o in opp_engine.daily(workspace.opportunities)[:6]],
        "data_health": {"score": (workspace.quality or {}).get("score"),
                        "summary": (workspace.quality or {}).get("summary")},
    }, ensure_ascii=False, default=str)

    brief = _call(prompts.EXECUTIVE_SYSTEM,
                  f"Computed metrics:\n{payload}\n\nWrite the weekly briefing.", max_tokens=1200)
    return {"brief": brief or computed, "engine": "claude" if brief else "computed",
            "trend": trend, "computed_brief": computed}


def campaign_copy(campaign: dict[str, Any]) -> dict[str, Any]:
    """Rationale + draft message for a campaign."""
    audience = campaign.get("audience", [])
    computed = (
        f"{campaign.get('name')}: {len(audience)} customers selected because "
        f"{campaign.get('criteria', 'they match the campaign rules')}. "
        f"Estimated value €{campaign.get('estimated_value') or 0:,.0f}."
    )
    if not is_available():
        return {"rationale": computed, "message": None, "engine": "computed"}

    payload = json.dumps({
        "campaign": campaign.get("name"),
        "goal": campaign.get("goal"),
        "criteria": campaign.get("criteria"),
        "audience_size": len(audience),
        "audience_sample": [{"value_tier": a.get("value_tier"), "lifecycle": a.get("lifecycle"),
                             "top_category": a.get("top_category")}
                            for a in audience[:8]],
        "products": campaign.get("products", [])[:5],
        "estimated_value": campaign.get("estimated_value"),
    }, ensure_ascii=False, default=str)

    text = _call(prompts.CAMPAIGN_SYSTEM, f"Campaign data:\n{payload}", max_tokens=700)
    if not text:
        return {"rationale": computed, "message": None, "engine": "computed"}

    parts = text.split("\n\n", 1)
    return {
        "rationale": parts[0].strip(),
        "message": parts[1].strip() if len(parts) > 1 else None,
        "engine": "claude",
    }
