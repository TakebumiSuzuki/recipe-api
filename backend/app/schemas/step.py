from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PositiveInt


def _strip(v: Any):
    return v.strip() if isinstance(v, str) else v


StepInstruction = Annotated[
    str,
    BeforeValidator(_strip),
    Field(min_length=1, max_length=1000),
]


class StepCreate(BaseModel):
    step_no: PositiveInt
    instruction: StepInstruction


class StepUpdate(BaseModel):
    id: int | None = None
    step_no: PositiveInt
    instruction: StepInstruction


class StepPublic(BaseModel):
    id: int
    recipe_id: int
    step_no: int
    instruction: str

    model_config = ConfigDict(from_attributes=True)
