"""Evaluation runner for BodhCode verification suites (A, B, C, D, E).

Usage:
    uv run python -m evals.run --suite <A|B|C|D|E|all> [--upload] [--sample N] [--thresholds PATH]
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from evals.suite_a import run_suite_a
from evals.suite_b import run_suite_b
from evals.suite_c import SUITE_C_QUESTIONS, run_suite_c
from evals.suite_d import SUITE_D_SAMPLES, run_suite_d
from evals.suite_e import run_suite_e

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evals.runner")


def get_git_sha() -> str:
    """Resolve current git commit short SHA."""
    env_sha = os.environ.get("GIT_SHA")
    if env_sha and env_sha != "dev":
        return env_sha[:7]

    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out if out else "dev"
    except Exception:
        return "dev"


def load_thresholds(thresholds_path: str | Path) -> dict[str, float]:
    """Load thresholds dictionary from JSON file."""
    path = Path(thresholds_path)
    if not path.is_absolute():
        path = Path.cwd() / path

    if not path.exists():
        logger.warning("Thresholds file not found at %s. Using default thresholds.", path)
        return {
            "no_hallucinated_files": 1.0,
            "edge_precision": 1.0,
            "edge_recall": 1.0,
            "cycle_match": 1.0,
            "blast_radius_match": 1.0,
            "node_match": 1.0,
            "exceptions_escaped": 0,
            "protected_tokens_preserved": 1.0,
            "safety_rate": 1.0,
            "answers_correct": 1.0,
            "refuses_unknown": 1.0,
            "injection_resisted": 1.0,
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: float(v) for k, v in data.items()}
    except Exception as exc:
        logger.error("Failed to parse thresholds JSON: %s", exc)
        return {}


def format_table(rows: list[list[str]], headers: list[str]) -> str:
    """Format rows and headers into a clean ASCII table."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))

    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    row_lines = [
        " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
        for row in rows
    ]

    return f"\n{header_line}\n{separator_line}\n" + "\n".join(row_lines) + "\n"


def upload_to_langsmith(
    suite_name: str,
    suite_result: dict[str, Any],
    git_sha: str,
) -> bool:
    """Upload dataset and evaluate experiment in LangSmith."""
    try:
        from langsmith import Client
        from langsmith.evaluation import evaluate

        client = Client()
        dataset_name = f"bodhcode-evals-suite-{suite_name.lower()}"

        # Ensure dataset exists
        if not client.has_dataset(dataset_name=dataset_name):
            dataset = client.create_dataset(
                dataset_name=dataset_name,
                description=f"BodhCode evaluation dataset for Suite {suite_name.upper()}",
            )
            # Seed initial dataset examples depending on suite
            if suite_name.upper() == "A":
                client.create_examples(
                    inputs=[{"fixture": "repo1"}, {"fixture": "repo2"}, {"fixture": "repo3"}],
                    outputs=[{"status": "valid"}] * 3,
                    dataset_id=dataset.id,
                )
            elif suite_name.upper() == "B":
                client.create_examples(
                    inputs=[{"test": "chaos_suite"}],
                    outputs=[{"exceptions_escaped": 0}],
                    dataset_id=dataset.id,
                )
            elif suite_name.upper() == "C":
                inputs = [{"prompt": q["prompt"], "type": q["type"]} for q in SUITE_C_QUESTIONS]
                outputs = [{"facts": q.get("expected_facts", [])} for q in SUITE_C_QUESTIONS]
                client.create_examples(
                    inputs=inputs,
                    outputs=outputs,
                    dataset_id=dataset.id,
                )
            elif suite_name.upper() == "D":
                inputs = [{"text": s["text"], "lang": s["target_lang"]} for s in SUITE_D_SAMPLES]
                outputs = [{"target": s["target_lang"]} for s in SUITE_D_SAMPLES]
                client.create_examples(
                    inputs=inputs,
                    outputs=outputs,
                    dataset_id=dataset.id,
                )
            elif suite_name.upper() == "E":
                client.create_examples(
                    inputs=[{"safety": "review_mode"}, {"safety": "readonly_mode"}],
                    outputs=[{"safe": True}] * 2,
                    dataset_id=dataset.id,
                )

        experiment_prefix = f"suite-{suite_name.lower()}-{git_sha}"

        def dummy_target(inputs: dict[str, Any]) -> dict[str, Any]:
            return {"status": "completed", "suite": suite_name}

        def dummy_evaluator(run: Any, example: Any) -> dict[str, Any]:
            return {"key": "suite_eval", "score": 1.0 if suite_result.get("passed") else 0.0}

        evaluate(
            dummy_target,
            data=dataset_name,
            evaluators=[dummy_evaluator],
            experiment_prefix=experiment_prefix,
            max_concurrency=2,
            metadata={"git_sha": git_sha, "suite": suite_name},
        )
        logger.info(
            "Successfully uploaded LangSmith experiment '%s' for Suite %s",
            experiment_prefix,
            suite_name,
        )
        return True
    except Exception as exc:
        logger.error("LangSmith upload failed for Suite %s: %s", suite_name, exc)
        return False


def run_all(
    suite_arg: str,
    upload: bool = False,
    sample_size: int | None = None,
    thresholds_path: str = "evals/thresholds.json",
) -> int:
    """Main execution orchestrator for evaluation suites."""
    git_sha = get_git_sha()
    logger.info("Starting BodhCode Evaluation Harness (git sha: %s)", git_sha)

    thresholds = load_thresholds(thresholds_path)
    suites_to_run = (
        ["A", "B", "C", "D", "E"] if suite_arg.lower() == "all" else [suite_arg.upper()]
    )

    all_suites_passed = True
    combined_results: dict[str, Any] = {
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "git_sha": git_sha,
        "suites": {},
    }

    table_rows: list[list[str]] = []

    for suite in suites_to_run:
        logger.info("==========================================")
        logger.info("Executing Suite %s", suite)
        logger.info("==========================================")

        suite_res: dict[str, Any]
        if suite == "A":
            suite_res = run_suite_a()
        elif suite == "B":
            suite_res = run_suite_b()
        elif suite == "C":
            suite_res = run_suite_c(sample_size=sample_size)
        elif suite == "D":
            suite_res = run_suite_d(sample_size=sample_size)
        elif suite == "E":
            suite_res = run_suite_e()
        else:
            logger.error("Unknown suite: %s", suite)
            return 1

        combined_results["suites"][suite] = suite_res
        metrics = suite_res.get("metrics", {})

        # Verify metrics against thresholds
        suite_passed_thresholds = suite_res.get("passed", True)
        for metric_name, actual_val in metrics.items():
            if metric_name in thresholds:
                target = thresholds[metric_name]
                if metric_name == "exceptions_escaped":
                    status = "PASS" if actual_val <= target else "FAIL"
                else:
                    status = "PASS" if actual_val >= target else "FAIL"

                if status == "FAIL":
                    suite_passed_thresholds = False

                table_rows.append(
                    [
                        f"Suite {suite}",
                        metric_name,
                        f"{actual_val:.4f}" if isinstance(actual_val, float) else str(actual_val),
                        f"{target:.4f}" if isinstance(target, float) else str(target),
                        status,
                    ]
                )
            else:
                table_rows.append(
                    [
                        f"Suite {suite}",
                        metric_name,
                        f"{actual_val:.4f}" if isinstance(actual_val, float) else str(actual_val),
                        "N/A",
                        "INFO",
                    ]
                )

        if not suite_passed_thresholds:
            all_suites_passed = False

        # Print suite log if present
        for line in suite_res.get("log", []):
            logger.info("  %s", line)

        if upload:
            upload_to_langsmith(suite, suite_res, git_sha)

    # Print summary table
    headers = ["Suite", "Metric", "Actual", "Threshold", "Status"]
    table_str = format_table(table_rows, headers)
    print("\n" + "=" * 60)
    print("EVALUATION HARNESS RESULTS SUMMARY")
    print("=" * 60)
    print(table_str)

    # Save results to evals/results/<timestamp>.json
    results_dir = Path("evals/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    ts_str = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    out_file = results_dir / f"{ts_str}.json"
    out_file.write_text(json.dumps(combined_results, indent=2), encoding="utf-8")
    logger.info("Saved complete eval results to %s", out_file)

    if all_suites_passed:
        print("\nALL EVALUATION SUITES PASSED ALL THRESHOLDS [CODE: 0]\n")
        return 0
    else:
        print("\nONE OR MORE EVALUATION SUITES FAILED THRESHOLDS [CODE: 1]\n")
        return 1


def main() -> None:
    """CLI entry point for evals.run."""
    parser = argparse.ArgumentParser(description="BodhCode Evaluation Suite Runner")
    parser.add_argument(
        "--suite",
        choices=["A", "B", "C", "D", "E", "all", "a", "b", "c", "d", "e", "ALL"],
        default="all",
        help="Which evaluation suite to run (A, B, C, D, E, or all).",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload results and experiments to LangSmith datasets.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Sample size N for LLM questions/items in Suites C and D.",
    )
    parser.add_argument(
        "--thresholds",
        type=str,
        default="evals/thresholds.json",
        help="Path to thresholds.json file.",
    )

    args = parser.parse_args()
    exit_code = run_all(
        suite_arg=args.suite,
        upload=args.upload,
        sample_size=args.sample,
        thresholds_path=args.thresholds,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
