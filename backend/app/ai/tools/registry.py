"""Tool registry with schema validation, permission checks, timeouts, and error handling."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import jsonschema

from app.ai.tools.base import Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

MAX_RAW_ARGS_CHARS = 65536
TOOL_EXECUTION_TIMEOUT_SECONDS = 20.0


class ToolRegistry:
    """Registry managing tool schemas and safe execution dispatching."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Retrieve tool by name."""
        return self._tools.get(name)

    def schemas(self, allowed: set[str] | None = None) -> list[dict[str, Any]]:
        """Return function calling schemas compatible with Groq / OpenAI tool specs."""
        result: list[dict[str, Any]] = []
        for tool in self._tools.values():
            if allowed is not None and tool.name not in allowed:
                continue
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return result

    async def dispatch(
        self,
        ctx: ToolContext,
        name: str,
        raw_args: dict[str, Any] | Any,
    ) -> ToolResult:
        """Safely validate and execute a tool call."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                ok=False,
                data={"error": f"Unknown tool '{name}'."},
                error=f"Unknown tool '{name}'.",
                summary=f"unknown tool {name}",
            )

        if ctx.allowed_tools is not None and name not in ctx.allowed_tools:
            return ToolResult(
                ok=False,
                data={"error": f"Tool '{name}' is not permitted."},
                error=f"Tool '{name}' is not permitted.",
                summary=f"{name} (not permitted)",
            )

        if not isinstance(raw_args, dict):
            return ToolResult(
                ok=False,
                data={"error": f"Tool arguments for '{name}' must be a dictionary."},
                error=f"Tool arguments for '{name}' must be a dictionary.",
                summary=f"{name} (invalid args)",
            )

        # Cap argument size
        try:
            dumped = json.dumps(raw_args)
            if len(dumped) > MAX_RAW_ARGS_CHARS:
                err_msg = f"Argument size for '{name}' exceeds limit of {MAX_RAW_ARGS_CHARS} chars."
                return ToolResult(
                    ok=False,
                    data={"error": err_msg},
                    error=err_msg,
                    summary=f"{name} (args too large)",
                )
        except Exception as exc:
            return ToolResult(
                ok=False,
                data={"error": f"Argument serialization error for '{name}': {exc}"},
                error=f"Argument serialization error for '{name}': {exc}",
                summary=f"{name} (invalid args)",
            )

        # Validate against tool JSON schema
        try:
            jsonschema.validate(instance=raw_args, schema=tool.parameters)
        except jsonschema.ValidationError as val_err:
            return ToolResult(
                ok=False,
                data={"error": f"Invalid arguments for tool '{name}': {val_err.message}"},
                error=f"Invalid arguments for tool '{name}': {val_err.message}",
                summary=f"{name} (invalid args)",
            )

        # Execute with timeout and error containment
        try:
            return await asyncio.wait_for(
                tool.run(ctx, raw_args),
                timeout=TOOL_EXECUTION_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            tout_msg = f"Tool '{name}' timed out after {TOOL_EXECUTION_TIMEOUT_SECONDS}s."
            return ToolResult(
                ok=False,
                data={"error": tout_msg},
                error=tout_msg,
                summary=f"{name} (timeout)",
            )
        except Exception as exc:
            logger.exception("Unexpected exception in tool %s: %s", name, exc)
            return ToolResult(
                ok=False,
                data={"error": f"Tool error in '{name}': {exc}"},
                error=f"Tool error in '{name}': {exc}",
                summary=f"{name} (error)",
            )
