
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Notification
from app.schemas import ticket
from app.websockets.notification_manager import notification_manager


def user_notification_type(user: dict) -> str:
    if user.get("account_type") == "customer":
        return "Customer"

    if user.get("role") == "Admin":
        return "Admin"

    return "Agent"


def serialize_notification(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "recipient_type": notification.recipient_type,
        "recipient_id": notification.recipient_id,
        "ticket_id": notification.ticket_id,
        "notification_type": notification.notification_type,
        "title": notification.title,
        "message": notification.message,
        "is_read": notification.is_read,
        "created_at": (
            notification.created_at.isoformat()
            if notification.created_at else None
        ),
    }


async def create_notification(
    db: AsyncSession,
    recipient_type: str,
    recipient_id: int,
    notification_type: str,
    title: str,
    message: str,
    ticket_id: int = None,
):
    notification = Notification(
        recipient_type=recipient_type,
        recipient_id=recipient_id,
        ticket_id=ticket_id,
        notification_type=notification_type,
        title=title,
        message=message,
        is_read=False,
    )

    db.add(notification)
    await db.flush()
    await db.refresh(notification)

    # Do not commit here. The caller owns the transaction.
    return notification


async def push_notification(notification: Notification):
    """Call only after the transaction containing the notification commits."""
    user_key = (
        notification.recipient_type,
        notification.recipient_id,
    )

    await notification_manager.send_to_user(
        user_key,
        {
            "event": "notification",
            "data": serialize_notification(notification),
        },
    )

async def notify_and_push(
    db: AsyncSession,
    recipient_type: str,
    recipient_id: int,
    notification_type: str,
    title: str,
    message: str,
    ticket_id: int = None,
):
    notification = await create_notification(
        db=db,
        recipient_type=recipient_type,
        recipient_id=recipient_id,
        notification_type=notification_type,
        title=title,
        message=message,
        ticket_id=ticket_id,
    )

    # This helper is for use after the ticket's own transaction commits.
    await db.commit()
    await db.refresh(notification)
    await push_notification(notification)

    return notification
    await notify_and_push(
    db=db,
    recipient_type="Agent",
    recipient_id=agent.id,
    notification_type="ticket_assigned",
    title="New ticket assigned",
    message=f"Ticket {ticket.ticket_number} was assigned to you.",
    ticket_id=ticket.id,
)