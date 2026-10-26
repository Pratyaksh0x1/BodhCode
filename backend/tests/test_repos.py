import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.crypto import encrypt_token
from app.auth.deps import get_current_user
from app.github.ingest import ingest_repo
from app.github.limits import INGEST_VERSION
from app.models.repo import Repo
from app.models.user import User, utc_now


@pytest.fixture(name="user_a")
def user_a_fixture(db_session: Session) -> User:
    """Fixture creating user A with encrypted token."""
    user = User(
        github_id=101,
        login="alice",
        name="Alice Coder",
        avatar_url="https://avatar.url/alice",
        email="alice@example.com",
        encrypted_github_token=encrypt_token("gho_alice_secret_token_123"),
        token_scopes="read:user",
        created_at=utc_now(),
        last_login_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(name="user_b")
def user_b_fixture(db_session: Session) -> User:
    """Fixture creating user B with encrypted token."""
    user = User(
        github_id=102,
        login="bob",
        name="Bob Builder",
        avatar_url="https://avatar.url/bob",
        email="bob@example.com",
        encrypted_github_token=encrypt_token("gho_bob_secret_token_456"),
        token_scopes="read:user",
        created_at=utc_now(),
        last_login_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_sample_zip() -> bytes:
    """Create a minimal valid GitHub repo zipball in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("owner-sample-repo-sha123/package.json", '{"name": "sample"}')
        zf.writestr("owner-sample-repo-sha123/src/index.ts", "export const main = 42;")
        zf.writestr("owner-sample-repo-sha123/node_modules/skipped.js", "ignored")
    return buf.getvalue()


def test_create_repo_requires_csrf(client: TestClient, user_a: User):
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        resp = client.post("/repos", json={"url": "https://github.com/facebook/react"})
        assert resp.status_code == 403
        assert "CSRF" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_create_repo_valid_url(client: TestClient, user_a: User, db_session: Session):
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        with patch("app.routes.repos.ingest_repo", new_callable=AsyncMock) as mock_ingest:
            resp = client.post(
                "/repos",
                json={"url": "facebook/react"},
                headers={"X-Requested-With": "bodhcode"},
            )
            assert resp.status_code == 202
            data = resp.json()
            assert data["owner"] == "facebook"
            assert data["name"] == "react"
            assert data["status"] == "queued"
            assert data["user_id"] == user_a.id

            # Verify in db
            repo = db_session.get(Repo, data["id"])
            assert repo is not None
            assert repo.owner == "facebook"
            assert repo.name == "react"

            # Ingestion background task should be enqueued
            mock_ingest.assert_called_once_with(repo.id)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_create_repo_invalid_url(client: TestClient, user_a: User):
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        resp = client.post(
            "/repos",
            json={"url": "https://gitlab.com/owner/repo"},
            headers={"X-Requested-With": "bodhcode"},
        )
        assert resp.status_code == 422
        assert "Only public GitHub repositories" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_list_repos_tenant_isolation_and_sorting(
    client: TestClient,
    user_a: User,
    user_b: User,
    db_session: Session,
):
    from app.main import app

    now = utc_now()
    repo_a1 = Repo(
        user_id=user_a.id,
        owner="facebook",
        name="react",
        branch="main",
        status="fetched",
        created_at=now,
        updated_at=now,
    )
    repo_a2 = Repo(
        user_id=user_a.id,
        owner="vercel",
        name="next.js",
        branch="canary",
        status="queued",
        created_at=now,
        updated_at=now,
    )
    repo_b = Repo(
        user_id=user_b.id,
        owner="torvalds",
        name="linux",
        branch="master",
        status="fetched",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([repo_a1, repo_a2, repo_b])
    db_session.commit()

    # User A queries /repos
    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        resp_a = client.get("/repos")
        assert resp_a.status_code == 200
        repos_a = resp_a.json()
        assert len(repos_a) == 2
        names_a = [r["name"] for r in repos_a]
        assert "react" in names_a
        assert "next.js" in names_a
        assert "linux" not in names_a
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # User B queries /repos
    app.dependency_overrides[get_current_user] = lambda: user_b
    try:
        resp_b = client.get("/repos")
        assert resp_b.status_code == 200
        repos_b = resp_b.json()
        assert len(repos_b) == 1
        assert repos_b[0]["name"] == "linux"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_get_repo_multi_tenant_404_never_403(
    client: TestClient,
    user_a: User,
    user_b: User,
    db_session: Session,
):
    from app.main import app

    now = utc_now()
    repo_a = Repo(
        user_id=user_a.id,
        owner="secret",
        name="private-alpha",
        branch="main",
        status="fetched",
        created_at=now,
        updated_at=now,
    )
    db_session.add(repo_a)
    db_session.commit()
    db_session.refresh(repo_a)

    # User B queries repo owned by User A -> Must return 404, NEVER 403
    app.dependency_overrides[get_current_user] = lambda: user_b
    try:
        resp = client.get(f"/repos/{repo_a.id}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Repository not found"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_delete_repo_deletes_db_row(
    client: TestClient,
    user_a: User,
    db_session: Session,
):
    from app.main import app

    now = utc_now()
    repo = Repo(
        user_id=user_a.id,
        owner="test-owner",
        name="test-repo",
        branch="main",
        status="fetched",
        created_at=now,
        updated_at=now,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        resp = client.delete(f"/repos/{repo.id}", headers={"X-Requested-With": "bodhcode"})
        assert resp.status_code == 204

        # Verify row deleted from DB
        deleted = db_session.get(Repo, repo.id)
        assert deleted is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_ingest_repo_happy_path(
    user_a: User,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # Set DATA_DIR to tmp_path
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()

    now = utc_now()
    repo = Repo(
        user_id=user_a.id,
        owner="sample-owner",
        name="sample-name",
        branch="main",
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    zip_bytes = create_sample_zip()

    async with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get("/repos/sample-owner/sample-name").respond(
            200,
            json={"default_branch": "main", "size": 250, "private": False},
        )
        respx_mock.get("/repos/sample-owner/sample-name/commits/main").respond(
            200,
            json={"sha": "sha123456789"},
        )
        respx_mock.get("/repos/sample-owner/sample-name/zipball/sha123456789").respond(
            200,
            content=zip_bytes,
        )

        await ingest_repo(repo.id)

    db_session.refresh(repo)
    assert repo.status == "fetched"
    assert repo.commit_sha == "sha123456789"
    assert repo.file_count == 2  # package.json and src/index.ts (node_modules skipped)
    assert repo.ingest_version == INGEST_VERSION

    # Check extracted files on disk
    src_dir = tmp_path / "repos" / "sample-owner" / "sample-name" / "sha123456789" / "src"
    assert (src_dir / "package.json").exists()
    assert (src_dir / "src" / "index.ts").exists()
    assert (src_dir / ".ingest_version").read_text(encoding="utf-8").strip() == str(INGEST_VERSION)


@pytest.mark.asyncio
async def test_ingest_repo_github_404_marks_failed(
    user_a: User,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()

    now = utc_now()
    repo = Repo(
        user_id=user_a.id,
        owner="ghost",
        name="does-not-exist",
        branch="main",
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    async with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get("/repos/ghost/does-not-exist").respond(404)

        await ingest_repo(repo.id)

    db_session.refresh(repo)
    assert repo.status == "failed"
    assert repo.error_code == "not_found"
    assert "only public repos are supported" in repo.error_message


@pytest.mark.asyncio
async def test_ingest_repo_shared_cache_hit(
    user_a: User,
    user_b: User,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()

    now = utc_now()
    repo_a = Repo(
        user_id=user_a.id,
        owner="org",
        name="shared-project",
        branch="main",
        status="queued",
        created_at=now,
        updated_at=now,
    )
    repo_b = Repo(
        user_id=user_b.id,
        owner="org",
        name="shared-project",
        branch="main",
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([repo_a, repo_b])
    db_session.commit()
    db_session.refresh(repo_a)
    db_session.refresh(repo_b)

    zip_bytes = create_sample_zip()

    async with respx.mock(base_url="https://api.github.com") as respx_mock:
        respx_mock.get("/repos/org/shared-project").respond(
            200,
            json={"default_branch": "main", "size": 100, "private": False},
        )
        respx_mock.get("/repos/org/shared-project/commits/main").respond(
            200,
            json={"sha": "sha_shared_999"},
        )
        zip_route = respx_mock.get("/repos/org/shared-project/zipball/sha_shared_999").respond(
            200,
            content=zip_bytes,
        )

        # First ingest by User A: downloads and extracts
        await ingest_repo(repo_a.id)
        assert zip_route.call_count == 1

        # Second ingest by User B with same SHA: hits cache, should NOT download again
        await ingest_repo(repo_b.id)
        assert zip_route.call_count == 1  # Still 1 call!

    db_session.refresh(repo_a)
    db_session.refresh(repo_b)
    assert repo_a.status == "fetched"
    assert repo_b.status == "fetched"
    assert repo_a.file_count == 2
    assert repo_b.file_count == 2
