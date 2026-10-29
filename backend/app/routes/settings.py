"""User settings management API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, field_validator
from sqlmodel import Session

from app.auth.crypto import encrypt_token
from app.auth.deps import get_current_user, require_csrf_header
from app.db import get_session
from app.i18n.languages import is_supported
from app.models.user import User, UserPublic

router = APIRouter(prefix="/auth", tags=["Settings"])

THEME_VALUES: tuple[str, ...] = ("system", "light", "dark")
EDITOR_THEME_VALUES: tuple[str, ...] = ("auto", "vs", "vs-dark", "hc-black", "hc-light")
REVIEW_MODE_VALUES: tuple[str, ...] = ("review", "auto", "readonly")
GROK_MODEL_VALUES: tuple[str, ...] = ("gpt-oss-120b", "grok-2", "grok-beta", "grok-vision-beta")


class UserSettings(BaseModel):
    """Extensible user settings schema.

    Later phases can add settings here without rewriting update logic.
    Unknown fields are strictly forbidden with HTTP 422.
    """

    model_config = ConfigDict(extra="forbid")

    preferred_language: str | None = None
    theme: str | None = None
    editor_theme: str | None = None
    review_mode: str | None = None
    grok_api_key: str | None = None
    grok_model: str | None = None

    @field_validator("preferred_language")
    @classmethod
    def validate_language(cls, v: str | None) -> str | None:
        if v is not None:
            clean_code = v.lower().strip()
            if not is_supported(clean_code):
                raise ValueError(
                    f"Unsupported language code '{v}'. See /meta/languages for supported languages."
                )
            return clean_code
        return v

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, v: str | None) -> str | None:
        if v is not None:
            clean_theme = v.lower().strip()
            if clean_theme not in THEME_VALUES:
                raise ValueError(f"Invalid theme '{v}'. Allowed values: {', '.join(THEME_VALUES)}.")
            return clean_theme
        return v

    @field_validator("editor_theme")
    @classmethod
    def validate_editor_theme(cls, v: str | None) -> str | None:
        if v is not None:
            clean_theme = v.strip()
            if clean_theme not in EDITOR_THEME_VALUES:
                raise ValueError(
                    f"Invalid editor_theme '{v}'. Allowed values: {', '.join(EDITOR_THEME_VALUES)}."
                )
            return clean_theme
        return v

    @field_validator("review_mode")
    @classmethod
    def validate_review_mode(cls, v: str | None) -> str | None:
        if v is not None:
            clean_mode = v.lower().strip()
            if clean_mode not in REVIEW_MODE_VALUES:
                raise ValueError(
                    f"Invalid review_mode '{v}'. Allowed values: {', '.join(REVIEW_MODE_VALUES)}."
                )
            return clean_mode
        return v

    @field_validator("grok_model")
    @classmethod
    def validate_grok_model(cls, v: str | None) -> str | None:
        if v is not None:
            clean_model = v.lower().strip()
            if clean_model not in GROK_MODEL_VALUES:
                raise ValueError(
                    f"Invalid grok_model '{v}'. Allowed values: {', '.join(GROK_MODEL_VALUES)}."
                )
            return clean_model
        return v


def to_user_public(user: User) -> UserPublic:
    """Convert User db model to UserPublic exposing only safe fields."""
    return UserPublic(
        id=user.id,
        login=user.login,
        name=user.name,
        avatar_url=user.avatar_url,
        email=user.email,
        preferred_language=user.preferred_language,
        theme=user.theme,
        editor_theme=user.editor_theme,
        review_mode=user.review_mode,
        grok_configured=bool(user.encrypted_grok_key),
        grok_model=user.grok_model or "gpt-oss-120b",
    )


def apply_user_settings(user: User, settings: UserSettings, session: Session) -> UserPublic:
    """Apply validated settings to user model and persist to database.

    Modularized in one place so future settings additions require zero rewrites.
    """
    data = settings.model_dump(exclude_unset=True)
    for field_name, val in data.items():
        if field_name == "grok_api_key":
            if val is not None:
                stripped = val.strip()
                user.encrypted_grok_key = encrypt_token(stripped) if stripped else None
        elif field_name == "grok_model":
            if val is not None:
                user.grok_model = val
        elif val is not None and hasattr(user, field_name):
            setattr(user, field_name, val)
    session.add(user)
    session.commit()
    session.refresh(user)
    return to_user_public(user)


@router.patch("/me/settings", response_model=UserPublic)
def update_user_settings(
    settings: UserSettings,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[None, Depends(require_csrf_header)],
) -> UserPublic:
    """Update settings for the currently authenticated user."""
    return apply_user_settings(current_user, settings, session)
