"""Security middleware enforcing headers, payload size limits, and cache controls."""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

DEFAULT_MAX_BODY_BYTES = int(1.5 * 1024 * 1024)  # 1.5 MB
SMALL_MAX_BODY_BYTES = 20 * 1024  # 20 KB for skills / metadata endpoints

SMALL_LIMIT_PATHS = (
    "/evals/import-skill",
    "/meta/",
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces secure browser headers, cache controls, and CSP across all responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # Baseline security headers on every response
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        content_type = response.headers.get("content-type", "").lower()

        # Cache-Control: no-store on all authenticated JSON responses
        # (checks for user session safely without requiring SessionMiddleware on preflights)
        session = request.scope.get("session")
        has_session_user = bool(session.get("user_id")) if isinstance(session, dict) else False
        is_authenticated_request = bool(
            has_session_user
            or request.url.path.startswith(("/repos", "/auth/me", "/proposals"))
        )
        if is_authenticated_request and "application/json" in content_type:
            if "cache-control" not in response.headers:
                response.headers["Cache-Control"] = "no-store"

        # Content-Security-Policy on any HTML returned by the backend
        if "text/html" in content_type:
            response.headers["Content-Security-Policy"] = "default-src 'self';"

        return response


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    """Rejects request bodies exceeding strict resource thresholds with 413 Payload Too Large."""

    def _get_max_size(self, path: str) -> int:
        for prefix in SMALL_LIMIT_PATHS:
            if path.startswith(prefix):
                return SMALL_MAX_BODY_BYTES
        return DEFAULT_MAX_BODY_BYTES

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in ("POST", "PUT", "PATCH"):
            max_bytes = self._get_max_size(request.url.path)
            headers = Headers(scope=request.scope)
            content_length = headers.get("content-length")

            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        return JSONResponse(
                            status_code=413,
                            content={
                                "detail": (
                                    f"Payload Too Large: body length {content_length} "
                                    f"exceeds limit of {max_bytes} bytes."
                                )
                            },
                        )
                except ValueError:
                    pass

            # Buffer and measure body content
            body = await request.body()
            if len(body) > max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"Payload Too Large: body size {len(body)} "
                            f"exceeds limit of {max_bytes} bytes."
                        )
                    },
                )

        return await call_next(request)
