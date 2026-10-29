from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from app.auth.scope import (
    ScopeRequiredError,
    TokenRevokedError,
    require_scope,
    verify_live_scope,
)
from app.db import get_session
from app.models.user import User

__all__ = [
    "ScopeRequiredError",
    "TokenRevokedError",
    "get_current_user",
    "get_optional_user",
    "require_csrf_header",
    "require_scope",
    "verify_live_scope",
]


async def require_csrf_header(request: Request) -> None:
    """Validate CSRF protection header for mutating requests.

    Rejects POST, PUT, PATCH, DELETE requests lacking 'X-Requested-With: bodhcode'.
    Cross-site browser requests cannot attach this header without CORS preflight.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        header_val = request.headers.get("x-requested-with")
        if header_val != "bodhcode":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing or invalid CSRF header: X-Requested-With: bodhcode required",
            )


async def get_optional_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> User | None:
    """Retrieve currently authenticated user from session if present."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = session.get(User, user_id)
    return user


async def get_current_user(
    user: Annotated[User | None, Depends(get_optional_user)],
) -> User:
    """Ensure user is authenticated.

    Raises 401 Unauthorized if session is missing or user is not found in database.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user
