"""GitHub repository content viewing and translation endpoints."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth.crypto import get_github_token
from app.auth.deps import get_current_user
from app.db import get_session
from app.github.client import GitHubClient, GitHubClientError, RateLimited, RepoNotFound
from app.i18n.detect import detect_language
from app.i18n.languages import is_supported
from app.i18n.translate import translate_many, translate_text
from app.models.repo import Repo
from app.models.user import User
from app.rate_limiter import rate_limit_translations

router = APIRouter(
    prefix="/repos",
    tags=["Repository Content"],
    dependencies=[Depends(rate_limit_translations)],
)


class ReadmeResponse(BaseModel):
    file_name: str
    original: str
    translated: str | None
    source_lang: str | None
    target_lang: str
    translated_ok: bool
    reason: str | None = None


class CommentItem(BaseModel):
    id: int | None
    original_body: str
    translated_body: str | None
    translated_ok: bool
    author: dict[str, str]
    created_at: str | None
    updated_at: str | None
    html_url: str


class IssueListItem(BaseModel):
    number: int
    title: str
    original_title: str
    translated_title: str | None
    state: str
    author: dict[str, str]
    created_at: str | None
    updated_at: str | None
    labels: list[dict[str, str]]
    comment_count: int
    html_url: str


class IssueListResponse(BaseModel):
    items: list[IssueListItem]
    next_page: int | None
    source_lang: str | None
    target_lang: str


class IssueDetailResponse(BaseModel):
    number: int
    title: str
    original_title: str
    translated_title: str | None
    original_body: str
    translated_body: str | None
    translated_ok: bool
    state: str
    author: dict[str, str]
    created_at: str | None
    updated_at: str | None
    labels: list[dict[str, str]]
    comment_count: int
    html_url: str
    comments: list[CommentItem]
    source_lang: str | None
    target_lang: str


def _get_verified_repo(repo_id: int, user: User, session: Session) -> Repo:
    """Ensure repository exists and belongs to the authenticated user."""
    statement = select(Repo).where(Repo.id == repo_id, Repo.user_id == user.id)
    repo = session.exec(statement).first()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )
    return repo


def _resolve_target_lang(lang: str | None, user: User) -> str:
    """Determine target language, defaulting to user preference, validating catalogue."""
    target = lang.lower().strip() if lang and lang.strip() else (user.preferred_language or "en")
    if not is_supported(target):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Unsupported language code '{target}'. "
                "See /meta/languages for supported catalogue."
            ),
        )
    return target


@router.get("/{repo_id}/readme", response_model=ReadmeResponse)
async def get_repo_readme(
    repo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    lang: str | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> ReadmeResponse:
    """Fetch repository README, detect source language, and translate if necessary."""
    repo = _get_verified_repo(repo_id, current_user, session)
    target_lang = _resolve_target_lang(lang, current_user)

    token = get_github_token(current_user)
    try:
        async with GitHubClient(token) as client:
            readme_data = await client.get_readme(repo.owner, repo.name, repo.branch)
    except RepoNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RateLimited as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except GitHubClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    file_name = readme_data["file_name"]
    original_text = readme_data["content"]

    # Detect language if not yet recorded on repo
    source_lang = repo.source_language
    if source_lang is None and original_text.strip():
        detection = detect_language(original_text)
        if detection.code:
            source_lang = detection.code
            repo.source_language = detection.code
            repo.source_language_confidence = detection.confidence
            session.add(repo)
            session.commit()
            session.refresh(repo)

    if not source_lang or source_lang == target_lang:
        return ReadmeResponse(
            file_name=file_name,
            original=original_text,
            translated=None,
            source_lang=source_lang or target_lang,
            target_lang=target_lang,
            translated_ok=True,
        )

    res = await translate_text(
        original_text,
        source=source_lang,
        target=target_lang,
        kind="readme",
        session=session,
        refresh=refresh,
    )

    return ReadmeResponse(
        file_name=file_name,
        original=original_text,
        translated=res.text if res.ok else None,
        source_lang=source_lang,
        target_lang=target_lang,
        translated_ok=res.ok,
        reason=res.reason,
    )


@router.get("/{repo_id}/issues", response_model=IssueListResponse)
async def list_repo_issues(
    repo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    state: str = Query(default="open"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    lang: str | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> IssueListResponse:
    """List repository issues (excluding PRs) with titles translated in a single batch."""
    repo = _get_verified_repo(repo_id, current_user, session)
    target_lang = _resolve_target_lang(lang, current_user)

    token = get_github_token(current_user)
    try:
        async with GitHubClient(token) as client:
            issues_data = await client.list_issues(
                repo.owner,
                repo.name,
                state=state,
                page=page,
                per_page=per_page,
            )
    except GitHubClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    raw_items = issues_data["items"]
    source_lang = repo.source_language

    titles = [it.get("title", "") for it in raw_items]
    translated_titles: list[str | None] = [None] * len(titles)

    if source_lang and source_lang != target_lang and titles:
        trans_results = await translate_many(
            titles,
            source=source_lang,
            target=target_lang,
            kind="issue_title",
            session=session,
            refresh=refresh,
        )
        for i, res in enumerate(trans_results):
            if res.ok and res.text != titles[i]:
                translated_titles[i] = res.text

    items: list[IssueListItem] = []
    for i, it in enumerate(raw_items):
        items.append(
            IssueListItem(
                number=it["number"],
                title=it["title"],
                original_title=it["title"],
                translated_title=translated_titles[i],
                state=it["state"],
                author=it["author"],
                created_at=it["created_at"],
                updated_at=it["updated_at"],
                labels=it["labels"],
                comment_count=it["comment_count"],
                html_url=it["html_url"],
            )
        )

    return IssueListResponse(
        items=items,
        next_page=issues_data["next_page"],
        source_lang=source_lang,
        target_lang=target_lang,
    )


@router.get("/{repo_id}/issues/{issue_number}", response_model=IssueDetailResponse)
async def get_repo_issue_detail(
    repo_id: int,
    issue_number: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    lang: str | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> IssueDetailResponse:
    """Fetch full issue details and comments, translating body and comments lazily."""
    repo = _get_verified_repo(repo_id, current_user, session)
    target_lang = _resolve_target_lang(lang, current_user)

    token = get_github_token(current_user)
    try:
        async with GitHubClient(token) as client:
            issue = await client.get_issue(repo.owner, repo.name, issue_number)
            comments_data = await client.list_issue_comments(repo.owner, repo.name, issue_number)
    except RepoNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitHubClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    source_lang = repo.source_language
    body = issue.get("body") or ""
    title = issue.get("title") or ""

    # Translate title
    translated_title = None
    if source_lang and source_lang != target_lang and title.strip():
        title_res = await translate_text(
            title,
            source=source_lang,
            target=target_lang,
            kind="issue_title",
            session=session,
            refresh=refresh,
        )
        if title_res.ok and title_res.text != title:
            translated_title = title_res.text

    # Translate body
    translated_body = None
    body_ok = True
    if source_lang and source_lang != target_lang and body.strip():
        body_res = await translate_text(
            body,
            source=source_lang,
            target=target_lang,
            kind="issue_body",
            session=session,
            refresh=refresh,
        )
        translated_body = body_res.text if body_res.ok else None
        body_ok = body_res.ok

    # Translate comments with bounded parallelism
    sem = asyncio.Semaphore(5)

    async def translate_one_comment(c: dict[str, Any]) -> CommentItem:
        c_body = c.get("body") or ""
        if not c_body.strip() or not source_lang or source_lang == target_lang:
            return CommentItem(
                id=c.get("id"),
                original_body=c_body,
                translated_body=None,
                translated_ok=True,
                author=c.get("author", {}),
                created_at=c.get("created_at"),
                updated_at=c.get("updated_at"),
                html_url=c.get("html_url", ""),
            )
        async with sem:
            res = await translate_text(
                c_body,
                source=source_lang,
                target=target_lang,
                kind="comment",
                session=session,
                refresh=refresh,
            )
            return CommentItem(
                id=c.get("id"),
                original_body=c_body,
                translated_body=res.text if res.ok else None,
                translated_ok=res.ok,
                author=c.get("author", {}),
                created_at=c.get("created_at"),
                updated_at=c.get("updated_at"),
                html_url=c.get("html_url", ""),
            )

    comment_items = await asyncio.gather(
        *(translate_one_comment(c) for c in comments_data["items"])
    )

    return IssueDetailResponse(
        number=issue["number"],
        title=title,
        original_title=title,
        translated_title=translated_title,
        original_body=body,
        translated_body=translated_body,
        translated_ok=body_ok,
        state=issue["state"],
        author=issue["author"],
        created_at=issue["created_at"],
        updated_at=issue["updated_at"],
        labels=issue["labels"],
        comment_count=issue["comment_count"],
        html_url=issue["html_url"],
        comments=list(comment_items),
        source_lang=source_lang,
        target_lang=target_lang,
    )


@router.get("/{repo_id}/pulls", response_model=IssueListResponse)
async def list_repo_pulls(
    repo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    state: str = Query(default="open"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    lang: str | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> IssueListResponse:
    """List repository pull requests with titles translated in a single batch."""
    repo = _get_verified_repo(repo_id, current_user, session)
    target_lang = _resolve_target_lang(lang, current_user)

    token = get_github_token(current_user)
    try:
        async with GitHubClient(token) as client:
            pulls_data = await client.list_pulls(
                repo.owner,
                repo.name,
                state=state,
                page=page,
                per_page=per_page,
            )
    except GitHubClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    raw_items = pulls_data["items"]
    source_lang = repo.source_language

    titles = [it.get("title", "") for it in raw_items]
    translated_titles: list[str | None] = [None] * len(titles)

    if source_lang and source_lang != target_lang and titles:
        trans_results = await translate_many(
            titles,
            source=source_lang,
            target=target_lang,
            kind="pr_body",
            session=session,
            refresh=refresh,
        )
        for i, res in enumerate(trans_results):
            if res.ok and res.text != titles[i]:
                translated_titles[i] = res.text

    items: list[IssueListItem] = []
    for i, it in enumerate(raw_items):
        items.append(
            IssueListItem(
                number=it["number"],
                title=it["title"],
                original_title=it["title"],
                translated_title=translated_titles[i],
                state=it["state"],
                author=it["author"],
                created_at=it["created_at"],
                updated_at=it["updated_at"],
                labels=it["labels"],
                comment_count=it["comment_count"],
                html_url=it["html_url"],
            )
        )

    return IssueListResponse(
        items=items,
        next_page=pulls_data["next_page"],
        source_lang=source_lang,
        target_lang=target_lang,
    )


@router.get("/{repo_id}/pulls/{pull_number}", response_model=IssueDetailResponse)
async def get_repo_pull_detail(
    repo_id: int,
    pull_number: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    lang: str | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> IssueDetailResponse:
    """Fetch full pull request details and comments, translating body and comments lazily."""
    repo = _get_verified_repo(repo_id, current_user, session)
    target_lang = _resolve_target_lang(lang, current_user)

    token = get_github_token(current_user)
    try:
        async with GitHubClient(token) as client:
            pull = await client.get_pull(repo.owner, repo.name, pull_number)
            comments_data = await client.list_pull_comments(repo.owner, repo.name, pull_number)
    except RepoNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except GitHubClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    source_lang = repo.source_language
    body = pull.get("body") or ""
    title = pull.get("title") or ""

    # Translate title
    translated_title = None
    if source_lang and source_lang != target_lang and title.strip():
        title_res = await translate_text(
            title,
            source=source_lang,
            target=target_lang,
            kind="pr_body",
            session=session,
            refresh=refresh,
        )
        if title_res.ok and title_res.text != title:
            translated_title = title_res.text

    # Translate body
    translated_body = None
    body_ok = True
    if source_lang and source_lang != target_lang and body.strip():
        body_res = await translate_text(
            body,
            source=source_lang,
            target=target_lang,
            kind="pr_body",
            session=session,
            refresh=refresh,
        )
        translated_body = body_res.text if body_res.ok else None
        body_ok = body_res.ok

    # Translate comments with bounded parallelism
    sem = asyncio.Semaphore(5)

    async def translate_one_comment(c: dict[str, Any]) -> CommentItem:
        c_body = c.get("body") or ""
        if not c_body.strip() or not source_lang or source_lang == target_lang:
            return CommentItem(
                id=c.get("id"),
                original_body=c_body,
                translated_body=None,
                translated_ok=True,
                author=c.get("author", {}),
                created_at=c.get("created_at"),
                updated_at=c.get("updated_at"),
                html_url=c.get("html_url", ""),
            )
        async with sem:
            res = await translate_text(
                c_body,
                source=source_lang,
                target=target_lang,
                kind="comment",
                session=session,
                refresh=refresh,
            )
            return CommentItem(
                id=c.get("id"),
                original_body=c_body,
                translated_body=res.text if res.ok else None,
                translated_ok=res.ok,
                author=c.get("author", {}),
                created_at=c.get("created_at"),
                updated_at=c.get("updated_at"),
                html_url=c.get("html_url", ""),
            )

    comment_items = await asyncio.gather(
        *(translate_one_comment(c) for c in comments_data["items"])
    )

    return IssueDetailResponse(
        number=pull["number"],
        title=title,
        original_title=title,
        translated_title=translated_title,
        original_body=body,
        translated_body=translated_body,
        translated_ok=body_ok,
        state=pull["state"],
        author=pull["author"],
        created_at=pull["created_at"],
        updated_at=pull["updated_at"],
        labels=pull["labels"],
        comment_count=pull["comment_count"],
        html_url=pull["html_url"],
        comments=list(comment_items),
        source_lang=source_lang,
        target_lang=target_lang,
    )
