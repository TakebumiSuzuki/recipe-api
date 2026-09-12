from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import UserAlreadyExists, UserNotFound
from app.models import User
from app.schemas.user import UserCreate, UserUpdate


def get_users(db_session: Session) -> Sequence[User]:
    stmt = select(User).order_by(User.id.desc())
    result = db_session.execute(stmt).scalars().all()
    return result


def get_user_by_id(db_session: Session, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id)
    result = db_session.execute(stmt).scalar_one_or_none()
    return result


def get_user_by_email(db_session: Session, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    result = db_session.execute(stmt).scalar_one_or_none()
    return result


def create_user(db_session: Session, user_in: UserCreate) -> User:
    existing_user = get_user_by_email(db_session=db_session, email=user_in.email)
    if existing_user:
        raise UserAlreadyExists(user_in.email)
    new_user = User(**user_in.model_dump())
    db_session.add(new_user)
    db_session.commit()
    db_session.refresh(new_user)
    return new_user


def update_user(db_session: Session, user_id: int, user_in: UserUpdate) -> User:
    user = get_user_by_id(db_session=db_session, user_id=user_id)
    if user is None:
        raise UserNotFound(user_id=user_id)
    if user_in.email:
        existing_user = get_user_by_email(db_session=db_session, email=user_in.email)
        if existing_user and existing_user.id != user.id:
            raise UserAlreadyExists(email=user_in.email)
    for key, value in user_in.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db_session.commit()
    db_session.refresh(user)
    return user
