"""Repository chat agent with iterative tool execution, SSE streaming, and verification."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import networkx as nx
from fastapi import Request
from pydantic import BaseModel, Field

from app.ai.llm import LLMClient, LLMResult, get_llm_client
from app.ai.prompts.chat import CHAT_PROMPT_VERSION, build_chat_system_message
from app.ai.tools import ToolContext, ToolResult, build_read_tools_registry
from app.ai.untrusted import truncate
from app.ai.verify import extract_path_mentions, verify_mentions

logger = logging.getLogger(__name__)

# Maximum tool execution iterations per turn
MAX_TOOL_STEPS = 8

# Maximum turns and characters from history
MAX_HISTORY_TURNS = 10
MAX_HISTORY_CHARS = 8000

# Concurrency tracking: one in-flight chat per user per repo
_ACTIVE_CHATS: set[tuple[int, int]] = set()
_LOCK = asyncio.Lock()


async def acquire_chat_slot(user_id: int, repo_id: int) -> bool:
    """Acquire chat slot for (user_id, repo_id). Returns False if already in-flight."""
    async with _LOCK:
        if (user_id, repo_id) in _ACTIVE_CHATS:
            return False
        _ACTIVE_CHATS.add((user_id, repo_id))
        return True


async def release_chat_slot(user_id: int, repo_id: int) -> None:
    """Release chat slot for (user_id, repo_id)."""
    async with _LOCK:
        _ACTIVE_CHATS.discard((user_id, repo_id))


class ChatMessage(BaseModel):
    """Client-provided chat message in history."""

    role: str
    content: str = ""


class ChatRequest(BaseModel):
    """Chat endpoint request body."""

    messages: list[ChatMessage] = Field(default_factory=list)


def prepare_conversation_history(
    messages: list[ChatMessage],
    language: str,
) -> list[dict[str, Any]]:
    """Format, bound, and prepend system prompt to conversation messages."""
    system_msg = build_chat_system_message(language)

    # Take the last MAX_HISTORY_TURNS messages
    recent = messages[-MAX_HISTORY_TURNS:] if len(messages) > MAX_HISTORY_TURNS else messages

    # Enforce character bound across messages, retaining newest
    total_chars = 0
    bounded_recent: list[ChatMessage] = []
    for msg in reversed(recent):
        msg_len = len(msg.content)
        if total_chars + msg_len > MAX_HISTORY_CHARS and bounded_recent:
            break
        total_chars += msg_len
        bounded_recent.append(msg)

    bounded_recent.reverse()

    conversation: list[dict[str, Any]] = [system_msg]
    for m in bounded_recent:
        role = m.role if m.role in ("user", "assistant") else "user"
        conversation.append({"role": role, "content": m.content})

    return conversation


async def run_chat_stream(
    request: Request,
    conversation: list[dict[str, Any]],
    graph: nx.DiGraph,
    source_dir: Path | None,
    llm_client: LLMClient | None = None,
) -> AsyncIterator[str]:
    """Execute iterative tool calling loop and stream SSE events to client."""
    client = llm_client or get_llm_client()
    registry = build_read_tools_registry()
    tool_ctx = ToolContext(
        user=None,
        repo=None,
        graph=graph,
        files=None,
        review_mode="readonly",
        source_dir=source_dir,
    )
    tools_schemas = registry.schemas()

    step_count = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    accumulated_answer = ""

    try:
        # Tool execution loop
        while step_count < MAX_TOOL_STEPS:
            if await request.is_disconnected():
                logger.info("Client disconnected during chat tool loop.")
                return

            llm_result: LLMResult = await client.chat(
                messages=conversation,
                tools=tools_schemas,
                feature="chat.loop",
                temperature=0.1,
                max_tokens=1024,
                prompt_name="chat",
                prompt_version=CHAT_PROMPT_VERSION,
            )

            total_prompt_tokens += llm_result.usage.prompt_tokens
            total_completion_tokens += llm_result.usage.completion_tokens

            if not llm_result.tool_calls:
                # Model finished tool invocations; record final text
                accumulated_answer = llm_result.text or ""
                break

            # Execute tool calls
            assistant_tool_calls_payload = []
            executed_results: list[tuple[Any, dict[str, Any]]] = []

            for tc in llm_result.tool_calls:
                step_count += 1
                args_summary = truncate(json.dumps(tc.arguments), max_chars=120)

                tool_result: ToolResult = await registry.dispatch(tool_ctx, tc.name, tc.arguments)
                tool_output = (
                    tool_result.data
                    if tool_result.ok
                    else (
                        tool_result.data
                        if "error" in tool_result.data
                        else {"error": tool_result.error or "Tool execution failed"}
                    )
                )
                executed_results.append((tc, tool_output))

                result_summary = truncate(json.dumps(tool_output), max_chars=200)

                # Emit step SSE event
                step_event = {
                    "type": "step",
                    "id": tc.id,
                    "tool": tc.name,
                    "args_summary": args_summary,
                    "ok": tool_result.ok,
                    "result_summary": result_summary,
                }
                yield f"data: {json.dumps(step_event)}\n\n"

                assistant_tool_calls_payload.append(
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                )

                if step_count >= MAX_TOOL_STEPS:
                    break

            # Append assistant message with tool calls
            conversation.append(
                {
                    "role": "assistant",
                    "content": llm_result.text or "",
                    "tool_calls": assistant_tool_calls_payload,
                }
            )

            # Append tool outputs
            for tc, tool_output in executed_results:
                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_output),
                    }
                )

            if step_count >= MAX_TOOL_STEPS:
                break

        # If model exhausted steps or didn't output text in last chat call, make final answer call
        if not accumulated_answer:
            if await request.is_disconnected():
                return

            final_result = await client.chat(
                messages=conversation,
                feature="chat.final",
                temperature=0.2,
                max_tokens=1024,
                prompt_name="chat",
                prompt_version=CHAT_PROMPT_VERSION,
            )
            accumulated_answer = final_result.text or ""
            total_prompt_tokens += final_result.usage.prompt_tokens
            total_completion_tokens += final_result.usage.completion_tokens

        # Stream the final answer tokens
        # Split into small delta chunks for smooth client rendering
        chunk_size = 12
        for i in range(0, len(accumulated_answer), chunk_size):
            if await request.is_disconnected():
                return
            delta = accumulated_answer[i : i + chunk_size]
            token_event = {"type": "token", "text": delta}
            yield f"data: {json.dumps(token_event)}\n\n"
            await asyncio.sleep(0.01)

        # Path verification on the complete answer
        mentions = extract_path_mentions(accumulated_answer)
        verified_map, flagged_mentions = verify_mentions(mentions, graph)

        verified_nodes = sorted(list(set(verified_map.values())))
        flagged_nodes = sorted(list(set(m.cleaned for m in flagged_mentions)))

        verification_event = {
            "type": "verification",
            "verified": verified_nodes,
            "flagged": flagged_nodes,
        }
        yield f"data: {json.dumps(verification_event)}\n\n"

        # Done event
        done_event = {
            "type": "done",
            "usage": {
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
            },
            "steps": step_count,
        }
        yield f"data: {json.dumps(done_event)}\n\n"

    except Exception as exc:
        logger.exception("Error during chat stream execution: %s", exc)
        err_event = {
            "type": "error",
            "code": "chat_error",
            "message": "An error occurred while generating the repository answer.",
        }
        yield f"data: {json.dumps(err_event)}\n\n"
