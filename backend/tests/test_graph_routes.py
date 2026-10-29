"""Tests for repository dependency graph API routes and background analysis job."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.crypto import encrypt_token
from app.auth.deps import get_current_user
from app.config import get_settings
from app.github.limits import INGEST_VERSION
from app.main import app
from app.models.graph import RepoGraph
from app.models.repo import Repo
from app.models.user import User, utc_now
from app.parser.graph import PARSER_VERSION, GraphDoc
from app.routes.graph_cache import clear_graph_cache
from app.services.analyze import analyze_repo


@pytest.fixture(name="user_a")
def user_a_fixture(db_session: Session) -> User:
    """Fixture creating user A with encrypted token."""
    user = User(
        github_id=101,
        login="alice",
        name="Alice Coder",
        avatar_url="https://avatar.url/alice",
        email="alice@example.com",
        encrypted_github_token=encrypt_token("gho_alice_secret_token_123"),
        token_scopes="read:user",
        created_at=utc_now(),
        last_login_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(name="user_b")
def user_b_fixture(db_session: Session) -> User:
    """Fixture creating user B with encrypted token."""
    user = User(
        github_id=102,
        login="bob",
        name="Bob Builder",
        avatar_url="https://avatar.url/bob",
        email="bob@example.com",
        encrypted_github_token=encrypt_token("gho_bob_secret_token_456"),
        token_scopes="read:user",
        created_at=utc_now(),
        last_login_at=utc_now(),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(autouse=True)
def clean_cache() -> None:
    """Ensure in-memory graph cache is pristine for each test."""
    clear_graph_cache()


def _create_sample_graph_json(owner: str, name: str, commit_sha: str) -> str:
    """Generate sample canonical GraphDoc json for testing."""
    diamond_dict = {
        "version": PARSER_VERSION,
        "repo": {"owner": owner, "name": name, "commit_sha": commit_sha},
        "nodes": [
            {
                "id": "src/S.ts",
                "name": "S.ts",
                "folder": "src",
                "size": 100,
                "exports": ["S"],
                "has_default_export": False,
                "external_deps": ["react"],
                "unresolved_count": 0,
                "unresolved_dynamic": 0,
                "flags": [],
            },
            {
                "id": "src/L.ts",
                "name": "L.ts",
                "folder": "src",
                "size": 150,
                "exports": ["L"],
                "has_default_export": False,
                "external_deps": [],
                "unresolved_count": 0,
                "unresolved_dynamic": 0,
                "flags": [],
            },
            {
                "id": "src/R.ts",
                "name": "R.ts",
                "folder": "src",
                "size": 150,
                "exports": ["R"],
                "has_default_export": False,
                "external_deps": [],
                "unresolved_count": 0,
                "unresolved_dynamic": 0,
                "flags": [],
            },
            {
                "id": "src/T.ts",
                "name": "T.ts",
                "folder": "src",
                "size": 200,
                "exports": ["T"],
                "has_default_export": False,
                "external_deps": [],
                "unresolved_count": 0,
                "unresolved_dynamic": 0,
                "flags": [],
            },
        ],
        "edges": [
            {
                "id": "src/L.ts>src/S.ts#import",
                "source": "src/L.ts",
                "target": "src/S.ts",
                "kind": "import",
                "type_only": False,
                "count": 1,
            },
            {
                "id": "src/R.ts>src/S.ts#import",
                "source": "src/R.ts",
                "target": "src/S.ts",
                "kind": "import",
                "type_only": False,
                "count": 1,
            },
            {
                "id": "src/T.ts>src/L.ts#import",
                "source": "src/T.ts",
                "target": "src/L.ts",
                "kind": "import",
                "type_only": False,
                "count": 1,
            },
            {
                "id": "src/T.ts>src/R.ts#import",
                "source": "src/T.ts",
                "target": "src/R.ts",
                "kind": "import",
                "type_only": False,
                "count": 1,
            },
        ],
        "folders": [{"id": "src", "parent": "", "file_count": 4}],
        "stats": {
            "files": 4,
            "edges": 4,
            "external_packages": 1,
            "cycles": 0,
            "unresolved": 0,
        },
    }
    return GraphDoc.from_dict(diamond_dict).to_json()


def test_graph_not_ready_returns_409(
    client: TestClient,
    user_a: User,
    db_session: Session,
) -> None:
    """Verify GET /repos/{id}/graph returns 409 when repo is not analyzed."""
    repo = Repo(
        user_id=user_a.id,  # type: ignore[arg-type]
        owner="facebook",
        name="react",
        branch="main",
        status="fetched",
        commit_sha="c123456",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        resp = client.get(
            f"/repos/{repo.id}/graph",
            headers={"X-CSRF-Token": "1"},
        )
        assert resp.status_code == 409
        assert resp.json() == {"detail": "not_ready"}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_graph_etag_and_304(
    client: TestClient,
    user_a: User,
    db_session: Session,
) -> None:
    """Verify ETag and If-None-Match caching on GET /repos/{id}/graph."""
    commit_sha = "c999888"
    graph_json = _create_sample_graph_json("facebook", "react", commit_sha)

    repo = Repo(
        user_id=user_a.id,  # type: ignore[arg-type]
        owner="facebook",
        name="react",
        branch="main",
        status="ready",
        commit_sha=commit_sha,
        file_count=4,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    repo_graph = RepoGraph(
        repo_id=repo.id,  # type: ignore[arg-type]
        commit_sha=commit_sha,
        parser_version=PARSER_VERSION,
        graph_json=graph_json,
        node_count=4,
        edge_count=4,
        created_at=utc_now(),
    )
    db_session.add(repo_graph)
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        # First request: 200 OK with ETag
        resp1 = client.get(
            f"/repos/{repo.id}/graph",
            headers={"X-CSRF-Token": "1"},
        )
        assert resp1.status_code == 200
        etag = resp1.headers.get("etag")
        assert etag is not None
        assert f"{commit_sha}_{PARSER_VERSION}" in etag
        assert resp1.headers.get("cache-control") == "private, max-age=0, must-revalidate"
        assert resp1.json()["stats"]["files"] == 4

        # Second request with If-None-Match: 304 NOT MODIFIED
        resp2 = client.get(
            f"/repos/{repo.id}/graph",
            headers={"X-CSRF-Token": "1", "If-None-Match": etag},
        )
        assert resp2.status_code == 304
        assert resp2.headers.get("etag") == etag
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_blast_endpoint_queries(
    client: TestClient,
    user_a: User,
    db_session: Session,
) -> None:
    """Verify blast radius endpoint impacts, leaf files, 404 for unknown, 400 for path traversal."""
    commit_sha = "c999888"
    graph_json = _create_sample_graph_json("facebook", "react", commit_sha)

    repo = Repo(
        user_id=user_a.id,  # type: ignore[arg-type]
        owner="facebook",
        name="react",
        branch="main",
        status="ready",
        commit_sha=commit_sha,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    repo_graph = RepoGraph(
        repo_id=repo.id,  # type: ignore[arg-type]
        commit_sha=commit_sha,
        parser_version=PARSER_VERSION,
        graph_json=graph_json,
        node_count=4,
        edge_count=4,
        created_at=utc_now(),
    )
    db_session.add(repo_graph)
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        # 1. Query S.ts: transitively imported by L, R, and T
        resp = client.get(
            f"/repos/{repo.id}/blast?file=src/S.ts",
            headers={"X-CSRF-Token": "1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["file"] == "src/S.ts"
        assert data["total"] == 3
        assert len(data["impacts"]) == 3

        # 2. Query T.ts (leaf with no importers): total is 0
        resp_leaf = client.get(
            f"/repos/{repo.id}/blast?file=src/T.ts",
            headers={"X-CSRF-Token": "1"},
        )
        assert resp_leaf.status_code == 200
        assert resp_leaf.json()["total"] == 0
        assert resp_leaf.json()["impacts"] == []

        # 3. Query non-existent file: 404 file_not_in_graph
        resp_not_found = client.get(
            f"/repos/{repo.id}/blast?file=nope.ts",
            headers={"X-CSRF-Token": "1"},
        )
        assert resp_not_found.status_code == 404
        assert resp_not_found.json() == {"detail": "file_not_in_graph"}

        # 4. Path traversal attempt: 400
        resp_bad = client.get(
            f"/repos/{repo.id}/blast?file=../x",
            headers={"X-CSRF-Token": "1"},
        )
        assert resp_bad.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_deps_and_cycles_endpoints(
    client: TestClient,
    user_a: User,
    db_session: Session,
) -> None:
    """Verify /deps and /cycles endpoints return correct dependencies and cycles list."""
    commit_sha = "c999888"
    graph_json = _create_sample_graph_json("facebook", "react", commit_sha)

    repo = Repo(
        user_id=user_a.id,  # type: ignore[arg-type]
        owner="facebook",
        name="react",
        branch="main",
        status="ready",
        commit_sha=commit_sha,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    repo_graph = RepoGraph(
        repo_id=repo.id,  # type: ignore[arg-type]
        commit_sha=commit_sha,
        parser_version=PARSER_VERSION,
        graph_json=graph_json,
        node_count=4,
        edge_count=4,
        created_at=utc_now(),
    )
    db_session.add(repo_graph)
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        # /deps for src/T.ts
        resp_deps = client.get(
            f"/repos/{repo.id}/deps?file=src/T.ts&depth=1",
            headers={"X-CSRF-Token": "1"},
        )
        assert resp_deps.status_code == 200
        deps_data = resp_deps.json()
        assert deps_data["file"] == "src/T.ts"
        assert len(deps_data["dependencies"]) == 2
        assert deps_data["dependents"] == []

        # /cycles: diamond has 0 cycles
        resp_cycles = client.get(
            f"/repos/{repo.id}/cycles",
            headers={"X-CSRF-Token": "1"},
        )
        assert resp_cycles.status_code == 200
        assert resp_cycles.json() == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_ownership_isolation(
    client: TestClient,
    user_a: User,
    user_b: User,
    db_session: Session,
) -> None:
    """Verify User B cannot access User A's repo graph, blast, or start analysis (404)."""
    commit_sha = "c111222"
    graph_json = _create_sample_graph_json("alice_owner", "alice_repo", commit_sha)

    repo = Repo(
        user_id=user_a.id,  # type: ignore[arg-type]
        owner="alice_owner",
        name="alice_repo",
        branch="main",
        status="ready",
        commit_sha=commit_sha,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    repo_graph = RepoGraph(
        repo_id=repo.id,  # type: ignore[arg-type]
        commit_sha=commit_sha,
        parser_version=PARSER_VERSION,
        graph_json=graph_json,
        node_count=4,
        edge_count=4,
        created_at=utc_now(),
    )
    db_session.add(repo_graph)
    db_session.commit()

    # User B tries to read User A's graph endpoints
    app.dependency_overrides[get_current_user] = lambda: user_b
    try:
        resp_graph = client.get(f"/repos/{repo.id}/graph", headers={"X-CSRF-Token": "1"})
        assert resp_graph.status_code == 404

        resp_blast = client.get(
            f"/repos/{repo.id}/blast?file=src/S.ts",
            headers={"X-CSRF-Token": "1"},
        )
        assert resp_blast.status_code == 404

        resp_analyze = client.post(
            f"/repos/{repo.id}/analyze",
            headers={"X-Requested-With": "bodhcode"},
        )
        assert resp_analyze.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_analyze_job_end_to_end(
    tmp_path: Path,
    db_session: Session,
    user_a: User,
) -> None:
    """Test full analyze_repo execution on source files on disk, and instant second run skip."""
    owner = "org"
    name = "repo"
    commit_sha = "deadbeef1234"

    # Set up simulated Phase 3 extracted directory
    repo_src = tmp_path / "repos" / owner / name / commit_sha / "src"
    repo_src.mkdir(parents=True, exist_ok=True)
    (repo_src / ".ingest_version").write_text(str(INGEST_VERSION), encoding="utf-8")
    (repo_src / "tsconfig.json").write_text('{"compilerOptions": {"baseUrl": "."}}')
    (repo_src / "a.ts").write_text('import { b } from "./b";\nexport const a = b;')
    (repo_src / "b.ts").write_text("export const b = 42;")

    repo = Repo(
        user_id=user_a.id,  # type: ignore[arg-type]
        owner=owner,
        name=name,
        branch="main",
        status="fetched",
        commit_sha=commit_sha,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    with patch.object(get_settings(), "DATA_DIR", str(tmp_path)):
        import asyncio

        # First run: analyzes files and produces RepoGraph
        asyncio.run(analyze_repo(repo.id))  # type: ignore[arg-type]

        db_session.refresh(repo)
        assert repo.status == "ready"
        assert repo.file_count == 2

        graph_record = db_session.exec(
            select(RepoGraph).where(RepoGraph.repo_id == repo.id)
        ).first()
        assert graph_record is not None
        assert graph_record.node_count == 2
        assert graph_record.edge_count == 1
        initial_json = graph_record.graph_json

        # Second run: instant skip (cached valid graph), unchanged JSON
        asyncio.run(analyze_repo(repo.id))  # type: ignore[arg-type]
        db_session.refresh(repo)
        assert repo.status == "ready"

        second_graph_record = db_session.exec(
            select(RepoGraph).where(RepoGraph.repo_id == repo.id)
        ).first()
        assert second_graph_record is not None
        assert second_graph_record.graph_json == initial_json
