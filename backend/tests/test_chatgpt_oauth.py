import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.chatgpt_oauth import (
    OPENAI_CLIENT_ID,
    build_chatgpt_authorize_url,
    decode_jwt_payload,
    generate_pkce,
)
from app.main import create_app


def test_generate_pkce() -> None:
    verifier, challenge = generate_pkce()
    assert len(verifier) >= 43
    assert len(challenge) >= 43
    assert "=" not in verifier
    assert "=" not in challenge


def test_build_chatgpt_authorize_url() -> None:
    verifier, challenge = generate_pkce()
    url = build_chatgpt_authorize_url(
        client_id=OPENAI_CLIENT_ID,
        redirect_uri="http://localhost:1455/auth/callback",
        code_challenge=challenge,
        state="test-state-123",
    )
    assert url.startswith("https://auth.openai.com/oauth/authorize?")
    assert f"client_id={OPENAI_CLIENT_ID}" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback" in url
    assert f"code_challenge={challenge}" in url
    assert "code_challenge_method=S256" in url
    assert "state=test-state-123" in url
    assert "originator=codex_cli_rs" in url


def test_decode_jwt_payload() -> None:
    # Sample payload: {"email": "test@example.com", "sub": "user_123"}
    # base64url encoded: eyJlbWFpbCI6ICJ0ZXN0QGV4YW1wbGUuY29tIiwgInN1YiI6ICJ1c2VyXzEyMyJ9
    fake_jwt = "header.eyJlbWFpbCI6ICJ0ZXN0QGV4YW1wbGUuY29tIiwgInN1YiI6ICJ1c2VyXzEyMyJ9.signature"
    claims = decode_jwt_payload(fake_jwt)
    assert claims.get("email") == "test@example.com"
    assert claims.get("sub") == "user_123"


@pytest.mark.asyncio
async def test_chatgpt_oauth_start_endpoint() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/auth/chatgpt/oauth/start?ticket=ticket-abc-123")
        assert resp.status_code == 200
        data = resp.json()
        assert "auth_url" in data
        assert "port" in data
        assert "state" in data
        assert "https://auth.openai.com/oauth/authorize" in data["auth_url"]
        assert f"client_id={OPENAI_CLIENT_ID}" in data["auth_url"]
