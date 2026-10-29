"""Pure review policy decisions, proposal application, stale checking, and undo."""

from __future__ import annotations

import json
from typing import Any, Literal

from sqlmodel import Session, select

from app.files.errors import FileNotFound
from app.files.service import (
    compute_content_hash,
    delete_file,
    read_effective,
    write_file,
)
from app.models.files import WorkingFile
from app.models.proposals import Checkpoint, Proposal
from app.models.repo import Repo
from app.models.user import User, utc_now

ReviewMode = Literal["review", "auto", "readonly"]
ReviewDecision = Literal["queue", "apply", "block"]


class StaleProposalError(Exception):
    """Raised when attempting to apply a proposal whose base_hash does not match."""


class InvalidProposalStateError(Exception):
    """Raised when attempting to act on a proposal in an incompatible status."""


class ProposalConflictError(Exception):
    """Raised when undo is refused because file was changed after proposal apply."""


def decide(mode: str, kind: str) -> ReviewDecision:
    """Decide whether a write tool action should queue for human review, apply, or block.

    Rules:
    - review -> always "queue"
    - auto -> "apply" for create and edit; "queue" for delete (delete always asks)
    - readonly -> "block" (write tools return error telling model to describe plan)
    """
    clean_mode = mode.lower().strip() if isinstance(mode, str) else "review"
    clean_kind = kind.lower().strip() if isinstance(kind, str) else "edit"

    if clean_mode == "readonly":
        return "block"

    if clean_mode == "auto":
        if clean_kind in ("create", "edit"):
            return "apply"
        if clean_kind == "delete":
            return "queue"

    # Default and "review" mode
    return "queue"


def check_stale(
    proposal: Proposal,
    user: User,
    repo: Repo,
    session: Session,
) -> bool:
    """Return True if the proposal's base_hash no longer matches the effective content."""
    if proposal.kind == "create":
        try:
            # If the file now exists, proposal to create it is stale
            read_effective(user, repo, proposal.path, session)
            return True
        except FileNotFound:
            return False

    # edit or delete
    try:
        eff = read_effective(user, repo, proposal.path, session)
        current_hash = eff["hash"]
        if proposal.base_hash is None:
            return True
        return current_hash != proposal.base_hash
    except FileNotFound:
        # File was deleted since proposal was generated
        return True


def apply_proposal(
    proposal: Proposal,
    user: User,
    repo: Repo,
    session: Session,
) -> Checkpoint:
    """Apply a proposal to the user's working copy with a reversible Checkpoint."""
    if proposal.status != "pending":
        raise InvalidProposalStateError(
            f"Cannot apply proposal #{proposal.id} in status '{proposal.status}'."
        )

    # 1. Stale check
    if check_stale(proposal, user, repo, session):
        proposal.status = "stale"
        session.add(proposal)
        session.commit()
        session.refresh(proposal)
        raise StaleProposalError(
            f"Proposal #{proposal.id} on '{proposal.path}' is stale: file has changed."
        )

    # 2. Record checkpoint
    working_stmt = select(WorkingFile).where(
        WorkingFile.user_id == user.id,
        WorkingFile.repo_id == repo.id,
        WorkingFile.path == proposal.path,
    )
    working_row = session.exec(working_stmt).first()

    if working_row is not None:
        prev_data: dict[str, Any] = {
            "existed": True,
            "content": working_row.content,
            "is_new": working_row.is_new,
            "is_deleted": working_row.is_deleted,
            "base_hash": working_row.base_hash,
        }
    else:
        prev_data = {"existed": False}

    checkpoint = Checkpoint(
        proposal_id=proposal.id,  # type: ignore
        previous=json.dumps(prev_data),
        created_at=utc_now(),
    )
    session.add(checkpoint)
    session.flush()

    # 3. Apply change through WorkingFileService
    if proposal.kind in ("create", "edit"):
        content_to_write = proposal.new_content if proposal.new_content is not None else ""
        write_file(user, repo, proposal.path, content_to_write, session)
    elif proposal.kind == "delete":
        delete_file(user, repo, proposal.path, session)

    # 4. Mark applied
    proposal.status = "applied"
    proposal.decided_at = utc_now()
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    return checkpoint


def undo_proposal(
    proposal: Proposal,
    user: User,
    repo: Repo,
    session: Session,
) -> None:
    """Undo an applied proposal, restoring exact state from Checkpoint."""
    if proposal.status != "applied":
        raise InvalidProposalStateError(
            f"Cannot undo proposal #{proposal.id} in status '{proposal.status}'. Must be 'applied'."
        )

    # Find checkpoint
    cp_stmt = select(Checkpoint).where(Checkpoint.proposal_id == proposal.id)
    checkpoint = session.exec(cp_stmt).first()
    if checkpoint is None:
        raise InvalidProposalStateError(f"No checkpoint found for proposal #{proposal.id}.")

    # Hash check: has the file changed since this proposal was applied?
    if proposal.kind in ("create", "edit"):
        expected_hash = compute_content_hash(proposal.new_content or "")
        try:
            curr = read_effective(user, repo, proposal.path, session)
            if curr["hash"] != expected_hash:
                raise ProposalConflictError(
                    f"Cannot undo: file '{proposal.path}' was modified "
                    "after this change was applied."
                )
        except FileNotFound as err:
            raise ProposalConflictError(
                f"Cannot undo: file '{proposal.path}' was deleted after this change was applied."
            ) from err
    elif proposal.kind == "delete":
        # Ensure file has not been recreated
        try:
            read_effective(user, repo, proposal.path, session)
            raise ProposalConflictError(
                f"Cannot undo: file '{proposal.path}' was recreated after it was deleted."
            )
        except FileNotFound:
            pass

    # Restore prior working state
    prev = json.loads(checkpoint.previous)
    working_stmt = select(WorkingFile).where(
        WorkingFile.user_id == user.id,
        WorkingFile.repo_id == repo.id,
        WorkingFile.path == proposal.path,
    )
    working_row = session.exec(working_stmt).first()

    if prev.get("existed", False):
        if working_row is None:
            working_row = WorkingFile(
                user_id=user.id,
                repo_id=repo.id,
                path=proposal.path,
                content=prev.get("content", ""),
                is_new=bool(prev.get("is_new", False)),
                is_deleted=bool(prev.get("is_deleted", False)),
                base_hash=prev.get("base_hash"),
                updated_at=utc_now(),
            )
            session.add(working_row)
        else:
            working_row.content = prev.get("content", "")
            working_row.is_new = bool(prev.get("is_new", False))
            working_row.is_deleted = bool(prev.get("is_deleted", False))
            working_row.base_hash = prev.get("base_hash")
            working_row.updated_at = utc_now()
            session.add(working_row)
    else:
        # File had no working copy row prior to applying proposal
        if working_row is not None:
            session.delete(working_row)

    proposal.status = "undone"
    proposal.decided_at = utc_now()
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
