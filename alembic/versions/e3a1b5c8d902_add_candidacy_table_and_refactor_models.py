"""add candidacy table and refactor models

Revision ID: e3a1b5c8d902
Revises: d1f2b72fddbe
Create Date: 2026-03-15 01:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e3a1b5c8d902"
down_revision: str | None = "d1f2b72fddbe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- 1. Create candidacies table ---
    op.create_table(
        "candidacies",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("election_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("party", sa.String(length=50), nullable=True),
        sa.Column("filing_status", sa.String(length=20), server_default="qualified", nullable=False),
        sa.Column("ballot_order", sa.Integer(), nullable=True),
        sa.Column("is_incumbent", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("contest_name", sa.String(length=500), nullable=True),
        sa.Column("qualified_date", sa.Date(), nullable=True),
        sa.Column("occupation", sa.String(length=200), nullable=True),
        sa.Column("home_county", sa.String(length=100), nullable=True),
        sa.Column("municipality", sa.String(length=100), nullable=True),
        sa.Column("sos_ballot_option_id", sa.String(length=50), nullable=True),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["election_id"], ["elections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["import_job_id"], ["import_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "election_id", name="uq_candidacy_candidate_election"),
        sa.CheckConstraint(
            "filing_status IN ('qualified', 'withdrawn', 'disqualified', 'write_in')",
            name="ck_candidacy_filing_status",
        ),
    )
    op.create_index("ix_candidacies_candidate_id", "candidacies", ["candidate_id"])
    op.create_index("ix_candidacies_election_id", "candidacies", ["election_id"])
    op.create_index("ix_candidacies_filing_status", "candidacies", ["filing_status"])
    op.create_index("ix_candidacies_home_county", "candidacies", ["home_county"])

    # --- 2. Add new columns to election_events ---
    op.add_column("election_events", sa.Column("election_stage", sa.String(length=30), nullable=True))
    op.add_column("election_events", sa.Column("registration_deadline", sa.Date(), nullable=True))
    op.add_column("election_events", sa.Column("early_voting_start", sa.Date(), nullable=True))
    op.add_column("election_events", sa.Column("early_voting_end", sa.Date(), nullable=True))
    op.add_column("election_events", sa.Column("absentee_request_deadline", sa.Date(), nullable=True))
    op.add_column("election_events", sa.Column("qualifying_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("election_events", sa.Column("qualifying_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("election_events", sa.Column("data_source_url", sa.Text(), nullable=True))
    op.add_column("election_events", sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "election_events",
        sa.Column("refresh_interval_seconds", sa.Integer(), server_default="120", nullable=True),
    )

    # --- 3. Add election_stage to elections ---
    op.add_column("elections", sa.Column("election_stage", sa.String(length=30), nullable=True))

    # --- 4. Add external_ids JSONB column to candidates ---
    op.add_column("candidates", sa.Column("external_ids", postgresql.JSONB(), nullable=True))

    # --- 5. Make candidates.election_id nullable ---
    op.alter_column("candidates", "election_id", existing_type=postgresql.UUID(), nullable=True)

    # --- 6. Data migration: copy candidate contest-specific data to candidacies ---
    op.execute(
        """
        INSERT INTO candidacies (id, candidate_id, election_id, party, filing_status,
            ballot_order, is_incumbent, contest_name, qualified_date, occupation,
            home_county, municipality, sos_ballot_option_id, import_job_id, created_at, updated_at)
        SELECT gen_random_uuid(), c.id, c.election_id, c.party, c.filing_status,
            c.ballot_order, c.is_incumbent, c.contest_name, c.qualified_date, c.occupation,
            c.home_county, c.municipality, c.sos_ballot_option_id, c.import_job_id, now(), now()
        FROM candidates c
        WHERE c.election_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )

    # --- 7. Copy calendar fields from elections to election_events where linked ---
    op.execute(
        """
        UPDATE election_events ee
        SET
            registration_deadline = e.registration_deadline,
            early_voting_start = e.early_voting_start,
            early_voting_end = e.early_voting_end,
            absentee_request_deadline = e.absentee_request_deadline,
            qualifying_start = e.qualifying_start,
            qualifying_end = e.qualifying_end,
            data_source_url = e.data_source_url,
            last_refreshed_at = e.last_refreshed_at,
            refresh_interval_seconds = e.refresh_interval_seconds
        FROM elections e
        WHERE e.election_event_id = ee.id
            AND (
                e.registration_deadline IS NOT NULL
                OR e.early_voting_start IS NOT NULL
                OR e.early_voting_end IS NOT NULL
                OR e.absentee_request_deadline IS NOT NULL
                OR e.qualifying_start IS NOT NULL
                OR e.qualifying_end IS NOT NULL
            )
        """
    )


def downgrade() -> None:
    # --- Reverse step 5: make candidates.election_id NOT NULL again ---
    # First, delete any candidates with NULL election_id (created after migration)
    op.execute("DELETE FROM candidates WHERE election_id IS NULL")
    op.alter_column("candidates", "election_id", existing_type=postgresql.UUID(), nullable=False)

    # --- Reverse step 4: drop external_ids from candidates ---
    op.drop_column("candidates", "external_ids")

    # --- Reverse step 3: drop election_stage from elections ---
    op.drop_column("elections", "election_stage")

    # --- Reverse step 2: drop new columns from election_events ---
    op.drop_column("election_events", "refresh_interval_seconds")
    op.drop_column("election_events", "last_refreshed_at")
    op.drop_column("election_events", "data_source_url")
    op.drop_column("election_events", "qualifying_end")
    op.drop_column("election_events", "qualifying_start")
    op.drop_column("election_events", "absentee_request_deadline")
    op.drop_column("election_events", "early_voting_end")
    op.drop_column("election_events", "early_voting_start")
    op.drop_column("election_events", "registration_deadline")
    op.drop_column("election_events", "election_stage")

    # --- Reverse step 1: drop candidacies table ---
    op.drop_index("ix_candidacies_home_county", "candidacies")
    op.drop_index("ix_candidacies_filing_status", "candidacies")
    op.drop_index("ix_candidacies_election_id", "candidacies")
    op.drop_index("ix_candidacies_candidate_id", "candidacies")
    op.drop_table("candidacies")
