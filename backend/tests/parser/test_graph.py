"""Golden and property tests for dependency graph schema and builder."""

import json
import random
from pathlib import Path

import pytest

from app.parser.analyze import analyze_repo_files
from app.parser.blast import blast_radius, to_digraph
from app.parser.graph import (
    MAX_GRAPH_NODES,
    GraphDoc,
    GraphTooLargeError,
    RepoMeta,
    build_graph,
)
from app.parser.types import AnalyzedFile, FileFacts

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _load_raw_fixture_files(fixture_name: str) -> dict[str, bytes]:
    fixture_path = FIXTURES_DIR / fixture_name
    files: dict[str, bytes] = {}
    for p in fixture_path.rglob("*"):
        if p.is_file() and p.name not in ("expected.json", "expected_graph.json"):
            rel_posix = p.relative_to(fixture_path).as_posix()
            files[rel_posix] = p.read_bytes()
    return files


def test_build_graph_determinism() -> None:
    """Verify building twice or shuffling input order produces 100% identical JSON bytes."""
    files = _load_raw_fixture_files("basic_imports")
    analyzed = analyze_repo_files(files)
    meta = RepoMeta(owner="bodh", name="code", commit_sha="1234567890abcdef")

    doc1 = build_graph(analyzed, meta)
    doc2 = build_graph(analyzed, meta)
    assert doc1.to_json() == doc2.to_json()

    # Shuffled input order
    shuffled_analyzed = list(analyzed)
    random.seed(42)
    random.shuffle(shuffled_analyzed)
    doc_shuffled = build_graph(shuffled_analyzed, meta)
    assert doc1.to_json() == doc_shuffled.to_json()


def test_graph_serialization_roundtrip() -> None:
    """Verify GraphDoc serialization to_dict / to_json and from_dict / from_json."""
    files = _load_raw_fixture_files("basic_imports")
    analyzed = analyze_repo_files(files)
    meta = RepoMeta(owner="bodh", name="code", commit_sha="1234567890abcdef")

    doc = build_graph(analyzed, meta)
    json_str = doc.to_json()

    restored = GraphDoc.from_json(json_str)
    assert restored == doc
    assert restored.to_dict() == json.loads(json_str)


def test_barrel_reexport_blast_radius() -> None:
    """Verify barrel fixture correctly links consumers to re-exported files."""
    files = _load_raw_fixture_files("barrel")
    analyzed = analyze_repo_files(files)
    meta = RepoMeta(owner="bodh", name="barrel", commit_sha="barrel123")

    doc = build_graph(analyzed, meta)
    g = to_digraph(doc)

    # When src/components/Button.ts changes:
    # src/components/index.ts imports (re-exports) it at depth 1
    # src/app.ts imports src/components/index.ts at depth 2
    impacts = blast_radius(g, "src/components/Button.ts")
    assert len(impacts) == 2
    assert impacts[0]["file"] == "src/components/index.ts"
    assert impacts[0]["depth"] == 1
    assert impacts[0]["via"] == "src/components/Button.ts"

    assert impacts[1]["file"] == "src/app.ts"
    assert impacts[1]["depth"] == 2
    assert impacts[1]["via"] == "src/components/index.ts"


def test_cycle_fixture_detection() -> None:
    """Verify cycle fixture detects circular dependency a -> b -> c -> a."""
    files = _load_raw_fixture_files("cycle")
    analyzed = analyze_repo_files(files)
    meta = RepoMeta(owner="bodh", name="cycle", commit_sha="cycle123")

    doc = build_graph(analyzed, meta)
    assert doc.stats.cycles == 1
    assert doc.stats.files == 3
    assert doc.stats.edges == 3


def test_graph_limits_exceeded() -> None:
    """Verify GraphTooLargeError when nodes > 5000 or edges > 20000."""
    meta = RepoMeta(owner="test", name="large", commit_sha="large123")

    # Exceed nodes
    fake_nodes = [
        AnalyzedFile(
            path=f"src/file_{i}.ts",
            facts=FileFacts(
                path=f"src/file_{i}.ts",
                imports=(),
                exports=(),
                has_default_export=False,
                unresolved_dynamic=0,
                flags=(),
            ),
            resolved_imports=(),
            size=10,
        )
        for i in range(MAX_GRAPH_NODES + 1)
    ]
    with pytest.raises(GraphTooLargeError):
        build_graph(fake_nodes, meta)


def test_basic_imports_golden_schema() -> None:
    """Verify basic_imports produces expected graph structure and values."""
    files = _load_raw_fixture_files("basic_imports")
    analyzed = analyze_repo_files(files)
    meta = RepoMeta(owner="test", name="basic", commit_sha="basic123")

    doc = build_graph(analyzed, meta)
    data = doc.to_dict()

    assert data["version"] == 1
    assert data["repo"] == {"owner": "test", "name": "basic", "commit_sha": "basic123"}
    assert data["stats"]["files"] == 3
    assert data["stats"]["edges"] == 3
    assert data["stats"]["cycles"] == 0

    # Folders check
    assert len(data["folders"]) == 1
    assert data["folders"][0] == {"id": "src", "parent": "", "file_count": 3}

    # Edges check: index.ts imports dep.ts (both runtime and type_only) and side-effect.ts
    edge_ids = [e["id"] for e in data["edges"]]
    assert "src/index.ts>src/dep.ts#import" in edge_ids
    assert "src/index.ts>src/dep.ts#import:type" in edge_ids
    assert "src/index.ts>src/side-effect.ts#import" in edge_ids
