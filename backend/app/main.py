from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.error_handlers import register_error_handlers
from app.core.logging_config import setup_logging
from app.deps import get_db_session
from app.routes.users import router as users_router

setup_logging()
app = FastAPI()

app.include_router(users_router)

register_error_handlers(app=app)


@app.get("/health")
def db_test(db_session: Annotated[Session, Depends(get_db_session)]) -> dict:
    result = db_session.execute(text("SELECT 1")).scalar()
    if result == 1:
        return {"db": "ok"}
    else:
        return {"db": "ng"}
