from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlmodel import Session, select

from app.auth.deps import get_current_user, require_csrf_header
from app.db import get_session
from app.github.ingest import ingest_repo
from app.github.urls import InvalidRepoUrl, parse_repo_url
from app.models.graph import RepoGraph
from app.models.repo import Repo, RepoCreate, RepoRead
from app.models.user import User, utc_now
from app.parser.blast import (
    blast_radius,
    dependencies,
    dependents,
    find_cycles,
)
from app.parser.graph import PARSER_VERSION
from app.rate_limiter import rate_limit_repo_ingest
from app.routes.graph_cache import get_cached_digraph
from app.services.analyze import analyze_repo

router = APIRouter(
    prefix="/repos",
    tags=["Repositories"],
    dependencies=[Depends(require_csrf_header)],
)


@router.post(
    "",
    response_model=RepoRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit_repo_ingest)],
)
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


@router.post(
    "/{repo_id}/refresh",
    response_model=RepoRead,
    dependencies=[Depends(rate_limit_repo_ingest)],
)
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


def _validate_file_path(file: str) -> None:
    """Ensure file path is normalized, non-empty, and free of traversal indicators."""
    if not file or ".." in file or "\\" in file or file.startswith("/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path: path traversal and backslashes are forbidden",
        )


def _get_repo_and_valid_graph(
    repo_id: int,
    user_id: int,
    session: Session,
) -> tuple[Repo, RepoGraph]:
    """Retrieve user-owned repo and ensure valid RepoGraph exists; raise 404 or 409."""
    statement = select(Repo).where(
        Repo.id == repo_id,
        Repo.user_id == user_id,
    )
    repo = session.exec(statement).first()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )

    if repo.commit_sha is None or repo.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="not_ready",
        )

    graph_statement = select(RepoGraph).where(
        RepoGraph.repo_id == repo.id,
        RepoGraph.commit_sha == repo.commit_sha,
        RepoGraph.parser_version == PARSER_VERSION,
    )
    graph_record = session.exec(graph_statement).first()
    if graph_record is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="not_ready",
        )

    return repo, graph_record


@router.post("/{repo_id}/analyze", response_model=RepoRead)
def analyze_repo_endpoint(
    repo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    background_tasks: BackgroundTasks,
) -> Repo:
    """Launch asynchronous repository dependency analysis."""
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

    if repo.status not in ("fetched", "ready", "failed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository cannot be analyzed while in status '{repo.status}'",
        )

    if repo.commit_sha is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Repository must be fetched before analysis can start",
        )

    repo.status = "analyzing"
    repo.error_code = None
    repo.error_message = None
    repo.updated_at = utc_now()
    session.add(repo)
    session.commit()
    session.refresh(repo)

    background_tasks.add_task(analyze_repo, repo.id)  # type: ignore[arg-type]
    return repo


@router.get("/{repo_id}/graph")
def get_repo_graph(
    repo_id: int,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Retrieve canonical dependency graph JSON with ETag / 304 caching."""
    repo, graph_record = _get_repo_and_valid_graph(repo_id, current_user.id, session)

    etag = f'"{repo.commit_sha}_{PARSER_VERSION}"'
    headers = {
        "ETag": etag,
        "Cache-Control": "private, max-age=0, must-revalidate",
    }

    if_none_match = request.headers.get("if-none-match")
    if if_none_match:
        client_tag = if_none_match.strip()
        if client_tag == "*" or client_tag == etag or client_tag == etag.strip('"'):
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    return Response(
        content=graph_record.graph_json,
        media_type="application/json",
        headers=headers,
    )


@router.get("/{repo_id}/blast")
def get_repo_blast(
    repo_id: int,
    file: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    include_type_only: bool = True,
    max_depth: int | None = None,
) -> dict[str, Any]:
    """Calculate transitive blast radius impacts for a file."""
    _validate_file_path(file)
    _, graph_record = _get_repo_and_valid_graph(repo_id, current_user.id, session)

    g = get_cached_digraph(graph_record)
    if file not in g:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="file_not_in_graph",
        )

    impacts = blast_radius(
        g,
        file,
        include_type_only=include_type_only,
        max_depth=max_depth,
    )
    return {
        "file": file,
        "total": len(impacts),
        "impacts": impacts,
    }


@router.get("/{repo_id}/deps")
def get_repo_deps(
    repo_id: int,
    file: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    depth: int = 1,
) -> dict[str, Any]:
    """Retrieve forward dependencies and direct dependents for a file."""
    _validate_file_path(file)
    _, graph_record = _get_repo_and_valid_graph(repo_id, current_user.id, session)

    g = get_cached_digraph(graph_record)
    if file not in g:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="file_not_in_graph",
        )

    return {
        "file": file,
        "dependencies": dependencies(g, file, depth=depth),
        "dependents": dependents(g, file),
    }


@router.get("/{repo_id}/cycles")
def get_repo_cycles(
    repo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[list[str]]:
    """Retrieve strongly connected components / cycles in the repository dependency graph."""
    _, graph_record = _get_repo_and_valid_graph(repo_id, current_user.id, session)
    g = get_cached_digraph(graph_record)
    return find_cycles(g)
