from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI
from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.services.scheduler import start_scheduler, stop_scheduler
from app.routers.auth import router as auth_router
from app.routers.agents import router as agents_router
from app.routers.categories import router as categories_router
from app.routers.sla_policies import router as sla_policies_router
from app.routers.tickets import router as tickets_router
from app.routers.ticket_assignment import (
    router as ticket_assignment_router,
)
from app.routers.chat import router as chat_router
from app.routers.notifications import router as notifications_router
from app.routers.feedback import router as feedback_router
from app.routers import reports
app = FastAPI(
    title="Real-Time Support Ticket System",
    description="Support tickets, authentication and live chat",
    version="1.0.0",
)

app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(categories_router)
app.include_router(sla_policies_router)
app.include_router(tickets_router)
app.include_router(ticket_assignment_router)
app.include_router(chat_router)
app.include_router(notifications_router)
app.include_router(feedback_router)
app.include_router(reports.router, prefix="/reports", tags=["Reports"])
@app.get("/", tags=["Health"])
async def health_check():
    return {
        "message": "Support Ticket System API is running",
        "status": "healthy",
    }
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)

