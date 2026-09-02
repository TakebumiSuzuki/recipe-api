from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.deps import get_db_session

app = FastAPI()


@app.get("/health")
def db_test(db_session: Annotated[Session, Depends(get_db_session)]) -> dict:
    result = db_session.execute(text("SELECT 1")).scalar()
    if result == 1:
        return {"db": "ok"}
    else:
        return {"db": "ng"}
