"""add_grok_config_to_users

Revision ID: 653f67f50a2f
Revises: a5294b96c51d
Create Date: 2026-10-29 15:38:54.574725

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "653f67f50a2f"
down_revision: str | Sequence[str] | None = "a5294b96c51d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema by adding grok configuration columns to users table."""
    op.add_column(
        "users",
        sa.Column("encrypted_grok_key", sa.String(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("grok_model", sa.String(), nullable=False, server_default="gpt-oss-120b"),
    )


def downgrade() -> None:
    """Downgrade schema by dropping grok configuration columns."""
    op.drop_column("users", "grok_model")
    op.drop_column("users", "encrypted_grok_key")
