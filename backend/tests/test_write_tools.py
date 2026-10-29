"""Unit tests for write tools (create_file, edit_file, delete_file) and security constraints."""

from pathlib import Path

import networkx as nx
import pytest
from sqlmodel import Session

from app.ai.tools.base import ToolContext
from app.ai.tools.write_tools import CreateFileTool, DeleteFileTool, EditFileTool
from app.files.service import BoundFileService
from app.github.limits import INGEST_VERSION
from app.models.repo import Repo
from app.models.user import User


@pytest.fixture
def test_user(db_session: Session) -> User:
    user = User(
        github_id=54321,
        login="testcoder",
        avatar_url="https://avatar.test/coder",
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

    monkeypatch.setattr(get_settings(), "DATA_DIR", str(tmp_path))
    owner = "testcoder"
    name = "saferepo"
    commit_sha = "deadbeef123"

    src_dir = tmp_path / "repos" / owner / name / commit_sha / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / ".ingest_version").write_bytes(str(INGEST_VERSION).encode("utf-8"))
    (src_dir / "src").mkdir(parents=True, exist_ok=True)
    (src_dir / "src" / "index.ts").write_bytes(b"const a = 1;\nconst b = 2;\n")

    return tmp_path, commit_sha


@pytest.fixture
def test_repo(db_session: Session, test_user: User, test_repo_env: tuple[Path, str]) -> Repo:
    _, commit_sha = test_repo_env
    repo = Repo(
        user_id=test_user.id,
        owner="testcoder",
        name="saferepo",
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


@pytest.fixture
def tool_ctx(db_session: Session, test_user: User, test_repo: Repo) -> ToolContext:
    g = nx.DiGraph()
    g.add_node("src/index.ts", name="index.ts", external_deps=[])
    files_svc = BoundFileService(user=test_user, repo=test_repo, session=db_session)
    return ToolContext(
        user=test_user,
        repo=test_repo,
        graph=g,
        files=files_svc,
        review_mode="review",
        session=db_session,
    )


@pytest.mark.asyncio
async def test_edit_file_matches(tool_ctx: ToolContext) -> None:
    """Test edit_file: 0 matches, multiple matches, exactly one."""
    tool = EditFileTool()

    # 1. Zero matches
    res_zero = await tool.run(
        tool_ctx,
        {
            "path": "src/index.ts",
            "old": "nonexistent_var = 42",
            "new": "something_else",
            "rationale": "testing zero matches",
        },
    )
    assert not res_zero.ok
    assert "Zero matches" in (res_zero.error or "")

    # 2. Multiple matches: add duplicate lines
    tool_ctx.files.write_file("src/index.ts", "const x = 1;\nconst x = 1;\n")
    res_multi = await tool.run(
        tool_ctx,
        {
            "path": "src/index.ts",
            "old": "const x = 1;",
            "new": "const x = 2;",
            "rationale": "testing multi matches",
        },
    )
    assert not res_multi.ok
    assert "matches 2 times" in (res_multi.error or "")

    # 3. Exactly one match
    res_one = await tool.run(
        tool_ctx,
        {
            "path": "src/index.ts",
            "old": "const x = 1;\nconst x = 1;",
            "new": "const x = 1;\nconst x = 2;",
            "rationale": "replace duplicate with unique context",
        },
    )
    assert res_one.ok
    assert res_one.proposal_id is not None
    # In review mode, proposal is pending and working copy is unchanged!
    assert res_one.data["status"] == "pending"
    eff = tool_ctx.files.read_effective("src/index.ts")
    assert eff["content"] == "const x = 1;\nconst x = 1;\n"


@pytest.mark.asyncio
async def test_auto_mode_applies_edit_and_queues_delete(tool_ctx: ToolContext) -> None:
    """Auto mode automatically applies edit, but delete ALWAYS queues for review."""
    tool_ctx.review_mode = "auto"

    # Edit in auto mode
    edit_tool = EditFileTool()
    tool_ctx.files.write_file("src/index.ts", "const val = 100;\n")
    res_edit = await edit_tool.run(
        tool_ctx,
        {
            "path": "src/index.ts",
            "old": "100",
            "new": "200",
            "rationale": "Update value to 200",
        },
    )
    assert res_edit.ok
    assert res_edit.data["status"] == "applied"
    eff = tool_ctx.files.read_effective("src/index.ts")
    assert "const val = 200;" in eff["content"]

    # Delete in auto mode -> still queues!
    del_tool = DeleteFileTool()
    res_del = await del_tool.run(
        tool_ctx,
        {
            "path": "src/index.ts",
            "rationale": "Delete index file",
        },
    )
    assert res_del.ok
    assert res_del.data["status"] == "pending"  # STILL PENDING!
    # File is still present in working copy
    eff_still_there = tool_ctx.files.read_effective("src/index.ts")
    assert eff_still_there["status"] != "deleted"


@pytest.mark.asyncio
async def test_readonly_mode_blocks_all_writes(tool_ctx: ToolContext) -> None:
    """Read-only mode blocks create, edit, and delete tools."""
    tool_ctx.review_mode = "readonly"

    create_tool = CreateFileTool()
    res_create = await create_tool.run(
        tool_ctx,
        {"path": "src/new.ts", "content": "hello", "rationale": "test"},
    )
    assert not res_create.ok
    assert "Read-only mode is active" in (res_create.error or "")

    edit_tool = EditFileTool()
    res_edit = await edit_tool.run(
        tool_ctx,
        {"path": "src/index.ts", "old": "1", "new": "2", "rationale": "test"},
    )
    assert not res_edit.ok
    assert "Read-only mode is active" in (res_edit.error or "")

    del_tool = DeleteFileTool()
    res_del = await del_tool.run(
        tool_ctx,
        {"path": "src/index.ts", "rationale": "test"},
    )
    assert not res_del.ok
    assert "Read-only mode is active" in (res_del.error or "")


@pytest.mark.asyncio
async def test_write_tools_reject_path_traversal_and_git(tool_ctx: ToolContext) -> None:
    """Write tools must reject traversal ('..'), absolute paths, and '.git'."""
    create_tool = CreateFileTool()
    for bad_path in ("../outside.ts", "/root.ts", ".git/evil", "src/.git/config"):
        res = await create_tool.run(
            tool_ctx,
            {"path": bad_path, "content": "payload", "rationale": "attack"},
        )
        assert not res.ok
        assert "Invalid path" in (res.error or "")
