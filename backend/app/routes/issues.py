"""GitHub issues and comments creation endpoints with outgoing translation and confirmation."""

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.auth.crypto import get_github_token
from app.auth.deps import (
    ScopeRequiredError,
    TokenRevokedError,
    get_current_user,
    require_csrf_header,
    require_scope,
    verify_live_scope,
)
from app.db import get_session
from app.github.language import get_repo_language
from app.github.push import GitHubPushClient
from app.github.rate_limit import check_issue_comment_rate_limit
from app.github.secrets import scan_changes
from app.i18n.translate import translate_text
from app.models.push import ActionLog, PushPreview
from app.models.repo import Repo
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/repos",
    tags=["Issues and Comments"],
    dependencies=[Depends(require_csrf_header)],
)


class IssuePreviewRequest(BaseModel):
    title: str
    body: str
    written_in: str | None = None


class IssuePreviewEditRequest(BaseModel):
    title: str | None = None
    body: str | None = None


class CommentPreviewRequest(BaseModel):
    body: str
    written_in: str | None = None


class CommentPreviewEditRequest(BaseModel):
    body: str | None = None


class ActionConfirmRequest(BaseModel):
    preview_id: str
    confirm: bool = Field(default=True)


def _get_user_repo(repo_id: int, user: User, session: Session) -> Repo:
    repo = session.get(Repo, repo_id)
    if not repo or repo.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return repo


@router.post("/{repo_id}/issues/preview")
async def preview_create_issue(
    repo_id: int,
    req: IssuePreviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Translate and preview an issue before submitting to GitHub."""
    require_scope(current_user, "public_repo")
    check_issue_comment_rate_limit(current_user.id, session)
    repo = _get_user_repo(repo_id, current_user, session)

    if not req.title.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Title cannot be empty")

    # Scan for secrets in title and body
    findings = scan_changes(
        [
            {"path": "issue_title", "content": req.title},
            {"path": "issue_body", "content": req.body},
        ]
    )
    if findings:
        formatted = [{"path": f.path, "rule_name": f.pattern_name} for f in findings]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "secret_detected",
                "message": "Blocked: Secret detected in issue text. Please remove before sending.",
                "findings": formatted,
            },
        )

    token = get_github_token(current_user)
    repo_language = await get_repo_language(repo, session=session, token=token)
    written_in = req.written_in or current_user.preferred_language or "en"

    if written_in == repo_language:
        texts = {
            "title": {"original": req.title, "translated": req.title},
            "body": {"original": req.body, "translated": req.body},
        }
    else:
        res_title = await translate_text(
            req.title,
            source=written_in,
            target=repo_language,
            kind="outgoing",
            session=session,
        )
        res_body = await translate_text(
            req.body,
            source=written_in,
            target=repo_language,
            kind="outgoing",
            session=session,
        )
        texts = {
            "title": {
                "original": req.title,
                "translated": res_title.text if res_title.ok else req.title,
            },
            "body": {
                "original": req.body,
                "translated": res_body.text if res_body.ok else req.body,
            },
        }

    payload_dict = {
        "texts": texts,
        "repo_language": repo_language,
        "written_in": written_in,
    }
    payload_json = json.dumps(payload_dict, sort_keys=True)
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    now = datetime.now(UTC)
    preview = PushPreview(
        user_id=current_user.id,
        repo_id=repo.id,
        kind="issue",
        payload=payload_json,
        payload_hash=payload_hash,
        expires_at=now + timedelta(minutes=30),
    )
    session.add(preview)
    session.add(
        ActionLog(
            user_id=current_user.id,
            repo_id=repo.id,
            action="issue_create",
            status="previewed",
            meta=json.dumps({"preview_id": preview.id}),
        )
    )
    session.commit()
    session.refresh(preview)

    return {
        "preview_id": preview.id,
        "texts": texts,
        "repo_language": repo_language,
        "written_in": written_in,
        "expires_at": preview.expires_at.isoformat(),
    }


@router.post("/{repo_id}/issues/preview/{preview_id}/edit")
async def edit_issue_preview(
    repo_id: int,
    preview_id: str,
    req: IssuePreviewEditRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Edit translated text in an unexpired, unconsumed issue preview."""
    preview = session.get(PushPreview, preview_id)
    if not preview or preview.user_id != current_user.id or preview.repo_id != repo_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview not found")

    now = datetime.now(UTC)
    if preview.consumed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Preview has already been confirmed/consumed",
        )
    if now > preview.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Preview has expired. Please preview again.",
        )

    payload = json.loads(preview.payload)
    texts = payload.get("texts", {})

    if req.title is not None:
        texts.setdefault("title", {})["translated"] = req.title
    if req.body is not None:
        texts.setdefault("body", {})["translated"] = req.body

    payload["texts"] = texts
    new_json = json.dumps(payload, sort_keys=True)
    preview.payload = new_json
    preview.payload_hash = hashlib.sha256(new_json.encode("utf-8")).hexdigest()

    session.add(preview)
    session.commit()
    session.refresh(preview)

    return {
        "preview_id": preview.id,
        "texts": texts,
        "payload_hash": preview.payload_hash,
    }


@router.post("/{repo_id}/issues")
async def confirm_create_issue(
    repo_id: int,
    req: ActionConfirmRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Confirm and create an issue on GitHub using stored preview."""
    if not req.confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation required")

    repo = _get_user_repo(repo_id, current_user, session)
    check_issue_comment_rate_limit(current_user.id, session)

    preview = session.get(PushPreview, req.preview_id)
    if not preview or preview.user_id != current_user.id or preview.repo_id != repo.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview not found")

    now = datetime.now(UTC)
    if preview.consumed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Preview has already been confirmed/consumed",
        )
    if now > preview.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Preview has expired. Please preview again.",
        )

    token = get_github_token(current_user)
    try:
        await verify_live_scope(token, "public_repo")
    except TokenRevokedError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.detail) from exc
    except ScopeRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="scope_required") from exc

    # Consume preview before write
    preview.consumed_at = now
    session.add(preview)
    session.commit()

    payload = json.loads(preview.payload)
    title = payload["texts"]["title"]["translated"]
    body = payload["texts"]["body"]["translated"]

    try:
        async with GitHubPushClient(token) as client:
            issue_data = await client.create_issue(repo.owner, repo.name, title=title, body=body)

        issue_url = issue_data.get("html_url", "")
        number = issue_data.get("number", 0)

        session.add(
            ActionLog(
                user_id=current_user.id,
                repo_id=repo.id,
                action="issue_create",
                status="succeeded",
                target_url=issue_url,
                meta=json.dumps({"number": number, "issue_url": issue_url}),
            )
        )
        session.commit()

        return {"issue_url": issue_url, "number": number}

    except Exception as exc:
        logger.error(f"Failed to create issue on GitHub: {type(exc).__name__}")
        session.add(
            ActionLog(
                user_id=current_user.id,
                repo_id=repo.id,
                action="issue_create",
                status="failed",
                target_url=None,
                meta=json.dumps({"error": type(exc).__name__}),
            )
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub error: {exc}",
        ) from exc


@router.post("/{repo_id}/issues/{issue_number}/comments/preview")
async def preview_create_comment(
    repo_id: int,
    issue_number: int,
    req: CommentPreviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Translate and preview a comment before sending to GitHub."""
    require_scope(current_user, "public_repo")
    check_issue_comment_rate_limit(current_user.id, session)
    repo = _get_user_repo(repo_id, current_user, session)

    if not req.body.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Body cannot be empty")

    findings = scan_changes([{"path": "comment_body", "content": req.body}])
    if findings:
        formatted = [{"path": f.path, "rule_name": f.pattern_name} for f in findings]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "secret_detected",
                "message": (
                    "Blocked: Secret detected in comment text. Please remove before sending."
                ),
                "findings": formatted,
            },
        )

    token = get_github_token(current_user)
    repo_language = await get_repo_language(repo, session=session, token=token)
    written_in = req.written_in or current_user.preferred_language or "en"

    if written_in == repo_language:
        texts = {"body": {"original": req.body, "translated": req.body}}
    else:
        res_body = await translate_text(
            req.body,
            source=written_in,
            target=repo_language,
            kind="outgoing",
            session=session,
        )
        texts = {
            "body": {
                "original": req.body,
                "translated": res_body.text if res_body.ok else req.body,
            }
        }

    payload_dict = {
        "issue_number": issue_number,
        "texts": texts,
        "repo_language": repo_language,
        "written_in": written_in,
    }
    payload_json = json.dumps(payload_dict, sort_keys=True)
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    now = datetime.now(UTC)
    preview = PushPreview(
        user_id=current_user.id,
        repo_id=repo.id,
        kind="comment",
        payload=payload_json,
        payload_hash=payload_hash,
        expires_at=now + timedelta(minutes=30),
    )
    session.add(preview)
    session.add(
        ActionLog(
            user_id=current_user.id,
            repo_id=repo.id,
            action="comment_create",
            status="previewed",
            meta=json.dumps({"preview_id": preview.id, "issue_number": issue_number}),
        )
    )
    session.commit()
    session.refresh(preview)

    return {
        "preview_id": preview.id,
        "issue_number": issue_number,
        "texts": texts,
        "repo_language": repo_language,
        "written_in": written_in,
        "expires_at": preview.expires_at.isoformat(),
    }


@router.post("/{repo_id}/issues/{issue_number}/comments/preview/{preview_id}/edit")
async def edit_comment_preview(
    repo_id: int,
    issue_number: int,
    preview_id: str,
    req: CommentPreviewEditRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Edit translated text in an unexpired, unconsumed comment preview."""
    preview = session.get(PushPreview, preview_id)
    if not preview or preview.user_id != current_user.id or preview.repo_id != repo_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview not found")

    now = datetime.now(UTC)
    if preview.consumed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Preview has already been confirmed/consumed",
        )
    if now > preview.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Preview has expired. Please preview again.",
        )

    payload = json.loads(preview.payload)
    texts = payload.get("texts", {})

    if req.body is not None:
        texts.setdefault("body", {})["translated"] = req.body

    payload["texts"] = texts
    new_json = json.dumps(payload, sort_keys=True)
    preview.payload = new_json
    preview.payload_hash = hashlib.sha256(new_json.encode("utf-8")).hexdigest()

    session.add(preview)
    session.commit()
    session.refresh(preview)

    return {
        "preview_id": preview.id,
        "texts": texts,
        "payload_hash": preview.payload_hash,
    }


@router.post("/{repo_id}/issues/{issue_number}/comments")
async def confirm_create_comment(
    repo_id: int,
    issue_number: int,
    req: ActionConfirmRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Confirm and submit comment to GitHub."""
    if not req.confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation required")

    repo = _get_user_repo(repo_id, current_user, session)
    check_issue_comment_rate_limit(current_user.id, session)

    preview = session.get(PushPreview, req.preview_id)
    if not preview or preview.user_id != current_user.id or preview.repo_id != repo.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview not found")

    now = datetime.now(UTC)
    if preview.consumed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Preview has already been confirmed/consumed",
        )
    if now > preview.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Preview has expired. Please preview again.",
        )

    token = get_github_token(current_user)
    try:
        await verify_live_scope(token, "public_repo")
    except TokenRevokedError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.detail) from exc
    except ScopeRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="scope_required") from exc

    preview.consumed_at = now
    session.add(preview)
    session.commit()

    payload = json.loads(preview.payload)
    body = payload["texts"]["body"]["translated"]

    try:
        async with GitHubPushClient(token) as client:
            comment_data = await client.create_comment(
                repo.owner, repo.name, number=issue_number, body=body
            )

        comment_url = comment_data.get("html_url", "")
        session.add(
            ActionLog(
                user_id=current_user.id,
                repo_id=repo.id,
                action="comment_create",
                status="succeeded",
                target_url=comment_url,
                meta=json.dumps({"issue_number": issue_number, "comment_url": comment_url}),
            )
        )
        session.commit()

        return {"comment_url": comment_url}

    except Exception as exc:
        logger.error(f"Failed to create comment on GitHub: {type(exc).__name__}")
        session.add(
            ActionLog(
                user_id=current_user.id,
                repo_id=repo.id,
                action="comment_create",
                status="failed",
                target_url=None,
                meta=json.dumps({"error": type(exc).__name__}),
            )
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub error: {exc}",
        ) from exc
