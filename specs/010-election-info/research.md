# Research: 010-election-info

## Phase 0 Research Findings

### 1. Candidate Entity Design

**Decision**: Model candidates as a standalone table with FK to `elections.id` (CASCADE delete).

**Rationale**:
- Each `Election` row already represents a single race/contest (via `ballot_item_id`), so candidates associate directly to elections without a separate contest/race entity.
- Follows the `ElectedOfficial` pattern: `Base, UUIDMixin, TimestampMixin`, with a `CheckConstraint` for status values.
- `lazy="selectin"` on the `links` relationship avoids N+1 queries when loading candidate detail.

**Alternatives considered**:
- **Separate Contest/Race table between Election and Candidate**: Rejected — adds an unnecessary join for no functional benefit given the 1:1 election-to-race model.
- **Store candidates in JSONB on Election**: Rejected — loses queryability, indexing, and relational integrity. The SOS results already demonstrate the limitations of JSONB-only candidate storage.

### 2. Candidate Link Storage

**Decision**: Separate `candidate_links` table with FK to `candidates.id` (CASCADE delete), typed entries with `link_type` enum.

**Rationale**:
- Multiple links per candidate, each with a type (website, campaign, facebook, twitter, instagram, youtube, linkedin, other).
- A normalized table enables querying by link type and avoids JSONB complexity.
- Follows the `ElectedOfficialSource` one-to-many pattern but simpler (no `raw_data`, `is_current`, etc.).

**Alternatives considered**:
- **JSONB array of links on Candidate**: Rejected — harder to validate individual entries, no referential integrity, and the `ElectedOfficialSource` pattern demonstrates the project prefers normalized tables for child records.
- **Single `website` field + social JSONB**: Rejected — inconsistent with the spec requirement (FR-015) for a structured typed collection.

### 3. Election Metadata Enrichment

**Decision**: Add nullable columns directly to the existing `elections` table via a single Alembic migration.

**Rationale**:
- New fields are all optional (nullable), so existing records remain valid without data backfill.
- Adding columns to the existing table is simpler than creating a separate `election_metadata` table with a 1:1 FK.
- The existing `ElectionUpdateRequest` schema is extended with the new fields — no new endpoint needed.

**Alternatives considered**:
- **Separate `election_metadata` table**: Rejected — adds a join for every election detail query, and the fields are tightly coupled to the election entity. A 1:1 table is only justified when the child record has a different lifecycle, which is not the case here.

### 4. Candidate Uniqueness Constraint

**Decision**: `UNIQUE(election_id, full_name)` — prevents accidental duplicate entries for the same person in the same election.

**Rationale**:
- In the real world, two candidates with the exact same full name in the same race is extremely rare. If it occurs, an admin can distinguish them by appending a suffix (e.g., "John Smith Jr.").
- Matches the `ElectedOfficial` pattern: `UNIQUE(boundary_type, district_identifier, full_name)`.

**Alternatives considered**:
- **No uniqueness constraint**: Rejected — too easy to create accidental duplicates during data entry.
- **`UNIQUE(election_id, ballot_order)`**: Rejected — ballot order may not be known at initial entry and is nullable.

### 5. Filing Status Lifecycle

**Decision**: Four-state enum: `qualified`, `withdrawn`, `disqualified`, `write_in`. Default: `qualified`.

**Rationale**:
- Covers the real-world lifecycle observed in Macon-Bibb data: candidates qualify during the filing period, may withdraw or be disqualified, and write-in candidates are a distinct category.
- `qualified` is the default because candidates are typically entered after they have qualified.
- No `pending` or `filed` state — the spec assumes candidates are only entered once confirmed as qualified.

### 6. Migration Numbering

**Decision**: Two migrations: `037_add_candidates.py` (creates `candidates` + `candidate_links` tables) and `038_add_election_metadata.py` (adds columns to `elections` table).

**Rationale**:
- Separating into two migrations keeps each migration focused and independently reversible.
- The current highest migration is `036_add_server_default_uuid_to_all_tables.py`.

### 7. API Routing: Nested vs. Top-Level

**Decision**: Candidates are accessed via `/api/v1/elections/{election_id}/candidates` (nested under elections) for listing and creation, with `/api/v1/candidates/{candidate_id}` for detail/update/delete.

**Rationale**:
- Listing candidates always requires an election context — nesting under elections makes this explicit and avoids requiring `?election_id=` on every list request.
- Detail/update/delete operations reference a specific candidate by its UUID, so a top-level path is cleaner and avoids redundant election_id in the URL.
- This hybrid pattern (nested for collection, flat for item) is a common REST convention.

**Alternatives considered**:
- **Fully nested** (`/elections/{eid}/candidates/{cid}` for all ops): Rejected — redundant election_id in the URL for item operations, and FastAPI route ordering becomes more complex.
- **Fully flat** (`/candidates?election_id=...` for list): Rejected — listing without election context is not a supported use case.

### 8. Existing Election Update Pattern

**Decision**: Extend the existing `ElectionUpdateRequest` schema and `PATCH /elections/{id}` route to accept the new metadata fields.

**Rationale**:
- The election update service already uses `model_dump(exclude_unset=True)` + `setattr()` loop — new fields are automatically handled by adding them to the request schema.
- No new endpoint needed — the enrichment is a natural extension of the existing PATCH semantics.
- Backward compatible: clients that don't send the new fields see no change in behavior.
