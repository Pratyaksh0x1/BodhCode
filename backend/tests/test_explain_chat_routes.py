"""API integration tests for /repos/{id}/explain and /repos/{id}/chat endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.ai.llm import LLMResult, LLMUsage
from app.auth.deps import get_current_user
from app.main import app
from app.models.graph import RepoGraph
from app.models.repo import Repo
from app.models.user import User
from app.parser.graph import PARSER_VERSION, GraphDoc, NodeDoc, StatsDoc


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create test user."""
    from app.auth.crypto import encrypt_token

    user = User(
        login="testdev",
        avatar_url="https://github.com/testdev.png",
        email="dev@example.com",
        github_id=98765,
        encrypted_github_token=encrypt_token("gho_dummy_test_token"),
        preferred_language="en",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_repo_with_graph(test_user: User, db_session: Session) -> tuple[Repo, RepoGraph]:
    """Create test repo and associated RepoGraph."""
    repo = Repo(
        user_id=test_user.id,
        owner="testdev",
        name="testrepo",
        branch="main",
        commit_sha="commit123",
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    doc = GraphDoc(
        version=PARSER_VERSION,
        repo={"owner": "testdev", "name": "testrepo", "commit_sha": "commit123"},
        nodes=[
            NodeDoc(
                id="src/auth.ts",
                name="auth.ts",
                folder="src",
                size=1200,
                exports=["login"],
                has_default_export=False,
                external_deps=["jwt"],
                unresolved_count=0,
                unresolved_dynamic=0,
                flags=[],
            ),
        ],
        edges=[],
        folders=[],
        stats=StatsDoc(files=1, edges=0, external_packages=1, cycles=0, unresolved=0),
    )

    repo_graph = RepoGraph(
        repo_id=repo.id,
        commit_sha=repo.commit_sha,
        parser_version=PARSER_VERSION,
        graph_json=doc.to_json(),
        node_count=1,
        edge_count=0,
    )
    db_session.add(repo_graph)
    db_session.commit()
    db_session.refresh(repo_graph)

    return repo, repo_graph


@pytest.fixture(autouse=True)
def override_auth_user(test_user: User, client: TestClient):
    """Override get_current_user dependency for routes."""
    app.dependency_overrides[get_current_user] = lambda: test_user
    client.headers["X-Requested-With"] = "bodhcode"
    yield
    client.headers.pop("X-Requested-With", None)
    app.dependency_overrides.pop(get_current_user, None)


def test_explain_endpoint_file_not_in_graph(
    client: TestClient,
    test_repo_with_graph: tuple[Repo, RepoGraph],
) -> None:
    """Unknown file path returns 404 with code file_not_in_graph."""
    repo, _ = test_repo_with_graph
    response = client.post(
        f"/repos/{repo.id}/explain",
        json={"file": "nonexistent/file.ts"},
    )
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "file_not_in_graph"


def test_explain_endpoint_unsupported_language_returns_422(
    client: TestClient,
    test_repo_with_graph: tuple[Repo, RepoGraph],
) -> None:
    """Unsupported language returns 422 Unprocessable Content."""
    repo, _ = test_repo_with_graph
    response = client.post(
        f"/repos/{repo.id}/explain?lang=klingon",
        json={"file": "src/auth.ts"},
    )
    assert response.status_code == 422


def test_explain_endpoint_success(
    client: TestClient,
    test_repo_with_graph: tuple[Repo, RepoGraph],
) -> None:
    """Happy path explain endpoint with mocked LLM response."""
    repo, _ = test_repo_with_graph
    fake_result = LLMResult(
        text="`src/auth.ts` handles user credentials.",
        latency_ms=10.0,
        model="fake-groq",
        usage=LLMUsage(prompt_tokens=50, completion_tokens=20, total_tokens=70),
    )

    fake_client = AsyncMock()
    fake_client.chat.return_value = fake_result

    with patch("app.ai.explain.get_llm_client", return_value=fake_client):
        response = client.post(
            f"/repos/{repo.id}/explain",
            json={"file": "src/auth.ts"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "src/auth.ts" in data["verified_files"]
        assert "handles user credentials" in data["explanation"]
        assert not data["cached"]


def test_chat_endpoint_concurrency_409(
    client: TestClient,
    test_repo_with_graph: tuple[Repo, RepoGraph],
) -> None:
    """Assert second chat request while one is running returns 409 Conflict."""
    repo, _ = test_repo_with_graph

    with patch("app.routes.explain_chat.acquire_chat_slot", return_value=False):
        response = client.post(
            f"/repos/{repo.id}/chat",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["code"] == "chat_in_progress"
