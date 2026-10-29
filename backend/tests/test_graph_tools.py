"""Unit tests for app/ai/graph_tools.py."""

from pathlib import Path

import networkx as nx
import pytest

from app.ai.graph_tools import (
    GRAPH_TOOL_SCHEMAS,
    GraphTools,
    blast_radius,
    find_files,
    get_file_exports,
    get_graph_summary,
    list_dependencies,
    list_dependents,
    read_file,
)


@pytest.fixture
def sample_graph() -> nx.DiGraph:
    """Create a sample dependency graph for testing."""
    g = nx.DiGraph()

    # Nodes
    g.add_node(
        "src/index.ts",
        name="index.ts",
        exports=["main", "init"],
        has_default_export=True,
        external_deps=["react", "lodash"],
    )
    g.add_node(
        "src/auth.ts",
        name="auth.ts",
        exports=["login", "logout", "User"],
        has_default_export=False,
        external_deps=["jsonwebtoken"],
    )
    g.add_node(
        "src/utils.ts",
        name="utils.ts",
        exports=["formatDate"],
        has_default_export=False,
        external_deps=[],
    )
    g.add_node(
        "src/api/client.ts",
        name="client.ts",
        exports=["fetchData"],
        has_default_export=True,
        external_deps=["axios"],
    )

    # Edges: source imports target
    # index.ts imports auth.ts and utils.ts
    g.add_edge("src/index.ts", "src/auth.ts", kinds={"import"}, type_only=False, count=2)
    g.add_edge("src/index.ts", "src/utils.ts", kinds={"import"}, type_only=False, count=1)
    # auth.ts imports utils.ts and api/client.ts
    g.add_edge("src/auth.ts", "src/utils.ts", kinds={"import"}, type_only=False, count=1)
    g.add_edge("src/auth.ts", "src/api/client.ts", kinds={"import"}, type_only=False, count=1)

    return g


def test_tool_schemas_valid() -> None:
    """Verify tool schemas are properly formatted."""
    assert len(GRAPH_TOOL_SCHEMAS) == 7
    for schema in GRAPH_TOOL_SCHEMAS:
        assert schema["type"] == "function"
        assert "name" in schema["function"]
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]


def test_list_dependencies(sample_graph: nx.DiGraph) -> None:
    """Test direct dependency listing and external dependencies."""
    res = list_dependencies(sample_graph, "src/index.ts")
    assert res["file"] == "src/index.ts"
    deps = [d["file"] for d in res["dependencies"]]
    assert deps == ["src/auth.ts", "src/utils.ts"]
    assert res["external_packages"] == ["lodash", "react"]


def test_list_dependencies_unknown_file(sample_graph: nx.DiGraph) -> None:
    """Unknown file returns error and suggestions."""
    res = list_dependencies(sample_graph, "src/aut.ts")
    assert "error" in res
    assert "src/auth.ts" in res["suggestions"]


def test_list_dependents(sample_graph: nx.DiGraph) -> None:
    """Test listing direct dependents (importers)."""
    res = list_dependents(sample_graph, "src/utils.ts")
    assert res["file"] == "src/utils.ts"
    dependents = [d["file"] for d in res["dependents"]]
    assert dependents == ["src/auth.ts", "src/index.ts"]
    assert res["total"] == 2


def test_list_dependents_unknown_file(sample_graph: nx.DiGraph) -> None:
    """Unknown file returns error and suggestions."""
    res = list_dependents(sample_graph, "nonexistent.ts")
    assert "error" in res


def test_blast_radius(sample_graph: nx.DiGraph) -> None:
    """Test blast radius calculation."""
    # Changing api/client.ts affects auth.ts (depth 1) and index.ts (depth 2)
    res = blast_radius(sample_graph, "src/api/client.ts", max_depth=3)
    assert res["file"] == "src/api/client.ts"
    assert res["total"] == 2
    impact_files = [imp["file"] for imp in res["impacts"]]
    assert impact_files == ["src/auth.ts", "src/index.ts"]


def test_blast_radius_truncation() -> None:
    """Test blast radius truncation when impacts exceed 200."""
    g = nx.DiGraph()
    root = "src/root.ts"
    g.add_node(root)
    for i in range(250):
        node = f"src/file_{i}.ts"
        g.add_node(node)
        g.add_edge(node, root, kinds={"import"}, type_only=False, count=1)

    res = blast_radius(g, root)
    assert res["total"] == 250
    assert len(res["impacts"]) == 200
    assert res["truncated"] is True


def test_find_files(sample_graph: nx.DiGraph) -> None:
    """Test substring and fuzzy file matching."""
    res = find_files(sample_graph, "auth")
    assert "src/auth.ts" in res["matches"]

    # Fuzzy match
    res_fuzzy = find_files(sample_graph, "clinet")
    assert "src/api/client.ts" in res_fuzzy["matches"]

    # Limit enforcement
    res_limit = find_files(sample_graph, "src", limit=2)
    assert len(res_limit["matches"]) <= 2

    # Never returns non-existent paths
    for m in res_limit["matches"]:
        assert m in sample_graph.nodes


def test_get_file_exports(sample_graph: nx.DiGraph) -> None:
    """Test retrieving file exports and default export flag."""
    res = get_file_exports(sample_graph, "src/auth.ts")
    assert res["exports"] == ["User", "login", "logout"]
    assert res["has_default_export"] is False

    res_idx = get_file_exports(sample_graph, "src/index.ts")
    assert res_idx["has_default_export"] is True


def test_read_file(tmp_path: Path, sample_graph: nx.DiGraph) -> None:
    """Test reading file lines with line numbers and character bounds."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    auth_file = src_dir / "auth.ts"
    content = (
        "import { utils } from './utils';\n"
        "export function login() {}\n"
        "export function logout() {}\n"
    )
    auth_file.write_text(content, encoding="utf-8")

    res = read_file(sample_graph, "src/auth.ts", tmp_path, start=1, end=2)
    assert res["file"] == "src/auth.ts"
    assert res["start_line"] == 1
    assert res["end_line"] == 2
    assert "1: import { utils }" in res["content"]
    assert "2: export function login()" in res["content"]
    assert "<untrusted_data" in res["content"]


def test_read_file_caps_and_traversal(tmp_path: Path, sample_graph: nx.DiGraph) -> None:
    """Test read_file 300-line cap, 12000 character cap, and path traversal rejection."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    index_file = src_dir / "index.ts"

    # Write 400 lines
    lines = [f"// Line {i}: " + ("x" * 50) for i in range(1, 401)]
    index_file.write_text("\n".join(lines), encoding="utf-8")

    # Line cap test: request 1 to 400 -> capped at 300
    res = read_file(sample_graph, "src/index.ts", tmp_path, start=1, end=400)
    assert res["end_line"] - res["start_line"] + 1 <= 300

    # Character cap test: 300 lines of 50 chars is ~15,000 chars -> truncated to 12,000 chars
    assert res["truncated"] is True
    assert "[truncated]" in res["content"]

    # Non-node file rejection
    res_non_node = read_file(sample_graph, "src/other.ts", tmp_path)
    assert "error" in res_non_node

    # Path traversal rejection
    sample_graph.add_node("../../etc/passwd")
    res_traversal = read_file(sample_graph, "../../etc/passwd", tmp_path)
    assert "error" in res_traversal


def test_get_graph_summary(sample_graph: nx.DiGraph) -> None:
    """Test graph summary calculation."""
    res = get_graph_summary(sample_graph)
    assert res["total_files"] == 4
    assert res["total_edges"] == 4
    assert res["total_external_packages"] == 4  # react, lodash, jsonwebtoken, axios
    assert len(res["top_files_by_dependents"]) > 0
    assert res["cycles_count"] == 0


def test_graph_tools_dispatcher(sample_graph: nx.DiGraph) -> None:
    """Test GraphTools wrapper dispatching calls."""
    tools = GraphTools(sample_graph)
    res = tools.execute("list_dependencies", {"file": "src/index.ts"})
    assert res["file"] == "src/index.ts"

    res_unknown = tools.execute("unknown_tool", {})
    assert "error" in res_unknown
