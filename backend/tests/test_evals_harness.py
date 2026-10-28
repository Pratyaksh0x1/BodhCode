"""Unit tests for the evaluation harness itself."""

import json
from pathlib import Path
from unittest.mock import patch

from evals.run import run_all
from evals.suite_a import get_fixture_dir, run_suite_a


def test_suite_a_detects_altered_truth(tmp_path: Path):
    """Suite A must fail when a fixture's truth.json is deliberately altered."""
    # First verify Suite A currently passes
    clean_result = run_suite_a()
    assert clean_result["passed"] is True

    # Alter truth.json for repo1 in memory or via mock
    repo1_dir = get_fixture_dir("repo1_esm_aliases")
    truth_file = repo1_dir / "truth.json"
    original_truth = truth_file.read_text(encoding="utf-8")

    tampered_truth_dict = json.loads(original_truth)
    # Add a bogus edge that does not exist in the code
    tampered_truth_dict["edges"].append(
        {"source": "src/index.ts", "target": "src/ghost_file.ts", "kind": "import"}
    )

    with patch("evals.suite_a.load_truth", return_value=tampered_truth_dict):
        tampered_result = run_suite_a()
        assert tampered_result["passed"] is False
        assert tampered_result["metrics"]["edge_precision"] < 1.0 or tampered_result["metrics"][
            "edge_recall"
        ] < 1.0


def test_threshold_logic(tmp_path: Path):
    """Test that metric below threshold causes non-zero exit; at threshold exits zero."""
    strict_thresholds = {
        "edge_precision": 1.0,
        "edge_recall": 1.0,
        "exceptions_escaped": 0,
    }
    strict_file = tmp_path / "thresholds_pass.json"
    strict_file.write_text(json.dumps(strict_thresholds), encoding="utf-8")

    # Running suite A with matching thresholds should pass and exit 0
    exit_pass = run_all(suite_arg="A", upload=False, thresholds_path=str(strict_file))
    assert exit_pass == 0

    # Impossible threshold (e.g. edge_precision >= 1.5) must fail and exit 1
    impossible_thresholds = {
        "edge_precision": 1.5,
    }
    fail_file = tmp_path / "thresholds_fail.json"
    fail_file.write_text(json.dumps(impossible_thresholds), encoding="utf-8")

    exit_fail = run_all(suite_arg="A", upload=False, thresholds_path=str(fail_file))
    assert exit_fail == 1


def test_exceptions_escaped_threshold(tmp_path: Path):
    """Threshold for exceptions_escaped is 0; any escape causes failure."""
    thresholds = {"exceptions_escaped": 0}
    thresh_file = tmp_path / "thresholds_exc.json"
    thresh_file.write_text(json.dumps(thresholds), encoding="utf-8")

    # Mock Suite B to return 1 escaped exception
    mock_b_result = {
        "suite": "B",
        "passed": False,
        "metrics": {"exceptions_escaped": 1},
        "log": ["FAIL: Escaped exception"],
    }
    with patch("evals.run.run_suite_b", return_value=mock_b_result):
        exit_code = run_all(suite_arg="B", upload=False, thresholds_path=str(thresh_file))
        assert exit_code == 1
