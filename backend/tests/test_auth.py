from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from starlette.responses import Response

from app.auth.github_oauth import get_oauth
from app.auth.service import upsert_github_user
from app.models.user import User


def test_auth_me_unauthorized_without_cookie(client: TestClient):
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_csrf_header_protection(client: TestClient):
    # Mutating request without X-Requested-With header fails with 403
    resp_missing = client.post("/auth/logout")
    assert resp_missing.status_code == 403
    assert "CSRF" in resp_missing.json()["detail"]

    # Mutating request with incorrect header fails with 403
    resp_wrong = client.post("/auth/logout", headers={"X-Requested-With": "wrong"})
    assert resp_wrong.status_code == 403

    # Mutating request with correct X-Requested-With: bodhcode passes
    resp_valid = client.post("/auth/logout", headers={"X-Requested-With": "bodhcode"})
    assert resp_valid.status_code == 204


def test_upsert_helper_creates_and_updates_without_duplicates(db_session: Session):
    # Initial create
    user1 = upsert_github_user(
        db_session,
        github_id=98765,
        login="octocat",
        name="The Octocat",
        avatar_url="https://github.com/images/error/octocat_happy.gif",
        email="octocat@github.com",
        access_token="gho_initialAccessToken123",
        token_scopes="read:user,user:email",
    )
    assert user1.id is not None
    assert user1.github_id == 98765
    assert user1.login == "octocat"
    assert user1.name == "The Octocat"

    # Second call for same github_id updates existing user
    user2 = upsert_github_user(
        db_session,
        github_id=98765,
        login="octocat-updated",
        name="Updated Octocat",
        avatar_url="https://github.com/images/avatar_new.gif",
        email="octo_new@github.com",
        access_token="gho_freshAccessToken456",
        token_scopes="read:user",
    )

    assert user2.id == user1.id
    assert user2.login == "octocat-updated"
    assert user2.name == "Updated Octocat"

    # Verify only 1 row exists
    users = db_session.exec(select(User).where(User.github_id == 98765)).all()
    assert len(users) == 1


def test_callback_replaces_attacker_session_and_authenticates(
    client: TestClient,
    monkeypatch,
):
    # Establish pre-login session state (simulating attacker session fixation attempt)
    # We set session cookie with an attacker state
    client.cookies.set("bodhcode_session", "pre_existing_attacker_session_cookie")

    oauth_client = get_oauth().github

    # Mock authorize_access_token
    mock_token = {
        "access_token": "gho_mockGithubTokenABC123",
        "scope": "read:user user:email",
        "token_type": "bearer",
    }
    monkeypatch.setattr(
        oauth_client,
        "authorize_access_token",
        AsyncMock(return_value=mock_token),
    )

    # Mock GET /user and GET /user/emails
    mock_user_profile = {
        "id": 112233,
        "login": "dev-user",
        "name": "Developer User",
        "avatar_url": "https://avatars.githubusercontent.com/u/112233",
        "email": None,
    }
    mock_emails_data = [
        {"email": "secondary@example.com", "primary": False, "verified": True},
        {"email": "primary@example.com", "primary": True, "verified": True},
    ]

    async def mock_get(url, token=None):
        resp = MagicMock(spec=Response)
        resp.status_code = 200
        if url == "user":
            resp.json = MagicMock(return_value=mock_user_profile)
        elif url == "user/emails":
            resp.json = MagicMock(return_value=mock_emails_data)
        return resp

    monkeypatch.setattr(oauth_client, "get", mock_get)

    # Execute callback
    callback_resp = client.get(
        "/auth/github/callback?code=mock_code&state=mock_state",
        follow_redirects=False,
    )
    assert callback_resp.status_code == 302
    assert callback_resp.headers["location"] == "http://localhost:5173/"

    # Now verify /auth/me returns the authenticated user
    me_resp = client.get("/auth/me")
    assert me_resp.status_code == 200
    user_data = me_resp.json()
    assert "github_id" not in user_data
    assert user_data["login"] == "dev-user"
    assert user_data["name"] == "Developer User"
    assert user_data["email"] == "primary@example.com"
    assert user_data["avatar_url"] == "https://avatars.githubusercontent.com/u/112233"
    assert user_data["preferred_language"] == "en"
    assert user_data["theme"] == "dark"

    # CRITICAL: Verify NO secret token fields are returned
    assert "encrypted_github_token" not in user_data
    assert "token_scopes" not in user_data
    assert "access_token" not in user_data


def test_logout_clears_session(client: TestClient, monkeypatch):
    oauth_client = get_oauth().github
    monkeypatch.setattr(
        oauth_client,
        "authorize_access_token",
        AsyncMock(return_value={"access_token": "gho_testToken", "scope": "read:user"}),
    )

    async def mock_get(url, token=None):
        resp = MagicMock(spec=Response)
        resp.status_code = 200
        if url == "user":
            resp.json = MagicMock(
                return_value={
                    "id": 556677,
                    "login": "logout-user",
                    "avatar_url": "https://avatar.url/img.png",
                    "email": "logout@test.com",
                }
            )
        return resp

    monkeypatch.setattr(oauth_client, "get", mock_get)

    # Log in
    client.get("/auth/github/callback?code=abc")
    me_before = client.get("/auth/me")
    assert me_before.status_code == 200

    # Logout
    logout_resp = client.post("/auth/logout", headers={"X-Requested-With": "bodhcode"})
    assert logout_resp.status_code == 204

    # Subsequent /auth/me must return 401
    me_after = client.get("/auth/me")
    assert me_after.status_code == 401


def test_callback_handles_oauth_error_gracefully(client: TestClient, monkeypatch):
    oauth_client = get_oauth().github
    monkeypatch.setattr(
        oauth_client,
        "authorize_access_token",
        AsyncMock(side_effect=Exception("User cancelled authorization")),
    )

    callback_resp = client.get("/auth/github/callback?error=access_denied", follow_redirects=False)
    assert callback_resp.status_code == 302
    assert callback_resp.headers["location"] == "http://localhost:5173/?auth_error=denied"
