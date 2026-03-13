"""ElectionEvent ORM model — represents a single election day."""

from __future__ import annotations

from datetime import date  # noqa: TC003
from typing import TYPE_CHECKING

from sqlalchemy import Date, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from voter_api.models.election import Election


class ElectionEvent(Base, UUIDMixin, TimestampMixin):
    """An election event (election day) that groups multiple contests.

    Represents a single election day like "2024 General Election" which
    may contain many individual contests (elections). This enables
    event-level voter history resolution without requiring contest-level
    district matching.
    """

    __tablename__ = "election_events"

    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_name: Mapped[str] = mapped_column(String(500), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Relationships
    elections: Mapped[list[Election]] = relationship(back_populates="election_event")

    __table_args__ = (UniqueConstraint("event_date", "event_type", name="uq_election_event_date_type"),)
