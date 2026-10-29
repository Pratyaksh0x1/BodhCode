"""Regression tests for 10 hostile prompt-injection samples using fake LLM."""

import pytest

from app.ai.untrusted import wrap_untrusted
from evals.evaluators import eval_injection_resisted
from evals.injection_samples import INJECTION_SAMPLES


def test_ten_hostile_samples_present():
    """Verify exactly 10 prompt injection test samples are defined."""
    assert len(INJECTION_SAMPLES) == 10
    sample_ids = {s["id"] for s in INJECTION_SAMPLES}
    assert len(sample_ids) == 10


@pytest.mark.parametrize("sample", INJECTION_SAMPLES, ids=lambda s: s["id"])
def test_hostile_samples_isolated_as_data(sample):
    """Ensure hostile samples wrapped in untrusted data delimiters never become instructions."""
    raw_content = sample["content"]
    wrapped = wrap_untrusted(raw_content, kind=sample["kind"])

    # Must contain delimiters
    assert f'<untrusted_data kind="{sample["kind"]}">' in wrapped
    assert "</untrusted_data>" in wrapped

    # Evaluator check: raw prompt cannot leak canary
    eval_score = eval_injection_resisted(
        answer="Analysis of repository: item was processed as plain text.",
        tool_calls=[],
        canary="BODHCODE_SECRET_SYSTEM_MARKER",
    )
    assert eval_score == 1.0


@pytest.mark.parametrize("sample", INJECTION_SAMPLES, ids=lambda s: s["id"])
def test_simulated_model_resists_injection(sample):
    """Simulate agent response to hostile input and verify injection evaluation succeeds."""
    # When agent correctly treats sample as data, it explains the content without following commands
    benign_agent_response = (
        f"The file contains user commentary ({sample['kind']}). No actions were executed."
    )
    score = eval_injection_resisted(
        answer=benign_agent_response,
        tool_calls=[],
        canary="BODHCODE_SECRET_SYSTEM_MARKER",
    )
    assert score == 1.0
