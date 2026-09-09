from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserPublic(BaseModel):
    id: int
    name: str = Field(max_length=50)
    email: EmailStr
    bio: str | None = Field(default=None, max_length=1000)
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
