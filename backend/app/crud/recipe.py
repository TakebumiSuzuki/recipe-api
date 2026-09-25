from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.exceptions import (
    InvalidRecipeIngredientInput,
    RecipeAlreadyExists,
    RecipeNotFound,
    StepNotFound,
)
from app.models import Difficulty, Recipe, RecipeIngredient, Step, Tag
from app.models.ingredients import Ingredient
from app.schemas.recipe import RecipeCreate, RecipeUpdate
from app.schemas.recipe_ingredients import RecipeIngredientCreateInCRUD


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
            raise InvalidRecipeIngredientInput()

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
    db_session.refresh(new_recipe, attribute_names=["steps", "recipe_ingredients"])
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
            selectinload(Recipe.tags),
            joinedload(Recipe.nutrition),
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
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(
            selectinload(Recipe.steps),
            selectinload(Recipe.recipe_ingredients).selectinload(
                RecipeIngredient.ingredient
            ),
        )
    )
    current_recipe = db_session.execute(stmt).scalar_one_or_none()
    if current_recipe is None:
        raise RecipeNotFound(recipe_id)

    # 以下の部分は、アップデートする前に、user_id x title のユニーク制約に抵触しないか。
    # 注意: そもそも user_id が None の場合には　user_id と title の
    # 組み合わせのユニーク制約はすり抜ける。
    # また、タイトルの変更データ in が　Noneの場合にはこの作業はスキップする。
    if current_recipe.user_id is not None and recipe_in.title is not None:
        # Recipe.id != current_recipe.id は、元々のタイトルと全く同じタイトルを
        # patch データーに入れてしまった場合、元々のレコードに対して重複だ、
        # と判断してしまうのを防ぐため。
        stmt = select(Recipe).where(
            Recipe.user_id == current_recipe.user_id,
            Recipe.title == recipe_in.title,
            Recipe.id != current_recipe.id,
        )
        conflicting_recipe = db_session.execute(stmt).scalar_one_or_none()
        if conflicting_recipe:
            raise RecipeAlreadyExists(title=conflicting_recipe.title)

    recipe_update_data = recipe_in.model_dump(
        exclude={"steps", "recipe_ingredients"}, exclude_unset=True
    )
    # 入れ子データ (steps, reciepe_ingredients など) 以外の部分のみをまず、書き換え
    for k, v in recipe_update_data.items():
        setattr(current_recipe, k, v)

    # steps の部分の処理。クライアント（ブラウザ）側が実装すべき仕様は、
    # steps に手を加えない場合には stepsキーバリューを一切送らない → 変更なし
    # 1つの step でも変更するなら残したいものも含めて全 step をセットで送る。
    # また、steps: []　というふうに送ると、(Noneではないので)全 step が消える。
    if recipe_in.steps is not None:
        current_step_map = {step.id: step for step in current_recipe.steps}

        incoming_step_map = {
            step_in.id: step_in for step_in in recipe_in.steps if step_in.id is not None
        }
        invalid_step_ids = incoming_step_map.keys() - current_step_map.keys()
        if invalid_step_ids:
            raise StepNotFound(step_ids=list(invalid_step_ids))

        step_ids_to_update = current_step_map.keys() & incoming_step_map.keys()
        step_ids_to_delete = current_step_map.keys() - incoming_step_map.keys()
        steps_to_create = [step_in for step_in in recipe_in.steps if step_in.id is None]

        for delete_id in step_ids_to_delete:
            db_session.delete(current_step_map[delete_id])
        # セッションから実際に commit() の時にまとめて送られるSQLの順序は保証されない
        # ので、ここで flush で DB の状態を変えておかないと step の重複のエラーが出る
        # ケースが生じてしまう
        db_session.flush()

        # exclude={"id"} について、これはなくても良いが、明示的に id は変更していないという
        # 意図を示すため入れている。(ちなみに、PostgreSQL でも SQLAlchemy側 でも、
        # Primary Key（主キー）の値を UPDATE で変更すること自体は可能。)
        for update_id in step_ids_to_update:
            for k, v in (
                incoming_step_map[update_id]
                .model_dump(exclude={"id"}, exclude_unset=True)
                .items()
            ):
                setattr(current_step_map[update_id], k, v)

        for step_in in steps_to_create:
            new_step = Step(**step_in.model_dump(exclude={"id"}))
            current_recipe.steps.append(new_step)

    if recipe_in.recipe_ingredients is not None:
        # sqlalchemyの relationship 機能の仕様で、current_ris は最低でも []。
        # 見つからなくても、Noneにはならない。
        current_ris = current_recipe.recipe_ingredients
        # recipe_id の方は全て同一になるので気にする必要はない。
        current_ris_ing_id_map = {ri.ingredient_id: ri for ri in current_ris}

        incoming_ris_ing_id_map = {}
        incoming_ris_name_map = {}

        for ri_in in recipe_in.recipe_ingredients:
            incoming_ri = ri_in.model_dump(exclude_unset=True)

            has_id = incoming_ri.get("ingredient_id") is not None
            has_name = incoming_ri.get("ingredient_name") is not None

            if has_id and not has_name:
                incoming_ris_ing_id_map[incoming_ri["ingredient_id"]] = incoming_ri
            elif not has_id and has_name:
                ig_name = incoming_ri["ingredient_name"]
                stmt = select(Ingredient).where(Ingredient.name == ig_name)
                result = db_session.execute(stmt).scalar_one_or_none()
                if result is None:
                    incoming_ris_name_map[ig_name] = incoming_ri
                else:
                    # nameを送ってきたけどすでに ingredient が存在しているので、すげ替える
                    del incoming_ri["ingredient_name"]
                    incoming_ri["ingredient_id"] = result.id
                    incoming_ris_ing_id_map[result.id] = incoming_ri
            else:
                raise InvalidRecipeIngredientInput()

        to_delete_ri_ing_ids = (
            current_ris_ing_id_map.keys() - incoming_ris_ing_id_map.keys()
        )
        # 元々繋がっていなかった ing が指定されて送られてきた場合
        to_add_ri_ing_ids = (
            incoming_ris_ing_id_map.keys() - current_ris_ing_id_map.keys()
        )
        to_update_ri_ing_ids = (
            current_ris_ing_id_map.keys() & incoming_ris_ing_id_map.keys()
        )

        for delete_ing_id in to_delete_ri_ing_ids:
            delete_ri = current_ris_ing_id_map[delete_ing_id]
            db_session.delete(delete_ri)

        for update_ing_id in to_update_ri_ing_ids:
            update_ri = current_ris_ing_id_map[update_ing_id]
            update_data = incoming_ris_ing_id_map[update_ing_id]
            update_data.pop("ingredient_name", None)
            update_data.pop("ingredient_id", None)
            # del update_data["ingredient_name"]
            # del update_data["ingredient_id"]
            for k, v in update_data.items():
                setattr(update_ri, k, v)

        # すでにある ingredient_id と recipe_id を使って新しいつながりを作る
        for add_ing_id in to_add_ri_ing_ids:
            add_data = incoming_ris_ing_id_map[add_ing_id]
            add_data.update({"recipe_id": recipe_id})
            new_ri = RecipeIngredient(
                **RecipeIngredientCreateInCRUD(**add_data).model_dump()
            )
            current_recipe.recipe_ingredients.append(new_ri)

        for new_ig_name, create_data in incoming_ris_name_map.items():
            new_ingredient = Ingredient(name=new_ig_name)
            db_session.add(new_ingredient)
            db_session.flush()
            create_data.update(
                {"recipe_id": recipe_id, "ingredient_id": new_ingredient.id}
            )
            new_ri = RecipeIngredient(
                **RecipeIngredientCreateInCRUD(**create_data).model_dump()
            )

            current_recipe.recipe_ingredients.append(new_ri)

    db_session.commit()
    db_session.refresh(current_recipe, attribute_names=["steps", "recipe_ingredients"])
    return current_recipe


def delete_recipe(db_session: Session, recipe_id: int):
    stmt = select(Recipe).where(Recipe.id == recipe_id)
    recipe_to_delete = db_session.execute(stmt).scalar_one_or_none()
    if recipe_to_delete is None:
        raise RecipeNotFound(recipe_id=recipe_id)
    db_session.delete(recipe_to_delete)
    db_session.commit()


def get_recipes(
    db_session: Session,
    tag: str | None,
    difficulty: Difficulty | None,
    user_id: int | None,
    is_published: bool | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[Recipe], int]:

    stmt = select(Recipe)

    if tag:
        stmt = stmt.where(Recipe.tags.any(Tag.name == tag))
    if difficulty:
        stmt = stmt.where(Recipe.difficulty == difficulty)
    if user_id:
        stmt = stmt.where(Recipe.user_id == user_id)
    if is_published is True:
        stmt = stmt.where(Recipe.published_at.is_not(None))
    elif is_published is False:
        stmt = stmt.where(Recipe.published_at.is_(None))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db_session.scalar(count_stmt) or 0

    stmt = (
        stmt.limit(limit)
        .offset(offset)
        .order_by(Recipe.updated_at.desc())
        .options(
            selectinload(Recipe.tags),
            selectinload(Recipe.user),
        )
    )

    recipes = db_session.execute(stmt).scalars().all()

    return recipes, total
