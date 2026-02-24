"""Add district resolution columns to elections and election_id FK to voter_history.

Revision ID: 028
Revises: 027
Create Date: 2026-02-24

Adds structured district fields to elections (parsed from free-text `district`
column) plus a direct `boundary_id` FK linking each election to its GIS
boundary. Adds `election_id` FK to voter_history for resolved election links.

Also backfills the new election columns by parsing existing district text.
"""

import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None

# --- District parsing logic (duplicated from lib to avoid app imports) ---

_PREFIX_MAP = [
    ("state house of representatives", "state_house"),
    ("us house of representatives", "congressional"),
    ("state senate", "state_senate"),
    ("psc", "psc"),
]

_DISTRICT_NUMBER_RE = re.compile(r"District\s+(\d+)", re.IGNORECASE)
_PARTY_SUFFIX_RE = re.compile(r"-\s*(Dem|Rep)\s*$", re.IGNORECASE)

_BOUNDARY_TYPE_MAP = {
    "state_senate": "state_senate",
    "state_house": "state_house",
    "congressional": "congressional",
    "psc": "psc",
}


def _parse_district(district_text):
    """Parse district text -> (district_type, identifier, party)."""
    text = district_text
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    if text.lower().startswith("special "):
        text = text[len("special ") :]

    district_type = None
    lower = text.lower()
    for prefix, dtype in _PREFIX_MAP:
        if lower.startswith(prefix):
            district_type = dtype
            break
    if district_type is None:
        return None, None, None

    party = None
    party_match = _PARTY_SUFFIX_RE.search(text)
    if party_match:
        party = party_match.group(1)

    identifier = None
    number_match = _DISTRICT_NUMBER_RE.search(text)
    if number_match:
        identifier = number_match.group(1)

    return district_type, identifier, party


def upgrade() -> None:
    """Add district resolution columns and backfill from existing data."""
    # --- Elections: add 4 columns ---
    op.add_column("elections", sa.Column("boundary_id", UUID(as_uuid=True), nullable=True))
    op.add_column("elections", sa.Column("district_type", sa.String(50), nullable=True))
    op.add_column("elections", sa.Column("district_identifier", sa.String(50), nullable=True))
    op.add_column("elections", sa.Column("district_party", sa.String(10), nullable=True))

    op.create_foreign_key(
        "fk_elections_boundary_id",
        "elections",
        "boundaries",
        ["boundary_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_elections_boundary_id", "elections", ["boundary_id"])
    op.create_index("idx_elections_district_type", "elections", ["district_type"])

    # --- Voter history: add election_id FK ---
    op.add_column("voter_history", sa.Column("election_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_voter_history_election_id",
        "voter_history",
        "elections",
        ["election_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_voter_history_election_id", "voter_history", ["election_id"])

    # --- Backfill election district fields ---
    conn = op.get_bind()
    elections = conn.execute(sa.text("SELECT id, district FROM elections")).fetchall()

    for election_id, district_text in elections:
        dtype, identifier, party = _parse_district(district_text)
        if dtype is None:
            continue

        # Look up boundary by (type, zero-padded identifier)
        boundary_id = None
        if identifier is not None:
            padded = identifier.zfill(3)
            boundary_type = _BOUNDARY_TYPE_MAP.get(dtype)
            if boundary_type:
                row = conn.execute(
                    sa.text(
                        "SELECT id FROM boundaries WHERE boundary_type = :btype AND boundary_identifier = :bid LIMIT 1"
                    ),
                    {"btype": boundary_type, "bid": padded},
                ).fetchone()
                if row:
                    boundary_id = row[0]

        conn.execute(
            sa.text(
                "UPDATE elections SET "
                "district_type = :dtype, "
                "district_identifier = :did, "
                "district_party = :party, "
                "boundary_id = :bid "
                "WHERE id = :eid"
            ),
            {
                "dtype": dtype,
                "did": identifier,
                "party": party,
                "bid": boundary_id,
                "eid": election_id,
            },
        )


def downgrade() -> None:
    """Remove district resolution columns."""
    op.drop_index("idx_voter_history_election_id", table_name="voter_history")
    op.drop_constraint("fk_voter_history_election_id", "voter_history", type_="foreignkey")
    op.drop_column("voter_history", "election_id")

    op.drop_index("idx_elections_district_type", table_name="elections")
    op.drop_index("idx_elections_boundary_id", table_name="elections")
    op.drop_constraint("fk_elections_boundary_id", "elections", type_="foreignkey")
    op.drop_column("elections", "district_party")
    op.drop_column("elections", "district_identifier")
    op.drop_column("elections", "district_type")
    op.drop_column("elections", "boundary_id")
