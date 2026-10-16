
from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    category_name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class CategoryUpdate(BaseModel):
    category_name: str | None = Field(
        default=None, min_length=2, max_length=100
    )
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class CategoryResponse(BaseModel):
    id: int
    category_name: str
    description: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
