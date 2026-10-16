
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.security import decode_access_token
from app.database import get_db, AsyncSessionLocal
from app.models.entities import Notification, Customer, Agent
from app.services.notification_service import (
    user_notification_type,
    serialize_notification,
)
from app.websockets.notification_manager import notification_manager


router = APIRouter(tags=["Notifications"])


def recipient_for_user(user: dict):
    return (
        user_notification_type(user),
        user["id"],
    )


@router.get("/notifications")
async def get_notifications(
    user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    recipient_type, recipient_id = recipient_for_user(user)

    query = select(Notification).where(
        Notification.recipient_type == recipient_type,
        Notification.recipient_id == recipient_id,
    )

    if unread_only:
        query = query.where(Notification.is_read.is_(False))

    query = (
        query.order_by(
            Notification.created_at.desc(),
            Notification.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(query)
    notifications = result.scalars().all()

    return {
        "count": len(notifications),
        "notifications": [
            serialize_notification(item) for item in notifications
        ],
    }


@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    recipient_type, recipient_id = recipient_for_user(user)

    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_type == recipient_type,
            Notification.recipient_id == recipient_id,
        )
    )
    notification = result.scalar_one_or_none()

    if notification is None:
        raise HTTPException(
            status_code=404,
            detail="Notification not found",
        )

    notification.is_read = True
    await db.commit()

    return {
        "message": "Notification marked as read",
        "notification_id": notification_id,
        "is_read": True,
    }


@router.put("/notifications/read-all")
async def mark_all_notifications_read(
    user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    recipient_type, recipient_id = recipient_for_user(user)

    result = await db.execute(
        update(Notification)
        .where(
            Notification.recipient_type == recipient_type,
            Notification.recipient_id == recipient_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )

    await db.commit()

    return {
        "message": "All notifications marked as read",
        "updated_count": result.rowcount,
    }


async def authenticate_ws_token(token: str):
    """Validate the existing JWT and load its active account."""
    payload = decode_access_token(token)

    if not payload:
        return None

    subject = payload.get("sub", "")
    if not isinstance(subject, str) or ":" not in subject:
        return None

    account_type, raw_id = subject.split(":", 1)

    try:
        account_id = int(raw_id)
    except (TypeError, ValueError):
        return None

    async with AsyncSessionLocal() as db:
        if account_type == "customer":
            result = await db.execute(
                select(Customer).where(Customer.id == account_id)
            )
            account = result.scalar_one_or_none()

            if not account or not account.is_active:
                return None

            return {
                "id": account.id,
                "account_type": "customer",
                "role": "Customer",
            }

        if account_type == "agent":
            result = await db.execute(
                select(Agent).where(Agent.id == account_id)
            )
            account = result.scalar_one_or_none()

            if not account or not account.is_active:
                return None

            # Use the database role, not a role supplied by the client.
            if account.role not in ("Agent", "Admin"):
                return None

            return {
                "id": account.id,
                "account_type": "agent",
                "role": account.role,
            }

    return None


@router.websocket("/ws/notifications")
async def notifications_websocket(websocket: WebSocket):
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    user = await authenticate_ws_token(token)

    if user is None:
        await websocket.close(code=1008, reason="Invalid token")
        return

    user_key = recipient_for_user(user)

    await notification_manager.connect(websocket, user_key)

    try:
        await websocket.send_json({
            "event": "connected",
            "message": "Live notifications connected",
        })

        # Keep the connection alive. The client can send ping messages.
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "ping":
                await websocket.send_json({"event": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception:
        # Avoid exposing internal errors to the client.
        pass
    finally:
        await notification_manager.disconnect(websocket, user_key)
