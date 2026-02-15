"""Unit tests for SoS feed fetcher."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from voter_api.lib.election_tracker.fetcher import FetchError, fetch_election_results
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
