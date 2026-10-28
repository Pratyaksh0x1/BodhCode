"""Suite A: Deterministic graph correctness evaluation against hand-crafted truth.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.parser.analyze import analyze_repo_files
from app.parser.blast import blast_radius, find_cycles, to_digraph
from app.parser.graph import RepoMeta, build_graph

REPOS_DIR = Path(__file__).resolve().parent / "repos"


def get_fixture_dir(repo_name: str) -> Path:
    """Return Path to a fixture repository by name."""
    return REPOS_DIR / repo_name


def load_truth(truth_path: Path) -> dict[str, Any]:
    """Load and parse truth.json dictionary."""
    return json.loads(truth_path.read_text(encoding="utf-8"))


def run_suite_a(repos_dir: Path = REPOS_DIR) -> dict[str, Any]:
    """Execute Suite A across all fixture repositories.

    Asserts 100% equality for nodes, edges (precision & recall = 1.0), cycles, and blast radius.
    Returns metrics dict and detailed per-repo reports.
    """
    repo_results: list[dict[str, Any]] = []
    total_expected_edges = 0
    total_actual_edges = 0
    total_matched_edges = 0
    total_repos = 0
    all_nodes_matched = True
    all_cycles_matched = True
    all_blast_matched = True

    diff_tables: list[str] = []

    for repo_path in sorted(repos_dir.iterdir()):
        if not repo_path.is_dir():
            continue
        truth_path = repo_path / "truth.json"
        if not truth_path.exists():
            continue

        total_repos += 1
        repo_name = repo_path.name
        truth = load_truth(truth_path)

        # Load repository files
        files: dict[str, bytes] = {}
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and file_path.name != "truth.json":
                rel = file_path.relative_to(repo_path).as_posix()
                files[rel] = file_path.read_bytes()

        # Parse graph
        analyzed = analyze_repo_files(files)
        doc = build_graph(analyzed, RepoMeta(owner="evals", name=repo_name, commit_sha="eval"))
        digraph = to_digraph(doc)

        # 1. Node equality
        actual_nodes = set(n.id for n in doc.nodes)
        expected_nodes = set(truth.get("nodes", []))
        nodes_ok = actual_nodes == expected_nodes
        if not nodes_ok:
            all_nodes_matched = False
            missing_nodes = expected_nodes - actual_nodes
            extra_nodes = actual_nodes - expected_nodes
            diff_tables.append(
                f"[{repo_name}] Nodes Mismatch:\n"
                f"  Missing: {sorted(missing_nodes)}\n"
                f"  Extra:   {sorted(extra_nodes)}"
            )

        # 2. Edge precision & recall
        actual_edges = set((e.source, e.target, e.kind) for e in doc.edges)
        expected_edges = set(
            (e["source"], e["target"], e["kind"]) for e in truth.get("edges", [])
        )
        matched_edges = actual_edges & expected_edges
        missing_edges = expected_edges - actual_edges
        extra_edges = actual_edges - expected_edges

        total_expected_edges += len(expected_edges)
        total_actual_edges += len(actual_edges)
        total_matched_edges += len(matched_edges)

        edges_ok = actual_edges == expected_edges
        if not edges_ok:
            missing_lines = "\n".join(
                f"    - {src} -> {tgt} ({kind})" for src, tgt, kind in sorted(missing_edges)
            )
            extra_lines = "\n".join(
                f"    + {src} -> {tgt} ({kind})" for src, tgt, kind in sorted(extra_edges)
            )
            diff_tables.append(
                f"[{repo_name}] Edges Diff Table:\n"
                f"  Missing Edges ({len(missing_edges)}):\n"
                f"{missing_lines}\n"
                f"  Extra Edges ({len(extra_edges)}):\n"
                f"{extra_lines}"
            )

        # 3. Cycle equality
        actual_cycles = find_cycles(digraph)
        expected_cycles = [sorted(c) for c in truth.get("cycles", [])]
        expected_cycles.sort(key=lambda c: c[0] if c else "")
        cycles_ok = actual_cycles == expected_cycles
        if not cycles_ok:
            all_cycles_matched = False
            diff_tables.append(
                f"[{repo_name}] Cycles Mismatch:\n"
                f"  Actual:   {actual_cycles}\n"
                f"  Expected: {expected_cycles}"
            )

        # 4. Blast radius equality
        blast_ok = True
        for target_file, exp_impacts in truth.get("blast_radius", {}).items():
            if target_file not in digraph:
                blast_ok = False
                all_blast_matched = False
                diff_tables.append(f"[{repo_name}] Blast file not in graph: {target_file}")
                continue
            raw_impacts = blast_radius(digraph, target_file)
            act_impacts = [{"file": imp["file"], "depth": imp["depth"]} for imp in raw_impacts]
            if act_impacts != exp_impacts:
                blast_ok = False
                all_blast_matched = False
                diff_tables.append(
                    f"[{repo_name}] Blast Radius Diff for {target_file}:\n"
                    f"  Actual:   {act_impacts}\n"
                    f"  Expected: {exp_impacts}"
                )

        repo_results.append(
            {
                "repo": repo_name,
                "nodes_ok": nodes_ok,
                "edges_ok": edges_ok,
                "cycles_ok": cycles_ok,
                "blast_ok": blast_ok,
                "nodes_count": len(actual_nodes),
                "edges_count": len(actual_edges),
            }
        )

    edge_precision = (
        total_matched_edges / total_actual_edges if total_actual_edges > 0 else 1.0
    )
    edge_recall = (
        total_matched_edges / total_expected_edges if total_expected_edges > 0 else 1.0
    )

    metrics = {
        "edge_precision": round(edge_precision, 4),
        "edge_recall": round(edge_recall, 4),
        "node_match": 1.0 if all_nodes_matched else 0.0,
        "cycle_match": 1.0 if all_cycles_matched else 0.0,
        "blast_radius_match": 1.0 if all_blast_matched else 0.0,
        "repos_evaluated": total_repos,
    }

    return {
        "suite": "A",
        "passed": (
            edge_precision == 1.0
            and edge_recall == 1.0
            and all_nodes_matched
            and all_cycles_matched
            and all_blast_matched
        ),
        "metrics": metrics,
        "repo_results": repo_results,
        "diff_output": "\n\n".join(diff_tables) if diff_tables else "All fixtures matched 100%.",
        "log": diff_tables,
    }
