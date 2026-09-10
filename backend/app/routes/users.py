from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.crud import user as crud_user
from app.deps import get_db_session
from app.exceptions import UserNotFound
from app.models import User
from app.schemas.user import UserPublic

router = APIRouter(prefix="/api/v1/users")


@router.get("", response_model=list[UserPublic])
def get_users(
    db_session: Annotated[Session, Depends(get_db_session)],
) -> Sequence[User]:
    result = crud_user.get_users(db_session=db_session)
    return result


@router.get("/{user_id}", response_model=UserPublic)
def get_user_by_id(
    db_session: Annotated[Session, Depends(get_db_session)],
    user_id: Annotated[int, Path()],
) -> User:
    result = crud_user.get_user_by_id(db_session=db_session, user_id=user_id)
    if result is None:
        raise UserNotFound(user_id=user_id)
    return result
