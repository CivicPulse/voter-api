"""SoS feed HTTP client for fetching election results.

Uses httpx for async HTTP requests with timeout and error handling.
Includes SSRF protection via domain allowlisting.
"""

from urllib.parse import urlparse

import httpx
from loguru import logger

from voter_api.lib.election_tracker.parser import SoSFeed, parse_sos_feed


class FetchError(Exception):
    """Raised when fetching election results fails."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def validate_url_domain(url: str, allowed_domains: list[str]) -> None:
    """Validate that a URL's hostname is in the allowed domains list.

    Args:
        url: The URL to validate.
        allowed_domains: List of allowed domain names (lowercase).

    Raises:
        FetchError: If the URL's hostname is not in the allowed list.
    """
    if not allowed_domains:
        return

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if not hostname or hostname not in allowed_domains:
        msg = f"Domain '{hostname}' is not in the allowed domains list"
        raise FetchError(msg)


async def fetch_election_results(
    url: str,
    timeout: float = 30.0,
    allowed_domains: list[str] | None = None,
) -> SoSFeed:
    """Fetch and parse election results from a SoS feed URL.

    Args:
        url: The SoS JSON feed URL.
        timeout: HTTP request timeout in seconds.
        allowed_domains: List of allowed domain names for SSRF protection.
            If None, domain validation is skipped.

    Returns:
        A validated SoSFeed instance.

    Raises:
        FetchError: If the HTTP request fails or the response is invalid.
    """
    if allowed_domains is not None:
        validate_url_domain(url, allowed_domains)

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            logger.debug("Fetching election results from {}", url)
            response = await client.get(url)
            response.raise_for_status()
    except httpx.TimeoutException as exc:
        msg = f"Timeout fetching election results from {url}"
        logger.error(msg)
        raise FetchError(msg) from exc
    except httpx.HTTPStatusError as exc:
        msg = f"HTTP {exc.response.status_code} fetching election results from {url}"
        logger.error(msg)
        raise FetchError(msg, status_code=exc.response.status_code) from exc
    except httpx.HTTPError as exc:
        msg = f"HTTP error fetching election results from {url}: {exc}"
        logger.error(msg)
        raise FetchError(msg) from exc

    try:
        raw_json = response.json()
    except ValueError as exc:
        msg = f"Invalid JSON response from {url}"
        logger.error(msg)
        raise FetchError(msg) from exc

    try:
        return parse_sos_feed(raw_json)
    except Exception as exc:
        msg = f"Failed to parse SoS feed from {url}: {exc}"
        logger.error(msg)
        raise FetchError(msg) from exc
