"""Unit tests for results file loading and ballot item iteration."""

import json
from pathlib import Path

import pytest

from voter_api.lib.results_importer.parser import (
    iter_ballot_items,
    load_results_file,
)


@pytest.fixture()
def sample_feed_json(tmp_path: Path) -> Path:
    """Create a minimal valid SoS results JSON file."""
    data = {
        "electionDate": "2026-01-06",
        "electionName": "January 6, 2026 \u2013 HD 23 Special Election Runoff",
        "createdAt": "2026-01-28T22:27:45Z",
        "results": {
            "id": "test-id",
            "name": "Georgia",
            "ballotItems": [
                {
                    "id": "SHD23",
                    "name": "State House of Representatives - District 23",
                    "voteFor": 1,
                    "ballotOptions": [
                        {
                            "id": "1",
                            "name": "Bill Fincher (Rep)",
                            "ballotOrder": 1,
                            "voteCount": 4345,
                            "politicalParty": "Rep",
                            "groupResults": [],
                        },
                        {
                            "id": "5",
                            "name": "Scott Sanders (Dem)",
                            "ballotOrder": 2,
                            "voteCount": 1742,
                            "politicalParty": "Dem",
                            "groupResults": [],
                        },
                    ],
                }
            ],
        },
        "localResults": [
            {
                "id": "county1",
                "name": "Cherokee County",
                "ballotItems": [
                    {
                        "id": "SHD23",
                        "name": "State House of Representatives - District 23",
                        "voteFor": 1,
                        "precinctsParticipating": 8,
                        "precinctsReporting": 8,
                        "ballotOptions": [
                            {
                                "id": "1",
                                "name": "Bill Fincher (Rep)",
                                "ballotOrder": 1,
                                "voteCount": 4345,
                                "politicalParty": "Rep",
                                "groupResults": [],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    path = tmp_path / "test_results.json"
    path.write_text(json.dumps(data))
    return path


class TestLoadResultsFile:
    def test_loads_valid_json(self, sample_feed_json: Path) -> None:
        feed = load_results_file(sample_feed_json)
        assert feed.electionDate == "2026-01-06"
        assert feed.electionName == "January 6, 2026 \u2013 HD 23 Special Election Runoff"
        assert len(feed.results.ballotItems) == 1

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_results_file(tmp_path / "nonexistent.json")

    def test_invalid_json(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            load_results_file(bad_file)


class TestIterBallotItems:
    def test_produces_contexts(self, sample_feed_json: Path) -> None:
        feed = load_results_file(sample_feed_json)
        contexts = iter_ballot_items(feed)
        assert len(contexts) == 1

        ctx = contexts[0]
        assert ctx.ballot_item_id == "SHD23"
        assert ctx.ballot_item_name == "State House of Representatives - District 23"
        assert str(ctx.election_date) == "2026-01-06"
        # "Runoff" appears in the name, so detect_election_type returns "runoff"
        assert ctx.election_type == "runoff"

    def test_candidates_parsed(self, sample_feed_json: Path) -> None:
        feed = load_results_file(sample_feed_json)
        contexts = iter_ballot_items(feed)
        candidates = contexts[0].candidates

        assert len(candidates) == 2
        assert candidates[0].full_name == "Bill Fincher"
        assert candidates[0].party == "Republican"
        assert candidates[0].vote_count == 4345
        assert candidates[0].sos_ballot_option_id == "1"

        assert candidates[1].full_name == "Scott Sanders"
        assert candidates[1].party == "Democrat"

    def test_ingestion_has_county_data(self, sample_feed_json: Path) -> None:
        feed = load_results_file(sample_feed_json)
        contexts = iter_ballot_items(feed)
        ingestion = contexts[0].ingestion

        assert len(ingestion.counties) == 1
        assert ingestion.counties[0].county_name == "Cherokee County"

    def test_multi_ballot_items(self, tmp_path: Path) -> None:
        """Feed with multiple ballot items produces multiple contexts."""
        data = {
            "electionDate": "2025-12-09",
            "electionName": "December 9th, 2025 - Special Election",
            "createdAt": "2025-12-10T00:00:00Z",
            "results": {
                "id": "r1",
                "name": "Georgia",
                "ballotItems": [
                    {
                        "id": "SHD23",
                        "name": "State House - District 23",
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
                    },
                    {
                        "id": "SHD121",
                        "name": "State House - District 121",
                        "ballotOptions": [
                            {
                                "id": "2",
                                "name": "Candidate B",
                                "ballotOrder": 1,
                                "voteCount": 200,
                                "politicalParty": "Dem",
                                "groupResults": [],
                            },
                        ],
                    },
                ],
            },
            "localResults": [],
        }
        path = tmp_path / "multi.json"
        path.write_text(json.dumps(data))

        feed = load_results_file(path)
        contexts = iter_ballot_items(feed)
        assert len(contexts) == 2
        assert contexts[0].ballot_item_id == "SHD23"
        assert contexts[1].ballot_item_id == "SHD121"
