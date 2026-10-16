
from typing import Literal

from pydantic import BaseModel, Field


Priority = Literal["Low", "Medium", "High", "Urgent"]


class SLAPolicyUpdate(BaseModel):
    first_response_minutes: int = Field(gt=0)
    resolution_minutes: int = Field(gt=0)


class SLAPolicyResponse(BaseModel):
    id: int
    priority: Priority
    first_response_minutes: int
    resolution_minutes: int
