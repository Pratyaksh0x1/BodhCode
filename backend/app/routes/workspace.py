"""Workspace AST analysis and interactive grounded ping endpoints."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user, require_csrf_header
from app.models.user import User
from app.parser.cli import analyze_directory
from app.parser.graph import PARSER_VERSION

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspace",
    tags=["Workspace"],
    dependencies=[Depends(require_csrf_header)],
)

# In-memory cache for latest analyzed workspace graph
_WORKSPACE_CACHE: dict[str, Any] = {}


class WorkspaceAnalyzeRequest(BaseModel):
    """Request payload to analyze a local directory."""

    path: str = Field(default=".", description="Local folder path to analyze.")


class WorkspacePingRequest(BaseModel):
    """Request payload to ask a grounded question about the workspace AST."""

    question: str = Field(
        min_length=1, max_length=1000, description="Question about workspace structure."
    )
    path: str = Field(default=".", description="Target workspace directory path.")


class WorkspacePingResponse(BaseModel):
    """Response containing grounded AST answers and verified paths."""

    answer: str
    verified_paths: list[str]
    nodes_count: int
    edges_count: int


@router.get("/graph")
def get_workspace_graph(
    current_user: Annotated[User, Depends(get_current_user)],
    dir_path: str = Query(default=".", description="Directory path to analyze"),
) -> dict[str, Any]:
    """Deterministically analyze and return the AST dependency graph of the workspace.

    Graph nodes and edges come strictly from pure Tree-Sitter parsing and graph math.
    """
    resolved_path = Path(dir_path).resolve()
    cache_key = str(resolved_path)
    if cache_key in _WORKSPACE_CACHE:
        return _WORKSPACE_CACHE[cache_key]

    try:
        result = analyze_directory(resolved_path)
        _WORKSPACE_CACHE[cache_key] = result
        return result
    except Exception as exc:
        logger.error(f"Failed to analyze workspace at {resolved_path}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse workspace directory: {exc}",
        ) from exc


@router.post("/analyze")
def analyze_workspace_dir(
    payload: WorkspaceAnalyzeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Force re-analysis of a workspace directory."""
    resolved_path = Path(payload.path).resolve()

    try:
        result = analyze_directory(resolved_path)
        _WORKSPACE_CACHE[str(resolved_path)] = result
        return result
    except Exception as exc:
        logger.error(f"Failed to analyze workspace at {resolved_path}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse workspace directory: {exc}",
        ) from exc


@router.post("/ping", response_model=WorkspacePingResponse)
def ping_workspace(
    payload: WorkspacePingRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> WorkspacePingResponse:
    """Ask a question about the workspace grounded in the AST graph.

    Adheres strictly to AGENTS.md:
    Graph nodes and edges come only from tree-sitter parsing.
    Verified filenames only; text is pure data.
    """
    resolved_path = Path(payload.path).resolve()
    cache_key = str(resolved_path)
    if cache_key not in _WORKSPACE_CACHE:
        # Check if any cache entry exists
        if _WORKSPACE_CACHE:
            data = next(iter(_WORKSPACE_CACHE.values()))
        else:
            data = analyze_directory(resolved_path)
            _WORKSPACE_CACHE[cache_key] = data
    else:
        data = _WORKSPACE_CACHE[cache_key]

    graph = data.get("graph", {})
    if hasattr(graph, "nodes"):
        raw_nodes = graph.nodes
        raw_edges = graph.edges
    elif isinstance(graph, dict):
        raw_nodes = graph.get("nodes", [])
        raw_edges = graph.get("edges", [])
    else:
        raw_nodes = []
        raw_edges = []

    all_file_paths: list[str] = []
    for n in raw_nodes:
        if isinstance(n, dict):
            nid = n.get("id")
            if nid:
                all_file_paths.append(str(nid))
        elif hasattr(n, "id"):
            all_file_paths.append(str(n.id))

    # Find question keywords matching verified paths
    q_lower = payload.question.lower()
    matched_paths = [
        p for p in all_file_paths if Path(p).name.lower() in q_lower or p.lower() in q_lower
    ]

    if not matched_paths and all_file_paths:
        matched_paths = all_file_paths[:5]

    matched_str = ", ".join(matched_paths[:10])
    summary_text = (
        f"Workspace graph contains {len(raw_nodes)} verified nodes and {len(raw_edges)} edges "
        f"(Parser v{PARSER_VERSION}). Relevant components: {matched_str}."
    )

    return WorkspacePingResponse(
        answer=summary_text,
        verified_paths=matched_paths,
        nodes_count=len(raw_nodes),
        edges_count=len(raw_edges),
    )
