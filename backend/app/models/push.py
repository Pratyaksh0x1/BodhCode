"""SQLModel models for GitHub push, previews, action logs, and audit trails."""

import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.user import utc_now


class ActionLog(SQLModel, table=True):
    """Audit log tracking all outgoing GitHub operations.

    Crucially, logs contain only IDs and URLs, NEVER tokens, API keys,
    or raw file contents.
    """

    __tablename__ = "action_logs"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="users.id")
    repo_id: int | None = Field(default=None, index=True, foreign_key="repos.id")
    action: str = Field(index=True)  # "push" | "issue_create" | "comment_create" | "scope_upgrade"
    status: str = Field(index=True)  # "previewed" | "confirmed" | "succeeded" | "failed"
    target_url: str | None = Field(default=None)
    meta: str = Field(default="{}")  # Sanitized JSON metadata (no secrets, no file contents)
    created_at: datetime = Field(default_factory=utc_now)


class PushPreview(SQLModel, table=True):
    """Stored preview contract ensuring only explicitly verified texts and files are pushed.

    The confirm step sends ONLY what is stored here.
    """

    __tablename__ = "push_previews"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: int = Field(index=True, foreign_key="users.id")
    repo_id: int = Field(index=True, foreign_key="repos.id")
    kind: str = Field(index=True)  # "push" | "issue" | "comment"
    payload: str  # JSON payload of exact texts, language, and file changes
    payload_hash: str = Field(index=True)  # SHA-256 of the exact payload string
    expires_at: datetime = Field(index=True)  # 30-minute validity
    consumed_at: datetime | None = Field(default=None)  # Timestamp when confirmed
    created_at: datetime = Field(default_factory=utc_now)
