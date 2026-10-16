
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.sla_jobs import check_sla_job, auto_close_job


scheduler = AsyncIOScheduler(timezone="UTC")


def start_scheduler():
    if scheduler.running:
        return

    scheduler.add_job(
        check_sla_job,
        trigger="interval",
        minutes=5,
        id="ticket_sla_check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        auto_close_job,
        trigger="cron",
        hour=0,
        minute=0,
        id="ticket_auto_close",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
