
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.entities import Ticket, Feedback
from app.schemas.feedback import FeedbackCreate, FeedbackResponse


router = APIRouter(tags=["Customer Feedback"])


@router.post(
    "/tickets/{ticket_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket_feedback(
    ticket_id: int,
    payload: FeedbackCreate,
    user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Only customers can submit feedback.
    if user.get("account_type") != "customer":
        raise HTTPException(
            status_code=403,
            detail="Only customers can submit feedback",
        )

    result = await db.execute(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .with_for_update()
    )
    ticket = result.scalar_one_or_none()

    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found",
        )

    # Ensure the ticket belongs to the logged-in customer.
    if ticket.customer_id != user["id"]:
        raise HTTPException(
            status_code=403,
            detail="You can only give feedback for your own tickets",
        )

    if ticket.status not in ("Resolved", "Closed"):
        raise HTTPException(
            status_code=400,
            detail="Feedback is allowed only for Resolved or Closed tickets",
        )

    existing_result = await db.execute(
        select(Feedback).where(Feedback.ticket_id == ticket_id)
    )
    existing_feedback = existing_result.scalar_one_or_none()

    if existing_feedback is not None:
        raise HTTPException(
            status_code=409,
            detail="Feedback has already been submitted for this ticket",
        )

    feedback = Feedback(
        ticket_id=ticket_id,
        rating=payload.rating,
        comment=payload.comment,
    )

    db.add(feedback)

    try:
        await db.commit()
        await db.refresh(feedback)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Feedback has already been submitted for this ticket",
        )

    return feedback


@router.get(
    "/tickets/{ticket_id}/feedback",
    response_model=FeedbackResponse,
)
async def get_ticket_feedback(
    ticket_id: int,
    user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()

    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail="Ticket not found",
        )

    # Customers may see feedback only for their own tickets.
    if user.get("account_type") == "customer":
        if ticket.customer_id != user["id"]:
            raise HTTPException(
                status_code=403,
                detail="You cannot view feedback for this ticket",
            )
    else:
        # Agents may view only tickets assigned to them.
        # Admins may view feedback for any ticket.
        if user.get("role") != "Admin":
            if (
                user.get("role") != "Agent"
                or ticket.agent_id != user["id"]
            ):
                raise HTTPException(
                    status_code=403,
                    detail="You are not authorized to view this feedback",
                )

    feedback_result = await db.execute(
        select(Feedback).where(Feedback.ticket_id == ticket_id)
    )
    feedback = feedback_result.scalar_one_or_none()

    if feedback is None:
        raise HTTPException(
            status_code=404,
            detail="No feedback has been submitted for this ticket",
        )

    return feedback
