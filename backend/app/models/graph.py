"""Repository dependency graph database model."""

from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Column, Field, SQLModel, UniqueConstraint

from app.models.user import utc_now
from app.parser.graph import PARSER_VERSION


class RepoGraph(SQLModel, table=True):
    """Stored dependency graph for a specific repository commit."""

    __tablename__ = "repo_graphs"
    __table_args__ = (
        UniqueConstraint("repo_id", "commit_sha", name="uq_repo_graphs_repo_id_commit_sha"),
    )

    id: int | None = Field(default=None, primary_key=True)
    repo_id: int = Field(foreign_key="repos.id", index=True)
    commit_sha: str = Field(index=True)
    parser_version: int = Field(default=PARSER_VERSION)
    graph_json: str = Field(sa_column=Column(sa.Text, nullable=False))
    node_count: int = Field(default=0)
    edge_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now)

    def is_valid(self, current_commit_sha: str | None) -> bool:
        """Check if graph matches current commit SHA and parser version."""
        return (
            self.parser_version == PARSER_VERSION
            and current_commit_sha is not None
            and self.commit_sha == current_commit_sha
        )
