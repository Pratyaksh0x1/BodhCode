"""Unit tests for new read tools: parse_file, list_files, search_code, translate_text."""

from pathlib import Path

import networkx as nx
import pytest
from sqlmodel import Session

from app.ai.tools.base import ToolContext
from app.ai.tools.read_tools import (
    ListFilesTool,
    ParseFileTool,
    SearchCodeTool,
    UseSkillTool,
)
from app.files.service import BoundFileService
from app.github.limits import INGEST_VERSION
from app.models.repo import Repo
from app.models.user import User


@pytest.fixture
def test_user(db_session: Session) -> User:
    user = User(
        github_id=66666,
        login="readerdev",
        avatar_url="https://avatar.test/reader",
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
    owner = "readerdev"
    name = "readrepo"
    commit_sha = "aabbccddee"

    src_dir = tmp_path / "repos" / owner / name / commit_sha / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / ".ingest_version").write_bytes(str(INGEST_VERSION).encode("utf-8"))

    (src_dir / "src").mkdir(parents=True, exist_ok=True)
    (src_dir / "src" / "math.ts").write_bytes(
        b"export const add = (a: number, b: number): number => a + b;\n"
    )
    (src_dir / "src" / "index.ts").write_bytes(
        b"import { add } from './math';\nexport const result = add(1, 2);\n"
    )

    return tmp_path, commit_sha


@pytest.fixture
def test_repo(db_session: Session, test_user: User, test_repo_env: tuple[Path, str]) -> Repo:
    _, commit_sha = test_repo_env
    repo = Repo(
        user_id=test_user.id,
        owner="readerdev",
        name="readrepo",
        branch="main",
        commit_sha=commit_sha,
        status="ready",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


@pytest.fixture
def read_ctx(db_session: Session, test_user: User, test_repo: Repo) -> ToolContext:
    g = nx.DiGraph()
    g.add_node("src/index.ts", name="index.ts", external_deps=[])
    g.add_node("src/math.ts", name="math.ts", external_deps=[])
    g.add_edge("src/index.ts", "src/math.ts", kinds={"import"}, type_only=False, count=1)

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
async def test_parse_file_tool(read_ctx: ToolContext) -> None:
    """parse_file extracts imports with resolutions and exports deterministically."""
    tool = ParseFileTool()
    res = await tool.run(read_ctx, {"path": "src/index.ts"})
    assert res.ok
    data = res.data
    assert data["path"] == "src/index.ts"
    assert "result" in data["exports"]
    assert len(data["imports"]) == 1
    imp = data["imports"][0]
    assert imp["specifier"] == "./math"
    assert imp["target"] == "src/math.ts"
    assert imp["resolution_kind"] == "file"


@pytest.mark.asyncio
async def test_list_files_tool(read_ctx: ToolContext) -> None:
    """list_files lists tree items and supports subdirectory filtering."""
    tool = ListFilesTool()
    # List all
    res_all = await tool.run(read_ctx, {"dir": ""})
    assert res_all.ok
    paths = [f["path"] for f in res_all.data["files"]]
    assert "src/math.ts" in paths
    assert "src/index.ts" in paths

    # Filter dir
    res_sub = await tool.run(read_ctx, {"dir": "src"})
    assert res_sub.ok
    assert len(res_sub.data["files"]) >= 2


@pytest.mark.asyncio
async def test_search_code_tool(read_ctx: ToolContext) -> None:
    """search_code finds substring and regex matches across files."""
    tool = SearchCodeTool()

    # Substring search
    res_sub = await tool.run(read_ctx, {"query": "export const add"})
    assert res_sub.ok
    assert len(res_sub.data["matches"]) >= 1
    assert res_sub.data["matches"][0]["path"] == "src/math.ts"

    # Regex search
    res_reg = await tool.run(read_ctx, {"query": r"result\s*=", "regex": True})
    assert res_reg.ok
    assert len(res_reg.data["matches"]) >= 1
    assert res_reg.data["matches"][0]["path"] == "src/index.ts"

    # Reject oversized pattern
    res_huge = await tool.run(read_ctx, {"query": "x" * 201})
    assert not res_huge.ok
    assert "exceeds maximum length" in (res_huge.error or "")


@pytest.mark.asyncio
async def test_use_skill_stub(read_ctx: ToolContext) -> None:
    """use_skill returns stub message for Phase 13."""
    tool = UseSkillTool()
    res = await tool.run(read_ctx, {"name": "refactor_architecture", "args": {}})
    assert not res.ok
    assert "Phase 13" in (res.error or "")
