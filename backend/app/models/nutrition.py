from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.recipe import Recipe


class Nutrition(Base):
    __tablename__ = "nutritions"

    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True
    )
    calories: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    protein_g: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    fat_g: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    carb_g: Mapped[Decimal] = mapped_column(Numeric(8, 2))

    recipe: Mapped["Recipe"] = relationship(back_populates="nutrition")

    __table_args__ = (
        CheckConstraint("calories >= 0", name="calories_gte"),
        CheckConstraint("protein_g >= 0", name="protein_g_gte"),
        CheckConstraint("fat_g >= 0", name="fat_g_gte"),
        CheckConstraint("carb_g >= 0", name="carb_g_gte"),
    )
