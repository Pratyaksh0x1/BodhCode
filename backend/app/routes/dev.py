"""Development-only diagnostic endpoints. Registered exclusively in development environment."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.ai.llm import LLMAuthError, LLMError, LLMRateLimited, LLMUnavailable, get_llm_client
from app.ai.prompts import ping as ping_prompt
from app.auth.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/dev", tags=["dev"])


@router.get("/llm-ping")
async def dev_llm_ping(
    _current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Test Groq connectivity and LangSmith tracing end-to-end. Available only in development."""
    client = get_llm_client()
    messages = [
        {"role": "system", "content": ping_prompt.SYSTEM_PROMPT},
        {"role": "user", "content": "PING"},
    ]
    try:
        result = await client.chat(
            messages,
            feature="ping",
            fast=True,
            max_tokens=64,
            prompt_name=ping_prompt.NAME,
            prompt_version=ping_prompt.VERSION,
        )
        return {
            "ok": True,
            "text": result.text,
            "latency_ms": result.latency_ms,
            "model": result.model,
            "usage": result.usage.model_dump(),
        }
    except LLMAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM authentication failed: {exc}",
        ) from None
    except LLMRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"LLM rate limited: {exc}",
        ) from None
    except LLMUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM service unavailable: {exc}",
        ) from None
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM error: {exc}",
        ) from None
