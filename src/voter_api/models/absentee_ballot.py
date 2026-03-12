"""AbsenteeBallotApplication model — GA SoS absentee ballot application data."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, UUIDMixin


class AbsenteeBallotApplication(Base, UUIDMixin):
    """Absentee ballot application record from the GA Secretary of State.

    Each row represents one absentee ballot application for a voter in a
    specific election/ballot style. Sourced from GA SoS bulk absentee
    ballot data files.
    """

    __tablename__ = "absentee_ballot_applications"

    # Voter identification
    county: Mapped[str] = mapped_column(String(100), nullable=False)
    voter_registration_number: Mapped[str] = mapped_column(String(20), nullable=False)

    # Name fields
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    suffix: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Residence address
    street_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    street_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    apt_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Mailing address
    mailing_street_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mailing_street_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mailing_apt_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mailing_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mailing_state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    mailing_zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Status fields
    application_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ballot_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Date fields
    application_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    ballot_issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    ballot_return_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Ballot details
    ballot_style: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ballot_assisted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    challenged_provisional: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    id_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Precinct / district fields
    municipal_precinct: Mapped[str | None] = mapped_column(String(20), nullable=True)
    county_precinct: Mapped[str | None] = mapped_column(String(20), nullable=True)
    congressional_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    state_senate_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    state_house_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    judicial_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    combo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vote_center_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ballot_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    party: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Import tracking
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("import_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps (created_at only — no updated_at for append-only import data)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    import_job = relationship("ImportJob", lazy="selectin")

    __table_args__ = (
        UniqueConstraint(
            "voter_registration_number",
            "application_date",
            "ballot_style",
            name="uq_aba_voter_appdate_ballotstyle",
        ),
        Index("ix_aba_voter_reg_num", "voter_registration_number"),
        Index("ix_aba_county", "county"),
        Index("ix_aba_application_status", "application_status"),
        Index("ix_aba_ballot_status", "ballot_status"),
        Index("ix_aba_import_job_id", "import_job_id"),
    )
