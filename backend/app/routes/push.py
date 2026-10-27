"""Push to GitHub endpoints: preview, edit translation, confirm, and language settings."""

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

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
from app.files.service import normalize_path
from app.github.branch import InvalidBranchNameError, validate_branch_name
from app.github.client import RateLimited, RepoNotFound, TokenInvalid
from app.github.language import get_repo_language
from app.github.push import (
    Conflict,
    GitHubPushClient,
    PermissionDenied,
    ValidationFailed,
)
from app.github.rate_limit import check_push_rate_limit
from app.github.secrets import scan_changes
from app.i18n.languages import is_supported
from app.i18n.translate import translate_text
from app.models.files import WorkingFile
from app.models.push import ActionLog, PushPreview
from app.models.repo import Repo
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/repos",
    tags=["Push to GitHub"],
    dependencies=[Depends(require_csrf_header)],
)


class PushPreviewRequest(BaseModel):
    branch_name: str
    commit_message: str
    pr_title: str
    pr_body: str
    language_override: str | None = None
    written_in: str | None = None


class PushPreviewEditRequest(BaseModel):
    commit_message: str | None = None
    pr_title: str | None = None
    pr_body: str | None = None


class PushConfirmRequest(BaseModel):
    preview_id: str
    confirm: bool = Field(default=True)


class RepoLanguageOverrideRequest(BaseModel):
    push_language_override: str | None = None


def _get_user_repo(repo_id: int, user: User, session: Session) -> Repo:
    repo = session.get(Repo, repo_id)
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    if repo.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return repo


def _compute_working_copy_hash(changes: list[dict[str, Any]]) -> str:
    sorted_changes = sorted(changes, key=lambda c: c["path"])
    raw_str = "|".join(
        f"{c['path']}:{c['status']}:{c.get('content_hash', '')}" for c in sorted_changes
    )
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()


@router.post("/{repo_id}/push/preview")
async def create_push_preview(
    repo_id: int,
    req: PushPreviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Validate changes, scan secrets, determine repo language, translate, and store preview."""
    # 1. Fast cached scope check
    require_scope(current_user, "public_repo")

    repo = _get_user_repo(repo_id, current_user, session)

    # 2. Validate branch name
    try:
        validate_branch_name(req.branch_name)
    except InvalidBranchNameError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # 3. Retrieve working copy changes
    statement = (
        select(WorkingFile)
        .where(WorkingFile.user_id == current_user.id, WorkingFile.repo_id == repo.id)
        .order_by(WorkingFile.path)
    )
    working_rows = session.exec(statement).all()

    if not working_rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes to push")
    if len(working_rows) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Change set exceeds 100 files limit",
        )

    # 4. Process files, check sizes and forbidden paths
    changes: list[dict[str, Any]] = []
    scan_items: list[dict[str, Any]] = []

    for wf in working_rows:
        try:
            norm_path = normalize_path(wf.path)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file path '{wf.path}': {exc}",
            ) from exc

        if norm_path.startswith(".github/workflows/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"File '{norm_path}' cannot be pushed: GitHub Actions workflow files "
                    "require additional permissions not supported with public_repo scope."
                ),
            )

        if wf.is_deleted:
            status_str = "deleted"
            content = None
            content_hash = ""
        elif wf.is_new:
            status_str = "added"
            content = wf.content
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        else:
            status_str = "modified"
            content = wf.content
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        if content is not None:
            content_bytes = content.encode("utf-8")
            if len(content_bytes) > 1_000_000:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File '{norm_path}' exceeds 1 MB limit",
                )
            scan_items.append({"path": norm_path, "content": content})
        else:
            scan_items.append({"path": norm_path, "content": None})

        changes.append(
            {
                "path": norm_path,
                "status": status_str,
                "content": content,
                "content_hash": content_hash,
            }
        )

    # 5. Scan for secrets
    findings = scan_changes(scan_items)
    if findings:
        formatted_findings = [{"path": f.path, "rule_name": f.pattern_name} for f in findings]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "secret_detected",
                "message": (
                    f"Blocked: Secret detected in {len(findings)} file(s). "
                    "Please remove secrets before pushing."
                ),
                "findings": formatted_findings,
            },
        )

    working_copy_hash = _compute_working_copy_hash(changes)

    # 6. Determine repository language
    token = get_github_token(current_user)
    if req.language_override and is_supported(req.language_override):
        repo_language = req.language_override
        repo.push_language_override = req.language_override
        session.add(repo)
        session.commit()
    else:
        repo_language = await get_repo_language(repo, session=session, token=token)

    written_in = req.written_in or current_user.preferred_language or "en"

    # 7. Translation of outgoing texts
    if written_in == repo_language:
        texts = {
            "commit_message": {
                "original": req.commit_message,
                "translated": req.commit_message,
            },
            "pr_title": {"original": req.pr_title, "translated": req.pr_title},
            "pr_body": {"original": req.pr_body, "translated": req.pr_body},
        }
    else:
        res_commit = await translate_text(
            req.commit_message,
            source=written_in,
            target=repo_language,
            kind="outgoing",
            session=session,
        )
        res_title = await translate_text(
            req.pr_title,
            source=written_in,
            target=repo_language,
            kind="outgoing",
            session=session,
        )
        res_body = await translate_text(
            req.pr_body,
            source=written_in,
            target=repo_language,
            kind="outgoing",
            session=session,
        )
        texts = {
            "commit_message": {
                "original": req.commit_message,
                "translated": res_commit.text if res_commit.ok else req.commit_message,
            },
            "pr_title": {
                "original": req.pr_title,
                "translated": res_title.text if res_title.ok else req.pr_title,
            },
            "pr_body": {
                "original": req.pr_body,
                "translated": res_body.text if res_body.ok else req.pr_body,
            },
        }

    # 8. Check fork requirement
    will_fork = True
    target_repo = f"{current_user.login}/{repo.name}"
    try:
        async with GitHubPushClient(token) as gh_client:
            gh_repo_data = await gh_client.get_repo(repo.owner, repo.name)
            if gh_repo_data.get("permissions", {}).get("push") is True:
                will_fork = False
                target_repo = f"{repo.owner}/{repo.name}"
    except Exception as exc:
        logger.debug(f"Could not check upstream push permission: {exc}")

    # 9. Store preview
    payload_data = {
        "branch_name": req.branch_name,
        "texts": texts,
        "changes": changes,
        "working_copy_hash": working_copy_hash,
        "repo_language": repo_language,
        "written_in": written_in,
        "will_fork": will_fork,
        "target_repo": target_repo,
    }
    payload_json = json.dumps(payload_data, sort_keys=True)
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    now = datetime.now(UTC)
    preview = PushPreview(
        user_id=current_user.id,
        repo_id=repo.id,
        kind="push",
        payload=payload_json,
        payload_hash=payload_hash,
        expires_at=now + timedelta(minutes=30),
    )
    session.add(preview)

    # Log action
    log = ActionLog(
        user_id=current_user.id,
        repo_id=repo.id,
        action="push",
        status="previewed",
        meta=json.dumps({"preview_id": preview.id, "branch": req.branch_name}),
    )
    session.add(log)
    session.commit()
    session.refresh(preview)

    return {
        "preview_id": preview.id,
        "changes": [{"path": c["path"], "status": c["status"]} for c in changes],
        "texts": texts,
        "repo_language": repo_language,
        "written_in": written_in,
        "target_repo": target_repo,
        "will_fork": will_fork,
        "expires_at": preview.expires_at.isoformat(),
    }


@router.post("/{repo_id}/push/preview/{preview_id}/edit")
async def edit_push_preview(
    repo_id: int,
    preview_id: str,
    req: PushPreviewEditRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Edit translated texts in an unexpired, unconsumed push preview."""
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

    if req.commit_message is not None:
        texts.setdefault("commit_message", {})["translated"] = req.commit_message
    if req.pr_title is not None:
        texts.setdefault("pr_title", {})["translated"] = req.pr_title
    if req.pr_body is not None:
        texts.setdefault("pr_body", {})["translated"] = req.pr_body

    payload["texts"] = texts
    new_payload_json = json.dumps(payload, sort_keys=True)
    preview.payload = new_payload_json
    preview.payload_hash = hashlib.sha256(new_payload_json.encode("utf-8")).hexdigest()

    session.add(preview)
    session.commit()
    session.refresh(preview)

    return {
        "preview_id": preview.id,
        "texts": texts,
        "payload_hash": preview.payload_hash,
    }


@router.post("/{repo_id}/push")
async def confirm_push(
    repo_id: int,
    req: PushConfirmRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Execute push: live scope check, verify preview, consume preview, and write Git Data."""
    if not req.confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation required")

    repo = _get_user_repo(repo_id, current_user, session)

    # 1. Check user rate limit (5 pushes per hour)
    check_push_rate_limit(current_user.id, session)

    # 2. Validate preview state
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

    payload = json.loads(preview.payload)

    # 3. Live scope check against GitHub API
    token = get_github_token(current_user)
    try:
        await verify_live_scope(token, "public_repo")
    except TokenRevokedError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=exc.detail) from exc
    except ScopeRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="scope_required") from exc

    # 4. Verify working copy still matches stored preview
    statement = (
        select(WorkingFile)
        .where(WorkingFile.user_id == current_user.id, WorkingFile.repo_id == repo.id)
        .order_by(WorkingFile.path)
    )
    current_working = session.exec(statement).all()
    current_changes: list[dict[str, Any]] = []
    for wf in current_working:
        status_str = "deleted" if wf.is_deleted else ("added" if wf.is_new else "modified")
        c_hash = ""
        if not wf.is_deleted:
            c_hash = hashlib.sha256(wf.content.encode("utf-8")).hexdigest()
        current_changes.append(
            {"path": normalize_path(wf.path), "status": status_str, "content_hash": c_hash}
        )

    current_hash = _compute_working_copy_hash(current_changes)
    if current_hash != payload.get("working_copy_hash"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="changes were modified — preview again",
        )

    # 5. Mark preview consumed BEFORE first write to ensure idempotency
    preview.consumed_at = now
    session.add(preview)

    session.add(
        ActionLog(
            user_id=current_user.id,
            repo_id=repo.id,
            action="push",
            status="confirmed",
            meta=json.dumps({"preview_id": preview.id}),
        )
    )
    session.commit()

    # 6. Execute Git Data API writes
    branch_name = payload["branch_name"]
    commit_msg = payload["texts"]["commit_message"]["translated"]
    pr_title = payload["texts"]["pr_title"]["translated"]
    pr_body = payload["texts"]["pr_body"]["translated"]
    file_changes = payload["changes"]

    created_branch_ref: str | None = None
    created_commit_sha: str | None = None
    target_owner: str = repo.owner
    target_name: str = repo.name

    try:
        async with GitHubPushClient(token) as gh_client:
            # Fork check / creation
            target_owner, target_name = await gh_client.ensure_fork(
                repo.owner, repo.name, current_user.login
            )

            # Get base commit SHA
            base_sha = repo.commit_sha
            if not base_sha:
                base_sha = await gh_client.get_branch_sha(repo.owner, repo.name, repo.branch)

            # Fetch base commit to obtain base tree SHA
            base_commit_info = await gh_client._request(
                "GET", f"/repos/{repo.owner}/{repo.name}/git/commits/{base_sha}"
            )
            base_tree_sha = base_commit_info["tree"]["sha"]

            # Create blobs
            tree_entries: list[dict[str, Any]] = []
            for ch in file_changes:
                p = ch["path"]
                st = ch["status"]
                if st in ("added", "modified"):
                    b_sha = await gh_client.create_blob(target_owner, target_name, ch["content"])
                    tree_entries.append(
                        {"path": p, "mode": "100644", "type": "blob", "sha": b_sha}
                    )
                elif st == "deleted":
                    tree_entries.append(
                        {"path": p, "mode": "100644", "type": "blob", "sha": None}
                    )

            # Create tree
            new_tree_sha = await gh_client.create_tree(
                target_owner, target_name, base_tree_sha, tree_entries
            )

            # Create commit
            new_commit_sha = await gh_client.create_commit(
                target_owner, target_name, commit_msg, new_tree_sha, [base_sha]
            )
            created_commit_sha = new_commit_sha

            # Create branch or update ref
            await gh_client.create_branch(target_owner, target_name, branch_name, new_commit_sha)
            await gh_client.update_ref(target_owner, target_name, branch_name, new_commit_sha)
            created_branch_ref = branch_name

            # Open PR on upstream repository
            head = (
                f"{target_owner}:{branch_name}"
                if target_owner.lower() != repo.owner.lower()
                else branch_name
            )
            pr_data = await gh_client.open_pull_request(
                upstream_owner=repo.owner,
                upstream_name=repo.name,
                head=head,
                base=repo.branch,
                title=pr_title,
                body=pr_body,
            )
            pr_url = pr_data.get("html_url", "")

            # Log success
            session.add(
                ActionLog(
                    user_id=current_user.id,
                    repo_id=repo.id,
                    action="push",
                    status="succeeded",
                    target_url=pr_url,
                    meta=json.dumps(
                        {
                            "pr_url": pr_url,
                            "branch": branch_name,
                            "commit_sha": new_commit_sha,
                        }
                    ),
                )
            )
            session.commit()

            return {
                "pr_url": pr_url,
                "branch": branch_name,
                "commit_sha": new_commit_sha,
                "fork": f"{target_owner}/{target_name}",
            }

    except (
        RepoNotFound,
        TokenInvalid,
        RateLimited,
        PermissionDenied,
        ValidationFailed,
        Conflict,
    ) as exc:
        logger.error(f"Push operation failed: {type(exc).__name__}")
        session.add(
            ActionLog(
                user_id=current_user.id,
                repo_id=repo.id,
                action="push",
                status="failed",
                target_url=None,
                meta=json.dumps(
                    {
                        "error": type(exc).__name__,
                        "branch": created_branch_ref,
                        "commit_sha": created_commit_sha,
                    }
                ),
            )
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": type(exc).__name__,
                "message": str(exc),
                "branch": created_branch_ref,
                "commit_sha": created_commit_sha,
                "fork": f"{target_owner}/{target_name}" if target_owner else None,
            },
        ) from exc
    except Exception as exc:
        logger.error(f"Unexpected error in push confirm: {type(exc).__name__}")
        session.add(
            ActionLog(
                user_id=current_user.id,
                repo_id=repo.id,
                action="push",
                status="failed",
                target_url=None,
                meta=json.dumps(
                    {
                        "error": type(exc).__name__,
                        "branch": created_branch_ref,
                        "commit_sha": created_commit_sha,
                    }
                ),
            )
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "push_failed",
                "message": "Push failed during Git operations",
                "branch": created_branch_ref,
                "commit_sha": created_commit_sha,
                "fork": f"{target_owner}/{target_name}" if target_owner else None,
            },
        ) from exc


@router.patch("/{repo_id}/language")
async def update_repo_language_override(
    repo_id: int,
    req: RepoLanguageOverrideRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Set or clear push_language_override for a repository."""
    repo = _get_user_repo(repo_id, current_user, session)
    if req.push_language_override is not None:
        if not is_supported(req.push_language_override):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported language code '{req.push_language_override}'",
            )
        repo.push_language_override = req.push_language_override
    else:
        repo.push_language_override = None

    session.add(repo)
    session.commit()
    session.refresh(repo)

    token = get_github_token(current_user)
    resolved_lang = await get_repo_language(repo, session=session, token=token)
    return {
        "push_language_override": repo.push_language_override,
        "resolved_language": resolved_lang,
    }
