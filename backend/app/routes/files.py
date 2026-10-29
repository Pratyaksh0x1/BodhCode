"""FastAPI routes for working file operations and the code editor workspace."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.auth.deps import get_current_user, require_csrf_header
from app.db import get_session
from app.files.errors import (
    BinaryFileNotSupported,
    FileNotFound,
    FileTooLarge,
    InvalidPath,
    PreconditionFailed,
    RepoFilesUnavailable,
)
from app.files.service import (
    delete_file,
    diff_for,
    get_changes,
    list_tree,
    read_effective,
    rename_file,
    revert_file,
    write_file,
)
from app.models.graph import RepoGraph
from app.models.repo import Repo
from app.models.user import User

router = APIRouter(prefix="/repos", tags=["Files & Editor"])


class WriteFileRequest(BaseModel):
    """Payload to write or create a working file."""

    content: str = Field(description="New or updated text content for the working file.")


class RenameFileRequest(BaseModel):
    """Payload to rename a working file."""

    new_path: str = Field(description="Destination path for the renamed file.")


def _get_user_repo(repo_id: int, user: User, session: Session) -> Repo:
    """Verify repo ownership and fetch Repo instance."""
    statement = select(Repo).where(
        Repo.id == repo_id,
        Repo.user_id == user.id,
    )
    repo = session.exec(statement).first()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )
    return repo


@router.get("/{repo_id}/files")
def get_repo_files(
    repo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """List effective file tree with status annotations and graph membership."""
    repo = _get_user_repo(repo_id, current_user, session)

    try:
        tree = list_tree(current_user, repo, session)
    except RepoFilesUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # Check for graph nodes to mark graph_node flag
    graph_stmt = select(RepoGraph).where(RepoGraph.repo_id == repo.id)
    repo_graph = session.exec(graph_stmt).first()
    graph_nodes: set[str] = set()
    if repo_graph is not None and repo_graph.graph_json:
        try:
            graph_data = json.loads(repo_graph.graph_json)
            graph_nodes = {node["id"] for node in graph_data.get("nodes", []) if "id" in node}
        except (json.JSONDecodeError, KeyError):
            graph_nodes = set()

    for item in tree:
        item["graph_node"] = item["path"] in graph_nodes

    return {"files": tree, "count": len(tree)}


@router.get("/{repo_id}/files/{file_path:path}")
def get_file_content(
    repo_id: int,
    file_path: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Read effective file content (working copy if modified/new, else original)."""
    repo = _get_user_repo(repo_id, current_user, session)

    try:
        return read_effective(current_user, repo, file_path, session)
    except InvalidPath as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FileTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except BinaryFileNotSupported as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except RepoFilesUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/{repo_id}/files/{file_path:path}", dependencies=[Depends(require_csrf_header)])
def put_file_content(
    repo_id: int,
    file_path: str,
    body: WriteFileRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> dict[str, Any]:
    """Save changes to user's working copy with optional concurrency guard."""
    repo = _get_user_repo(repo_id, current_user, session)
    clean_if_match = if_match.strip('"') if if_match else None

    try:
        return write_file(
            current_user,
            repo,
            file_path,
            body.content,
            session,
            if_match=clean_if_match,
        )
    except PreconditionFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail=str(exc),
        ) from exc
    except InvalidPath as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except BinaryFileNotSupported as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except RepoFilesUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{repo_id}/files/{file_path:path}", dependencies=[Depends(require_csrf_header)])
def delete_repo_file(
    repo_id: int,
    file_path: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Delete file from user's working copy."""
    repo = _get_user_repo(repo_id, current_user, session)

    try:
        new_status = delete_file(current_user, repo, file_path, session)
        return {"path": file_path, "status": new_status}
    except InvalidPath as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{repo_id}/files/{file_path:path}/revert",
    dependencies=[Depends(require_csrf_header)],
)
def revert_repo_file(
    repo_id: int,
    file_path: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Revert working copy edits on file, restoring original repository content."""
    repo = _get_user_repo(repo_id, current_user, session)

    try:
        reverted = revert_file(current_user, repo, file_path, session)
        return {"path": file_path, "reverted": reverted}
    except InvalidPath as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{repo_id}/changes")
def get_repo_changes(
    repo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Get all modified, added, or deleted files in user's working copy."""
    repo = _get_user_repo(repo_id, current_user, session)
    changes = get_changes(current_user, repo, session)
    return {"changes": changes, "count": len(changes)}


@router.get("/{repo_id}/diff/{file_path:path}")
def get_file_diff(
    repo_id: int,
    file_path: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Get original and modified content for diff comparison."""
    repo = _get_user_repo(repo_id, current_user, session)

    try:
        return diff_for(current_user, repo, file_path, session)
    except InvalidPath as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/{repo_id}/files/{file_path:path}/rename",
    dependencies=[Depends(require_csrf_header)],
)
def rename_repo_file(
    repo_id: int,
    file_path: str,
    body: RenameFileRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Rename file in working copy (implemented as delete + add)."""
    repo = _get_user_repo(repo_id, current_user, session)

    try:
        rename_file(current_user, repo, file_path, body.new_path, session)
        return {
            "old_path": file_path,
            "new_path": body.new_path,
            "status": "renamed",
        }
    except InvalidPath as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
