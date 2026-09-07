from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.recipe import Recipe


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    bio: Mapped[str | None] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    recipes: Mapped[list["Recipe"]] = relationship(
        back_populates="user", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("length(trim(name)) >= 2", name="name_length_gte"),
        CheckConstraint("length(bio) <= 1000", name="bio_length_lte"),
        CheckConstraint("bio IS NULL or length(trim(bio)) >= 1", name="bio_not_blank"),
        CheckConstraint(
            r"email ~ '^[^@]+@[^@]+\.[^@]+$'", name="email_validation_loose"
        ),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        # Index(None, "email"), unique制約を入れているので不要
    )
