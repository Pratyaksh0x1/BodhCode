from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DISALLOWED_PLACEHOLDERS = {
    "change-me",
    "changeme",
    "secret",
    "placeholder",
    "your-secret-key",
    "replace-me",
}


class Settings(BaseSettings):
    """BodhCode application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_SECRET_KEY: str
    FRONTEND_URL: str
    BACKEND_URL: str
    DATABASE_URL: str
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str
    TOKEN_ENCRYPTION_KEY: str

    ENV: Literal["development", "production"] = "development"
    DATA_DIR: str = "./data"

    @field_validator("APP_SECRET_KEY")
    @classmethod
    def validate_app_secret_key(cls, v: str) -> str:
        stripped = v.strip() if v else ""
        if len(stripped) < 32:
            raise ValueError("APP_SECRET_KEY must be at least 32 characters long")
        if stripped.lower() in DISALLOWED_PLACEHOLDERS:
            raise ValueError(f"APP_SECRET_KEY cannot be an insecure placeholder: '{v}'")
        return stripped

    @field_validator("FRONTEND_URL", "BACKEND_URL")
    @classmethod
    def validate_and_normalize_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("URL cannot be empty")
        normalized = v.strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"URL must be a valid http(s) URL: '{v}'")
        return normalized

    @field_validator("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET")
    @classmethod
    def validate_github_credentials(cls, v: str) -> str:
        stripped = v.strip() if v else ""
        if not stripped:
            raise ValueError("Credential cannot be empty")
        if stripped.lower() in DISALLOWED_PLACEHOLDERS:
            raise ValueError(f"Credential cannot be an insecure placeholder: '{v}'")
        return stripped

    @field_validator("TOKEN_ENCRYPTION_KEY")
    @classmethod
    def validate_token_encryption_key(cls, v: str) -> str:
        stripped = v.strip() if v else ""
        if not stripped:
            raise ValueError("TOKEN_ENCRYPTION_KEY cannot be empty")
        try:
            Fernet(stripped.encode("utf-8"))
        except Exception as e:
            raise ValueError(f"TOKEN_ENCRYPTION_KEY is malformed: {e}") from e
        return stripped


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance for dependency injection."""
    return Settings()
