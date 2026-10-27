"""Purity and determinism verification for app/parser/."""

import ast
from pathlib import Path

from app.parser.analyze import analyze_repo_files

PARSER_DIR = Path(__file__).resolve().parent.parent.parent / "app" / "parser"

FORBIDDEN_MODULES = {
    "httpx",
    "sqlmodel",
    "groq",
    "socket",
    "requests",
    "urllib",
    "alembic",
    "pydantic_settings",
    "app.db",
    "app.github",
    "app.ai",
}

FORBIDDEN_CALLS_OR_ATTRS = {
    "environ",
    "getenv",
}


def test_parser_purity_no_forbidden_imports_or_env() -> None:
    """Ensure no file in app/parser/ imports forbidden packages or accesses env vars."""
    py_files = list(PARSER_DIR.glob("*.py"))
    assert len(py_files) >= 5, "Expected parser files (extract, resolve, tsconfig, types, analyze)"

    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in FORBIDDEN_MODULES:
                        assert not alias.name.startswith(forbidden), (
                            f"Forbidden import '{alias.name}' in {py_file.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for forbidden in FORBIDDEN_MODULES:
                    assert not mod.startswith(forbidden), (
                        f"Forbidden from-import '{mod}' in {py_file.name}"
                    )
            elif isinstance(node, ast.Attribute):
                if node.attr in FORBIDDEN_CALLS_OR_ATTRS:
                    # Check if it's os.environ or os.getenv
                    if isinstance(node.value, ast.Name) and node.value.id == "os":
                        raise AssertionError(
                            f"Forbidden env access 'os.{node.attr}' in {py_file.name}"
                        )


def test_analyze_repo_files_is_deterministic() -> None:
    """Ensure repeated runs produce 100% identical outputs."""
    files = {
        "src/z.ts": b'import { a } from "./a"; export const z = 1;',
        "src/a.ts": b'import { b } from "./b"; export const a = 2;',
        "src/b.ts": b"export const b = 3;",
        "tsconfig.json": b'{"compilerOptions": {"baseUrl": "."}}',
    }

    run1 = analyze_repo_files(files)
    run2 = analyze_repo_files(files)
    run3 = analyze_repo_files(files)

    assert run1 == run2 == run3
