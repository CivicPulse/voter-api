"""Open States API v3 provider for GA state legislators."""

import httpx
from loguru import logger

from voter_api.lib.officials.base import BaseOfficialsProvider, OfficialRecord, OfficialsProviderError

_BASE_URL = "https://v3.openstates.org"

# Map Open States org_classification to our boundary types
_ORG_TO_BOUNDARY = {
    "upper": "state_senate",
    "lower": "state_house",
}

# Reverse map for querying
_BOUNDARY_TO_ORG = {v: k for k, v in _ORG_TO_BOUNDARY.items()}


class OpenStatesProvider(BaseOfficialsProvider):
    """Fetches GA state legislator data from Open States API v3.

    Args:
        api_key: Open States API key.
    """

    def __init__(self, api_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"X-API-KEY": api_key},
            timeout=30.0,
        )

    @property
    def provider_name(self) -> str:
        return "open_states"

    async def fetch_by_district(
        self,
        boundary_type: str,
        district_identifier: str,
    ) -> list[OfficialRecord]:
        """Fetch officials for a specific GA legislative district.

        Args:
            boundary_type: Must be "state_senate" or "state_house".
            district_identifier: District number (e.g. "39").

        Returns:
            List of OfficialRecord for the district.
        """
        org_classification = _BOUNDARY_TO_ORG.get(boundary_type)
        if org_classification is None:
            msg = f"Unsupported boundary type for Open States: {boundary_type}"
            raise OfficialsProviderError(self.provider_name, msg)

        params: dict[str, str | int] = {
            "jurisdiction": "Georgia",
            "org_classification": org_classification,
            "district": district_identifier,
            "include": "offices",
            "per_page": 10,
        }
        return await self._fetch_people(params)

    async def fetch_all_for_chamber(
        self,
        org_classification: str,
    ) -> list[OfficialRecord]:
        """Fetch all current legislators for a chamber.

        Args:
            org_classification: "upper" (senate) or "lower" (house).

        Returns:
            All current legislators for the chamber.
        """
        params: dict[str, str | int] = {
            "jurisdiction": "Georgia",
            "org_classification": org_classification,
            "include": "offices",
            "per_page": 100,
        }
        return await self._fetch_people(params)

    async def fetch_by_point(
        self,
        latitude: float,
        longitude: float,
    ) -> list[OfficialRecord]:
        """Fetch officials for a geographic point via Open States geo-lookup.

        Args:
            latitude: WGS84 latitude.
            longitude: WGS84 longitude.

        Returns:
            List of OfficialRecord for officials representing the point.
        """
        params: dict[str, str | float] = {
            "lat": latitude,
            "lng": longitude,
            "include": "offices",
        }
        response = await self._request("/people.geo", params)
        results = response.get("results", [])
        return [self._map_person(person) for person in results]

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_people(
        self,
        params: dict,
    ) -> list[OfficialRecord]:
        """Paginate through /people endpoint and collect all results."""
        records: list[OfficialRecord] = []
        page = 1

        while True:
            params["page"] = page
            data = await self._request("/people", params)
            results = data.get("results", [])
            records.extend(self._map_person(person) for person in results)

            pagination = data.get("pagination", {})
            max_page = pagination.get("max_page", 1)
            if page >= max_page:
                break
            page += 1

        return records

    async def _request(self, path: str, params: dict) -> dict:
        """Make an authenticated GET request to the Open States API."""
        try:
            response = await self._client.get(path, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Open States API error: {} {} for {}",
                exc.response.status_code,
                exc.response.reason_phrase,
                path,
            )
            raise OfficialsProviderError(
                self.provider_name,
                f"HTTP {exc.response.status_code}: {exc.response.reason_phrase}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            logger.error("Open States request failed: {}", exc)
            raise OfficialsProviderError(
                self.provider_name,
                f"Request failed: {exc}",
            ) from exc

    def _map_person(self, person: dict) -> OfficialRecord:
        """Map an Open States person object to an OfficialRecord."""
        current_role = person.get("current_role") or {}
        offices = person.get("offices") or []
        links = person.get("links") or []

        # Derive boundary type from org_classification
        org_classification = current_role.get("org_classification", "")
        boundary_type = _ORG_TO_BOUNDARY.get(org_classification, org_classification)

        # Contact info from first office
        first_office = offices[0] if offices else {}

        # Website: prefer openstates_url, fall back to first link
        website = person.get("openstates_url")
        if not website and links:
            website = links[0].get("url")

        return OfficialRecord(
            source_name=self.provider_name,
            source_record_id=person.get("id", ""),
            boundary_type=boundary_type,
            district_identifier=str(current_role.get("district", "")),
            full_name=person.get("name", ""),
            first_name=person.get("given_name"),
            last_name=person.get("family_name"),
            party=person.get("party"),
            title=current_role.get("title"),
            photo_url=person.get("image"),
            email=person.get("email"),
            website=website,
            phone=first_office.get("voice"),
            office_address=first_office.get("address"),
            raw_data=person,
        )
