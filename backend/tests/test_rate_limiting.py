"""Unit tests for sliding-window rate limiting on API endpoints."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.models.user import User
from app.rate_limiter import (
    SlidingWindowRateLimiter,
    rate_limit_auth_ip,
    rate_limit_chat_turn,
    rate_limit_explain,
    rate_limit_repo_ingest,
    rate_limit_translations,
    rate_limiter,
)


@pytest.fixture(autouse=True)
def clean_rate_limits() -> None:
    """Clear in-memory rate limiter state before each test."""
    rate_limiter.clear()


def test_sliding_window_basic_limit() -> None:
    """Ensure sliding window allows up to max_requests and blocks beyond."""
    limiter = SlidingWindowRateLimiter()
    key = "test_user_1"

    # Allow 5 requests per 10 seconds
    for _ in range(5):
        limiter.check(key, max_requests=5, window_seconds=10)

    # 6th request must raise 429 with Retry-After header
    with pytest.raises(HTTPException) as exc_info:
        limiter.check(key, max_requests=5, window_seconds=10)

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers
    retry_after = int(exc_info.value.headers["Retry-After"])
    assert 1 <= retry_after <= 10


def test_sliding_window_user_isolation() -> None:
    """Ensure rate limits are strictly isolated by key (User A does not affect User B)."""
    limiter = SlidingWindowRateLimiter()
    key_a = "user:1:action"
    key_b = "user:2:action"

    for _ in range(3):
        limiter.check(key_a, max_requests=3, window_seconds=60)

    # User A is blocked
    with pytest.raises(HTTPException):
        limiter.check(key_a, max_requests=3, window_seconds=60)

    # User B is NOT blocked
    limiter.check(key_b, max_requests=3, window_seconds=60)


def test_rate_limit_translations_blocks_at_61() -> None:
    """Ensure translations limit caps at 60/min per user."""
    user = User(id=42, login="tester")
    for _ in range(60):
        rate_limit_translations(user)

    with pytest.raises(HTTPException) as exc_info:
        rate_limit_translations(user)

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_rate_limit_explain_blocks_at_31() -> None:
    """Ensure explain limit caps at 30/min per user."""
    user = User(id=42, login="tester")
    for _ in range(30):
        rate_limit_explain(user)

    with pytest.raises(HTTPException) as exc_info:
        rate_limit_explain(user)

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_rate_limit_repo_ingest_blocks_at_11() -> None:
    """Ensure repo ingest limit caps at 10/hour per user."""
    user = User(id=42, login="tester")
    for _ in range(10):
        rate_limit_repo_ingest(user)

    with pytest.raises(HTTPException) as exc_info:
        rate_limit_repo_ingest(user)

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_rate_limit_chat_turn_minute_limit() -> None:
    """Ensure chat/agent turns limit caps at 20/min."""
    user = User(id=42, login="tester")
    for _ in range(20):
        rate_limit_chat_turn(user)

    with pytest.raises(HTTPException) as exc_info:
        rate_limit_chat_turn(user)

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_rate_limit_auth_ip_blocks_at_31() -> None:
    """Ensure /auth/* routes cap at 30/min per client IP."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/auth/github/login",
        "headers": [(b"x-forwarded-for", b"203.0.113.195")],
    }
    request = Request(scope)

    for _ in range(30):
        rate_limit_auth_ip(request)

    with pytest.raises(HTTPException) as exc_info:
        rate_limit_auth_ip(request)

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers

    # Different IP should succeed
    other_scope = {
        "type": "http",
        "method": "GET",
        "path": "/auth/github/login",
        "headers": [(b"x-forwarded-for", b"198.51.100.10")],
    }
    other_request = Request(other_scope)
    rate_limit_auth_ip(other_request)
