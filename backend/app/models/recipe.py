from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class Difficulty(StrEnum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text())
    servings: Mapped[int]
    cook_time_min: Mapped[int]
    difficulty: Mapped[Difficulty] = mapped_column(
        SAEnum(
            Difficulty,
            values_callable=lambda x: [e.value for e in x],
            native_enum=False,
            create_constraint=True,
            length=10,
            name="difficulty_values",
        )
    )
    source: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSONB())
    )

    # is_published: Mapped[bool] = mapped_column(server_default=text("false"))
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User | None"] = relationship(back_populates="recipes")

    __table_args__ = (
        UniqueConstraint("user_id", "title"),
        CheckConstraint("length(trim(title)) >= 1", name="title_gte"),
        CheckConstraint("servings >= 1", name="servings_gte"),
        CheckConstraint("length(description) <= 5000", name="description_length_lte"),
        CheckConstraint(
            "description IS NULL OR length(trim(description)) >= 1",
            name="description_not_blank",
        ),
        CheckConstraint("cook_time_min >= 1", name="cook_time_gte"),
        Index(None, "source", postgresql_using="gin"),
    )
