"""Production Groq LLM client with concurrency control, retries, and LangSmith tracing."""

import asyncio
import json
import logging
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from groq import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncGroq,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from langsmith import traceable
from pydantic import BaseModel, ConfigDict, Field

from app.ai.redact import redact
from app.ai.tracing import update_current_llm_run
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed Exceptions (Zero secret leakage)
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Base exception for LLM layer errors."""


class LLMRateLimited(LLMError):
    """Raised when Groq rate limits (429) persist after backoff retries."""


class LLMUnavailable(LLMError):
    """Raised when Groq service is unavailable, connections drop, or 5xx occurs."""


class LLMBadRequest(LLMError):
    """Raised on invalid request parameters, malformed schema, or context length exceeded."""


class LLMAuthError(LLMError):
    """Raised on Groq authentication failure or invalid API key."""


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    """Parsed tool invocation requested by the model."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class LLMUsage(BaseModel):
    """Token usage metrics."""

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResult(BaseModel):
    """Unified result structure returned by chat completions."""

    model_config = ConfigDict(frozen=True)

    text: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    usage: LLMUsage = Field(default_factory=LLMUsage)
    model: str
    latency_ms: float
    request_id: str | None = None


class StreamChunk(BaseModel):
    """Streaming delta or completion token chunk."""

    model_config = ConfigDict(frozen=True)

    delta: str = ""
    finish_reason: str | None = None
    usage: LLMUsage | None = None


# ---------------------------------------------------------------------------
# LLMClient Implementation
# ---------------------------------------------------------------------------


class LLMClient:
    """Thread-safe, rate-limited, and traced wrapper around Groq AsyncGroq SDK."""

    def __init__(
        self,
        settings: Settings | None = None,
        groq_client: AsyncGroq | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._groq_client = groq_client or AsyncGroq(api_key=self.settings.GROQ_API_KEY)
        self._clock = clock or time.perf_counter
        self._sleep = sleep or asyncio.sleep
        self._semaphore = semaphore or asyncio.Semaphore(self.settings.LLM_MAX_CONCURRENCY)

    def _select_model(self, model: str | None, fast: bool) -> str:
        if model:
            return model
        if fast and self.settings.GROQ_FAST_MODEL:
            return self.settings.GROQ_FAST_MODEL
        return self.settings.GROQ_MODEL

    def _parse_retry_after(self, error: Exception) -> float | None:
        """Extract retry-after header if present on a 429 response."""
        if hasattr(error, "response") and error.response is not None:
            retry_header = error.response.headers.get("retry-after")
            if retry_header:
                try:
                    val = float(retry_header)
                    if val > 0:
                        return val
                except (ValueError, TypeError):
                    pass
        return None

    def _parse_tool_calls(self, raw_calls: Any) -> list[ToolCall]:
        """Safely parse raw tool calls from model choice message."""
        parsed: list[ToolCall] = []
        if not raw_calls:
            return parsed
        for tc in raw_calls:
            fn_name = getattr(tc.function, "name", "")
            raw_args = getattr(tc.function, "arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    args_dict = json.loads(raw_args)
                except Exception:
                    args_dict = {"_raw": raw_args}
            elif isinstance(raw_args, dict):
                args_dict = raw_args
            else:
                args_dict = {}
            parsed.append(ToolCall(id=str(tc.id), name=fn_name, arguments=args_dict))
        return parsed

    @traceable(
        run_type="llm",
        name="groq.call",
        process_inputs=redact,
        process_outputs=redact,
    )
    async def _execute_chat_with_tracing(
        self,
        messages: list[dict[str, Any]],
        *,
        feature: str,
        effective_model: str,
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | None,
        response_format: dict[str, Any] | None,
        prompt_name: str | None,
        prompt_version: int | None,
    ) -> LLMResult:
        """Internal worker executing Groq chat with backoff and concurrency limits."""
        start_time = self._clock()

        # Build clean kwargs for Groq SDK
        kwargs: dict[str, Any] = {
            "model": effective_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        if response_format:
            kwargs["response_format"] = response_format

        max_rate_limit_attempts = 4
        max_transient_attempts = 3
        rate_limit_attempts = 0
        transient_attempts = 0

        # Backoff schedule: 0.5s, 1s, 2s, 4s
        backoff_delays = [0.5, 1.0, 2.0, 4.0]

        async with self._semaphore:
            while True:
                try:
                    response = await asyncio.wait_for(
                        self._groq_client.chat.completions.create(**kwargs),
                        timeout=self.settings.LLM_TIMEOUT_SECONDS,
                    )
                    break
                except (RateLimitError, APIStatusError) as exc:
                    status_code = getattr(exc, "status_code", None)
                    if isinstance(exc, RateLimitError) or status_code == 429:
                        rate_limit_attempts += 1
                        if rate_limit_attempts >= max_rate_limit_attempts:
                            raise LLMRateLimited(
                                "Groq rate limit exceeded after maximum retry attempts"
                            ) from None

                        # Check for retry-after or use exponential backoff with jitter
                        delay = self._parse_retry_after(exc)
                        if delay is None:
                            idx = min(rate_limit_attempts - 1, len(backoff_delays) - 1)
                            base = backoff_delays[idx]
                            jitter = random.uniform(0.0, 0.25)
                            delay = base + jitter

                        logger.warning(
                            "Groq 429 rate limit hit for feature '%s'. "
                            "Retrying in %.2fs (attempt %d/%d)",
                            feature,
                            delay,
                            rate_limit_attempts,
                            max_rate_limit_attempts,
                        )
                        await self._sleep(delay)
                        continue

                    # 4xx handling (Non-retryable)
                    if isinstance(
                        exc, (AuthenticationError, PermissionDeniedError)
                    ) or status_code in (401, 403):
                        raise LLMAuthError(
                            "Groq authentication failed or invalid API credentials"
                        ) from None
                    if isinstance(exc, (BadRequestError, UnprocessableEntityError)) or (
                        status_code is not None and 400 <= status_code < 500
                    ):
                        raise LLMBadRequest(
                            "Invalid LLM request parameters or context exceeded"
                        ) from None

                    # 5xx handling (Transient)
                    if isinstance(exc, InternalServerError) or (
                        status_code is not None and status_code >= 500
                    ):
                        transient_attempts += 1
                        if transient_attempts >= max_transient_attempts:
                            raise LLMUnavailable(
                                "Groq service returned server error after retries"
                            ) from None
                        delay = 1.0 + random.uniform(0.0, 0.5)
                        logger.warning(
                            "Groq 5xx error for feature '%s'. Retrying in %.2fs (attempt %d/%d)",
                            feature,
                            delay,
                            transient_attempts,
                            max_transient_attempts,
                        )
                        await self._sleep(delay)
                        continue

                    raise LLMUnavailable("Groq service communication error") from None

                except (APITimeoutError, TimeoutError):
                    transient_attempts += 1
                    if transient_attempts >= max_transient_attempts:
                        raise LLMUnavailable(
                            "Groq request timed out after maximum attempts"
                        ) from None
                    delay = 1.0 + random.uniform(0.0, 0.5)
                    logger.warning(
                        "Groq timeout for feature '%s'. Retrying in %.2fs (attempt %d/%d)",
                        feature,
                        delay,
                        transient_attempts,
                        max_transient_attempts,
                    )
                    await self._sleep(delay)
                    continue

                except APIConnectionError:
                    transient_attempts += 1
                    if transient_attempts >= max_transient_attempts:
                        raise LLMUnavailable(
                            "Groq network connection failed after maximum attempts"
                        ) from None
                    delay = 1.0 + random.uniform(0.0, 0.5)
                    logger.warning(
                        "Groq connection error for feature '%s'. Retrying in %.2fs (attempt %d/%d)",
                        feature,
                        delay,
                        transient_attempts,
                        max_transient_attempts,
                    )
                    await self._sleep(delay)
                    continue

        latency_ms = round((self._clock() - start_time) * 1000.0, 2)

        # Parse output choice
        choice = response.choices[0] if response.choices else None
        text_content = choice.message.content if choice and choice.message else None
        raw_tool_calls = (
            getattr(choice.message, "tool_calls", None) if choice and choice.message else None
        )
        tool_calls = self._parse_tool_calls(raw_tool_calls)
        finish_reason = getattr(choice, "finish_reason", None)

        # Parse usage
        raw_usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(raw_usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(raw_usage, "completion_tokens", 0) or 0)
        total_tokens = int(
            getattr(raw_usage, "total_tokens", prompt_tokens + completion_tokens) or 0
        )

        usage = LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

        # Update LangSmith span with metadata and usage tokens
        update_current_llm_run(
            feature=feature,
            model=effective_model,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

        return LLMResult(
            text=text_content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            usage=usage,
            model=effective_model,
            latency_ms=latency_ms,
            request_id=getattr(response, "id", None),
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        feature: str,
        model: str | None = None,
        fast: bool = False,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_format: dict[str, Any] | None = None,
        prompt_name: str | None = None,
        prompt_version: int | None = None,
    ) -> LLMResult:
        """Perform a chat completion with retries, concurrency bounds, and tracing."""
        effective_model = self._select_model(model, fast)
        return await self._execute_chat_with_tracing(
            messages=messages,
            feature=feature,
            effective_model=effective_model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        feature: str,
        model: str | None = None,
        fast: bool = False,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_format: dict[str, Any] | None = None,
        prompt_name: str | None = None,
        prompt_version: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream chat completion chunks wrapped in concurrency semaphore."""
        effective_model = self._select_model(model, fast)
        kwargs: dict[str, Any] = {
            "model": effective_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        if response_format:
            kwargs["response_format"] = response_format

        async with self._semaphore:
            try:
                stream_response = await self._groq_client.chat.completions.create(**kwargs)
            except RateLimitError:
                raise LLMRateLimited("Groq rate limit exceeded on stream initiation") from None
            except (AuthenticationError, PermissionDeniedError):
                raise LLMAuthError("Groq authentication failed") from None
            except BadRequestError:
                raise LLMBadRequest("Invalid LLM streaming request") from None
            except Exception:
                raise LLMUnavailable("Groq streaming service unavailable") from None

            async for chunk in stream_response:
                choice = chunk.choices[0] if chunk.choices else None
                delta_content = (
                    getattr(choice.delta, "content", "") if choice and choice.delta else ""
                )
                finish_reason = getattr(choice, "finish_reason", None) if choice else None
                chunk_usage = None
                if hasattr(chunk, "usage") and chunk.usage:
                    chunk_usage = LLMUsage(
                        prompt_tokens=getattr(chunk.usage, "prompt_tokens", 0) or 0,
                        completion_tokens=getattr(chunk.usage, "completion_tokens", 0) or 0,
                        total_tokens=getattr(chunk.usage, "total_tokens", 0) or 0,
                    )
                yield StreamChunk(
                    delta=delta_content or "",
                    finish_reason=finish_reason,
                    usage=chunk_usage,
                )


# ---------------------------------------------------------------------------
# Client Singleton
# ---------------------------------------------------------------------------

_CLIENT_INSTANCE: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Retrieve or create application-wide LLMClient singleton."""
    global _CLIENT_INSTANCE
    if _CLIENT_INSTANCE is None:
        _CLIENT_INSTANCE = LLMClient()
    return _CLIENT_INSTANCE
