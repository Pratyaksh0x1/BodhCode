"""Unit tests for BodhCode LLM layer, retries, semaphore concurrency, and error mapping."""

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from groq import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from app.ai.llm import (
    LLMAuthError,
    LLMBadRequest,
    LLMClient,
    LLMRateLimited,
    LLMUnavailable,
)
from app.config import Settings


class MockMessage:
    def __init__(self, content: str | None = "PONG", tool_calls: list[Any] | None = None):
        self.content = content
        self.tool_calls = tool_calls


class MockChoice:
    def __init__(
        self,
        content: str | None = "PONG",
        tool_calls: list[Any] | None = None,
        finish_reason: str | None = "stop",
    ):
        self.message = MockMessage(content, tool_calls)
        self.finish_reason = finish_reason


class MockUsage:
    def __init__(self, prompt_tokens: int = 10, completion_tokens: int = 5, total_tokens: int = 15):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class MockResponse:
    def __init__(
        self,
        content: str | None = "PONG",
        tool_calls: list[Any] | None = None,
        finish_reason: str = "stop",
        usage: Any | None = None,
        id: str = "chatcmpl-test-123",
    ):
        self.id = id
        self.choices = [MockChoice(content, tool_calls, finish_reason)]
        self.usage = usage if usage is not None else MockUsage()


def create_test_settings() -> Settings:
    return Settings(
        APP_SECRET_KEY="a" * 32,
        FRONTEND_URL="http://localhost:5173",
        BACKEND_URL="http://localhost:8000",
        DATABASE_URL="sqlite:///./test.db",
        GITHUB_CLIENT_ID="gh_id",
        GITHUB_CLIENT_SECRET="gh_sec",
        TOKEN_ENCRYPTION_KEY="rMRb5uNBakxqd2ErZ0BYAe-N1amHtrQVayLBJpdXiOA=",
        GROQ_API_KEY="gsk_test_key_1234567890",
        GROQ_MODEL="openai/gpt-oss-120b",
        GROQ_FAST_MODEL="openai/gpt-oss-20b",
        LLM_MAX_CONCURRENCY=3,
        LANGSMITH_TRACING=False,
    )


@pytest.mark.asyncio
async def test_llm_chat_plain_text():
    mock_groq = MagicMock()
    mock_groq.chat.completions.create = AsyncMock(return_value=MockResponse(content="Hello world"))

    client = LLMClient(settings=create_test_settings(), groq_client=mock_groq)
    res = await client.chat([{"role": "user", "content": "Hi"}], feature="test")

    assert res.text == "Hello world"
    assert res.model == "openai/gpt-oss-120b"
    assert res.usage.prompt_tokens == 10
    assert res.usage.completion_tokens == 5
    assert res.usage.total_tokens == 15
    assert res.finish_reason == "stop"


@pytest.mark.asyncio
async def test_llm_chat_fast_model_selection():
    mock_groq = MagicMock()
    mock_groq.chat.completions.create = AsyncMock(return_value=MockResponse())

    client = LLMClient(settings=create_test_settings(), groq_client=mock_groq)
    res = await client.chat([{"role": "user", "content": "Hi"}], feature="test", fast=True)

    assert res.model == "openai/gpt-oss-20b"


@pytest.mark.asyncio
async def test_llm_chat_tool_calls_parsing():
    class RawFunction:
        name = "get_weather"
        arguments = '{"location": "Tokyo", "unit": "celsius"}'

    class RawToolCall:
        id = "call_abc123"
        function = RawFunction()

    mock_groq = MagicMock()
    mock_groq.chat.completions.create = AsyncMock(
        return_value=MockResponse(
            content=None,
            tool_calls=[RawToolCall()],
            finish_reason="tool_calls",
        )
    )

    client = LLMClient(settings=create_test_settings(), groq_client=mock_groq)
    res = await client.chat([{"role": "user", "content": "Weather in Tokyo"}], feature="tools")

    assert res.text is None
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].id == "call_abc123"
    assert res.tool_calls[0].name == "get_weather"
    assert res.tool_calls[0].arguments == {"location": "Tokyo", "unit": "celsius"}
    assert res.finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_llm_chat_missing_usage():
    mock_groq = MagicMock()
    # Response without usage attribute
    resp = MockResponse(content="No usage")
    resp.usage = None
    mock_groq.chat.completions.create = AsyncMock(return_value=resp)

    client = LLMClient(settings=create_test_settings(), groq_client=mock_groq)
    res = await client.chat([{"role": "user", "content": "Hi"}], feature="test")

    assert res.text == "No usage"
    assert res.usage.prompt_tokens == 0
    assert res.usage.completion_tokens == 0
    assert res.usage.total_tokens == 0


@pytest.mark.asyncio
async def test_retry_on_429_honors_retry_after():
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    dummy_request = httpx.Request("POST", "https://api.groq.com")
    rate_limit_resp = httpx.Response(429, headers={"retry-after": "1.5"}, request=dummy_request)
    rate_err = RateLimitError(
        message="rate limit reached",
        response=rate_limit_resp,
        body={"error": {"message": "Rate limit exceeded"}},
    )

    mock_groq = MagicMock()
    # Fails twice with 429 and retry-after=1.5, succeeds on 3rd attempt
    mock_groq.chat.completions.create = AsyncMock(
        side_effect=[rate_err, rate_err, MockResponse(content="Success after 429")]
    )

    client = LLMClient(
        settings=create_test_settings(),
        groq_client=mock_groq,
        sleep=fake_sleep,
    )
    res = await client.chat([{"role": "user", "content": "Hi"}], feature="test")

    assert res.text == "Success after 429"
    assert len(sleep_calls) == 2
    assert sleep_calls == [1.5, 1.5]


@pytest.mark.asyncio
async def test_retry_on_429_backoff_exhausts_and_raises():
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    dummy_request = httpx.Request("POST", "https://api.groq.com")
    rate_limit_resp = httpx.Response(429, headers={}, request=dummy_request)
    rate_err = RateLimitError(
        message="rate limit reached",
        response=rate_limit_resp,
        body={"error": {"message": "Rate limit exceeded"}},
    )

    mock_groq = MagicMock()
    mock_groq.chat.completions.create = AsyncMock(side_effect=rate_err)

    client = LLMClient(
        settings=create_test_settings(),
        groq_client=mock_groq,
        sleep=fake_sleep,
    )

    with pytest.raises(LLMRateLimited) as exc_info:
        await client.chat([{"role": "user", "content": "Hi"}], feature="test")

    assert "rate limit exceeded" in str(exc_info.value).lower()
    # 4 attempts means 3 sleep retries: base delays 0.5, 1.0, 2.0 (with jitter >= base)
    assert len(sleep_calls) == 3
    assert sleep_calls[0] >= 0.5
    assert sleep_calls[1] >= 1.0
    assert sleep_calls[2] >= 2.0


@pytest.mark.asyncio
async def test_401_auth_error_not_retried():
    dummy_request = httpx.Request("POST", "https://api.groq.com")
    resp_401 = httpx.Response(401, request=dummy_request)
    auth_err = AuthenticationError(
        message="invalid api key gsk_12345",
        response=resp_401,
        body={"error": {"message": "invalid api key"}},
    )

    mock_groq = MagicMock()
    mock_groq.chat.completions.create = AsyncMock(side_effect=auth_err)

    client = LLMClient(settings=create_test_settings(), groq_client=mock_groq)

    with pytest.raises(LLMAuthError) as exc_info:
        await client.chat([{"role": "user", "content": "Hi"}], feature="test")

    # Error message must NOT leak api key
    err_str = str(exc_info.value)
    assert "gsk_12345" not in err_str
    # Only attempted once
    assert mock_groq.chat.completions.create.call_count == 1


@pytest.mark.asyncio
async def test_400_bad_request_not_retried():
    dummy_request = httpx.Request("POST", "https://api.groq.com")
    resp_400 = httpx.Response(400, request=dummy_request)
    bad_req_err = BadRequestError(
        message="context length exceeded",
        response=resp_400,
        body={"error": {"message": "context length exceeded"}},
    )

    mock_groq = MagicMock()
    mock_groq.chat.completions.create = AsyncMock(side_effect=bad_req_err)

    client = LLMClient(settings=create_test_settings(), groq_client=mock_groq)

    with pytest.raises(LLMBadRequest):
        await client.chat([{"role": "user", "content": "Hi"}], feature="test")

    assert mock_groq.chat.completions.create.call_count == 1


@pytest.mark.asyncio
async def test_500_transient_error_retried_and_raises_unavailable():
    dummy_request = httpx.Request("POST", "https://api.groq.com")
    resp_500 = httpx.Response(500, request=dummy_request)
    server_err = InternalServerError(
        message="internal server error",
        response=resp_500,
        body={"error": {"message": "internal error"}},
    )

    mock_groq = MagicMock()
    mock_groq.chat.completions.create = AsyncMock(side_effect=server_err)

    client = LLMClient(
        settings=create_test_settings(),
        groq_client=mock_groq,
        sleep=AsyncMock(),
    )

    with pytest.raises(LLMUnavailable):
        await client.chat([{"role": "user", "content": "Hi"}], feature="test")

    # 3 attempts total (1 initial + 2 retries)
    assert mock_groq.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_timeout_and_connection_error_retried():
    dummy_request = httpx.Request("POST", "https://api.groq.com")
    timeout_err = APITimeoutError(request=dummy_request)
    conn_err = APIConnectionError(request=dummy_request)

    mock_groq = MagicMock()
    # 1 timeout, 1 conn error, then success
    mock_groq.chat.completions.create = AsyncMock(
        side_effect=[timeout_err, conn_err, MockResponse(content="Recovered")]
    )

    client = LLMClient(
        settings=create_test_settings(),
        groq_client=mock_groq,
        sleep=AsyncMock(),
    )

    res = await client.chat([{"role": "user", "content": "Hi"}], feature="test")
    assert res.text == "Recovered"
    assert mock_groq.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_concurrency_semaphore_limits_in_flight():
    """Verify that with concurrency limit 2 and 6 requests, <= 2 run at once."""
    max_active = 0
    current_active = 0

    async def fake_completion(**kwargs):
        nonlocal current_active, max_active
        current_active += 1
        if current_active > max_active:
            max_active = current_active
        await asyncio.sleep(0.02)
        current_active -= 1
        return MockResponse(content="done")

    mock_groq = MagicMock()
    mock_groq.chat.completions.create = fake_completion

    semaphore = asyncio.Semaphore(2)
    client = LLMClient(
        settings=create_test_settings(),
        groq_client=mock_groq,
        semaphore=semaphore,
    )

    tasks = [
        client.chat([{"role": "user", "content": f"msg {i}"}], feature="concurrency_test")
        for i in range(6)
    ]
    results = await asyncio.gather(*tasks)

    assert len(results) == 6
    assert max_active == 2


def test_only_llm_py_imports_groq():
    """Ensure that ONLY app/ai/llm.py imports the 'groq' package across the entire backend."""
    backend_app_dir = Path(__file__).resolve().parent.parent / "app"
    violating_files: list[str] = []

    for py_file in backend_app_dir.glob("**/*.py"):
        rel_path = py_file.relative_to(backend_app_dir).as_posix()
        # app/ai/llm.py is the ONLY file allowed to import groq
        if rel_path == "ai/llm.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        if "import groq" in content or "from groq" in content:
            violating_files.append(rel_path)

    assert not violating_files, f"Unauthorized files importing groq: {violating_files}"
