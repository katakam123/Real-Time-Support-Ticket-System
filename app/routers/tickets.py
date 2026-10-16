
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.entities import (
    Agent,
    Category,
    Customer,
    SLAPolicy,
    StatusHistory,
    Ticket,
)
from app.schemas.ticket import (
    TicketCreate,
    TicketPriorityUpdate,
    TicketStatusUpdate,
)

router = APIRouter(prefix="/tickets", tags=["Tickets"])

Database = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[dict, Depends(get_current_user)]

PRIORITIES = {"Low", "Medium", "High", "Urgent"}

ALLOWED_TRANSITIONS = {
    "Open": {"Assigned"},
    "Assigned": {"In Progress"},
    "In Progress": {"Waiting on Customer", "Resolved"},
    "Waiting on Customer": {"In Progress", "Resolved"},
    "Resolved": {"Closed"},
    "Closed": set(),
}


def now_utc():
    return datetime.now(timezone.utc)


def is_admin(user: dict) -> bool:
    return user["role"] == "Admin"


def can_view_ticket(ticket: Ticket, user: dict) -> bool:
    if is_admin(user):
        return True

    if user["role"] == "Customer":
        return (
            user["account_type"] == "customer"
            and ticket.customer_id == user["id"]
        )

    if user["role"] == "Agent":
        return (
            user["account_type"] == "agent"
            and ticket.agent_id == user["id"]
        )

    return False


async def get_ticket_or_404(
    db: AsyncSession,
    ticket_id: int,
) -> Ticket:
    result = await db.execute(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .with_for_update()
    )
    ticket = result.scalar_one_or_none()

    if ticket is None:
        raise HTTPException(404, "Ticket not found")

    return ticket


async def get_sla_policy(
    db: AsyncSession,
    priority: str,
) -> SLAPolicy:
    result = await db.execute(
        select(SLAPolicy).where(SLAPolicy.priority == priority)
    )
    policy = result.scalar_one_or_none()

    if policy is None:
        raise HTTPException(
            500,
            f"SLA policy for priority {priority} is not configured",
        )

    return policy


async def save_status_history(
    db: AsyncSession,
    ticket: Ticket,
    old_status: str,
    new_status: str,
    user: dict,
    note: str | None = None,
):
    history = StatusHistory(
        ticket_id=ticket.id,
        old_status=old_status,
        new_status=new_status,
        changed_by_type=user["role"],
        changed_by_id=user["id"],
        note=note,
    )
    db.add(history)


@router.post("/", status_code=201)
async def create_ticket(
    payload: TicketCreate,
    db: Database,
    user: CurrentUser,
):
    if user["role"] != "Customer":
        raise HTTPException(
            403,
            "Only customers can create tickets",
        )

    category_result = await db.execute(
        select(Category).where(Category.id == payload.category_id)
    )
    category = category_result.scalar_one_or_none()

    if category is None:
        raise HTTPException(404, "Category not found")

    if not category.is_active:
        raise HTTPException(
            400,
            "Cannot create a ticket under an inactive category",
        )

    policy = await get_sla_policy(db, payload.priority)
    created_at = now_utc()

    ticket = Ticket(
        customer_id=user["id"],
        category_id=payload.category_id,
        subject=payload.subject.strip(),
        description=payload.description.strip(),
        priority=payload.priority,
        status="Open",
        agent_id=None,
        first_response_due=created_at + timedelta(
            minutes=policy.first_response_minutes
        ),
        resolution_due=created_at + timedelta(
            minutes=policy.resolution_minutes
        ),
        sla_deadline=created_at + timedelta(
            minutes=policy.resolution_minutes
        ),
        sla_breached=False,
        reopen_count=0,
    )

    try:
        db.add(ticket)
        await db.flush()

        ticket.ticket_number = (
            f"TKT-{created_at:%Y%m%d}-{ticket.id:04d}"
        )

        db.add(
            StatusHistory(
                ticket_id=ticket.id,
                old_status=None,
                new_status="Open",
                changed_by_type=user["role"],
                changed_by_id=user["id"],
                note="Ticket created",
            )
        )

        await db.commit()
        await db.refresh(ticket)
    except Exception:
        await db.rollback()
        raise

    return ticket_response(ticket)


def ticket_response(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "customer_id": ticket.customer_id,
        "category_id": ticket.category_id,
        "subject": ticket.subject,
        "description": ticket.description,
        "priority": ticket.priority,
        "status": ticket.status,
        "assigned_agent_id": ticket.agent_id,
        "first_response_due": ticket.first_response_due,
        "resolution_due": ticket.resolution_due,
        "first_response_at": ticket.first_response_at,
        "resolved_at": ticket.resolved_at,
        "closed_at": ticket.closed_at,
        "sla_breached": ticket.sla_breached,
        "reopen_count": ticket.reopen_count,
    }


@router.get("/")
async def list_tickets(
    db: Database,
    user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = None,
    category_id: int | None = None,
):
    query = select(Ticket)

    if user["role"] == "Customer":
        query = query.where(Ticket.customer_id == user["id"])
    elif user["role"] == "Agent":
        query = query.where(Ticket.agent_id == user["id"])
    elif not is_admin(user):
        raise HTTPException(403, "Access denied")

    if status_filter:
        query = query.where(Ticket.status == status_filter)

    if priority:
        if priority not in PRIORITIES:
            raise HTTPException(400, "Invalid priority")
        query = query.where(Ticket.priority == priority)

    if category_id is not None:
        query = query.where(Ticket.category_id == category_id)

    query = query.order_by(Ticket.id.desc())
    result = await db.execute(query)

    return [ticket_response(t) for t in result.scalars().all()]


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: int,
    db: Database,
    user: CurrentUser,
):
    ticket = await get_ticket_or_404(db, ticket_id)

    if not can_view_ticket(ticket, user):
        raise HTTPException(403, "You cannot view this ticket")

    return ticket_response(ticket)


@router.put("/{ticket_id}/status")
async def update_ticket_status(
    ticket_id: int,
    payload: TicketStatusUpdate,
    db: Database,
    user: CurrentUser,
):
    if user["role"] not in {"Admin", "Agent"}:
        raise HTTPException(
            403,
            "Only the assigned agent or an Admin can change status",
        )

    ticket = await get_ticket_or_404(db, ticket_id)

    if not is_admin(user) and ticket.agent_id != user["id"]:
        raise HTTPException(
            403,
            "Agents can update only their assigned tickets",
        )

    if ticket.status == "Closed":
        raise HTTPException(400, "Closed tickets cannot be updated")

    old_status = ticket.status
    new_status = payload.status

    if new_status == old_status:
        raise HTTPException(400, "Ticket already has this status")

    if new_status not in ALLOWED_TRANSITIONS.get(old_status, set()):
        raise HTTPException(
            400,
            f"Invalid status transition: {old_status} -> {new_status}",
        )

    if new_status == "Assigned":
        if not is_admin(user):
            raise HTTPException(
                403,
                "Only an Admin can assign a ticket",
            )

        if payload.assigned_agent_id is None:
            raise HTTPException(
                400,
                "assigned_agent_id is required when assigning a ticket",
            )

        agent_result = await db.execute(
            select(Agent).where(Agent.id == payload.assigned_agent_id)
        )
        agent = agent_result.scalar_one_or_none()

        if agent is None or not agent.is_active:
            raise HTTPException(400, "Agent not found or inactive")

        if not agent.is_available:
            raise HTTPException(400, "Agent is not available")

        ticket.agent_id = agent.id

    elif payload.assigned_agent_id is not None:
        if not is_admin(user):
            raise HTTPException(
                403,
                "Only an Admin can assign a ticket",
            )

        agent_result = await db.execute(
            select(Agent).where(
                Agent.id == payload.assigned_agent_id
            )
        )
        agent = agent_result.scalar_one_or_none()

        if agent is None or not agent.is_active:
            raise HTTPException(400, "Agent not found or inactive")

        ticket.agent_id = agent.id

    current_time = now_utc()
    ticket.status = new_status

    if new_status in {"In Progress", "Waiting on Customer", "Resolved"}:
        if ticket.first_response_at is None:
            ticket.first_response_at = current_time

    if new_status == "Resolved":
        ticket.resolved_at = current_time

    if new_status == "Closed":
        if ticket.resolved_at is None:
            raise HTTPException(
                400,
                "Only a resolved ticket can be closed",
            )
        ticket.closed_at = current_time

    if new_status == "In Progress" and old_status == "Waiting on Customer":
        ticket.resolved_at = None

    try:
        await save_status_history(
            db,
            ticket,
            old_status,
            new_status,
            user,
            payload.note,
        )
        await db.commit()
        await db.refresh(ticket)
    except Exception:
        await db.rollback()
        raise

    return ticket_response(ticket)


@router.put("/{ticket_id}/priority")
async def update_ticket_priority(
    ticket_id: int,
    payload: TicketPriorityUpdate,
    db: Database,
    user: CurrentUser,
):
    if user["role"] not in {"Admin", "Agent"}:
        raise HTTPException(
            403,
            "Only the assigned agent or an Admin can change priority",
        )

    ticket = await get_ticket_or_404(db, ticket_id)

    if not can_view_ticket(ticket, user):
        raise HTTPException(403, "You cannot update this ticket")

    if ticket.status == "Closed":
        raise HTTPException(400, "Closed tickets cannot be updated")

    policy = await get_sla_policy(db, payload.priority)
    current_time = now_utc()

    ticket.priority = payload.priority

    # Recalculate only milestones that have not already happened.
    if ticket.first_response_at is None:
        ticket.first_response_due = current_time + timedelta(
            minutes=policy.first_response_minutes
        )

    if ticket.resolved_at is None:
        ticket.resolution_due = current_time + timedelta(
            minutes=policy.resolution_minutes
        )
        ticket.sla_deadline = ticket.resolution_due

    await db.commit()
    await db.refresh(ticket)

    return ticket_response(ticket)


@router.put("/{ticket_id}/reopen")
async def reopen_ticket(
    ticket_id: int,
    db: Database,
    user: CurrentUser,
):
    if user["role"] != "Customer" or user["account_type"] != "customer":
        raise HTTPException(
            403,
            "Only the customer who owns the ticket can reopen it",
        )

    ticket = await get_ticket_or_404(db, ticket_id)

    if ticket.customer_id != user["id"]:
        raise HTTPException(403, "You do not own this ticket")

    if ticket.status != "Resolved":
        raise HTTPException(
            400,
            "Only resolved tickets can be reopened",
        )

    if ticket.resolved_at is None:
        raise HTTPException(
            400,
            "Resolution timestamp is missing",
        )

    if now_utc() > ticket.resolved_at + timedelta(days=7):
        raise HTTPException(
            400,
            "The 7-day reopening window has expired",
        )

    if ticket.reopen_count >= 2:
        raise HTTPException(
            400,
            "A ticket can be reopened at most two times",
        )

    old_status = ticket.status
    ticket.status = "In Progress"
    ticket.reopen_count += 1
    ticket.resolved_at = None
    ticket.closed_at = None

    try:
        await save_status_history(
            db,
            ticket,
            old_status,
            "In Progress",
            user,
            "Reopened by customer",
        )
        await db.commit()
        await db.refresh(ticket)
    except Exception:
        await db.rollback()
        raise

    return ticket_response(ticket)


@router.get("/{ticket_id}/history")
async def get_ticket_history(
    ticket_id: int,
    db: Database,
    user: CurrentUser,
):
    ticket = await get_ticket_or_404(db, ticket_id)

    if not can_view_ticket(ticket, user):
        raise HTTPException(403, "You cannot view this ticket history")

    result = await db.execute(
        select(StatusHistory)
        .where(StatusHistory.ticket_id == ticket_id)
        .order_by(StatusHistory.created_at.asc(), StatusHistory.id.asc())
    )

    history = result.scalars().all()

    return [
        {
            "id": item.id,
            "old_status": item.old_status,
            "new_status": item.new_status,
            "changed_by_type": item.changed_by_type,
            "changed_by_id": item.changed_by_id,
            "note": item.note,
            "created_at": item.created_at,
        }
        for item in history
    ]
