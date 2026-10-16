
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import Agent, Ticket

OPEN_TICKET_STATUSES = [
    "Open",
    "Assigned",
    "In Progress",
    "Waiting on Customer",
]


async def find_available_agent(
    db: AsyncSession,
    category_id: int,
    exclude_agent_id: int | None = None,
):
    # Lock eligible agent rows so concurrent assignments are less
    # likely to exceed an agent's ticket limit.
    query = (
        select(Agent)
        .options(selectinload(Agent.categories))
        .where(
            Agent.is_active.is_(True),
            Agent.is_available.is_(True),
            Agent.role == "Agent",
        )
        .order_by(Agent.id)
        .with_for_update()
    )

    result = await db.execute(query)
    agents = result.scalars().unique().all()

    candidates = []

    for agent in agents:
        if exclude_agent_id is not None and agent.id == exclude_agent_id:
            continue

        supported_category_ids = {
            category.id for category in agent.categories
        }

        if category_id not in supported_category_ids:
            continue

        count_result = await db.execute(
            select(func.count(Ticket.id)).where(
                Ticket.agent_id == agent.id,
                Ticket.status.in_(OPEN_TICKET_STATUSES),
            )
        )
        open_count = count_result.scalar_one()

        if open_count >= agent.max_open_tickets:
            continue

        candidates.append((open_count, agent.id, agent))

    # Fewest open tickets first; agent ID breaks ties deterministically.
    candidates.sort(key=lambda item: (item[0], item[1]))

    return candidates[0][2] if candidates else None

from app.models.entities import (
    AgentNotification,
    StatusHistory,
)


async def record_assignment(
    db: AsyncSession,
    ticket: Ticket,
    old_agent_id: int | None,
    new_agent: Agent,
    changed_by_type: str = "System",
    changed_by_id: int | None = None,
):
    old_status = ticket.status

    ticket.agent_id = new_agent.id

    # A newly assigned ticket moves from Open to Assigned.
    if ticket.status == "Open":
        ticket.status = "Assigned"

        db.add(
            StatusHistory(
                ticket_id=ticket.id,
                old_status=old_status,
                new_status="Assigned",
                changed_by_type=changed_by_type,
                changed_by_id=changed_by_id or 0,
                previous_agent_id=old_agent_id,
                new_agent_id=new_agent.id,
                note=f"Ticket assigned to agent {new_agent.id}",
            )
        )
    else:
        # Reassignment doesn't change the ticket's workflow status.
        db.add(
            StatusHistory(
                ticket_id=ticket.id,
                old_status=old_status,
                new_status=old_status,
                changed_by_type=changed_by_type,
                changed_by_id=changed_by_id or 0,
                previous_agent_id=old_agent_id,
                new_agent_id=new_agent.id,
                note=(
                    f"Ticket reassigned from agent {old_agent_id} "
                    f"to agent {new_agent.id}"
                ),
            )
        )

    # Notify the previous agent if this was a reassignment.
    if old_agent_id is not None and old_agent_id != new_agent.id:
        db.add(
            AgentNotification(
                agent_id=old_agent_id,
                ticket_id=ticket.id,
                message=(
                    f"Ticket {ticket.ticket_number} was reassigned "
                    "to another agent."
                ),
            )
        )

    # Notify the new agent.
    if old_agent_id != new_agent.id:
        db.add(
            AgentNotification(
                agent_id=new_agent.id,
                ticket_id=ticket.id,
                message=(
                    f"Ticket {ticket.ticket_number} has been assigned "
                    "to you."
                ),
            )
        )

async def assign_ticket_automatically(
    db: AsyncSession,
    ticket: Ticket,
):
    if ticket.status != "Open" or ticket.agent_id is not None:
        return None

    agent = await find_available_agent(
        db=db,
        category_id=ticket.category_id,
    )

    if agent is None:
        # Keep the ticket Open and unassigned.
        return None

    await record_assignment(
        db=db,
        ticket=ticket,
        old_agent_id=None,
        new_agent=agent,
        changed_by_type="System",
        changed_by_id=None,
    )

    return agent


async def assign_pending_tickets(db: AsyncSession):
    result = await db.execute(
        select(Ticket)
        .where(
            Ticket.status == "Open",
            Ticket.agent_id.is_(None),
        )
        .order_by(Ticket.created_at.asc(), Ticket.id.asc())
        .with_for_update()
    )

    pending_tickets = result.scalars().all()
    assigned_count = 0

    for ticket in pending_tickets:
        agent = await assign_ticket_automatically(db, ticket)

        if agent is not None:
            assigned_count += 1

    return assigned_count
