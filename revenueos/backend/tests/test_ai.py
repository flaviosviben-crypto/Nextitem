"""The AI layer, exercised with a stubbed Claude.

No live API call is made here. What is under test is the *contract* around the
model: that it can only reach data through the analytics tools, that PII is
stripped before anything leaves the process, and that the product degrades to
computed answers rather than failing when the model is unavailable.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from app.ai import client
from app.ai.analyst import ask
from app.ai.context_builder import customer_brief, scrub, workspace_overview
from app.ai.tools import TOOL_SPECS, run_tool
from app.store import Workspace


@pytest.fixture
def workspace(tables) -> Workspace:
    ws = Workspace(id="test", name="Test Boutique", source="demo")
    for entity, frame in tables.items():
        ws.set_table(entity, frame)
    ws.recompute(force=True)
    return ws


def fake_response(text: str = "", tool_calls=None) -> client.AIResponse:
    return client.AIResponse(text=text, tool_calls=tool_calls,
                             usage={"inputTokens": 10, "outputTokens": 5})


class TestToolContract:
    def test_every_tool_is_declared_with_a_schema(self):
        from app.ai.tools import _HANDLERS

        declared = {spec["name"] for spec in TOOL_SPECS}
        assert declared == set(_HANDLERS), "a declared tool must have a handler"
        for spec in TOOL_SPECS:
            assert spec["description"], f"{spec['name']} has no description"
            assert spec["input_schema"]["type"] == "object"

    @pytest.mark.parametrize("name", [spec["name"] for spec in TOOL_SPECS])
    def test_every_tool_runs_without_raising(self, workspace, name):
        payload = {"type": "discount"} if name == "simulate" else {}
        if name == "recommend_products_for_customer":
            payload = {"customerId": workspace.customer_metrics.iloc[0]["customer_id"]}
        if name == "recommend_customers_for_product":
            payload = {"productId": workspace.inventory_metrics.iloc[0]["product_id"]}
        result = run_tool(workspace, name, payload)
        assert isinstance(result, dict)
        assert "error" not in result, result.get("error")

    def test_an_unknown_tool_returns_an_error_not_an_exception(self, workspace):
        assert "error" in run_tool(workspace, "drop_database", {})

    def test_a_tool_asked_for_a_nonexistent_customer_says_so(self, workspace):
        result = run_tool(workspace, "recommend_products_for_customer",
                          {"customerName": "Nobody At All"})
        assert "error" in result
        assert "no customer matching" in result["error"].lower()

    def test_tools_return_real_records_only(self, workspace):
        result = run_tool(workspace, "find_customers", {"limit": 5})
        known = set(workspace.customer_metrics["customer_id"].astype(str))
        for row in result["rows"]:
            assert row["id"] in known, "a tool returned a customer that does not exist"


class TestPiiMinimisation:
    def test_direct_identifiers_are_stripped(self):
        record = {"id": "C1", "name": "Giulia Rossi", "email": "g@x.it",
                  "phone": "+39 333 1234567", "notes": "private", "totalSpend": 1200}
        cleaned = scrub(record)
        assert "email" not in cleaned
        assert "phone" not in cleaned
        assert "notes" not in cleaned
        # what the owner needs to act survives
        assert cleaned["name"] == "Giulia Rossi"
        assert cleaned["totalSpend"] == 1200

    def test_customer_briefs_carry_no_contact_details(self, workspace):
        for _, row in workspace.customer_metrics.head(20).iterrows():
            brief = customer_brief(row)
            serialised = str(brief).lower()
            assert "@" not in serialised, "an email reached the model payload"
            assert "+39" not in serialised, "a phone number reached the model payload"

    def test_the_workspace_overview_is_aggregate_only(self, workspace):
        overview = workspace_overview(workspace)
        serialised = str(overview)
        assert "@" not in serialised
        assert overview["counts"]["customers"] > 0


class TestAnalystLoop:
    def test_the_model_can_only_get_numbers_through_a_tool(self, workspace):
        """Claude asks for a tool; the tool result is what it then narrates."""
        calls = []

        def stub(system, messages, tools=None, **kwargs):
            calls.append(messages)
            if len(calls) == 1:
                assert tools, "tools must be offered on the first turn"
                return fake_response(tool_calls=[{
                    "id": "t1", "name": "find_customers",
                    "input": {"overdueOnly": True, "limit": 3},
                }])
            # the tool result must have been fed back before the model answers
            last = messages[-1]["content"]
            assert last[0]["type"] == "tool_result"
            assert "rows" in last[0]["content"]
            return fake_response(text="Contact these three customers today.")

        with patch.object(client, "is_available", return_value=True), \
             patch.object(client, "complete", side_effect=stub):
            answer = ask(workspace, "Who should I contact today?")

        assert answer.mode == "ai"
        assert answer.answer == "Contact these three customers today."
        assert answer.tool_calls[0]["tool"] == "find_customers"
        assert answer.data[0]["result"]["rows"]

    def test_several_tools_can_run_in_one_turn(self, workspace):
        def stub(system, messages, tools=None, **kwargs):
            if not any(m["role"] == "assistant" for m in messages):
                return fake_response(tool_calls=[
                    {"id": "a", "name": "get_segments", "input": {}},
                    {"id": "b", "name": "get_inventory_summary", "input": {}},
                ])
            return fake_response(text="Here is the picture.")

        with patch.object(client, "is_available", return_value=True), \
             patch.object(client, "complete", side_effect=stub):
            answer = ask(workspace, "Give me an overview")

        assert {c["tool"] for c in answer.tool_calls} == {"get_segments", "get_inventory_summary"}

    def test_a_runaway_tool_loop_is_bounded(self, workspace):
        """A model that never stops calling tools must still return an answer."""
        def stub(system, messages, tools=None, **kwargs):
            if tools:
                return fake_response(tool_calls=[
                    {"id": "x", "name": "get_segments", "input": {}}
                ])
            return fake_response(text="Final answer after the cap.")

        with patch.object(client, "is_available", return_value=True), \
             patch.object(client, "complete", side_effect=stub):
            answer = ask(workspace, "Loop forever")

        assert answer.answer == "Final answer after the cap."
        assert len(answer.tool_calls) <= 8

    def test_history_is_passed_but_bounded(self, workspace):
        captured = {}

        def stub(system, messages, tools=None, **kwargs):
            captured["messages"] = messages
            return fake_response(text="ok")

        history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}"}
                   for i in range(20)]
        with patch.object(client, "is_available", return_value=True), \
             patch.object(client, "complete", side_effect=stub):
            ask(workspace, "And now?", history)

        assert len(captured["messages"]) <= 7
        assert captured["messages"][-1]["content"] == "And now?"


class TestGracefulDegradation:
    def test_an_api_failure_falls_back_to_computed_answers(self, workspace):
        with patch.object(client, "is_available", return_value=True), \
             patch.object(client, "complete",
                          side_effect=client.AIUnavailable("service down")):
            answer = ask(workspace, "Who should I contact today?")

        assert answer.mode == "deterministic"
        assert answer.answer, "the user must still get an answer"
        assert answer.tool_calls, "the same analytics must still run"
        assert "unavailable" in (answer.notice or "").lower()

    def test_without_a_key_the_same_tools_still_run(self, workspace):
        with patch.object(client, "is_available", return_value=False):
            answer = ask(workspace, "What are my biggest inventory problems?")

        assert answer.mode == "deterministic"
        assert answer.tool_calls[0]["tool"] == "find_products"
        assert "|" in answer.answer, "the fallback presents a real table"

    def test_no_data_is_answered_honestly(self):
        empty = Workspace(id="empty", name="Empty")
        answer = ask(empty, "Who should I contact?")
        assert "no data" in answer.answer.lower()
        assert not answer.tool_calls

    def test_missing_key_produces_a_clear_message_not_a_crash(self):
        from dataclasses import replace

        # Settings is frozen on purpose (config must not drift at runtime),
        # so swap the whole object rather than mutating a field.
        keyless = replace(client.settings, anthropic_api_key=None)
        with patch.object(client, "settings", keyless):
            client._client = None
            with pytest.raises(client.AIUnavailable) as exc:
                client.complete("system", [{"role": "user", "content": "hi"}])
            assert "ANTHROPIC_API_KEY" in str(exc.value)
        client._client = None


def flat(text: str) -> str:
    """Prompts are hard-wrapped, so collapse whitespace before matching."""
    return " ".join(text.lower().split())


class TestPrompts:
    def test_the_system_prompt_forbids_invention(self, workspace):
        from app.ai.prompts import analyst_system

        prompt = flat(analyst_system(workspace_overview(workspace)))
        assert "never estimate" in prompt or "never invent" in prompt
        assert "not enough information" in prompt
        assert "tool result" in prompt

    def test_narration_prompts_all_carry_the_ground_rules(self):
        from app.ai import prompts

        for builder in (prompts.customer_summary_system, prompts.briefing_system,
                        prompts.insights_system, prompts.campaign_system,
                        prompts.scenario_system):
            prompt = flat(builder())
            assert "ground rules" in prompt
            assert "never estimate, never extrapolate" in prompt
            assert "not enough information" in prompt
