from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class FeedbackCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(
        default=None,
        max_length=2000,
    )

    model_config = ConfigDict(extra="forbid")


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    rating: int
    comment: Optional[str] = None