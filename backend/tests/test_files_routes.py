"""Integration tests for files and editor API routes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.crypto import encrypt_token
from app.auth.deps import get_current_user
from app.config import get_settings
from app.github.limits import INGEST_VERSION
from app.main import app
from app.models.graph import RepoGraph
from app.models.repo import Repo
from app.models.user import User
from app.parser.graph import PARSER_VERSION, GraphDoc, NodeDoc, StatsDoc


@pytest.fixture(name="test_user")
def test_user_fixture(db_session: Session) -> User:
    """Create test user fixture."""
    user = User(
        login="testdev",
        avatar_url="https://github.com/testdev.png",
        email="dev@example.com",
        github_id=98765,
        encrypted_github_token=encrypt_token("gho_dummy_token"),
        preferred_language="en",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(name="user_b")
def user_b_fixture(db_session: Session) -> User:
    """Create a second distinct user for isolation testing."""
    user = User(
        login="intruder",
        avatar_url="https://github.com/intruder.png",
        email="intruder@example.com",
        github_id=54321,
        encrypted_github_token=encrypt_token("gho_other_token"),
        preferred_language="en",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(name="test_repo_env")
def test_repo_env_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_user: User,
    db_session: Session,
) -> tuple[Repo, Path]:
    """Sets up a test repo with disk files and graph."""
    monkeypatch.setattr(get_settings(), "DATA_DIR", str(tmp_path))
    owner = "testdev"
    name = "editor-demo"
    commit_sha = "abc789def"

    src_dir = tmp_path / "repos" / owner / name / commit_sha / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / ".ingest_version").write_bytes(str(INGEST_VERSION).encode("utf-8"))
    (src_dir / "index.ts").write_bytes(b"export const hello = 'world';\n")
    (src_dir / "utils.ts").write_bytes(
        b"export function sum(a: number, b: number) { return a + b; }\n"
    )

    repo = Repo(
        user_id=test_user.id,
        owner=owner,
        name=name,
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    # Attach graph
    doc = GraphDoc(
        version=1,
        repo={"owner": owner, "name": name, "commit_sha": commit_sha},
        nodes=[
            NodeDoc(
                id="index.ts",
                name="index.ts",
                folder="",
                size=30,
                exports=["hello"],
                has_default_export=False,
                external_deps=[],
                unresolved_count=0,
                unresolved_dynamic=0,
                flags=[],
            ),
        ],
        edges=[],
        folders=[],
        stats=StatsDoc(files=1, edges=0, external_packages=0, cycles=0, unresolved=0),
    )
    graph = RepoGraph(
        repo_id=repo.id,
        commit_sha=repo.commit_sha,
        parser_version=PARSER_VERSION,
        graph_json=doc.to_json(),
        node_count=1,
        edge_count=0,
    )
    db_session.add(graph)
    db_session.commit()

    return repo, tmp_path


@pytest.fixture(autouse=True)
def override_auth_user(test_user: User, client: TestClient):
    """Override get_current_user dependency to use test_user by default."""
    app.dependency_overrides[get_current_user] = lambda: test_user
    client.headers["X-Requested-With"] = "bodhcode"
    yield
    client.headers.pop("X-Requested-With", None)
    app.dependency_overrides.pop(get_current_user, None)


def test_get_repo_files_tree(client: TestClient, test_repo_env: tuple[Repo, Path]) -> None:
    repo, _ = test_repo_env
    res = client.get(f"/repos/{repo.id}/files")
    assert res.status_code == 200
    data = res.json()
    assert "files" in data
    paths = {f["path"]: f for f in data["files"]}
    assert "index.ts" in paths
    assert paths["index.ts"]["graph_node"] is True
    assert paths["index.ts"]["status"] == "unchanged"
    assert "utils.ts" in paths
    assert paths["utils.ts"]["graph_node"] is False


def test_get_file_content(client: TestClient, test_repo_env: tuple[Repo, Path]) -> None:
    repo, _ = test_repo_env
    res = client.get(f"/repos/{repo.id}/files/index.ts")
    assert res.status_code == 200
    data = res.json()
    assert data["path"] == "index.ts"
    assert data["content"] == "export const hello = 'world';\n"
    assert data["language_hint"] == "typescript"
    assert data["status"] == "unchanged"
    assert "content_hash" in data


def test_put_file_edit_and_if_match_protection(
    client: TestClient,
    test_repo_env: tuple[Repo, Path],
) -> None:
    repo, _ = test_repo_env

    # 1. Read to get current hash
    read_res = client.get(f"/repos/{repo.id}/files/index.ts")
    initial_hash = read_res.json()["content_hash"]

    # 2. Put edit with matching If-Match header
    new_content = "export const hello = 'updated world';\n"
    put_res = client.put(
        f"/repos/{repo.id}/files/index.ts",
        json={"content": new_content},
        headers={"If-Match": f'"{initial_hash}"'},
    )
    assert put_res.status_code == 200
    data = put_res.json()
    assert data["status"] == "modified"
    new_hash = data["content_hash"]

    # 3. Put second edit with stale If-Match header -> 412
    stale_put = client.put(
        f"/repos/{repo.id}/files/index.ts",
        json={"content": "stale content"},
        headers={"If-Match": initial_hash},
    )
    assert stale_put.status_code == 412

    # 4. Put with correct new hash -> 200
    valid_put = client.put(
        f"/repos/{repo.id}/files/index.ts",
        json={"content": "final content"},
        headers={"If-Match": new_hash},
    )
    assert valid_put.status_code == 200


def test_delete_and_revert_file(client: TestClient, test_repo_env: tuple[Repo, Path]) -> None:
    repo, _ = test_repo_env

    # Delete index.ts
    del_res = client.delete(f"/repos/{repo.id}/files/index.ts")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Subsequent GET returns 404
    get_res = client.get(f"/repos/{repo.id}/files/index.ts")
    assert get_res.status_code == 404

    # Changes endpoint lists deleted file
    changes_res = client.get(f"/repos/{repo.id}/changes")
    assert changes_res.status_code == 200
    changes = {c["path"]: c["status"] for c in changes_res.json()["changes"]}
    assert changes.get("index.ts") == "deleted"

    # Revert index.ts
    rev_res = client.post(f"/repos/{repo.id}/files/index.ts/revert")
    assert rev_res.status_code == 200
    assert rev_res.json()["reverted"] is True

    # Now file is restored
    restored_get = client.get(f"/repos/{repo.id}/files/index.ts")
    assert restored_get.status_code == 200
    assert restored_get.json()["status"] == "unchanged"


def test_diff_endpoint(client: TestClient, test_repo_env: tuple[Repo, Path]) -> None:
    repo, _ = test_repo_env

    # Unmodified diff
    diff_unmod = client.get(f"/repos/{repo.id}/diff/index.ts")
    assert diff_unmod.status_code == 200
    assert diff_unmod.json()["status"] == "unchanged"

    # Edit file
    client.put(f"/repos/{repo.id}/files/index.ts", json={"content": "console.log('modified');\n"})

    # Modified diff
    diff_mod = client.get(f"/repos/{repo.id}/diff/index.ts")
    assert diff_mod.status_code == 200
    data = diff_mod.json()
    assert data["status"] == "modified"
    assert "export const hello" in data["original"]
    assert "console.log('modified')" in data["modified"]


def test_rename_endpoint(client: TestClient, test_repo_env: tuple[Repo, Path]) -> None:
    repo, _ = test_repo_env

    rename_res = client.post(
        f"/repos/{repo.id}/files/index.ts/rename",
        json={"new_path": "main.ts"},
    )
    assert rename_res.status_code == 200
    assert rename_res.json()["status"] == "renamed"

    # index.ts is now deleted (404 on get)
    assert client.get(f"/repos/{repo.id}/files/index.ts").status_code == 404

    # main.ts exists with index.ts's content
    new_file = client.get(f"/repos/{repo.id}/files/main.ts")
    assert new_file.status_code == 200
    assert new_file.json()["status"] == "added"
    assert "export const hello" in new_file.json()["content"]


def test_path_traversal_rejection(client: TestClient, test_repo_env: tuple[Repo, Path]) -> None:
    repo, _ = test_repo_env

    # 1. Traversal path
    res_traversal = client.get(f"/repos/{repo.id}/files/..%2F..%2Fetc%2Fpasswd")
    assert res_traversal.status_code == 400

    # 2. .git segment
    res_git = client.get(f"/repos/{repo.id}/files/.git/config")
    assert res_git.status_code == 400


def test_ownership_isolation(
    client: TestClient,
    test_repo_env: tuple[Repo, Path],
    user_b: User,
) -> None:
    repo, _ = test_repo_env

    # Edit file as test_user
    client.put(f"/repos/{repo.id}/files/index.ts", json={"content": "secret user A edit"})

    # Switch current user to user_b
    app.dependency_overrides[get_current_user] = lambda: user_b
    try:
        # User B cannot access User A's repo -> 404
        assert client.get(f"/repos/{repo.id}/files").status_code == 404
        assert client.get(f"/repos/{repo.id}/files/index.ts").status_code == 404
        hack_res = client.put(f"/repos/{repo.id}/files/index.ts", json={"content": "hack"})
        assert hack_res.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_binary_and_oversize_rejection(
    client: TestClient,
    test_repo_env: tuple[Repo, Path],
) -> None:
    repo, _ = test_repo_env

    # Binary file (contains null byte)
    res_bin = client.put(f"/repos/{repo.id}/files/binary.dat", json={"content": "hello\x00world"})
    assert res_bin.status_code == 415

    # Oversize file (> 1 MB)
    res_large = client.put(f"/repos/{repo.id}/files/large.txt", json={"content": "x" * 1_000_001})
    assert res_large.status_code == 413
