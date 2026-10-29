"""ChatGPT / OpenAI Codex OAuth integration module.

Implements PKCE-based authorization code flow and token exchange according to
the OpenAI Codex protocol (codex-rs/login).
"""

import asyncio
import base64
import hashlib
import json
import logging
import secrets
import urllib.parse
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# OpenAI official Codex/CLI client ID (from codex-rs/login/src/auth/manager.rs:1784)
OPENAI_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_ISSUER = "https://auth.openai.com"
OPENAI_AUTHORIZE_URL = f"{OPENAI_ISSUER}/oauth/authorize"
OPENAI_TOKEN_URL = f"{OPENAI_ISSUER}/oauth/token"
DEFAULT_PORT = 1455
FALLBACK_PORT = 1457
DEFAULT_SCOPES = "openid profile email offline_access api.connectors.read api.connectors.invoke"

# In-memory store for pending ChatGPT OAuth sessions: state -> SessionData
_CHATGPT_SESSIONS: dict[str, dict[str, Any]] = {}
_ACTIVE_SERVERS: dict[int, Any] = {}


def generate_pkce() -> tuple[str, str]:
    """Generate RFC 7636 PKCE code_verifier and code_challenge (S256).

    Matches codex-rs/login/src/oauth/pkce.rs: 64 random bytes, base64url-encoded without padding.
    """
    verifier_bytes = secrets.token_bytes(64)
    code_verifier = base64.urlsafe_b64encode(verifier_bytes).decode("ascii").rstrip("=")
    challenge_digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_digest).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def decode_jwt_payload(jwt_str: str) -> dict[str, Any]:
    """Safely decode unverified claims from JWT payload without external dependencies."""
    try:
        parts = jwt_str.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1]
            rem = len(payload_b64) % 4
            if rem > 0:
                payload_b64 += "=" * (4 - rem)
            raw = base64.urlsafe_b64decode(payload_b64.encode("ascii")).decode("utf-8")
            return json.loads(raw)
    except Exception as exc:
        logger.warning("Failed to decode JWT payload: %s", exc)
    return {}


def build_chatgpt_authorize_url(
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    state: str,
) -> str:
    """Build the official OpenAI OAuth authorization URL."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": DEFAULT_SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "state": state,
        "originator": "codex_cli_rs",
    }
    return f"{OPENAI_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code_for_tokens(
    code: str,
    code_verifier: str,
    redirect_uri: str,
    client_id: str = OPENAI_CLIENT_ID,
) -> dict[str, Any]:
    """Exchange authorization code for access_token, id_token, and refresh_token."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            OPENAI_TOKEN_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "codex_cli_rs",
            },
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def obtain_api_key(
    id_token: str,
    client_id: str = OPENAI_CLIENT_ID,
) -> str | None:
    """Attempt token-exchange for an OpenAI API key (codex-rs obtain_api_key pattern)."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                OPENAI_TOKEN_URL,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "codex_cli_rs",
                },
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                    "client_id": client_id,
                    "requested_token": "openai-api-key",
                    "subject_token": id_token,
                    "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("access_token")
    except Exception as exc:
        logger.debug("Token exchange for API key returned error: %s", exc)
    return None


SUCCESS_HTML = b"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>ChatGPT Connected \xe2\x80\x94 BodhCode</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #09090b;
      color: #f4f4f5;
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100vh;
      margin: 0;
    }
    .card {
      background: #18181b;
      border: 1px solid #27272a;
      border-radius: 16px;
      padding: 36px 44px;
      text-align: center;
      max-width: 440px;
      box-shadow: 0 25px 50px -12px rgba(0,0,0,0.6);
    }
    .badge {
      display: inline-block;
      padding: 4px 14px;
      background: rgba(34,197,94,0.15);
      color: #4ade80;
      border: 1px solid rgba(34,197,94,0.3);
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      margin-bottom: 16px;
    }
    h1 { font-size: 20px; font-weight: 700; margin: 0 0 10px; color: #ffffff; }
    p { font-size: 13px; color: #a1a1aa; line-height: 1.6; margin: 0; }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">\xe2\x9c\x93 Sign-in Completed</div>
    <h1>Connected to BodhCode Studio</h1>
    <p>Your ChatGPT account is now securely connected.
    You can close this tab and return to the application.</p>
  </div>
  <script>setTimeout(() => window.close(), 3000);</script>
</body>
</html>"""


class ChatGPTCallbackServer:
    """Asynchronous HTTP server that listens on port 1455 (or 1457) for OAuth redirect."""

    def __init__(self, port: int, callback_handler: Any) -> None:
        self.port = port
        self.callback_handler = callback_handler
        self.server: asyncio.Server | None = None

    async def start(self) -> None:
        """Start listening on 127.0.0.1."""
        self.server = await asyncio.start_server(self.handle_client, "127.0.0.1", self.port)
        logger.info("ChatGPT callback server started on 127.0.0.1:%d", self.port)

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle incoming HTTP GET /auth/callback request."""
        try:
            line = await reader.readline()
            if not line:
                writer.close()
                await writer.wait_closed()
                return

            request_line = line.decode("utf-8", errors="replace").strip()
            parts = request_line.split(" ")
            if len(parts) >= 2 and parts[0] == "GET":
                parsed = urllib.parse.urlparse(parts[1])
                if parsed.path == "/auth/callback":
                    query_params = urllib.parse.parse_qs(parsed.query)
                    code = query_params.get("code", [None])[0]
                    state = query_params.get("state", [None])[0]

                    # Respond with HTTP 200 and success page
                    response_headers = (
                        b"HTTP/1.1 200 OK\r\n"
                        b"Content-Type: text/html; charset=utf-8\r\n"
                        b"Connection: close\r\n"
                        b"Content-Length: " + str(len(SUCCESS_HTML)).encode("ascii") + b"\r\n"
                        b"\r\n"
                    )
                    writer.write(response_headers + SUCCESS_HTML)
                    await writer.drain()

                    # Trigger the async callback handler
                    if code and state:
                        asyncio.create_task(self.callback_handler(code, state, self.port))
                    return

            # Default response
            not_found = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            writer.write(not_found)
            await writer.drain()
        except Exception as exc:
            logger.error("Error handling ChatGPT callback request: %s", exc)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def stop(self) -> None:
        """Close the server and stop listening."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
            logger.info("ChatGPT callback server on port %d stopped.", self.port)


async def start_chatgpt_callback_server(
    port: int,
    callback_handler: Any,
) -> ChatGPTCallbackServer:
    """Start and register callback server."""
    global _ACTIVE_SERVERS
    if port in _ACTIVE_SERVERS:
        try:
            await _ACTIVE_SERVERS[port].stop()
        except Exception:
            pass

    server = ChatGPTCallbackServer(port, callback_handler)
    await server.start()
    _ACTIVE_SERVERS[port] = server
    return server


async def stop_chatgpt_callback_server(port: int) -> None:
    """Stop active server if running."""
    global _ACTIVE_SERVERS
    server = _ACTIVE_SERVERS.pop(port, None)
    if server:
        await server.stop()
