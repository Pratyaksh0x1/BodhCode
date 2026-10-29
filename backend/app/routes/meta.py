"""Public metadata endpoints."""

from fastapi import APIRouter, Response

from app.i18n.languages import SUPPORTED_LANGUAGES, Language

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/languages", response_model=list[Language])
def list_supported_languages(response: Response) -> list[Language]:
    """Retrieve public, cacheable supported languages catalogue."""
    response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"
    return list(SUPPORTED_LANGUAGES)
