"""LangSmith tracing integration with zero-trust redaction and fail-open resilience."""

import logging
import os
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree

from app.ai.redact import redact

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def traced(
    name: str | None = None,
    run_type: str = "chain",
    metadata: dict[str, Any] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to trace high-level workflow spans (parent runs for chains/agents/jobs).

    Automatically redacts secrets from inputs and outputs and nests child runs.
    Fails open if LangSmith encounters errors.
    """

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        try:
            traced_fn = traceable(
                name=name,
                run_type=run_type,
                metadata=metadata,
                process_inputs=redact,
                process_outputs=redact,
            )(fn)
            return traced_fn
        except Exception as exc:
            logger.warning(
                "Failed to initialize LangSmith traceable decorator: %s", redact(str(exc))
            )
            return fn

    return decorator


def update_current_llm_run(
    *,
    feature: str,
    model: str,
    prompt_name: str | None = None,
    prompt_version: int | None = None,
    usage: Any = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
) -> None:
    """Attach feature metadata, model info, and token usage to current LangSmith LLM span."""
    if usage is not None:
        prompt_tokens = getattr(usage, "prompt_tokens", prompt_tokens)
        completion_tokens = getattr(usage, "completion_tokens", completion_tokens)
        total_tokens = getattr(usage, "total_tokens", total_tokens)
    try:
        run_tree = get_current_run_tree()
        if run_tree is None:
            return

        run_tree.name = f"groq.{feature}"
        run_metadata: dict[str, Any] = {
            "feature": feature,
            "model": model,
            "prompt_name": prompt_name,
            "prompt_version": prompt_version,
            "ls_provider": "groq",
            "ls_model_name": model,
            "usage_metadata": {
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        }
        if hasattr(run_tree, "add_metadata"):
            run_tree.add_metadata(run_metadata)
        elif hasattr(run_tree, "metadata") and isinstance(run_tree.metadata, dict):
            run_tree.metadata.update(run_metadata)
    except Exception as exc:
        logger.warning("Failed to attach metadata to LangSmith run: %s", redact(str(exc)))


def flush_tracing() -> None:
    """Flush pending LangSmith traces on application shutdown with fail-open guarantee."""
    if os.environ.get("LANGSMITH_TRACING", "").lower() not in ("true", "1"):
        return

    try:
        from langsmith import Client

        client = Client()
        if hasattr(client, "flush"):
            client.flush()
    except Exception as exc:
        logger.warning("Error during LangSmith trace flush: %s", redact(str(exc)))
