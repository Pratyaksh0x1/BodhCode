from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.ai.tracing import flush_tracing
from app.config import Settings, export_langsmith_env, get_settings
from app.github.ingest import sweep_stale_fetching_repos
from app.logging_setup import setup_logging
from app.routes.auth import router as auth_router
from app.routes.content import router as content_router
from app.routes.explain_chat import router as explain_chat_router
from app.routes.meta import router as meta_router
from app.routes.repos import router as repos_router
from app.routes.settings import router as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan hook to handle application startup and shutdown tasks."""
    settings = get_settings()
    # Export LangSmith environment variables before first traced call
    export_langsmith_env(settings)
    # Ensure DATA_DIR exists on startup
    Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)
    # Recover any ingestion jobs interrupted if server was killed during fetching
    sweep_stale_fetching_repos()
    try:
        yield
    finally:
        flush_tracing()


def create_app() -> FastAPI:
    """Application factory for BodhCode FastAPI backend."""
    setup_logging()
    settings = get_settings()

    app = FastAPI(
        title="BodhCode API",
        version="0.1.0",
        description="BodhCode backend service for repository dependency mapping and AI coding",
        lifespan=lifespan,
    )

    # Configure cookie-based session storage
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.APP_SECRET_KEY,
        session_cookie="bodhcode_session",
        max_age=14 * 24 * 60 * 60,
        same_site="lax",
        https_only=(settings.ENV == "production"),
    )

    # Configure strict CORS for frontend integration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Requested-With"],
    )

    # Register modular routers
    app.include_router(auth_router)
    app.include_router(settings_router)
    app.include_router(repos_router)
    app.include_router(content_router)
    app.include_router(explain_chat_router)
    app.include_router(meta_router)

    if settings.ENV == "development":
        from app.routes.dev import router as dev_router

        app.include_router(dev_router)

    @app.get("/health", tags=["Monitoring"])
    def health_check(
        current_settings: Annotated[Settings, Depends(get_settings)],
    ) -> dict[str, str]:
        """Health check endpoint: verifies service status without database or external calls."""
        return {"status": "ok", "env": current_settings.ENV}

    return app


app = create_app()
