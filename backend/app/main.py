from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.logging_setup import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan hook to handle application startup and shutdown tasks."""
    settings = get_settings()
    # Ensure DATA_DIR exists on startup
    Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)
    yield


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

    # Configure strict CORS for frontend integration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Requested-With"],
    )

    @app.get("/health", tags=["Monitoring"])
    def health_check(
        current_settings: Annotated[Settings, Depends(get_settings)],
    ) -> dict[str, str]:
        """Health check endpoint: verifies service status without database or external calls."""
        return {"status": "ok", "env": current_settings.ENV}

    return app


app = create_app()
