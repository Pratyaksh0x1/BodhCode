"""Production boot guard and egress allowlist verification.

Enforces zero-trust production startup guarantees:
- Rejects boot if secrets are dev defaults or placeholders.
- Rejects boot if URLs do not use HTTPS in production.
- Rejects boot if allowed origins include localhost or 127.0.0.1 in production.
- Validates outbound network targets strictly match the approved egress allowlist.
"""

from __future__ import annotations

import base64
import logging
from urllib.parse import urlparse

from cryptography.fernet import Fernet

from app.config import Settings

logger = logging.getLogger(__name__)

DISALLOWED_SECRET_PATTERNS = (
    "change_me",
    "changeme",
    "change-me",
    "secret",
    "placeholder",
    "your-secret-key",
    "replace-me",
    "dev_secret",
    "dev_token",
)

ALLOWED_EGRESS_HOSTS = frozenset(
    {
        "api.github.com",
        "codeload.github.com",
        "api.groq.com",
        "api.smith.langchain.com",
    }
)


class EgressViolationError(PermissionError):
    """Raised when an outbound network request targets an unauthorized host."""

    pass


def verify_egress_url(url: str, tracing_enabled: bool = True) -> str:
    """Verify an outbound URL against the strict egress allowlist.

    Only GitHub, Groq, and LangSmith (when tracing is enabled) are allowed.
    Returns the host if authorized; raises EgressViolationError otherwise.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        raise EgressViolationError(f"Invalid outbound URL missing hostname: '{url}'")

    if host not in ALLOWED_EGRESS_HOSTS:
        raise EgressViolationError(
            f"Blocked outbound request to unauthorized host '{host}'. "
            f"Allowed egress targets: {sorted(ALLOWED_EGRESS_HOSTS)}"
        )

    if host == "api.smith.langchain.com" and not tracing_enabled:
        raise EgressViolationError(
            "Outbound call to api.smith.langchain.com blocked because tracing is disabled"
        )

    return host


def validate_production_boot(settings: Settings) -> None:
    """Verify application configuration safety before startup.

    If ENV is 'production' (or ENVIRONMENT='production'), this function ensures:
    1. APP_SECRET_KEY is at least 32 characters and not a known placeholder.
    2. TOKEN_ENCRYPTION_KEY is a valid 32-byte Fernet key and not a known placeholder.
    3. FRONTEND_URL and BACKEND_URL use the 'https://' scheme.
    4. ALLOWED_ORIGINS does not include localhost or 127.0.0.1.

    Raises RuntimeError naming the offending configuration variable if any check fails.
    In development/test environments, logs warnings instead of aborting boot.
    """
    is_production = settings.ENV.lower() == "production"

    # --- 1. APP_SECRET_KEY Check ---
    secret_key = (settings.APP_SECRET_KEY or "").strip()
    secret_key_lower = secret_key.lower()
    is_secret_placeholder = any(
        pattern in secret_key_lower for pattern in DISALLOWED_SECRET_PATTERNS
    )
    is_secret_too_short = len(secret_key) < 32

    if is_secret_placeholder or is_secret_too_short:
        msg = (
            "Production boot guard violation: APP_SECRET_KEY must be at least 32 characters "
            "and cannot be a development placeholder."
        )
        if is_production:
            logger.error(msg)
            raise RuntimeError(msg)
        logger.warning(
            "Insecure APP_SECRET_KEY in non-production environment: %s",
            "too short" if is_secret_too_short else "placeholder",
        )

    # --- 2. TOKEN_ENCRYPTION_KEY Check ---
    encryption_key = (settings.TOKEN_ENCRYPTION_KEY or "").strip()
    is_encryption_placeholder = any(
        pattern in encryption_key.lower() for pattern in DISALLOWED_SECRET_PATTERNS
    )

    valid_fernet = False
    try:
        decoded = base64.urlsafe_b64decode(encryption_key.encode("utf-8"))
        if len(decoded) == 32:
            Fernet(encryption_key.encode("utf-8"))
            valid_fernet = True
    except Exception:
        valid_fernet = False

    if is_encryption_placeholder or not valid_fernet:
        msg = (
            "Production boot guard violation: TOKEN_ENCRYPTION_KEY must be a valid 32-byte "
            "urlsafe-base64-encoded Fernet key and cannot be a development placeholder."
        )
        if is_production:
            logger.error(msg)
            raise RuntimeError(msg)
        logger.warning(
            "Insecure or invalid TOKEN_ENCRYPTION_KEY in non-production environment: %s",
            "placeholder" if is_encryption_placeholder else "invalid Fernet format",
        )

    # --- 3. FRONTEND_URL and BACKEND_URL HTTPS Check ---
    frontend_url = settings.FRONTEND_URL.strip()
    backend_url = settings.BACKEND_URL.strip()

    if is_production:
        if frontend_url.startswith("http://") or not frontend_url.startswith("https://"):
            msg = (
                f"Production boot guard violation: FRONTEND_URL must use 'https://' "
                f"in production (got '{frontend_url}')."
            )
            logger.error(msg)
            raise RuntimeError(msg)

        if backend_url.startswith("http://") or not backend_url.startswith("https://"):
            msg = (
                f"Production boot guard violation: BACKEND_URL must use 'https://' "
                f"in production (got '{backend_url}')."
            )
            logger.error(msg)
            raise RuntimeError(msg)

    # --- 4. ALLOWED_ORIGINS Check ---
    origins_to_check: list[str] = [frontend_url]
    if hasattr(settings, "ALLOWED_ORIGINS") and settings.ALLOWED_ORIGINS:
        origins_to_check.extend(settings.ALLOWED_ORIGINS)

    if is_production:
        for origin in origins_to_check:
            origin_lower = origin.lower()
            if "localhost" in origin_lower or "127.0.0.1" in origin_lower:
                msg = (
                    f"Production boot guard violation: ALLOWED_ORIGINS cannot contain "
                    f"localhost or 127.0.0.1 in production (found '{origin}')."
                )
                logger.error(msg)
                raise RuntimeError(msg)
