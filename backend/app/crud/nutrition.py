from sqlalchemy.orm import Session

from app.crud.recipe import get_recipe_by_id
from app.exceptions import RecipeNotFound
from app.models.nutrition import Nutrition
from app.schemas.nutrition import NutritionCreate


def add_nutrition(
    db_session: Session,
    recipe_id: int,
    nutrition_in: NutritionCreate,
) -> Nutrition:
    recipe = get_recipe_by_id(db_session=db_session, recipe_id=recipe_id)
    if recipe is None:
        raise RecipeNotFound(recipe_id=recipe_id)

    new_nutrition = Nutrition(**nutrition_in.model_dump() | {"recipe_id": recipe_id})
    recipe.nutrition = new_nutrition
    db_session.commit()
    db_session.refresh(recipe, attribute_names=["nutrition"])

    return new_nutrition


def delete_nutrition(
    db_session: Session,
    recipe_id: int,
):
    recipe = get_recipe_by_id(db_session=db_session, recipe_id=recipe_id)
    if recipe is None:
        raise RecipeNotFound(recipe_id=recipe_id)

    # ここの実装では、元々から None であった場合にもエラーにならず、
    # エラーにならず、None のままになる。これは問題のない挙動。
    recipe.nutrition = None
    db_session.commit()
