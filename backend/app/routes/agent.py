"""FastAPI routes for coding agent execution with SSE streaming."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.ai.agent import (
    AgentRequest,
    acquire_agent_slot,
    prepare_agent_conversation,
    release_agent_slot,
    run_agent_turn,
)
from app.auth.deps import get_current_user
from app.db import get_session
from app.files.service import get_repo_source_dir
from app.models.graph import RepoGraph
from app.models.repo import Repo
from app.models.user import User
from app.parser.blast import to_digraph
from app.parser.graph import PARSER_VERSION, GraphDoc

router = APIRouter(prefix="/repos", tags=["Agent"])

# Cache for parsed networkx DiGraphs
_GRAPH_CACHE: dict[int, Any] = {}


def _get_cached_digraph(repo_graph: RepoGraph) -> Any:
    """Retrieve or deserialize networkx DiGraph from stored GraphDoc."""
    if repo_graph.id in _GRAPH_CACHE:
        return _GRAPH_CACHE[repo_graph.id]

    doc = GraphDoc.model_validate_json(repo_graph.graph_json)
    graph = to_digraph(doc)
    _GRAPH_CACHE[repo_graph.id] = graph
    return graph


def _get_repo_and_graph(
    repo_id: int,
    user: User,
    session: Session,
) -> tuple[Repo, RepoGraph]:
    """Verify repo ownership and fetch Repo and RepoGraph."""
    stmt = select(Repo).where(Repo.id == repo_id, Repo.user_id == user.id)
    repo = session.exec(stmt).first()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    if repo.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "repo_not_ready", "message": "Repository is not in ready state"},
        )

    graph_stmt = select(RepoGraph).where(
        RepoGraph.repo_id == repo.id,
        RepoGraph.commit_sha == repo.commit_sha,
        RepoGraph.parser_version == PARSER_VERSION,
    )
    repo_graph = session.exec(graph_stmt).first()
    if repo_graph is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "repo_not_ready", "message": "Repository graph not found"},
        )

    return repo, repo_graph


@router.post("/{repo_id}/agent")
async def run_agent_endpoint(
    repo_id: int,
    payload: AgentRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> StreamingResponse:
    """Run an interactive agent turn streaming tool steps, proposals, tokens, and verification."""
    repo, repo_graph = _get_repo_and_graph(repo_id, current_user, session)

    acquired = await acquire_agent_slot(current_user.id, repo.id)
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "agent_in_progress",
                "message": "An agent run is already in progress for this repository.",
            },
        )

    # Determine effective review mode for this turn
    review_mode = payload.review_mode or current_user.review_mode or "review"
    if review_mode not in ("review", "auto", "readonly"):
        await release_agent_slot(current_user.id, repo.id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid review_mode '{review_mode}'. Allowed: review, auto, readonly.",
        )

    graph = _get_cached_digraph(repo_graph)
    source_dir: Path | None = None
    try:
        source_dir = get_repo_source_dir(repo)
    except Exception:
        source_dir = None

    language = current_user.preferred_language or "en"
    conversation = prepare_agent_conversation(
        message=payload.message,
        history=payload.history,
        language=language,
        active_file=payload.active_file,
        selection=payload.selection,
        review_mode=review_mode,
    )

    async def sse_event_stream():
        try:
            stream_gen = run_agent_turn(
                request=request,
                user=current_user,
                repo=repo,
                graph=graph,
                session=session,
                conversation=conversation,
                review_mode=review_mode,
                source_dir=source_dir,
            )

            stream_iter = stream_gen.__aiter__()
            while True:
                if await request.is_disconnected():
                    break

                try:
                    chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=15.0)
                    yield chunk
                except TimeoutError:
                    yield ": heartbeat\n\n"
                except StopAsyncIteration:
                    break
        finally:
            await release_agent_slot(current_user.id, repo.id)

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
