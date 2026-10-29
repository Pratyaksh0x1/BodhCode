from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.crypto import encrypt_token
from app.auth.scope import (
    ScopeRequiredError,
    TokenRevokedError,
    require_scope,
    validate_return_to,
    verify_live_scope,
)
from app.models.push import ActionLog
from app.models.user import User


def test_validate_return_to() -> None:
    assert validate_return_to(None) == "/"
    assert validate_return_to("") == "/"
    assert validate_return_to("/") == "/"
    assert validate_return_to("/repos/42") == "/repos/42"
    assert validate_return_to("/editor/1?file=app.ts") == "/editor/1?file=app.ts"
    # Reject open redirects
    assert validate_return_to("//attacker.com") == "/"
    assert validate_return_to("/\\attacker.com") == "/"
    assert validate_return_to("https://attacker.com") == "/"
    assert validate_return_to("javascript:alert(1)") == "/"


def test_require_scope() -> None:
    now = datetime.now(UTC)
    user_no_scope = User(
        id=1,
        github_id=100,
        login="coder",
        avatar_url="",
        encrypted_github_token="enc",
        token_scopes="read:user,user:email",
        created_at=now,
        last_login_at=now,
    )
    with pytest.raises(ScopeRequiredError) as exc_info:
        require_scope(user_no_scope, "public_repo")
    assert exc_info.value.status_code == 403
    assert exc_info.value.needed == "public_repo"

    user_with_scope = User(
        id=2,
        github_id=101,
        login="coder2",
        avatar_url="",
        encrypted_github_token="enc",
        token_scopes="read:user, user:email, public_repo",
        created_at=now,
        last_login_at=now,
    )
    require_scope(user_with_scope, "public_repo")  # does not raise

    user_with_full_repo = User(
        id=3,
        github_id=102,
        login="coder3",
        avatar_url="",
        encrypted_github_token="enc",
        token_scopes="repo, user",
        created_at=now,
        last_login_at=now,
    )
    require_scope(user_with_full_repo, "public_repo")  # does not raise


@respx.mock
@pytest.mark.asyncio
async def test_verify_live_scope_success() -> None:
    respx.get("https://api.github.com/user").respond(
        status_code=200,
        headers={"x-oauth-scopes": "read:user, user:email, public_repo"},
        json={"login": "testuser"},
    )
    scopes = await verify_live_scope("fake-token", "public_repo")
    assert "public_repo" in scopes


@respx.mock
@pytest.mark.asyncio
async def test_verify_live_scope_missing_scope() -> None:
    respx.get("https://api.github.com/user").respond(
        status_code=200,
        headers={"x-oauth-scopes": "read:user, user:email"},
        json={"login": "testuser"},
    )
    with pytest.raises(ScopeRequiredError) as exc_info:
        await verify_live_scope("fake-token", "public_repo")
    assert exc_info.value.needed == "public_repo"


@respx.mock
@pytest.mark.asyncio
async def test_verify_live_scope_revoked_token() -> None:
    respx.get("https://api.github.com/user").respond(
        status_code=401,
        json={"message": "Bad credentials"},
    )
    with pytest.raises(TokenRevokedError) as exc_info:
        await verify_live_scope("revoked-token", "public_repo")
    assert exc_info.value.status_code == 401
    assert "permission was revoked — reconnect" in exc_info.value.detail


def test_scope_error_handling_in_app() -> None:
    from app.main import create_app

    app = create_app()

    @app.get("/test-scope")
    def dummy_scope_route() -> None:
        raise ScopeRequiredError("public_repo")

    @app.get("/test-revoked")
    def dummy_revoked_route() -> None:
        raise TokenRevokedError()

    client = TestClient(app)
    r1 = client.get("/test-scope")
    assert r1.status_code == 403
    assert r1.json() == {"detail": "scope_required", "needed": "public_repo"}

    r2 = client.get("/test-revoked")
    assert r2.status_code == 401
    assert r2.json() == {"detail": "permission was revoked — reconnect"}


def test_upgrade_without_auth(client: TestClient) -> None:
    resp = client.get("/auth/github/upgrade?return_to=/repos/1", follow_redirects=False)
    assert resp.status_code == 302
    assert "auth_error=not_authenticated" in resp.headers["location"]


@pytest.mark.asyncio
async def test_upgrade_callback_success(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from starlette.responses import Response as StarletteResponse

    from app.auth.crypto import decrypt_token
    from app.auth.github_oauth import get_oauth

    now = datetime.now(UTC)
    user = User(
        github_id=999,
        login="octocat",
        avatar_url="https://avatar",
        encrypted_github_token=encrypt_token("old-token"),
        token_scopes="read:user,user:email",
        created_at=now,
        last_login_at=now,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    oauth_client = get_oauth().github

    mock_token = {
        "access_token": "gho_newElevatedTokenXYZ",
        "scope": "read:user,user:email,public_repo",
    }
    monkeypatch.setattr(
        oauth_client,
        "authorize_access_token",
        AsyncMock(return_value=mock_token),
    )

    async def mock_get(url: str, token: dict | None = None) -> StarletteResponse:
        resp = AsyncMock(spec=StarletteResponse)
        resp.status_code = 200
        resp.json = lambda: {"id": 999, "login": "octocat"}
        return resp

    monkeypatch.setattr(oauth_client, "get", mock_get)

    # Simulate existing session with user_id, upgrade_in_progress, and return_to
    # TestClient session cookie simulation via Request session patching
    with patch(
        "starlette.requests.Request.session",
        {
            "user_id": user.id,
            "is_scope_upgrade": True,
            "upgrade_return_to": "/repos/42",
        },
    ):
        resp = client.get(
            "/auth/github/upgrade/callback?code=mock_code&state=mock_state",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"].endswith("/repos/42")

    # Verify user record updated in database
    db_session.refresh(user)
    assert "public_repo" in user.token_scopes
    assert decrypt_token(user.encrypted_github_token) == "gho_newElevatedTokenXYZ"

    # Verify ActionLog created
    action_logs = db_session.exec(
        select(ActionLog).where(
            ActionLog.user_id == user.id,
            ActionLog.action == "scope_upgrade",
        )
    ).all()
    import json

    assert len(action_logs) == 1
    assert action_logs[0].status == "succeeded"
    meta_dict = json.loads(action_logs[0].meta)
    assert "public_repo" in meta_dict.get("scopes", "")
