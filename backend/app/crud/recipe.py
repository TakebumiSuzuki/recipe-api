from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.exceptions import RecipeAlreadyExists, RecipeNotFound
from app.models import Recipe, Step
from app.schemas.recipe import RecipeCreate, RecipeUpdate


def create_recipe(db_session: Session, recipe_in: RecipeCreate):

    user_id = recipe_in.user_id
    title = recipe_in.title
    if user_id is not None:
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


def get_recipe_by_id(db_session: Session, recipe_id: int) -> Recipe | None:
    stmt = (
        select(Recipe).where(Recipe.id == recipe_id).options(selectinload(Recipe.steps))
    )
    recipe = db_session.execute(stmt).scalar_one_or_none()
    return recipe


def update_recipe(
    db_session: Session,
    recipe_id: int,
    recipe_in: RecipeUpdate,
) -> Recipe:

    stmt = (
        select(Recipe).where(Recipe.id == recipe_id).options(selectinload(Recipe.steps))
    )
    current_recipe = db_session.execute(stmt).scalar_one_or_none()
    if current_recipe is None:
        raise RecipeNotFound(recipe_id)

    recipe_update_data = recipe_in.model_dump(exclude={"steps"}, exclude_unset=True)
    for k, v in recipe_update_data.items():
        setattr(current_recipe, k, v)

    if recipe_in.steps is not None:
        current_step_map = {step.id: step for step in current_recipe.steps}

        incoming_step_map = {
            step.id: step for step in recipe_in.steps if step.id is not None
        }

        step_ids_to_update = current_step_map.keys() & incoming_step_map.keys()
        step_ids_to_delete = current_step_map.keys() - incoming_step_map.keys()
        steps_to_create = [step for step in recipe_in.steps if step.id is None]

        for step_id in step_ids_to_delete:
            db_session.delete(current_step_map[step_id])
        # セッションから実際に commit() の時に送られるSQLの順序は保証されないので、ここで flush で DB の状態を変えておかないとstep の重複のエラーが出るケースが生じてしまう
        db_session.flush()
        for step_id in step_ids_to_update:
            for k, v in (
                incoming_step_map[step_id]
                .model_dump(exclude={"id"}, exclude_unset=True)
                .items()
            ):
                setattr(current_step_map[step_id], k, v)

        for step_in in steps_to_create:
            new_step = Step(**step_in.model_dump(exclude={"id"}))
            current_recipe.steps.append(new_step)

    db_session.commit()
    db_session.refresh(current_recipe)
    return current_recipe
