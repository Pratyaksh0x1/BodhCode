"""add translation cache and repo source language

Revision ID: 302ccfd153d6
Revises: b5bf9c8c11b8
Create Date: 2026-10-27 11:59:40.018973

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "302ccfd153d6"
down_revision: str | Sequence[str] | None = "b5bf9c8c11b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema with translation cache and repo source language metadata."""
    op.create_table(
        "translation_cache",
        sa.Column("key", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("source_lang", sa.String(length=16), nullable=False),
        sa.Column("target_lang", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_translation_cache_created_at",
        "translation_cache",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_translation_cache_source_lang",
        "translation_cache",
        ["source_lang"],
        unique=False,
    )
    op.create_index(
        "ix_translation_cache_target_lang",
        "translation_cache",
        ["target_lang"],
        unique=False,
    )

    op.add_column("repos", sa.Column("source_language", sa.String(length=16), nullable=True))
    op.add_column("repos", sa.Column("source_language_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("repos", "source_language_confidence")
    op.drop_column("repos", "source_language")
    op.drop_index("ix_translation_cache_target_lang", table_name="translation_cache")
    op.drop_index("ix_translation_cache_source_lang", table_name="translation_cache")
    op.drop_index("ix_translation_cache_created_at", table_name="translation_cache")
    op.drop_table("translation_cache")
