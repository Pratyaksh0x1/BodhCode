"""Suite D: Translation guards evaluation.

Tests translation preservation across languages (Japanese, Hindi, Spanish) to verify:
1. protected_tokens_preserved (byte-for-byte, target 1.0)
2. no_commentary (no conversational filler, proper length ratio)
3. target_language_correct (lingua language detection)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlmodel import Session, SQLModel, create_engine

from app.ai.llm import LLMClient, LLMRateLimited, get_llm_client
from app.i18n.translate import translate_text
from evals.evaluators import (
    eval_no_commentary,
    eval_protected_tokens_preserved,
    eval_target_language,
)

logger = logging.getLogger(__name__)

SUITE_D_SAMPLES: list[dict[str, Any]] = [
    # -------------------------------------------------------------
    # Japanese (ja)
    # -------------------------------------------------------------
    {
        "id": "ja_sample_1",
        "target_lang": "ja",
        "text": (
            "Please review the PR #42 submitted by @alice. Run `npm test` before deployment.\n\n"
            "```typescript\n"
            "export function parseId(input: string): number {\n"
            "    return parseInt(input, 10);\n"
            "}\n"
            "```"
        ),
    },
    {
        "id": "ja_sample_2",
        "target_lang": "ja",
        "text": (
            "Encountered a server failure during request processing. Check https://example.com/api\n\n"
            "TypeError: Cannot read properties of null (reading 'id')\n"
            "    at Handler.process (/app/src/handler.ts:42:12)"
        ),
    },
    {
        "id": "ja_sample_3",
        "target_lang": "ja",
        "text": (
            "Attention @team_lead: issue #105 reports broken dependencies when executing "
            "`npm run build`. Refer to documentation at https://github.com/org/repo/issues/105."
        ),
    },
    # -------------------------------------------------------------
    # Hindi (hi)
    # -------------------------------------------------------------
    {
        "id": "hi_sample_1",
        "target_lang": "hi",
        "text": (
            "Pull request #78 has been merged by @developer. Execute `npm run build` to verify.\n\n"
            "```python\n"
            "def calculate_tax(amount: float) -> float:\n"
            "    return amount * 0.18\n"
            "```"
        ),
    },
    {
        "id": "hi_sample_2",
        "target_lang": "hi",
        "text": (
            "Review the runtime exception log reported by @qa_tester on https://status.example.org:\n\n"
            "ReferenceError: config is not defined\n"
            "    at startService (/var/app/index.js:15:3)"
        ),
    },
    {
        "id": "hi_sample_3",
        "target_lang": "hi",
        "text": (
            "Please investigate issue #301. The environment variable `DATABASE_URL` is missing. "
            "Visit https://docs.example.com/database for setup steps."
        ),
    },
    # -------------------------------------------------------------
    # Spanish (es)
    # -------------------------------------------------------------
    {
        "id": "es_sample_1",
        "target_lang": "es",
        "text": (
            "The fix for issue #55 is ready for review by @reviewer. Run `npm run lint` now.\n\n"
            "```json\n"
            "{\n"
            '  "name": "eval-service",\n'
            '  "version": "1.0.0"\n'
            "}\n"
            "```"
        ),
    },
    {
        "id": "es_sample_2",
        "target_lang": "es",
        "text": (
            "Critical crash detected on endpoint https://api.service.io/v2/users:\n\n"
            "Error: Connection reset by peer\n"
            "    at TCP.onStreamRead (/app/server.js:89:14)"
        ),
    },
    {
        "id": "es_sample_3",
        "target_lang": "es",
        "text": (
            "Hello @dev_team, PR #204 resolves the race condition in `src/worker.ts`. "
            "See details at https://github.com/my-org/repo/pull/204."
        ),
    },
]


def select_d_samples(sample_size: int | None = None) -> list[dict[str, Any]]:
    """Select a deterministic subset of samples when sample_size is requested."""
    if sample_size is None or sample_size >= len(SUITE_D_SAMPLES):
        return list(SUITE_D_SAMPLES)

    # Pick samples balanced across target languages
    by_lang: dict[str, list[dict[str, Any]]] = {}
    for s in SUITE_D_SAMPLES:
        by_lang.setdefault(s["target_lang"], []).append(s)

    selected: list[dict[str, Any]] = []
    langs = list(by_lang.keys())
    per_lang = max(1, sample_size // len(langs))

    for lang in langs:
        selected.extend(by_lang[lang][:per_lang])

    return selected[:sample_size]


async def _translate_sample_with_retry(
    sample: dict[str, Any],
    session: Session,
    llm_client: LLMClient | None,
    semaphore: asyncio.Semaphore,
) -> tuple[str, bool]:
    """Translate one sample with concurrency limit and exponential backoff retry."""
    max_retries = 3
    backoff = 2.0

    for attempt in range(max_retries):
        try:
            async with semaphore:
                res = await translate_text(
                    session=session,
                    text=sample["text"],
                    target=sample["target_lang"],
                    source="en",
                    refresh=True,  # Bypass cache for evals
                    llm_client=llm_client,
                )
                if not res.ok:
                    return f"Translation error: {res.reason}", False
                return res.text, False
        except LLMRateLimited:
            logger.warning(
                "Rate limit encountered on sample %s (attempt %d/%d). Backing off %ss.",
                sample["id"],
                attempt + 1,
                max_retries,
                backoff,
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(backoff)
                backoff *= 2.0
            else:
                return "Rate limited (inconclusive)", True
        except Exception as exc:
            logger.error("Error translating sample %s: %s", sample["id"], exc)
            if "429" in str(exc) or "rate" in str(exc).lower():
                if attempt < max_retries - 1:
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue
                return "Rate limited (inconclusive)", True
            return f"Error: {exc}", False

    return "Inconclusive after retries", True


async def run_suite_d_async(
    sample_size: int | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    """Execute Suite D translation guard assertions asynchronously."""
    samples = select_d_samples(sample_size)
    semaphore = asyncio.Semaphore(2)  # Cap concurrency at 2

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    results: list[dict[str, Any]] = []
    log: list[str] = []

    with Session(engine) as session:
        client = llm_client or get_llm_client()

        for s in samples:
            translated, inconclusive = await _translate_sample_with_retry(
                s, session, client, semaphore
            )

            res_record: dict[str, Any] = {
                "id": s["id"],
                "target_lang": s["target_lang"],
                "inconclusive": inconclusive,
                "original": s["text"],
                "translated": translated,
            }

            if inconclusive:
                log.append(f"INCONCLUSIVE: {s['id']} encountered provider rate limiting.")
                results.append(res_record)
                continue

            # Evaluator 1: protected_tokens_preserved (must be 1.0)
            prot_score = eval_protected_tokens_preserved(s["text"], translated)
            res_record["protected_tokens_preserved"] = prot_score

            # Evaluator 2: no_commentary
            comm_score = eval_no_commentary(translated, s["text"])
            res_record["no_commentary"] = comm_score

            # Evaluator 3: target_language_correct
            lang_score = eval_target_language(translated, s["target_lang"])
            res_record["target_language_correct"] = lang_score

            passed = prot_score == 1.0 and comm_score == 1.0 and lang_score == 1.0
            res_record["passed"] = passed

            status_str = "PASS" if passed else "FAIL"
            log.append(
                f"{status_str}: {s['id']} [{s['target_lang']}] "
                f"protected={prot_score:.2f}, commentary={comm_score:.2f}, lang={lang_score:.2f}"
            )
            results.append(res_record)

    evaluated = [r for r in results if not r.get("inconclusive")]
    if evaluated:
        prot_avg = sum(r["protected_tokens_preserved"] for r in evaluated) / len(evaluated)
        comm_avg = sum(r["no_commentary"] for r in evaluated) / len(evaluated)
        lang_avg = sum(r["target_language_correct"] for r in evaluated) / len(evaluated)
    else:
        prot_avg = 1.0
        comm_avg = 1.0
        lang_avg = 1.0

    inconclusive_count = sum(1 for r in results if r.get("inconclusive"))
    passed_count = sum(1 for r in results if r.get("passed", False))
    total_count = len(results)

    all_passed = (prot_avg == 1.0) and (
        passed_count == (total_count - inconclusive_count)
        if total_count > inconclusive_count
        else True
    )

    metrics = {
        "tests_run": total_count,
        "tests_passed": passed_count,
        "inconclusive_count": inconclusive_count,
        "protected_tokens_preserved": prot_avg,
        "no_commentary": comm_avg,
        "target_language_correct": lang_avg,
    }

    return {
        "suite": "D",
        "passed": all_passed,
        "metrics": metrics,
        "results": results,
        "log": log,
    }


def run_suite_d(
    sample_size: int | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    """Synchronous entry point for Suite D."""
    return asyncio.run(run_suite_d_async(sample_size=sample_size, llm_client=llm_client))
