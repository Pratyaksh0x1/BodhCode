"""Tests for blast radius calculation, dependencies, dependents, and cycle detection."""

import networkx as nx
import pytest

from app.parser.blast import (
    Impact,
    NodeNotFound,
    blast_radius,
    degree_stats,
    dependencies,
    dependents,
    find_cycles,
    to_digraph,
)
from app.parser.graph import (
    EdgeDoc,
    FolderDoc,
    GraphDoc,
    NodeDoc,
    StatsDoc,
)


def _make_dummy_doc(nodes: list[str], edges: list[tuple[str, str, str, bool, int]]) -> GraphDoc:
    """Helper to build a minimal GraphDoc for testing."""
    node_docs = [
        NodeDoc(
            id=nid,
            name=nid.rsplit("/", 1)[-1],
            folder=nid.rsplit("/", 1)[0] if "/" in nid else "",
            size=100,
            exports=["exp"],
            has_default_export=False,
            external_deps=[],
            unresolved_count=0,
            unresolved_dynamic=0,
            flags=[],
        )
        for nid in sorted(nodes)
    ]
    edge_docs = [
        EdgeDoc(
            id=f"{src}>{tgt}#{kind}{':type' if type_only else ''}",
            source=src,
            target=tgt,
            kind=kind,
            type_only=type_only,
            count=count,
        )
        for src, tgt, kind, type_only, count in edges
    ]
    return GraphDoc(
        version=1,
        repo={"owner": "test", "name": "repo", "commit_sha": "abc1234"},
        nodes=node_docs,
        edges=edge_docs,
        folders=[FolderDoc(id="src", parent="", file_count=len(node_docs))],
        stats=StatsDoc(
            files=len(node_docs),
            edges=len(edge_docs),
            external_packages=0,
            cycles=0,
            unresolved=0,
        ),
    )


def test_diamond_graph_blast_radius() -> None:
    """Verify exact (file, depth, via) lists on a diamond graph.

    Graph:
      L imports S
      R imports S
      T imports L and R
    """
    doc = _make_dummy_doc(
        nodes=["src/S.ts", "src/L.ts", "src/R.ts", "src/T.ts"],
        edges=[
            ("src/L.ts", "src/S.ts", "import", False, 1),
            ("src/R.ts", "src/S.ts", "import", False, 1),
            ("src/T.ts", "src/L.ts", "import", False, 1),
            ("src/T.ts", "src/R.ts", "import", False, 1),
        ],
    )
    g = to_digraph(doc)

    impacts = blast_radius(g, "src/S.ts")
    assert len(impacts) == 3

    # Sorted by (depth, file): depth 1 has L and R, depth 2 has T via L (alphabetical BFS order)
    assert impacts[0] == Impact(file="src/L.ts", depth=1, via="src/S.ts")
    assert impacts[1] == Impact(file="src/R.ts", depth=1, via="src/S.ts")
    assert impacts[2] == Impact(file="src/T.ts", depth=2, via="src/L.ts")

    # Leaf with no importers returns []
    assert blast_radius(g, "src/T.ts") == []


def test_blast_radius_max_depth() -> None:
    """Verify max_depth truncates transitive impacts."""
    doc = _make_dummy_doc(
        nodes=["src/S.ts", "src/L.ts", "src/R.ts", "src/T.ts"],
        edges=[
            ("src/L.ts", "src/S.ts", "import", False, 1),
            ("src/R.ts", "src/S.ts", "import", False, 1),
            ("src/T.ts", "src/L.ts", "import", False, 1),
            ("src/T.ts", "src/R.ts", "import", False, 1),
        ],
    )
    g = to_digraph(doc)

    depth_1_impacts = blast_radius(g, "src/S.ts", max_depth=1)
    assert len(depth_1_impacts) == 2
    assert [i["file"] for i in depth_1_impacts] == ["src/L.ts", "src/R.ts"]

    depth_0_impacts = blast_radius(g, "src/S.ts", max_depth=0)
    assert depth_0_impacts == []


def test_blast_radius_include_type_only() -> None:
    """Verify include_type_only=False removes impacts through type-only edges."""
    doc = _make_dummy_doc(
        nodes=["src/base.ts", "src/type_user.ts", "src/runtime_user.ts"],
        edges=[
            ("src/type_user.ts", "src/base.ts", "import", True, 1),
            ("src/runtime_user.ts", "src/base.ts", "import", False, 1),
        ],
    )
    g = to_digraph(doc, include_type_only=True)

    with_type = blast_radius(g, "src/base.ts", include_type_only=True)
    assert len(with_type) == 2
    assert [i["file"] for i in with_type] == ["src/runtime_user.ts", "src/type_user.ts"]

    without_type = blast_radius(g, "src/base.ts", include_type_only=False)
    assert len(without_type) == 1
    assert without_type[0]["file"] == "src/runtime_user.ts"


def test_dependencies_and_dependents() -> None:
    """Verify forward dependencies and direct dependents."""
    doc = _make_dummy_doc(
        nodes=["src/A.ts", "src/B.ts", "src/C.ts"],
        edges=[
            ("src/A.ts", "src/B.ts", "import", False, 1),
            ("src/B.ts", "src/C.ts", "import", False, 1),
        ],
    )
    g = to_digraph(doc)

    # A imports B (depth 1) and C (depth 2)
    deps_depth1 = dependencies(g, "src/A.ts", depth=1)
    assert deps_depth1 == [Impact(file="src/B.ts", depth=1, via="src/A.ts")]

    deps_depth2 = dependencies(g, "src/A.ts", depth=2)
    assert deps_depth2 == [
        Impact(file="src/B.ts", depth=1, via="src/A.ts"),
        Impact(file="src/C.ts", depth=2, via="src/B.ts"),
    ]

    # Direct dependents
    assert dependents(g, "src/C.ts") == ["src/B.ts"]
    assert dependents(g, "src/B.ts") == ["src/A.ts"]
    assert dependents(g, "src/A.ts") == []


def test_cycles_detection() -> None:
    """Verify cycles detection on circular graph, diamond graph, and self-loops."""
    # 1. Circular graph a -> b -> c -> a
    g_cycle = nx.DiGraph()
    g_cycle.add_edges_from(
        [
            ("src/a.ts", "src/b.ts"),
            ("src/b.ts", "src/c.ts"),
            ("src/c.ts", "src/a.ts"),
        ]
    )
    cycles = find_cycles(g_cycle)
    assert cycles == [["src/a.ts", "src/b.ts", "src/c.ts"]]

    # 2. No false positives on diamond
    g_diamond = nx.DiGraph()
    g_diamond.add_edges_from(
        [
            ("src/T.ts", "src/L.ts"),
            ("src/T.ts", "src/R.ts"),
            ("src/L.ts", "src/S.ts"),
            ("src/R.ts", "src/S.ts"),
        ]
    )
    assert find_cycles(g_diamond) == []

    # 3. Single self-loop node
    g_self = nx.DiGraph()
    g_self.add_edge("src/self.ts", "src/self.ts")
    assert find_cycles(g_self) == [["src/self.ts"]]


def test_degree_stats() -> None:
    """Verify degree_stats reports correct fan_in and fan_out."""
    doc = _make_dummy_doc(
        nodes=["src/S.ts", "src/T.ts"],
        edges=[
            ("src/T.ts", "src/S.ts", "import", False, 1),
        ],
    )
    g = to_digraph(doc)
    stats = degree_stats(g)

    assert stats["src/S.ts"] == {"fan_in": 1, "fan_out": 0}
    assert stats["src/T.ts"] == {"fan_in": 0, "fan_out": 1}


def test_unknown_node_raises_not_found() -> None:
    """Verify NodeNotFound is raised for non-existent files."""
    g = nx.DiGraph()
    g.add_node("src/known.ts")

    with pytest.raises(NodeNotFound):
        blast_radius(g, "src/unknown.ts")

    with pytest.raises(NodeNotFound):
        dependencies(g, "src/unknown.ts")

    with pytest.raises(NodeNotFound):
        dependents(g, "src/unknown.ts")
