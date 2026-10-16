
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models.entities import Agent, Ticket
from app.schemas.ticket_assignment import TicketAssign
from app.services.assignment_service import (
    OPEN_TICKET_STATUSES,
    record_assignment,
)

router = APIRouter(tags=["Ticket Assignment"])

Database = Annotated[AsyncSession, Depends(get_db)]
AdminUser = Annotated[dict, Depends(require_roles("Admin"))]


@router.put("/tickets/{ticket_id}/assign")
async def assign_ticket_manually(
    ticket_id: int,
    payload: TicketAssign,
    db: Database,
    admin: AdminUser,
):
    ticket_result = await db.execute(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .with_for_update()
    )
    ticket = ticket_result.scalar_one_or_none()

    if ticket is None:
        raise HTTPException(404, "Ticket not found")

    if ticket.status in {"Resolved", "Closed"}:
        raise HTTPException(
            400,
            "Resolved or closed tickets cannot be reassigned",
        )

    agent_result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.categories))
        .where(Agent.id == payload.assigned_agent_id)
        .with_for_update()
    )
    new_agent = agent_result.scalar_one_or_none()

    if new_agent is None or not new_agent.is_active:
        raise HTTPException(400, "Agent not found or inactive")

    if new_agent.role != "Agent":
        raise HTTPException(400, "The selected account is not an Agent")

    if not new_agent.is_available:
        raise HTTPException(400, "The selected agent is Offline")

    category_ids = {category.id for category in new_agent.categories}

    if ticket.category_id not in category_ids:
        raise HTTPException(
            400,
            "The agent does not support this ticket category",
        )

    old_agent_id = ticket.agent_id

    if old_agent_id == new_agent.id:
        return {
            "message": "Ticket is already assigned to this agent",
            "ticket_id": ticket.id,
            "assigned_agent_id": new_agent.id,
            "status": ticket.status,
        }

    count_result = await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.agent_id == new_agent.id,
            Ticket.status.in_(OPEN_TICKET_STATUSES),
        )
    )
    open_count = count_result.scalar_one()

    if open_count >= new_agent.max_open_tickets:
        raise HTTPException(
            409,
            "The selected agent has reached their open-ticket limit",
        )

    try:
        await record_assignment(
            db=db,
            ticket=ticket,
            old_agent_id=old_agent_id,
            new_agent=new_agent,
            changed_by_type="Admin",
            changed_by_id=admin["id"],
        )

        await db.commit()
        await db.refresh(ticket)

    except Exception:
        await db.rollback()
        raise

    return {
        "message": "Ticket assigned successfully",
        "ticket_id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "previous_agent_id": old_agent_id,
        "assigned_agent_id": new_agent.id,
        "status": ticket.status,
    }
