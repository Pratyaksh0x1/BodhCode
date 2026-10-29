"""Unit tests for review policy: decide truth table, proposal apply, stale detection, and undo."""

import json
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.ai.review import (
    ProposalConflictError,
    StaleProposalError,
    apply_proposal,
    check_stale,
    decide,
    undo_proposal,
)
from app.files.service import compute_content_hash, read_effective, write_file
from app.models.files import WorkingFile
from app.models.proposals import Proposal
from app.models.repo import Repo
from app.models.user import User


def test_review_policy_truth_table() -> None:
    """Verify decision matrix for all combinations of review mode and tool kind."""
    # Review mode -> always queues
    assert decide("review", "create") == "queue"
    assert decide("review", "edit") == "queue"
    assert decide("review", "delete") == "queue"

    # Auto mode -> applies create and edit, but queues delete
    assert decide("auto", "create") == "apply"
    assert decide("auto", "edit") == "apply"
    assert decide("auto", "delete") == "queue"  # Delete always requires review!

    # Readonly mode -> blocks every write tool
    assert decide("readonly", "create") == "block"
    assert decide("readonly", "edit") == "block"
    assert decide("readonly", "delete") == "block"

    # Default / fallback is review behavior
    assert decide("unknown", "edit") == "queue"


@pytest.fixture
def test_user(db_session: Session) -> User:
    user = User(
        github_id=12345,
        login="testdev",
        name="Test Developer",
        avatar_url="https://avatar.test/dev",
        encrypted_github_token="fake_token",
        review_mode="review",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_repo_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    from app.config import get_settings
    from app.github.limits import INGEST_VERSION

    monkeypatch.setattr(get_settings(), "DATA_DIR", str(tmp_path))
    owner = "testdev"
    name = "testrepo"
    commit_sha = "c0ffee123456"

    src_dir = tmp_path / "repos" / owner / name / commit_sha / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / ".ingest_version").write_bytes(str(INGEST_VERSION).encode("utf-8"))
    (src_dir / "existing.ts").write_bytes(b"export const original = true;\n")

    return tmp_path, commit_sha


@pytest.fixture
def test_repo(db_session: Session, test_user: User, test_repo_env: tuple[Path, str]) -> Repo:
    _, commit_sha = test_repo_env
    repo = Repo(
        user_id=test_user.id,
        owner="testdev",
        name="testrepo",
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


def test_apply_and_undo_create_proposal(
    db_session: Session,
    test_user: User,
    test_repo: Repo,
) -> None:
    """Test applying a create proposal, checkpointing, and cleanly undoing it."""
    path = "src/new_module.ts"
    content = "export const meaning = 42;\n"

    proposal = Proposal(
        user_id=test_user.id,
        repo_id=test_repo.id,
        kind="create",
        path=path,
        new_content=content,
        rationale="Add new module",
        status="pending",
    )
    db_session.add(proposal)
    db_session.commit()
    db_session.refresh(proposal)

    # 1. Apply proposal
    cp = apply_proposal(proposal, test_user, test_repo, db_session)
    assert proposal.status == "applied"
    assert cp.proposal_id == proposal.id
    cp_data = json.loads(cp.previous)
    assert cp_data["existed"] is False

    # Effective content now exists
    eff = read_effective(test_user, test_repo, path, db_session)
    assert eff["content"] == content
    assert eff["status"] == "added"

    # 2. Undo proposal
    undo_proposal(proposal, test_user, test_repo, db_session)
    assert proposal.status == "undone"

    # File should no longer exist in working copy
    working_row = db_session.exec(
        select(WorkingFile).where(
            WorkingFile.user_id == test_user.id,
            WorkingFile.repo_id == test_repo.id,
            WorkingFile.path == path,
        )
    ).first()
    assert working_row is None


def test_apply_and_undo_edit_proposal(
    db_session: Session,
    test_user: User,
    test_repo: Repo,
) -> None:
    """Test applying an edit proposal over an existing working file and undoing it."""
    path = "src/config.ts"
    orig_content = "export const TIMEOUT = 5000;\n"
    new_content = "export const TIMEOUT = 10000;\n"

    # Initialize file in working copy
    write_file(test_user, test_repo, path, orig_content, db_session)
    base_hash = compute_content_hash(orig_content)

    proposal = Proposal(
        user_id=test_user.id,
        repo_id=test_repo.id,
        kind="edit",
        path=path,
        old_content=orig_content,
        new_content=new_content,
        base_hash=base_hash,
        rationale="Double timeout",
        status="pending",
    )
    db_session.add(proposal)
    db_session.commit()
    db_session.refresh(proposal)

    # Apply
    apply_proposal(proposal, test_user, test_repo, db_session)
    assert proposal.status == "applied"

    eff_applied = read_effective(test_user, test_repo, path, db_session)
    assert eff_applied["content"] == new_content

    # Undo
    undo_proposal(proposal, test_user, test_repo, db_session)
    assert proposal.status == "undone"

    eff_restored = read_effective(test_user, test_repo, path, db_session)
    assert eff_restored["content"] == orig_content


def test_stale_detection(
    db_session: Session,
    test_user: User,
    test_repo: Repo,
) -> None:
    """A proposal becomes stale if the effective file changes before acceptance."""
    path = "src/counter.ts"
    write_file(test_user, test_repo, path, "let count = 0;\n", db_session)

    proposal = Proposal(
        user_id=test_user.id,
        repo_id=test_repo.id,
        kind="edit",
        path=path,
        old_content="let count = 0;\n",
        new_content="let count = 1;\n",
        base_hash=compute_content_hash("let count = 0;\n"),
        rationale="Increment count",
        status="pending",
    )
    db_session.add(proposal)
    db_session.commit()
    db_session.refresh(proposal)

    assert not check_stale(proposal, test_user, test_repo, db_session)

    # Modify file externally/manually before accepting proposal
    write_file(test_user, test_repo, path, "let count = 99;\n", db_session)

    assert check_stale(proposal, test_user, test_repo, db_session)

    # Attempting to apply raises StaleProposalError and marks proposal stale
    with pytest.raises(StaleProposalError):
        apply_proposal(proposal, test_user, test_repo, db_session)

    assert proposal.status == "stale"


def test_undo_refused_after_later_modification(
    db_session: Session,
    test_user: User,
    test_repo: Repo,
) -> None:
    """Undo is refused (409) if the file changed after apply."""
    path = "src/app.ts"
    write_file(test_user, test_repo, path, "v1", db_session)

    proposal = Proposal(
        user_id=test_user.id,
        repo_id=test_repo.id,
        kind="edit",
        path=path,
        old_content="v1",
        new_content="v2",
        base_hash=compute_content_hash("v1"),
        rationale="Update to v2",
        status="pending",
    )
    db_session.add(proposal)
    db_session.commit()
    db_session.refresh(proposal)

    apply_proposal(proposal, test_user, test_repo, db_session)
    assert proposal.status == "applied"

    # User manually edits file after proposal was applied
    write_file(test_user, test_repo, path, "v3_user_edit", db_session)

    with pytest.raises(ProposalConflictError) as exc_info:
        undo_proposal(proposal, test_user, test_repo, db_session)

    assert "modified after this change was applied" in str(exc_info.value)
    assert proposal.status == "applied"  # Stays applied, not undone
