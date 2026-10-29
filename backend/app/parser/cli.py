"""Command-line interface for pure repository AST analysis and dependency graph generation."""

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.parser.analyze import analyze_repo_files
from app.parser.extract import extract_file
from app.parser.graph import RepoMeta, build_graph

IGNORED_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "dist",
        "build",
        ".next",
        ".turbo",
        ".venv",
        "__pycache__",
        ".pytest_cache",
    }
)


def analyze_directory(target_dir: Path | str) -> dict[str, Any]:
    """Analyze all files in a directory and return stats, breakdown, and GraphDoc."""
    dir_path = Path(target_dir).resolve()
    if not dir_path.exists() or not dir_path.is_dir():
        raise ValueError(f"Directory '{dir_path}' does not exist or is not a directory.")

    files: dict[str, bytes] = {}
    for p in dir_path.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(dir_path).parts
        if any(part in IGNORED_DIRS for part in rel_parts[:-1]):
            continue
        rel_posix = p.relative_to(dir_path).as_posix()
        try:
            files[rel_posix] = p.read_bytes()
        except Exception as err:
            sys.stderr.write(f"Warning: Failed to read file {rel_posix}: {err}\n")

    found_count = len(files)
    parsed_files: list[str] = []
    skipped_by_reason: dict[str, list[str]] = defaultdict(list)

    for path, source in sorted(files.items()):
        facts = extract_file(path, source)
        skip_flags = [f for f in facts.flags if f.startswith("skipped_")]
        if skip_flags:
            for flag in skip_flags:
                skipped_by_reason[flag].append(path)
        else:
            parsed_files.append(path)

    total_skipped = sum(len(items) for items in skipped_by_reason.values())
    parsed_count = len(parsed_files)

    analyzed = analyze_repo_files(files)
    repo_meta = RepoMeta(
        owner=dir_path.parent.name if dir_path.parent else "local",
        name=dir_path.name,
        commit_sha="local",
    )
    graph_doc = build_graph(analyzed, repo_meta)

    return {
        "stats": {
            "found": found_count,
            "parsed": parsed_count,
            "skipped": total_skipped,
        },
        "parsed_files": parsed_files,
        "skipped_by_reason": dict(skipped_by_reason),
        "graph": graph_doc,
        "files": files,
    }


def run_cli(args_list: list[str] | str | Path | None = None) -> int:
    """Execute parser CLI with given arguments."""
    parser = argparse.ArgumentParser(
        prog="python -m app.parser.cli",
        description="Extract AST facts and build deterministic dependency graph for a repository.",
    )
    parser.add_argument("dir", help="Path to repository root directory to analyze")
    parser.add_argument(
        "--out",
        "-o",
        dest="out",
        default=None,
        help="Optional path to output graph JSON file",
    )

    if isinstance(args_list, (str, Path)):
        args_list = [str(args_list)]

    args = parser.parse_args(args_list)
    target_dir = Path(args.dir).resolve()

    if not target_dir.exists() or not target_dir.is_dir():
        sys.stderr.write(f"Error: Directory '{target_dir}' does not exist or is not a directory.\n")
        return 1

    try:
        result = analyze_directory(target_dir)
    except Exception as err:
        sys.stderr.write(f"Error analyzing directory: {err}\n")
        return 1

    stats = result["stats"]
    print(f"found = parsed + skipped ({stats['found']} = {stats['parsed']} + {stats['skipped']})")

    skipped_by_reason = result["skipped_by_reason"]
    if skipped_by_reason:
        print("Skipped files breakdown:")
        for reason, paths in sorted(skipped_by_reason.items()):
            print(f"  [{reason}]: {len(paths)} file(s)")
            for sample in paths[:5]:
                print(f"    - {sample}")
            if len(paths) > 5:
                print(f"    ... and {len(paths) - 5} more")

    graph_doc = result["graph"]
    cov = graph_doc.coverage
    cov_str = f"{cov['percent']}%" if cov["percent"] is not None else "null"
    print(
        f"Coverage: {cov_str} "
        f"(internal_resolved: {cov['internal_resolved']}, unresolved: {cov['unresolved']})"
    )
    print(
        f"Graph stats: {graph_doc.stats.files} nodes, "
        f"{graph_doc.stats.edges} edges, "
        f"{graph_doc.stats.external_packages} packages, "
        f"{graph_doc.stats.cycles} cycles"
    )

    if args.out:
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(graph_doc.to_json(indent=2), encoding="utf-8")
        print(f"Wrote graph JSON to: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
