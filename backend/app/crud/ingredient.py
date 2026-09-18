from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import IngredientAlreadyExists, IngredientNotFound
from app.models import Ingredient
from app.schemas.ingredient import IngredientCreate


def create_ingredient(
    db_session: Session, ingredient_in: IngredientCreate
) -> Ingredient:
    stmt = select(Ingredient).where(Ingredient.name == ingredient_in.name)
    existing_ingredient = db_session.execute(stmt).scalar_one_or_none()
    if existing_ingredient:
        raise IngredientAlreadyExists(name=ingredient_in.name)

    new_ingredient = Ingredient(**ingredient_in.model_dump())
    db_session.add(new_ingredient)
    db_session.commit()
    db_session.refresh(new_ingredient)
    return new_ingredient


def get_ingredient_by_id(
    db_session: Session,
    ingredient_id: int,
) -> Ingredient | None:
    result = db_session.get(Ingredient, ingredient_id)
    return result


def delete_ingredient(
    db_session: Session,
    ingredient_id: int,
) -> None:
    ingredient = db_session.get(Ingredient, ingredient_id)
    if ingredient is None:
        raise IngredientNotFound(ingredient_id=ingredient_id)
    db_session.delete(ingredient)
    db_session.commit()
