"""add_openai_config_to_users

Revision ID: a3bf8e52f412
Revises: 653f67f50a2f
Create Date: 2026-10-29 18:56:12.021784

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3bf8e52f412'
down_revision: str | Sequence[str] | None = '653f67f50a2f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema by adding openai/chatgpt configuration columns to users table."""
    op.add_column(
        "users",
        sa.Column("encrypted_openai_key", sa.String(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("openai_model", sa.String(), nullable=False, server_default="gpt-4o"),
    )
    op.add_column(
        "users",
        sa.Column("auth_provider", sa.String(), nullable=False, server_default="github"),
    )


def downgrade() -> None:
    """Downgrade schema by dropping openai/chatgpt configuration columns."""
    op.drop_column("users", "auth_provider")
    op.drop_column("users", "openai_model")
    op.drop_column("users", "encrypted_openai_key")
