"""Voter Pydantic v2 request/response schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, computed_field

from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.voter_history import ParticipationSummary


class AddressResponse(BaseModel):
    """Voter residence address components."""

    street_number: str | None = None
    pre_direction: str | None = None
    street_name: str | None = None
    street_type: str | None = None
    post_direction: str | None = None
    apt_unit_number: str | None = None
    city: str | None = None
    zipcode: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def full_address(self) -> str:
        """Reconstruct full address from components."""
        parts = [
            self.street_number,
            self.pre_direction,
            self.street_name,
            self.street_type,
            self.post_direction,
        ]
        street = " ".join(p for p in parts if p)
        if self.apt_unit_number:
            street = f"{street} APT {self.apt_unit_number}"
        city_zip = ", ".join(p for p in [self.city, self.zipcode] if p)
        return f"{street}, {city_zip}" if city_zip else street


class MailingAddressResponse(BaseModel):
    """Voter mailing address components."""

    street_number: str | None = None
    street_name: str | None = None
    apt_unit_number: str | None = None
    city: str | None = None
    zipcode: str | None = None
    state: str | None = None
    country: str | None = None


class RegisteredDistrictsResponse(BaseModel):
    """Voter registered district assignments."""

    county_precinct: str | None = None
    county_precinct_description: str | None = None
    municipal_precinct: str | None = None
    municipal_precinct_description: str | None = None
    congressional_district: str | None = None
    state_senate_district: str | None = None
    state_house_district: str | None = None
    judicial_district: str | None = None
    county_commission_district: str | None = None
    school_board_district: str | None = None
    city_council_district: str | None = None
    municipal_school_board_district: str | None = None
    water_board_district: str | None = None
    super_council_district: str | None = None
    super_commissioner_district: str | None = None
    super_school_board_district: str | None = None
    fire_district: str | None = None
    combo: str | None = None
    land_lot: str | None = None
    land_district: str | None = None


class VoterSummaryResponse(BaseModel):
    """Compact voter summary for list views."""

    id: UUID
    county: str
    voter_registration_number: str
    status: str
    last_name: str
    first_name: str
    middle_name: str | None = None
    residence_city: str | None = None
    residence_zipcode: str | None = None
    present_in_latest_import: bool

    model_config = {"from_attributes": True}


class VoterDetailResponse(BaseModel):
    """Full voter detail including nested address and district objects."""

    id: UUID
    county: str
    voter_registration_number: str
    status: str
    status_reason: str | None = None
    last_name: str
    first_name: str
    middle_name: str | None = None
    suffix: str | None = None
    birth_year: int | None = None
    race: str | None = None
    gender: str | None = None

    residence_address: AddressResponse = Field(default_factory=AddressResponse)
    mailing_address: MailingAddressResponse = Field(default_factory=MailingAddressResponse)
    registered_districts: RegisteredDistrictsResponse = Field(default_factory=RegisteredDistrictsResponse)

    registration_date: date | None = None
    last_modified_date: date | None = None
    date_of_last_contact: date | None = None
    last_vote_date: date | None = None
    voter_created_date: date | None = None
    last_party_voted: str | None = None
    municipality: str | None = None

    participation_summary: ParticipationSummary = Field(default_factory=ParticipationSummary)

    present_in_latest_import: bool
    soft_deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedVoterResponse(BaseModel):
    """Paginated list of voter summaries."""

    items: list[VoterSummaryResponse]
    pagination: PaginationMeta
