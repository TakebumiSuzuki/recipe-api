from typing import Annotated

from fastapi import Depends, Path
from fastapi.routing import APIRouter
from sqlalchemy.orm import Session

from app.crud import ingredient as crud_ingredient
from app.deps import get_db_session
from app.exceptions import IngredientNotFound
from app.models import Ingredient
from app.schemas.ingredient import IngredientCreate, IngredientPublic

router = APIRouter(prefix="/api/v1/ingredients", tags=["ingredients"])


@router.post("", response_model=IngredientPublic, status_code=201)
def create_ingredient(
    db_session: Annotated[Session, Depends(get_db_session)],
    ingredient_in: IngredientCreate,
) -> Ingredient:
    result = crud_ingredient.create_ingredient(
        db_session=db_session, ingredient_in=ingredient_in
    )
    return result


@router.get("/{ingredient_id}", response_model=IngredientPublic)
def get_ingredient_by_id(
    db_session: Annotated[Session, Depends(get_db_session)],
    ingredient_id: Annotated[int, Path()],
) -> Ingredient:
    result = crud_ingredient.get_ingredient_by_id(
        db_session=db_session, ingredient_id=ingredient_id
    )
    if result is None:
        raise IngredientNotFound(ingredient_id)
    return result


@router.delete("/{ingredient_id}", status_code=204)
def delete_ingredient(
    db_session: Annotated[Session, Depends(get_db_session)],
    ingredient_id: Annotated[int, Path()],
) -> None:
    crud_ingredient.delete_ingredient(
        db_session=db_session, ingredient_id=ingredient_id
    )
