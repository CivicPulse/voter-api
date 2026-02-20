# Data Model: Meeting Records API

**Branch**: `007-meeting-records` | **Date**: 2026-02-19

## Overview

Six new tables support the meeting records feature: a lookup table for governing body types, the core entity tables (governing bodies, meetings, agenda items), and two polymorphic child tables (attachments, video embeds). All tables use UUID primary keys, timestamps, and soft delete via a shared `SoftDeleteMixin`.

## Entities

### 1. GoverningBodyType (lookup table)

Admin-extensible enumeration of governing body classifications.

| Column       | Type         | Constraints                        | Description                              |
|--------------|--------------|------------------------------------|------------------------------------------|
| id           | UUID         | PK, default gen_random_uuid()      | Unique identifier                        |
| name         | VARCHAR(100) | NOT NULL, UNIQUE                   | Display name (e.g., "County Commission") |
| slug         | VARCHAR(100) | NOT NULL, UNIQUE                   | URL-safe identifier (e.g., "county-commission") |
| description  | TEXT         | nullable                           | Optional description of the type         |
| is_default   | BOOLEAN      | NOT NULL, default true             | System-provided (true) vs admin-added (false); defaults cannot be deleted |
| created_at   | TIMESTAMPTZ  | NOT NULL, default now()            | Record creation timestamp                |

**Constraints**:
- `uq_governing_body_type_name` — UNIQUE on `name`
- `uq_governing_body_type_slug` — UNIQUE on `slug`

**Seeded default types**: county commission, city council, school board, planning commission, water authority, housing authority, transit authority.

### 2. GoverningBody

A local government entity that holds meetings.

| Column       | Type         | Constraints                        | Description                              |
|--------------|--------------|------------------------------------|------------------------------------------|
| id           | UUID         | PK, default gen_random_uuid()      | Unique identifier                        |
| name         | VARCHAR(200) | NOT NULL                           | Official name of the governing body      |
| type_id      | UUID         | FK → governing_body_types.id, NOT NULL | Classification type                  |
| jurisdiction | VARCHAR(200) | NOT NULL                           | Geographic jurisdiction (free text)      |
| description  | TEXT         | nullable                           | Optional description                     |
| website_url  | VARCHAR(500) | nullable                           | Official website URL                     |
| deleted_at   | TIMESTAMPTZ  | nullable                           | Soft delete timestamp (null = active)    |
| created_at   | TIMESTAMPTZ  | NOT NULL, default now()            | Record creation timestamp                |
| updated_at   | TIMESTAMPTZ  | NOT NULL, default now()            | Last update timestamp                    |

**Constraints**:
- `uq_governing_body_name_jurisdiction` — UNIQUE on `(name, jurisdiction)` WHERE `deleted_at IS NULL`
- `fk_governing_body_type` — FK to `governing_body_types.id`

**Indexes**:
- `ix_governing_bodies_type_id` — B-tree on `type_id`
- `ix_governing_bodies_jurisdiction` — B-tree on `jurisdiction`
- `ix_governing_bodies_deleted_at` — B-tree on `deleted_at` (for filtering active records)

### 3. Meeting

A specific session of a governing body.

| Column             | Type         | Constraints                         | Description                                |
|--------------------|--------------|-------------------------------------|--------------------------------------------|
| id                 | UUID         | PK, default gen_random_uuid()       | Unique identifier                          |
| governing_body_id  | UUID         | FK → governing_bodies.id, NOT NULL  | Parent governing body                      |
| meeting_date       | TIMESTAMPTZ  | NOT NULL                            | Date and time of the meeting (with TZ)     |
| location           | VARCHAR(500) | nullable                            | Physical or virtual meeting location       |
| meeting_type       | VARCHAR(20)  | NOT NULL                            | Type: regular, special, work_session, emergency, public_hearing |
| status             | VARCHAR(20)  | NOT NULL                            | Status: scheduled, completed, cancelled, postponed |
| external_source_url| VARCHAR(1000)| nullable                            | Link to official government meeting page   |
| approval_status    | VARCHAR(20)  | NOT NULL, default 'approved'        | Workflow: pending, approved, rejected       |
| submitted_by       | UUID         | FK → users.id, nullable             | User who created the record                |
| approved_by        | UUID         | FK → users.id, nullable             | Admin who approved/rejected                |
| approved_at        | TIMESTAMPTZ  | nullable                            | When approval/rejection occurred           |
| rejection_reason   | TEXT         | nullable                            | Reason for rejection (required on reject)  |
| deleted_at         | TIMESTAMPTZ  | nullable                            | Soft delete timestamp                      |
| created_at         | TIMESTAMPTZ  | NOT NULL, default now()             | Record creation timestamp                  |
| updated_at         | TIMESTAMPTZ  | NOT NULL, default now()             | Last update timestamp                      |

**Constraints**:
- `fk_meeting_governing_body` — FK to `governing_bodies.id`
- `fk_meeting_submitted_by` — FK to `users.id`
- `fk_meeting_approved_by` — FK to `users.id`
- `ck_meeting_type` — CHECK `meeting_type IN ('regular', 'special', 'work_session', 'emergency', 'public_hearing')`
- `ck_meeting_status` — CHECK `status IN ('scheduled', 'completed', 'cancelled', 'postponed')`
- `ck_meeting_approval_status` — CHECK `approval_status IN ('pending', 'approved', 'rejected')`

**Indexes**:
- `ix_meetings_governing_body_id` — B-tree on `governing_body_id`
- `ix_meetings_date` — B-tree on `meeting_date`
- `ix_meetings_type_status` — Composite B-tree on `(meeting_type, status)`
- `ix_meetings_approval_status` — B-tree on `approval_status`
- `ix_meetings_submitted_by` — B-tree on `submitted_by`
- `ix_meetings_deleted_at` — B-tree on `deleted_at`

### 4. AgendaItem

An ordered item on a meeting's agenda.

| Column        | Type         | Constraints                       | Description                                |
|---------------|--------------|-----------------------------------|--------------------------------------------|
| id            | UUID         | PK, default gen_random_uuid()     | Unique identifier                          |
| meeting_id    | UUID         | FK → meetings.id, NOT NULL        | Parent meeting                             |
| title         | VARCHAR(500) | NOT NULL                          | Agenda item title                          |
| description   | TEXT         | nullable                          | Detailed description of the item           |
| action_taken  | TEXT         | nullable                          | Free-text record of action taken           |
| disposition   | VARCHAR(20)  | nullable                          | Outcome: approved, denied, tabled, no_action, informational |
| display_order | INTEGER      | NOT NULL                          | Position within the meeting agenda         |
| search_vector | TSVECTOR     | GENERATED ALWAYS AS (…) STORED    | Full-text search index combining title + description |
| deleted_at    | TIMESTAMPTZ  | nullable                          | Soft delete timestamp                      |
| created_at    | TIMESTAMPTZ  | NOT NULL, default now()           | Record creation timestamp                  |
| updated_at    | TIMESTAMPTZ  | NOT NULL, default now()           | Last update timestamp                      |

**Constraints**:
- `fk_agenda_item_meeting` — FK to `meetings.id`
- `ck_agenda_item_disposition` — CHECK `disposition IN ('approved', 'denied', 'tabled', 'no_action', 'informational')` (nullable allowed)
- `uq_agenda_item_meeting_order` — UNIQUE on `(meeting_id, display_order)` WHERE `deleted_at IS NULL`

**Indexes**:
- `ix_agenda_items_meeting_id` — B-tree on `meeting_id`
- `ix_agenda_items_search_vector` — GIN on `search_vector`

**Generated column definition**:
```sql
search_vector TSVECTOR GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(description, '')), 'B')
) STORED
```

### 5. MeetingAttachment

A file associated with a meeting or agenda item (exclusive belongs-to).

| Column            | Type         | Constraints                       | Description                                |
|-------------------|--------------|-----------------------------------|--------------------------------------------|
| id                | UUID         | PK, default gen_random_uuid()     | Unique identifier                          |
| meeting_id        | UUID         | FK → meetings.id, nullable        | Parent meeting (if meeting-level)          |
| agenda_item_id    | UUID         | FK → agenda_items.id, nullable    | Parent agenda item (if item-level)         |
| original_filename | VARCHAR(500) | NOT NULL                          | Original uploaded filename                 |
| stored_path       | VARCHAR(1000)| NOT NULL                          | Path/key in storage backend                |
| file_size         | BIGINT       | NOT NULL                          | File size in bytes                         |
| content_type      | VARCHAR(100) | NOT NULL                          | MIME type (e.g., application/pdf)          |
| deleted_at        | TIMESTAMPTZ  | nullable                          | Soft delete timestamp                      |
| created_at        | TIMESTAMPTZ  | NOT NULL, default now()           | Upload timestamp                           |

**Constraints**:
- `fk_attachment_meeting` — FK to `meetings.id`
- `fk_attachment_agenda_item` — FK to `agenda_items.id`
- `ck_attachment_parent` — CHECK `(meeting_id IS NOT NULL AND agenda_item_id IS NULL) OR (meeting_id IS NULL AND agenda_item_id IS NOT NULL)` — exactly one parent

**Indexes**:
- `ix_meeting_attachments_meeting_id` — B-tree on `meeting_id`
- `ix_meeting_attachments_agenda_item_id` — B-tree on `agenda_item_id`
- `ix_meeting_attachments_filename` — B-tree on `original_filename` (for search)

### 6. MeetingVideoEmbed

A video recording link associated with a meeting or agenda item.

| Column         | Type         | Constraints                       | Description                                |
|----------------|--------------|-----------------------------------|--------------------------------------------|
| id             | UUID         | PK, default gen_random_uuid()     | Unique identifier                          |
| meeting_id     | UUID         | FK → meetings.id, nullable        | Parent meeting (if meeting-level)          |
| agenda_item_id | UUID         | FK → agenda_items.id, nullable    | Parent agenda item (if item-level)         |
| video_url      | VARCHAR(1000)| NOT NULL                          | Full URL to YouTube or Vimeo video         |
| platform       | VARCHAR(20)  | NOT NULL                          | Platform: youtube, vimeo                   |
| start_seconds  | INTEGER      | nullable                          | Start timestamp in seconds                 |
| end_seconds    | INTEGER      | nullable                          | End timestamp in seconds                   |
| deleted_at     | TIMESTAMPTZ  | nullable                          | Soft delete timestamp                      |
| created_at     | TIMESTAMPTZ  | NOT NULL, default now()           | Record creation timestamp                  |

**Constraints**:
- `fk_video_embed_meeting` — FK to `meetings.id`
- `fk_video_embed_agenda_item` — FK to `agenda_items.id`
- `ck_video_embed_parent` — CHECK `(meeting_id IS NOT NULL AND agenda_item_id IS NULL) OR (meeting_id IS NULL AND agenda_item_id IS NOT NULL)` — exactly one parent
- `ck_video_embed_platform` — CHECK `platform IN ('youtube', 'vimeo')`
- `ck_video_embed_timestamps` — CHECK `start_seconds IS NULL OR end_seconds IS NULL OR end_seconds > start_seconds`

**Indexes**:
- `ix_meeting_video_embeds_meeting_id` — B-tree on `meeting_id`
- `ix_meeting_video_embeds_agenda_item_id` — B-tree on `agenda_item_id`

## Relationships

```
governing_body_types 1──< governing_bodies 1──< meetings 1──< agenda_items
                                                    │                 │
                                                    │                 ├──< meeting_attachments
                                                    │                 └──< meeting_video_embeds
                                                    │
                                                    ├──< meeting_attachments
                                                    └──< meeting_video_embeds

users ──< meetings (submitted_by)
users ──< meetings (approved_by)
```

- `governing_body_types` → `governing_bodies`: one-to-many via `type_id`
- `governing_bodies` → `meetings`: one-to-many via `governing_body_id`
- `meetings` → `agenda_items`: one-to-many via `meeting_id`
- `meetings` → `meeting_attachments`: one-to-many via `meeting_id` (exclusive belongs-to)
- `meetings` → `meeting_video_embeds`: one-to-many via `meeting_id` (exclusive belongs-to)
- `agenda_items` → `meeting_attachments`: one-to-many via `agenda_item_id` (exclusive belongs-to)
- `agenda_items` → `meeting_video_embeds`: one-to-many via `agenda_item_id` (exclusive belongs-to)
- `users` → `meetings`: via `submitted_by` and `approved_by` FKs

## Design Decisions

### D1: SoftDeleteMixin

**Decision**: Introduce a `SoftDeleteMixin` in `models/base.py` with `deleted_at: Mapped[datetime | None]`.
**Rationale**: All 6 entity tables need soft delete. A mixin ensures consistency and enables shared query filters.
**Trade-offs**: Adds a mixin to `base.py` that existing models don't use; acceptable since it's opt-in.

### D2: Generated tsvector Column

**Decision**: Use a PostgreSQL generated column for `search_vector` on `agenda_items`.
**Rationale**: Automatically maintained by PostgreSQL — no application-level trigger or service code needed to keep the search index in sync. GIN index provides sub-second search across millions of rows.
**Trade-offs**: Generated columns require PostgreSQL 12+; we run 15+.

### D3: Exclusive Belongs-To Pattern

**Decision**: Attachments and video embeds use two nullable FKs with a CHECK constraint.
**Rationale**: Simpler than generic FK patterns; maintains database-level referential integrity.
**Trade-offs**: Two nullable FK columns per table vs. one FK + one type discriminator. The CHECK constraint prevents orphaned records.

### D4: Partial Unique Index for Soft Delete

**Decision**: Unique constraints use `WHERE deleted_at IS NULL` to allow "re-creation" after soft delete.
**Rationale**: Without the partial index, soft-deleted records would block creation of new records with the same natural key.

### D5: Gap-Based Ordering

**Decision**: `display_order` uses gaps of 10 for new items; reorder normalizes to sequential integers.
**Rationale**: Minimizes write amplification for the common case (appending items) while supporting arbitrary reordering.

## Migration Notes

**Migration**: `023_create_meeting_records_tables.py`
**Revision**: 023 | **Down revision**: 022

**Prerequisites**: PostgreSQL 15+ with PostGIS (already in place).

**Upgrade steps**:
1. Create `governing_body_types` table and seed default types
2. Create `governing_bodies` table with FK to types
3. Create `meetings` table with FKs to governing_bodies and users
4. Create `agenda_items` table with generated `search_vector` column and GIN index
5. Create `meeting_attachments` table with exclusive belongs-to CHECK constraint
6. Create `meeting_video_embeds` table with exclusive belongs-to CHECK constraint
7. Update `users` table CHECK constraint to include 'contributor' role

**Downgrade steps** (reverse order):
1. Revert `users` table CHECK constraint to exclude 'contributor' role
2. Drop `meeting_video_embeds` table
3. Drop `meeting_attachments` table
4. Drop `agenda_items` table
5. Drop `meetings` table
6. Drop `governing_bodies` table
7. Drop `governing_body_types` table

## References

- [spec.md](./spec.md) — Feature specification
- [contracts/openapi.yaml](./contracts/openapi.yaml) — API contracts
- [research.md](./research.md) — Research decisions
- `src/voter_api/models/base.py` — Base model and mixins
