from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crud import recipe as crud_recipe
from app.exceptions import (
    RecipeNotFound,
    TagAlreadyAttached,
    TagAlreadyExists,
    TagNotFound,
)
from app.models import Tag
from app.schemas.tag import TagCreate


def get_tag_by_name(db_session: Session, tag_name: str) -> Tag | None:
    stmt = select(Tag).where(Tag.name == tag_name)
    result = db_session.execute(stmt).scalar_one_or_none()
    return result


def get_tag_by_id(db_session: Session, tag_id: int) -> Tag | None:
    result = db_session.get(Tag, tag_id)
    return result


def add_tag(db_session: Session, tag_name: str) -> Tag:
    result = get_tag_by_name(db_session=db_session, tag_name=tag_name)
    if result is not None:
        raise TagAlreadyExists(tag_name=tag_name)

    new_tag = Tag(name=tag_name)
    db_session.add(new_tag)
    db_session.commit()
    db_session.refresh(new_tag)
    return new_tag


def delete_tag(db_session: Session, tag_id: int):
    tag = get_tag_by_id(db_session=db_session, tag_id=tag_id)
    if tag is None:
        raise TagNotFound(tag_id=tag_id)
    db_session.delete(tag)
    db_session.commit()


def add_tag_to_recipe(
    db_session: Session, recipe_id: int, tag_in: TagCreate
) -> Sequence[Tag]:
    recipe = crud_recipe.get_recipe_by_id(db_session=db_session, recipe_id=recipe_id)
    if recipe is None:
        raise RecipeNotFound(recipe_id=recipe_id)

    tag_in_db = get_tag_by_name(db_session=db_session, tag_name=tag_in.name)
    if tag_in_db:
        if tag_in.name in [tag.name for tag in recipe.tags]:
            raise TagAlreadyAttached(tag_name=tag_in.name)
        recipe.tags.append(tag_in_db)
    else:
        recipe.tags.append(Tag(name=tag_in.name))
    db_session.commit()

    # db_session.refresh(recipe)と呼んだだけでは、リレーション（入れ子）は同期
    # されず、非同期環境では return recipe.tags の行でクラッシュしてしまう。
    db_session.refresh(recipe, attribute_names=["tags"])

    return recipe.tags


def remove_tag_from_recipe(
    db_session: Session,
    recipe_id: int,
    tag_name: str,
) -> None:
    recipe = crud_recipe.get_recipe_by_id(db_session=db_session, recipe_id=recipe_id)
    if recipe is None:
        raise RecipeNotFound(recipe_id=recipe_id)
    for tag in recipe.tags:
        if tag.name == tag_name:
            recipe.tags.remove(tag)
            break
    db_session.commit()
