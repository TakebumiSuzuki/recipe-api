from decimal import Decimal
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

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
            "システムエラー：材料IDまたは名前のいずれか一方を指定してください。"
        )


# これは Recipeの update crud のなかの差分判定後の分岐先で使われる
class RecipeIngredientCreateInCRUD(BaseModel):
    recipe_id: int
    ingredient_id: int
    quantity: Decimal = Field(gt=0)
    unit: Unit
    note: str | None = Field(None, max_length=1000, min_length=1)

    @field_validator("note", mode="before")
    @classmethod
    def _empty_to_none(cls, v: Any):
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


class RecipeIngredientPublic(BaseModel):
    recipe_id: int
    ingredient_id: int
    quantity: Decimal
    unit: Unit
    note: str | None
    ingredient: IngredientPublic  # 自動で id と name が展開される

    model_config = ConfigDict(from_attributes=True)  # ★ 追加


# quantity, unit は、updateでありながら、Noneを許容しない。これは実装の簡略化のため、
# フロントからは、全ての　ri をリストにして必要な中身を全て詰めて送るという仕様にするため。
class RecipeIngredientUpdate(BaseModel):
    ingredient_id: int | None = None
    ingredient_name: str | None = Field(None, max_length=50, min_length=1)
    quantity: Decimal = Field(gt=0)
    unit: Unit
    note: str | None = Field(None, max_length=1000, min_length=1)

    @field_validator("quantity", "unit", mode="before")
    @classmethod
    def _cant_be_None(cls, v: Any, info: ValidationInfo):
        if v is None:
            raise ValueError(f"{info.field_name} には値が必要です")
        return v

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
            "システムエラー：材料IDまたは名前のいずれか一方を指定してください。"
        )
