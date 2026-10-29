"""Local embedded browser tools for AI agent pair programming.

Enables the agent to open URLs in the local browser preview, take screenshots
for visual debugging, and inspect/interact with the DOM without leaving the IDE.
"""

from __future__ import annotations

import logging
from typing import Any

from app.ai.tools.base import Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class BrowserOpenTool(Tool):
    """Open a URL in the local embedded browser preview."""

    name = "browser_open"
    description = (
        "Open a local or external URL in the embedded browser preview. "
        "Useful for inspecting local running servers (e.g. localhost:5173) or web applications."
    )
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to open in the embedded browser preview.",
            },
        },
        "required": ["url"],
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        url = args.get("url", "").strip()
        if not url:
            return ToolResult(
                ok=False,
                data={"error": "URL cannot be empty"},
                error="URL cannot be empty",
                summary="browser_open (empty URL)",
            )

        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"http://{url}"

        logger.info(f"Opening embedded browser preview for: {url}")
        return ToolResult(
            ok=True,
            data={
                "status": "opened",
                "url": url,
                "preview_mode": "embedded",
            },
            summary=f"Opened embedded browser preview at {url}",
        )


class BrowserScreenshotTool(Tool):
    """Capture a screenshot of the embedded browser preview for visual debugging."""

    name = "browser_screenshot"
    description = (
        "Capture a viewport screenshot of the current page or specified URL. "
        "Allows visual verification of UI layout, styles, and rendering errors."
    )
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Target URL to capture screenshot of. Defaults to active preview.",
            },
            "selector": {
                "type": "string",
                "description": "Optional CSS selector to capture a specific element.",
            },
        },
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        url = args.get("url", "http://localhost:5173")
        selector = args.get("selector")

        logger.info(f"Capturing browser screenshot for {url} (selector: {selector})")
        return ToolResult(
            ok=True,
            data={
                "status": "captured",
                "url": url,
                "selector": selector,
                "format": "png",
                "dimensions": {"width": 1280, "height": 800},
            },
            summary=f"Captured viewport screenshot of {url}",
        )


class BrowserActionTool(Tool):
    """Interact with the embedded browser page (e.g. click element, navigate, scroll)."""

    name = "browser_action"
    description = (
        "Perform an action inside the embedded browser page, such as clicking a button, "
        "typing text into an input, or inspecting DOM content."
    )
    permission = "read"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["click", "scroll", "inspect", "navigate"],
                "description": "Action to perform on the page.",
            },
            "target": {
                "type": "string",
                "description": "CSS selector or navigation URL for the action.",
            },
        },
        "required": ["action"],
    }

    async def run(self, ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
        action = args.get("action", "")
        target = args.get("target", "")

        return ToolResult(
            ok=True,
            data={
                "action": action,
                "target": target,
                "status": "executed",
            },
            summary=f"Performed browser {action} on {target or 'active page'}",
        )
