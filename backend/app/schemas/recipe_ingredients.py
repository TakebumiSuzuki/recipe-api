from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Unit
from app.schemas.ingredient import IngredientPublic


# Decimal, Unit は pydantic が自動で型変換を試みてくれる。
class RecipeIngredientCreate(BaseModel):
    ingredient_id: int | None = None
    ingredient_name: str | None = Field(None, max_length=50, min_length=1)
    quantity: Decimal = Field(gt=0)
    unit: Unit
    note: str | None = Field(None, max_length=1000, min_length=1)

    @field_validator("ingredient_name", "note", mode="before")
    @classmethod
    def _empty_to_none(cls, v: Any):
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v

    @model_validator(mode="after")
    def id_or_name(self):
        if (self.ingredient_id or self.ingredient_name) and not (
            self.ingredient_id and self.ingredient_name
        ):
            return self
        raise ValueError(
            "システムエラー：材料IDと名前を同時に指定することはできません。"
        )


class RecipeIngredientPublic(BaseModel):
    recipe_id: int
    ingredient_id: int
    quantity: Decimal
    unit: Unit
    note: str | None
    ingredient: IngredientPublic  # 自動で id と name が展開される

    model_config = ConfigDict(from_attributes=True)  # ★ 追加
