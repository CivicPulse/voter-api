"""Create meeting records tables.

Revision ID: 023
Revises: 022
Create Date: 2026-02-19

Creates 6 new tables for the meeting records feature:
1. governing_body_types (lookup with seeded defaults)
2. governing_bodies (with partial unique and soft delete)
3. meetings (with approval workflow and FKs to users)
4. agenda_items (with generated tsvector and GIN index)
5. meeting_attachments (exclusive belongs-to pattern)
6. meeting_video_embeds (exclusive belongs-to pattern)

Also updates the users table CHECK constraint to include 'contributor' role.
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "023"
down_revision: str = "022"
branch_labels = None
depends_on = None

# Default governing body types to seed
_DEFAULT_TYPES = [
    ("county-commission", "County Commission", "A county-level governing commission"),
    ("city-council", "City Council", "A municipal city council"),
    ("school-board", "School Board", "A local school board or board of education"),
    ("planning-commission", "Planning Commission", "A planning and zoning commission"),
    ("water-authority", "Water Authority", "A water and sewer authority"),
    ("housing-authority", "Housing Authority", "A housing authority"),
    ("transit-authority", "Transit Authority", "A public transit authority"),
]


def upgrade() -> None:
    """Create meeting records tables and seed default types."""
    # 1. governing_body_types
    op.create_table(
        "governing_body_types",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_governing_body_type_name"),
        sa.UniqueConstraint("slug", name="uq_governing_body_type_slug"),
    )

    # Seed default types
    governing_body_types = sa.table(
        "governing_body_types",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("is_default", sa.Boolean),
    )
    op.bulk_insert(
        governing_body_types,
        [
            {
                "id": uuid.uuid4(),
                "slug": slug,
                "name": name,
                "description": desc,
                "is_default": True,
            }
            for slug, name, desc in _DEFAULT_TYPES
        ],
    )

    # 2. governing_bodies
    op.create_table(
        "governing_bodies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type_id", UUID(as_uuid=True), sa.ForeignKey("governing_body_types.id"), nullable=False),
        sa.Column("jurisdiction", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_governing_bodies_type_id", "governing_bodies", ["type_id"])
    op.create_index("ix_governing_bodies_jurisdiction", "governing_bodies", ["jurisdiction"])
    op.create_index("ix_governing_bodies_deleted_at", "governing_bodies", ["deleted_at"])
    # Partial unique: name+jurisdiction only for active records
    op.execute(
        "CREATE UNIQUE INDEX uq_governing_body_name_jurisdiction "
        "ON governing_bodies (name, jurisdiction) WHERE deleted_at IS NULL"
    )

    # 3. meetings
    op.create_table(
        "meetings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("governing_body_id", UUID(as_uuid=True), sa.ForeignKey("governing_bodies.id"), nullable=False),
        sa.Column("meeting_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("meeting_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("external_source_url", sa.String(1000), nullable=True),
        sa.Column("approval_status", sa.String(20), nullable=False, server_default="approved"),
        sa.Column("submitted_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "meeting_type IN ('regular', 'special', 'work_session', 'emergency', 'public_hearing')",
            name="ck_meeting_type",
        ),
        sa.CheckConstraint(
            "status IN ('scheduled', 'completed', 'cancelled', 'postponed')",
            name="ck_meeting_status",
        ),
        sa.CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected')",
            name="ck_meeting_approval_status",
        ),
    )
    op.create_index("ix_meetings_governing_body_id", "meetings", ["governing_body_id"])
    op.create_index("ix_meetings_date", "meetings", ["meeting_date"])
    op.create_index("ix_meetings_type_status", "meetings", ["meeting_type", "status"])
    op.create_index("ix_meetings_approval_status", "meetings", ["approval_status"])
    op.create_index("ix_meetings_submitted_by", "meetings", ["submitted_by"])
    op.create_index("ix_meetings_deleted_at", "meetings", ["deleted_at"])

    # 4. agenda_items (with generated tsvector column)
    op.create_table(
        "agenda_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("meeting_id", UUID(as_uuid=True), sa.ForeignKey("meetings.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("action_taken", sa.Text, nullable=True),
        sa.Column("disposition", sa.String(20), nullable=True),
        sa.Column("display_order", sa.Integer, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "disposition IS NULL OR disposition IN ('approved', 'denied', 'tabled', 'no_action', 'informational')",
            name="ck_agenda_item_disposition",
        ),
    )
    # Add the generated tsvector column
    op.execute(
        "ALTER TABLE agenda_items ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS ("
        "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
        "setweight(to_tsvector('english', coalesce(description, '')), 'B')"
        ") STORED"
    )
    op.create_index("ix_agenda_items_meeting_id", "agenda_items", ["meeting_id"])
    op.create_index("ix_agenda_items_search_vector", "agenda_items", ["search_vector"], postgresql_using="gin")
    # Partial unique: meeting_id+display_order for active records
    op.execute(
        "CREATE UNIQUE INDEX uq_agenda_item_meeting_order "
        "ON agenda_items (meeting_id, display_order) WHERE deleted_at IS NULL"
    )

    # 5. meeting_attachments
    op.create_table(
        "meeting_attachments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("meeting_id", UUID(as_uuid=True), sa.ForeignKey("meetings.id"), nullable=True),
        sa.Column("agenda_item_id", UUID(as_uuid=True), sa.ForeignKey("agenda_items.id"), nullable=True),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("stored_path", sa.String(1000), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(meeting_id IS NOT NULL AND agenda_item_id IS NULL) OR "
            "(meeting_id IS NULL AND agenda_item_id IS NOT NULL)",
            name="ck_attachment_parent",
        ),
    )
    op.create_index("ix_meeting_attachments_meeting_id", "meeting_attachments", ["meeting_id"])
    op.create_index("ix_meeting_attachments_agenda_item_id", "meeting_attachments", ["agenda_item_id"])
    op.create_index("ix_meeting_attachments_filename", "meeting_attachments", ["original_filename"])

    # 6. meeting_video_embeds
    op.create_table(
        "meeting_video_embeds",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("meeting_id", UUID(as_uuid=True), sa.ForeignKey("meetings.id"), nullable=True),
        sa.Column("agenda_item_id", UUID(as_uuid=True), sa.ForeignKey("agenda_items.id"), nullable=True),
        sa.Column("video_url", sa.String(1000), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False),
        sa.Column("start_seconds", sa.Integer, nullable=True),
        sa.Column("end_seconds", sa.Integer, nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(meeting_id IS NOT NULL AND agenda_item_id IS NULL) OR "
            "(meeting_id IS NULL AND agenda_item_id IS NOT NULL)",
            name="ck_video_embed_parent",
        ),
        sa.CheckConstraint("platform IN ('youtube', 'vimeo')", name="ck_video_embed_platform"),
        sa.CheckConstraint(
            "start_seconds IS NULL OR end_seconds IS NULL OR end_seconds > start_seconds",
            name="ck_video_embed_timestamps",
        ),
    )
    op.create_index("ix_meeting_video_embeds_meeting_id", "meeting_video_embeds", ["meeting_id"])
    op.create_index("ix_meeting_video_embeds_agenda_item_id", "meeting_video_embeds", ["agenda_item_id"])

    # 7. Update users CHECK constraint to include 'contributor' role
    # Drop old constraint and add new one with contributor
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_user_role")
    op.create_check_constraint(
        "ck_user_role",
        "users",
        "role IN ('admin', 'analyst', 'viewer', 'contributor')",
    )


def downgrade() -> None:
    """Drop meeting records tables in reverse order."""
    # 1. Revert users CHECK constraint
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_user_role")
    op.create_check_constraint(
        "ck_user_role",
        "users",
        "role IN ('admin', 'analyst', 'viewer')",
    )

    # 2. Drop tables in reverse dependency order
    op.drop_table("meeting_video_embeds")
    op.drop_table("meeting_attachments")

    # Drop partial unique index explicitly before dropping table
    op.execute("DROP INDEX IF EXISTS uq_agenda_item_meeting_order")
    op.drop_table("agenda_items")

    op.drop_table("meetings")

    op.execute("DROP INDEX IF EXISTS uq_governing_body_name_jurisdiction")
    op.drop_table("governing_bodies")

    op.drop_table("governing_body_types")
