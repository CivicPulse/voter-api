# Data Model: Voter History Ingestion

**Feature Branch**: `006-voter-history`
**Date**: 2026-02-17
**Migration**: `020_voter_history.py`

## Entity Relationship Diagram

```text
┌─────────────────────┐       ┌──────────────────────────┐       ┌─────────────────────┐
│     import_jobs      │       │      voter_history       │       │       voters         │
│─────────────────────│       │──────────────────────────│       │─────────────────────│
│ id (PK, UUID)       │──┐    │ id (PK, UUID)            │    ┌──│ voter_registration_  │
│ file_name            │  │    │ voter_registration_      │    │  │   number (UQ)       │
│ file_type            │  │    │   number                 │────┘  │ county              │
│ status               │  └───│ import_job_id (FK)       │       │ ...                 │
│ records_skipped  NEW │       │ county                   │       └─────────────────────┘
│ records_unmatched NEW│       │ election_date            │
│ ...                  │       │ election_type            │       ┌─────────────────────┐
└─────────────────────┘       │ normalized_election_type │       │      elections       │
                               │ party                    │       │                     │
                               │ ballot_style             │       │─────────────────────│
                               │ absentee                 │       │ id (PK, UUID)       │
                               │ provisional              │       │ name                │
                               │ supplemental             │       │ election_date       │
                               │ created_at               │       │ election_type       │
                               └──────────────────────────┘       │ creation_method NEW │
                                                                  │ ...                 │
                                                                  └─────────────────────┘
```

**Relationships**:

- `voter_history.import_job_id` → `import_jobs.id` (FK, CASCADE on delete)
- `voter_history.voter_registration_number` → `voters.voter_registration_number` (logical join, NO FK constraint — supports lazy reconciliation for unmatched records)
- `voter_history` → `elections` (logical join on `election_date` + `normalized_election_type` = `elections.election_type` — NO FK constraint)

## New Table: `voter_history`

Stores individual voter participation records from GA SoS voter history CSV files.

| Column                    | Type              | Nullable | Default       | Notes                                              |
| ------------------------- | ----------------- | -------- | ------------- | -------------------------------------------------- |
| id                        | UUID              | NOT NULL | gen_random_uuid() | Primary key                                    |
| voter_registration_number | VARCHAR(20)       | NOT NULL |               | Joins to `voters` at query time                    |
| county                    | VARCHAR(100)      | NOT NULL |               | County name from CSV                               |
| election_date             | DATE              | NOT NULL |               | Parsed from MM/DD/YYYY                             |
| election_type             | VARCHAR(50)       | NOT NULL |               | Raw value from CSV (e.g., "GENERAL ELECTION")      |
| normalized_election_type  | VARCHAR(20)       | NOT NULL |               | Mapped type for election join (e.g., "general")    |
| party                     | VARCHAR(50)       | NULL     |               | Party ballot for primaries; null otherwise          |
| ballot_style              | VARCHAR(100)      | NULL     |               | Ballot style code from CSV                         |
| absentee                  | BOOLEAN           | NOT NULL | false         | "Y" → true, else false                             |
| provisional               | BOOLEAN           | NOT NULL | false         | "Y" → true, blank → false                          |
| supplemental              | BOOLEAN           | NOT NULL | false         | "Y" → true, blank → false                          |
| import_job_id             | UUID              | NOT NULL |               | FK to `import_jobs.id`                             |
| created_at                | TIMESTAMPTZ       | NOT NULL | now()         | Record creation timestamp                          |

### Constraints

| Constraint                      | Type      | Columns/Expression                                           |
| ------------------------------- | --------- | ------------------------------------------------------------ |
| pk_voter_history                | PRIMARY   | `id`                                                         |
| uq_voter_history_participation  | UNIQUE    | `(voter_registration_number, election_date, election_type)`  |
| fk_voter_history_import_job     | FOREIGN   | `import_job_id` → `import_jobs.id` ON DELETE CASCADE         |

### Indexes

| Index Name                               | Columns                                                    | Type    | Notes                                           |
| ---------------------------------------- | ---------------------------------------------------------- | ------- | ----------------------------------------------- |
| idx_voter_history_reg_num                | `voter_registration_number`                                | B-tree  | Primary lookup for voter history queries         |
| idx_voter_history_election_date          | `election_date`                                            | B-tree  | Date range filtering                             |
| idx_voter_history_election_type          | `election_type`                                            | B-tree  | Election type filtering                          |
| idx_voter_history_county                 | `county`                                                   | B-tree  | County filtering and aggregation                 |
| idx_voter_history_import_job_id          | `import_job_id`                                            | B-tree  | Re-import deletion (delete by import job)        |
| idx_voter_history_date_type              | `(election_date, normalized_election_type)`                | B-tree  | Join to elections table; aggregate queries        |

## Modified Table: `elections`

### New Column

| Column          | Type        | Nullable | Default    | Notes                                                |
| --------------- | ----------- | -------- | ---------- | ---------------------------------------------------- |
| creation_method | VARCHAR(20) | NOT NULL | `'manual'` | How the election record was created                  |

**Valid values**: `'manual'`, `'feed_import'`, `'voter_history'`

**Migration strategy**: Add column with `server_default='manual'`. All existing records are backfilled as `'manual'`. The SoS feed import service should be updated to set `'feed_import'` on new elections (separate concern, not blocking this feature).

### New Index

| Index Name                         | Columns           | Type   | Notes                           |
| ---------------------------------- | ----------------- | ------ | ------------------------------- |
| idx_elections_creation_method      | `creation_method` | B-tree | Filter elections by source       |

## Modified Table: `import_jobs`

### New Columns

| Column            | Type    | Nullable | Default | Notes                                            |
| ----------------- | ------- | -------- | ------- | ------------------------------------------------ |
| records_skipped   | INTEGER | NULL     |         | Duplicate records within the same file           |
| records_unmatched | INTEGER | NULL     |         | Records with voter reg numbers not in voters table |

These columns are nullable and default to NULL, matching the convention of existing counter columns.

## State Transitions

### ImportJob Status

```text
pending → running → completed
                  → failed
completed → superseded (when a newer import of the same file replaces it)
```

The `superseded` status is new — applied to previous import jobs when their records are replaced by a re-import.

### Election creation_method Values

```text
manual        — Created via API/CLI by an administrator
feed_import   — Created by SoS feed ingestion
voter_history — Auto-created during voter history import
```

## Validation Rules

### VoterHistory Record Validation (at parse time)

1. `voter_registration_number` — REQUIRED, non-empty string, max 20 chars
2. `county` — REQUIRED, non-empty string, max 100 chars
3. `election_date` — REQUIRED, must parse from MM/DD/YYYY format; reject record on failure
4. `election_type` — REQUIRED, non-empty string, max 50 chars
5. `party` — OPTIONAL, stored as-is; null/empty accepted
6. `ballot_style` — OPTIONAL, stored as-is; null/empty accepted
7. `absentee` — OPTIONAL, "Y" → true, anything else (including blank) → false
8. `provisional` — OPTIONAL, "Y" → true, anything else (including blank) → false
9. `supplemental` — OPTIONAL, "Y" → true, anything else (including blank) → false

### Duplicate Handling

Within a single import file, if multiple records share the same `(voter_registration_number, election_date, election_type)`, only the first occurrence is stored. Subsequent duplicates are counted in `records_skipped`.

### Unmatched Voter Handling

Records whose `voter_registration_number` does not exist in the `voters` table are still stored in `voter_history`. They are counted in `records_unmatched`. At query time, these records are joined to voters lazily — if the voter is later imported, the history automatically associates.

## Sample Data

### Input CSV (GA SoS format)

```csv
County Name,Voter Registration Number,Election Date,Election Type,Party,Ballot Style,Absentee,Provisional,Supplemental
FULTON,12345678,11/05/2024,GENERAL ELECTION,,GENERAL,N,N,N
FULTON,12345678,05/21/2024,GENERAL PRIMARY,REPUBLICAN,PARTISAN,Y,,
DEKALB,87654321,11/05/2024,GENERAL ELECTION,,GENERAL,N,,
COBB,11111111,01/05/2021,SPECIAL ELECTION RUNOFF,,GENERAL,Y,N,N
```

### Resulting `voter_history` Records

| voter_registration_number | county  | election_date | election_type          | party      | ballot_style | absentee | provisional | supplemental |
| ------------------------- | ------- | ------------- | ---------------------- | ---------- | ------------ | -------- | ----------- | ------------ |
| 12345678                  | FULTON  | 2024-11-05    | GENERAL ELECTION       | NULL       | GENERAL      | false    | false       | false        |
| 12345678                  | FULTON  | 2024-05-21    | GENERAL PRIMARY        | REPUBLICAN | PARTISAN     | true     | false       | false        |
| 87654321                  | DEKALB  | 2024-11-05    | GENERAL ELECTION       | NULL       | GENERAL      | false    | false       | false        |
| 11111111                  | COBB    | 2021-01-05    | SPECIAL ELECTION RUNOFF| NULL       | GENERAL      | true     | false       | false        |

### Auto-Created Elections

If no elections exist for these dates/types, the import auto-creates:

| name                                      | election_date | election_type | creation_method | status    | district  | data_source_url |
| ----------------------------------------- | ------------- | ------------- | --------------- | --------- | --------- | --------------- |
| General Election - 11/05/2024             | 2024-11-05    | general       | voter_history   | finalized | Statewide | n/a             |
| General Primary - 05/21/2024              | 2024-05-21    | primary       | voter_history   | finalized | Statewide | n/a             |
| Special Election Runoff - 01/05/2021      | 2021-01-05    | runoff        | voter_history   | finalized | Statewide | n/a             |
