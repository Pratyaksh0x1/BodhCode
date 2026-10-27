"""User activity audit log endpoints."""

import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.auth.deps import get_current_user, require_csrf_header
from app.db import get_session
from app.models.push import ActionLog
from app.models.user import User

router = APIRouter(
    prefix="/user",
    tags=["User Activity"],
    dependencies=[Depends(require_csrf_header)],
)


class ActivityItem(BaseModel):
    id: int
    repo_id: int | None
    action: str
    status: str
    target_url: str | None
    created_at: datetime
    meta: dict[str, Any] = {}


@router.get("/activity", response_model=list[ActivityItem])
def get_user_activity(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ActivityItem]:
    """Retrieve audit history of outgoing actions performed by the current user.

    Ensures zero secret or token exposure.
    """
    statement = (
        select(ActionLog)
        .where(ActionLog.user_id == current_user.id)
        .order_by(col(ActionLog.created_at).desc())
        .limit(limit)
    )
    logs = session.exec(statement).all()

    items: list[ActivityItem] = []
    for log in logs:
        parsed_meta: dict[str, Any] = {}
        if log.meta:
            try:
                parsed_meta = json.loads(log.meta)
            except Exception:
                parsed_meta = {}

        items.append(
            ActivityItem(
                id=log.id or 0,
                repo_id=log.repo_id,
                action=log.action,
                status=log.status,
                target_url=log.target_url,
                created_at=log.created_at,
                meta=parsed_meta,
            )
        )

    return items
