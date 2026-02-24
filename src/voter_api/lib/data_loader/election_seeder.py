"""Fetch elections from a remote voter-api instance for DB seeding.

Standalone library module that fetches election data from a production
API and returns structured dicts ready for bulk upsert into the local
database.  Uses the paginated list endpoint for discovery and the detail
endpoint for fields (``data_source_url``, ``refresh_interval_seconds``)
that the list response omits.
"""

from __future__ import annotations

import httpx
from loguru import logger

# Timeout for individual HTTP requests (seconds).
_REQUEST_TIMEOUT = 30.0

# Maximum page size supported by the elections list endpoint.
_PAGE_SIZE = 100


async def fetch_elections_from_api(source_url: str) -> list[dict]:
    """Fetch all elections from a remote voter-api instance.

    Paginates through the list endpoint, then fetches each election's
    detail endpoint to obtain ``data_source_url`` and
    ``refresh_interval_seconds`` (not included in the list response).

    Args:
        source_url: Base URL of the source API
            (e.g. ``https://voteapi.civpulse.org``).

    Returns:
        A list of dicts, one per election, containing all fields needed
        for a bulk ``INSERT ... ON CONFLICT DO UPDATE`` into the
        ``elections`` table.

    Raises:
        httpx.HTTPStatusError: If any API request returns a non-2xx status.
        httpx.ConnectError: If the remote server is unreachable.
    """
    base = source_url.rstrip("/")
    elections: list[dict] = []

    async with httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        # --- Paginate through the list endpoint ---
        page = 1
        total_pages = 1  # will be updated from the first response

        while page <= total_pages:
            list_url = f"{base}/api/v1/elections?page={page}&page_size={_PAGE_SIZE}"
            logger.debug("Fetching election list page {}/{}: {}", page, total_pages, list_url)

            resp = await client.get(list_url)
            resp.raise_for_status()
            data = resp.json()

            total_pages = data["pagination"]["total_pages"]

            for item in data["items"]:
                elections.append(item)

            page += 1

        logger.info("Discovered {} elections from {}", len(elections), base)

        # --- Fetch detail for each election (adds data_source_url, refresh_interval_seconds) ---
        enriched: list[dict] = []
        for election in elections:
            detail_url = f"{base}/api/v1/elections/{election['id']}"
            logger.debug("Fetching election detail: {}", detail_url)

            resp = await client.get(detail_url)
            resp.raise_for_status()
            detail = resp.json()

            enriched.append(
                _extract_election_record(detail),
            )

    logger.info("Fetched details for {} elections", len(enriched))
    return enriched


def _extract_election_record(detail: dict) -> dict:
    """Extract DB-ready fields from an election detail API response.

    Args:
        detail: JSON response from ``GET /api/v1/elections/{id}``.

    Returns:
        A dict suitable for ``pg_insert(Election).values(...)``.
    """
    return {
        "id": detail["id"],
        "name": detail["name"],
        "election_date": detail["election_date"],
        "election_type": detail["election_type"],
        "district": detail["district"],
        "status": detail["status"],
        "data_source_url": detail["data_source_url"],
        "refresh_interval_seconds": detail["refresh_interval_seconds"],
        "ballot_item_id": detail.get("ballot_item_id"),
        "last_refreshed_at": detail.get("last_refreshed_at"),
        "creation_method": "manual",
    }
