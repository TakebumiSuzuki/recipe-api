from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path
from sqlalchemy.orm import Session

from app.crud import recipe as crud_recipe
from app.deps import get_db_session
from app.exceptions import RecipeNotFound
from app.models import Recipe
from app.schemas.recipe import RecipeCreate, RecipeDetail, RecipeUpdate

router = APIRouter(prefix="/api/v1/recipes", tags=["recipes"])


@router.post("", response_model=RecipeDetail, status_code=201)
def create_recipe(
    db_session: Annotated[Session, Depends(get_db_session)],
    recipe_in: Annotated[RecipeCreate, Body()],
) -> Recipe:
    result = crud_recipe.create_recipe(db_session=db_session, recipe_in=recipe_in)
    return result


@router.get("/{recipe_id}", response_model=RecipeDetail)
def get_recipe_by_id(
    db_session: Annotated[Session, Depends(get_db_session)],
    recipe_id: Annotated[int, Path()],
) -> Recipe:
    result = crud_recipe.get_recipe_by_id(db_session=db_session, recipe_id=recipe_id)
    if result is None:
        raise RecipeNotFound(recipe_id)
    return result


@router.patch("/{recipe_id}", response_model=RecipeDetail)
def update_recipe(
    db_session: Annotated[Session, Depends(get_db_session)],
    recipe_id: Annotated[int, Path()],
    recipe_in: Annotated[RecipeUpdate, Body()],
) -> Recipe:
    result = crud_recipe.update_recipe(
        db_session=db_session, recipe_id=recipe_id, recipe_in=recipe_in
    )
    return result
