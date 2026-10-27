"""Tests for user settings API and language catalogue."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.service import upsert_github_user
from app.i18n.languages import get_language, is_supported
from app.models.user import User


def test_meta_languages_catalogue(client: TestClient):
    """Verify /meta/languages returns the valid catalogue with required keys and uniqueness."""
    response = client.get("/meta/languages")
    assert response.status_code == 200
    assert "public" in response.headers.get("cache-control", "")

    languages = response.json()
    assert len(languages) >= 31

    codes = set()
    for lang in languages:
        assert "code" in lang
        assert "english_name" in lang
        assert "native_name" in lang
        assert "rtl" in lang
        assert isinstance(lang["rtl"], bool)

        code = lang["code"]
        assert len(code) == 2, f"Language code '{code}' must be two letters"
        assert code.islower(), f"Language code '{code}' must be lowercase"
        assert code not in codes, f"Duplicate language code found: '{code}'"
        codes.add(code)

    # Verify key languages are present
    for expected in ("en", "hi", "ja", "zh", "es", "fr", "ar", "he", "ur"):
        assert expected in codes


def test_language_helpers():
    """Verify is_supported and get_language helper functions."""
    assert is_supported("en") is True
    assert is_supported("HI") is True  # Case insensitive
    assert is_supported("ja ") is True  # Whitespace trimmed
    assert is_supported("xx") is False
    assert is_supported("") is False

    en_lang = get_language("en")
    assert en_lang is not None
    assert en_lang.english_name == "English"
    assert en_lang.rtl is False

    ar_lang = get_language("ar")
    assert ar_lang is not None
    assert ar_lang.rtl is True

    assert get_language("invalid") is None


def test_settings_requires_authentication(client: TestClient):
    """PATCH /auth/me/settings returns 401 when not authenticated."""
    response = client.patch(
        "/auth/me/settings",
        json={"preferred_language": "hi"},
        headers={"X-Requested-With": "bodhcode"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_settings_requires_csrf_header(client: TestClient, db_session: Session):
    """PATCH /auth/me/settings returns 403 when CSRF header is missing or incorrect."""
    user = upsert_github_user(
        db_session,
        github_id=12345,
        login="settings-test-user",
        name="Test User",
        avatar_url="https://avatar.url/1.png",
        email="test@example.com",
        access_token="gho_dummy",
        token_scopes="read:user",
    )

    from app.auth.deps import get_current_user

    client.app.dependency_overrides[get_current_user] = lambda: db_session.get(User, user.id)
    try:
        # Missing CSRF header -> 403
        resp = client.patch("/auth/me/settings", json={"theme": "dark"})
        assert resp.status_code == 403
        assert "CSRF" in resp.json()["detail"]

        # Wrong CSRF header -> 403
        resp_wrong = client.patch(
            "/auth/me/settings",
            json={"theme": "dark"},
            headers={"X-Requested-With": "wrong"},
        )
        assert resp_wrong.status_code == 403
        assert "CSRF" in resp_wrong.json()["detail"]
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


def test_settings_valid_update_persists(client: TestClient, db_session: Session):
    """Verify valid settings updates persist and update /auth/me."""
    user = upsert_github_user(
        db_session,
        github_id=20001,
        login="user-a",
        name="User A",
        avatar_url="https://avatar.url/a.png",
        email="user_a@example.com",
        access_token="gho_token_a",
        token_scopes="read:user",
    )

    from app.auth.deps import get_current_user

    client.app.dependency_overrides[get_current_user] = lambda: db_session.get(User, user.id)
    headers = {"X-Requested-With": "bodhcode"}

    try:
        # Initial verify
        me_resp = client.get("/auth/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["preferred_language"] == "en"
        assert me_resp.json()["theme"] == "dark"
        assert me_resp.json()["editor_theme"] == "auto"

        # 1. Update preferred_language
        resp1 = client.patch(
            "/auth/me/settings",
            json={"preferred_language": "ja"},
            headers=headers,
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["preferred_language"] == "ja"
        assert data1["theme"] == "dark"
        assert data1["editor_theme"] == "auto"

        # Verify DB persisted
        db_user = db_session.get(User, user.id)
        assert db_user.preferred_language == "ja"

        # 2. Update theme
        resp2 = client.patch(
            "/auth/me/settings",
            json={"theme": "light"},
            headers=headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["theme"] == "light"
        assert resp2.json()["preferred_language"] == "ja"

        # 3. Update editor_theme
        resp3 = client.patch(
            "/auth/me/settings",
            json={"editor_theme": "hc-black"},
            headers=headers,
        )
        assert resp3.status_code == 200
        assert resp3.json()["editor_theme"] == "hc-black"

        # 4. Update all together
        resp4 = client.patch(
            "/auth/me/settings",
            json={
                "preferred_language": "hi",
                "theme": "system",
                "editor_theme": "vs-dark",
            },
            headers=headers,
        )
        assert resp4.status_code == 200
        assert resp4.json()["preferred_language"] == "hi"
        assert resp4.json()["theme"] == "system"
        assert resp4.json()["editor_theme"] == "vs-dark"

        # Verify GET /auth/me reflects updated preferences
        me_final = client.get("/auth/me")
        assert me_final.status_code == 200
        assert me_final.json()["preferred_language"] == "hi"
        assert me_final.json()["theme"] == "system"
        assert me_final.json()["editor_theme"] == "vs-dark"

    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


def test_settings_validation_errors(client: TestClient, db_session: Session):
    """Verify invalid values and unknown fields trigger 422 with clear messages."""
    user = upsert_github_user(
        db_session,
        github_id=20002,
        login="user-val",
        name="Validation User",
        avatar_url="https://avatar.url/v.png",
        email="val@example.com",
        access_token="gho_token_val",
        token_scopes="read:user",
    )

    from app.auth.deps import get_current_user

    client.app.dependency_overrides[get_current_user] = lambda: db_session.get(User, user.id)
    headers = {"X-Requested-With": "bodhcode"}

    try:
        # Invalid language code -> 422
        resp_lang = client.patch(
            "/auth/me/settings", json={"preferred_language": "xx"}, headers=headers
        )
        assert resp_lang.status_code == 422
        assert "Unsupported language code" in resp_lang.text

        # Invalid theme -> 422
        resp_theme = client.patch("/auth/me/settings", json={"theme": "solarized"}, headers=headers)
        assert resp_theme.status_code == 422
        assert "Invalid theme" in resp_theme.text

        # Invalid editor theme -> 422
        resp_editor = client.patch(
            "/auth/me/settings", json={"editor_theme": "sublime"}, headers=headers
        )
        assert resp_editor.status_code == 422
        assert "Invalid editor_theme" in resp_editor.text

        # Unknown extra field -> 422 (forbid)
        resp_extra = client.patch(
            "/auth/me/settings", json={"unknown_key": "some_value"}, headers=headers
        )
        assert resp_extra.status_code == 422
        assert "extra_forbidden" in resp_extra.text

    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


def test_user_settings_isolation(client: TestClient, db_session: Session):
    """Verify updating User A's settings does not touch User B's settings."""
    user_a = upsert_github_user(
        db_session,
        github_id=30001,
        login="user-iso-a",
        name="Iso User A",
        avatar_url="https://avatar.url/a.png",
        email="a@iso.com",
        access_token="gho_token_a",
        token_scopes="read:user",
    )
    user_b = upsert_github_user(
        db_session,
        github_id=30002,
        login="user-iso-b",
        name="Iso User B",
        avatar_url="https://avatar.url/b.png",
        email="b@iso.com",
        access_token="gho_token_b",
        token_scopes="read:user",
    )

    from app.auth.deps import get_current_user

    # Act as User A
    client.app.dependency_overrides[get_current_user] = lambda: db_session.get(User, user_a.id)
    headers = {"X-Requested-With": "bodhcode"}

    try:
        resp = client.patch(
            "/auth/me/settings",
            json={
                "preferred_language": "de",
                "theme": "light",
                "editor_theme": "vs",
            },
            headers=headers,
        )
        assert resp.status_code == 200

        # Verify User A was updated
        db_user_a = db_session.get(User, user_a.id)
        assert db_user_a.preferred_language == "de"
        assert db_user_a.theme == "light"
        assert db_user_a.editor_theme == "vs"

        # Verify User B was NOT modified
        db_user_b = db_session.get(User, user_b.id)
        assert db_user_b.preferred_language == "en"
        assert db_user_b.theme == "dark"
        assert db_user_b.editor_theme == "auto"

    finally:
        client.app.dependency_overrides.pop(get_current_user, None)
