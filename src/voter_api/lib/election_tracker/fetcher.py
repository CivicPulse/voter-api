"""SoS feed HTTP client for fetching election results.

Uses httpx for async HTTP requests with timeout and error handling.
Includes SSRF protection via domain allowlisting.
"""

import ipaddress
import socket
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
    """Validate that a URL is safe to request and in the allowed domains list.

    This enforces:
        * Scheme must be http or https.
        * ``allowed_domains`` is non-empty.
        * Hostname must be in the allowed_domains list.
        * All resolved IP addresses must be public (no private/loopback/etc.).

    Args:
        url: The URL to validate.
        allowed_domains: Non-empty list of allowed domain names (lowercase).

    Raises:
        FetchError: If the URL is not safe or the hostname is not allowed.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        msg = f"Unsupported URL scheme '{parsed.scheme}'"
        raise FetchError(msg)

    hostname = (parsed.hostname or "").lower()

    if not hostname:
        msg = "URL must include a hostname"
        raise FetchError(msg)

    # Require a non-empty allowlist to prevent unrestricted outbound requests.
    if not allowed_domains:
        msg = "allowed_domains must be a non-empty list"
        raise FetchError(msg)

    if hostname not in allowed_domains:
        msg = f"Domain '{hostname}' is not in the allowed domains list"
        raise FetchError(msg)

    # Resolve hostname and ensure it does not point to a private or loopback IP.
    try:
        addrinfo_list = socket.getaddrinfo(hostname, parsed.port, type=socket.SOCK_STREAM)
    except OSError as exc:
        msg = f"Failed to resolve hostname '{hostname}': {exc}"
        raise FetchError(msg) from exc

    for family, _socktype, _proto, _canonname, sockaddr in addrinfo_list:
        ip_str = None
        if family == socket.AF_INET or family == socket.AF_INET6:
            ip_str = sockaddr[0]

        if not ip_str:
            continue

        ip = ipaddress.ip_address(ip_str)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            msg = f"Resolved IP address '{ip}' for hostname '{hostname}' is not allowed"
            raise FetchError(msg)


async def fetch_election_results(
    url: str,
    timeout: float = 30.0,
    *,
    allowed_domains: list[str],
) -> SoSFeed:
    """Fetch and parse election results from a SoS feed URL.

    Args:
        url: The SoS JSON feed URL.
        timeout: HTTP request timeout in seconds.
        allowed_domains: Non-empty list of allowed domain names for SSRF
            protection. Required to ensure every request is validated.

    Returns:
        A validated SoSFeed instance.

    Raises:
        FetchError: If the HTTP request fails or the response is invalid.
    """
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
