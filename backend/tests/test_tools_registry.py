"""Unit tests for AI ToolRegistry: schemas, validation, limits, timeout, and exceptions."""

import asyncio
from typing import Any

import networkx as nx
import pytest

from app.ai.tools.base import Tool, ToolContext, ToolResult
from app.ai.tools.registry import ToolRegistry


class DummyEchoTool(Tool):
    """Tool that echoes string argument."""

    name = "dummy_echo"
    description = "Echoes back the input text."
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1},
            "count": {"type": "integer", "minimum": 1},
        },
        "required": ["text"],
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        text = args["text"]
        count = args.get("count", 1)
        return ToolResult(
            ok=True,
            data={"echo": text * count},
            summary=f"dummy_echo {text}",
        )


class DummySlowTool(Tool):
    """Tool that sleeps longer than execution timeout."""

    name = "dummy_slow"
    description = "A very slow tool that times out."
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "seconds": {"type": "number"},
        },
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        await asyncio.sleep(args.get("seconds", 25.0))
        return ToolResult(ok=True, data={"finished": True})


class DummyFailingTool(Tool):
    """Tool that raises an unexpected exception."""

    name = "dummy_fail"
    description = "A failing tool."
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {},
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        raise RuntimeError("Simulated crash in dummy_fail")


@pytest.fixture
def empty_ctx() -> ToolContext:
    return ToolContext(
        user=None,
        repo=None,
        graph=nx.DiGraph(),
        files=None,
        review_mode="review",
    )


@pytest.mark.asyncio
async def test_registry_unknown_tool(empty_ctx: ToolContext) -> None:
    registry = ToolRegistry()
    res = await registry.dispatch(empty_ctx, "non_existent_tool", {})
    assert not res.ok
    assert "Unknown tool" in (res.error or "")
    assert res.summary == "unknown tool non_existent_tool"


@pytest.mark.asyncio
async def test_registry_allowed_tools_filtering(empty_ctx: ToolContext) -> None:
    registry = ToolRegistry()
    registry.register(DummyEchoTool())

    empty_ctx.allowed_tools = {"other_tool"}
    res = await registry.dispatch(empty_ctx, "dummy_echo", {"text": "hello"})
    assert not res.ok
    assert "not permitted" in (res.error or "")

    empty_ctx.allowed_tools = {"dummy_echo"}
    res_ok = await registry.dispatch(empty_ctx, "dummy_echo", {"text": "hello"})
    assert res_ok.ok
    assert res_ok.data == {"echo": "hello"}


@pytest.mark.asyncio
async def test_registry_invalid_schema_arguments(empty_ctx: ToolContext) -> None:
    registry = ToolRegistry()
    registry.register(DummyEchoTool())

    # Missing required 'text'
    res = await registry.dispatch(empty_ctx, "dummy_echo", {"count": 2})
    assert not res.ok
    assert "Invalid arguments" in (res.error or "")

    # Invalid type for 'count'
    res_bad_type = await registry.dispatch(
        empty_ctx, "dummy_echo", {"text": "hi", "count": "not_an_int"}
    )
    assert not res_bad_type.ok
    assert "Invalid arguments" in (res_bad_type.error or "")


@pytest.mark.asyncio
async def test_registry_oversize_arguments(empty_ctx: ToolContext) -> None:
    registry = ToolRegistry()
    registry.register(DummyEchoTool())

    huge_text = "a" * 70000
    res = await registry.dispatch(empty_ctx, "dummy_echo", {"text": huge_text})
    assert not res.ok
    assert "exceeds limit" in (res.error or "")
    assert res.summary == "dummy_echo (args too large)"


@pytest.mark.asyncio
async def test_registry_tool_timeout(
    empty_ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ai.tools import registry as reg_module

    # Temporarily set timeout to 0.1s for fast test
    monkeypatch.setattr(reg_module, "TOOL_EXECUTION_TIMEOUT_SECONDS", 0.1)

    reg = ToolRegistry()
    reg.register(DummySlowTool())

    res = await reg.dispatch(empty_ctx, "dummy_slow", {"seconds": 0.5})
    assert not res.ok
    assert "timed out" in (res.error or "")
    assert res.summary == "dummy_slow (timeout)"


@pytest.mark.asyncio
async def test_registry_tool_exception_handling(empty_ctx: ToolContext) -> None:
    reg = ToolRegistry()
    reg.register(DummyFailingTool())

    res = await reg.dispatch(empty_ctx, "dummy_fail", {})
    assert not res.ok
    assert "Simulated crash" in (res.error or "")
    assert res.summary == "dummy_fail (error)"


def test_registry_schemas_generation() -> None:
    reg = ToolRegistry()
    reg.register(DummyEchoTool())
    reg.register(DummyFailingTool())

    all_schemas = reg.schemas()
    assert len(all_schemas) == 2
    assert all_schemas[0]["type"] == "function"
    assert all_schemas[0]["function"]["name"] == "dummy_echo"

    filtered_schemas = reg.schemas(allowed={"dummy_fail"})
    assert len(filtered_schemas) == 1
    assert filtered_schemas[0]["function"]["name"] == "dummy_fail"
