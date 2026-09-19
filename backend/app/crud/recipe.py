from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.exceptions import RecipeAlreadyExists, RecipeNotFound, StepNotFound
from app.models import Recipe, RecipeIngredient, Step
from app.models.ingredients import Ingredient
from app.schemas.recipe import RecipeCreate, RecipeUpdate


def create_recipe(db_session: Session, recipe_in: RecipeCreate):
    user_id = recipe_in.user_id
    title = recipe_in.title
    # このアプリでは、user_id の情報なしで送ると、schemaが Noneに設定するようにしてある
    if user_id is not None:
        stmt = select(Recipe).where(Recipe.user_id == user_id, Recipe.title == title)
        existing_recipe = db_session.execute(stmt).scalar_one_or_none()
        if existing_recipe:
            raise RecipeAlreadyExists(title)

    # ここで、steps 項目については Stepモデルのリストが完成
    steps = [Step(**step_in.model_dump()) for step_in in recipe_in.steps]

    # 以下で、ingredients項目の Ingredientモデルのリストを作る
    recipe_ingredients = []
    for ri_in in recipe_in.recipe_ingredients:
        if ri_in.ingredient_name:
            ing_name = ri_in.ingredient_name
            stmt = select(Ingredient).where(Ingredient.name == ing_name)
            existing_ingredient = db_session.execute(stmt).scalar_one_or_none()
            # ingredient_name を送ってきたにもかかわらず、すでに存在していた場合
            if existing_ingredient:
                ri_in.ingredient_id = existing_ingredient.id
                new_ri = RecipeIngredient(
                    **ri_in.model_dump(exclude={"ingredient_name"})
                )
                recipe_ingredients.append(new_ri)

            # 送られてきた ingredient_name を使って新しく Ingredient を作り登録
            else:
                new_ing = Ingredient(name=ing_name)
                new_ri = RecipeIngredient(
                    **(
                        ri_in.model_dump(exclude={"ingredient_name"})
                        | {"ingredient": new_ing}
                    )
                )

                recipe_ingredients.append(new_ri)

        # ingredientの id を送ってきた場合
        elif ri_in.ingredient_id:
            new_ri = RecipeIngredient(**ri_in.model_dump(exclude={"ingredient_name"}))
            recipe_ingredients.append(new_ri)

        else:
            raise RuntimeError(
                "RecipeIngredient must have either ingredient_id or ingredient_name. "
                "This should have been caught by schema validation."
            )

    new_recipe = Recipe(
        **(
            recipe_in.model_dump()
            | {
                "steps": steps,
                "recipe_ingredients": recipe_ingredients,
            }
        )
    )
    db_session.add(new_recipe)
    db_session.commit()
    db_session.refresh(new_recipe)
    return new_recipe


def get_recipe_by_id(db_session: Session, recipe_id: int) -> Recipe | None:
    stmt = (
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(
            selectinload(Recipe.steps),
            selectinload(Recipe.recipe_ingredients).selectinload(
                RecipeIngredient.ingredient
            ),
        )
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

    # user_id が None の場合には　user_id と title の組み合わせのユニーク制約は適用されない。
    if current_recipe.user_id is not None:
        # Recipe.id != current_recipe.id は、元々のタイトルと全く同じタイトルを patch データーに
        # 入れてしまった場合、元々のレコードに対して重複だ、と判断してしまうのを防ぐため。
        stmt = select(Recipe).where(
            Recipe.user_id == current_recipe.user_id,
            Recipe.title == recipe_in.title,
            Recipe.id != current_recipe.id,
        )
        duplicated_recipe = db_session.execute(stmt).scalar_one_or_none()
        if duplicated_recipe:
            raise RecipeAlreadyExists(title=duplicated_recipe.title)

    recipe_update_data = recipe_in.model_dump(exclude={"steps"}, exclude_unset=True)
    for k, v in recipe_update_data.items():
        setattr(current_recipe, k, v)

    if recipe_in.steps is not None:
        current_step_map = {step.id: step for step in current_recipe.steps}

        incoming_step_map = {
            step.id: step for step in recipe_in.steps if step.id is not None
        }
        invalid_step_ids = incoming_step_map.keys() - current_step_map.keys()
        if invalid_step_ids:
            raise StepNotFound(step_ids=list(invalid_step_ids))

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


def delete_recipe(db_session: Session, recipe_id: int):
    stmt = select(Recipe).where(Recipe.id == recipe_id)
    recipe_to_delete = db_session.execute(stmt).scalar_one_or_none()
    if recipe_to_delete is None:
        raise RecipeNotFound(recipe_id=recipe_id)
    db_session.delete(recipe_to_delete)
    db_session.commit()
