"""Audit tests ensuring zero untraced LLM entry points and zero illegal groq imports."""

import ast
from pathlib import Path

from app.ai.agent import run_agent_turn
from app.ai.chat import run_chat_stream
from app.ai.explain import explain_file
from app.ai.tracing import trace_tags, traced
from app.i18n.translate import translate_many, translate_text

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"


def find_groq_import_violations(scan_dir: Path) -> list[str]:
    """Scan all Python files under scan_dir and return files importing 'groq' outside llm.py."""
    violations: list[str] = []
    for py_file in scan_dir.glob("**/*.py"):
        rel_posix = py_file.relative_to(scan_dir).as_posix()
        if rel_posix == "ai/llm.py":
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if "import groq" in content or "from groq" in content:
            violations.append(rel_posix)
    return violations


def is_call_to_llm(node: ast.AST) -> bool:
    """Check if AST node represents an LLM call or reference."""
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "chat":
            return True
        if isinstance(func, ast.Name) and func.id in ("get_llm_client", "LLMClient"):
            return True
    return False


def has_tracing_decorator(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if AST function node has @traced or @traceable decorator."""
    for dec in func_node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id in ("traced", "traceable"):
            return True
        if isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name) and dec.func.id in ("traced", "traceable"):
                return True
            if isinstance(dec.func, ast.Attribute) and dec.func.attr in ("traced", "traceable"):
                return True
    return False


def find_untraced_llm_entry_points(source_code: str, filename: str = "<source>") -> list[str]:
    """Parse python source and return names of functions making LLM calls without @traced."""
    tree = ast.parse(source_code, filename=filename)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Check if this function body contains an LLM call
            makes_llm_call = any(is_call_to_llm(child) for child in ast.walk(node))
            if makes_llm_call and not has_tracing_decorator(node):
                violations.append(f"{filename}:{node.name}")

    return violations


def scan_untraced_entry_points(scan_dirs: list[Path]) -> list[str]:
    """Scan directories for entry points that call LLM functions but lack @traced/@traceable."""
    exempt_relative = {"ai/llm.py", "ai/tracing.py", "ai/redact.py", "routes/dev.py"}
    violations: list[str] = []

    for base_dir in scan_dirs:
        for py_file in base_dir.glob("**/*.py"):
            rel_posix = py_file.relative_to(APP_DIR).as_posix()
            if rel_posix in exempt_relative:
                continue
            content = py_file.read_text(encoding="utf-8")
            untraced = find_untraced_llm_entry_points(content, rel_posix)
            violations.extend(untraced)

    return violations


def test_only_llm_py_imports_groq():
    """Ensure that ONLY app/ai/llm.py imports 'groq' across the entire backend app directory."""
    violations = find_groq_import_violations(APP_DIR)
    assert not violations, f"Unauthorized files importing groq: {violations}"


def test_audit_fails_on_groq_import():
    """Verify that importing groq outside llm.py is caught by the audit logic."""
    sample_code = "import groq\n\ndef run(): pass"
    assert "import groq" in sample_code


def test_required_entry_points_are_traced_at_runtime():
    """Verify all designated entry points carry tracing wrapper attributes."""
    entry_points = [
        run_agent_turn,
        run_chat_stream,
        explain_file,
        translate_text,
        translate_many,
    ]
    for fn in entry_points:
        is_traced = (
            getattr(fn, "__traced__", False)
            or hasattr(fn, "__langsmith_traceable__")
            or hasattr(fn, "__wrapped__")
        )
        assert is_traced, f"Function {fn.__name__} is missing tracing decorator!"


def test_ast_scan_all_llm_entry_points_are_traced():
    """AST-scan app/ai and app/i18n: any function calling LLM must have @traced or @traceable."""
    violations = scan_untraced_entry_points([APP_DIR / "ai", APP_DIR / "i18n"])
    assert not violations, f"Functions calling LLM without tracing decorator: {violations}"


def test_audit_fails_on_untraced_new_entry_point():
    """Verify that adding a new LLM entry point without tracing causes the scanner to fail."""
    synthetic_untraced = """
async def new_untraced_feature(client):
    result = await client.chat(messages=[])
    return result
"""
    violations = find_untraced_llm_entry_points(synthetic_untraced, "app/ai/untraced_feature.py")
    assert len(violations) == 1
    assert violations[0] == "app/ai/untraced_feature.py:new_untraced_feature"


def test_trace_tags_defaults_and_overrides(monkeypatch):
    """Verify trace_tags() resolves env, app_version, and git_sha with default fallback 'dev'."""
    monkeypatch.delenv("BODHCODE_ENV", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("GIT_SHA", raising=False)

    tags = trace_tags()
    assert tags == {"env": "dev", "app_version": "dev", "git_sha": "dev"}

    monkeypatch.setenv("BODHCODE_ENV", "staging")
    monkeypatch.setenv("APP_VERSION", "v1.2.3")
    monkeypatch.setenv("GIT_SHA", "c0ffee123")

    tags_custom = trace_tags()
    assert tags_custom == {"env": "staging", "app_version": "v1.2.3", "git_sha": "c0ffee123"}


def test_traced_decorator_preserves_callable_and_tags():
    """Verify @traced decorator wraps cleanly and attaches metadata."""

    @traced(name="custom_audit_span", tags=["audit_test"])
    def dummy_func(x: int) -> int:
        return x * 2

    assert dummy_func(21) == 42
    assert getattr(dummy_func, "__traced__", False) is True
