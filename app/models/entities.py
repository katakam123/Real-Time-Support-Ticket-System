from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Table,
    Column,
    String,
    Text,
    Integer,
    Boolean,
    ForeignKey,
    DateTime,
    CheckConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


# =========================================================
# MANY-TO-MANY TABLE: AGENTS <-> CATEGORIES
# =========================================================

agent_categories = Table(
    "agent_categories",
    Base.metadata,
    Column(
        "agent_id",
        ForeignKey("agents.id"),
        primary_key=True,
    ),
    Column(
        "category_id",
        ForeignKey("categories.id"),
        primary_key=True,
    ),
)


# =========================================================
# CATEGORY
# =========================================================

class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="category",
    )


# =========================================================
# CUSTOMER
# =========================================================

class Customer(TimestampMixin, Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="customer",
    )


# =========================================================
# AGENT / ADMIN
# =========================================================

class Agent(TimestampMixin, Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Agent or Admin
    role: Mapped[str] = mapped_column(
        String(20),
        default="Agent",
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_available: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    max_open_tickets: Mapped[int] = mapped_column(
        Integer,
        default=10,
        nullable=False,
    )

    assigned_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="agent",
    )

    categories: Mapped[list["Category"]] = relationship(
        secondary=agent_categories,
        lazy="selectin",
    )


# =========================================================
# TICKET
# =========================================================

class Ticket(TimestampMixin, Base):
    __tablename__ = "tickets"

    __table_args__ = (
        CheckConstraint(
            "priority IN ('Low', 'Medium', 'High', 'Urgent')",
            name="ck_ticket_priority",
        ),
        CheckConstraint(
            "status IN "
            "('Open', 'Assigned', 'In Progress', "
            "'Waiting on Customer', 'Pending', "
            "'Resolved', 'Closed', 'Escalated')",
            name="ck_ticket_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    ticket_number: Mapped[Optional[str]] = mapped_column(
        String(30),
        unique=True,
        index=True,
        nullable=True,
    )

    subject: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        default="Medium",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="Open",
        nullable=False,
    )

    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"),
        nullable=False,
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
        nullable=False,
    )
    agent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("agents.id"),
        nullable=True,
        index=True,
    )

    # SLA deadlines
    sla_deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    first_response_due: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolution_due: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # SLA response and resolution timestamps
    first_response_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # SLA tracking
    sla_breached: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    sla_paused_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        default=None,
    )

    first_response_breached_at: Mapped[Optional[datetime]] = (
        mapped_column(DateTime, nullable=True, default=None)
    )
    resolution_breached_at: Mapped[Optional[datetime]] = (
        mapped_column(DateTime, nullable=True, default=None)
    )
    first_response_escalated_at: Mapped[Optional[datetime]] = (
        mapped_column(DateTime, nullable=True, default=None)
    )
    resolution_escalated_at: Mapped[Optional[datetime]] = (
        mapped_column(DateTime, nullable=True, default=None)
    )

    reopen_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Relationships
    category: Mapped["Category"] = relationship(
        back_populates="tickets",
    )
    customer: Mapped["Customer"] = relationship(
        back_populates="tickets",
    )
    agent: Mapped[Optional["Agent"]] = relationship(
        back_populates="assigned_tickets",
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
    )
    status_history: Mapped[list["StatusHistory"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
    )
    feedback: Mapped[Optional["Feedback"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        uselist=False,
    )


# =========================================================
# CHAT MESSAGES
# =========================================================

class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id"),
        nullable=False,
        index=True,
    )
    sender_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    sender_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_internal_note: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    ticket: Mapped["Ticket"] = relationship(
        back_populates="messages",
    )
    attachment_filename = Column(String(255), nullable=True)
attachment_original_filename = Column(String(255), nullable=True)
attachment_content_type = Column(String(100), nullable=True)
attachment_size_bytes = Column(Integer, nullable=True)
attachment_storage_path = Column(String(500), nullable=True)

# =========================================================
# TICKET STATUS AND ASSIGNMENT HISTORY
# =========================================================

class StatusHistory(TimestampMixin, Base):
    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id"),
        nullable=False,
        index=True,
    )

    old_status: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
    )
    new_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    changed_by_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    changed_by_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    note: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Optional assignment history
    previous_agent_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    new_agent_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    ticket: Mapped["Ticket"] = relationship(
        back_populates="status_history",
    )


# =========================================================
# CUSTOMER FEEDBACK
# =========================================================

class Feedback(TimestampMixin, Base):
    __tablename__ = "feedback"

    __table_args__ = (
        CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_feedback_rating",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id"),
        unique=True,
        nullable=False,
    )
    rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    comment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    ticket: Mapped["Ticket"] = relationship(
        back_populates="feedback",
    )


# =========================================================
# SLA POLICIES
# =========================================================

class SLAPolicy(TimestampMixin, Base):
    __tablename__ = "sla_policies"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
    )
    first_response_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    resolution_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )


# =========================================================
# AGENT NOTIFICATIONS
# =========================================================

class AgentNotification(TimestampMixin, Base):
    __tablename__ = "agent_notifications"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id"),
        nullable=False,
        index=True,
    )
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id"),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )


# =========================================================
# GENERAL NOTIFICATIONS
# =========================================================

class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"

    __table_args__ = (
        Index(
            "ix_notifications_recipient",
            "recipient_type",
            "recipient_id",
            "is_read",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )
    recipient_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    recipient_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    ticket_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
    )
    notification_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )