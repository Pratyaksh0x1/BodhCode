"""AI tool registry, base definitions, and standard tool factories."""

from app.ai.tools.base import Tool, ToolContext, ToolResult
from app.ai.tools.browser_tools import (
    BrowserActionTool,
    BrowserOpenTool,
    BrowserScreenshotTool,
)
from app.ai.tools.read_tools import (
    BlastRadiusTool,
    FindFilesTool,
    GetFileExportsTool,
    GetGraphSummaryTool,
    ListDependenciesTool,
    ListDependentsTool,
    ListFilesTool,
    ParseFileTool,
    ReadFileTool,
    SearchCodeTool,
    TranslateTextTool,
    UseSkillTool,
)
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.write_tools import CreateFileTool, DeleteFileTool, EditFileTool


def build_read_tools_registry() -> ToolRegistry:
    """Build a ToolRegistry populated with all read tools."""
    reg = ToolRegistry()
    reg.register(ParseFileTool())
    reg.register(GetGraphSummaryTool())
    reg.register(ListDependenciesTool())
    reg.register(ListDependentsTool())
    reg.register(BlastRadiusTool())
    reg.register(ListFilesTool())
    reg.register(ReadFileTool())
    reg.register(SearchCodeTool())
    reg.register(TranslateTextTool())
    reg.register(UseSkillTool())
    reg.register(BrowserOpenTool())
    reg.register(BrowserScreenshotTool())
    reg.register(BrowserActionTool())
    # Backwards compatibility with Phase 10 schemas
    reg.register(FindFilesTool())
    reg.register(GetFileExportsTool())
    return reg


def build_agent_tools_registry() -> ToolRegistry:
    """Build a ToolRegistry populated with both read tools and write proposal tools."""
    reg = build_read_tools_registry()
    reg.register(CreateFileTool())
    reg.register(EditFileTool())
    reg.register(DeleteFileTool())
    return reg


__all__ = [
    "BlastRadiusTool",
    "BrowserActionTool",
    "BrowserOpenTool",
    "BrowserScreenshotTool",
    "CreateFileTool",
    "DeleteFileTool",
    "EditFileTool",
    "FindFilesTool",
    "GetFileExportsTool",
    "GetGraphSummaryTool",
    "ListDependenciesTool",
    "ListDependentsTool",
    "ListFilesTool",
    "ParseFileTool",
    "ReadFileTool",
    "SearchCodeTool",
    "Tool",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "TranslateTextTool",
    "UseSkillTool",
    "build_agent_tools_registry",
    "build_read_tools_registry",
]
