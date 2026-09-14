from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import RecipeAlreadyExists
from app.models import Recipe, Step
from app.schemas.recipe import RecipeCreate


def create_recipe(db_session: Session, recipe_in: RecipeCreate):

    user_id = recipe_in.user_id
    title = recipe_in.title
    stmt = select(Recipe).where(Recipe.user_id == user_id, Recipe.title == title)
    existing_recipe = db_session.execute(stmt).scalar_one_or_none()
    if existing_recipe:
        raise RecipeAlreadyExists(title)

    steps = [Step(**step.model_dump()) for step in recipe_in.steps]

    new_recipe = Recipe(**(recipe_in.model_dump() | {"steps": steps}))
    db_session.add(new_recipe)
    db_session.commit()
    db_session.refresh(new_recipe)
    return new_recipe
