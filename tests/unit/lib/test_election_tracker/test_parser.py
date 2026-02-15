"""Unit tests for SoS feed parser."""

import pytest
from pydantic import ValidationError

from voter_api.lib.election_tracker.parser import SoSFeed, parse_sos_feed


def _make_feed(**overrides):
    """Build a minimal valid SoS feed dict."""
    base = {
        "electionDate": "2026-02-17",
        "electionName": "February 17, 2026 Special Election",
        "createdAt": "2026-02-09T17:40:56.307557Z",
        "results": {
            "id": "state-001",
            "name": "Georgia",
            "ballotItems": [
                {
                    "id": "SSD18",
                    "name": "State Senate - District 18",
                    "precinctsParticipating": None,
                    "precinctsReporting": None,
                    "ballotOptions": [
                        {
                            "id": "2",
                            "name": "LeMario Nicholas Brown (Dem)",
                            "ballotOrder": 1,
                            "voteCount": 1234,
                            "politicalParty": "Dem",
                            "groupResults": [
                                {
                                    "groupName": "Election Day",
                                    "voteCount": 800,
                                    "isFromVirtualPrecinct": False,
                                },
                            ],
                        },
                    ],
                },
            ],
        },
        "localResults": [
            {
                "id": "county-001",
                "name": "Houston County",
                "ballotItems": [
                    {
                        "id": "SSD18",
                        "name": "State Senate - District 18",
                        "precinctsParticipating": 7,
                        "precinctsReporting": 5,
                        "ballotOptions": [
                            {
                                "id": "2",
                                "name": "LeMario Nicholas Brown (Dem)",
                                "ballotOrder": 1,
                                "voteCount": 42,
                                "politicalParty": "Dem",
                                "groupResults": [],
                            },
                        ],
                    },
                ],
            },
        ],
    }
    base.update(overrides)
    return base


class TestParseSosFeed:
    """Tests for parse_sos_feed()."""

    def test_valid_feed_parses_successfully(self):
        feed = parse_sos_feed(_make_feed())
        assert isinstance(feed, SoSFeed)
        assert feed.electionName == "February 17, 2026 Special Election"
        assert feed.electionDate == "2026-02-17"
        assert len(feed.results.ballotItems) == 1
        assert len(feed.localResults) == 1

    def test_statewide_candidates_parsed(self):
        feed = parse_sos_feed(_make_feed())
        ballot = feed.results.ballotItems[0]
        assert len(ballot.ballotOptions) == 1
        candidate = ballot.ballotOptions[0]
        assert candidate.name == "LeMario Nicholas Brown (Dem)"
        assert candidate.voteCount == 1234
        assert candidate.politicalParty == "Dem"

    def test_county_results_parsed(self):
        feed = parse_sos_feed(_make_feed())
        county = feed.localResults[0]
        assert county.name == "Houston County"
        ballot = county.ballotItems[0]
        assert ballot.precinctsParticipating == 7
        assert ballot.precinctsReporting == 5

    def test_group_results_parsed(self):
        feed = parse_sos_feed(_make_feed())
        groups = feed.results.ballotItems[0].ballotOptions[0].groupResults
        assert len(groups) == 1
        assert groups[0].groupName == "Election Day"
        assert groups[0].voteCount == 800

    def test_created_at_dt_property(self):
        feed = parse_sos_feed(_make_feed())
        dt = feed.created_at_dt
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 9

    def test_missing_required_field_raises_validation_error(self):
        raw = _make_feed()
        del raw["electionName"]
        with pytest.raises(ValidationError):
            parse_sos_feed(raw)

    def test_missing_results_raises_validation_error(self):
        raw = _make_feed()
        del raw["results"]
        with pytest.raises(ValidationError):
            parse_sos_feed(raw)

    def test_empty_local_results_ok(self):
        feed = parse_sos_feed(_make_feed(localResults=[]))
        assert feed.localResults == []

    def test_malformed_json_structure_raises_validation_error(self):
        with pytest.raises(ValidationError):
            parse_sos_feed({"bad": "data"})

    def test_multiple_candidates(self):
        raw = _make_feed()
        raw["results"]["ballotItems"][0]["ballotOptions"].append(
            {
                "id": "4",
                "name": "Steven McNeel (Rep)",
                "ballotOrder": 2,
                "voteCount": 5678,
                "politicalParty": "Rep",
                "groupResults": [],
            }
        )
        feed = parse_sos_feed(raw)
        assert len(feed.results.ballotItems[0].ballotOptions) == 2
