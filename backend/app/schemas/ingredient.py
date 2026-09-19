from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator


class IngredientCreate(BaseModel):
    name: Annotated[str, Field(max_length=50, min_length=1)]

    @field_validator("name", mode="before")
    @classmethod
    def _strip(cls, v: Any):
        if isinstance(v, str):
            return v.strip()
        return v


class IngredientPublic(BaseModel):
    id: int
    name: str
