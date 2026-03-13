"""Unit tests for results file validation."""

from voter_api.lib.election_tracker.parser import SoSFeed
from voter_api.lib.results_importer.validator import validate_results_file


def _make_feed(**overrides) -> SoSFeed:
    """Build a minimal SoSFeed for testing."""
    defaults = {
        "electionDate": "2026-01-06",
        "electionName": "Test Election",
        "createdAt": "2026-01-07T00:00:00Z",
        "results": {
            "id": "r1",
            "name": "Georgia",
            "ballotItems": [
                {
                    "id": "BI1",
                    "name": "Test Race",
                    "ballotOptions": [
                        {
                            "id": "1",
                            "name": "Candidate A",
                            "ballotOrder": 1,
                            "voteCount": 100,
                            "politicalParty": "Rep",
                            "groupResults": [],
                        },
                    ],
                }
            ],
        },
        "localResults": [],
    }
    defaults.update(overrides)
    return SoSFeed.model_validate(defaults)


class TestValidateResultsFile:
    def test_valid_feed_no_errors(self):
        feed = _make_feed()
        assert validate_results_file(feed) == []

    def test_missing_election_date(self):
        feed = _make_feed(electionDate="")
        errors = validate_results_file(feed)
        assert any("electionDate" in e for e in errors)

    def test_no_ballot_items(self):
        feed = _make_feed(results={"id": "r1", "name": "Georgia", "ballotItems": []})
        errors = validate_results_file(feed)
        assert any("ballot items" in e.lower() for e in errors)

    def test_ballot_item_no_options(self):
        feed = _make_feed(
            results={
                "id": "r1",
                "name": "Georgia",
                "ballotItems": [
                    {
                        "id": "BI1",
                        "name": "Empty Race",
                        "ballotOptions": [],
                    },
                ],
            }
        )
        errors = validate_results_file(feed)
        assert any("no ballot options" in e.lower() for e in errors)
