"""Database model for persistent translation caching."""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.user import utc_now


class TranslationCache(SQLModel, table=True):
    """Persistent cache for machine translations keyed by deterministic sha256 hash."""

    __tablename__ = "translation_cache"

    key: str = Field(primary_key=True, max_length=64)
    source_lang: str = Field(max_length=16, index=True)
    target_lang: str = Field(max_length=16, index=True)
    kind: str = Field(max_length=32)
    prompt_version: int
    text: str
    created_at: datetime = Field(default_factory=utc_now, index=True)
