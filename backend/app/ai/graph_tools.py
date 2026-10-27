"""Grounded graph tools and schemas over dependency graphs.

Pure functions that inspect the stored dependency DiGraph and read validated source files.
Every tool validates arguments and returns a JSON-serializable dictionary.
Errors return {"error": "...", "suggestions": [...]} instead of raising exceptions.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

import networkx as nx

from app.ai.untrusted import wrap_untrusted
from app.parser.blast import blast_radius as blast_algo

# ---------------------------------------------------------------------------
# JSON Schemas for LLM Tool Calling (Clean, standard function definitions)
# ---------------------------------------------------------------------------

GRAPH_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_dependencies",
            "description": (
                "List direct internal module dependencies (imports) and external NPM/package "
                "dependencies for a given file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Exact file path in repo (e.g., 'src/auth/jwt.ts').",
                    },
                },
                "required": ["file"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dependents",
            "description": (
                "List direct importers (dependents) that import or re-export the specified file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Exact file path in repo (e.g., 'src/auth/jwt.ts').",
                    },
                },
                "required": ["file"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "blast_radius",
            "description": (
                "Compute the transitive blast radius (impacted downstream files) if the "
                "specified file is modified, ordered by BFS distance depth."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Exact file path in repo (e.g., 'src/auth/jwt.ts').",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum BFS traversal depth. Defaults to 3.",
                        "default": 3,
                    },
                },
                "required": ["file"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_files",
            "description": (
                "Search for valid file paths in the repository using case-insensitive substring "
                "or fuzzy matching. Never returns paths that do not exist in the graph."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query or partial name (e.g. 'auth', 'Button.tsx').",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (max 20).",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_exports",
            "description": (
                "Retrieve the named export symbols and default export status for a given file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Exact file path in repo (e.g., 'src/auth/jwt.ts').",
                    },
                },
                "required": ["file"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read lines from a verified source code file in the repository. "
                "Capped at 300 lines and 12,000 characters per call. "
                "The file MUST be an existing node in the graph."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "Exact file path in repo (e.g., 'src/auth/jwt.ts').",
                    },
                    "start": {
                        "type": "integer",
                        "description": "1-based starting line number. Defaults to 1.",
                        "default": 1,
                    },
                    "end": {
                        "type": "integer",
                        "description": "1-based ending line number. Defaults to 200.",
                        "default": 200,
                    },
                },
                "required": ["file"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_graph_summary",
            "description": (
                "Get high-level repository graph statistics including file counts, "
                "edge counts, cycles count, and top 10 files with the highest number of dependents."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Helper: Find similar valid paths
# ---------------------------------------------------------------------------


def find_similar_files(graph: nx.DiGraph, file: str, limit: int = 5) -> list[str]:
    """Find up to limit closest matching valid node ids in the graph."""
    if not graph.nodes:
        return []
    nodes = list(graph.nodes)
    matches = difflib.get_close_matches(file, nodes, n=limit, cutoff=0.3)
    if not matches and "/" in file:
        bare_name = file.split("/")[-1].lower()
        matches = [n for n in nodes if n.lower().endswith(bare_name)][:limit]
    return matches


# ---------------------------------------------------------------------------
# Core Tool Implementations
# ---------------------------------------------------------------------------


def list_dependencies(graph: nx.DiGraph, file: str) -> dict[str, Any]:
    """List direct module dependencies (successors) and external dependencies."""
    if not isinstance(file, str) or not file.strip():
        return {
            "error": "Argument 'file' must be a non-empty string.",
            "suggestions": [],
        }

    file = file.strip().replace("\\", "/")
    if file not in graph:
        return {
            "error": f"File '{file}' not found in dependency graph.",
            "suggestions": find_similar_files(graph, file),
        }

    dependencies = []
    for succ in sorted(graph.successors(file)):
        edge_data = graph[file][succ]
        kinds = sorted(list(edge_data.get("kinds", ["import"])))
        type_only = bool(edge_data.get("type_only", False))
        dependencies.append(
            {
                "file": succ,
                "kinds": kinds,
                "type_only": type_only,
            }
        )

    node_data = graph.nodes[file]
    external_packages = sorted(node_data.get("external_deps", []))

    return {
        "file": file,
        "dependencies": dependencies,
        "external_packages": external_packages,
        "total_internal_deps": len(dependencies),
        "total_external_deps": len(external_packages),
    }


def list_dependents(graph: nx.DiGraph, file: str) -> dict[str, Any]:
    """List direct importers (predecessors) that depend on file."""
    if not isinstance(file, str) or not file.strip():
        return {
            "error": "Argument 'file' must be a non-empty string.",
            "suggestions": [],
        }

    file = file.strip().replace("\\", "/")
    if file not in graph:
        return {
            "error": f"File '{file}' not found in dependency graph.",
            "suggestions": find_similar_files(graph, file),
        }

    dependents = []
    for pred in sorted(graph.predecessors(file)):
        edge_data = graph[pred][file]
        kinds = sorted(list(edge_data.get("kinds", ["import"])))
        type_only = bool(edge_data.get("type_only", False))
        dependents.append(
            {
                "file": pred,
                "kinds": kinds,
                "type_only": type_only,
            }
        )

    return {
        "file": file,
        "dependents": dependents,
        "total": len(dependents),
    }


def blast_radius(
    graph: nx.DiGraph,
    file: str,
    max_depth: int = 3,
) -> dict[str, Any]:
    """Calculate transitive downstream blast radius impacts."""
    if not isinstance(file, str) or not file.strip():
        return {
            "error": "Argument 'file' must be a non-empty string.",
            "suggestions": [],
        }

    file = file.strip().replace("\\", "/")
    if file not in graph:
        return {
            "error": f"File '{file}' not found in dependency graph.",
            "suggestions": find_similar_files(graph, file),
        }

    try:
        max_depth = int(max_depth)
        if max_depth <= 0:
            max_depth = 3
    except (ValueError, TypeError):
        max_depth = 3

    impacts = blast_algo(graph, file, max_depth=max_depth)
    truncated = len(impacts) > 200

    return {
        "file": file,
        "max_depth": max_depth,
        "total": len(impacts),
        "impacts": impacts[:200],
        "truncated": truncated,
    }


def find_files(graph: nx.DiGraph, query: str, limit: int = 20) -> dict[str, Any]:
    """Search for valid files in the graph using case-insensitive match."""
    if not isinstance(query, str):
        return {"query": str(query), "matches": [], "total_matches": 0}

    q = query.strip().lower()
    if not q:
        return {"query": query, "matches": [], "total_matches": 0}

    try:
        limit = min(max(1, int(limit)), 20)
    except (ValueError, TypeError):
        limit = 20

    nodes = sorted(graph.nodes)
    substring_matches = [n for n in nodes if q in n.lower()]

    fuzzy_matches = difflib.get_close_matches(q, nodes, n=limit, cutoff=0.3)

    # Combine preserving order and uniqueness
    seen = set()
    combined: list[str] = []
    for match in substring_matches + fuzzy_matches:
        if match not in seen:
            seen.add(match)
            combined.append(match)

    return {
        "query": query,
        "matches": combined[:limit],
        "total_matches": len(combined),
    }


def get_file_exports(graph: nx.DiGraph, file: str) -> dict[str, Any]:
    """Retrieve named exports and default-export status for a file."""
    if not isinstance(file, str) or not file.strip():
        return {
            "error": "Argument 'file' must be a non-empty string.",
            "suggestions": [],
        }

    file = file.strip().replace("\\", "/")
    if file not in graph:
        return {
            "error": f"File '{file}' not found in dependency graph.",
            "suggestions": find_similar_files(graph, file),
        }

    node_data = graph.nodes[file]
    exports = sorted(node_data.get("exports", []))
    has_default = bool(node_data.get("has_default_export", False))

    return {
        "file": file,
        "exports": exports,
        "has_default_export": has_default,
    }


def read_file(
    graph: nx.DiGraph,
    file: str,
    source_dir: Path | None,
    start: int = 1,
    end: int = 200,
) -> dict[str, Any]:
    """Read bounded source code lines from a verified repository file."""
    if not isinstance(file, str) or not file.strip():
        return {
            "error": "Argument 'file' must be a non-empty string.",
            "suggestions": [],
        }

    file = file.strip().replace("\\", "/")
    if file not in graph:
        return {
            "error": f"File '{file}' not found in dependency graph.",
            "suggestions": find_similar_files(graph, file),
        }

    if source_dir is None:
        return {"error": "Repository source directory is not configured."}

    resolved_base = source_dir.resolve()
    target_path = (source_dir / file).resolve()

    # Path traversal protection: target must be inside source_dir
    try:
        target_path.relative_to(resolved_base)
    except ValueError:
        return {"error": f"Path '{file}' attempts path traversal outside source repository."}

    if not target_path.is_file():
        return {"error": f"File '{file}' does not exist on disk."}

    try:
        start_line = max(1, int(start))
    except (ValueError, TypeError):
        start_line = 1

    try:
        end_line = max(start_line, int(end))
    except (ValueError, TypeError):
        end_line = start_line + 199

    # Cap at 300 lines per call
    max_lines = 300
    if end_line - start_line + 1 > max_lines:
        end_line = start_line + max_lines - 1

    try:
        raw_text = target_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"error": f"Failed to read file: {exc}"}

    lines = raw_text.splitlines()
    total_lines = len(lines)

    selected_lines = lines[start_line - 1 : end_line]
    actual_end_line = min(start_line + len(selected_lines) - 1, total_lines)

    # Format lines with numbers: "1: import ..."
    formatted_lines = [
        f"{start_line + idx}: {line}" for idx, line in enumerate(selected_lines)
    ]
    content_str = "\n".join(formatted_lines)

    # Character cap: 12,000 characters
    max_chars = 12000
    truncated = False
    if len(content_str) > max_chars:
        content_str = content_str[:max_chars] + "\n[truncated]"
        truncated = True

    wrapped = wrap_untrusted(content_str, kind="source_code")

    return {
        "file": file,
        "start_line": start_line,
        "end_line": actual_end_line,
        "total_lines": total_lines,
        "content": wrapped,
        "truncated": truncated,
    }


def get_graph_summary(graph: nx.DiGraph) -> dict[str, Any]:
    """Calculate high-level metrics: counts, fan-in ranking, and cycles."""
    total_files = graph.number_of_nodes()
    total_edges = graph.number_of_edges()

    # Collect unique external packages
    external_pkgs = set()
    for _, data in graph.nodes(data=True):
        for pkg in data.get("external_deps", []):
            external_pkgs.add(pkg)

    # Fan-in ranking: in_degree counts direct importers
    in_degrees = [
        {"file": node, "dependents_count": deg}
        for node, deg in graph.in_degree()
    ]
    in_degrees.sort(key=lambda x: (-x["dependents_count"], x["file"]))
    top_files = in_degrees[:10]

    # Cycles count: strongly connected components with >1 node
    cycles_count = sum(
        1 for scc in nx.strongly_connected_components(graph) if len(scc) > 1
    )

    return {
        "total_files": total_files,
        "total_edges": total_edges,
        "total_external_packages": len(external_pkgs),
        "top_files_by_dependents": top_files,
        "cycles_count": cycles_count,
    }


# ---------------------------------------------------------------------------
# GraphTools Dispatcher Class
# ---------------------------------------------------------------------------


class GraphTools:
    """Execution dispatcher over a specific repository graph and source directory."""

    def __init__(self, graph: nx.DiGraph, source_dir: Path | None = None) -> None:
        self.graph = graph
        self.source_dir = source_dir

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a tool call by name and validate inputs."""
        if tool_name == "list_dependencies":
            return list_dependencies(self.graph, file=arguments.get("file", ""))
        elif tool_name == "list_dependents":
            return list_dependents(self.graph, file=arguments.get("file", ""))
        elif tool_name == "blast_radius":
            return blast_radius(
                self.graph,
                file=arguments.get("file", ""),
                max_depth=arguments.get("max_depth", 3),
            )
        elif tool_name == "find_files":
            return find_files(
                self.graph,
                query=arguments.get("query", ""),
                limit=arguments.get("limit", 20),
            )
        elif tool_name == "get_file_exports":
            return get_file_exports(self.graph, file=arguments.get("file", ""))
        elif tool_name == "read_file":
            return read_file(
                self.graph,
                file=arguments.get("file", ""),
                source_dir=self.source_dir,
                start=arguments.get("start", 1),
                end=arguments.get("end", 200),
            )
        elif tool_name == "get_graph_summary":
            return get_graph_summary(self.graph)
        else:
            return {"error": f"Unknown tool '{tool_name}'."}
