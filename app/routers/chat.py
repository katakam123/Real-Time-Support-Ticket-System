
import json
from datetime import datetime, timezone
from typing import Annotated

import jwt
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_access_token
from app.database import AsyncSessionLocal, get_db
from app.models.entities import Agent, Customer, Message, Ticket, SLAPolicy
from app.websockets.manager import manager

router = APIRouter(tags=["Ticket Chat"])

Database = Annotated[AsyncSession, Depends(get_db)]


class MessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    is_internal_note: bool = False


def now_utc():
    return datetime.now(timezone.utc)


def serialize_message(item: Message) -> dict:
    return {
        "id": item.id,
        "ticket_id": item.ticket_id,
        "sender_id": item.sender_id,
        "sender_role": item.sender_type,
        "message": item.content,
        "is_internal_note": item.is_internal_note,
        "is_read": item.is_read,
        "created_at": (
            item.created_at.isoformat()
            if item.created_at
            else None
        ),
    }


async def authenticate_token(db: AsyncSession, token: str):
    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        role = payload.get("role")

        if not isinstance(subject, str) or ":" not in subject:
            return None

        account_type, raw_id = subject.split(":", 1)
        user_id = int(raw_id)

    except (jwt.InvalidTokenError, ValueError, TypeError):
        return None

    if account_type == "customer" and role == "Customer":
        result = await db.execute(
            select(Customer).where(Customer.id == user_id)
        )
        account = result.scalar_one_or_none()

        if account and account.is_active:
            return {
                "id": account.id,
                "role": "Customer",
                "account_type": "customer",
            }

    elif account_type == "agent" and role in ("Agent", "Admin"):
        result = await db.execute(
            select(Agent).where(Agent.id == user_id)
        )
        account = result.scalar_one_or_none()

        if account and account.is_active and account.role == role:
            return {
                "id": account.id,
                "role": account.role,
                "account_type": "agent",
            }

    return None


async def authorize_ticket_chat(
    db: AsyncSession,
    ticket_id: int,
    user: dict,
):
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()

    if ticket is None:
        return None

    if user["role"] == "Admin":
        return ticket

    if (
        user["role"] == "Customer"
        and ticket.customer_id == user["id"]
    ):
        return ticket

    if (
        user["role"] == "Agent"
        and ticket.agent_id == user["id"]
    ):
        return ticket

    return None


async def save_message(
    db: AsyncSession,
    ticket: Ticket,
    user: dict,
    content: str,
    is_internal_note: bool = False,
):
    content = content.strip()

    if not content:
        raise HTTPException(422, "Message cannot be empty")

    if user["role"] == "Customer" and ticket.status == "Closed":
        raise HTTPException(
            400,
            "Customers cannot send messages on closed tickets",
        )

    if is_internal_note and user["role"] not in ("Agent", "Admin"):
        raise HTTPException(
            403,
            "Only Agents and Admins can send internal notes",
        )

    message = Message(
        ticket_id=ticket.id,
        sender_id=user["id"],
        sender_type=user["role"],
        content=content,
        is_internal_note=is_internal_note,
        is_read=False,
    )

    db.add(message)

    # The first Agent reply starts the first-response SLA milestone.
    if (
        user["role"] == "Agent"
        and not is_internal_note
        and ticket.first_response_at is None
    ):
        ticket.first_response_at = now_utc()

        # Record whether the first reply was late.
        if (
            ticket.first_response_due is not None
            and ticket.first_response_at > ticket.first_response_due
        ):
            ticket.sla_breached = True

    await db.flush()
    await db.refresh(message)

    return message


async def get_visible_messages(
    db: AsyncSession,
    ticket_id: int,
    user: dict,
    limit: int = 50,
):
    query = select(Message).where(Message.ticket_id == ticket_id)

    if user["role"] == "Customer":
        query = query.where(Message.is_internal_note.is_(False))

    result = await db.execute(
        query.order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())

    # Mark other people's visible messages as read.
    for item in messages:
        if (
            item.sender_id != user["id"]
            or item.sender_type != user["role"]
        ):
            item.is_read = True

    await db.commit()

    return list(reversed(messages))


@router.get("/tickets/{ticket_id}/messages")
async def get_ticket_messages(
    ticket_id: int,
    db: Database,
    user: Annotated[dict, Depends(
        # Reuse the same HTTP bearer authentication as other endpoints.
        __import__(
            "app.auth.dependencies",
            fromlist=["get_current_user"],
        ).get_current_user
    )],
):
    ticket = await authorize_ticket_chat(db, ticket_id, user)

    if ticket is None:
        raise HTTPException(
            403,
            "You cannot access this ticket's chat",
        )

    messages = await get_visible_messages(
        db,
        ticket_id,
        user,
        limit=50,
    )

    return [serialize_message(item) for item in messages]


@router.post("/tickets/{ticket_id}/messages", status_code=201)
async def create_ticket_message(
    ticket_id: int,
    payload: MessageCreate,
    db: Database,
    user: Annotated[dict, Depends(
        __import__(
            "app.auth.dependencies",
            fromlist=["get_current_user"],
        ).get_current_user
    )],
):
    ticket = await authorize_ticket_chat(db, ticket_id, user)

    if ticket is None:
        raise HTTPException(
            403,
            "You cannot access this ticket's chat",
        )

    try:
        item = await save_message(
            db=db,
            ticket=ticket,
            user=user,
            content=payload.message,
            is_internal_note=payload.is_internal_note,
        )
        await db.commit()
        await db.refresh(item)

        response = serialize_message(item)

        await manager.broadcast(
            ticket_id,
            {"type": "message", "data": response},
            internal=payload.is_internal_note,
        )

        return response

    except Exception:
        await db.rollback()
        raise


@router.websocket("/ws/tickets/{ticket_id}")
async def ticket_chat_websocket(
    websocket: WebSocket,
    ticket_id: int,
    token: str = Query(...),
):
    async with AsyncSessionLocal() as db:
        user = await authenticate_token(db, token)

        if user is None:
            await websocket.close(code=1008, reason="Invalid access token")
            return

        ticket = await authorize_ticket_chat(db, ticket_id, user)

        if ticket is None:
            await websocket.close(code=1008, reason="Access denied")
            return

        await manager.connect(ticket_id, websocket, user)

        try:
            # Send chat history immediately after connecting.
            messages = await get_visible_messages(
                db,
                ticket_id,
                user,
                limit=50,
            )

            await websocket.send_text(
                json.dumps(
                    {
                        "type": "history",
                        "data": [
                            serialize_message(item)
                            for item in messages
                        ],
                    }
                )
            )

            while True:
                raw_data = await websocket.receive_text()

                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    await websocket.send_text(
                        json.dumps({
                            "type": "error",
                            "message": "Send a valid JSON object",
                        })
                    )
                    continue

                event_type = data.get("type", "message")

                if event_type == "typing":
                    await manager.broadcast(
                        ticket_id,
                        {
                            "type": "typing",
                            "sender_id": user["id"],
                            "sender_role": user["role"],
                            "is_typing": bool(data.get("is_typing", True)),
                        },
                        exclude=websocket,
                    )
                    continue

                if event_type != "message":
                    await websocket.send_text(
                        json.dumps({
                            "type": "error",
                            "message": "Unsupported event type",
                        })
                    )
                    continue

                async with AsyncSessionLocal() as message_db:
                    current_ticket = await authorize_ticket_chat(
                        message_db,
                        ticket_id,
                        user,
                    )

                    if current_ticket is None:
                        await websocket.close(
                            code=1008,
                            reason="Ticket access revoked",
                        )
                        break

                    try:
                        item = await save_message(
                            db=message_db,
                            ticket=current_ticket,
                            user=user,
                            content=data.get("message", ""),
                            is_internal_note=bool(
                                data.get("is_internal_note", False)
                            ),
                        )

                        await message_db.commit()
                        await message_db.refresh(item)

                        response = serialize_message(item)

                    except HTTPException as exc:
                        await message_db.rollback()
                        await websocket.send_text(
                            json.dumps({
                                "type": "error",
                                "message": exc.detail,
                            })
                        )
                        continue
                    except Exception:
                        await message_db.rollback()
                        await websocket.send_text(
                            json.dumps({
                                "type": "error",
                                "message": "Unable to save message",
                            })
                        )
                        continue

                # Broadcast only after the database transaction commits.
                await manager.broadcast(
                    ticket_id,
                    {"type": "message", "data": response},
                    internal=response["is_internal_note"],
                )

        except WebSocketDisconnect:
            pass
        finally:
            await manager.disconnect(ticket_id, websocket)
class MessageCreate(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=1999,
        strip_whitespace=True,
    )
    is_internal_note: bool = False

    model_config = ConfigDict(extra="forbid")