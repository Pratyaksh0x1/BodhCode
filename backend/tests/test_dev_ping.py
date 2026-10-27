from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.ai.llm import LLMAuthError, LLMRateLimited, LLMResult, LLMUnavailable, LLMUsage
from app.auth.crypto import encrypt_token
from app.auth.deps import get_current_user
from app.config import Settings
from app.main import create_app
from app.models.user import User, utc_now


@pytest.fixture(name="dev_user")
def dev_user_fixture(db_session: Session) -> User:
    """Fixture creating an authenticated developer user."""
    user = User(
        github_id=999,
        login="devuser",
        name="Dev User",
        avatar_url="https://avatar.url/devuser",
        email="dev@example.com",
        encrypted_github_token=encrypt_token("gho_test_token_dev_123"),
        token_scopes="read:user",
        created_at=utc_now(),
        last_login_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_dev_ping_requires_auth(client: TestClient) -> None:
    response = client.get("/dev/llm-ping")
    assert response.status_code == 401


def test_dev_ping_success(client: TestClient, dev_user: User) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: dev_user
    mock_result = LLMResult(
        text="PONG",
        model="mock-fast-model",
        latency_ms=123.45,
        usage=LLMUsage(prompt_tokens=10, completion_tokens=2, total_tokens=12),
    )

    with patch("app.routes.dev.get_llm_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.chat.return_value = mock_result
        mock_get_client.return_value = mock_client

        response = client.get("/dev/llm-ping")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["text"] == "PONG"
        assert data["latency_ms"] == 123.45
        assert data["model"] == "mock-fast-model"
        assert data["usage"] == {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "total_tokens": 12,
        }

        # Check call arguments
        mock_client.chat.assert_awaited_once()
        _, kwargs = mock_client.chat.call_args
        assert kwargs["feature"] == "ping"
        assert kwargs["fast"] is True
        assert kwargs["max_tokens"] == 64
        assert kwargs["prompt_name"] == "ping"
        assert kwargs["prompt_version"] == 1

    client.app.dependency_overrides.pop(get_current_user, None)


def test_dev_ping_auth_error_maps_to_502(client: TestClient, dev_user: User) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: dev_user

    with patch("app.routes.dev.get_llm_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.chat.side_effect = LLMAuthError("Invalid credentials")
        mock_get_client.return_value = mock_client

        response = client.get("/dev/llm-ping")
        assert response.status_code == 502
        assert "LLM authentication failed" in response.json()["detail"]

    client.app.dependency_overrides.pop(get_current_user, None)


def test_dev_ping_unavailable_maps_to_502(client: TestClient, dev_user: User) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: dev_user

    with patch("app.routes.dev.get_llm_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.chat.side_effect = LLMUnavailable("Groq connection timeout")
        mock_get_client.return_value = mock_client

        response = client.get("/dev/llm-ping")
        assert response.status_code == 502
        assert "LLM service unavailable" in response.json()["detail"]

    client.app.dependency_overrides.pop(get_current_user, None)


def test_dev_ping_rate_limited_maps_to_429(client: TestClient, dev_user: User) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: dev_user

    with patch("app.routes.dev.get_llm_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.chat.side_effect = LLMRateLimited("Rate limit exceeded")
        mock_get_client.return_value = mock_client

        response = client.get("/dev/llm-ping")
        assert response.status_code == 429
        assert "LLM rate limited" in response.json()["detail"]

    client.app.dependency_overrides.pop(get_current_user, None)


def test_dev_ping_not_found_in_production(monkeypatch) -> None:
    # Set ENV to production and recreate app
    monkeypatch.setenv("ENV", "production")
    prod_settings = Settings(ENV="production")

    with patch("app.main.get_settings", return_value=prod_settings):
        prod_app = create_app()
        with TestClient(prod_app) as prod_client:
            response = prod_client.get("/dev/llm-ping")
            assert response.status_code == 404
