from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserPublic(BaseModel):
    id: int
    name: str = Field(min_length=2, max_length=50)
    email: EmailStr
    bio: str | None = Field(None, max_length=1000)
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    email: EmailStr
    bio: str | None = Field(None, max_length=1000)

    @field_validator("bio", mode="after")
    @classmethod
    def process_blank(cls, bio: str | None):
        if bio is None:
            return None
        stripped = bio.strip()
        if len(stripped) == 0:
            return None
        else:
            return stripped


class UserUpdate(BaseModel):
    # id: int
    name: str | None = Field(None, min_length=2, max_length=50)
    email: EmailStr | None = Field(None)
    bio: str | None = Field(None, max_length=1000)

    @field_validator("bio", mode="after")
    @classmethod
    def process_blank(cls, bio: str | None):
        if bio is None:
            return None
        stripped = bio.strip()
        if len(stripped) == 0:
            return None
        else:
            return stripped
