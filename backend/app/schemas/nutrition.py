from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class NutritionPublic(BaseModel):
    recipe_id: int
    calories: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carb_g: Decimal

    model_config = ConfigDict(from_attributes=True)


# pydantic は、クライアント側が "433.24" のように文字列や、数値で送ってきても、
# Decimal に変換してくれる。
# さらに、ge=0 の様に書くと、decimalのまま大小を比較してくれる。
class NutritionCreate(BaseModel):
    calories: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    protein_g: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    fat_g: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    carb_g: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
