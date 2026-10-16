
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models.entities import SLAPolicy
from app.schemas.sla_policy import (
    Priority,
    SLAPolicyUpdate,
)

router = APIRouter(prefix="/sla-policies", tags=["SLA Policies"])

AdminUser = Annotated[dict, Depends(require_roles("Admin"))]
Database = Annotated[AsyncSession, Depends(get_db)]


def serialize_policy(policy: SLAPolicy) -> dict:
    return {
        "id": policy.id,
        "priority": policy.priority,
        "first_response_minutes": policy.first_response_minutes,
        "resolution_minutes": policy.resolution_minutes,
    }


@router.get("/")
async def get_sla_policies(
    db: Database,
    current_user: AdminUser,
):
    result = await db.execute(
        select(SLAPolicy).order_by(SLAPolicy.id)
    )

    return [
        serialize_policy(policy)
        for policy in result.scalars().all()
    ]


@router.put("/{priority}")
async def update_sla_policy(
    priority: Priority,
    payload: SLAPolicyUpdate,
    db: Database,
    current_user: AdminUser,
):
    result = await db.execute(
        select(SLAPolicy).where(
            SLAPolicy.priority == priority
        )
    )
    policy = result.scalar_one_or_none()

    if policy is None:
        raise HTTPException(
            404,
            "SLA policy not found. Initialize the default policies first.",
        )

    policy.first_response_minutes = payload.first_response_minutes
    policy.resolution_minutes = payload.resolution_minutes

    await db.commit()
    await db.refresh(policy)

    return serialize_policy(policy)
