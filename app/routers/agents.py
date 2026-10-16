
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.services.assignment_service import assign_pending_tickets
from app.auth.dependencies import require_roles
from app.auth.security import hash_password
from app.database import get_db
from app.models.entities import Agent, Category
from app.schemas.agent import (
    AgentCreate,
    AgentResponse,
    AgentUpdate,
    AvailabilityUpdate,
)


router = APIRouter(prefix="/agents", tags=["Agents"])

AdminUser = Annotated[dict, Depends(require_roles("Admin"))]
AgentOrAdmin = Annotated[
    dict, Depends(require_roles("Agent", "Admin"))
]
Database = Annotated[AsyncSession, Depends(get_db)]


async def load_agent(db: AsyncSession, agent_id: int):
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.categories))
        .where(Agent.id == agent_id)
    )
    return result.scalar_one_or_none()


def serialize_agent(agent: Agent) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "email": agent.email,
        "category_ids": [category.id for category in agent.categories],
        "availability": (
            "Online" if agent.is_available else "Offline"
        ),
        "max_open_tickets": agent.max_open_tickets,
        "is_active": agent.is_active,
    }


async def validate_categories(
    db: AsyncSession,
    category_ids: list[int],
):
    if len(category_ids) != len(set(category_ids)):
        raise HTTPException(
            status_code=422,
            detail="Duplicate category IDs are not allowed",
        )

    if not category_ids:
        return []

    result = await db.execute(
        select(Category).where(Category.id.in_(category_ids))
    )
    categories = result.scalars().all()

    if len(categories) != len(category_ids):
        raise HTTPException(
            status_code=422,
            detail="One or more category IDs do not exist",
        )

    return list(categories)


@router.post(
    "",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(
    data: AgentCreate,
    db: Database,
    current_user: AdminUser,
):
    existing = await db.execute(
        select(Agent).where(Agent.email == data.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Agent email is already registered",
        )

    categories = await validate_categories(db, data.category_ids)

    agent = Agent(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role="Agent",
        is_active=True,
        is_available=False,
        max_open_tickets=data.max_open_tickets,
        categories=categories,
    )

    try:
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email is already registered",
        )

    agent = await load_agent(db, agent.id)
    return serialize_agent(agent)


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    db: Database,
    current_user: AdminUser,
):
    result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.categories))
        .order_by(Agent.id)
    )
    agents = result.scalars().all()
    return [serialize_agent(agent) for agent in agents]


@router.put(
    "/me/availability",
    response_model=AgentResponse,
)
async def update_my_availability(
    data: AvailabilityUpdate,
    db: Database,
    current_user: AgentOrAdmin,
):
    if current_user["account_type"] != "agent":
        raise HTTPException(
            status_code=403,
            detail="Only agent accounts can update availability",
        )

    agent = await load_agent(db, current_user["id"])
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.is_available = data.availability == "Online"

    await db.commit()
    agent = await load_agent(db, agent.id)
    return serialize_agent(agent)


@router.put(
    "/{agent_id}",
    response_model=AgentResponse,
)
async def update_agent(
    agent_id: int,
    data: AgentUpdate,
    db: Database,
    current_user: AdminUser,
):
    agent = await load_agent(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    updates = data.model_dump(exclude_unset=True)

    if "email" in updates and updates["email"] is not None:
        result = await db.execute(
            select(Agent).where(
                Agent.email == updates["email"],
                Agent.id != agent_id,
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="Email is already registered",
            )

    if "category_ids" in updates and updates["category_ids"] is not None:
        agent.categories = await validate_categories(
            db, updates.pop("category_ids")
        )

    for field, value in updates.items():
        if value is not None:
            setattr(agent, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Update conflicts with an existing record",
        )

    agent = await load_agent(db, agent_id)
    return serialize_agent(agent)

from sqlalchemy import select

from app.models.entities import Ticket
from app.services.assignment_service import OPEN_TICKET_STATUSES


@router.get("/me/tickets")
async def get_my_tickets(
    db: Database,
    current_user: AgentOrAdmin,
    include_closed: bool = False,
):
    if current_user["role"] != "Agent":
        raise HTTPException(
            403,
            "This endpoint is only for Agent accounts",
        )

    query = select(Ticket).where(
        Ticket.agent_id == current_user["id"]
    )

    if not include_closed:
        query = query.where(
            Ticket.status.in_(OPEN_TICKET_STATUSES)
        )

    query = query.order_by(Ticket.created_at.desc())

    result = await db.execute(query)
    tickets = result.scalars().all()

    return [
        {
            "id": ticket.id,
            "ticket_number": ticket.ticket_number,
            "subject": ticket.subject,
            "priority": ticket.priority,
            "status": ticket.status,
            "category_id": ticket.category_id,
            "customer_id": ticket.customer_id,
            "created_at": ticket.created_at,
        }
        for ticket in tickets
    ]
