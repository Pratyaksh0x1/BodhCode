from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.auth.deps import get_current_user, require_csrf_header
from app.auth.github_oauth import get_oauth
from app.auth.service import upsert_github_user
from app.config import get_settings
from app.db import get_session
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

    try:
        token = await client.authorize_access_token(request)
        if not token or "access_token" not in token:
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/?auth_error=denied",
                status_code=status.HTTP_302_FOUND,
            )
    except Exception:
        # Never echo provider error text to client
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/?auth_error=denied",
            status_code=status.HTTP_302_FOUND,
        )

    # Fetch GitHub user profile
    try:
        user_resp = await client.get("user", token=token)
        if user_resp.status_code != 200:
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/?auth_error=denied",
                status_code=status.HTTP_302_FOUND,
            )
        user_data = user_resp.json()
    except Exception:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/?auth_error=denied",
            status_code=status.HTTP_302_FOUND,
        )

    github_id = user_data.get("id")
    login = user_data.get("login")
    if not github_id or not login:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/?auth_error=denied",
            status_code=status.HTTP_302_FOUND,
        )

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

    access_token = token.get("access_token", "")
    scopes = token.get("scope", "read:user,user:email")

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
