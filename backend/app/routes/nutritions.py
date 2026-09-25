from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path
from sqlalchemy.orm import Session

from app.crud import nutrition as crud_nutrition
from app.deps import get_db_session
from app.models.nutrition import Nutrition
from app.schemas.nutrition import NutritionCreate, NutritionPublic

router = APIRouter(prefix="/api/v1", tags=["nutritions"])


@router.put(
    "/recipes/{recipe_id}/nutrition", response_model=NutritionPublic, status_code=201
)
def add_nutrition(
    db_session: Annotated[Session, Depends(get_db_session)],
    recipe_id: Annotated[int, Path(ge=1)],
    nutrition_in: Annotated[NutritionCreate, Body()],
) -> Nutrition:
    result = crud_nutrition.add_nutrition(
        db_session=db_session, recipe_id=recipe_id, nutrition_in=nutrition_in
    )
    return result


@router.delete("/recipes/{recipe_id}/nutrition", status_code=204)
def delete_nutrition(
    db_session: Annotated[Session, Depends(get_db_session)],
    recipe_id: Annotated[int, Path(ge=1)],
) -> None:
    crud_nutrition.delete_nutrition(
        db_session=db_session,
        recipe_id=recipe_id,
    )
