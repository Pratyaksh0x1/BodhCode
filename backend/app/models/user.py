from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


class User(SQLModel, table=True):
    """User database model storing GitHub OAuth credentials and user preferences."""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    github_id: int = Field(unique=True, index=True)
    login: str = Field(index=True)
    name: str | None = Field(default=None)
    avatar_url: str
    email: str | None = Field(default=None)
    preferred_language: str = Field(default="en")
    theme: str = Field(default="dark")
    editor_theme: str = Field(default="auto")
    review_mode: str = Field(default="review")
    encrypted_github_token: str
    token_scopes: str = Field(default="read:user,user:email")
    encrypted_grok_key: str | None = Field(default=None)
    grok_model: str = Field(default="gpt-oss-120b")
    created_at: datetime = Field(default_factory=utc_now)
    last_login_at: datetime = Field(default_factory=utc_now)


class UserPublic(SQLModel):
    """Publicly exposed user details for /auth/me.

    Crucially, encrypted_github_token, encrypted_grok_key, and token_scopes are NEVER included.
    """

    id: int
    login: str
    name: str | None = None
    avatar_url: str
    email: str | None = None
    preferred_language: str
    theme: str
    editor_theme: str = "auto"
    review_mode: str = "review"
    grok_configured: bool = False
    grok_model: str = "gpt-oss-120b"
