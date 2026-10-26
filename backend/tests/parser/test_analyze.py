"""Integration tests for analyze_repo_files against fixtures 1 to 9."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.parser.analyze import analyze_repo_files
from app.parser.types import AnalyzedFile

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

FIXTURE_NAMES = [
    "basic_imports",
    "reexports",
    "dynamic_and_require",
    "aliases",
    "esm_extensions",
    "index_files",
    "externals",
    "monorepo",
    "broken_syntax",
]


def _analyzed_file_to_dict(af: AnalyzedFile) -> dict[str, Any]:
    return {
        "path": af.path,
        "facts": {
            "path": af.facts.path,
            "imports": [
                {
                    "specifier": imp.specifier,
                    "kind": imp.kind,
                    "line": imp.line,
                    "type_only": imp.type_only,
                }
                for imp in af.facts.imports
            ],
            "exports": list(af.facts.exports),
            "has_default_export": af.facts.has_default_export,
            "unresolved_dynamic": af.facts.unresolved_dynamic,
            "flags": list(af.facts.flags),
        },
        "resolved_imports": [
            {
                "ref": {
                    "specifier": ri.ref.specifier,
                    "kind": ri.ref.kind,
                    "line": ri.ref.line,
                    "type_only": ri.ref.type_only,
                },
                "resolution": {
                    "kind": ri.resolution.kind,
                    "target": ri.resolution.target,
                    "package": ri.resolution.package,
                },
            }
            for ri in af.resolved_imports
        ],
    }


def _load_fixture_files(fixture_path: Path) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    files: dict[str, bytes] = {}
    expected_data: list[dict[str, Any]] = []

    for file_path in fixture_path.rglob("*"):
        if file_path.is_file():
            rel_posix = file_path.relative_to(fixture_path).as_posix()
            if rel_posix == "expected.json":
                expected_data = json.loads(file_path.read_text(encoding="utf-8"))
            else:
                files[rel_posix] = file_path.read_bytes()

    return files, expected_data


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_fixtures_end_to_end(fixture_name: str) -> None:
    fixture_path = FIXTURES_DIR / fixture_name
    assert fixture_path.exists(), f"Missing fixture directory {fixture_path}"

    files, expected = _load_fixture_files(fixture_path)
    analyzed = analyze_repo_files(files)
    actual = [_analyzed_file_to_dict(af) for af in analyzed]

    assert actual == expected


def test_real_repo_spot_check() -> None:
    """Spot check real TypeScript source files from frontend codebase (Acceptance item 8)."""
    frontend_dir = Path(__file__).resolve().parent.parent.parent.parent / "frontend"
    src_dir = frontend_dir / "src"
    assert src_dir.exists(), "frontend/src must exist"

    sample_paths = [
        "src/App.tsx",
        "src/components/Layout.tsx",
        "src/components/RequireAuth.tsx",
        "src/lib/auth.ts",
        "src/lib/env.ts",
    ]
    files: dict[str, bytes] = {}
    for rel_path in sample_paths:
        p = frontend_dir / rel_path
        if p.exists():
            files[rel_path] = p.read_bytes()

    results = analyze_repo_files(files)
    assert len(results) >= 4

    results_by_path = {r.path: r for r in results}

    # 1. App.tsx
    app_res = results_by_path.get("src/App.tsx")
    assert app_res is not None
    assert app_res.facts.has_default_export is True
    assert "App" in app_res.facts.exports
    layout_imp = next(
        (ri for ri in app_res.resolved_imports if ri.ref.specifier == "./components/Layout"),
        None,
    )
    assert layout_imp is not None
    assert layout_imp.resolution.kind == "file"
    assert layout_imp.resolution.target == "src/components/Layout.tsx"

    # 2. Layout.tsx
    layout_res = results_by_path.get("src/components/Layout.tsx")
    assert layout_res is not None
    assert "Layout" in layout_res.facts.exports
    auth_imp = next(
        (ri for ri in layout_res.resolved_imports if ri.ref.specifier == "../lib/auth"),
        None,
    )
    assert auth_imp is not None
    assert auth_imp.resolution.kind == "file"
    assert auth_imp.resolution.target == "src/lib/auth.ts"

    # 3. RequireAuth.tsx
    require_auth_res = results_by_path.get("src/components/RequireAuth.tsx")
    assert require_auth_res is not None
    auth_imp2 = next(
        (ri for ri in require_auth_res.resolved_imports if ri.ref.specifier == "../lib/auth"),
        None,
    )
    assert auth_imp2 is not None
    assert auth_imp2.resolution.kind == "file"
    assert auth_imp2.resolution.target == "src/lib/auth.ts"
