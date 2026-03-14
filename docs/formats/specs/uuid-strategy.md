# UUID Strategy

This document defines how UUIDs are embedded, managed, and validated in the election data markdown files. It provides unambiguous rules for the Phase 2 converter, backfill command, and any future tooling that reads or writes UUIDs.

## Core Principle

**The markdown file is the source of truth for identity.** Every entity that will be imported into the database carries a UUID in its markdown metadata table. The converter reads this UUID and passes it through to JSONL output. The converter never generates UUIDs.

## UUID Embedding Format

UUIDs appear as `| ID | {uuid} |` rows in the markdown metadata table:

```markdown
## Metadata

| Field | Value |
|-------|-------|
| ID | 550e8400-e29b-41d4-a716-446655440000 |
| Format Version | 1 |
| ...   | ...   |
```

### Format Rules

- **UUID format:** Standard UUID v4 string, lowercase hex with hyphens (e.g., `550e8400-e29b-41d4-a716-446655440000`)
- **Field name:** Always `ID` (uppercase), never `id`, `UUID`, or `Identifier`
- **Position:** The `ID` row must be the first row in the metadata table (after the header row)
- **No backticks:** The UUID value is plain text, not wrapped in backticks or quotes

## Which File Types Have UUIDs

| File Type | Entity | Has UUID | Source of UUID |
|-----------|--------|----------|----------------|
| Election overview | ElectionEvent | Yes | Backfill from DB or manual assignment |
| Single-contest file | Election | Yes | Backfill from DB or manual assignment |
| Multi-contest (county) file | Election (one per contest section) | Yes (file-level ID for the county grouping) | Backfill from DB or manual assignment |
| Candidate file | Candidate | Yes | Backfill from DB or manual assignment |
| County reference file | -- | **No** | County references are reference data, not imported entities |

### Multi-Contest File Detail

In multi-contest (county) files, the file-level `| ID | {uuid} |` in the metadata table identifies the county's local elections grouping. Individual contests within the file are identified by their `### Contest Name` heading, which maps to an Election record. Contest-level UUIDs are not embedded in the multi-contest file itself; they are resolved during conversion via the contest name + election event pairing.

### Candidacy UUIDs

Candidacy records (the junction between a candidate and an election) get their UUIDs from one of two sources:

1. **Candidate file:** Each election-keyed section in a candidate file can include a candidacy ID
2. **Auto-generated during import:** If no candidacy UUID is specified, the importer generates one from a deterministic hash of `(candidate_id, election_id)` to ensure idempotency

## Converter Validation Rules

### Missing ID: validation error

If a file that requires an ID (overview, single-contest, candidate) has:
- No `| ID | ... |` row at all, OR
- An `| ID | |` row with an empty value

The converter MUST emit a **validation error** and skip this record. The converter must NOT:
- Silently generate a UUID
- Use a placeholder value
- Fall back to a natural key

**Rationale:** Silent UUID generation creates identity drift. Two converter runs on the same file would produce different UUIDs, breaking idempotency and making it impossible to correlate records across import cycles.

### Invalid ID: validation error

If the ID value is present but not a valid UUID (e.g., malformed string, wrong length, non-hex characters), the converter MUST emit a **validation error** with the file path and the invalid value.

### Duplicate ID: validation error

If two different files contain the same UUID, the converter MUST emit a **validation error** listing both file paths. UUIDs must be globally unique across all election data files.

## UUID Lifecycle

### Phase 1 (Current)

Files are created with empty ID rows (`| ID | |`). The format spec and validation rules are defined but not enforced by running code.

### Phase 2 (Backfill)

The backfill CLI command (see [backfill-rules.md](./backfill-rules.md)):
1. Reads markdown files with empty ID rows
2. Matches records to existing DB entries using natural keys
3. Writes the DB UUID back into the markdown `| ID | {uuid} |` row
4. For records with no DB match, generates a new UUID v4 and writes it

After backfill, all files have populated ID rows.

### Phase 2 (Converter)

The converter:
1. Reads the `| ID | {uuid} |` row from each file
2. Validates it is a non-empty, valid UUID
3. Passes it through to the JSONL output as the `id` field
4. The importer uses this UUID as the database primary key (upsert on ID)

### Ongoing

When creating new election files (e.g., for a new election cycle):
1. New files start with `| ID | |` (empty)
2. Run backfill to check for pre-existing DB records
3. If no match, backfill generates and writes a new UUID
4. Subsequent converter runs use this UUID

## UUID Generation Method

When new UUIDs need to be created (by the backfill command, not the converter):

- Use Python's `uuid.uuid4()` -- random UUID v4
- Do NOT use UUID v1 (includes MAC address), UUID v3/v5 (namespace-based), or sequential UUIDs
- The generated UUID is written into the markdown file immediately, making the file the permanent source of truth

## Error Message Format

All UUID-related validation errors should follow this format:

```
UUID_MISSING: {file_path} - No ID found in metadata table. Run backfill to assign UUIDs.
UUID_INVALID: {file_path} - Invalid UUID value: "{value}"
UUID_DUPLICATE: {file_path_1} and {file_path_2} - Duplicate UUID: {uuid}
```
