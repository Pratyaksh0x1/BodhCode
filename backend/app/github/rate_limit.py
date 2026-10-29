"""Rate limiting based on persistent ActionLog history."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlmodel import Session, col, select

from app.models.push import ActionLog

MAX_PUSHES_PER_HOUR = 5
MAX_ISSUES_COMMENTS_PER_HOUR = 20


def check_push_rate_limit(user_id: int, session: Session) -> None:
    """Ensure user does not exceed 5 successful pushes per hour."""
    now = datetime.now(UTC)
    one_hour_ago = now - timedelta(hours=1)

    statement = (
        select(ActionLog)
        .where(
            ActionLog.user_id == user_id,
            ActionLog.action == "push",
            ActionLog.status == "succeeded",
            ActionLog.created_at >= one_hour_ago,
        )
        .order_by(col(ActionLog.created_at).asc())
    )
    logs = session.exec(statement).all()

    if len(logs) >= MAX_PUSHES_PER_HOUR:
        oldest = logs[0]
        # Calculate seconds until oldest action falls outside the 1-hour window
        wait_seconds = max(1, int((oldest.created_at + timedelta(hours=1) - now).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: maximum {MAX_PUSHES_PER_HOUR} pushes per hour.",
            headers={"Retry-After": str(wait_seconds)},
        )


def check_issue_comment_rate_limit(user_id: int, session: Session) -> None:
    """Ensure user does not exceed 20 issue/comment creations per hour."""
    now = datetime.now(UTC)
    one_hour_ago = now - timedelta(hours=1)

    statement = (
        select(ActionLog)
        .where(
            ActionLog.user_id == user_id,
            col(ActionLog.action).in_(["issue_create", "comment_create"]),
            ActionLog.status == "succeeded",
            ActionLog.created_at >= one_hour_ago,
        )
        .order_by(col(ActionLog.created_at).asc())
    )
    logs = session.exec(statement).all()

    if len(logs) >= MAX_ISSUES_COMMENTS_PER_HOUR:
        oldest = logs[0]
        wait_seconds = max(1, int((oldest.created_at + timedelta(hours=1) - now).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit exceeded: maximum {MAX_ISSUES_COMMENTS_PER_HOUR} issues "
                "and comments per hour."
            ),
            headers={"Retry-After": str(wait_seconds)},
        )
