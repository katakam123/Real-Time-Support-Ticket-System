
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    category_ids: list[int] = Field(default_factory=list)
    max_open_tickets: int = Field(default=10, ge=1, le=100)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = None
    category_ids: list[int] | None = None
    max_open_tickets: int | None = Field(default=None, ge=1, le=100)
    is_active: bool | None = None


class AvailabilityUpdate(BaseModel):
    availability: Literal["Online", "Offline"]


class AgentResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    category_ids: list[int]
    availability: Literal["Online", "Offline"]
    max_open_tickets: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
