"""SSE contract test for POST /chat (the multi-mode streaming rewrite).

A fake compiled graph emits the LangGraph stream-mode tuples the endpoint
consumes (`messages` token deltas, `custom` research progress, `updates` tool
node output); we assert they're translated into the right SSE events.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


class FakeGraph:
    """Yields (mode, chunk) tuples like graph.astream(stream_mode=[...])."""

    async def astream(self, state, stream_mode=None):
        # chat_node token deltas
        yield ("messages", (SimpleNamespace(content="Mer"), {"langgraph_node": "chat_node"}))
        yield ("messages", (SimpleNamespace(content="haba"), {"langgraph_node": "chat_node"}))
        # tokens from a tool node must NOT be forwarded as deltas
        yield ("messages", (SimpleNamespace(content='{"json":1}'), {"langgraph_node": "task_tool_node"}))
        # live research progress (custom channel)
        yield ("custom", {"type": "research_progress", "phase": "searching",
                          "round": 1, "total_sources": 2})
        # final tool-node output (updates channel)
        yield ("updates", {"task_tool_node": {"messages": [SimpleNamespace(content="1 görev eklendi.")],
                                              "active_tool": "add_task"}})


@pytest.fixture
def client_with_fake_graph():
    from fastapi.testclient import TestClient
    import app as app_module

    with TestClient(app_module.app) as c:
        c.app.state.graph = FakeGraph()
        yield c


def _parse_sse(body: str) -> list[dict]:
    events = []
    for frame in body.split("\n\n"):
        frame = frame.strip()
        if frame.startswith("data:"):
            events.append(json.loads(frame[len("data:"):].strip()))
    return events


def test_chat_stream_emits_typed_events(client_with_fake_graph):
    r = client_with_fake_graph.post("/chat", json={"message": "selam", "history": []})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(r.text)
    types = [e["type"] for e in events]

    # token deltas from chat_node only
    deltas = [e["content"] for e in events if e["type"] == "delta"]
    assert "".join(deltas) == "Merhaba"
    assert not any(e["type"] == "delta" and "json" in e["content"] for e in events)

    # research progress forwarded verbatim
    rp = [e for e in events if e["type"] == "research_progress"]
    assert rp and rp[0]["phase"] == "searching" and rp[0]["total_sources"] == 2

    # tool node surfaces a tool_start + its message
    assert "tool_start" in types
    assert any(e.get("tool") == "add_task" for e in events if e["type"] == "tool_start")
    assert any(e["type"] == "message" and "görev eklendi" in e["content"] for e in events)

    # stream terminates cleanly
    assert types[-1] == "done"


def test_chat_503_without_graph():
    from fastapi.testclient import TestClient
    import app as app_module

    with TestClient(app_module.app) as c:
        c.app.state.graph = None
        r = c.post("/chat", json={"message": "selam", "history": []})
        assert r.status_code == 503


def test_brain_extract_requires_llm_http():
    """With no OPENROUTER_API_KEY in tests the extractor LLM is absent → 503."""
    from fastapi.testclient import TestClient
    import app as app_module

    with TestClient(app_module.app) as c:
        r = c.post("/brain/extract", json={"history": [{"role": "user", "text": "selam"}]})
        assert r.status_code == 503
