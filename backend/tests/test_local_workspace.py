import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.crypto import encrypt_token
from app.auth.deps import get_current_user
from app.main import app
from app.models.user import User, utc_now


@pytest.fixture(name="user_a")
def user_a_fixture(db_session: Session) -> User:
    """Fixture creating user A with encrypted token."""
    user = User(
        github_id=101,
        login="alice",
        name="Alice Coder",
        avatar_url="https://avatar.url/alice",
        encrypted_github_token=encrypt_token("gho_dummy_token_a"),
        token_scopes="read:user,user:email",
        created_at=utc_now(),
        last_login_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_create_local_project_success(
    client: TestClient,
    user_a: User,
    db_session: Session,
) -> None:
    """Test creating a standalone local workspace project with initial files and graph."""
    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        response = client.post(
            "/repos/local",
            headers={"X-Requested-With": "bodhcode"},
            json={"name": "test-editor-workspace"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["owner"] == user_a.login
        assert data["name"] == "test-editor-workspace"
        assert data["status"] == "ready"
        assert data["file_count"] >= 2

        # Test idempotency - calling again returns existing repo
        resp2 = client.post(
            "/repos/local",
            headers={"X-Requested-With": "bodhcode"},
            json={"name": "test-editor-workspace"},
        )
        assert resp2.status_code == 201
        assert resp2.json()["id"] == data["id"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
