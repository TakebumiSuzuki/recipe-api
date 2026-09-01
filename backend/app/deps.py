from collections.abc import Generator

from app.core.db import SessionLocal
from sqlalchemy.orm import Session


def get_db_session() -> Generator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
