from datetime import datetime

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.github.limits import INGEST_VERSION
from app.models.user import utc_now


class Repo(SQLModel, table=True):
    """Repository model representing user-ingested repository metadata and state."""

    __tablename__ = "repos"
    __table_args__ = (
        UniqueConstraint("user_id", "owner", "name", name="uq_repos_user_owner_name"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    owner: str = Field(index=True)
    name: str = Field(index=True)
    branch: str = Field(default="main")
    commit_sha: str | None = Field(default=None, index=True)
    status: str = Field(default="queued", index=True)
    error_code: str | None = Field(default=None)
    error_message: str | None = Field(default=None)
    file_count: int = Field(default=0)
    default_branch_size_kb: int = Field(default=0)
    ingest_version: int = Field(default=INGEST_VERSION)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RepoRead(SQLModel):
    """Schema for public repository responses."""

    id: int
    user_id: int
    owner: str
    name: str
    branch: str
    commit_sha: str | None = None
    status: str
    error_code: str | None = None
    error_message: str | None = None
    file_count: int
    default_branch_size_kb: int
    ingest_version: int
    created_at: datetime
    updated_at: datetime


class RepoCreate(SQLModel):
    """Schema for repository creation request."""

    url: str
