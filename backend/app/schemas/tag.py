from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TagCreate(BaseModel):
    name: str = Field(max_length=30, min_length=1)

    @field_validator("name", mode="before")
    @classmethod
    def trim_str(cls, v: Any):
        if isinstance(v, str):
            return v.strip()
        return v


class TagPublic(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)
