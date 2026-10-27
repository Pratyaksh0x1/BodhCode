"""Routes for grounded file explanation and repository chat agent."""

import asyncio
import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.ai.chat import (
    ChatRequest,
    acquire_chat_slot,
    prepare_conversation_history,
    release_chat_slot,
    run_chat_stream,
)
from app.ai.explain import ExplainResult, explain_file
from app.auth.deps import get_current_user
from app.config import get_settings
from app.db import get_session
from app.i18n.languages import is_supported
from app.models.graph import RepoGraph
from app.models.repo import Repo
from app.models.user import User
from app.parser.graph import PARSER_VERSION
from app.routes.graph_cache import get_cached_digraph

router = APIRouter(prefix="/repos", tags=["Explain & Chat"])


class ExplainRequest(BaseModel):
    """File explanation request body."""

    file: str = Field(description="Exact file path in repository graph.")


def _get_repo_and_graph(
    repo_id: int,
    user: User,
    session: Session,
) -> tuple[Repo, RepoGraph]:
    """Verify repo ownership and ready status, and fetch RepoGraph."""
    statement = select(Repo).where(
        Repo.id == repo_id,
        Repo.user_id == user.id,
    )
    repo = session.exec(statement).first()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    if repo.commit_sha is None or repo.status != "ready":
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


def _resolve_language(lang: str | None, user: User) -> str:
    """Validate and resolve requested language against catalogue."""
    target = lang.lower().strip() if lang and lang.strip() else (user.preferred_language or "en")
    if not is_supported(target):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported language code '{target}'. See /meta/languages.",
        )
    return target


@router.post("/{repo_id}/explain", response_model=ExplainResult)
async def explain_file_endpoint(
    repo_id: int,
    payload: ExplainRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    lang: str | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> ExplainResult:
    """Explain a file's role in the codebase, grounded in the dependency graph."""
    repo, repo_graph = _get_repo_and_graph(repo_id, current_user, session)
    language = _resolve_language(lang, current_user)

    graph = get_cached_digraph(repo_graph)
    target_file = payload.file.strip().replace("\\", "/")

    if target_file not in graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "file_not_in_graph",
                "message": f"File '{target_file}' not found in repository graph",
            },
        )

    settings = get_settings()
    source_dir = (
        Path(settings.DATA_DIR)
        / "repos"
        / repo.owner
        / repo.name
        / (repo.commit_sha or "HEAD")
        / "src"
    )

    return await explain_file(
        repo=repo,
        file_path=target_file,
        language=language,
        graph=graph,
        source_dir=source_dir if source_dir.exists() else None,
        session=session,
        refresh=refresh,
    )


@router.post("/{repo_id}/chat")
async def chat_endpoint(
    repo_id: int,
    payload: ChatRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    lang: str | None = Query(default=None),
) -> StreamingResponse:
    """Execute streaming repository architecture chat agent turn (SSE)."""
    repo, repo_graph = _get_repo_and_graph(repo_id, current_user, session)
    language = _resolve_language(lang, current_user)

    # Concurrency control: 1 in-flight chat per user per repo
    acquired = await acquire_chat_slot(current_user.id, repo.id)
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "chat_in_progress",
                "message": "A chat request is already running for this repository.",
            },
        )

    graph = get_cached_digraph(repo_graph)
    settings = get_settings()
    source_dir = (
        Path(settings.DATA_DIR)
        / "repos"
        / repo.owner
        / repo.name
        / (repo.commit_sha or "HEAD")
        / "src"
    )

    conversation = prepare_conversation_history(payload.messages, language)

    async def sse_event_stream():
        try:
            stream_gen = run_chat_stream(
                request=request,
                conversation=conversation,
                graph=graph,
                source_dir=source_dir if source_dir.exists() else None,
            )

            # Max turn timeout: 120 seconds
            async def run_with_timeout():
                async for event_chunk in stream_gen:
                    yield event_chunk

            # Run with periodic heartbeat every 15 seconds
            timeout_seconds = 120.0
            start_time = asyncio.get_event_loop().time()

            stream_iter = stream_gen.__aiter__()
            while True:
                if await request.is_disconnected():
                    break

                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout_seconds:
                    timeout_payload = json.dumps({
                        "type": "error",
                        "code": "timeout",
                        "message": "Chat turn timed out after 120 seconds.",
                    })
                    yield f"data: {timeout_payload}\n\n"
                    break

                try:
                    # Wait up to 15s for the next SSE chunk
                    chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=15.0)
                    yield chunk
                except TimeoutError:
                    # Send heartbeat comment to keep connection alive
                    yield ": heartbeat\n\n"
                except StopAsyncIteration:
                    break

        finally:
            await release_chat_slot(current_user.id, repo.id)

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
