from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db_session
from app.models import User
from app.schemas.user import UserPublic

router = APIRouter(prefix="/api/v1/users")


@router.get("", response_model=list[UserPublic])
def get_users(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> Sequence[User]:
    stmt = select(User).order_by(User.id)
    result = db_session.execute(stmt).scalars().all()
    return result
