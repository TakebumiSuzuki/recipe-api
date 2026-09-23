from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.recipe import Recipe


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)

    recipes: Mapped[list["Recipe"]] = relationship(
        secondary="recipe_tags",
        back_populates="tags",
    )

    __table_args__ = (
        CheckConstraint("length(trim(name)) >= 1", name="name_length_gte"),
    )


# クラスは作らず、SQLAlchemy の Table オブジェクトとして定義する
recipe_tags = Table(
    "recipe_tags",
    Base.metadata,
    Column(
        "recipe_id",
        Integer,
        ForeignKey("recipes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
