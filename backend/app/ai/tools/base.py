"""Base abstractions for AI tool calling framework."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import networkx as nx
from pydantic import BaseModel, Field


@dataclass
class ToolContext:
    """Execution context provided to tools during agent or chat turn."""

    user: Any
    repo: Any
    graph: nx.DiGraph
    files: Any  # File service adapter bound to user and repo
    review_mode: str = "review"  # "review" | "auto" | "readonly"
    session: Any = None  # SQLModel DB session
    session_id: str | None = None  # Turn session identifier
    skill_depth: int = 0
    allowed_tools: set[str] | None = None
    emit: Callable[[dict[str, Any]], Awaitable[None]] | None = None
    source_dir: Path | None = None


class ToolResult(BaseModel):
    """Outcome of a single tool execution."""

    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    proposal_id: int | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert result to serializable dictionary for LLM and event streams."""
        res: dict[str, Any] = {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "summary": self.summary,
        }
        if self.proposal_id is not None:
            res["proposal_id"] = self.proposal_id
        return res


class Tool:
    """Abstract interface for all agent and chat tools."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    permission: Literal["read", "write"]

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        """Execute the tool with given context and validated arguments."""
        raise NotImplementedError
