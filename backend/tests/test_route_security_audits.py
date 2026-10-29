"""Security audit tests: route authentication, CSRF enforcement, and ownership isolation.

Ensures no route can be exposed without proper authentication and CSRF guards,
and that multi-tenant resource access is strictly isolated (User B gets 404 on User A resources).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.auth.crypto import encrypt_token
from app.auth.deps import get_current_user, require_csrf_header
from app.db import get_session
from app.main import create_app
from app.models.proposals import Proposal
from app.models.push import PushPreview
from app.models.repo import Repo
from app.models.user import User

# Explicit allow-list of public endpoints that do not require get_current_user
PUBLIC_AUTH_ALLOWLIST: frozenset[str] = frozenset(
    {
        "/health",
        "/ready",
        "/meta/languages",
        "/auth/github/login",
        "/auth/github/upgrade",
        "/auth/github/callback",
        "/auth/github/upgrade/callback",
        "/auth/logout",
    }
)

# Openapi / documentation endpoints generated automatically
DOCS_ALLOWLIST: frozenset[str] = frozenset(
    {
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
)

# Mutating routes exempt from X-Requested-With header (browser redirects from external OAuth)
CSRF_EXEMPT_MUTATING: frozenset[str] = frozenset(
    {
        "/auth/github/callback",
        "/auth/github/upgrade/callback",
    }
)


def _collect_all_api_routes(app: Any) -> list[APIRoute]:
    """Recursively collect all APIRoute instances registered on the application."""
    routes: list[APIRoute] = []

    def _traverse(router_or_item: Any) -> None:
        sub_routes = getattr(router_or_item, "routes", None)
        if sub_routes:
            for r in sub_routes:
                if isinstance(r, APIRoute):
                    routes.append(r)
                elif hasattr(r, "original_router"):
                    _traverse(r.original_router)
                elif hasattr(r, "routes"):
                    _traverse(r)

    _traverse(app.router)
    # Deduplicate while preserving order
    seen: set[tuple[str, frozenset[str]]] = set()
    unique_routes: list[APIRoute] = []
    for r in routes:
        key = (r.path, frozenset(r.methods))
        if key not in seen:
            seen.add(key)
            unique_routes.append(r)
    return unique_routes


def _has_dependency(route: APIRoute, target_dep: Any) -> bool:
    """Check if target_dep exists anywhere in the route's dependency hierarchy."""
    dependant = getattr(route, "dependant", None)
    if not dependant:
        return False

    def _search_deps(deps: list[Any]) -> bool:
        for d in deps:
            if getattr(d, "call", None) == target_dep:
                return True
            if _search_deps(getattr(d, "dependencies", [])):
                return True
        return False

    return _search_deps(dependant.dependencies)


def test_routes_auth_audit() -> None:
    """Enumerate ALL routes and assert every non-public route depends on get_current_user."""
    app = create_app()
    all_routes = _collect_all_api_routes(app)
    assert len(all_routes) > 10, "Failed to discover application routes"

    unprotected: list[tuple[str, set[str]]] = []

    for route in all_routes:
        path = route.path
        if path in DOCS_ALLOWLIST or path in PUBLIC_AUTH_ALLOWLIST:
            continue
        # Also check development route exemptions if present
        if path.startswith("/dev/"):
            continue

        if not _has_dependency(route, get_current_user):
            unprotected.append((path, set(route.methods)))

    assert not unprotected, (
        f"Found {len(unprotected)} non-public route(s) missing `get_current_user`: {unprotected}"
    )


def test_routes_csrf_audit() -> None:
    """Enumerate all POST/PUT/PATCH/DELETE routes and assert require_csrf_header is present."""
    app = create_app()
    all_routes = _collect_all_api_routes(app)
    mutating_methods = {"POST", "PUT", "PATCH", "DELETE"}

    missing_csrf: list[tuple[str, set[str]]] = []

    for route in all_routes:
        mutating = set(route.methods).intersection(mutating_methods)
        if not mutating:
            continue

        path = route.path
        if path in CSRF_EXEMPT_MUTATING:
            continue
        if path.startswith("/dev/"):
            continue

        if not _has_dependency(route, require_csrf_header):
            missing_csrf.append((path, mutating))

    assert not missing_csrf, (
        f"Found {len(missing_csrf)} mutating route(s) missing `require_csrf_header`: {missing_csrf}"
    )


# ---------------------------------------------------------------------------
# Parametrized Resource Ownership Tests (User B always gets 404)
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_db_and_client() -> Generator[tuple[Session, TestClient, User, User], None, None]:
    """Provide isolated in-memory test database, test client, and two distinct users."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)

    app = create_app()

    def get_session_override() -> Session:
        return session

    app.dependency_overrides[get_session] = get_session_override

    # Create User A and User B
    enc_token = encrypt_token("gho_test_token_12345")
    user_a = User(
        github_id=1001,
        login="usera",
        avatar_url="https://avatars.githubusercontent.com/u/1001",
        encrypted_github_token=enc_token,
        token_scopes="read:user,repo",
    )
    user_b = User(
        github_id=1002,
        login="userb",
        avatar_url="https://avatars.githubusercontent.com/u/1002",
        encrypted_github_token=enc_token,
        token_scopes="read:user,repo",
    )
    session.add(user_a)
    session.add(user_b)
    session.commit()
    session.refresh(user_a)
    session.refresh(user_b)

    client = TestClient(app)

    yield session, client, user_a, user_b

    session.close()


@pytest.mark.parametrize(
    ("method", "path_template", "payload"),
    [
        ("GET", "/repos/{repo_id}", None),
        ("POST", "/repos/{repo_id}/refresh", None),
        ("DELETE", "/repos/{repo_id}", None),
        ("POST", "/repos/{repo_id}/analyze", None),
        ("GET", "/repos/{repo_id}/graph", None),
        ("GET", "/repos/{repo_id}/blast?file=src/index.ts", None),
        ("GET", "/repos/{repo_id}/deps?file=src/index.ts", None),
        ("GET", "/repos/{repo_id}/cycles", None),
        ("GET", "/repos/{repo_id}/readme", None),
        ("GET", "/repos/{repo_id}/issues", None),
        ("GET", "/repos/{repo_id}/pulls", None),
        ("GET", "/repos/{repo_id}/files", None),
        ("GET", "/repos/{repo_id}/changes", None),
        ("GET", "/repos/{repo_id}/proposals", None),
        ("POST", "/repos/{repo_id}/push", {"preview_id": "prev-123"}),
        ("PATCH", "/repos/{repo_id}/language", {"preferred_language": "Hindi"}),
    ],
)
def test_repo_ownership_user_b_gets_404(
    isolated_db_and_client: tuple[Session, TestClient, User, User],
    method: str,
    path_template: str,
    payload: dict[str, Any] | None,
) -> None:
    """User B accessing User A's repo always receives 404 Not Found."""
    session, client, user_a, user_b = isolated_db_and_client

    repo_a = Repo(
        user_id=user_a.id,
        owner="usera",
        name="private-repo",
        default_branch="main",
        status="ready",
    )
    session.add(repo_a)
    session.commit()
    session.refresh(repo_a)

    path = path_template.format(repo_id=repo_a.id)

    # Act as User B
    client.app.dependency_overrides[get_current_user] = lambda: user_b
    headers = {"X-Requested-With": "bodhcode"}

    if method == "GET":
        resp = client.get(path, headers=headers)
    elif method == "POST":
        resp = client.post(path, json=payload or {}, headers=headers)
    elif method == "DELETE":
        resp = client.delete(path, headers=headers)
    elif method == "PATCH":
        resp = client.patch(path, json=payload or {}, headers=headers)
    else:
        pytest.fail(f"Unsupported method {method}")

    assert resp.status_code == 404, (
        f"User B expected 404 on User A's repo ({method} {path}), "
        f"got {resp.status_code}: {resp.text}"
    )


def test_proposal_ownership_user_b_gets_404(
    isolated_db_and_client: tuple[Session, TestClient, User, User],
) -> None:
    """User B accessing User A's proposal receives 404 Not Found."""
    session, client, user_a, user_b = isolated_db_and_client

    repo_a = Repo(
        user_id=user_a.id,
        owner="usera",
        name="repo-prop",
        default_branch="main",
        status="ready",
    )
    session.add(repo_a)
    session.commit()
    session.refresh(repo_a)

    proposal_a = Proposal(
        user_id=user_a.id,
        repo_id=repo_a.id,
        kind="edit",
        path="src/index.ts",
        old_content="old",
        new_content="new",
        rationale="update",
        status="pending",
    )
    session.add(proposal_a)
    session.commit()
    session.refresh(proposal_a)

    client.app.dependency_overrides[get_current_user] = lambda: user_b
    headers = {"X-Requested-With": "bodhcode"}

    # Attempt accept, reject, edit, undo
    r1 = client.post(f"/proposals/{proposal_a.id}/accept", headers=headers)
    assert r1.status_code == 404, f"Expected 404, got {r1.status_code}"

    r2 = client.post(f"/proposals/{proposal_a.id}/reject", headers=headers)
    assert r2.status_code == 404, f"Expected 404, got {r2.status_code}"

    r3 = client.put(f"/proposals/{proposal_a.id}", json={"new_content": "hacked"}, headers=headers)
    assert r3.status_code == 404, f"Expected 404, got {r3.status_code}"

    r4 = client.post(f"/proposals/{proposal_a.id}/undo", headers=headers)
    assert r4.status_code == 404, f"Expected 404, got {r4.status_code}"


def test_preview_ownership_user_b_gets_404(
    isolated_db_and_client: tuple[Session, TestClient, User, User],
) -> None:
    """User B editing User A's push preview receives 404 Not Found."""
    session, client, user_a, user_b = isolated_db_and_client

    repo_a = Repo(
        user_id=user_a.id,
        owner="usera",
        name="repo-preview",
        default_branch="main",
        status="ready",
    )
    session.add(repo_a)
    session.commit()
    session.refresh(repo_a)

    preview_a = PushPreview(
        id="preview-abc-123",
        user_id=user_a.id,
        repo_id=repo_a.id,
        kind="push",
        payload='{"texts": {"pr_title": {"translated": "test"}}}',
        payload_hash="hash123",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    session.add(preview_a)
    session.commit()

    client.app.dependency_overrides[get_current_user] = lambda: user_b
    headers = {"X-Requested-With": "bodhcode"}

    resp = client.post(
        f"/repos/{repo_a.id}/push/preview/{preview_a.id}/edit",
        json={"pr_title": "attacker title"},
        headers=headers,
    )
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
