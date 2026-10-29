import json
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.auth.crypto import encrypt_token
from app.auth.deps import get_current_user, require_csrf_header
from app.auth.github_oauth import get_oauth
from app.auth.scope import validate_return_to
from app.auth.service import upsert_github_user
from app.config import get_settings
from app.db import get_session
from app.models.files import WorkingFile
from app.models.graph import RepoGraph
from app.models.proposals import Checkpoint, Proposal
from app.models.push import ActionLog, PushPreview
from app.models.repo import Repo
from app.models.user import User, UserPublic
from app.rate_limiter import rate_limit_auth_ip

router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
    dependencies=[Depends(require_csrf_header), Depends(rate_limit_auth_ip)],
)

# In-memory ticket store for Chrome-based desktop authorization
_DESKTOP_TICKETS: dict[str, dict[str, Any]] = {}


def _cleanup_old_tickets() -> None:
    now = time.time()
    expired = [k for k, v in _DESKTOP_TICKETS.items() if now - v.get("created_at", 0) > 600]
    for k in expired:
        _DESKTOP_TICKETS.pop(k, None)


def delete_user_data(session: Session, user: User) -> None:
    """Delete all personal records, files, proposals, and repo links for a user."""
    user_id = user.id
    if not user_id:
        return

    # Delete ActionLogs
    action_logs = session.exec(select(ActionLog).where(ActionLog.user_id == user_id)).all()
    for log in action_logs:
        session.delete(log)

    # Delete PushPreviews
    previews = session.exec(select(PushPreview).where(PushPreview.user_id == user_id)).all()
    for preview in previews:
        session.delete(preview)

    # Delete Proposals and Checkpoints
    proposals = session.exec(select(Proposal).where(Proposal.user_id == user_id)).all()
    for proposal in proposals:
        if proposal.id is not None:
            checkpoints = session.exec(
                select(Checkpoint).where(Checkpoint.proposal_id == proposal.id)
            ).all()
            for cp in checkpoints:
                session.delete(cp)
        session.delete(proposal)

    # Delete WorkingFiles
    working_files = session.exec(select(WorkingFile).where(WorkingFile.user_id == user_id)).all()
    for wf in working_files:
        session.delete(wf)

    # Delete Repos and RepoGraphs
    repos = session.exec(select(Repo).where(Repo.user_id == user_id)).all()
    for repo in repos:
        if repo.id is not None:
            graphs = session.exec(select(RepoGraph).where(RepoGraph.repo_id == repo.id)).all()
            for g in graphs:
                session.delete(g)
        session.delete(repo)

    # Delete the user row
    session.delete(user)
    session.commit()


@router.get("/github/login")
async def github_login(request: Request, ticket: str | None = None) -> Response:
    """Redirect to GitHub OAuth authorization screen."""
    settings = get_settings()
    if ticket:
        _cleanup_old_tickets()
        _DESKTOP_TICKETS[ticket] = {"status": "pending", "created_at": time.time()}
        request.session["desktop_ticket"] = ticket

    client = get_oauth().github
    redirect_uri = f"{settings.BACKEND_URL}/auth/github/callback"
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/github/upgrade")
async def github_upgrade(
    request: Request,
    return_to: str | None = None,
) -> Response:
    """Redirect to GitHub OAuth authorization screen requesting public_repo scope."""
    settings = get_settings()
    user_id = request.session.get("user_id")
    safe_return_to = validate_return_to(return_to)
    if not user_id:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/?auth_error=not_authenticated",
            status_code=status.HTTP_302_FOUND,
        )

    request.session["is_scope_upgrade"] = True
    request.session["upgrade_return_to"] = safe_return_to
    client = get_oauth().github
    redirect_uri = f"{settings.BACKEND_URL}/auth/github/callback"
    return await client.authorize_redirect(
        request,
        redirect_uri,
        scope="read:user user:email public_repo",
    )


@router.get("/github/callback")
async def github_callback(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Process OAuth callback from GitHub.

    Exchanges authorization code for access token, retrieves user profile,
    upserts user record, rotates session to prevent session fixation,
    and redirects user to the frontend application.
    """
    settings = get_settings()
    client = get_oauth().github

    is_upgrade = bool(request.session.pop("is_scope_upgrade", False))
    return_to = validate_return_to(request.session.pop("upgrade_return_to", "/"))

    def _denied_redirect() -> RedirectResponse:
        error_param = "upgrade_error=denied" if is_upgrade else "auth_error=denied"
        target_path = return_to if is_upgrade else "/"
        sep = "&" if "?" in target_path else "?"
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}{target_path}{sep}{error_param}",
            status_code=status.HTTP_302_FOUND,
        )

    try:
        token = await client.authorize_access_token(request)
        if not token or "access_token" not in token:
            if is_upgrade:
                user_id = request.session.get("user_id")
                if user_id:
                    session.add(
                        ActionLog(
                            user_id=user_id,
                            repo_id=None,
                            action="scope_upgrade",
                            status="failed",
                            target_url=None,
                            meta=json.dumps({"error": "token_missing"}),
                        )
                    )
                    session.commit()
            return _denied_redirect()
    except Exception:
        if is_upgrade:
            user_id = request.session.get("user_id")
            if user_id:
                session.add(
                    ActionLog(
                        user_id=user_id,
                        repo_id=None,
                        action="scope_upgrade",
                        status="failed",
                        target_url=None,
                        meta=json.dumps({"error": "oauth_exception"}),
                    )
                )
                session.commit()
        return _denied_redirect()

    # Fetch GitHub user profile
    try:
        user_resp = await client.get("user", token=token)
        if user_resp.status_code != 200:
            return _denied_redirect()
        user_data = user_resp.json()
    except Exception:
        return _denied_redirect()

    github_id = user_data.get("id")
    login = user_data.get("login")
    if not github_id or not login:
        return _denied_redirect()

    access_token = token.get("access_token", "")
    scopes = token.get("scope", "read:user,user:email")

    if is_upgrade:
        user_id = request.session.get("user_id")
        current_user = session.get(User, user_id) if user_id else None
        if not current_user or current_user.github_id != github_id:
            return _denied_redirect()

        current_user.encrypted_github_token = encrypt_token(access_token)
        current_user.token_scopes = scopes
        session.add(current_user)

        action_log = ActionLog(
            user_id=current_user.id,
            repo_id=None,
            action="scope_upgrade",
            status="succeeded",
            target_url=None,
            meta=json.dumps({"scopes": scopes}),
        )
        session.add(action_log)
        session.commit()
        session.refresh(current_user)

        target_url = f"{settings.FRONTEND_URL}{return_to}"
        return RedirectResponse(
            url=target_url,
            status_code=status.HTTP_302_FOUND,
        )

    # Standard login flow
    # Fetch primary verified email if not public on profile
    email = user_data.get("email")
    if not email:
        try:
            emails_resp = await client.get("user/emails", token=token)
            if emails_resp.status_code == 200:
                emails_data = emails_resp.json()
                email = next(
                    (e["email"] for e in emails_data if e.get("primary") and e.get("verified")),
                    None,
                )
        except Exception:
            email = None

    user = upsert_github_user(
        session,
        github_id=github_id,
        login=login,
        name=user_data.get("name"),
        avatar_url=user_data.get("avatar_url", ""),
        email=email,
        access_token=access_token,
        token_scopes=scopes,
    )

    # Clear old session and set user_id to prevent session fixation attacks
    desktop_ticket = request.session.pop("desktop_ticket", None)
    request.session.clear()
    request.session["user_id"] = user.id

    if desktop_ticket:
        _DESKTOP_TICKETS[desktop_ticket] = {
            "status": "approved",
            "user_id": user.id,
            "created_at": time.time(),
        }
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/desktop-success?ticket={desktop_ticket}",
            status_code=status.HTTP_302_FOUND,
        )

    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/github/upgrade/callback")
async def github_upgrade_callback(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """OAuth callback endpoint for upgrade requests."""
    request.session["is_scope_upgrade"] = True
    return await github_callback(request, session)


@router.get("/desktop-poll")
def desktop_poll(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    ticket: str = Query(description="Desktop OAuth verification ticket"),
) -> dict[str, Any]:
    """Poll for approval of a desktop OAuth login initiated via external Chrome browser."""
    _cleanup_old_tickets()
    ticket_data = _DESKTOP_TICKETS.get(ticket)
    if not ticket_data:
        return {"status": "not_found"}

    if ticket_data.get("status") == "approved":
        user_id = ticket_data.get("user_id")
        user = session.get(User, user_id)
        if user:
            request.session["user_id"] = user.id
            return {
                "status": "approved",
                "user": UserPublic(
                    id=user.id,
                    login=user.login,
                    name=user.name,
                    avatar_url=user.avatar_url,
                    email=user.email,
                    preferred_language=user.preferred_language,
                    theme=user.theme,
                    editor_theme=user.editor_theme,
                    review_mode=user.review_mode,
                    grok_configured=bool(user.encrypted_grok_key),
                    grok_model=user.grok_model or "gpt-oss-120b",
                    github_connected=bool(user.encrypted_github_token),
                    chatgpt_connected=bool(user.encrypted_openai_key),
                    openai_model=user.openai_model or "gpt-4o",
                    auth_provider=user.auth_provider or "github",
                ).model_dump(),
            }

    return {"status": "pending"}


class ChatGPTLoginRequest(BaseModel):
    """Payload to authenticate or connect a ChatGPT / OpenAI Codex account."""

    api_key: str = Field(description="OpenAI API key or ChatGPT session token")
    model: str = Field(default="gpt-4o", description="Default OpenAI/ChatGPT model")
    ticket: str | None = Field(default=None, description="Optional desktop ticket ID")


@router.post("/chatgpt/login")
async def chatgpt_login(
    payload: ChatGPTLoginRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Authenticate or connect a ChatGPT / OpenAI Codex account."""
    api_key = payload.api_key.strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="API Key or ChatGPT token is required.",
        )

    # Check if a user is currently signed in
    user_id = request.session.get("user_id")
    current_user = session.get(User, user_id) if user_id else None

    if current_user:
        # Link ChatGPT account to existing user
        current_user.encrypted_openai_key = encrypt_token(api_key)
        current_user.openai_model = payload.model
        if current_user.auth_provider == "github":
            current_user.auth_provider = "both"
        session.add(current_user)
        session.commit()
        session.refresh(current_user)
        user = current_user
    else:
        # Create a new ChatGPT/Codex user profile
        key_preview = api_key[-4:] if len(api_key) >= 4 else "key"
        new_user = User(
            github_id=int(time.time() * 1000) % 2147483647,
            login=f"chatgpt_user_{key_preview}",
            name="ChatGPT / Codex User",
            avatar_url="https://chatgpt.com/favicon.ico",
            encrypted_github_token="",
            encrypted_openai_key=encrypt_token(api_key),
            openai_model=payload.model,
            auth_provider="chatgpt",
        )
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        request.session.clear()
        request.session["user_id"] = new_user.id
        user = new_user

    if payload.ticket:
        _DESKTOP_TICKETS[payload.ticket] = {
            "status": "approved",
            "user_id": user.id,
            "created_at": time.time(),
        }

    return {
        "status": "ok",
        "user": UserPublic(
            id=user.id,
            login=user.login,
            name=user.name,
            avatar_url=user.avatar_url,
            email=user.email,
            preferred_language=user.preferred_language,
            theme=user.theme,
            editor_theme=user.editor_theme,
            review_mode=user.review_mode,
            grok_configured=bool(user.encrypted_grok_key),
            grok_model=user.grok_model or "gpt-oss-120b",
            github_connected=bool(user.encrypted_github_token),
            chatgpt_connected=bool(user.encrypted_openai_key),
            openai_model=user.openai_model or "gpt-4o",
            auth_provider=user.auth_provider or "chatgpt",
        ).model_dump(),
    }


@router.get("/me", response_model=UserPublic)
def get_me(current_user: Annotated[User, Depends(get_current_user)]) -> UserPublic:
    """Return profile details for the currently signed-in user.

    Never exposes encrypted token or internal scopes.
    """
    return UserPublic(
        id=current_user.id,
        login=current_user.login,
        name=current_user.name,
        avatar_url=current_user.avatar_url,
        email=current_user.email,
        preferred_language=current_user.preferred_language,
        theme=current_user.theme,
        editor_theme=current_user.editor_theme,
        review_mode=current_user.review_mode,
        grok_configured=bool(current_user.encrypted_grok_key),
        grok_model=current_user.grok_model or "gpt-oss-120b",
        github_connected=bool(current_user.encrypted_github_token),
        chatgpt_connected=bool(current_user.encrypted_openai_key),
        openai_model=current_user.openai_model or "gpt-4o",
        auth_provider=current_user.auth_provider or "github",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> Response:
    """Clear session cookie and invalidate current user session."""
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Permanently delete user account and all personal associated records.

    Deletes OAuth tokens, repo links, working files, proposals, previews,
    and action logs. Clears the session cookie. Shared public-repo cache
    directories remain intact.
    """
    delete_user_data(session, current_user)
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
