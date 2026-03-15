"""ElectionEvent ORM model — represents a single election day."""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Integer, String, Text, UniqueConstraint
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

    # Stage: "election", "runoff", "recount"
    election_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Calendar fields (populated from markdown overview)
    registration_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    early_voting_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    early_voting_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    absentee_request_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    qualifying_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    qualifying_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Feed fields (populated when results feed URL is known)
    data_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refresh_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="120")

    # Relationships
    elections: Mapped[list[Election]] = relationship(back_populates="election_event")

    __table_args__ = (UniqueConstraint("event_date", "event_type", name="uq_election_event_date_type"),)
