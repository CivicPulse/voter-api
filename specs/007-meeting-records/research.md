# Research: Meeting Records API

**Branch**: `007-meeting-records` | **Date**: 2026-02-19

## R1: Soft Delete Strategy

**Decision**: Create a reusable `SoftDeleteMixin` in `models/base.py` with a `deleted_at: datetime | None` column. Records with `deleted_at IS NOT NULL` are excluded from normal queries. No separate `is_deleted` boolean — the presence of a timestamp is the delete marker and doubles as audit metadata.

**Rationale**: The existing `Voter` model has a `soft_deleted_at` column but it's not a reusable mixin. Creating a shared mixin avoids duplicating the pattern across 6 new tables. A timestamp is more informative than a boolean — it records *when* deletion occurred.

**Alternatives considered**:
- Boolean `is_deleted` flag — simpler but loses temporal information.
- Status enum including "deleted" — mixes deletion with business state transitions.
- PostgreSQL row-level security — too complex for this use case and would require superuser setup.

## R2: Full-Text Search Approach

**Decision**: Use PostgreSQL native full-text search with a generated `tsvector` column on `agenda_items` and a GIN index. Search across attachment filenames uses a joined subquery with `ILIKE`. Results are unified in a single service-layer query using `LEFT JOIN` and `COALESCE` on `ts_rank`.

**Rationale**: The existing codebase uses `ILIKE` for simple name searches, which doesn't scale to relevance-ranked full-text search across 100K+ meetings. PostgreSQL `tsvector`/`tsquery` provides built-in relevance ranking (`ts_rank`), stemming, and stop-word handling with minimal overhead via GIN indexes. No external search engine (Elasticsearch, Meilisearch) needed — keeps the stack simple per constitution.

**Alternatives considered**:
- `ILIKE` everywhere — no relevance ranking, O(n) scan on large datasets.
- Elasticsearch/Meilisearch — adds operational complexity and a new service dependency; premature for this scale.
- Materialized view combining agenda items + attachment filenames — adds maintenance complexity (refresh scheduling); deferred to future optimization if needed.

## R3: File Storage Strategy

**Decision**: Local filesystem storage with a configurable upload directory (`MEETING_UPLOAD_DIR` env var). Files are stored with UUID-based filenames to avoid collisions, organized by `{year}/{month}/{uuid}.{ext}`. The storage layer is abstracted behind a `FileStorage` Protocol in `lib/meetings/storage.py` so it can be swapped to S3/R2 later.

**Rationale**: The existing codebase uses R2 (S3-compatible) for published datasets (`lib/publisher/storage.py`), but meeting attachments are different — they're user-uploaded documents, not generated artifacts. Local filesystem is simplest for initial deployment on piku, and the protocol abstraction means S3 migration requires only a new implementation class, not a rewrite.

**Alternatives considered**:
- R2/S3 from day one — adds boto3 dependency and credential management complexity; premature for initial deployment.
- Database BLOB storage — PostgreSQL can store files but it bloats the database and complicates backups.

## R4: Polymorphic Attachment/Video Embed Association

**Decision**: Use nullable FK columns (`meeting_id` and `agenda_item_id`) with a `CHECK` constraint enforcing exactly one is `NOT NULL`. This is the "exclusive belongs-to" pattern.

**Rationale**: SQLAlchemy supports this well with two nullable FKs and a check constraint. It avoids the complexity of generic FK patterns (content type + object ID) while keeping referential integrity enforced at the database level. The existing codebase doesn't use polymorphic patterns, so the simplest approach is best.

**Alternatives considered**:
- Generic FK (content_type + object_id strings) — loses database referential integrity, requires application-level joins.
- Separate tables per parent (meeting_attachments, agenda_item_attachments) — duplicates schema and logic; harder to search across all attachments.

## R5: Governing Body Type Extensibility

**Decision**: A dedicated `governing_body_types` lookup table with `id`, `name`, `slug`, `description`, and `is_default` flag. Default types are seeded via Alembic migration data insert. Admins add new types via a simple CRUD endpoint.

**Rationale**: A lookup table is more flexible than a Python `StrEnum` for admin-extensible values. The `is_default` flag distinguishes system-provided types (cannot be deleted) from admin-added types. The `slug` column provides a URL-safe, stable identifier for filtering.

**Alternatives considered**:
- Python StrEnum with database CHECK constraint — requires code deployment to add new types; rejected per spec clarification.
- JSONB column on governing bodies — loses referential integrity and makes filtering/reporting harder.

## R6: Approval Workflow Fields

**Decision**: Add `approval_status` (enum: pending, approved, rejected), `submitted_by` (FK to users), `approved_by` (FK to users, nullable), `approved_at` (timestamp, nullable), and `rejection_reason` (text, nullable) columns to the `meetings` table. Admin-created meetings default to `approved`; contributor-created meetings default to `pending`.

**Rationale**: Approval is meeting-level (per clarification), so all workflow fields live on the `meetings` table. Child records (agenda items, attachments, video embeds) inherit the meeting's approval status implicitly — no separate approval columns needed on child tables.

**Alternatives considered**:
- Separate `meeting_approvals` table — over-normalized for a simple 3-state workflow.
- Approval status on every table — rejected per clarification (meeting-level batch approval).

## R7: Contributor Role Addition

**Decision**: Add `"contributor"` to the role validation in the User model and auth system. The existing `require_role(*roles)` dependency factory already supports multiple roles, so endpoint-level auth is simply `Depends(require_role("admin", "contributor"))` for write endpoints.

**Rationale**: The existing role system is string-based with admin/analyst/viewer. Adding contributor follows the same pattern. No schema migration needed for the `users` table since `role` is a VARCHAR column — only the CHECK constraint needs updating.

**Alternatives considered**:
- Separate `permissions` table with many-to-many — over-engineered for 4 roles.
- Bitfield/bitmask roles — less readable, harder to query.

## R8: Agenda Item Ordering Strategy

**Decision**: Integer `display_order` column with a gap-based strategy. New items are assigned `display_order = (max_order + 1) * 10` (gaps of 10). Reorder operations update a batch of items in a single transaction. The service layer handles order normalization.

**Rationale**: Gap-based ordering reduces the number of rows that need updating on insert (most inserts at the end are free). When reordering, a single UPDATE with CASE/WHEN sets all positions atomically. This avoids the complexity of linked-list ordering while being efficient for the typical meeting agenda size (5-30 items).

**Alternatives considered**:
- Linked list (next_id FK) — complex reorder logic, expensive to render ordered lists.
- Fractional ordering (float) — precision issues over many reorderings.
- Dense integer with full renumber on every insert — unnecessary writes for append-heavy usage.
