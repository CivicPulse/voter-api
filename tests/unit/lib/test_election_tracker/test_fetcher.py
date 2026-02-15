"""Unit tests for SoS feed fetcher."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from voter_api.lib.election_tracker.fetcher import (
    FetchError,
    fetch_election_results,
    validate_url_domain,
)
from voter_api.lib.election_tracker.parser import SoSFeed


def _make_feed_json():
    """Return a minimal valid SoS feed JSON dict."""
    return {
        "electionDate": "2026-02-17",
        "electionName": "Test Election",
        "createdAt": "2026-02-09T17:40:56Z",
        "results": {
            "id": "state-001",
            "name": "Georgia",
            "ballotItems": [],
        },
        "localResults": [],
    }


class TestFetchElectionResults:
    """Tests for fetch_election_results()."""

    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        feed_json = _make_feed_json()
        mock_response = httpx.Response(
            200,
            json=feed_json,
            request=httpx.Request("GET", "https://example.com/feed.json"),
        )
        with patch("voter_api.lib.election_tracker.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await fetch_election_results("https://example.com/feed.json")
            assert isinstance(result, SoSFeed)
            assert result.electionName == "Test Election"

    @pytest.mark.asyncio
    async def test_timeout_raises_fetch_error(self):
        with patch("voter_api.lib.election_tracker.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(FetchError, match="Timeout"):
                await fetch_election_results("https://example.com/feed.json")

    @pytest.mark.asyncio
    async def test_http_404_raises_fetch_error(self):
        mock_response = httpx.Response(
            404,
            request=httpx.Request("GET", "https://example.com/feed.json"),
        )
        with patch("voter_api.lib.election_tracker.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(FetchError, match="HTTP 404"):
                await fetch_election_results("https://example.com/feed.json")

    @pytest.mark.asyncio
    async def test_http_500_raises_fetch_error(self):
        mock_response = httpx.Response(
            500,
            request=httpx.Request("GET", "https://example.com/feed.json"),
        )
        with patch("voter_api.lib.election_tracker.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(FetchError, match="HTTP 500"):
                await fetch_election_results("https://example.com/feed.json")

    @pytest.mark.asyncio
    async def test_invalid_json_raises_fetch_error(self):
        mock_response = httpx.Response(
            200,
            content=b"not json",
            request=httpx.Request("GET", "https://example.com/feed.json"),
            headers={"content-type": "text/plain"},
        )
        with patch("voter_api.lib.election_tracker.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(FetchError, match="Invalid JSON"):
                await fetch_election_results("https://example.com/feed.json")

    @pytest.mark.asyncio
    async def test_invalid_feed_structure_raises_fetch_error(self):
        mock_response = httpx.Response(
            200,
            json={"bad": "structure"},
            request=httpx.Request("GET", "https://example.com/feed.json"),
        )
        with patch("voter_api.lib.election_tracker.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(FetchError, match="Failed to parse"):
                await fetch_election_results("https://example.com/feed.json")

    @pytest.mark.asyncio
    async def test_allowed_domain_passes(self):
        """Fetch succeeds when domain is in the allowed list."""
        feed_json = _make_feed_json()
        mock_response = httpx.Response(
            200,
            json=feed_json,
            request=httpx.Request("GET", "https://results.enr.clarityelections.com/feed.json"),
        )
        with patch("voter_api.lib.election_tracker.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await fetch_election_results(
                "https://results.enr.clarityelections.com/feed.json",
                allowed_domains=["results.enr.clarityelections.com", "sos.ga.gov"],
            )
            assert isinstance(result, SoSFeed)

    @pytest.mark.asyncio
    async def test_disallowed_domain_raises_fetch_error(self):
        """Fetch raises FetchError when domain is not in allowed list."""
        with pytest.raises(FetchError, match="not in the allowed domains"):
            await fetch_election_results(
                "https://evil.example.com/feed.json",
                allowed_domains=["results.enr.clarityelections.com"],
            )

    @pytest.mark.asyncio
    async def test_localhost_blocked(self):
        """Internal addresses are blocked by domain allowlist."""
        with pytest.raises(FetchError, match="not in the allowed domains"):
            await fetch_election_results(
                "http://localhost:8080/metadata",
                allowed_domains=["results.enr.clarityelections.com"],
            )

    @pytest.mark.asyncio
    async def test_metadata_ip_blocked(self):
        """Cloud metadata IP is blocked by domain allowlist."""
        with pytest.raises(FetchError, match="not in the allowed domains"):
            await fetch_election_results(
                "http://169.254.169.254/latest/meta-data/",
                allowed_domains=["results.enr.clarityelections.com"],
            )

    @pytest.mark.asyncio
    async def test_empty_allowed_domains_skips_validation(self):
        """Empty allowed_domains list skips domain validation."""
        feed_json = _make_feed_json()
        mock_response = httpx.Response(
            200,
            json=feed_json,
            request=httpx.Request("GET", "https://any-domain.com/feed.json"),
        )
        with patch("voter_api.lib.election_tracker.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await fetch_election_results(
                "https://any-domain.com/feed.json",
                allowed_domains=[],
            )
            assert isinstance(result, SoSFeed)

    @pytest.mark.asyncio
    async def test_none_allowed_domains_skips_validation(self):
        """None allowed_domains skips domain validation entirely."""
        feed_json = _make_feed_json()
        mock_response = httpx.Response(
            200,
            json=feed_json,
            request=httpx.Request("GET", "https://any-domain.com/feed.json"),
        )
        with patch("voter_api.lib.election_tracker.fetcher.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await fetch_election_results("https://any-domain.com/feed.json")
            assert isinstance(result, SoSFeed)


class TestValidateUrlDomain:
    """Tests for validate_url_domain()."""

    def test_allowed_domain_passes(self):
        validate_url_domain("https://sos.ga.gov/results", ["sos.ga.gov"])

    def test_disallowed_domain_raises(self):
        with pytest.raises(FetchError, match="not in the allowed domains"):
            validate_url_domain("https://evil.com/data", ["sos.ga.gov"])

    def test_case_insensitive(self):
        validate_url_domain("https://SOS.GA.GOV/results", ["sos.ga.gov"])

    def test_empty_list_skips_validation(self):
        validate_url_domain("https://anything.com/data", [])

    def test_internal_ip_blocked(self):
        with pytest.raises(FetchError, match="not in the allowed domains"):
            validate_url_domain("http://169.254.169.254/latest", ["sos.ga.gov"])
