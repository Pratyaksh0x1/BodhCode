"""add editor_theme to users

Revision ID: b5bf9c8c11b8
Revises: 975ea2254f30
Create Date: 2026-10-27 09:21:07.744422

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5bf9c8c11b8"
down_revision: str | Sequence[str] | None = "975ea2254f30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema by adding editor_theme column to users table."""
    op.add_column(
        "users",
        sa.Column("editor_theme", sa.String(), nullable=False, server_default="auto"),
    )


def downgrade() -> None:
    """Downgrade schema by dropping editor_theme column."""
    op.drop_column("users", "editor_theme")
