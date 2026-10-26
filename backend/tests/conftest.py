from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app


@pytest.fixture(name="db_session")
def db_session_fixture() -> Generator[Session, None, None]:
    """In-memory SQLite test database fixture."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient fixture with app lifespan handling and DB session override."""
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app, base_url="http://localhost:8000") as test_client:
        yield test_client
    app.dependency_overrides.clear()
