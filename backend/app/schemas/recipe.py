from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.recipe import Difficulty
from app.schemas.step import StepPublic
from app.schemas.user import UserSummary


class RecipeBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str = Field(max_length=100, min_length=1)
    description: str | None = Field(None, max_length=5000, min_length=1)
    cook_time_min: int = Field(ge=1)
    servings: int = Field(ge=1)
    difficulty: Difficulty

    @field_validator("title", mode="before")
    @classmethod
    def process_blank_title(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            return v
        return v

    @field_validator("description", mode="before")
    @classmethod
    def process_blank_description(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


# 一覧用
class RecipeSummary(RecipeBase):
    id: int
    user_id: int | None = Field(ge=1)
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    user: UserSummary | None


class RecipePublic(RecipeSummary):
    source: dict[str, Any] | None
    steps: list[StepPublic]


class RecipeCreate(RecipeBase):
    source: dict[str, Any] | None
    steps: list[StepPublic]


class RecipeUpdate(BaseModel):
    title: str | None = Field(None, max_length=100, min_length=1)
    description: str | None = Field(None, max_length=5000, min_length=1)
    cook_time_min: int | None = Field(None, ge=1)
    servings: int | None = Field(None, ge=1)
    difficulty: Difficulty | None = None
    source: dict[str, Any] | None = None
    steps: list[StepPublic] | None = None

    @field_validator("title", mode="before")
    @classmethod
    def process_blank_title(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            return v
        return v

    @field_validator("description", mode="before")
    @classmethod
    def process_blank_description(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v
