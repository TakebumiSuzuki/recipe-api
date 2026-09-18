from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models import Recipe


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)

    recipe_ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="ingredient",
    )

    __table_args__ = (
        CheckConstraint("length(trim(name)) >= 1", name="name_not_blank"),
    )


class Unit(StrEnum):
    G = "g"
    ML = "ml"
    PIECE = "個"
    TABLESPOON = "大さじ"
    TEASPOON = "小さじ"


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True
    )
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredients.id", ondelete="RESTRICT"), primary_key=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    unit: Mapped[Unit] = mapped_column(
        SAEnum(
            Unit,
            values_callable=lambda x: [e.value for e in x],
            native_enum=False,
            create_constraint=True,
            length=10,
            name="unit_values",
        )
    )
    note: Mapped[str | None] = mapped_column(Text())

    recipe: Mapped["Recipe"] = relationship(back_populates="recipe_ingredients")
    ingredient: Mapped[Ingredient] = relationship(back_populates="recipe_ingredients")

    __table_args__ = (
        CheckConstraint("length(note) <= 1000", name="note_length_lte"),
        CheckConstraint("quantity > 0", name="quantity_gt"),
        CheckConstraint(
            "note IS NULL OR length(trim(note)) >= 1", name="note_not_blank"
        ),
    )
