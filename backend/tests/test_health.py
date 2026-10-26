from fastapi.testclient import TestClient

from app.config import get_settings


def test_health_check_returns_ok(client: TestClient) -> None:
    """Verify /health endpoint returns status ok and current environment."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["env"] == get_settings().ENV


def test_cors_headers_on_health_check(client: TestClient) -> None:
    """Verify CORS response headers match FRONTEND_URL and allow credentials."""
    settings = get_settings()
    headers = {"Origin": settings.FRONTEND_URL}
    response = client.get("/health", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == settings.FRONTEND_URL
    assert response.headers.get("access-control-allow-credentials") == "true"
