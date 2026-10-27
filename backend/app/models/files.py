"""Database models for per-user working copies in the code editor."""

from datetime import datetime

from sqlalchemy import Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.user import utc_now


class WorkingFile(SQLModel, table=True):
    """Represents a modified, added, or deleted file in a user's working copy."""

    __tablename__ = "working_files"
    __table_args__ = (
        UniqueConstraint("user_id", "repo_id", "path", name="uq_working_files_user_repo_path"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    repo_id: int = Field(foreign_key="repos.id", index=True, nullable=False)
    path: str = Field(index=True, nullable=False, max_length=300)
    content: str = Field(sa_column=Column(Text, nullable=False, default=""))
    is_new: bool = Field(default=False, nullable=False)
    is_deleted: bool = Field(default=False, nullable=False)
    base_hash: str | None = Field(default=None, nullable=True, max_length=64)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
