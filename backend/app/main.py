from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app import db
from app.ai.tracing import flush_tracing
from app.auth.scope import ScopeRequiredError, TokenRevokedError
from app.boot_guard import validate_production_boot
from app.cleanup import cleanup_sweep, evict_repo_cache_lru
from app.config import Settings, export_langsmith_env, get_settings
from app.github.ingest import sweep_stale_fetching_repos
from app.logging_setup import setup_logging
from app.middleware.security import (
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.routes.activity import router as activity_router
from app.routes.agent import router as agent_router
from app.routes.auth import router as auth_router
from app.routes.content import router as content_router
from app.routes.explain_chat import router as explain_chat_router
from app.routes.files import router as files_router
from app.routes.issues import router as issues_router
from app.routes.meta import router as meta_router
from app.routes.proposals import router as proposals_router
from app.routes.push import router as push_router
from app.routes.repos import router as repos_router
from app.routes.settings import router as settings_router
from app.routes.terminal import router as terminal_router
from app.routes.workspace import router as workspace_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan hook to handle application startup and shutdown tasks."""
    settings = get_settings()
    validate_production_boot(settings)
    # Export LangSmith environment variables before first traced call
    export_langsmith_env(settings)
    # Ensure DATA_DIR exists on startup
    Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)
    # Recover any ingestion jobs interrupted if server was killed during fetching
    sweep_stale_fetching_repos()
    # Execute database cleanup sweep and disk quota eviction
    try:
        from sqlmodel import Session

        with Session(db.engine) as session:
            cleanup_sweep(session)
            evict_repo_cache_lru(Path(settings.DATA_DIR), session=session)
    except Exception:
        pass
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

    # 1. Security headers (nosniff, referrer, Cache-Control: no-store, CSP)
    app.add_middleware(SecurityHeadersMiddleware)

    # 2. Body size limits (1.5 MB default, 20 KB small)
    app.add_middleware(RequestBodyLimitMiddleware)

    # 3. Configure cookie-based session storage (must execute before inner endpoints)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.APP_SECRET_KEY,
        session_cookie="bodhcode_session",
        max_age=14 * 24 * 60 * 60,
        same_site="lax",
        https_only=(settings.ENV == "production"),
    )

    # 4. Strict CORS (outermost to handle preflight OPTIONS cleanly)
    cors_origins = [settings.FRONTEND_URL] + [
        o for o in settings.ALLOWED_ORIGINS if o != settings.FRONTEND_URL
    ]
    if settings.ENV == "development":
        dev_origins = []
        for origin in cors_origins:
            if "localhost" in origin:
                dev_origins.append(origin.replace("localhost", "127.0.0.1"))
            elif "127.0.0.1" in origin:
                dev_origins.append(origin.replace("127.0.0.1", "localhost"))
        cors_origins.extend(dev_origins)
    cors_origins = list(dict.fromkeys(cors_origins))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Requested-With", "If-Match"],
    )

    @app.exception_handler(ScopeRequiredError)
    async def scope_required_handler(request: Request, exc: ScopeRequiredError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": "scope_required", "needed": exc.needed},
        )

    @app.exception_handler(TokenRevokedError)
    async def token_revoked_handler(request: Request, exc: TokenRevokedError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    # Register modular routers
    app.include_router(auth_router)
    app.include_router(settings_router)
    app.include_router(repos_router)
    app.include_router(content_router)
    app.include_router(explain_chat_router)
    app.include_router(files_router)
    app.include_router(issues_router)
    app.include_router(meta_router)
    app.include_router(agent_router)
    app.include_router(proposals_router)
    app.include_router(push_router)
    app.include_router(activity_router)
    app.include_router(workspace_router)
    app.include_router(terminal_router)

    if settings.ENV == "development":
        from app.routes.dev import router as dev_router

        app.include_router(dev_router)

    @app.get("/health", tags=["Monitoring"])
    def health_check(
        current_settings: Annotated[Settings, Depends(get_settings)],
    ) -> dict[str, str]:
        """Health check endpoint: verifies service status without database or external calls."""
        return {"status": "ok", "env": current_settings.ENV}

    @app.get("/ready", tags=["Monitoring"])
    def readiness_check(
        current_settings: Annotated[Settings, Depends(get_settings)],
    ) -> dict[str, str]:
        """Readiness probe endpoint: verifies application is initialized and ready."""
        return {"status": "ready", "env": current_settings.ENV}

    return app


app = create_app()
