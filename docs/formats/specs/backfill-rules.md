# Backfill Rules

This document defines the rules for matching existing database records to markdown files and writing the database UUID back into the markdown. The backfill process bridges the gap between the existing database (populated via the legacy import path) and the new markdown-first pipeline.

**Specced in Phase 1. Implemented as a CLI command in Phase 2.**

## Purpose

After migration (see [migration-rules.md](./migration-rules.md)), all election markdown files have empty `| ID | |` rows. The backfill command:

1. Reads each markdown file
2. Extracts natural key fields from the markdown content
3. Queries the database for a matching record using the natural key
4. If a match is found: writes the DB record's UUID into the markdown `| ID | {uuid} |` row
5. If no match is found: generates a new UUID v4 and writes it into the markdown

After backfill, every file has a populated UUID, and existing DB records are correlated with their markdown source files.

## Natural Key Definitions

Each entity type has a natural key -- the combination of fields that uniquely identifies a record in the database. These match existing database unique constraints.

### ElectionEvent Matching

**Natural key:** `(event_date, event_type)`

**DB constraint:** `uq_election_event_date_type` on the `election_events` table

**Extraction from markdown:**
- `event_date`: The `Date` value from the overview metadata table, parsed as a date (e.g., `May 19, 2026` -> `2026-05-19`)
- `event_type`: The `Type` value from the overview metadata table, mapped to the ElectionType enum (e.g., `General Primary` -> `general_primary`)

**Matching query:**
```sql
SELECT id FROM election_events
WHERE event_date = :event_date AND event_type = :event_type
```

**Edge cases:**
- If multiple matches are found (should not happen given the unique constraint): emit error requiring manual resolution
- If `event_type` in markdown does not map to a valid ElectionType enum value: emit error with the file path and the unrecognized value

### Election Matching

**Natural key:** `(name, election_date)`

**DB constraint:** `uq_election_name_date` on the `elections` table

**Extraction from markdown:**
- `name`: The H1 heading from the contest file (single-contest) or the `### Contest Name` heading (multi-contest county file)
- `election_date`: The election date from the parent overview file or the Election metadata link

**Matching query:**
```sql
SELECT id FROM elections
WHERE name = :name AND election_date = :election_date
```

**Edge cases:**
- Contest names must match exactly (case-sensitive). If the markdown contest name differs from the DB `name` value by case or whitespace, the match will fail silently and a new UUID will be generated. This is acceptable; the Phase 2 migration normalizes names.
- For multi-contest county files, the backfill iterates each `### Contest Name` section and matches individually. Each contest gets its own Election UUID, but these are tracked in an auxiliary mapping file (not embedded in the multi-contest markdown).

### Candidate Matching

**Natural key:** `(full_name, election_id)`

**DB constraint:** `uq_candidate_election_name` on the `candidates` table

**Extraction from markdown:**
- `full_name`: The candidate's full name from the candidate file's H1 heading or Person section
- `election_id`: Since candidate files are person-level (not election-level), the backfill must:
  1. Iterate each election-keyed section in the candidate file
  2. Find the election UUID from the section's election cross-link (which must already be backfilled)
  3. Match by `(full_name, election_id)` in the database

**Matching query:**
```sql
SELECT id FROM candidates
WHERE full_name = :full_name AND election_id = :election_id
```

**Edge cases:**
- If the referenced election has not yet been backfilled (no UUID), emit error: `BACKFILL_ORDER: {candidate_file} references election {election_link} which has no UUID. Run backfill on election files first.`
- If `full_name` matching fails due to name normalization differences (e.g., middle initial vs. middle name), the match will not be found and a new UUID is generated. The DB will have a duplicate after import; deduplication is a manual process.

## Backfill Process Order

Due to foreign key dependencies, backfill must proceed in this order:

1. **ElectionEvent files** (overview files) -- no dependencies
2. **Election files** (contest files) -- depend on ElectionEvent UUIDs for election_event_id
3. **Candidate files** -- depend on Election UUIDs for natural key matching

If a file at step N references a file from step N-1 that has no UUID, backfill emits an error and skips that file. Running backfill again after fixing the dependency resolves the skip.

## Conflict Resolution

### ID already exists and matches

If the markdown `| ID | {uuid} |` row already has a value and it matches the DB record's UUID:
- **Action:** Skip (no-op)
- **Log:** `SKIP: {file_path} - UUID already matches DB record`

### ID already exists but differs

If the markdown `| ID | {uuid} |` row already has a value and it does NOT match the DB record's UUID:
- **Action:** Emit error, do NOT overwrite
- **Log:** `CONFLICT: {file_path} - Markdown UUID {md_uuid} != DB UUID {db_uuid}. Manual resolution required.`

**Rationale:** Overwriting could corrupt cross-references in other files that already use the markdown UUID.

### No DB match found

If no matching DB record exists:
- **Action:** Generate a new UUID v4 and write it into the markdown
- **Log:** `NEW: {file_path} - No DB match for natural key ({key_values}). Generated UUID: {new_uuid}`

## CLI Command Specification

```bash
# Backfill all markdown files in an election directory
voter-api backfill data/elections/2026-05-19/

# Backfill with dry-run (show what would change without writing)
voter-api backfill data/elections/2026-05-19/ --dry-run

# Backfill only candidate files
voter-api backfill data/candidates/ --type candidates
```

### Output Format

```
Backfill Report: data/elections/2026-05-19/
  Matched:   42 files (UUID written from DB)
  New:        5 files (UUID generated)
  Skipped:   12 files (UUID already correct)
  Conflicts:  0 files
  Errors:     1 file
    BACKFILL_ORDER: data/candidates/jane-smith.md references election with no UUID

Total: 60 files processed
```

## Idempotency

Running backfill twice on the same directory produces the same result:
- Files with matching UUIDs are skipped
- Files with generated UUIDs already have values on the second run and are skipped
- No data is lost or changed on repeated runs
