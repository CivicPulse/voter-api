# Research: Voter History Ingestion

**Feature Branch**: `006-voter-history`
**Date**: 2026-02-17

## 1. Election Model Extension for Auto-Creation

**Decision**: Add a `creation_method` column to the `elections` table to distinguish auto-created elections from manually created or feed-imported ones.

**Rationale**: FR-006 requires auto-created elections to be "distinguishable from manually created or feed-imported elections." The existing `Election` model has no field to indicate how an election was created. A dedicated `creation_method` column (String(20), NOT NULL, default `"manual"`) is explicit, queryable, and filterable. Existing records are backfilled with `"manual"`.

**Alternatives considered**:

- **Sentinel `data_source_url` value** (e.g., `"voter-history://auto-created"`): Fragile, requires string matching, violates intent of the `data_source_url` column which expects a real URL.
- **Separate boolean `auto_created` flag**: Too narrow — doesn't distinguish between feed-imported and manually created. A string column is more extensible.
- **JSONB metadata column**: Over-engineered for a single-purpose field.

**Values**: `"manual"` (default for existing/admin-created), `"feed_import"` (for SoS feed ingestion), `"voter_history"` (for auto-created from voter history import).

## 2. Election NOT NULL Column Handling for Auto-Created Records

**Decision**: Use placeholder values for `data_source_url` and `district` on auto-created elections, since both columns are NOT NULL.

**Rationale**: Making these columns nullable would require auditing all existing queries and could introduce subtle bugs. Placeholder values are self-documenting and follow the principle of least surprise.

**Values**:

- `data_source_url`: `"n/a"` — clear sentinel indicating no feed URL exists.
- `district`: `"Statewide"` — Georgia voter history is statewide data; this is semantically accurate.
- `name`: Auto-generated as `"{Election Type} - {MM/DD/YYYY}"` (e.g., `"General Election - 11/03/2024"`).
- `status`: `"finalized"` — auto-created elections are historical, not actively tracked.

**Alternatives considered**:

- **Make columns nullable**: Migration risk, requires updating all SELECT queries and Pydantic schemas that assume non-null.
- **Create a separate `voter_history_elections` table**: Violates the principle that election events should be centralized. Creates two sources of truth for the same concept.

## 3. Voter History Table Design: Foreign Key Strategy

**Decision**: Store `import_job_id` as a FK to `import_jobs.id`. Do NOT store `election_id` as a FK. Join to elections at query time via `(election_date, election_type)`.

**Rationale**: The spec explicitly calls for lazy reconciliation and says the unique constraint is `(voter_registration_number, election_date, election_type)`. Storing `election_id` would create a dependency on election records existing before import, but the auto-creation happens during import. Since elections are auto-created during the same import, storing the reference is possible but adds complexity to the import loop (must flush elections before inserting history records). The `(election_date, election_type)` join is simple, matches the natural key, and the elections table is small enough that this join is performant.

However, `import_job_id` IS stored as a FK because it's essential for the re-import replacement logic (FR-004/FR-021): when re-importing, we delete all `voter_history` records matching the previous `import_job_id`.

**Alternatives considered**:

- **Store `election_id` FK**: Creates ordering dependency during import (must create elections first, then flush, then insert history records). Adds complexity for marginal query-time benefit on a small join table.
- **No `import_job_id` FK**: Makes re-import replacement impossible without scanning file names.

## 4. Re-Import Replacement Strategy

**Decision**: Atomic replacement via import job lineage. When re-importing a file:

1. Create a new `ImportJob` record with the same `file_name` and `file_type="voter_history"`.
2. Import all records from the new file, associating them with the new job.
3. On successful completion, delete all `voter_history` records associated with the previous import job(s) for the same `file_name`.
4. Mark previous job(s) as `"superseded"`.

**Rationale**: FR-021 requires atomic re-import — previous records are only removed after the new import succeeds. This approach uses the `import_job_id` FK to identify which records belong to which import, making replacement clean and targeted. Previous auto-created elections are NOT deleted (FR-021 explicitly states this).

**Alternatives considered**:

- **Delete-then-insert**: Not atomic — if import fails midway, data is lost.
- **Upsert by natural key**: The unique constraint `(voter_registration_number, election_date, election_type)` means records with the same key would be updated. But this doesn't handle the case where a record was in the previous file but not in the new one (it should be removed).
- **Soft-delete with `present_in_latest_import` flag**: Pattern used for voters, but voter history is append-only across files (a file can grow but records within it don't change), so hard delete of the previous import's records is appropriate.

## 5. Import Counter Extensions to ImportJob

**Decision**: Add `records_skipped` and `records_unmatched` columns to `import_jobs` table.

**Rationale**: FR-012 requires the import summary to include "skipped duplicates" and "unmatched registration numbers." The existing `ImportJob` model has specific columns for each counter type (`records_succeeded`, `records_failed`, `records_inserted`, etc.). Following this pattern, two new nullable Integer columns are cleaner than encoding these in the `error_log` JSONB field, which is reserved for detailed error entries.

- `records_skipped`: Count of records within the same file that duplicate an earlier row (same voter_registration_number + election_date + election_type). Only the first occurrence is stored.
- `records_unmatched`: Count of records whose `voter_registration_number` does not exist in the `voters` table at import time.

**Alternatives considered**:

- **Store in `error_log` JSONB**: Requires parsing JSON to get counts. Inconsistent with existing counter pattern.
- **Derive from data at query time**: Expensive for large imports. Counters should be snapshot at import time.

## 6. GA SoS Voter History CSV Format

**Decision**: Parse the 9-column GA SoS format with the following column mapping:

| CSV Column                   | Internal Field               | Type          | Notes                                    |
| ---------------------------- | ---------------------------- | ------------- | ---------------------------------------- |
| County Name                  | county                       | String(100)   | Stored as-is, no validation against list |
| Voter Registration Number    | voter_registration_number    | String(20)    | Natural key, joins to `voters` table     |
| Election Date                | election_date                | Date          | Parsed from MM/DD/YYYY format            |
| Election Type                | election_type                | String(50)    | e.g., "GENERAL ELECTION", "GENERAL PRIMARY" |
| Party                        | party                        | String(50)    | Null for non-primaries                   |
| Ballot Style                 | ballot_style                 | String(100)   | Open vocabulary, stored as-is            |
| Absentee                     | absentee                     | Boolean       | "Y" → True, anything else → False        |
| Provisional                  | provisional                  | Boolean       | "Y" → True, blank/anything else → False  |
| Supplemental                 | supplemental                 | Boolean       | "Y" → True, blank/anything else → False  |

**Rationale**: Direct mapping from the spec's FR-001 and the assumptions section. Boolean parsing follows FR-018 (blank = "N") and edge case rules. Election type values are stored as-is from the CSV (uppercase, e.g., "GENERAL ELECTION") rather than normalized to the `ElectionType` literal used by the election tracker (`"general"`, `"special"`, etc.). This preserves source fidelity and avoids lossy mapping of types like "GENERAL PRIMARY" which combine type and party context.

**Date parsing**: `datetime.strptime(value, "%m/%d/%Y").date()` with error handling per FR-019 — unparseable dates are logged and the record is rejected.

## 7. Election Type Mapping for Auto-Creation

**Decision**: Map GA SoS voter history election types to the existing `ElectionType` vocabulary when auto-creating election records.

| Voter History Value      | Mapped election_type | Notes                                    |
| ------------------------ | -------------------- | ---------------------------------------- |
| GENERAL ELECTION         | general              | Direct mapping                           |
| GENERAL PRIMARY          | primary              | Primary-type election                    |
| SPECIAL ELECTION         | special              | Direct mapping                           |
| SPECIAL ELECTION RUNOFF  | runoff               | Runoff variant                           |
| SPECIAL PRIMARY          | primary              | Primary-type election                    |
| SPECIAL PRIMARY RUNOFF   | runoff               | Runoff variant                           |
| PRESIDENTIAL PREFERENCE PRIMARY | primary       | Primary-type election                    |
| (other)                  | general              | Safe default for unknown types           |

**Rationale**: The `Election.election_type` column uses the existing `ElectionType` literal values (`"general"`, `"primary"`, `"special"`, `"runoff"`). When auto-creating an election, we need to normalize the verbose voter history type to this vocabulary. The VoterHistory record itself stores the original verbose value for fidelity.

**Alternatives considered**:

- **Store verbose type on Election too**: Would break existing election type conventions and filtering.
- **Expand ElectionType vocabulary**: Would require changes across the entire election subsystem for minimal benefit.

## 8. Voter Detail Enrichment Approach

**Decision**: Add a `participation_summary` field to `VoterDetailResponse` containing `total_elections: int` and `last_election_date: date | None`. Compute at query time via a subquery count on `voter_history`.

**Rationale**: FR-020 requires enriching the existing voter detail with participation data. A lightweight summary (count + last date) avoids loading full history records. The subquery is efficient with an index on `voter_history.voter_registration_number`.

**Schema addition**:

```python
class ParticipationSummary(BaseModel):
    total_elections: int = 0
    last_election_date: date | None = None

class VoterDetailResponse(BaseModel):
    # ... existing fields ...
    participation_summary: ParticipationSummary = Field(default_factory=ParticipationSummary)
```

**Alternatives considered**:

- **Denormalize counts onto Voter model**: Would require updating voter records on every history import. Violates separation of concerns.
- **Separate API call**: Spec explicitly says to enrich the existing endpoint, not create a new one.

## 9. Background Import Execution

**Decision**: Follow the existing background task pattern using `InProcessTaskRunner.submit_task()` for API-triggered imports. CLI imports run synchronously (blocking the CLI).

**Rationale**: Consistent with existing import and geocoding patterns. The API returns 202 Accepted with the import job ID. Users poll `GET /api/v1/imports/{job_id}` for status. CLI imports block and print progress directly, matching the existing `import voters` command pattern.

## 10. Pagination and Filtering Patterns

**Decision**: Follow existing pagination pattern (`page`/`page_size` query params, `PaginatedXxxResponse` wrapper) for all list endpoints. Filtering via query parameters.

**Filters for voter history query** (`GET /api/v1/voters/{reg_num}/history`):

- `election_type: str | None` — filter by election type
- `date_from: date | None` — filter by election date range start
- `date_to: date | None` — filter by election date range end
- `county: str | None` — filter by county name
- `ballot_style: str | None` — filter by ballot style

**Filters for election participation** (`GET /api/v1/elections/{id}/participation`):

- `county: str | None` — filter by county
- `ballot_style: str | None` — filter by ballot style
- `absentee: bool | None` — filter by absentee flag
- `provisional: bool | None` — filter by provisional flag
- `supplemental: bool | None` — filter by supplemental flag
