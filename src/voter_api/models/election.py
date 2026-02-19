"""Election tracking ORM models.

Provides Election, ElectionResult, and ElectionCountyResult models
for tracking Georgia Secretary of State election results.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, TimestampMixin, UUIDMixin


class Election(Base, UUIDMixin, TimestampMixin):
    """An election event being tracked with SoS data feed configuration."""

    __tablename__ = "elections"

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    election_date: Mapped[date] = mapped_column(Date, nullable=False)
    election_type: Mapped[str] = mapped_column(String(50), nullable=False)
    district: Mapped[str] = mapped_column(String(200), nullable=False)
    data_source_url: Mapped[str] = mapped_column(Text, nullable=False)
    ballot_item_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    creation_method: Mapped[str] = mapped_column(String(20), nullable=False, server_default="manual")
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refresh_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="120")

    # Relationships
    result: Mapped["ElectionResult | None"] = relationship(
        back_populates="election", uselist=False, cascade="all, delete-orphan"
    )
    county_results: Mapped[list["ElectionCountyResult"]] = relationship(
        back_populates="election", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("name", "election_date", name="uq_election_name_date"),
        CheckConstraint("status IN ('active', 'finalized')", name="ck_election_status"),
        CheckConstraint("refresh_interval_seconds >= 60", name="ck_election_refresh_interval"),
        Index("idx_elections_status", "status"),
        Index("idx_elections_election_date", "election_date"),
        Index("idx_elections_ballot_item_id", "ballot_item_id"),
        Index("idx_elections_creation_method", "creation_method"),
        Index(
            "uq_election_feed_ballot_item",
            "data_source_url",
            "ballot_item_id",
            unique=True,
            postgresql_where=text("ballot_item_id IS NOT NULL"),
        ),
    )


class ElectionResult(Base, UUIDMixin):
    """Statewide election result snapshot (one per election, upsert pattern)."""

    __tablename__ = "election_results"

    election_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("elections.id", ondelete="CASCADE"),
        nullable=False,
    )
    precincts_participating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precincts_reporting: Mapped[int | None] = mapped_column(Integer, nullable=True)
    results_data: Mapped[list] = mapped_column(JSONB, nullable=False)
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    election: Mapped["Election"] = relationship(back_populates="result")

    __table_args__ = (
        UniqueConstraint("election_id", name="uq_election_results_election_id"),
        Index(
            "idx_election_results_jsonb",
            "results_data",
            postgresql_using="gin",
        ),
    )


class ElectionCountyResult(Base, UUIDMixin):
    """County-level election result for GeoJSON visualization."""

    __tablename__ = "election_county_results"

    election_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("elections.id", ondelete="CASCADE"),
        nullable=False,
    )
    county_name: Mapped[str] = mapped_column(String(100), nullable=False)
    county_name_normalized: Mapped[str] = mapped_column(String(100), nullable=False)
    precincts_participating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precincts_reporting: Mapped[int | None] = mapped_column(Integer, nullable=True)
    results_data: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    election: Mapped["Election"] = relationship(back_populates="county_results")

    __table_args__ = (
        UniqueConstraint("election_id", "county_name", name="uq_election_county_results"),
        Index("idx_election_county_results_election_id", "election_id"),
        Index("idx_election_county_results_county_normalized", "county_name_normalized"),
        Index(
            "idx_election_county_results_jsonb",
            "results_data",
            postgresql_using="gin",
        ),
    )
