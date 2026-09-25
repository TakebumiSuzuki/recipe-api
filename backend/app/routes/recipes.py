from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Path, Query
from sqlalchemy.orm import Session

from app.crud import recipe as crud_recipe
from app.deps import get_db_session
from app.exceptions import RecipeNotFound
from app.models import Difficulty, Recipe
from app.schemas.recipe import (
    RecipeCreate,
    RecipeDetail,
    RecipeListResponse,
    RecipeUpdate,
)

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


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(
    db_session: Annotated[Session, Depends(get_db_session)],
    recipe_id: Annotated[int, Path()],
):
    crud_recipe.delete_recipe(db_session=db_session, recipe_id=recipe_id)


@router.get("", response_model=RecipeListResponse)
def get_recipes(
    db_session: Annotated[Session, Depends(get_db_session)],
    tag: Annotated[str | None, Query()] = None,
    difficulty: Annotated[Difficulty | None, Query()] = None,
    user_id: Annotated[int | None, Query()] = None,
    is_published: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:

    recipes, total = crud_recipe.get_recipes(
        db_session=db_session,
        tag=tag,
        difficulty=difficulty,
        user_id=user_id,
        is_published=is_published,
        limit=limit,
        offset=offset,
    )
    result_dic = {
        "items": recipes,
        "total": total,
        "limit": limit,
        "offset": offset,
    }

    return result_dic
