from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.deps import get_db_session
from app.main import app

engine = create_engine(url=get_settings().test_database_uri)
SessionLocal = sessionmaker(autoflush=False, bind=engine)


@pytest.fixture()
def db_session() -> Generator[Session]:
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture()
def test_client(db_session: Session) -> Generator[TestClient]:
    app.dependency_overrides[get_db_session] = lambda: db_session
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
