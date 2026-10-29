"""Tests for POST /auth/disconnect ("Delete my data").

Verifies that calling disconnect removes all of the user's data
(tokens, repo links, working files, proposals, checkpoints, previews, action logs, user row),
leaves other users completely untouched, clears the session, and subsequent calls return 401.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.auth.crypto import encrypt_token
from app.auth.deps import get_current_user
from app.db import get_session
from app.main import create_app
from app.models.files import WorkingFile
from app.models.graph import RepoGraph
from app.models.proposals import Checkpoint, Proposal
from app.models.push import ActionLog, PushPreview
from app.models.repo import Repo
from app.models.user import User


@pytest.fixture(name="db_session")
def db_session_fixture() -> Generator[Session, None, None]:
    """Provide an isolated in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(db_session: Session) -> Generator[TestClient, None, None]:
    """Provide a TestClient with overridden database session."""
    app = create_app()

    def _get_session_override() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_session] = _get_session_override
    with TestClient(app, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()


def test_disconnect_requires_csrf(client: TestClient, db_session: Session) -> None:
    """POST /auth/disconnect without X-Requested-With header must fail with 403."""
    user = User(
        github_id=101,
        login="testuser1",
        avatar_url="https://example.com/avatar1.png",
        encrypted_github_token=encrypt_token("ghp_testtoken1"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    app = client.app
    app.dependency_overrides[get_current_user] = lambda: user

    response = client.post("/auth/disconnect")
    assert response.status_code == 403
    assert "CSRF" in response.json().get("detail", "")


def test_disconnect_requires_auth(client: TestClient) -> None:
    """POST /auth/disconnect without active user session must return 401."""
    response = client.post("/auth/disconnect", headers={"X-Requested-With": "bodhcode"})
    assert response.status_code == 401


def test_disconnect_deletes_all_user_data_and_preserves_others(
    client: TestClient, db_session: Session
) -> None:
    """POST /auth/disconnect deletes User A's data, leaves User B untouched, clears session."""
    # 1. Create User A and User B
    user_a = User(
        github_id=1,
        login="usera",
        avatar_url="https://example.com/a.png",
        encrypted_github_token=encrypt_token("ghp_token_a"),
    )
    user_b = User(
        github_id=2,
        login="userb",
        avatar_url="https://example.com/b.png",
        encrypted_github_token=encrypt_token("ghp_token_b"),
    )
    db_session.add(user_a)
    db_session.add(user_b)
    db_session.commit()
    db_session.refresh(user_a)
    db_session.refresh(user_b)

    # 2. Populate User A data
    repo_a = Repo(user_id=user_a.id, owner="usera", name="repo-a", branch="main")
    db_session.add(repo_a)
    db_session.commit()
    db_session.refresh(repo_a)

    graph_a = RepoGraph(
        repo_id=repo_a.id,
        commit_sha="shaaa111",
        graph_json="{}",
    )
    wf_a = WorkingFile(
        user_id=user_a.id,
        repo_id=repo_a.id,
        path="src/index.ts",
        content="console.log('a');",
    )
    prop_a = Proposal(
        user_id=user_a.id,
        repo_id=repo_a.id,
        kind="edit",
        path="src/index.ts",
        rationale="Update index",
    )
    db_session.add(graph_a)
    db_session.add(wf_a)
    db_session.add(prop_a)
    db_session.commit()
    db_session.refresh(prop_a)

    cp_a = Checkpoint(
        proposal_id=prop_a.id,
        previous=json.dumps({"content": "old"}),
    )
    prev_a = PushPreview(
        user_id=user_a.id,
        repo_id=repo_a.id,
        kind="push",
        payload="{}",
        payload_hash="hash_a",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    log_a = ActionLog(
        user_id=user_a.id,
        repo_id=repo_a.id,
        action="push",
        status="succeeded",
    )
    db_session.add(cp_a)
    db_session.add(prev_a)
    db_session.add(log_a)

    # 3. Populate User B data
    repo_b = Repo(user_id=user_b.id, owner="userb", name="repo-b", branch="main")
    db_session.add(repo_b)
    db_session.commit()
    db_session.refresh(repo_b)

    graph_b = RepoGraph(
        repo_id=repo_b.id,
        commit_sha="shabbb222",
        graph_json="{}",
    )
    wf_b = WorkingFile(
        user_id=user_b.id,
        repo_id=repo_b.id,
        path="src/main.ts",
        content="console.log('b');",
    )
    prop_b = Proposal(
        user_id=user_b.id,
        repo_id=repo_b.id,
        kind="create",
        path="src/new.ts",
        rationale="Create new",
    )
    db_session.add(graph_b)
    db_session.add(wf_b)
    db_session.add(prop_b)
    db_session.commit()
    db_session.refresh(prop_b)

    cp_b = Checkpoint(
        proposal_id=prop_b.id,
        previous=json.dumps({"content": "b_prev"}),
    )
    prev_b = PushPreview(
        user_id=user_b.id,
        repo_id=repo_b.id,
        kind="issue",
        payload="{}",
        payload_hash="hash_b",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    log_b = ActionLog(
        user_id=user_b.id,
        repo_id=repo_b.id,
        action="issue_create",
        status="succeeded",
    )
    db_session.add(cp_b)
    db_session.add(prev_b)
    db_session.add(log_b)
    db_session.commit()

    # Log in as User A via cookie session
    app = client.app
    # Set session cookie by simulating login
    with client:
        # Override get_current_user dynamically during request
        app.dependency_overrides[get_current_user] = lambda: user_a

        resp = client.post(
            "/auth/disconnect",
            headers={"X-Requested-With": "bodhcode"},
        )
        assert resp.status_code == 204

    # 4. Assert User A's data is completely gone
    assert db_session.get(User, user_a.id) is None
    assert db_session.exec(select(Repo).where(Repo.user_id == user_a.id)).all() == []
    assert db_session.exec(select(RepoGraph).where(RepoGraph.repo_id == repo_a.id)).all() == []
    assert db_session.exec(select(WorkingFile).where(WorkingFile.user_id == user_a.id)).all() == []
    assert db_session.exec(select(Proposal).where(Proposal.user_id == user_a.id)).all() == []
    user_a_checkpoints = db_session.exec(
        select(Checkpoint).where(Checkpoint.proposal_id == prop_a.id)
    ).all()
    assert user_a_checkpoints == []
    assert db_session.exec(select(PushPreview).where(PushPreview.user_id == user_a.id)).all() == []
    assert db_session.exec(select(ActionLog).where(ActionLog.user_id == user_a.id)).all() == []

    # 5. Assert User B's data is 100% intact
    assert db_session.get(User, user_b.id) is not None
    assert len(db_session.exec(select(Repo).where(Repo.user_id == user_b.id)).all()) == 1
    assert len(db_session.exec(select(RepoGraph).where(RepoGraph.repo_id == repo_b.id)).all()) == 1
    user_b_files = db_session.exec(
        select(WorkingFile).where(WorkingFile.user_id == user_b.id)
    ).all()
    assert len(user_b_files) == 1
    assert len(db_session.exec(select(Proposal).where(Proposal.user_id == user_b.id)).all()) == 1
    assert (
        len(db_session.exec(select(Checkpoint).where(Checkpoint.proposal_id == prop_b.id)).all())
        == 1
    )
    user_b_previews = db_session.exec(
        select(PushPreview).where(PushPreview.user_id == user_b.id)
    ).all()
    assert len(user_b_previews) == 1
    assert len(db_session.exec(select(ActionLog).where(ActionLog.user_id == user_b.id)).all()) == 1

    # 6. Second call without override or as deleted user must fail with 401
    app.dependency_overrides.pop(get_current_user, None)
    resp2 = client.post(
        "/auth/disconnect",
        headers={"X-Requested-With": "bodhcode"},
    )
    assert resp2.status_code == 401
