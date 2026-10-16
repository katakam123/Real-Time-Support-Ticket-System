
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field
from pydantic import ConfigDict

TicketPriority = Literal["Low", "Medium", "High", "Urgent"]

TicketStatus = Literal[
    "Open",
    "Assigned",
    "In Progress",
    "Waiting on Customer",
    "Resolved",
    "Closed",
]


class TicketCreate(BaseModel):
    category_id: int
    subject: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=5000)
    priority: TicketPriority = "Medium"


class TicketStatusUpdate(BaseModel):
    status: TicketStatus
    assigned_agent_id: Optional[int] = None
    note: Optional[str] = Field(default=None, max_length=500)


class TicketPriorityUpdate(BaseModel):
    priority: TicketPriority


class TicketResponse(BaseModel):
    id: int
    ticket_number: Optional[str]
    customer_id: int
    category_id: int
    subject: str
    description: str
    priority: TicketPriority
    status: TicketStatus
    assigned_agent_id: Optional[int]
    first_response_due: Optional[datetime]
    resolution_due: Optional[datetime]
    first_response_at: Optional[datetime]
    resolved_at: Optional[datetime]
    closed_at: Optional[datetime]
    sla_breached: bool
    reopen_count: int


class StatusHistoryResponse(BaseModel):
    id: int
    old_status: Optional[str]
    new_status: str
    changed_by_type: str
    changed_by_id: int
    note: Optional[str]
    created_at: datetime
    
class TicketCreate(BaseModel):
    subject: str = Field(
        ...,
        min_length=5,
        max_length=150,
        strip_whitespace=True,
    )
    description: str = Field(
        ...,
        min_length=10,
        strip_whitespace=True,
    )
    category_id: int = Field(..., gt=0)
    priority: str = "Medium"

    model_config = ConfigDict(extra="forbid")