import re

import httpx
from fastapi import HTTPException, status

from app.models.user import User


class ScopeRequiredError(HTTPException):
    """Raised when user token does not have required GitHub OAuth scope."""

    def __init__(self, needed: str = "public_repo") -> None:
        self.needed = needed
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="scope_required",
        )


class TokenRevokedError(HTTPException):
    """Raised when live GitHub check detects token has been revoked or expired."""

    def __init__(self, detail: str = "permission was revoked — reconnect") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
        )


def validate_return_to(return_to: str | None) -> str:
    """Validate in-app return path against open redirect vulnerabilities."""
    if not return_to:
        return "/"
    # Must start with single slash, not double slash or backslash
    if not return_to.startswith("/") or return_to.startswith("//") or return_to.startswith("/\\"):
        return "/"
    # Must only contain safe path characters
    if not re.match(r"^/[a-zA-Z0-9_\-./?=&%#]*$", return_to):
        return "/"
    return return_to


def require_scope(user: User, needed_scope: str = "public_repo") -> None:
    """Validate cached user scopes in database.

    Raises ScopeRequiredError if needed_scope is not present.
    """
    scopes_str = user.token_scopes or ""
    # Scopes can be comma-separated or space-separated
    scopes = {s.strip() for s in scopes_str.replace(",", " ").split() if s.strip()}
    if needed_scope not in scopes and "repo" not in scopes:
        raise ScopeRequiredError(needed=needed_scope)


async def verify_live_scope(
    token: str,
    needed_scope: str = "public_repo",
    *,
    client: httpx.AsyncClient | None = None,
) -> list[str]:
    """Call GitHub GET /user to verify token validity and read live X-OAuth-Scopes header.

    Overrides stale or revoked stored token permissions.
    Never exposes or logs token values.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "BodhCode",
    }

    async def _do_request(http_client: httpx.AsyncClient) -> httpx.Response:
        return await http_client.get("https://api.github.com/user", headers=headers, timeout=10.0)

    try:
        if client is not None:
            resp = await _do_request(client)
        else:
            async with httpx.AsyncClient() as new_client:
                resp = await _do_request(new_client)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to connect to GitHub for permission verification",
        ) from exc

    if resp.status_code == 401:
        raise TokenRevokedError("permission was revoked — reconnect")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unexpected response from GitHub while verifying permissions",
        )

    scopes_header = resp.headers.get("x-oauth-scopes", "")
    scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]
    scope_set = set(scopes)

    if needed_scope not in scope_set and "repo" not in scope_set:
        raise ScopeRequiredError(needed=needed_scope)

    return scopes
