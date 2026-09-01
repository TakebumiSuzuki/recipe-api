from app.core.config import get_settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(url=get_settings().database_uri)

# SQLAlchemy 2.0 の Session は autocommit: Literal[False] = False という型で、False 以外を取れません。
# autoflushについてはデフォルトは True
SessionLocal = sessionmaker(
    autoflush=False,
    bind=engine,
)
