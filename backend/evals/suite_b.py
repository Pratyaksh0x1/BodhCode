"""Suite B: Parser robustness and chaos evaluation (no LLM, zero network)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.parser.analyze import analyze_repo_files
from app.parser.extract import extract_file

REPOS_DIR = Path(__file__).resolve().parent / "repos"


def generate_chaos_files() -> dict[str, bytes]:
    """Generate deterministic chaos test files covering extreme edge cases."""
    # 1. Broken syntax
    syntax_error_content = b"""
function brokenSyntax( {
    const x = === >>> ;;;
    (((([[]]{{{
    return undefined?::
"""

    # 2. Empty file
    empty_content = b""

    # 3. 1 MB generated TS file
    repeat_block = b"export const item_%d = %d;\nexport function get_%d(): number { return %d; }\n"
    blocks: list[bytes] = []
    current_size = 0
    target_size = 1_048_576  # 1 MB
    idx = 0
    while current_size < target_size:
        b_slice = repeat_block % (idx, idx, idx, idx)
        blocks.append(b_slice)
        current_size += len(b_slice)
        idx += 1
    one_mb_content = b"".join(blocks)

    # 4. Deeply nested expression (250 nested parentheses)
    nested_expr = b"(" * 250 + b"1" + b")" * 250
    deeply_nested_content = b"export const deep = " + nested_expr + b";\n"

    # 5. Odd encodings / special unicode / BOM
    odd_encoding_content = (
        b"\xef\xbb\xbf"  # UTF-8 BOM
        + b"// \xf0\x9f\x91\xa8\xe2\x80\x8d\xf0\x9f\x91\xa9\xe2\x80\x8d\xf0\x9f\x91\xa7 emoji\n"
        + b"export const \xc3\xa6_variable = 42;\n"
        + b"// Null \x00 bytes and control \x01\x02 characters\n"
        + b"export const msg = \"\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e "
        + b"\xe0\xa4\xb9\xe0\xa4\xbf\xe0\xa4\xa8\xe0\xa5\x8d\xe0\xa4\xa6\xe0\xa5\x80\";\n"
    )

    # 6. Unsupported binary file (should flag skipped_unsupported)
    unsupported_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"

    return {
        "chaos/syntax_error.ts": syntax_error_content,
        "chaos/empty_file.ts": empty_content,
        "chaos/large_file.ts": one_mb_content,
        "chaos/deeply_nested.ts": deeply_nested_content,
        "chaos/odd_encoding.ts": odd_encoding_content,
        "chaos/image.png": unsupported_content,
    }


def run_suite_b(repos_dir: Path = REPOS_DIR, max_per_file_ms: float = 5000.0) -> dict[str, Any]:
    """Execute Suite B over all fixture files and the generated chaos set.

    Asserts zero unhandled exceptions, correct flag assignment, and timing bounds.
    """
    total_files = 0
    exceptions_escaped = 0
    file_timings: dict[str, float] = {}
    flags_assigned: dict[str, tuple[str, ...]] = {}

    # 1. Gather all fixture files
    all_files: dict[str, bytes] = {}
    for repo_path in sorted(repos_dir.iterdir()):
        if not repo_path.is_dir():
            continue
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and file_path.name != "truth.json":
                rel = f"{repo_path.name}/{file_path.relative_to(repo_path).as_posix()}"
                all_files[rel] = file_path.read_bytes()

    # 2. Add chaos files
    chaos_files = generate_chaos_files()
    all_files.update(chaos_files)

    # 3. Process each file individually with timing
    for path, source in sorted(all_files.items()):
        total_files += 1
        start = time.perf_counter()
        try:
            facts = extract_file(path, source)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            file_timings[path] = round(elapsed_ms, 2)
            flags_assigned[path] = facts.flags

            if elapsed_ms > max_per_file_ms:
                exceptions_escaped += 1
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            file_timings[path] = round(elapsed_ms, 2)
            exceptions_escaped += 1

    # Verify expected chaos behaviors
    if "skipped_unsupported" not in flags_assigned.get("chaos/image.png", ()):
        exceptions_escaped += 1

    # 4. Also run whole repo analysis pipeline across all files
    try:
        analyze_repo_files(all_files)
    except Exception:
        exceptions_escaped += 1

    timings_list = list(file_timings.values())
    max_ms = max(timings_list) if timings_list else 0.0
    avg_ms = sum(timings_list) / len(timings_list) if timings_list else 0.0

    passed = (exceptions_escaped == 0)
    metrics = {
        "exceptions_escaped": exceptions_escaped,
        "total_files": total_files,
        "chaos_files": len(chaos_files),
        "max_parse_time_ms": round(max_ms, 2),
        "avg_parse_time_ms": round(avg_ms, 2),
    }

    return {
        "suite": "B",
        "passed": passed,
        "metrics": metrics,
        "timings": file_timings,
    }
