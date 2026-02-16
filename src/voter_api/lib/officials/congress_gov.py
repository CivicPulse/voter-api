"""Congress.gov API v3 provider for GA federal representatives and senators."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx
from loguru import logger

from voter_api.lib.officials.base import BaseOfficialsProvider, OfficialRecord, OfficialsProviderError

_BASE_URL = "https://api.congress.gov/v3"

# Current congress session (2025-2027)
_DEFAULT_CONGRESS = 119


class CongressGovProvider(BaseOfficialsProvider):
    """Fetches GA federal representative data from Congress.gov API v3.

    Args:
        api_key: Congress.gov API key.
        congress: Congress session number (default: 119 for 2025-2027).
    """

    def __init__(self, api_key: str, congress: int = _DEFAULT_CONGRESS) -> None:
        self._congress = congress
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            params={"api_key": api_key, "format": "json"},
            timeout=30.0,
        )

    @property
    def provider_name(self) -> str:
        return "congress_gov"

    async def fetch_by_district(
        self,
        boundary_type: str,
        district_identifier: str,
    ) -> list[OfficialRecord]:
        """Fetch officials for a specific GA federal district.

        Args:
            boundary_type: "congressional" or "us_senate".
            district_identifier: District number (for House) or "GA" (for Senate).

        Returns:
            List of OfficialRecord for the district.
        """
        if boundary_type == "congressional":
            return await self._fetch_house_district(district_identifier)
        if boundary_type == "us_senate":
            return await self._fetch_senators()
        msg = f"Unsupported boundary type for Congress.gov: {boundary_type}"
        raise OfficialsProviderError(self.provider_name, msg)

    async def fetch_all_ga_members(self) -> list[OfficialRecord]:
        """Fetch all current GA members of Congress (House + Senate).

        Returns:
            All current GA representatives and senators.
        """
        members = await self._fetch_member_list(
            f"/member/congress/{self._congress}/GA",
            params={"currentMember": "true", "limit": 250},
        )

        records: list[OfficialRecord] = []
        for member in members:
            bioguide_id = member.get("bioguideId", "")
            detail = await self._fetch_member_detail(bioguide_id)
            record = self._map_member(member, detail)
            if record is not None:
                records.append(record)

        return records

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_house_district(self, district: str) -> list[OfficialRecord]:
        """Fetch House representative(s) for a specific GA district."""
        members = await self._fetch_member_list(
            f"/member/congress/{self._congress}/GA/{district}",
            params={"currentMember": "true"},
        )

        records: list[OfficialRecord] = []
        for member in members:
            bioguide_id = member.get("bioguideId", "")
            detail = await self._fetch_member_detail(bioguide_id)
            record = self._map_member(member, detail)
            if record is not None:
                records.append(record)

        return records

    async def _fetch_senators(self) -> list[OfficialRecord]:
        """Fetch current GA senators."""
        members = await self._fetch_member_list(
            f"/member/congress/{self._congress}/GA",
            params={"currentMember": "true", "limit": 250},
        )

        # Filter to senators only (no district number)
        senators = [m for m in members if m.get("district") is None]

        records: list[OfficialRecord] = []
        for member in senators:
            bioguide_id = member.get("bioguideId", "")
            detail = await self._fetch_member_detail(bioguide_id)
            record = self._map_member(member, detail)
            if record is not None:
                records.append(record)

        return records

    async def _fetch_member_list(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Fetch a list of members from the Congress.gov API."""
        data = await self._request(path, params)
        members: list[dict[str, Any]] = data.get("members", [])
        return members

    async def _fetch_member_detail(self, bioguide_id: str) -> dict[str, Any]:
        """Fetch detailed member info by bioguide ID."""
        data = await self._request(f"/member/{bioguide_id}")
        member: dict[str, Any] = data.get("member", {})
        return member

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make an authenticated GET request to the Congress.gov API."""
        try:
            response = await self._client.get(path, params=params or {})
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Congress.gov API error: {} {} for {}",
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
            logger.error("Congress.gov request failed: {}", exc)
            raise OfficialsProviderError(
                self.provider_name,
                f"Request failed: {exc}",
            ) from exc
        except json.JSONDecodeError as exc:
            logger.error("Congress.gov returned non-JSON response for {}", path)
            raise OfficialsProviderError(
                self.provider_name,
                f"Invalid JSON response for {path}",
            ) from exc

    def _map_member(self, summary: dict, detail: dict) -> OfficialRecord | None:
        """Map Congress.gov member data to an OfficialRecord.

        Returns None and logs a warning if the member is missing a bioguideId
        or name.

        Args:
            summary: Member data from the list endpoint.
            detail: Member data from the detail endpoint.
        """
        source_id = summary.get("bioguideId") or ""
        full_name = detail.get("directOrderName") or summary.get("name") or ""
        if not source_id or not full_name:
            logger.warning(
                "Skipping Congress.gov member with missing bioguideId={!r} or name={!r}",
                source_id,
                full_name,
            )
            return None

        # Determine if senator or representative
        district = summary.get("district")
        if district is None:
            boundary_type = "us_senate"
            district_identifier = "GA"
            title = "U.S. Senator"
        else:
            boundary_type = "congressional"
            district_identifier = str(district)
            title = "U.S. Representative"

        # Party name from summary or detail
        party = summary.get("partyName") or detail.get("partyName")

        # Photo URL
        depiction = detail.get("depiction") or {}
        photo_url = depiction.get("imageUrl")

        # Contact info from detail
        website = detail.get("officialWebsiteUrl")
        phone = detail.get("phoneNumber")
        office_address = detail.get("officeAddress")

        # Term start date from the most recent term
        term_start_date = self._parse_term_start(detail.get("terms"))

        # Combine summary + detail for raw_data
        raw_data = {"summary": summary, "detail": detail}

        return OfficialRecord(
            source_name=self.provider_name,
            source_record_id=source_id,
            boundary_type=boundary_type,
            district_identifier=district_identifier,
            full_name=full_name,
            first_name=detail.get("firstName") or summary.get("firstName"),
            last_name=detail.get("lastName") or summary.get("lastName"),
            party=party,
            title=title,
            photo_url=photo_url,
            website=website,
            phone=phone,
            office_address=office_address,
            term_start_date=term_start_date,
            raw_data=raw_data,
        )

    @staticmethod
    def _parse_term_start(terms: list[dict] | None) -> date | None:
        """Safely parse the start date from the most recent term."""
        if not terms:
            return None
        last_term = terms[-1]
        start_year = last_term.get("startYear")
        if not start_year:
            return None
        try:
            return date(int(start_year), 1, 3)
        except (ValueError, TypeError):
            logger.warning("Malformed startYear in term data: {!r}", start_year)
            return None
