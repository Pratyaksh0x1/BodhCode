"""BodhCode coding agent loop with tool dispatching, review policy, and SSE streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import networkx as nx
from fastapi import Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.ai.llm import LLMClient, LLMResult, get_llm_client
from app.ai.prompts.agent import AGENT_PROMPT_VERSION, build_agent_system_message
from app.ai.tools import (
    ToolContext,
    ToolRegistry,
    ToolResult,
    build_agent_tools_registry,
)
from app.ai.tracing import traced
from app.ai.untrusted import truncate
from app.ai.verify import extract_path_mentions, verify_mentions
from app.files.service import BoundFileService
from app.models.proposals import Proposal
from app.models.repo import Repo
from app.models.user import User

logger = logging.getLogger(__name__)

MAX_AGENT_STEPS = 10
AGENT_TIMEOUT_SECONDS = 60.0

# Concurrency slot tracking: one in-flight agent run per user per repo
_ACTIVE_AGENT_RUNS: set[tuple[int, int]] = set()
_AGENT_LOCK = asyncio.Lock()


async def acquire_agent_slot(user_id: int, repo_id: int) -> bool:
    """Acquire single-flight agent run slot. Returns False if already running."""
    async with _AGENT_LOCK:
        if (user_id, repo_id) in _ACTIVE_AGENT_RUNS:
            return False
        _ACTIVE_AGENT_RUNS.add((user_id, repo_id))
        return True


async def release_agent_slot(user_id: int, repo_id: int) -> None:
    """Release single-flight agent run slot."""
    async with _AGENT_LOCK:
        _ACTIVE_AGENT_RUNS.discard((user_id, repo_id))


class SelectionModel(BaseModel):
    """Editor selection snippet payload."""

    path: str
    start_line: int
    end_line: int
    text: str


class AgentHistoryItem(BaseModel):
    """Historical conversation turn item."""

    role: str
    content: str = ""


class AgentRequest(BaseModel):
    """Agent run request body."""

    message: str
    history: list[AgentHistoryItem] = Field(default_factory=list)
    review_mode: str | None = None
    active_file: str | None = None
    selection: SelectionModel | None = None


def prepare_agent_conversation(
    message: str,
    history: list[AgentHistoryItem],
    language: str,
    active_file: str | None,
    selection: SelectionModel | None,
    review_mode: str,
) -> list[dict[str, Any]]:
    """Assemble agent prompt conversation including system prompt and history."""
    sel_dict = selection.model_dump() if selection else None
    system_msg = build_agent_system_message(
        language=language,
        active_file=active_file,
        selection=sel_dict,
        review_mode=review_mode,
    )

    # Take up to last 10 turns
    recent = history[-10:] if len(history) > 10 else history
    conversation: list[dict[str, Any]] = [system_msg]

    for item in recent:
        role = item.role if item.role in ("user", "assistant") else "user"
        conversation.append({"role": role, "content": item.content})

    conversation.append({"role": "user", "content": message})
    return conversation


@traced(name="agent.turn", run_type="chain")
async def run_agent_turn(
    request: Request,
    user: User,
    repo: Repo,
    graph: nx.DiGraph,
    session: Session,
    conversation: list[dict[str, Any]],
    review_mode: str,
    source_dir: Path | None = None,
    llm_client: LLMClient | None = None,
    registry: ToolRegistry | None = None,
) -> AsyncIterator[str]:
    """Execute multi-step agent loop and stream SSE events to client."""
    client = llm_client or get_llm_client()
    reg = registry or build_agent_tools_registry()
    files_svc = BoundFileService(user=user, repo=repo, session=session)

    session_id = str(uuid.uuid4())
    tool_ctx = ToolContext(
        user=user,
        repo=repo,
        graph=graph,
        files=files_svc,
        review_mode=review_mode,
        session=session,
        session_id=session_id,
        source_dir=source_dir,
    )

    tools_schemas = reg.schemas()
    step_count = 0
    start_time = time.monotonic()
    proposals_emitted: list[int] = []
    accumulated_answer = ""

    try:
        while step_count < MAX_AGENT_STEPS:
            # 1. Disconnect check
            if await request.is_disconnected():
                logger.info("Client disconnected from agent stream.")
                return

            # 2. Timeout check (60 seconds)
            elapsed = time.monotonic() - start_time
            if elapsed >= AGENT_TIMEOUT_SECONDS:
                logger.warning("Agent run reached %ds timeout.", AGENT_TIMEOUT_SECONDS)
                timeout_event = {
                    "type": "error",
                    "error": f"Agent reached time limit of {AGENT_TIMEOUT_SECONDS} seconds.",
                }
                yield f"data: {json.dumps(timeout_event)}\n\n"
                break

            # 3. LLM call
            llm_result: LLMResult = await client.chat(
                messages=conversation,
                tools=tools_schemas,
                feature="agent.loop",
                temperature=0.1,
                max_tokens=1536,
                prompt_name="agent",
                prompt_version=AGENT_PROMPT_VERSION,
            )

            if not llm_result.tool_calls:
                accumulated_answer = llm_result.text or ""
                break

            assistant_tool_calls_payload = []
            executed_results: list[tuple[Any, dict[str, Any]]] = []

            for tc in llm_result.tool_calls:
                step_count += 1
                args_summary = truncate(json.dumps(tc.arguments), max_chars=120)

                # Tool dispatch
                tool_res: ToolResult = await reg.dispatch(tool_ctx, tc.name, tc.arguments)
                tool_output = (
                    tool_res.data
                    if tool_res.ok
                    else (
                        tool_res.data
                        if "error" in tool_res.data
                        else {"error": tool_res.error or "Tool execution failed"}
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
                    "ok": tool_res.ok,
                    "result_summary": result_summary,
                    "proposal_id": tool_res.proposal_id,
                }
                yield f"data: {json.dumps(step_event)}\n\n"

                # If this write tool created or updated a proposal, emit proposal event
                if tool_res.proposal_id and tool_res.proposal_id not in proposals_emitted:
                    prop_stmt = select(Proposal).where(Proposal.id == tool_res.proposal_id)
                    p_model = session.exec(prop_stmt).first()
                    if p_model:
                        proposals_emitted.append(p_model.id)  # type: ignore
                        prop_event = {
                            "type": "proposal",
                            "id": p_model.id,
                            "kind": p_model.kind,
                            "path": p_model.path,
                            "rationale": p_model.rationale,
                            "blast_radius_count": p_model.blast_radius_count,
                            "status": p_model.status,
                            "new_content": p_model.new_content,
                            "old_content": p_model.old_content,
                        }
                        yield f"data: {json.dumps(prop_event)}\n\n"

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

                if step_count >= MAX_AGENT_STEPS:
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

            if step_count >= MAX_AGENT_STEPS:
                break

        # Stream final tokens
        if accumulated_answer:
            # Chunk words for fluid typing appearance
            words = accumulated_answer.split(" ")
            for i, w in enumerate(words):
                token_chunk = w + (" " if i < len(words) - 1 else "")
                token_event = {"type": "token", "token": token_chunk}
                yield f"data: {json.dumps(token_event)}\n\n"

        # Emit filename verification event
        mentions = extract_path_mentions(accumulated_answer)
        verified, flagged = verify_mentions(mentions, graph)
        verif_event = {
            "type": "verification",
            "verified": verified,
            "flagged": flagged,
        }
        yield f"data: {json.dumps(verif_event)}\n\n"

        # Emit done event
        done_event = {
            "type": "done",
            "total_steps": step_count,
            "proposals_count": len(proposals_emitted),
        }
        yield f"data: {json.dumps(done_event)}\n\n"

    except Exception as exc:
        logger.exception("Unexpected error in agent turn: %s", exc)
        err_event = {"type": "error", "error": f"Agent error: {exc}"}
        yield f"data: {json.dumps(err_event)}\n\n"
