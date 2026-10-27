"""Unit and integration tests for repository chat agent."""

import json
from unittest.mock import AsyncMock

import networkx as nx
import pytest
from starlette.requests import Request

from app.ai.chat import (
    ChatMessage,
    acquire_chat_slot,
    prepare_conversation_history,
    release_chat_slot,
    run_chat_stream,
)
from app.ai.llm import LLMClient, LLMResult, LLMUsage, ToolCall


class FakeScriptedChatLLM(LLMClient):
    """Fake LLM client that returns scripted responses."""

    def __init__(self, responses: list[LLMResult]) -> None:
        self.responses = list(responses)
        self.call_count = 0
        self.captured_conversations: list[list[dict]] = []

    async def chat(self, messages, **kwargs) -> LLMResult:
        self.call_count += 1
        self.captured_conversations.append(messages)
        if self.responses:
            return self.responses.pop(0)
        return LLMResult(
            text="Default response.",
            latency_ms=10.0,
            model="fake-groq",
            usage=LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


@pytest.fixture
def chat_graph() -> nx.DiGraph:
    """Fixture providing a dependency graph for chat tests."""
    g = nx.DiGraph()
    g.add_node("src/auth.ts", name="auth.ts", external_deps=["jsonwebtoken"])
    g.add_node("src/utils.ts", name="utils.ts", external_deps=[])
    g.add_edge("src/auth.ts", "src/utils.ts", kinds={"import"}, type_only=False, count=1)
    return g


def mock_request(disconnected: bool = False) -> Request:
    """Create a mock Starlette request."""
    req = AsyncMock(spec=Request)
    req.is_disconnected.return_value = disconnected
    return req


@pytest.mark.asyncio
async def test_chat_sse_event_ordering(chat_graph: nx.DiGraph) -> None:
    """Assert SSE event order: step* -> token* -> verification -> done."""
    # Scripted responses:
    # 1. LLM requests tool call: list_dependencies(file="src/auth.ts")
    # 2. LLM returns final text mentioning src/utils.ts
    step_res = LLMResult(
        tool_calls=[
            ToolCall(
                id="call_1",
                name="list_dependencies",
                arguments={"file": "src/auth.ts"},
            )
        ],
        latency_ms=10.0,
        model="fake-groq",
        usage=LLMUsage(prompt_tokens=50, completion_tokens=20, total_tokens=70),
    )
    final_res = LLMResult(
        text="`src/auth.ts` imports `src/utils.ts`.",
        latency_ms=10.0,
        model="fake-groq",
        usage=LLMUsage(prompt_tokens=80, completion_tokens=30, total_tokens=110),
    )

    fake_llm = FakeScriptedChatLLM([step_res, final_res])
    req = mock_request(disconnected=False)
    conversation = prepare_conversation_history(
        [ChatMessage(role="user", content="What does auth.ts depend on?")],
        language="en",
    )

    events: list[dict] = []
    async for sse_chunk in run_chat_stream(
        request=req,
        conversation=conversation,
        graph=chat_graph,
        source_dir=None,
        llm_client=fake_llm,
    ):
        if sse_chunk.startswith("data: "):
            payload = json.loads(sse_chunk[len("data: ") :].strip())
            events.append(payload)

    event_types = [e["type"] for e in events]

    # Verify event types and ordering
    assert "step" in event_types
    assert "token" in event_types
    assert "verification" in event_types
    assert "done" in event_types

    # Ordering assertions: step comes before token, token before verification,
    # and verification before done
    first_step_idx = event_types.index("step")
    first_token_idx = event_types.index("token")
    verif_idx = event_types.index("verification")
    done_idx = event_types.index("done")

    assert first_step_idx < first_token_idx < verif_idx < done_idx

    # Check verification event verified src/auth.ts and src/utils.ts
    verif_event = events[verif_idx]
    assert "src/auth.ts" in verif_event["verified"]
    assert "src/utils.ts" in verif_event["verified"]
    assert len(verif_event["flagged"]) == 0


@pytest.mark.asyncio
async def test_chat_tool_loop_8_step_cap(chat_graph: nx.DiGraph) -> None:
    """Assert tool execution loop respects the 8-step cap."""
    # Endless tool calls
    responses = [
        LLMResult(
            tool_calls=[
                ToolCall(
                    id=f"call_{i}",
                    name="list_dependencies",
                    arguments={"file": "src/auth.ts"},
                )
            ],
            latency_ms=10.0,
            model="fake-groq",
            usage=LLMUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        )
        for i in range(12)
    ]
    # Add one final text result
    responses.append(
        LLMResult(
            text="Completed 8 steps.",
            latency_ms=10.0,
            model="fake-groq",
            usage=LLMUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        )
    )

    fake_llm = FakeScriptedChatLLM(responses)
    req = mock_request(disconnected=False)
    conversation = prepare_conversation_history(
        [ChatMessage(role="user", content="Infinite tool test")],
        language="en",
    )

    events: list[dict] = []
    async for sse_chunk in run_chat_stream(
        request=req,
        conversation=conversation,
        graph=chat_graph,
        source_dir=None,
        llm_client=fake_llm,
    ):
        if sse_chunk.startswith("data: "):
            events.append(json.loads(sse_chunk[len("data: ") :].strip()))

    step_events = [e for e in events if e["type"] == "step"]
    assert len(step_events) == 8  # Strictly capped at 8!


@pytest.mark.asyncio
async def test_chat_tool_error_does_not_crash(chat_graph: nx.DiGraph) -> None:
    """A bad tool call yields ok=False step event and continues without crash."""
    bad_step = LLMResult(
        tool_calls=[
            ToolCall(
                id="bad_1",
                name="list_dependencies",
                arguments={"file": "nonexistent.ts"},
            )
        ],
        latency_ms=10.0,
        model="fake-groq",
        usage=LLMUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
    )
    final_res = LLMResult(
        text="The file nonexistent.ts is not in the graph.",
        latency_ms=10.0,
        model="fake-groq",
        usage=LLMUsage(prompt_tokens=30, completion_tokens=10, total_tokens=40),
    )

    fake_llm = FakeScriptedChatLLM([bad_step, final_res])
    req = mock_request(disconnected=False)
    conversation = prepare_conversation_history(
        [ChatMessage(role="user", content="Check nonexistent.ts")],
        language="en",
    )

    events: list[dict] = []
    async for sse_chunk in run_chat_stream(
        request=req,
        conversation=conversation,
        graph=chat_graph,
        source_dir=None,
        llm_client=fake_llm,
    ):
        if sse_chunk.startswith("data: "):
            events.append(json.loads(sse_chunk[len("data: ") :].strip()))

    step_events = [e for e in events if e["type"] == "step"]
    assert len(step_events) == 1
    assert step_events[0]["ok"] is False  # Recorded error gracefully!
    assert "not found in dependency graph" in step_events[0]["result_summary"]


@pytest.mark.asyncio
async def test_chat_concurrency_409() -> None:
    """Assert concurrent second request for same user and repo is rejected."""
    user_id = 99
    repo_id = 100

    # First slot acquisition succeeds
    slot1 = await acquire_chat_slot(user_id, repo_id)
    assert slot1 is True

    # Second concurrent acquisition fails (maps to 409 in endpoint)
    slot2 = await acquire_chat_slot(user_id, repo_id)
    assert slot2 is False

    # Release slot
    await release_chat_slot(user_id, repo_id)

    # Now can acquire again
    slot3 = await acquire_chat_slot(user_id, repo_id)
    assert slot3 is True
    await release_chat_slot(user_id, repo_id)
