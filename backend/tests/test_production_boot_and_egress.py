"""Tests for production boot guard and egress allowlist enforcement."""

from __future__ import annotations

import base64
from unittest.mock import patch

import httpx
import pytest
from cryptography.fernet import Fernet

from app.boot_guard import (
    EgressViolationError,
    validate_production_boot,
    verify_egress_url,
)
from app.config import Settings


def _create_valid_prod_settings(**overrides: object) -> Settings:
    """Helper to create Settings with valid production values."""
    valid_key = Fernet.generate_key().decode("utf-8")
    defaults = {
        "ENV": "production",
        "APP_SECRET_KEY": "a" * 32,
        "TOKEN_ENCRYPTION_KEY": valid_key,
        "FRONTEND_URL": "https://bodhcode.example.com",
        "BACKEND_URL": "https://api.bodhcode.example.com",
        "ALLOWED_ORIGINS": ["https://bodhcode.example.com"],
        "DATABASE_URL": "sqlite:///test.db",
        "GITHUB_CLIENT_ID": "client_id_12345",
        "GITHUB_CLIENT_SECRET": "client_secret_67890",
        "GROQ_API_KEY": "gsk_valid_key_12345",
        "GROQ_MODEL": "openai/gpt-oss-120b",
        "DATA_DIR": "./data",
        "LANGSMITH_TRACING": False,
    }
    defaults.update(overrides)
    return Settings.model_construct(**defaults)


def test_production_boot_guard_passes_with_valid_settings() -> None:
    """Ensure production boot succeeds when all security requirements are met."""
    settings = _create_valid_prod_settings()
    # Should not raise
    validate_production_boot(settings)


def test_production_boot_guard_rejects_placeholder_secret_key() -> None:
    """Refuse to boot in production if APP_SECRET_KEY is a dev placeholder."""
    settings = _create_valid_prod_settings(
        APP_SECRET_KEY="change_me_to_a_secure_random_hex_key_32_bytes",
    )
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_boot(settings)
    assert "APP_SECRET_KEY" in str(exc_info.value)


def test_production_boot_guard_rejects_short_secret_key() -> None:
    """Refuse to boot in production if APP_SECRET_KEY is shorter than 32 characters."""
    settings = _create_valid_prod_settings(
        APP_SECRET_KEY="short_key",
    )
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_boot(settings)
    assert "APP_SECRET_KEY" in str(exc_info.value)


def test_production_boot_guard_rejects_placeholder_token_encryption_key() -> None:
    """Refuse to boot in production if TOKEN_ENCRYPTION_KEY is a placeholder."""
    # A 32-byte key containing placeholder substring
    raw_placeholder = b"dev_secret_placeholder_key_32_b"
    b64_key = base64.urlsafe_b64encode(raw_placeholder).decode("utf-8")
    settings = _create_valid_prod_settings(
        TOKEN_ENCRYPTION_KEY=b64_key,
    )
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_boot(settings)
    assert "TOKEN_ENCRYPTION_KEY" in str(exc_info.value)


def test_production_boot_guard_rejects_invalid_fernet_key() -> None:
    """Refuse to boot in production if TOKEN_ENCRYPTION_KEY is not a valid 32-byte Fernet key."""
    # Encode only 16 bytes instead of 32
    short_raw = b"only_sixteen_byt"
    b64_key = base64.urlsafe_b64encode(short_raw).decode("utf-8")
    settings = _create_valid_prod_settings(
        TOKEN_ENCRYPTION_KEY=b64_key,
    )
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_boot(settings)
    assert "TOKEN_ENCRYPTION_KEY" in str(exc_info.value)


def test_production_boot_guard_rejects_http_frontend_url() -> None:
    """Refuse to boot in production if FRONTEND_URL starts with http://."""
    settings = _create_valid_prod_settings(
        FRONTEND_URL="http://bodhcode.example.com",
    )
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_boot(settings)
    assert "FRONTEND_URL" in str(exc_info.value)


def test_production_boot_guard_rejects_http_backend_url() -> None:
    """Refuse to boot in production if BACKEND_URL starts with http://."""
    settings = _create_valid_prod_settings(
        BACKEND_URL="http://api.bodhcode.example.com",
    )
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_boot(settings)
    assert "BACKEND_URL" in str(exc_info.value)


def test_production_boot_guard_rejects_localhost_origin() -> None:
    """Refuse to boot in production if ALLOWED_ORIGINS contains localhost or 127.0.0.1."""
    settings = _create_valid_prod_settings(
        ALLOWED_ORIGINS=["https://bodhcode.example.com", "http://localhost:5173"],
    )
    with pytest.raises(RuntimeError) as exc_info:
        validate_production_boot(settings)
    assert "ALLOWED_ORIGINS" in str(exc_info.value)


def test_dev_environment_warns_but_does_not_raise() -> None:
    """Dev and test environments log warnings on dev defaults but do not abort boot."""
    settings = _create_valid_prod_settings(
        ENV="development",
        APP_SECRET_KEY="change_me_to_a_secure_random_hex_key_32_bytes",
        FRONTEND_URL="http://localhost:5173",
        BACKEND_URL="http://localhost:8000",
        ALLOWED_ORIGINS=["http://localhost:5173"],
    )
    # Should not raise in development
    validate_production_boot(settings)


def test_egress_allowlist_allowed_hosts() -> None:
    """Approved external endpoints pass the egress validation check."""
    assert verify_egress_url("https://api.github.com/user") == "api.github.com"
    assert verify_egress_url("https://codeload.github.com/org/repo/tar.gz") == "codeload.github.com"
    assert verify_egress_url("https://api.groq.com/openai/v1/chat/completions") == "api.groq.com"
    assert (
        verify_egress_url("https://api.smith.langchain.com/runs", tracing_enabled=True)
        == "api.smith.langchain.com"
    )


def test_egress_allowlist_blocks_unauthorized_hosts() -> None:
    """Blocked external endpoints raise EgressViolationError."""
    unauthorized_urls = [
        "https://evil-exfil.com/data",
        "https://telemetry.segment.io/v1/track",
        "https://analytics.google.com/g/collect",
        "https://cdn.jsdelivr.net/npm/axios",
        "http://169.254.169.254/latest/meta-data/",
    ]
    for url in unauthorized_urls:
        with pytest.raises(EgressViolationError):
            verify_egress_url(url)


def test_egress_allowlist_blocks_langsmith_when_tracing_disabled() -> None:
    """api.smith.langchain.com is blocked if tracing is not enabled."""
    with pytest.raises(EgressViolationError) as exc_info:
        verify_egress_url("https://api.smith.langchain.com/runs", tracing_enabled=False)
    assert "tracing is disabled" in str(exc_info.value)


@pytest.mark.asyncio
async def test_egress_client_interceptor_blocks_unauthorized_requests() -> None:
    """Verify that outbound httpx client calls to unapproved hosts fail."""

    # Custom transport or send wrapper that applies egress policy
    async def guarded_send(
        self: httpx.AsyncClient, request: httpx.Request, *args: object, **kwargs: object
    ) -> httpx.Response:
        verify_egress_url(str(request.url), tracing_enabled=True)
        return httpx.Response(200, json={"status": "mocked"})

    with patch.object(httpx.AsyncClient, "send", guarded_send):
        async with httpx.AsyncClient() as client:
            # Authorized GitHub call succeeds
            resp = await client.get("https://api.github.com/zen")
            assert resp.status_code == 200

            # Unauthorized call raises EgressViolationError
            with pytest.raises(EgressViolationError):
                await client.post("https://unauthorized-analytics.com/event", json={})
