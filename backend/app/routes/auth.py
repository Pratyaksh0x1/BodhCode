import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.auth.crypto import encrypt_token
from app.auth.deps import get_current_user, require_csrf_header
from app.auth.github_oauth import get_oauth
from app.auth.scope import validate_return_to
from app.auth.service import upsert_github_user
from app.config import get_settings
from app.db import get_session
from app.models.push import ActionLog
from app.models.user import User, UserPublic

router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
    dependencies=[Depends(require_csrf_header)],
)


@router.get("/github/login")
async def github_login(request: Request) -> Response:
    """Redirect to GitHub OAuth authorization screen."""
    settings = get_settings()
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
    request.session.clear()
    request.session["user_id"] = user.id

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


@router.get("/me", response_model=UserPublic)
def get_me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Return profile details for the currently signed-in user.

    Never exposes encrypted token or internal scopes.
    """
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> Response:
    """Clear session cookie and invalidate current user session."""
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
