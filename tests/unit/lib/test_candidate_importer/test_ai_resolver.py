"""Tests for candidate importer AI resolver."""

import json
from unittest.mock import MagicMock, patch

from voter_api.lib.candidate_importer.ai_resolver import resolve_contest_names_batch


def _make_unresolved(contest_name: str) -> dict:
    """Build an unresolved record dict."""
    return {"contest_name": contest_name, "candidate_name": "TEST"}


def _make_api_response(results: list[dict]) -> MagicMock:
    """Build a mock Anthropic API response."""
    text_block = MagicMock()
    text_block.text = json.dumps(results)
    message = MagicMock()
    message.content = [text_block]
    return message


class TestResolveContestNamesBatch:
    """Tests for resolve_contest_names_batch."""

    def test_successful_resolution(self) -> None:
        unresolved = [
            _make_unresolved("Governor (R)"),
            _make_unresolved("State Senate, District 18 (D)"),
        ]

        api_results = [
            {
                "contest_name": "Governor (R)",
                "district_type": "statewide",
                "district_identifier": None,
                "district_party": "Republican",
            },
            {
                "contest_name": "State Senate, District 18 (D)",
                "district_type": "state_senate",
                "district_identifier": "18",
                "district_party": "Democrat",
            },
        ]

        with patch(
            "voter_api.lib.candidate_importer.ai_resolver._call_api",
            return_value=api_results,
        ):
            result = resolve_contest_names_batch(unresolved, "test-key")

        assert result[0]["district_type"] == "statewide"
        assert result[0]["district_party"] == "Republican"
        assert result[1]["district_type"] == "state_senate"
        assert result[1]["district_identifier"] == "18"

    def test_graceful_degradation_on_api_failure(self) -> None:
        unresolved = [_make_unresolved("Some Unknown Contest")]

        with patch(
            "voter_api.lib.candidate_importer.ai_resolver._call_api",
            return_value=None,
        ):
            result = resolve_contest_names_batch(unresolved, "test-key")

        assert result[0]["_needs_manual_review"] is True

    def test_deduplication(self) -> None:
        # 5 records with only 2 unique contest names
        unresolved = [
            _make_unresolved("Governor (R)"),
            _make_unresolved("Governor (R)"),
            _make_unresolved("Governor (R)"),
            _make_unresolved("State Senate, District 18 (D)"),
            _make_unresolved("State Senate, District 18 (D)"),
        ]

        api_results = [
            {
                "contest_name": "Governor (R)",
                "district_type": "statewide",
                "district_identifier": None,
                "district_party": "Republican",
            },
            {
                "contest_name": "State Senate, District 18 (D)",
                "district_type": "state_senate",
                "district_identifier": "18",
                "district_party": "Democrat",
            },
        ]

        with patch(
            "voter_api.lib.candidate_importer.ai_resolver._call_api",
            return_value=api_results,
        ) as mock_call:
            result = resolve_contest_names_batch(unresolved, "test-key")

        # Only 1 API call should have been made (2 unique names < batch size of 50)
        mock_call.assert_called_once()

        # Verify the API received exactly 2 unique names
        call_args = mock_call.call_args
        sent_names = call_args[0][0]  # first positional arg
        assert len(sent_names) == 2

        # All 5 records should be resolved
        for rec in result:
            assert "district_type" in rec
            assert "_needs_manual_review" not in rec

    def test_empty_input(self) -> None:
        result = resolve_contest_names_batch([], "test-key")
        assert result == []

    def test_partial_api_resolution(self) -> None:
        """When API resolves some but not all names, unresolved get review flag."""
        unresolved = [
            _make_unresolved("Governor (R)"),
            _make_unresolved("Weird Contest Name"),
        ]

        # API only resolves Governor
        api_results = [
            {
                "contest_name": "Governor (R)",
                "district_type": "statewide",
                "district_identifier": None,
                "district_party": "Republican",
            },
        ]

        with patch(
            "voter_api.lib.candidate_importer.ai_resolver._call_api",
            return_value=api_results,
        ):
            result = resolve_contest_names_batch(unresolved, "test-key")

        assert result[0]["district_type"] == "statewide"
        assert result[1]["_needs_manual_review"] is True

    def test_call_api_with_real_mock_client(self) -> None:
        """Test _call_api through the actual anthropic import path."""
        from voter_api.lib.candidate_importer.ai_resolver import _call_api

        api_results = [
            {
                "contest_name": "Governor (R)",
                "district_type": "statewide",
                "district_identifier": None,
                "district_party": "Republican",
            },
        ]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_api_response(api_results)

        with patch("anthropic.Anthropic", return_value=mock_client):
            result = _call_api(["Governor (R)"], "test-key")

        assert result is not None
        assert len(result) == 1
        assert result[0]["district_type"] == "statewide"

    def test_call_api_handles_exception(self) -> None:
        """Test _call_api returns None on exception."""
        from voter_api.lib.candidate_importer.ai_resolver import _call_api

        with patch("anthropic.Anthropic", side_effect=Exception("Connection error")):
            result = _call_api(["Governor (R)"], "test-key")

        assert result is None
