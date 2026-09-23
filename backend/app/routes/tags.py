from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path
from sqlalchemy.orm import Session

from app.crud import tag as crud_tag
from app.deps import get_db_session
from app.models import Tag
from app.schemas.tag import TagCreate, TagPublic

router = APIRouter(prefix="/api/v1", tags=["tags"])


@router.post(
    "/recipes/{recipe_id}/tags", response_model=list[TagPublic], status_code=201
)
def add_tag_to_recipe(
    db_session: Annotated[Session, Depends(get_db_session)],
    recipe_id: Annotated[int, Path()],
    tag_in: Annotated[TagCreate, Body()],
) -> Sequence[Tag]:
    tags = crud_tag.add_tag_to_recipe(
        db_session=db_session,
        recipe_id=recipe_id,
        tag_in=tag_in,
    )
    return tags
