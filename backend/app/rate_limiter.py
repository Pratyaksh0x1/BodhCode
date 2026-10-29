"""In-memory sliding-window rate limiter.

Guarantees resource exhaustion protection across API routes:
- Keyed strictly on user ID (never token) for authenticated endpoints.
- Keyed on client IP for public /auth/* endpoints.
- Always returns 429 Too Many Requests with a numeric 'Retry-After' header.
"""

from __future__ import annotations

import collections
import threading
import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.auth.deps import get_current_user
from app.models.user import User


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Maps key -> collections.deque of float timestamps
        self._buckets: dict[str, collections.deque[float]] = {}

    def clear(self) -> None:
        """Reset all buckets (primarily for testing)."""
        with self._lock:
            self._buckets.clear()

    def check(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> None:
        """Check and record a request.

        Raises HTTPException(429) with Retry-After header if limit is exceeded.
        """
        now = time.time()
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = collections.deque()
            queue = self._buckets[key]

            # Evict entries outside sliding window
            cutoff = now - window_seconds
            while queue and queue[0] <= cutoff:
                queue.popleft()

            if len(queue) >= max_requests:
                oldest = queue[0]
                retry_after = max(1, int(oldest + window_seconds - now + 0.999))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Rate limit exceeded: maximum {max_requests} requests "
                        f"per {window_seconds}s."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )

            queue.append(now)

    def check_multiple(
        self,
        key_prefix: str,
        limits: list[tuple[int, int]],
    ) -> None:
        """Check multiple tiered windows (e.g. 20/min and 200/day).

        If any window is exceeded, raises 429 with the longest required wait.
        Only commits the hit if all windows pass.
        """
        now = time.time()
        with self._lock:
            # 1. Verification pass
            worst_retry_after: int | None = None
            worst_limit: tuple[int, int] | None = None

            for max_reqs, win_sec in limits:
                bucket_key = f"{key_prefix}:{win_sec}"
                if bucket_key not in self._buckets:
                    self._buckets[bucket_key] = collections.deque()
                queue = self._buckets[bucket_key]

                cutoff = now - win_sec
                while queue and queue[0] <= cutoff:
                    queue.popleft()

                if len(queue) >= max_reqs:
                    oldest = queue[0]
                    wait_sec = max(1, int(oldest + win_sec - now + 0.999))
                    if worst_retry_after is None or wait_sec > worst_retry_after:
                        worst_retry_after = wait_sec
                        worst_limit = (max_reqs, win_sec)

            if worst_retry_after is not None and worst_limit is not None:
                max_reqs, win_sec = worst_limit
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded: maximum {max_reqs} requests per {win_sec}s.",
                    headers={"Retry-After": str(worst_retry_after)},
                )

            # 2. Commit pass
            for _max_reqs, win_sec in limits:
                bucket_key = f"{key_prefix}:{win_sec}"
                self._buckets[bucket_key].append(now)


# Global singleton rate limiter instance
rate_limiter = SlidingWindowRateLimiter()


# --- Route Dependencies ---


def rate_limit_translations(
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Rate limit translation requests to 60/minute per user."""
    assert current_user.id is not None
    rate_limiter.check(
        key=f"user:{current_user.id}:translations",
        max_requests=60,
        window_seconds=60,
    )


def rate_limit_chat_turn(
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Rate limit chat and agent turns to 20/minute and 200/day per user."""
    assert current_user.id is not None
    rate_limiter.check_multiple(
        key_prefix=f"user:{current_user.id}:chat_turns",
        limits=[
            (20, 60),  # 20 per 60 seconds
            (200, 86400),  # 200 per 24 hours
        ],
    )


def rate_limit_explain(
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Rate limit explanation requests to 30/minute per user."""
    assert current_user.id is not None
    rate_limiter.check(
        key=f"user:{current_user.id}:explain",
        max_requests=30,
        window_seconds=60,
    )


def rate_limit_repo_ingest(
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Rate limit repository ingestion/refresh requests to 10/hour per user."""
    assert current_user.id is not None
    rate_limiter.check(
        key=f"user:{current_user.id}:repo_ingest",
        max_requests=10,
        window_seconds=3600,
    )


def rate_limit_auth_ip(request: Request) -> None:
    """Rate limit /auth/* endpoints to 30/minute per client IP address."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.client and request.client.host:
        client_ip = request.client.host
    else:
        client_ip = "127.0.0.1"

    rate_limiter.check(
        key=f"ip:{client_ip}:auth",
        max_requests=30,
        window_seconds=60,
    )
