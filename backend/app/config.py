import os
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from pydantic import field_validator, model_validator
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

    ENV: Literal["development", "production", "test"] = "development"
    DATA_DIR: str = "./data"
    ALLOWED_ORIGINS: list[str] = []

    # Groq LLM Configuration
    GROQ_API_KEY: str
    GROQ_MODEL: str
    GROQ_FAST_MODEL: str | None = None
    LLM_MAX_CONCURRENCY: int = 3
    LLM_TIMEOUT_SECONDS: float = 60.0

    # LangSmith Tracing & Observability
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "bodhcode"
    LANGSMITH_ENDPOINT: str | None = None

    @field_validator("LLM_MAX_CONCURRENCY")
    @classmethod
    def validate_llm_concurrency(cls, v: int) -> int:
        if not (1 <= v <= 10):
            raise ValueError("LLM_MAX_CONCURRENCY must be between 1 and 10")
        return v

    @field_validator("GROQ_API_KEY", "GROQ_MODEL")
    @classmethod
    def validate_groq_required(cls, v: str) -> str:
        stripped = v.strip() if v else ""
        if not stripped:
            raise ValueError("Groq configuration value cannot be empty")
        return stripped

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        if isinstance(v, list):
            return [str(o).strip() for o in v if str(o).strip()]
        return []

    @model_validator(mode="after")
    def _validate_langsmith_and_defaults(self) -> "Settings":
        if not self.GROQ_FAST_MODEL:
            self.GROQ_FAST_MODEL = self.GROQ_MODEL
        if self.LANGSMITH_TRACING and (
            not self.LANGSMITH_API_KEY or not self.LANGSMITH_API_KEY.strip()
        ):
            raise ValueError("LANGSMITH_API_KEY is required when LANGSMITH_TRACING is true")
        return self

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


def export_langsmith_env(settings: Settings) -> None:
    """Copy LANGSMITH_* configuration values into os.environ for the LangSmith SDK.

    pydantic-settings does not export values to os.environ, but the LangSmith SDK
    reads environment variables. This must be invoked explicitly at startup.
    """
    if settings.LANGSMITH_TRACING:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
        if settings.LANGSMITH_API_KEY:
            os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
        if settings.LANGSMITH_ENDPOINT:
            os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    else:
        os.environ["LANGSMITH_TRACING"] = "false"
