import hashlib
import json
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session

from app.ai.llm import LLMResult, LLMUsage
from app.ai.prompts.translate import build_translate_messages
from app.github.language import get_repo_language
from app.i18n.translate import translate_text
from app.models.repo import Repo


@pytest.mark.asyncio
async def test_get_repo_language_precedence() -> None:
    # 1. Override takes first precedence
    repo1 = Repo(
        user_id=1,
        owner="test",
        name="repo1",
        push_language_override="ja",
        source_language="es",
    )
    lang1 = await get_repo_language(repo1)
    assert lang1 == "ja"

    # 2. Source language takes second precedence
    repo2 = Repo(
        user_id=1,
        owner="test",
        name="repo2",
        push_language_override=None,
        source_language="de",
    )
    lang2 = await get_repo_language(repo2)
    assert lang2 == "de"

    # 3. Fallback to "en" when nothing available
    repo3 = Repo(
        user_id=1,
        owner="test",
        name="repo3",
        push_language_override=None,
        source_language=None,
        commit_sha=None,
    )
    lang3 = await get_repo_language(repo3)
    assert lang3 == "en"


def test_build_outgoing_translate_messages() -> None:
    messages = build_translate_messages(
        text="Fix bug in auth handler",
        source_lang="en",
        target_lang="ja",
        kind="outgoing",
    )
    assert len(messages) == 2
    assert "strict, faithful software engineering translation engine" in messages[0]["content"]
    assert "Fix bug in auth handler" in messages[1]["content"]


@pytest.mark.asyncio
async def test_outgoing_translation_identical_languages_no_llm(db_session: Session) -> None:
    mock_llm = AsyncMock()
    result = await translate_text(
        text="Add search indexing for fast retrieval",
        source="en",
        target="en",
        kind="outgoing",
        session=db_session,
        llm_client=mock_llm,
    )
    assert result.ok is True
    assert result.text == "Add search indexing for fast retrieval"
    mock_llm.chat.assert_not_called()


@pytest.mark.asyncio
async def test_outgoing_translation_preserves_code_and_refs(db_session: Session) -> None:
    original_text = (
        "Fixes #42 and updates `authService.ts`. See https://github.com/issue/42 by @coder."
    )

    mock_llm = AsyncMock()
    # LLM translates the masked template preserving tokens ⟦K0⟧ ...
    async def fake_chat(**kwargs):
        # Inspect incoming prompt to ensure tokens were passed
        prompt_text = kwargs["messages"][1]["content"]
        assert "⟦K0⟧" in prompt_text  # #42
        assert "⟦K1⟧" in prompt_text  # `authService.ts`
        assert "⟦K2⟧" in prompt_text  # URL
        assert "⟦K3⟧" in prompt_text  # @coder
        # Return simulated translation keeping tokens
        return LLMResult(
            text="⟦K0⟧ を修正し、⟦K1⟧ を更新しました。⟦K3⟧ による ⟦K2⟧ を参照してください。",
            model="llama-3.3-70b-versatile",
            latency_ms=100.0,
            usage=LLMUsage(prompt_tokens=50, completion_tokens=30, total_tokens=80),
        )

    mock_llm.chat.side_effect = fake_chat

    result = await translate_text(
        text=original_text,
        source="en",
        target="ja",
        kind="outgoing",
        session=db_session,
        llm_client=mock_llm,
        refresh=True,
    )

    assert result.ok is True
    assert "#42" in result.text
    assert "`authService.ts`" in result.text
    assert "https://github.com/issue/42" in result.text
    assert "@coder" in result.text


def test_payload_hash_updates_on_edit() -> None:
    payload1 = {
        "commit_message": "Fix bug",
        "pr_title": "Fix #1",
        "pr_body": "Details here",
    }
    hash1 = hashlib.sha256(json.dumps(payload1, sort_keys=True).encode("utf-8")).hexdigest()

    payload2 = {
        "commit_message": "Fix critical bug",
        "pr_title": "Fix #1",
        "pr_body": "Details here",
    }
    hash2 = hashlib.sha256(json.dumps(payload2, sort_keys=True).encode("utf-8")).hexdigest()

    assert hash1 != hash2
