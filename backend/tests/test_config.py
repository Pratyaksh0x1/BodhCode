import pytest
from pydantic import ValidationError

from app.config import Settings

VALID_FERNET_KEY = "rMRb5uNBakxqd2ErZ0BYAe-N1amHtrQVayLBJpdXiOA="


def test_settings_valid_initialization():
    settings = Settings(
        APP_SECRET_KEY="a" * 32,
        FRONTEND_URL="http://localhost:5173/",
        BACKEND_URL="http://localhost:8000/",
        DATABASE_URL="sqlite:///./test.db",
        GITHUB_CLIENT_ID="gh_client_id_123",
        GITHUB_CLIENT_SECRET="gh_client_secret_456",
        TOKEN_ENCRYPTION_KEY=VALID_FERNET_KEY,
    )
    assert settings.APP_SECRET_KEY == "a" * 32
    assert settings.FRONTEND_URL == "http://localhost:5173"
    assert settings.BACKEND_URL == "http://localhost:8000"
    assert settings.GITHUB_CLIENT_ID == "gh_client_id_123"
    assert settings.GITHUB_CLIENT_SECRET == "gh_client_secret_456"
    assert settings.TOKEN_ENCRYPTION_KEY == VALID_FERNET_KEY
    assert settings.ENV == "development"
    assert settings.DATA_DIR == "./data"


def test_settings_raises_when_app_secret_key_missing():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_SECRET_KEY="",
            FRONTEND_URL="http://localhost:5173",
            BACKEND_URL="http://localhost:8000",
            DATABASE_URL="sqlite:///./test.db",
            GITHUB_CLIENT_ID="gh_client_id_123",
            GITHUB_CLIENT_SECRET="gh_client_secret_456",
            TOKEN_ENCRYPTION_KEY=VALID_FERNET_KEY,
        )
    assert "APP_SECRET_KEY" in str(exc_info.value)


def test_settings_raises_when_app_secret_key_too_short():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_SECRET_KEY="short-secret",
            FRONTEND_URL="http://localhost:5173",
            BACKEND_URL="http://localhost:8000",
            DATABASE_URL="sqlite:///./test.db",
            GITHUB_CLIENT_ID="gh_client_id_123",
            GITHUB_CLIENT_SECRET="gh_client_secret_456",
            TOKEN_ENCRYPTION_KEY=VALID_FERNET_KEY,
        )
    assert "APP_SECRET_KEY" in str(exc_info.value)
    assert "at least 32 characters" in str(exc_info.value)


def test_settings_raises_when_app_secret_key_is_placeholder():
    for placeholder in ["change-me", "changeme", "placeholder", "your-secret-key"]:
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                APP_SECRET_KEY=placeholder,
                FRONTEND_URL="http://localhost:5173",
                BACKEND_URL="http://localhost:8000",
                DATABASE_URL="sqlite:///./test.db",
                GITHUB_CLIENT_ID="gh_client_id_123",
                GITHUB_CLIENT_SECRET="gh_client_secret_456",
                TOKEN_ENCRYPTION_KEY=VALID_FERNET_KEY,
            )
        assert "APP_SECRET_KEY" in str(exc_info.value)


def test_settings_normalizes_trailing_slash_on_urls():
    settings = Settings(
        APP_SECRET_KEY="b" * 32,
        FRONTEND_URL="http://localhost:5173////",
        BACKEND_URL="https://api.example.com///",
        DATABASE_URL="sqlite:///./test.db",
        GITHUB_CLIENT_ID="gh_client_id_123",
        GITHUB_CLIENT_SECRET="gh_client_secret_456",
        TOKEN_ENCRYPTION_KEY=VALID_FERNET_KEY,
    )
    assert settings.FRONTEND_URL == "http://localhost:5173"
    assert settings.BACKEND_URL == "https://api.example.com"


def test_settings_raises_on_invalid_urls():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_SECRET_KEY="c" * 32,
            FRONTEND_URL="not-a-valid-url",
            BACKEND_URL="http://localhost:8000",
            DATABASE_URL="sqlite:///./test.db",
            GITHUB_CLIENT_ID="gh_client_id_123",
            GITHUB_CLIENT_SECRET="gh_client_secret_456",
            TOKEN_ENCRYPTION_KEY=VALID_FERNET_KEY,
        )
    assert "FRONTEND_URL" in str(exc_info.value)


def test_settings_raises_on_missing_github_credentials():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_SECRET_KEY="a" * 32,
            FRONTEND_URL="http://localhost:5173",
            BACKEND_URL="http://localhost:8000",
            DATABASE_URL="sqlite:///./test.db",
            GITHUB_CLIENT_ID="",
            GITHUB_CLIENT_SECRET="secret",
            TOKEN_ENCRYPTION_KEY=VALID_FERNET_KEY,
        )
    assert "GITHUB_CLIENT_ID" in str(exc_info.value)


def test_settings_raises_on_malformed_token_encryption_key():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_SECRET_KEY="a" * 32,
            FRONTEND_URL="http://localhost:5173",
            BACKEND_URL="http://localhost:8000",
            DATABASE_URL="sqlite:///./test.db",
            GITHUB_CLIENT_ID="gh_client_id_123",
            GITHUB_CLIENT_SECRET="gh_client_secret_456",
            TOKEN_ENCRYPTION_KEY="not-a-valid-fernet-key",
        )
    assert "TOKEN_ENCRYPTION_KEY" in str(exc_info.value)
