"""Abstract base interface for elected-official data providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


@dataclass
class OfficialRecord:
    """Normalized representation of an elected official from any provider.

    Providers parse their raw responses into this common shape so the
    service layer can upsert source records without knowing provider details.
    """

    # Source identification
    source_name: str
    source_record_id: str

    # District
    boundary_type: str
    district_identifier: str

    # Person
    full_name: str
    first_name: str | None = None
    last_name: str | None = None
    party: str | None = None
    title: str | None = None
    photo_url: str | None = None

    # Term dates
    term_start_date: date | None = None
    term_end_date: date | None = None

    # Contact
    website: str | None = None
    email: str | None = None
    phone: str | None = None
    office_address: str | None = None

    # Raw response for auditing
    raw_data: dict = field(default_factory=dict)


class OfficialsProviderError(Exception):
    """Raised when a provider experiences a transport or service error.

    Args:
        provider_name: Name of the failing provider.
        message: Human-readable error description.
        status_code: Optional HTTP status code from the provider.
    """

    def __init__(self, provider_name: str, message: str, status_code: int | None = None) -> None:
        self.provider_name = provider_name
        self.message = message
        self.status_code = status_code
        super().__init__(f"{provider_name}: {message}")


class BaseOfficialsProvider(ABC):
    """Abstract interface for elected-official data providers.

    Concrete implementations (Congress.gov, Open States, etc.) must
    implement the methods below. The service layer calls these to
    fetch and normalize records from external sources.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique short name for this provider (e.g. 'open_states')."""

    @abstractmethod
    async def fetch_by_district(
        self,
        boundary_type: str,
        district_identifier: str,
    ) -> list[OfficialRecord]:
        """Fetch officials for a specific district.

        Args:
            boundary_type: Boundary type (e.g. "congressional", "state_senate").
            district_identifier: District number/code.

        Returns:
            List of normalized official records from this provider.
        """

    async def fetch_by_point(
        self,
        latitude: float,
        longitude: float,
    ) -> list[OfficialRecord]:
        """Fetch officials for a geographic point (geo-lookup).

        Default implementation raises NotImplementedError.
        Providers with geo-lookup support (e.g. Open States /people.geo)
        should override this.

        Args:
            latitude: WGS84 latitude.
            longitude: WGS84 longitude.

        Returns:
            List of normalized official records.
        """
        msg = f"{self.provider_name} does not support geo-lookup"
        raise NotImplementedError(msg)
