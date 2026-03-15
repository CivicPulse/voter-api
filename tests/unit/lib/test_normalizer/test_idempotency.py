"""Hypothesis property-based idempotency tests for the normalizer.

Verifies the core idempotency property: normalize(normalize(input)) ==
normalize(input). Uses Hypothesis to generate random markdown-like
content with metadata tables and candidate tables.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from voter_api.lib.normalizer.normalize import (
    _normalize_candidate_file_content,
    _normalize_election_content,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Simple field values: printable ASCII, no leading/trailing pipe chars
_field_value_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Zs"),
        blacklist_characters="|",
    ),
    min_size=0,
    max_size=40,
).map(str.strip)

# Known date formats for generating test dates
_slash_date_st = st.builds(
    lambda m, d, y: f"{m:02d}/{d:02d}/{y:04d}",
    m=st.integers(min_value=1, max_value=12),
    d=st.integers(min_value=1, max_value=28),
    y=st.integers(min_value=2000, max_value=2099),
)

_iso_date_st = st.builds(
    lambda m, d, y: f"{y:04d}-{m:02d}-{d:02d}",
    m=st.integers(min_value=1, max_value=12),
    d=st.integers(min_value=1, max_value=28),
    y=st.integers(min_value=2000, max_value=2099),
)

_date_or_placeholder_st = st.one_of(
    _slash_date_st,
    _iso_date_st,
    st.just("--"),
    st.just("\u2014"),
)

_url_st = st.one_of(
    st.builds(
        lambda domain: f"https://{domain}.com",
        domain=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz",
            min_size=3,
            max_size=15,
        ),
    ),
    st.just("--"),
    st.just("\u2014"),
)

# Metadata field names
_meta_field_name_st = st.sampled_from(
    [
        "Name (SOS)",
        "Type",
        "Stage",
        "Body",
        "Seat",
        "ID",
        "Format Version",
    ]
)

# Occupation strings -- may include acronyms or mixed case
_occupation_st = st.one_of(
    st.sampled_from(
        [
            "ATTORNEY",
            "Attorney",
            "CPA",
            "CNC MACHINIST",
            "Retired Educator",
            "FARMER",
            "Farmer",
            "EDUCATOR",
            "BUSINESSMAN",
            "cpa",
            "--",
        ]
    ),
    _field_value_st,
)

# Candidate name strategies -- includes SOS-style ALL CAPS
_candidate_name_st = st.one_of(
    st.sampled_from(
        [
            "JOHN SMITH",
            "JANE DOE",
            "John Smith",
            "DAVID MINCEY III",
            "JESSICA MCCLOUD",
            "JAMES JOHNSON JR",
            "MARCUS O'BRIEN",
        ]
    ),
    st.builds(
        lambda first, last: f"{first.upper()} {last.upper()}",
        first=st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            min_size=2,
            max_size=10,
        ),
        last=st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            min_size=2,
            max_size=12,
        ),
    ),
)


def _make_metadata_table(
    name_sos: str = "Test Election",
    type_val: str = "general_primary",
    stage: str = "election",
    date_val: str = "05/19/2026",
) -> str:
    """Build a minimal metadata table string.

    Args:
        name_sos: The Name (SOS) field value.
        type_val: The Type field value.
        stage: The Stage field value.
        date_val: The Date field value.

    Returns:
        Markdown metadata table string.
    """
    return (
        "## Metadata\n\n"
        "| Field | Value |\n"
        "|-------|-------|\n"
        f"| ID | |\n"
        f"| Format Version | 1 |\n"
        f"| Name (SOS) | {name_sos} |\n"
        f"| Date | {date_val} |\n"
        f"| Type | {type_val} |\n"
        f"| Stage | {stage} |\n"
    )


def _make_candidate_table(candidates: list[tuple[str, str, str]]) -> str:
    """Build a candidate table string.

    Args:
        candidates: List of (name, occupation, date) tuples.

    Returns:
        Markdown candidate table string.
    """
    lines = [
        "## Candidates\n",
        "| Candidate | Status | Incumbent | Occupation | Qualified Date |",
        "|-----------|--------|-----------|------------|----------------|",
    ]
    for name, occ, date in candidates:
        lines.append(f"| {name} | Qualified | No | {occ} | {date} |")
    return "\n".join(lines) + "\n"


def _make_election_markdown(
    name_sos: str,
    date_val: str,
    candidates: list[tuple[str, str, str]],
) -> str:
    """Build a complete election markdown string.

    Args:
        name_sos: The election name.
        date_val: The date value.
        candidates: Candidate data list.

    Returns:
        Complete markdown string.
    """
    return (
        f"# {name_sos}\n\n"
        + _make_metadata_table(name_sos=name_sos, date_val=date_val)
        + "\n"
        + _make_candidate_table(candidates)
    )


def _make_candidate_markdown(
    name: str,
    photo_url: str,
    occupation: str,
    qualified_date: str,
) -> str:
    """Build a candidate file markdown string.

    Args:
        name: Candidate full name.
        photo_url: Photo URL or placeholder.
        occupation: Occupation string.
        qualified_date: Qualified date string.

    Returns:
        Complete candidate markdown string.
    """
    return (
        f"# {name}\n\n"
        "## Metadata\n\n"
        "| Field | Value |\n"
        "|-------|-------|\n"
        "| ID | |\n"
        "| Format Version | 1 |\n"
        f"| Name | {name} |\n"
        f"| Photo URL | {photo_url} |\n"
        "| Email | -- |\n\n"
        "## Bio\n\n"
        "--\n\n"
        "## Elections\n\n"
        "### Test Election -- Test Contest\n\n"
        "| Field | Value |\n"
        "|-------|-------|\n"
        "| Election ID | 550e8400-e29b-41d4-a716-446655440000 |\n"
        "| Contest File | [Contest](../elections/2026-05-19/test.md) |\n"
        "| Party | Non-Partisan |\n"
        f"| Occupation | {occupation} |\n"
        "| Filing Status | qualified |\n"
        f"| Qualified Date | {qualified_date} |\n"
        "| Is Incumbent | No |\n"
    )


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Hypothesis-powered idempotency tests."""

    @given(
        name_sos=_field_value_st,
        date_val=_date_or_placeholder_st,
        candidate_name=_candidate_name_st,
        occupation=_occupation_st,
        qualified_date=_date_or_placeholder_st,
    )
    @settings(max_examples=50, deadline=2000)
    def test_election_content_idempotent(
        self,
        name_sos: str,
        date_val: str,
        candidate_name: str,
        occupation: str,
        qualified_date: str,
    ) -> None:
        """normalize(normalize(election_content)) == normalize(election_content).

        For any election markdown content, applying normalization twice
        should produce the same result as applying it once.
        """
        candidates = [(candidate_name, occupation, qualified_date)]
        content = _make_election_markdown(name_sos, date_val, candidates)

        # First normalization
        once, changes1, _warnings1 = _normalize_election_content(content)

        # Second normalization (on already-normalized content)
        twice, changes2, _warnings2 = _normalize_election_content(once)

        assert once == twice, (
            f"Election normalization is not idempotent.\n"
            f"First pass changes: {len(changes1)}\n"
            f"Second pass changes: {len(changes2)}\n"
            f"Changes on second pass:\n"
            + "\n".join(f"  [{c.field_name}] {c.original!r} -> {c.normalized!r}" for c in changes2)
        )
        assert len(changes2) == 0, f"Second normalization pass made {len(changes2)} change(s) -- not idempotent"

    @given(
        name=_candidate_name_st,
        photo_url=_url_st,
        occupation=_occupation_st,
        qualified_date=_date_or_placeholder_st,
    )
    @settings(max_examples=50, deadline=2000)
    def test_candidate_content_idempotent(
        self,
        name: str,
        photo_url: str,
        occupation: str,
        qualified_date: str,
    ) -> None:
        """normalize(normalize(candidate_content)) == normalize(candidate_content).

        For any candidate markdown content, applying normalization twice
        should produce the same result as applying it once.
        """
        content = _make_candidate_markdown(name, photo_url, occupation, qualified_date)

        # First normalization
        once, changes1, _warnings1 = _normalize_candidate_file_content(content)

        # Second normalization (on already-normalized content)
        twice, changes2, _warnings2 = _normalize_candidate_file_content(once)

        assert once == twice, (
            f"Candidate normalization is not idempotent.\n"
            f"First pass changes: {len(changes1)}\n"
            f"Second pass changes: {len(changes2)}\n"
            f"Changes on second pass:\n"
            + "\n".join(f"  [{c.field_name}] {c.original!r} -> {c.normalized!r}" for c in changes2)
        )
        assert len(changes2) == 0, f"Second normalization pass made {len(changes2)} change(s) -- not idempotent"

    @given(
        name_sos=st.sampled_from(
            [
                "GEORGIA 2026 GENERAL PRIMARY",
                "Georgia 2026 General Primary",
                "BIBB COUNTY LOCAL ELECTIONS",
                "US SENATE",
                "Governor",
            ]
        ),
        date_val=_date_or_placeholder_st,
    )
    @settings(max_examples=20, deadline=2000)
    def test_election_round_trip_stable(
        self,
        name_sos: str,
        date_val: str,
    ) -> None:
        """A normalized file normalized again produces identical content.

        This verifies the round-trip property for common election name patterns.
        """
        content = _make_election_markdown(name_sos, date_val, [])
        once, _, _ = _normalize_election_content(content)
        twice, _, _ = _normalize_election_content(once)
        assert once == twice
