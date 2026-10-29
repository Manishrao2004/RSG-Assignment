import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.main import create_app


def call(name, args):
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": uuid4().hex, "type": "tool_call"}]
    )


def final(messages, message="Calculated from the database."):
    evidence = json.loads(messages[-1].content)
    return call(
        "final_answer", {"type": "answer", "message": message, "supporting_query_ids": [evidence["query_id"]]}
    )


class ScriptedModel:
    """Tests the real graph/checkpointer/tools with explicitly mocked model decisions."""

    def __init__(self, steps):
        self.steps = iter(steps)
        self.seen = []

    def bind_tools(self, tools, **kwargs):
        return self

    async def ainvoke(self, messages):
        self.seen.append(messages)
        step = next(self.steps)
        if isinstance(step, Exception):
            raise step
        return step(messages) if callable(step) else step


def test_followup_history_and_separate_threads(settings):
    model = ScriptedModel(
        [
            call(
                "sql_query",
                {
                    "sql": "SELECT product,SUM(revenue_cents)/100.0 AS revenue FROM sales GROUP BY product ORDER BY revenue DESC LIMIT 1"
                },
            ),
            lambda m: AIMessage(content="Monitor earned the most: 473,000."),
            call(
                "sql_query",
                {
                    "sql": "SELECT product,SUM(revenue_cents)/100.0 AS revenue FROM sales GROUP BY product ORDER BY revenue ASC LIMIT 1"
                },
            ),
            lambda m: AIMessage(content="Laptop Stand earned the least: 96,000."),
            call(
                "sql_query",
                {
                    "sql": "SELECT product,SUM(revenue_cents)/100.0 AS revenue FROM sales WHERE region=:region GROUP BY product ORDER BY revenue ASC LIMIT 1",
                    "parameters": {"region": "North"},
                },
            ),
            lambda m: AIMessage(content="USB-C Hub earned the least in North: 18,000."),
        ]
    )
    with TestClient(create_app(settings, model=model)) as client:
        first = client.post("/api/chat", json={"question": "Which product earned the most?"}).json()
        thread = first["thread_id"]
        second = client.post("/api/chat", json={"question": "And the least?", "thread_id": thread}).json()
        third = client.post("/api/chat", json={"question": "Only in North?", "thread_id": thread}).json()
        assert first["evidence"][0]["rows"][0]["product"] == "Monitor"
        assert second["evidence"][0]["rows"][0]["product"] == "Laptop Stand"
        assert third["evidence"][0]["rows"][0]["product"] == "USB-C Hub"
        assert third["evidence"][0]["rows"][0]["revenue"] == 18000
        assert len([m for m in model.seen[-1] if isinstance(m, HumanMessage)]) == 3
        history = client.get(f"/api/conversations/{thread}").json()["messages"]
        assert len(history) == 6
        assert client.get(f"/api/conversations/{uuid4()}").json()["messages"] == []
    # A new application/checkpointer connection restores the saved conversation.
    with TestClient(create_app(settings, model=model)) as restarted:
        assert restarted.get(f"/api/conversations/{thread}").json()["messages"] == history


def test_ambiguous_question_is_a_clarification(settings):
    model = ScriptedModel(
        [call("final_answer", {"type": "clarification", "message": "By product, region, or month?"})]
    )
    with TestClient(create_app(settings, model=model)) as client:
        result = client.post("/api/chat", json={"question": "which is the least revenue"}).json()
        assert result["type"] == "clarification"
        assert not result["evidence"]


def test_bad_sql_returns_error_to_model_then_retries(settings):
    def retry(messages):
        assert "error" in json.loads(messages[-1].content)
        return call("sql_query", {"sql": "SELECT SUM(revenue_cents)/100.0 AS revenue FROM sales"})

    model = ScriptedModel([call("sql_query", {"sql": "DELETE FROM sales"}), retry, final])
    with TestClient(create_app(settings, model=model)) as client:
        result = client.post("/api/chat", json={"question": "Total revenue?"})
        assert result.status_code == 200
        assert result.json()["evidence"][0]["rows"][0]["revenue"] == 1439200


def test_reject_invented_evidence(settings):
    model = ScriptedModel(
        [
            call(
                "final_answer",
                {"type": "answer", "message": "Revenue is 999", "supporting_query_ids": ["fake"]},
            ),
            call("final_answer", {"type": "cant_answer", "message": "I could not verify that figure."}),
        ]
    )
    with TestClient(create_app(settings, model=model)) as client:
        result = client.post("/api/chat", json={"question": "Total revenue?"}).json()
        assert result["type"] == "cant_answer"
        assert "valid supporting query" in model.seen[-1][-1].content


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": " "},
        {"question": "ab"},
        {"question": "x" * 2001},
        {"question": "Revenue?", "thread_id": "not-a-uuid"},
        {"question": "Revenue?", "sql": "DELETE"},
    ],
)
def test_invalid_request(client, payload):
    assert client.post("/api/chat", json=payload).status_code == 422


def test_key_required(client):
    result = client.post("/api/chat", json={"question": "Total revenue?"})
    assert result.status_code == 503
    assert "GROQ_API_KEY" in result.json()["detail"]


def test_provider_error_does_not_leak_secrets(settings):
    model = ScriptedModel([RuntimeError("secret-provider-body")])
    with TestClient(create_app(settings, model=model)) as client:
        result = client.post("/api/chat", json={"question": "Total revenue?"})
        assert result.status_code == 503
        assert "secret-provider-body" not in result.text


def test_answer_cannot_invent_currency(settings):
    def invalid(messages):
        return final(messages, "Revenue is $1,439,200.")

    def corrected(messages):
        assert "does not specify currency" in messages[-1].content
        data = next(
            json.loads(m.content)
            for m in reversed(messages)
            if isinstance(m, ToolMessage) and m.name == "sql_query"
        )
        return call(
            "final_answer",
            {
                "type": "answer",
                "message": "Revenue is 1,439,200.",
                "supporting_query_ids": [data["query_id"]],
            },
        )

    model = ScriptedModel(
        [
            call("sql_query", {"sql": "SELECT SUM(revenue_cents)/100.0 AS revenue FROM sales"}),
            invalid,
            corrected,
        ]
    )
    with TestClient(create_app(settings, model=model)) as client:
        result = client.post("/api/chat", json={"question": "Total revenue?"}).json()
        assert result["message"] == "Revenue is 1,439,200."


def test_interrupted_tool_call_is_repaired(settings):
    from app.main_agent.graph import repair_dangling_tool_calls

    pending = call("sql_query", {"sql": "SELECT COUNT(*) FROM sales"})
    repairs = repair_dangling_tool_calls([HumanMessage("Total?"), pending])
    assert len(repairs) == 1 and isinstance(repairs[0], ToolMessage)
    assert repairs[0].tool_call_id == pending.tool_calls[0]["id"]
