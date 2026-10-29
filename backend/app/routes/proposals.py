"""FastAPI routes for proposal review, accept, reject, edit, and undo."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.ai.review import (
    InvalidProposalStateError,
    ProposalConflictError,
    StaleProposalError,
    apply_proposal,
    check_stale,
    undo_proposal,
)
from app.auth.deps import get_current_user, require_csrf_header
from app.db import get_session
from app.models.proposals import Proposal
from app.models.repo import Repo
from app.models.user import User, utc_now

router = APIRouter(tags=["Proposals"])


class EditProposalRequest(BaseModel):
    """Payload to modify proposed new content prior to accepting."""

    new_content: str = Field(description="Updated proposed content.")


class BatchProposalRequest(BaseModel):
    """Payload for accept-all and reject-all operations."""

    repo_id: int = Field(description="Target repository identifier.")


def _get_user_repo(repo_id: int, user: User, session: Session) -> Repo:
    """Verify repo ownership and fetch Repo."""
    stmt = select(Repo).where(Repo.id == repo_id, Repo.user_id == user.id)
    repo = session.exec(stmt).first()
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found",
        )
    return repo


def _get_user_proposal(proposal_id: int, user: User, session: Session) -> Proposal:
    """Verify proposal ownership and fetch Proposal."""
    stmt = select(Proposal).where(
        Proposal.id == proposal_id,
        Proposal.user_id == user.id,
    )
    proposal = session.exec(stmt).first()
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proposal not found",
        )
    return proposal


@router.get("/repos/{repo_id}/proposals")
def list_proposals(
    repo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[dict[str, Any]]:
    """List proposals for repository with ownership enforcement and staleness flags."""
    repo = _get_user_repo(repo_id, current_user, session)

    stmt = select(Proposal).where(
        Proposal.repo_id == repo.id,
        Proposal.user_id == current_user.id,
    )
    if status_filter:
        stmt = stmt.where(Proposal.status == status_filter)
    stmt = stmt.order_by(Proposal.created_at.asc())

    proposals = session.exec(stmt).all()
    results: list[dict[str, Any]] = []

    for p in proposals:
        is_stale = False
        if p.status == "pending":
            is_stale = check_stale(p, current_user, repo, session)
            if is_stale and p.status == "pending":
                p.status = "stale"
                session.add(p)
                session.commit()
                session.refresh(p)

        results.append(
            {
                "id": p.id,
                "user_id": p.user_id,
                "repo_id": p.repo_id,
                "session_id": p.session_id,
                "kind": p.kind,
                "path": p.path,
                "old_content": p.old_content,
                "new_content": p.new_content,
                "base_hash": p.base_hash,
                "rationale": p.rationale,
                "blast_radius_count": p.blast_radius_count,
                "status": p.status,
                "is_stale": is_stale or (p.status == "stale"),
                "created_at": p.created_at.isoformat(),
                "decided_at": p.decided_at.isoformat() if p.decided_at else None,
            }
        )

    return results


@router.post("/proposals/{proposal_id}/accept")
def accept_proposal(
    proposal_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_csrf_header)],
) -> dict[str, Any]:
    """Accept a pending proposal, write to working copy, and record a Checkpoint."""
    proposal = _get_user_proposal(proposal_id, current_user, session)
    repo = _get_user_repo(proposal.repo_id, current_user, session)

    try:
        apply_proposal(proposal, current_user, repo, session)
    except StaleProposalError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from None
    except InvalidProposalStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None

    return {
        "id": proposal.id,
        "path": proposal.path,
        "kind": proposal.kind,
        "status": proposal.status,
        "decided_at": proposal.decided_at.isoformat() if proposal.decided_at else None,
    }


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(
    proposal_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_csrf_header)],
) -> dict[str, Any]:
    """Reject a proposal."""
    proposal = _get_user_proposal(proposal_id, current_user, session)
    proposal.status = "rejected"
    proposal.decided_at = utc_now()
    session.add(proposal)
    session.commit()
    session.refresh(proposal)

    return {
        "id": proposal.id,
        "path": proposal.path,
        "kind": proposal.kind,
        "status": proposal.status,
        "decided_at": proposal.decided_at.isoformat() if proposal.decided_at else None,
    }


@router.put("/proposals/{proposal_id}")
def update_proposal_content(
    proposal_id: int,
    payload: EditProposalRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_csrf_header)],
) -> dict[str, Any]:
    """Allow user to edit proposed content prior to accepting."""
    proposal = _get_user_proposal(proposal_id, current_user, session)
    if proposal.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit proposal in '{proposal.status}' status.",
        )

    # Size & encoding validation
    if "\x00" in payload.new_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content cannot contain null bytes.",
        )
    content_bytes = payload.new_content.encode("utf-8")
    if len(content_bytes) > 1_000_000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Proposed content exceeds 1,000,000 bytes limit.",
        )

    proposal.new_content = payload.new_content
    session.add(proposal)
    session.commit()
    session.refresh(proposal)

    return {
        "id": proposal.id,
        "path": proposal.path,
        "kind": proposal.kind,
        "status": proposal.status,
        "new_content": proposal.new_content,
    }


@router.post("/proposals/accept-all")
def accept_all_proposals(
    payload: BatchProposalRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_csrf_header)],
) -> dict[str, Any]:
    """Accept all pending proposals for repository in creation order, skipping stale ones."""
    repo = _get_user_repo(payload.repo_id, current_user, session)

    stmt = (
        select(Proposal)
        .where(
            Proposal.repo_id == repo.id,
            Proposal.user_id == current_user.id,
            Proposal.status == "pending",
        )
        .order_by(Proposal.created_at.asc())
    )
    proposals = session.exec(stmt).all()

    results: list[dict[str, Any]] = []
    for p in proposals:
        if check_stale(p, current_user, repo, session):
            p.status = "stale"
            session.add(p)
            session.commit()
            results.append({"id": p.id, "path": p.path, "status": "skipped_stale"})
        else:
            try:
                apply_proposal(p, current_user, repo, session)
                results.append({"id": p.id, "path": p.path, "status": "applied"})
            except Exception as exc:
                results.append({"id": p.id, "path": p.path, "status": "error", "error": str(exc)})

    return {"results": results, "total_processed": len(results)}


@router.post("/proposals/reject-all")
def reject_all_proposals(
    payload: BatchProposalRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_csrf_header)],
) -> dict[str, Any]:
    """Reject all pending proposals for repository in creation order."""
    repo = _get_user_repo(payload.repo_id, current_user, session)

    stmt = (
        select(Proposal)
        .where(
            Proposal.repo_id == repo.id,
            Proposal.user_id == current_user.id,
            Proposal.status == "pending",
        )
        .order_by(Proposal.created_at.asc())
    )
    proposals = session.exec(stmt).all()

    results: list[dict[str, Any]] = []
    for p in proposals:
        p.status = "rejected"
        p.decided_at = utc_now()
        session.add(p)
        results.append({"id": p.id, "path": p.path, "status": "rejected"})

    session.commit()
    return {"results": results, "total_rejected": len(results)}


@router.post("/proposals/{proposal_id}/undo")
def undo_applied_proposal(
    proposal_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_csrf_header)],
) -> dict[str, Any]:
    """Undo an applied proposal, restoring previous state from Checkpoint."""
    proposal = _get_user_proposal(proposal_id, current_user, session)
    repo = _get_user_repo(proposal.repo_id, current_user, session)

    try:
        undo_proposal(proposal, current_user, repo, session)
    except ProposalConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from None
    except InvalidProposalStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None

    return {
        "id": proposal.id,
        "path": proposal.path,
        "kind": proposal.kind,
        "status": proposal.status,
        "decided_at": proposal.decided_at.isoformat() if proposal.decided_at else None,
    }
