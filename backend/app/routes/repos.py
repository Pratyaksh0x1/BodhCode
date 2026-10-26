"""Repository management and ingestion API endpoints."""

from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Response,
    status,
)
from sqlmodel import Session, select

from app.auth.deps import get_current_user, require_csrf_header
from app.db import get_session
from app.github.ingest import ingest_repo
from app.github.urls import InvalidRepoUrl, parse_repo_url
from app.models.repo import Repo, RepoCreate, RepoRead
from app.models.user import User, utc_now

router = APIRouter(
    prefix="/repos",
    tags=["Repositories"],
    dependencies=[Depends(require_csrf_header)],
)


@router.post("", response_model=RepoRead, status_code=status.HTTP_202_ACCEPTED)
async def create_repo(
    payload: RepoCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    background_tasks: BackgroundTasks,
) -> Repo:
    """Register repository URL and launch asynchronous background ingestion."""
    try:
        ref = parse_repo_url(payload.url)
    except InvalidRepoUrl as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err

    statement = select(Repo).where(
        Repo.user_id == current_user.id,
        Repo.owner == ref.owner,
        Repo.name == ref.name,
    )
    repo = session.exec(statement).first()

    now = utc_now()
    if repo is not None:
        repo.status = "queued"
        repo.branch = ref.ref or repo.branch or "main"
        repo.error_code = None
        repo.error_message = None
        repo.updated_at = now
    else:
        repo = Repo(
            user_id=current_user.id,  # type: ignore[arg-type]
            owner=ref.owner,
            name=ref.name,
            branch=ref.ref or "main",
            status="queued",
            created_at=now,
            updated_at=now,
        )
        session.add(repo)

    session.commit()
    session.refresh(repo)

    background_tasks.add_task(ingest_repo, repo.id)  # type: ignore[arg-type]
    return repo


@router.get("", response_model=list[RepoRead])
def list_repos(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[Repo]:
    """List all repositories registered by current user, ordered newest first."""
    statement = (
        select(Repo).where(Repo.user_id == current_user.id).order_by(Repo.updated_at.desc())  # type: ignore[arg-type]
    )
    return list(session.exec(statement).all())


@router.get("/{repo_id}", response_model=RepoRead)
def get_repo(
    repo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Repo:
    """Retrieve details for a single repository owned by current user."""
    statement = select(Repo).where(
        Repo.id == repo_id,
        Repo.user_id == current_user.id,
    )
    repo = session.exec(statement).first()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )
    return repo


@router.post("/{repo_id}/refresh", response_model=RepoRead)
def refresh_repo(
    repo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    background_tasks: BackgroundTasks,
) -> Repo:
    """Trigger re-ingestion of the repository head."""
    statement = select(Repo).where(
        Repo.id == repo_id,
        Repo.user_id == current_user.id,
    )
    repo = session.exec(statement).first()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    repo.status = "queued"
    repo.error_code = None
    repo.error_message = None
    repo.updated_at = utc_now()
    session.add(repo)
    session.commit()
    session.refresh(repo)

    background_tasks.add_task(ingest_repo, repo.id)  # type: ignore[arg-type]
    return repo


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repo(
    repo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Delete repository record for current user."""
    statement = select(Repo).where(
        Repo.id == repo_id,
        Repo.user_id == current_user.id,
    )
    repo = session.exec(statement).first()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    session.delete(repo)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
