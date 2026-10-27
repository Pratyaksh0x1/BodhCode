"""Database model for caching grounded file explanations."""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.user import utc_now


class ExplainCache(SQLModel, table=True):
    """Persistent cache for grounded file explanations."""

    __tablename__ = "explain_cache"

    key: str = Field(primary_key=True, max_length=64)
    commit_sha: str = Field(max_length=64, index=True)
    file_path: str = Field(index=True)
    language: str = Field(max_length=16, index=True)
    prompt_version: int
    response_json: str
    created_at: datetime = Field(default_factory=utc_now, index=True)
