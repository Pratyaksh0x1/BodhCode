from collections.abc import Generator
from typing import Any

from sqlmodel import Session, create_engine

from app.config import get_settings

settings = get_settings()

connect_args: dict[str, Any] = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=connect_args,
)


def get_session() -> Generator[Session, None, None]:
    """Dependency providing a transactional database session."""
    with Session(engine) as session:
        yield session
