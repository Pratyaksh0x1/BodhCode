"""Tests for repository content viewing and translation routes."""

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.crypto import encrypt_token
from app.models.repo import Repo
from app.models.user import User


@pytest.fixture
def auth_user_and_repo(db_session: Session) -> tuple[User, Repo]:
    """Create test user with encrypted token and an ingested repo."""
    user = User(
        github_id=98765,
        login="content_tester",
        avatar_url="https://github.com/content_tester.png",
        preferred_language="en",
        encrypted_github_token=encrypt_token("gho_valid_dummy_token_for_tests"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    repo = Repo(
        user_id=user.id,  # type: ignore[arg-type]
        owner="tokyo",
        name="project-sakura",
        branch="main",
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    return user, repo


@pytest.fixture(autouse=True)
def mock_translator(monkeypatch):
    """Mock translate_text and translate_many to avoid live LLM calls during route testing."""
    from app.i18n.translate import TranslationResult

    async def fake_translate_text(text, *, source, target, kind, **kwargs):
        return TranslationResult(
            text=f"[TRANSLATED to {target}] {text}",
            source_lang=source,
            target_lang=target,
            from_cache=False,
            ok=True,
        )

    async def fake_translate_many(items, *, source, target, kind, **kwargs):
        return [
            TranslationResult(
                text=f"[TRANSLATED to {target}] {it}",
                source_lang=source,
                target_lang=target,
                from_cache=False,
                ok=True,
            )
            for it in items
        ]

    monkeypatch.setattr("app.routes.content.translate_text", fake_translate_text)
    monkeypatch.setattr("app.routes.content.translate_many", fake_translate_many)


@respx.mock
def test_get_readme_translation_and_language_detection(
    client: TestClient,
    auth_user_and_repo: tuple[User, Repo],
    db_session: Session,
):
    user, repo = auth_user_and_repo

    japanese_readme = (
        "# プロジェクト概要\n\n"
        "このリポジトリはサクラプロジェクトのソースコードを含んでいます。"
        "依存関係の解析と可視化をサポートします。"
    )

    respx.get(f"https://api.github.com/repos/{repo.owner}/{repo.name}/readme").mock(
        return_value=httpx.Response(
            200,
            text=japanese_readme,
            headers={
                "content-type": "application/vnd.github.raw+json",
                "content-disposition": 'attachment; filename="README.md"',
            },
        )
    )

    # Set authenticated session cookie
    client.cookies.set("bodhcode_session", "dummy")
    # Override get_current_user dependency
    from app.auth.deps import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: user

    try:
        response = client.get(f"/repos/{repo.id}/readme")
        assert response.status_code == 200
        data = response.json()
        assert data["file_name"] == "README.md"
        assert data["original"] == japanese_readme
        assert data["source_lang"] == "ja"
        assert data["target_lang"] == "en"

        # Verify Repo.source_language was updated in database
        db_session.refresh(repo)
        assert repo.source_language == "ja"
        assert repo.source_language_confidence is not None
    finally:
        app.dependency_overrides.clear()


def test_get_readme_unsupported_language_returns_422(
    client: TestClient,
    auth_user_and_repo: tuple[User, Repo],
):
    user, repo = auth_user_and_repo
    from app.auth.deps import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = client.get(f"/repos/{repo.id}/readme?lang=klingon")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_get_readme_unauthorized_repo_returns_404(
    client: TestClient,
    auth_user_and_repo: tuple[User, Repo],
    db_session: Session,
):
    user, repo = auth_user_and_repo
    other_user = User(
        github_id=55555,
        login="intruder",
        avatar_url="https://github.com/intruder.png",
        encrypted_github_token=encrypt_token("gho_dummy"),
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    from app.auth.deps import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: other_user
    try:
        response = client.get(f"/repos/{repo.id}/readme")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@respx.mock
def test_list_issues_and_pr_filter(
    client: TestClient,
    auth_user_and_repo: tuple[User, Repo],
):
    user, repo = auth_user_and_repo
    repo.source_language = "ja"

    mock_issues = [
        {
            "number": 101,
            "title": "バグの報告",
            "body": "問題が発生しました",
            "state": "open",
            "user": {"login": "dev1", "avatar_url": "https://avatars.com/1"},
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "labels": [{"name": "bug", "color": "red"}],
            "comments": 2,
            "html_url": "https://github.com/tokyo/project-sakura/issues/101",
        },
        {
            "number": 102,
            "title": "プルリクエスト",
            "body": "PR",
            "state": "open",
            "pull_request": {"url": "https://api.github.com/repos/tokyo/project-sakura/pulls/102"},
            "user": {"login": "dev2", "avatar_url": "https://avatars.com/2"},
            "created_at": "2026-01-02T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
            "labels": [],
            "comments": 0,
            "html_url": "https://github.com/tokyo/project-sakura/pull/102",
        },
    ]

    respx.get(f"https://api.github.com/repos/{repo.owner}/{repo.name}/issues").mock(
        return_value=httpx.Response(200, json=mock_issues)
    )

    from app.auth.deps import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = client.get(f"/repos/{repo.id}/issues")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["number"] == 101
        assert data["items"][0]["original_title"] == "バグの報告"
    finally:
        app.dependency_overrides.clear()
