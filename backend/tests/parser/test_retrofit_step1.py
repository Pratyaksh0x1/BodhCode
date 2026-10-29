"""Tests for BodhCode Retrofit Step 1: Parser coverage, accounting, CLI, hashes, CommonJS."""

from pathlib import Path

import networkx as nx

from app.parser.analyze import analyze_repo_files
from app.parser.blast import blast_radius, dependencies, walk
from app.parser.cli import analyze_directory
from app.parser.extract import extract_file
from app.parser.graph import (
    RepoMeta,
    build_graph,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _load_raw_fixture_files(fixture_name: str) -> dict[str, bytes]:
    fixture_path = FIXTURES_DIR / fixture_name
    files: dict[str, bytes] = {}
    for p in fixture_path.rglob("*"):
        if p.is_file() and p.name != "expected.json":
            rel_path = p.relative_to(fixture_path).as_posix()
            files[rel_path] = p.read_bytes()
    return files


def test_commonjs_exports_extraction() -> None:
    """Verify extraction of module.exports = ..., module.exports.x = ..., and exports.x = ..."""
    # 1. module.exports = { a, b: fn, c: 1 }
    cjs_obj = b"""
    const a = 1;
    function fn() {}
    module.exports = {
        a,
        b: fn,
        c: 2
    };
    """
    facts1 = extract_file("index.cjs", cjs_obj)
    assert facts1.has_default_export is True
    assert set(facts1.exports) == {"a", "b", "c"}

    # 2. module.exports = function myHandler() {}
    cjs_fn = b"""
    module.exports = function myHandler() { return true; };
    """
    facts2 = extract_file("handler.js", cjs_fn)
    assert facts2.has_default_export is True
    assert "myHandler" in facts2.exports

    # 3. module.exports = class AppServer {}
    cjs_class = b"""
    module.exports = class AppServer {};
    """
    facts3 = extract_file("server.cjs", cjs_class)
    assert facts3.has_default_export is True
    assert "AppServer" in facts3.exports

    # 4. module.exports = () => {}
    cjs_arrow = b"""
    module.exports = () => { return 42; };
    """
    facts4 = extract_file("arrow.js", cjs_arrow)
    assert facts4.has_default_export is True

    # 5. module.exports.api = handler; exports.util = helper;
    cjs_props = b"""
    module.exports.api = function() {};
    exports.util = 123;
    exports.helpers = {};
    """
    facts5 = extract_file("props.js", cjs_props)
    assert set(facts5.exports) == {"api", "util", "helpers"}


def test_accounting_found_parsed_skipped(tmp_path: Path) -> None:
    """Verify found = parsed + skipped accounting and skip reason tracking."""
    # Create test directory with 2 valid TS files, 1 unsupported, 1 json
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("export const a = 1;")
    (tmp_path / "src" / "b.ts").write_text("import { a } from './a';")
    (tmp_path / "README.md").write_text("# Readme")
    (tmp_path / "package.json").write_text("{}")

    cli_out = analyze_directory(tmp_path)
    assert cli_out["stats"]["found"] == 4
    assert cli_out["stats"]["parsed"] == 2
    assert cli_out["stats"]["skipped"] == 2
    assert cli_out["stats"]["found"] == cli_out["stats"]["parsed"] + cli_out["stats"]["skipped"]

    skip_reasons = cli_out["skipped_by_reason"]
    assert "skipped_unsupported" in skip_reasons
    assert len(skip_reasons["skipped_unsupported"]) == 2


def test_single_imported_file_rename_unresolved_with_reason() -> None:
    """Renaming an imported file results in unresolved imports with reason='file_not_found'."""
    files = {
        "src/index.ts": b"import { dep } from './dep'; export const main = () => dep();",
        "src/other.ts": b"export const other = 123;",
    }
    analyzed = analyze_repo_files(files)
    index_file = next(af for af in analyzed if af.path == "src/index.ts")

    assert len(index_file.resolved_imports) == 1
    ri = index_file.resolved_imports[0]
    assert ri.resolution.kind == "unresolved"
    assert ri.resolution.reason == "file_not_found"

    doc = build_graph(analyzed, RepoMeta(owner="test", name="rename", commit_sha="abc"))
    data = doc.to_dict()
    assert data["stats"]["unresolved"] == 1
    assert data["coverage"]["unresolved"] == 1
    assert data["coverage"]["internal_resolved"] == 0
    # 0 / (0 + 1) = 0.0%
    assert data["coverage"]["percent"] == 0.0


def test_coverage_calculation_rules() -> None:
    """Coverage: internal_resolved / (internal_resolved + unresolved); null when denom is 0."""
    # 1. Zero-import repo -> coverage percent is None (null in JSON), NOT "100%"
    files_zero = {
        "src/a.ts": b"export const a = 1;",
        "src/b.ts": b"export const b = 2;",
    }
    analyzed_zero = analyze_repo_files(files_zero)
    doc_zero = build_graph(analyzed_zero, RepoMeta(owner="test", name="zero", commit_sha="zero1"))
    dict_zero = doc_zero.to_dict()
    assert dict_zero["coverage"]["internal_resolved"] == 0
    assert dict_zero["coverage"]["unresolved"] == 0
    assert dict_zero["coverage"]["percent"] is None

    # 2. Repo with only external dependencies (e.g. react) -> denominator is 0 -> percent is None
    files_ext = {
        "src/app.ts": b"import React from 'react'; export const app = React.version;",
    }
    analyzed_ext = analyze_repo_files(files_ext)
    doc_ext = build_graph(analyzed_ext, RepoMeta(owner="test", name="ext", commit_sha="ext1"))
    dict_ext = doc_ext.to_dict()
    assert dict_ext["coverage"]["internal_resolved"] == 0
    assert dict_ext["coverage"]["unresolved"] == 0
    assert dict_ext["coverage"]["percent"] is None

    # 3. Repo with 1 internal resolved and 1 unresolved -> 50.0%
    files_half = {
        "src/main.ts": b"import { a } from './a'; import { missing } from './missing';",
        "src/a.ts": b"export const a = 1;",
    }
    analyzed_half = analyze_repo_files(files_half)
    doc_half = build_graph(analyzed_half, RepoMeta(owner="test", name="half", commit_sha="half1"))
    dict_half = doc_half.to_dict()
    assert dict_half["coverage"]["internal_resolved"] == 1
    assert dict_half["coverage"]["unresolved"] == 1
    assert dict_half["coverage"]["percent"] == 50.0


def test_walk_unified_and_thin_wrappers() -> None:
    """Verify walk function and thin wrappers blast_radius and dependencies."""
    g = nx.DiGraph()
    # A -> B -> C -> D
    g.add_edge("A", "B", kind="import", type_only=False, symbols=[])
    g.add_edge("B", "C", kind="import", type_only=False, symbols=[])
    g.add_edge("C", "D", kind="import", type_only=False, symbols=[])

    # Upstream (blast radius) from D:
    # In BodhCode graph, edge is source -> target (importer -> imported).
    # Blast radius of D: who imports D? (reverse edges)
    # blast_radius(D, depth=2) should find C (depth 1) and B (depth 2).
    br_walk = walk(g, "D", direction="upstream", depth=2)
    br_wrapper = blast_radius(g, "D", max_depth=2)
    assert br_walk == br_wrapper
    assert {i["file"] for i in br_walk} == {"C", "B"}
    assert max(i["depth"] for i in br_walk) == 2

    # Downstream (dependencies) from A:
    # Who does A import? (forward edges)
    # dependencies(A, depth=2) should find B (depth 1) and C (depth 2).
    dep_walk = walk(g, "A", direction="downstream", depth=2)
    dep_wrapper = dependencies(g, "A", depth=2)
    assert dep_walk == dep_wrapper
    assert {i["file"] for i in dep_walk} == {"B", "C"}
    assert max(i["depth"] for i in dep_walk) == 2

    # Unlimited depth (max_depth=None)
    all_deps = dependencies(g, "A", depth=None)
    assert {i["file"] for i in all_deps} == {"B", "C", "D"}
    assert max(i["depth"] for i in all_deps) == 3

    # Default depth = 2
    default_deps = dependencies(g, "A")
    assert {i["file"] for i in default_deps} == {"B", "C"}
    assert max(i["depth"] for i in default_deps) == 2


def test_golden_edge_list_byte_identical() -> None:
    """Verify that edge list for existing fixtures stays byte-identical and additive."""
    files = _load_raw_fixture_files("basic_imports")
    analyzed = analyze_repo_files(files)
    doc = build_graph(analyzed, RepoMeta(owner="test", name="basic", commit_sha="basic123"))
    data = doc.to_dict()

    # The exact canonical edges
    expected_edges = [
        {
            "id": "src/index.ts>src/dep.ts#import",
            "source": "src/index.ts",
            "target": "src/dep.ts",
            "kind": "import",
            "type_only": False,
            "count": 3,
        },
        {
            "id": "src/index.ts>src/dep.ts#import:type",
            "source": "src/index.ts",
            "target": "src/dep.ts",
            "kind": "import",
            "type_only": True,
            "count": 2,
        },
        {
            "id": "src/index.ts>src/side-effect.ts#import",
            "source": "src/index.ts",
            "target": "src/side-effect.ts",
            "kind": "import",
            "type_only": False,
            "count": 1,
        },
    ]

    assert data["edges"] == expected_edges

    # Check node additions: loc, content_hash are present and valid
    for node in data["nodes"]:
        assert isinstance(node["loc"], int)
        assert node["loc"] >= 1
        assert isinstance(node["content_hash"], str)
        assert len(node["content_hash"]) == 64  # sha256 hex


def test_reanalyze_all_script_structure() -> None:
    """Verify reanalyze_all script module imports and CLI interface."""
    from app.scripts.reanalyze_all import main, reanalyze_all

    assert callable(main)
    assert callable(reanalyze_all)
