
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.entities import Ticket, StatusHistory, Agent, Notification
from app.services.notification_service import serialize_notification
from app.websockets.notification_manager import notification_manager


OPEN_STATUSES = [
    "Open",
    "Assigned",
    "In Progress",
    "Waiting on Customer",
]

PRIORITY_ORDER = ["Low", "Medium", "High", "Urgent"]


def utc_now():
    # Use naive UTC to match MySQL DATETIME columns without timezone=True.
    return datetime.utcnow()


def next_priority(current_priority: str) -> str:
    if current_priority not in PRIORITY_ORDER:
        return current_priority

    index = PRIORITY_ORDER.index(current_priority)

    if index >= len(PRIORITY_ORDER) - 1:
        return current_priority

    return PRIORITY_ORDER[index + 1]


async def create_admin_notifications(
    db: AsyncSession,
    ticket: Ticket,
    event_type: str,
    title: str,
    message: str,
):
    result = await db.execute(
        select(Agent).where(
            Agent.role == "Admin",
            Agent.is_active.is_(True),
        )
    )
    admins = result.scalars().all()

    notification_payloads = []

    for admin in admins:
        notification = Notification(
            recipient_type="Admin",
            recipient_id=admin.id,
            ticket_id=ticket.id,
            notification_type=event_type,
            title=title,
            message=message,
            is_read=False,
        )

        db.add(notification)
        await db.flush()
        await db.refresh(notification)

        notification_payloads.append(
            (
                ("Admin", admin.id),
                {
                    "event": "notification",
                    "data": serialize_notification(notification),
                },
            )
        )

    return notification_payloads


async def record_sla_escalation(
    db: AsyncSession,
    ticket: Ticket,
    breach_type: str,
):
    old_priority = ticket.priority
    new_priority = next_priority(old_priority)

    # Even an Urgent ticket must generate an Admin notification.
    if new_priority != old_priority:
        ticket.priority = new_priority

    if breach_type == "first_response":
        ticket.first_response_escalated_at = utc_now()
    else:
        ticket.resolution_escalated_at = utc_now()

    history = StatusHistory(
        ticket_id=ticket.id,
        old_status=ticket.status,
        new_status=ticket.status,
        changed_by_type="System",
        changed_by_id=None,
        note=(
            f"SLA {breach_type} breach. "
            f"Priority changed from {old_priority} to {new_priority}."
            if new_priority != old_priority
            else (
                f"SLA {breach_type} breach. Ticket was already "
                f"{old_priority}; no further escalation is possible."
            )
        ),
    )
    db.add(history)

    if new_priority != old_priority:
        title = "Ticket SLA escalation"
        message = (
            f"Ticket {ticket.ticket_number} breached its "
            f"{breach_type.replace('_', ' ')} SLA. Priority increased "
            f"from {old_priority} to {new_priority}."
        )
    else:
        title = "Urgent ticket SLA breach"
        message = (
            f"Ticket {ticket.ticket_number} breached its "
            f"{breach_type.replace('_', ' ')} SLA. It is already Urgent "
            "and cannot be escalated further."
        )

    return await create_admin_notifications(
        db=db,
        ticket=ticket,
        event_type="sla_breach",
        title=title,
        message=message,
    )


async def check_sla_job():
    async with AsyncSessionLocal() as db:
        now = utc_now()

        result = await db.execute(
            select(Ticket)
            .where(Ticket.status.in_(OPEN_STATUSES))
            .order_by(Ticket.id)
            .with_for_update()
        )
        tickets = result.scalars().all()

        for ticket in tickets:
            notification_payloads = []
            changed = False

            # First response deadline: applies until the first response exists.
            if (
                ticket.first_response_at is None
                and ticket.first_response_due is not None
                and ticket.first_response_due <= now
                and ticket.first_response_breached_at is None
            ):
                ticket.first_response_breached_at = now
                ticket.sla_breached = True
                changed = True

                notification_payloads.extend(
                    await record_sla_escalation(
                        db, ticket, "first_response"
                    )
                )

            # Resolution deadline: pause while waiting for the customer.
            if (
                ticket.status != "Waiting on Customer"
                and ticket.resolved_at is None
                and ticket.closed_at is None
                and ticket.resolution_due is not None
                and ticket.resolution_due <= now
                and ticket.resolution_breached_at is None
            ):
                ticket.resolution_breached_at = now
                ticket.sla_breached = True
                changed = True

                notification_payloads.extend(
                    await record_sla_escalation(
                        db, ticket, "resolution"
                    )
                )

            if changed:
                await db.commit()

                # Publish only after the database transaction succeeds.
                for user_key, payload in notification_payloads:
                    await notification_manager.send_to_user(
                        user_key, payload
                    )


async def auto_close_job():
    async with AsyncSessionLocal() as db:
        cutoff = utc_now() - timedelta(days=7)

        result = await db.execute(
            select(Ticket)
            .where(
                Ticket.status == "Resolved",
                Ticket.resolved_at.is_not(None),
                Ticket.resolved_at <= cutoff,
            )
            .order_by(Ticket.id)
            .with_for_update()
        )
        tickets = result.scalars().all()

        for ticket in tickets:
            old_status = ticket.status
            now = utc_now()

            ticket.status = "Closed"
            ticket.closed_at = now

            db.add(
                StatusHistory(
                    ticket_id=ticket.id,
                    old_status=old_status,
                    new_status="Closed",
                    changed_by_type="System",
                    changed_by_id=None,
                    note=(
                        "Automatically closed because the ticket "
                        "remained Resolved for 7 days without reopening."
                    ),
                )
            )

        if tickets:
            await db.commit()

            # Open-ticket counts can change when tickets are closed.
            from app.services.live_counts import push_open_ticket_counts

            async with AsyncSessionLocal() as count_db:
                await push_open_ticket_counts(count_db)
