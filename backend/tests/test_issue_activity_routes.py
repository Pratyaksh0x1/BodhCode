from datetime import UTC, datetime

import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.crypto import encrypt_token
from app.auth.deps import get_current_user
from app.models.push import ActionLog
from app.models.repo import Repo
from app.models.user import User

CSRF_HEADERS = {"X-Requested-With": "bodhcode"}


@pytest.fixture
def auth_user(db_session: Session) -> User:
    user = User(
        github_id=12345,
        login="octocoder",
        avatar_url="https://avatar.test/octocoder",
        encrypted_github_token=encrypt_token("gho_live_oauth_token"),
        token_scopes="read:user,user:email,public_repo",
        preferred_language="en",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_repo(db_session: Session, auth_user: User) -> Repo:
    repo = Repo(
        user_id=auth_user.id,
        owner="octocoder",
        name="testrepo",
        branch="main",
        commit_sha="commitsha000111222333444555666777888999aa",
        status="ready",
        push_language_override=None,
        source_language="en",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


@respx.mock
def test_issue_preview_edit_and_confirm(
    client: TestClient, db_session: Session, auth_user: User, test_repo: Repo
) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: auth_user

    # Upstream check for repo language
    respx.get(f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}").respond(
        status_code=200,
        json={"name": test_repo.name, "description": "English repo"},
    )
    # GitHub user scope check
    respx.get("https://api.github.com/user").respond(
        status_code=200,
        headers={"x-oauth-scopes": "public_repo"},
        json={"login": auth_user.login},
    )
    # GitHub create issue call
    respx.post(f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}/issues").respond(
        status_code=201,
        json={
            "html_url": f"https://github.com/{test_repo.owner}/{test_repo.name}/issues/42",
            "number": 42,
        },
    )

    try:
        # 1. Preview
        prev_resp = client.post(
            f"/repos/{test_repo.id}/issues/preview",
            json={
                "title": "Bug in parser",
                "body": "Parser fails on JSX",
                "written_in": "en",
            },
            headers=CSRF_HEADERS,
        )
        assert prev_resp.status_code == 200
        prev_data = prev_resp.json()
        preview_id = prev_data["preview_id"]
        assert prev_data["repo_language"] == "en"
        assert prev_data["texts"]["title"]["translated"] == "Bug in parser"

        # 2. Edit preview
        edit_resp = client.post(
            f"/repos/{test_repo.id}/issues/preview/{preview_id}/edit",
            json={
                "title": "Bug in parser (JSX)",
                "body": "Parser crashes on JSX syntax",
            },
            headers=CSRF_HEADERS,
        )
        assert edit_resp.status_code == 200

        # 3. Confirm
        confirm_resp = client.post(
            f"/repos/{test_repo.id}/issues",
            json={"preview_id": preview_id, "confirm": True},
            headers=CSRF_HEADERS,
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["issue_url"] == (
            f"https://github.com/{test_repo.owner}/{test_repo.name}/issues/42"
        )
        assert confirm_resp.json()["number"] == 42

        # 4. Action log verification
        log = db_session.exec(
            select(ActionLog).where(
                ActionLog.user_id == auth_user.id,
                ActionLog.action == "issue_create",
                ActionLog.status == "succeeded",
            )
        ).first()
        assert log is not None
    finally:
        client.app.dependency_overrides.clear()


@respx.mock
def test_issue_secret_blocked(
    client: TestClient, db_session: Session, auth_user: User, test_repo: Repo
) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: auth_user

    try:
        resp = client.post(
            f"/repos/{test_repo.id}/issues/preview",
            json={
                "title": "Issue with key",
                "body": "Here is token ghp_111122223333444455556666777788889999",
            },
            headers=CSRF_HEADERS,
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["detail"]["error"] == "secret_detected"
        assert len(data["detail"]["findings"]) > 0
    finally:
        client.app.dependency_overrides.clear()


@respx.mock
def test_comment_preview_and_confirm(
    client: TestClient, db_session: Session, auth_user: User, test_repo: Repo
) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: auth_user

    respx.get(f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}").respond(
        status_code=200,
        json={"name": test_repo.name, "description": "Repo description"},
    )
    respx.get("https://api.github.com/user").respond(
        status_code=200,
        headers={"x-oauth-scopes": "public_repo"},
        json={"login": auth_user.login},
    )
    respx.post(
        f"https://api.github.com/repos/{test_repo.owner}/{test_repo.name}/issues/42/comments"
    ).respond(
        status_code=201,
        json={
            "html_url": f"https://github.com/{test_repo.owner}/{test_repo.name}/issues/42#issuecomment-123",
            "id": 123,
        },
    )

    try:
        # 1. Preview
        prev_resp = client.post(
            f"/repos/{test_repo.id}/issues/42/comments/preview",
            json={"body": "I can reproduce this on Windows.", "written_in": "en"},
            headers=CSRF_HEADERS,
        )
        assert prev_resp.status_code == 200
        preview_id = prev_resp.json()["preview_id"]

        # 2. Confirm
        confirm_resp = client.post(
            f"/repos/{test_repo.id}/issues/42/comments",
            json={"preview_id": preview_id, "confirm": True},
            headers=CSRF_HEADERS,
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["comment_url"] == (
            f"https://github.com/{test_repo.owner}/{test_repo.name}/issues/42#issuecomment-123"
        )
    finally:
        client.app.dependency_overrides.clear()


def test_activity_log_endpoint(
    client: TestClient, db_session: Session, auth_user: User, test_repo: Repo
) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: auth_user

    now = datetime.now(UTC)
    log1 = ActionLog(
        user_id=auth_user.id,
        repo_id=test_repo.id,
        action="push",
        status="succeeded",
        target_url="https://github.com/pr/1",
        created_at=now,
    )
    log2 = ActionLog(
        user_id=auth_user.id,
        repo_id=test_repo.id,
        action="issue",
        status="succeeded",
        issue_number=10,
        target_url="https://github.com/issues/10",
        created_at=now,
    )
    db_session.add(log1)
    db_session.add(log2)
    db_session.commit()

    try:
        resp = client.get("/user/activity", headers=CSRF_HEADERS)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 2
        actions = [item["action"] for item in items]
        assert "push" in actions
        assert "issue" in actions
    finally:
        client.app.dependency_overrides.clear()
