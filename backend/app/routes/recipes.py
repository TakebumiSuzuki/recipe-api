from typing import Annotated

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.crud import recipe as crud_recipe
from app.deps import get_db_session
from app.models import Recipe
from app.schemas.recipe import RecipeCreate, RecipeDetail

router = APIRouter(prefix="/api/v1/recipes", tags=["recipes"])


@router.post("", response_model=RecipeDetail, status_code=201)
def create_recipe(
    db_session: Annotated[Session, Depends(get_db_session)],
    recipe_in: Annotated[RecipeCreate, Body()],
) -> Recipe:
    result = crud_recipe.create_recipe(db_session=db_session, recipe_in=recipe_in)
    return result
