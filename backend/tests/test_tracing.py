from unittest.mock import MagicMock, patch

from app.ai.tracing import flush_tracing, traced, update_current_llm_run


def test_traced_decorator_preserves_function() -> None:
    @traced(name="test_span", run_type="chain")
    def add(a: int, b: int) -> int:
        return a + b

    assert add(2, 3) == 5


def test_update_current_llm_run_no_active_tree() -> None:
    # When not inside a traceable context, run tree is None. Must not crash.
    with patch("app.ai.tracing.get_current_run_tree", return_value=None):
        update_current_llm_run(
            feature="test",
            model="mock-model",
            prompt_name="prompt_a",
            prompt_version=1,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )


def test_update_current_llm_run_with_active_tree() -> None:
    mock_tree = MagicMock()
    mock_tree.metadata = {}
    with patch("app.ai.tracing.get_current_run_tree", return_value=mock_tree):
        update_current_llm_run(
            feature="ping",
            model="mock-fast-model",
            prompt_name="ping",
            prompt_version=1,
            prompt_tokens=12,
            completion_tokens=4,
            total_tokens=16,
        )

    assert mock_tree.name == "groq.ping"
    assert mock_tree.add_metadata.called or "feature" in mock_tree.metadata


def test_update_current_llm_run_fail_open() -> None:
    mock_tree = MagicMock()
    mock_tree.add_metadata.side_effect = RuntimeError("LangSmith internal failure")
    with patch("app.ai.tracing.get_current_run_tree", return_value=mock_tree):
        # Must not raise RuntimeError
        update_current_llm_run(
            feature="fail_test",
            model="mock-model",
        )


def test_flush_tracing_disabled(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    with patch("langsmith.Client") as mock_client_cls:
        flush_tracing()
        mock_client_cls.assert_not_called()


def test_flush_tracing_enabled(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    mock_client = MagicMock()
    with patch("langsmith.Client", return_value=mock_client):
        flush_tracing()
        mock_client.flush.assert_called_once()


def test_flush_tracing_fail_open(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    with patch("langsmith.Client", side_effect=Exception("LangSmith connection failed")):
        # Must not crash
        flush_tracing()
