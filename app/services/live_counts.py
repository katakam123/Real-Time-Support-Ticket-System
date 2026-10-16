
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Agent, Ticket
from app.websockets.notification_manager import notification_manager


OPEN_TICKET_STATUSES = [
    "Open",
    "Assigned",
    "In Progress",
    "Waiting on Customer",
]


async def push_open_ticket_counts(db: AsyncSession):
    # Total open tickets for the Admin dashboard
    result = await db.execute(
        select(func.count(Ticket.id)).where(
            Ticket.status.in_(OPEN_TICKET_STATUSES)
        )
    )
    total_open = result.scalar_one()

    # Open tickets grouped by assigned Agent
    result = await db.execute(
        select(Ticket.agent_id, func.count(Ticket.id))
        .where(
            Ticket.status.in_(OPEN_TICKET_STATUSES),
            Ticket.agent_id.is_not(None),
        )
        .group_by(Ticket.agent_id)
    )
    counts_by_agent = dict(result.all())

    result = await db.execute(
        select(Agent).where(Agent.is_active.is_(True))
    )
    agents = result.scalars().all()

    for agent in agents:
        if agent.role == "Admin":
            user_key = ("Admin", agent.id)
            count = total_open
        else:
            user_key = ("Agent", agent.id)
            count = counts_by_agent.get(agent.id, 0)

        await notification_manager.send_to_user(
            user_key,
            {
                "event": "open_ticket_count",
                "data": {"count": count},
            },
        )
