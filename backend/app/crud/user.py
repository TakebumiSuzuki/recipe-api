from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def get_users(db_session: Session) -> Sequence[User]:
    stmt = select(User).order_by(User.id.desc())
    result = db_session.execute(stmt).scalars().all()
    return result


def get_user_by_id(db_session: Session, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id)
    result = db_session.execute(stmt).scalar_one_or_none()
    return result
