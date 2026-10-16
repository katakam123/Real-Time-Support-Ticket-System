
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models.entities import Agent, Ticket, Category, Feedback


router = APIRouter(
    prefix="/reports",
    tags=["Reports & Dashboard"],
)


def check_admin(user: dict) -> None:
    """Allow only Admin accounts to access reports."""
    if user.get("role") != "Admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )


def validate_dates(
    from_date: Optional[date],
    to_date: Optional[date],
) -> None:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=422,
            detail="from_date cannot be after to_date",
        )


def date_filters(
    from_date: Optional[date],
    to_date: Optional[date],
):
    filters = []

    if from_date:
        filters.append(
            Ticket.created_at >= datetime.combine(
                from_date, time.min
            )
        )

    if to_date:
        filters.append(
            Ticket.created_at < datetime.combine(
                to_date + timedelta(days=1), time.min
            )
        )

    return filters


# =====================================================
# 1. DASHBOARD
# GET /reports/dashboard
# =====================================================

@router.get("/dashboard")
async def dashboard(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    check_admin(user)

    total_tickets = await db.scalar(
        select(func.count(Ticket.id))
    )

    status_result = await db.execute(
        select(
            Ticket.status,
            func.count(Ticket.id),
        ).group_by(Ticket.status)
    )

    tickets_by_status = {
        status: count
        for status, count in status_result.all()
    }

    unassigned_tickets = await db.scalar(
        select(func.count(Ticket.id)).where(
            Ticket.agent_id.is_(None)
        )
    )

    sla_breached_tickets = await db.scalar(
        select(func.count(Ticket.id)).where(
            Ticket.sla_breached.is_(True)
        )
    )

    online_agents = await db.scalar(
        select(func.count(Agent.id)).where(
            Agent.is_active.is_(True),
            Agent.is_available.is_(True),
        )
    )

    return {
        "total_tickets": total_tickets or 0,
        "tickets_by_status": tickets_by_status,
        "unassigned_tickets": unassigned_tickets or 0,
        "sla_breached_tickets": sla_breached_tickets or 0,
        "online_agents": online_agents or 0,
    }


# =====================================================
# 2. AGENT PERFORMANCE
# GET /reports/agent-performance
# =====================================================

@router.get("/agent-performance")
async def agent_performance(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    check_admin(user)
    validate_dates(from_date, to_date)

    agents_result = await db.execute(
        select(Agent).order_by(Agent.id)
    )
    agents = agents_result.scalars().all()

    filters = date_filters(from_date, to_date)

    tickets_result = await db.execute(
        select(Ticket).where(*filters)
    )
    tickets = tickets_result.scalars().all()

    feedback_result = await db.execute(
        select(Feedback, Ticket.agent_id)
        .join(Ticket, Feedback.ticket_id == Ticket.id)
        .where(*filters)
    )

    ratings_by_agent = {}
    for feedback, agent_id in feedback_result.all():
        if agent_id is not None:
            ratings_by_agent.setdefault(
                agent_id, []
            ).append(feedback.rating)

    reports = []

    for agent in agents:
        assigned = [
            ticket for ticket in tickets
            if ticket.agent_id == agent.id
        ]

        resolved = [
            ticket for ticket in assigned
            if ticket.resolved_at is not None
        ]

        response_seconds = [
            (ticket.first_response_at - ticket.created_at)
            .total_seconds()
            for ticket in assigned
            if ticket.first_response_at is not None
            and ticket.created_at is not None
        ]

        resolution_seconds = [
            (ticket.resolved_at - ticket.created_at)
            .total_seconds()
            for ticket in resolved
            if ticket.created_at is not None
        ]

        breached_count = sum(
            1 for ticket in assigned
            if ticket.sla_breached
        )

        rating_values = ratings_by_agent.get(agent.id, [])

        reports.append({
            "agent_id": agent.id,
            "agent_name": agent.name,
            "email": agent.email,
            "tickets_resolved": len(resolved),
            "average_first_response_minutes": (
                round(sum(response_seconds) / len(response_seconds) / 60, 2)
                if response_seconds else None
            ),
            "average_resolution_hours": (
                round(sum(resolution_seconds) / len(resolution_seconds) / 3600, 2)
                if resolution_seconds else None
            ),
            "sla_breach_percentage": (
                round(breached_count / len(assigned) * 100, 2)
                if assigned else 0
            ),
            "average_rating": (
                round(sum(rating_values) / len(rating_values), 2)
                if rating_values else None
            ),
        })

    return {
        "from_date": from_date,
        "to_date": to_date,
        "agents": reports,
    }


# =====================================================
# 3. CATEGORY SUMMARY
# GET /reports/category-summary
# =====================================================

@router.get("/category-summary")
async def category_summary(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    check_admin(user)
    validate_dates(from_date, to_date)

    filters = date_filters(from_date, to_date)

    result = await db.execute(
        select(
            Category.id,
            Category.name,
            func.count(Ticket.id).label("ticket_count"),
        )
        .outerjoin(
            Ticket,
            (Ticket.category_id == Category.id)
            & (
                Ticket.created_at >= datetime.combine(
                    from_date, time.min
                ) if from_date else True
            )
            & (
                Ticket.created_at < datetime.combine(
                    to_date + timedelta(days=1), time.min
                ) if to_date else True
            ),
        )
        .group_by(Category.id, Category.name)
        .order_by(Category.name)
    )

    categories = []

    for category_id, name, ticket_count in result.all():
        resolution_result = await db.execute(
            select(Ticket).where(
                Ticket.category_id == category_id,
                Ticket.resolved_at.is_not(None),
                *filters,
            )
        )

        resolved_tickets = resolution_result.scalars().all()

        durations = [
            (ticket.resolved_at - ticket.created_at).total_seconds()
            / 3600
            for ticket in resolved_tickets
            if ticket.created_at is not None
        ]

        categories.append({
            "category_id": category_id,
            "category_name": name,
            "ticket_count": ticket_count,
            "average_resolution_hours": (
                round(sum(durations) / len(durations), 2)
                if durations else None
            ),
        })

    return {
        "from_date": from_date,
        "to_date": to_date,
        "categories": categories,
    }


# =====================================================
# 4. SLA SUMMARY
# GET /reports/sla-summary
# =====================================================

@router.get("/sla-summary")
async def sla_summary(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    check_admin(user)

    result = await db.execute(
        select(
            Ticket.priority,
            func.count(Ticket.id).label("total"),
            func.sum(
                case(
                    (Ticket.sla_breached.is_(True), 1),
                    else_=0,
                )
            ).label("breached"),
        ).group_by(Ticket.priority)
    )

    summaries = []

    for priority, total, breached in result.all():
        breached_count = int(breached or 0)

        summaries.append({
            "priority": priority,
            "total_tickets": total,
            "sla_breached": breached_count,
            "sla_met": total - breached_count,
        })

    return {"priorities": summaries}


# =====================================================
# 5. CUSTOMER SATISFACTION
# GET /reports/customer-satisfaction
# =====================================================

@router.get("/customer-satisfaction")
async def customer_satisfaction(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    check_admin(user)

    average_rating = await db.scalar(
        select(func.avg(Feedback.rating))
    )

    result = await db.execute(
        select(
            Feedback.rating,
            func.count(Feedback.id),
        ).group_by(Feedback.rating)
    )

    rating_counts = {
        rating: count
        for rating, count in result.all()
    }

    distribution = {
        f"{star}_star": rating_counts.get(star, 0)
        for star in range(1, 6)
    }

    total_feedback = sum(distribution.values())

    return {
        "average_rating": (
            round(float(average_rating), 2)
            if average_rating is not None else None
        ),
        "total_feedback": total_feedback,
        "rating_distribution": distribution,
    }
