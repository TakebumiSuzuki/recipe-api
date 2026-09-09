from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.deps import get_db_session
from app.main import app
from app.models import Base


@pytest.fixture(scope="session")
def engine() -> Generator[Engine]:
    _engine = create_engine(url=get_settings().test_database_uri)
    yield _engine
    _engine.dispose()  # 全テスト終了時に接続プールを破棄


@pytest.fixture(scope="session")
def SessionLocal(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db(engine: Engine) -> Generator[None]:
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# @pytest.fixture()
# def db_session(SessionLocal: sessionmaker[Session]) -> Generator[Session]:
#     db_session = SessionLocal()
#     yield db_session
#     db_session.close()


@pytest.fixture()
def db_session(engine: Engine) -> Generator[Session]:
    connection = engine.connect()
    transaction = connection.begin()

    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def test_client(db_session: Session) -> Generator[TestClient]:
    # dependency_overrides の実体は Python辞書（型は dict[Callable, Callable]）
    app.dependency_overrides[get_db_session] = lambda: db_session
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()
