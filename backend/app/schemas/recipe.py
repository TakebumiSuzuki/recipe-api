from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PositiveInt

from app.models.recipe import Difficulty
from app.schemas.step import StepCreate, StepPublic, StepUpdate
from app.schemas.user import UserSummary


def _strip(v: Any) -> Any:
    return v.strip() if isinstance(v, str) else v


def _empty_to_none(v: Any) -> Any:
    if isinstance(v, str):
        v = v.strip()
        return v if v else None
    return v


RecipeTitle = Annotated[
    str,
    BeforeValidator(_strip),
    Field(min_length=1, max_length=100),
]
RecipeDesc = Annotated[
    Annotated[str, Field(min_length=1, max_length=5000)] | None,
    BeforeValidator(_empty_to_none),
]


class RecipeCreate(BaseModel):
    title: RecipeTitle
    description: RecipeDesc = None
    servings: PositiveInt
    cook_time_min: PositiveInt
    difficulty: Difficulty
    source: dict[str, Any] | None = None
    steps: list[StepCreate] = Field(default_factory=list)


class RecipeUpdate(BaseModel):
    title: RecipeTitle | None = None
    description: RecipeDesc = None
    servings: PositiveInt | None = None
    cook_time_min: PositiveInt | None = None
    difficulty: Difficulty | None = None
    source: dict[str, Any] | None = None
    steps: list[StepUpdate] | None = None


class RecipeSummary(BaseModel):
    id: int
    user_id: int | None
    title: str
    description: str | None
    # servings: int
    cook_time_min: int
    difficulty: Difficulty
    # source: dict[str, Any] | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    user: UserSummary | None

    model_config = ConfigDict(from_attributes=True)


class RecipeDetail(BaseModel):
    id: int
    user_id: int | None
    title: str
    description: str | None
    servings: int
    cook_time_min: int
    difficulty: Difficulty
    source: dict[str, Any] | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    user: UserSummary | None
    steps: list[StepPublic]

    model_config = ConfigDict(from_attributes=True)
