"""Absentee ballot application Pydantic v2 request/response schemas."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from voter_api.schemas.common import PaginationMeta


class AbsenteeBallotSummaryResponse(BaseModel):
    """Summary response for absentee ballot application list."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    county: str
    voter_registration_number: str
    first_name: str | None = None
    last_name: str | None = None
    application_status: str | None = None
    ballot_status: str | None = None
    application_date: date | None = None
    ballot_style: str | None = None
    party: str | None = None
    created_at: datetime


class AbsenteeBallotDetailResponse(AbsenteeBallotSummaryResponse):
    """Full detail response for absentee ballot application."""

    middle_name: str | None = None
    suffix: str | None = None
    street_number: str | None = None
    street_name: str | None = None
    apt_unit: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    mailing_street_number: str | None = None
    mailing_street_name: str | None = None
    mailing_apt_unit: str | None = None
    mailing_city: str | None = None
    mailing_state: str | None = None
    mailing_zip_code: str | None = None
    status_reason: str | None = None
    ballot_issued_date: date | None = None
    ballot_return_date: date | None = None
    ballot_assisted: bool | None = None
    challenged_provisional: bool | None = None
    id_required: bool | None = None
    municipal_precinct: str | None = None
    county_precinct: str | None = None
    congressional_district: str | None = None
    state_senate_district: str | None = None
    state_house_district: str | None = None
    judicial_district: str | None = None
    combo: str | None = None
    vote_center_id: str | None = None
    ballot_id: str | None = None
    import_job_id: uuid.UUID | None = None


class PaginatedAbsenteeResponse(BaseModel):
    """Paginated list of absentee ballot applications."""

    items: list[AbsenteeBallotSummaryResponse]
    pagination: PaginationMeta


class AbsenteeStatsResponse(BaseModel):
    """Aggregate statistics for absentee ballot applications."""

    total_applications: int
    by_county: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)
    by_party: dict[str, int] = Field(default_factory=dict)
