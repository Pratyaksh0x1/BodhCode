"""Integration tests for proposal API endpoints:
accept, reject, edit, accept-all, reject-all, undo.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.crypto import encrypt_token
from app.files.service import compute_content_hash, read_effective
from app.github.limits import INGEST_VERSION
from app.models.proposals import Proposal
from app.models.repo import Repo
from app.models.user import User


@pytest.fixture
def auth_user(db_session: Session) -> User:
    user = User(
        github_id=99999,
        login="reviewer",
        avatar_url="https://avatar.test/reviewer",
        encrypted_github_token=encrypt_token("gho_test_token"),
        review_mode="review",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def other_user(db_session: Session) -> User:
    user = User(
        github_id=88888,
        login="otheruser",
        avatar_url="https://avatar.test/other",
        encrypted_github_token=encrypt_token("gho_other_token"),
        review_mode="review",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def repo_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "DATA_DIR", str(tmp_path))
    owner = "reviewer"
    name = "myproject"
    commit_sha = "aabbcc123"

    src_dir = tmp_path / "repos" / owner / name / commit_sha / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / ".ingest_version").write_bytes(str(INGEST_VERSION).encode("utf-8"))
    (src_dir / "file1.ts").write_bytes(b"export const a = 1;\n")
    (src_dir / "file2.ts").write_bytes(b"export const b = 2;\n")

    return tmp_path, commit_sha


@pytest.fixture
def user_repo(db_session: Session, auth_user: User, repo_env: tuple[Path, str]) -> Repo:
    _, commit_sha = repo_env
    repo = Repo(
        user_id=auth_user.id,
        owner="reviewer",
        name="myproject",
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


@pytest.fixture
def client_with_auth(client: TestClient, auth_user: User) -> TestClient:
    """Simulate authenticated session cookie for auth_user."""
    # Use session middleware to set user_id
    with client:
        # FastAPI TestClient session cookie simulation
        client.cookies.set("bodhcode_session", "dummy")
    return client


def _headers() -> dict[str, str]:
    return {"X-Requested-With": "bodhcode"}


def test_proposal_accept_reject_edit_cycle(
    client: TestClient,
    db_session: Session,
    auth_user: User,
    user_repo: Repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.auth.deps import get_current_user

    client.app.dependency_overrides[get_current_user] = lambda: auth_user

    try:
        # Create a pending edit proposal
        prop = Proposal(
            user_id=auth_user.id,
            repo_id=user_repo.id,
            kind="edit",
            path="file1.ts",
            old_content="export const a = 1;\n",
            new_content="export const a = 100;\n",
            base_hash=compute_content_hash("export const a = 1;\n"),
            rationale="Make a 100",
            status="pending",
        )
        db_session.add(prop)
        db_session.commit()
        db_session.refresh(prop)

        # 1. Edit proposal content (PUT)
        put_res = client.put(
            f"/proposals/{prop.id}",
            json={"new_content": "export const a = 999;\n"},
            headers=_headers(),
        )
        assert put_res.status_code == 200
        assert put_res.json()["new_content"] == "export const a = 999;\n"

        # 2. Accept proposal (POST)
        accept_res = client.post(f"/proposals/{prop.id}/accept", headers=_headers())
        assert accept_res.status_code == 200
        assert accept_res.json()["status"] == "applied"

        # Verify file in working copy has updated content
        eff = read_effective(auth_user, user_repo, "file1.ts", db_session)
        assert eff["content"] == "export const a = 999;\n"

        # 3. Undo proposal (POST)
        undo_res = client.post(f"/proposals/{prop.id}/undo", headers=_headers())
        assert undo_res.status_code == 200
        assert undo_res.json()["status"] == "undone"

        eff_after_undo = read_effective(auth_user, user_repo, "file1.ts", db_session)
        assert eff_after_undo["content"] == "export const a = 1;\n"

        # 4. Reject another proposal
        prop2 = Proposal(
            user_id=auth_user.id,
            repo_id=user_repo.id,
            kind="delete",
            path="file2.ts",
            old_content="export const b = 2;\n",
            base_hash=compute_content_hash("export const b = 2;\n"),
            rationale="Remove file2",
            status="pending",
        )
        db_session.add(prop2)
        db_session.commit()
        db_session.refresh(prop2)

        rej_res = client.post(f"/proposals/{prop2.id}/reject", headers=_headers())
        assert rej_res.status_code == 200
        assert rej_res.json()["status"] == "rejected"

    finally:
        client.app.dependency_overrides.clear()


def test_proposal_accept_all_skips_stale(
    client: TestClient,
    db_session: Session,
    auth_user: User,
    user_repo: Repo,
) -> None:
    from app.auth.deps import get_current_user

    client.app.dependency_overrides[get_current_user] = lambda: auth_user

    try:
        # Create prop 1 (valid)
        p1 = Proposal(
            user_id=auth_user.id,
            repo_id=user_repo.id,
            kind="create",
            path="file_new.ts",
            new_content="export const n = 10;\n",
            rationale="Add new",
            status="pending",
        )
        # Create prop 2 (stale base_hash)
        p2 = Proposal(
            user_id=auth_user.id,
            repo_id=user_repo.id,
            kind="edit",
            path="file1.ts",
            old_content="outdated content",
            new_content="updated content",
            base_hash="stale_hash_that_does_not_match",
            rationale="Stale edit",
            status="pending",
        )
        db_session.add(p1)
        db_session.add(p2)
        db_session.commit()

        res = client.post(
            "/proposals/accept-all",
            json={"repo_id": user_repo.id},
            headers=_headers(),
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data["results"]) == 2
        # p1 was applied
        assert data["results"][0]["id"] == p1.id
        assert data["results"][0]["status"] == "applied"
        # p2 was skipped as stale
        assert data["results"][1]["id"] == p2.id
        assert data["results"][1]["status"] == "skipped_stale"

    finally:
        client.app.dependency_overrides.clear()


def test_proposal_ownership_isolation(
    client: TestClient,
    db_session: Session,
    auth_user: User,
    other_user: User,
    user_repo: Repo,
) -> None:
    """A user cannot view, accept, reject, edit, or undo another user's proposal."""
    from app.auth.deps import get_current_user

    # Proposal belongs to auth_user
    p = Proposal(
        user_id=auth_user.id,
        repo_id=user_repo.id,
        kind="create",
        path="secret.ts",
        new_content="private",
        rationale="private",
        status="pending",
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)

    # other_user tries to accept it
    client.app.dependency_overrides[get_current_user] = lambda: other_user

    try:
        res = client.post(f"/proposals/{p.id}/accept", headers=_headers())
        assert res.status_code == 404
        assert "Proposal not found" in res.json()["detail"]
    finally:
        client.app.dependency_overrides.clear()
