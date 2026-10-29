"""Tests for Workspace AST analysis routes and embedded browser tools."""

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.ai.tools.base import ToolContext
from app.ai.tools.browser_tools import (
    BrowserActionTool,
    BrowserOpenTool,
    BrowserScreenshotTool,
)
from app.auth.deps import get_current_user
from app.auth.service import upsert_github_user
from app.models.user import User


@pytest.fixture
def test_user(db_session: Session) -> User:
    return upsert_github_user(
        db_session,
        github_id=40001,
        login="workspace-tester",
        name="Workspace Tester",
        avatar_url="https://avatar.url/ws.png",
        email="ws@example.com",
        access_token="gho_ws_token",
        token_scopes="read:user",
    )


def test_workspace_graph_and_ping(
    client: TestClient, db_session: Session, test_user: User, tmp_path
):
    """Verify /workspace/graph returns deterministic AST graph and ping returns verified paths."""
    # Create a small valid workspace in tmp_path
    ws_dir = tmp_path / "my_project"
    ws_dir.mkdir()
    (ws_dir / "index.ts").write_text("import { util } from './util'; export const main = 1;")
    (ws_dir / "util.ts").write_text("export const util = () => true;")

    client.app.dependency_overrides[get_current_user] = lambda: db_session.get(User, test_user.id)
    headers = {"X-Requested-With": "bodhcode"}

    try:
        # 1. GET /workspace/graph
        resp = client.get(f"/workspace/graph?dir_path={ws_dir.as_posix()}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "graph" in data
        assert "stats" in data
        assert "nodes" in data["graph"]
        assert "edges" in data["graph"]
        assert len(data["graph"]["nodes"]) >= 2

        # 2. POST /workspace/analyze
        analyze_resp = client.post(
            "/workspace/analyze",
            json={"path": ws_dir.as_posix()},
            headers=headers,
        )
        assert analyze_resp.status_code == 200
        assert "graph" in analyze_resp.json()

        # 3. POST /workspace/ping
        ping_resp = client.post(
            "/workspace/ping",
            json={"question": "What is in index.ts?", "path": ws_dir.as_posix()},
            headers=headers,
        )
        assert ping_resp.status_code == 200
        ping_data = ping_resp.json()
        assert "answer" in ping_data
        assert "verified_paths" in ping_data
        assert ping_data["nodes_count"] >= 2
        assert "index.ts" in ping_data["verified_paths"]

    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_browser_tools(db_session: Session, test_user: User):
    """Verify embedded browser tools: open, screenshot, action."""
    ctx = ToolContext(
        user=test_user,
        repo=None,
        graph=nx.DiGraph(),
        files=None,
        review_mode="review",
        session=db_session,
    )

    # 1. BrowserOpenTool
    open_tool = BrowserOpenTool()
    res1 = await open_tool.run(ctx, {"url": "http://localhost:5173"})
    assert res1.ok is True
    assert res1.data["url"] == "http://localhost:5173"
    assert "embedded" in res1.data["preview_mode"]

    empty_res = await open_tool.run(ctx, {"url": ""})
    assert empty_res.ok is False

    # 2. BrowserScreenshotTool
    screenshot_tool = BrowserScreenshotTool()
    res2 = await screenshot_tool.run(ctx, {"url": "http://localhost:5173", "selector": "#root"})
    assert res2.ok is True
    assert res2.data["format"] == "png"
    assert res2.data["selector"] == "#root"

    # 3. BrowserActionTool
    action_tool = BrowserActionTool()
    res3 = await action_tool.run(ctx, {"action": "click", "target": "button#submit"})
    assert res3.ok is True
    assert res3.data["action"] == "click"
    assert res3.data["target"] == "button#submit"
