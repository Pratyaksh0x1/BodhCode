"""Unit tests for security headers, request body size limits, LRU eviction, and cleanup sweep."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.auth.crypto import encrypt_token
from app.auth.deps import get_current_user
from app.cleanup import cleanup_sweep, evict_repo_cache_lru
from app.main import create_app
from app.models.push import PushPreview
from app.models.repo import Repo
from app.models.translation import TranslationCache
from app.models.user import User


@pytest.fixture(name="db_session")
def db_session_fixture() -> Generator[Session, None, None]:
    """Provide an isolated in-memory SQLite database session."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_security_headers_on_responses() -> None:
    """Verify security headers (nosniff, referrer, CSP on HTML) are applied."""
    app = create_app()

    @app.get("/test/html")
    def html_view() -> HTMLResponse:
        return HTMLResponse("<html><body>Hello</body></html>")

    @app.get("/test/json")
    def json_view() -> JSONResponse:
        return JSONResponse({"ok": True})

    client = TestClient(app)

    # JSON response
    r1 = client.get("/test/json")
    assert r1.status_code == 200
    assert r1.headers["X-Content-Type-Options"] == "nosniff"
    assert r1.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    # HTML response
    r2 = client.get("/test/html")
    assert r2.status_code == 200
    assert r2.headers["X-Content-Type-Options"] == "nosniff"
    assert r2.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in r2.headers["Content-Security-Policy"]


def test_authenticated_json_cache_control_no_store() -> None:
    """Verify Cache-Control: no-store is applied to authenticated JSON endpoints."""
    app = create_app()
    client = TestClient(app)

    user = User(
        id=1,
        github_id=1,
        login="testuser",
        avatar_url="https://avatar.test",
        encrypted_github_token=encrypt_token("gho_test"),
    )
    app.dependency_overrides[get_current_user] = lambda: user

    # Access an authenticated JSON endpoint under /repos
    resp = client.get("/repos", headers={"X-Requested-With": "bodhcode"})
    assert resp.headers.get("Cache-Control") == "no-store"


def test_request_body_size_limits() -> None:
    """Verify 413 Payload Too Large on oversized bodies."""
    app = create_app()

    @app.post("/test/upload")
    def upload_view(data: dict[str, str]) -> dict[str, str]:
        return data

    @app.post("/evals/import-skill")
    def import_skill_view(data: dict[str, str]) -> dict[str, str]:
        return data

    client = TestClient(app)

    # 1. Normal payload accepted
    r1 = client.post(
        "/test/upload",
        json={"data": "small"},
        headers={"X-Requested-With": "bodhcode"},
    )
    assert r1.status_code == 200

    # 2. Oversized payload on small-limit endpoint (> 20 KB)
    oversized_small = "x" * (25 * 1024)
    r2 = client.post(
        "/evals/import-skill",
        json={"data": oversized_small},
        headers={"X-Requested-With": "bodhcode"},
    )
    assert r2.status_code == 413
    assert "Payload Too Large" in r2.json()["detail"]

    # 3. Payload under 20 KB accepted on small-limit endpoint
    under_small = "x" * (10 * 1024)
    r3 = client.post(
        "/evals/import-skill",
        json={"data": under_small},
        headers={"X-Requested-With": "bodhcode"},
    )
    assert r3.status_code == 200

    # 4. Oversized payload on default endpoint (> 1.5 MB)
    oversized_large = "x" * int(1.6 * 1024 * 1024)
    r4 = client.post(
        "/test/upload",
        json={"data": oversized_large},
        headers={"X-Requested-With": "bodhcode"},
    )
    assert r4.status_code == 413
    assert "Payload Too Large" in r4.json()["detail"]


def test_cleanup_sweep(db_session: Session) -> None:
    """Verify cleanup sweep purges expired previews, old translations, and resets stuck repos."""
    now = datetime.now(UTC)

    # User
    user = User(
        id=10,
        github_id=10,
        login="cleaner",
        avatar_url="https://avatar.test",
        encrypted_github_token=encrypt_token("gho_test"),
    )
    db_session.add(user)
    db_session.commit()

    # Previews: one expired 2 hours ago (should delete), one expired 10 min ago (keep)
    old_preview = PushPreview(
        id="preview-old",
        user_id=user.id,
        repo_id=1,
        kind="push",
        payload="{}",
        payload_hash="hash_old",
        expires_at=now - timedelta(hours=2),
    )
    fresh_preview = PushPreview(
        id="preview-fresh",
        user_id=user.id,
        repo_id=1,
        kind="push",
        payload="{}",
        payload_hash="hash_fresh",
        expires_at=now - timedelta(minutes=10),
    )
    db_session.add(old_preview)
    db_session.add(fresh_preview)

    # Translations: one created 35 days ago (should delete), one 5 days ago (keep)
    old_trans = TranslationCache(
        key="key-old",
        source_lang="en",
        target_lang="hi",
        kind="test",
        prompt_version=1,
        text="पुराना",
        created_at=now - timedelta(days=35),
    )
    fresh_trans = TranslationCache(
        key="key-fresh",
        source_lang="en",
        target_lang="hi",
        kind="test",
        prompt_version=1,
        text="नया",
        created_at=now - timedelta(days=5),
    )
    db_session.add(old_trans)
    db_session.add(fresh_trans)

    # Repos: one stuck in fetching > 40 min (reset), one fetching 5 min ago (keep)
    stuck_repo = Repo(
        user_id=user.id,
        owner="owner",
        name="stuck",
        status="fetching",
        updated_at=now - timedelta(minutes=40),
    )
    active_repo = Repo(
        user_id=user.id,
        owner="owner",
        name="active",
        status="fetching",
        updated_at=now - timedelta(minutes=5),
    )
    db_session.add(stuck_repo)
    db_session.add(active_repo)

    db_session.commit()

    # Execute cleanup sweep
    result = cleanup_sweep(db_session)
    assert result["previews_deleted"] == 1
    assert result["translations_deleted"] == 1
    assert result["stalled_repos_reset"] == 1

    # Verify state
    assert db_session.get(PushPreview, "preview-old") is None
    assert db_session.get(PushPreview, "preview-fresh") is not None

    assert db_session.get(TranslationCache, "key-old") is None
    assert db_session.get(TranslationCache, "key-fresh") is not None

    db_session.refresh(stuck_repo)
    assert stuck_repo.status == "error"
    assert stuck_repo.error_code == "timeout"

    db_session.refresh(active_repo)
    assert active_repo.status == "fetching"


def test_lru_repo_cache_eviction(tmp_path: Path, db_session: Session) -> None:
    """Verify LRU eviction frees space when quota exceeded while protecting active repos."""
    repos_dir = tmp_path / "repos"

    # Repo 1: oldest, inactive -> should be evicted
    r1_dir = repos_dir / "user1" / "repo1" / "commit1" / "src"
    r1_dir.mkdir(parents=True)
    (r1_dir / "code.ts").write_bytes(b"A" * 1000)
    # Set older mtime
    os.utime(r1_dir.parent, (1000, 1000))

    # Repo 2: newest, inactive -> kept if quota permits
    r2_dir = repos_dir / "user2" / "repo2" / "commit2" / "src"
    r2_dir.mkdir(parents=True)
    (r2_dir / "code.ts").write_bytes(b"B" * 1000)
    os.utime(r2_dir.parent, (2000, 2000))

    # Repo 3: oldest but in 'analyzing' state -> MUST NOT be evicted
    r3_dir = repos_dir / "user3" / "repo3" / "commit3" / "src"
    r3_dir.mkdir(parents=True)
    (r3_dir / "code.ts").write_bytes(b"C" * 1000)
    os.utime(r3_dir.parent, (500, 500))

    user = User(
        id=1,
        github_id=1,
        login="u3",
        avatar_url="https://avatar.test",
        encrypted_github_token=encrypt_token("tok"),
    )
    db_session.add(user)
    db_session.commit()

    active_repo = Repo(
        user_id=user.id,
        owner="user3",
        name="repo3",
        status="analyzing",
    )
    db_session.add(active_repo)
    db_session.commit()

    # Total bytes is ~3000 bytes. Set max_bytes to 2500 bytes.
    evicted = evict_repo_cache_lru(tmp_path, max_bytes=2500, session=db_session)

    # r1 was evicted
    assert len(evicted) == 1
    assert "repo1" in evicted[0]
    assert not (r1_dir.parent).exists()

    # r2 was kept
    assert (r2_dir.parent).exists()

    # r3 was protected because status is analyzing
    assert (r3_dir.parent).exists()
