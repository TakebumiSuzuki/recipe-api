from datetime import datetime
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PositiveInt,
    ValidationInfo,
    field_validator,
)

from app.models.recipe import Difficulty
from app.schemas.recipe_ingredients import (
    RecipeIngredientCreate,
    RecipeIngredientPublic,
    RecipeIngredientUpdate,
)
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


# default, default_factoryについて。Create系の場合、クライアントからの入力辞書の中に、
# そのキーバリューが存在しない場合には、これらが使われセットされる(しかし、後段で
# exclude_unset が設定されば drop される)。
# 同様に、Read系の場合、from_attributes=Trueで、sqlalchemy モデルにその属性が存在しない
# 場合には、この default, default_factoryが使われ補完される。しかし、通常の使用では、
# SQLAlchemym モデルは通常カラムには必ず何がしかの値が入るし、relationshipカラムでは、
# 該当するデータがない場合には、自動で [] などの空のリストを入れてくれるので、Read系で
# これらが使われることは基本、ないと考えて良い。
class RecipeCreate(BaseModel):
    user_id: int | None = (
        None  # このアプリではログイン機能がないので明示的に注入する仕様にする
    )
    title: RecipeTitle
    description: RecipeDesc = None
    servings: PositiveInt
    cook_time_min: PositiveInt
    difficulty: Difficulty
    source: dict[str, Any] | None = None
    steps: list[StepCreate] = Field(default_factory=list)
    recipe_ingredients: list[RecipeIngredientCreate] = Field(default_factory=list)


class RecipeUpdate(BaseModel):
    title: RecipeTitle | None = None
    description: RecipeDesc = None
    servings: PositiveInt | None = None
    cook_time_min: PositiveInt | None = None
    difficulty: Difficulty | None = None
    source: dict[str, Any] | None = None
    steps: list[StepUpdate] | None = None
    recipe_ingredients: list[RecipeIngredientUpdate] | None = None

    @field_validator("title", "servings", "cook_time_min", "difficulty")
    @classmethod
    def prevent_none_for_required_fields(cls, v: Any, info: ValidationInfo):
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v


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
    recipe_ingredients: list[RecipeIngredientPublic]

    model_config = ConfigDict(from_attributes=True)
