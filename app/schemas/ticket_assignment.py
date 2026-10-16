
from pydantic import BaseModel, Field


class TicketAssign(BaseModel):
    assigned_agent_id: int = Field(gt=0)
