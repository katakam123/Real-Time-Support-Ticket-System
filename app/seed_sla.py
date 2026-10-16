
import asyncio

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.entities import SLAPolicy


DEFAULT_POLICIES = [
    {
        "priority": "Low",
        "first_response_minutes": 24 * 60,
        "resolution_minutes": 72 * 60,
    },
    {
        "priority": "Medium",
        "first_response_minutes": 8 * 60,
        "resolution_minutes": 48 * 60,
    },
    {
        "priority": "High",
        "first_response_minutes": 2 * 60,
        "resolution_minutes": 24 * 60,
    },
    {
        "priority": "Urgent",
        "first_response_minutes": 30,
        "resolution_minutes": 8 * 60,
    },
]


async def seed_sla_policies():
    async with AsyncSessionLocal() as db:
        for item in DEFAULT_POLICIES:
            result = await db.execute(
                select(SLAPolicy).where(
                    SLAPolicy.priority == item["priority"]
                )
            )

            if result.scalar_one_or_none() is None:
                db.add(SLAPolicy(**item))

        await db.commit()

    print("Default SLA policies initialized successfully.")


if __name__ == "__main__":
    asyncio.run(seed_sla_policies())
