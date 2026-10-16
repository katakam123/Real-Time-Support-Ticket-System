
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models.entities import Category, Ticket
from app.schemas.category import (
    CategoryCreate,
    CategoryUpdate,
)

router = APIRouter(prefix="/categories", tags=["Categories"])

AdminUser = Annotated[dict, Depends(require_roles("Admin"))]
Database = Annotated[AsyncSession, Depends(get_db)]

OPEN_STATUSES = ["Open", "In Progress", "Pending", "Escalated"]


def serialize_category(category: Category) -> dict:
    return {
        "id": category.id,
        "category_name": category.name,
        "description": category.description,
        "is_active": category.is_active,
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    db: Database,
    current_user: AdminUser,
):
    category_name = payload.category_name.strip()

    if not category_name:
        raise HTTPException(400, "Category name cannot be empty")

    existing = await db.execute(
        select(Category).where(Category.name == category_name)
    )

    if existing.scalar_one_or_none():
        raise HTTPException(409, "Category name already exists")

    category = Category(
        name=category_name,
        description=payload.description,
        is_active=True,
    )

    db.add(category)

    try:
        await db.commit()
        await db.refresh(category)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Category name already exists")

    return serialize_category(category)


@router.get("/")
async def get_categories(
    db: Database,
    current_user: AdminUser,
):
    result = await db.execute(
        select(Category).order_by(Category.id)
    )

    categories = result.scalars().all()

    return [serialize_category(category) for category in categories]


@router.put("/{category_id}")
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: Database,
    current_user: AdminUser,
):
    result = await db.execute(
        select(Category).where(Category.id == category_id)
    )
    category = result.scalar_one_or_none()

    if category is None:
        raise HTTPException(404, "Category not found")

    data = payload.model_dump(exclude_unset=True)

    if "category_name" in data:
        new_name = data.pop("category_name")

        if new_name is None or not new_name.strip():
            raise HTTPException(400, "Category name cannot be empty")

        new_name = new_name.strip()

        duplicate = await db.execute(
            select(Category).where(
                Category.name == new_name,
                Category.id != category_id,
            )
        )

        if duplicate.scalar_one_or_none():
            raise HTTPException(409, "Category name already exists")

        category.name = new_name

    for field in ("description", "is_active"):
        if field in data:
            setattr(category, field, data[field])

    await db.commit()
    await db.refresh(category)

    return serialize_category(category)


@router.delete("/{category_id}")
async def delete_category(
    category_id: int,
    db: Database,
    current_user: AdminUser,
):
    result = await db.execute(
        select(Category).where(Category.id == category_id)
    )
    category = result.scalar_one_or_none()

    if category is None:
        raise HTTPException(404, "Category not found")

    open_ticket_result = await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.category_id == category_id,
            Ticket.status.in_(OPEN_STATUSES),
        )
    )

    if open_ticket_result.scalar_one() > 0:
        raise HTTPException(
            409,
            "Cannot delete a category that has open tickets",
        )

    # Preserve historical tickets that still reference this category.
    ticket_result = await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.category_id == category_id
        )
    )

    if ticket_result.scalar_one() > 0:
        raise HTTPException(
            409,
            "This category is referenced by historical tickets. "
            "Deactivate it instead.",
        )

    await db.delete(category)
    await db.commit()

    return {"message": "Category deleted successfully"}
