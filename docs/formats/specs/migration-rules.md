# Migration Rules

This document defines the concrete, per-file-type rules for migrating existing ~200 markdown election files from the legacy format to the enhanced format defined in Phase 1. These rules are specific enough that Phase 2 implementers make NO judgment calls -- every transformation is deterministic.

**Specced in Phase 1. Implemented as a Python migration script in Phase 2.**

## Scope

The migration script transforms files in `data/elections/` from the legacy format (pre-Phase 1) to the enhanced format defined in:
- [multi-contest.md](../markdown/multi-contest.md) (county files)
- [single-contest.md](../markdown/single-contest.md) (statewide/federal/special files)
- [overview.md](../markdown/overview.md) (election overview files)

## Overview Files

**Location:** `data/elections/{date}/{date}-{election-type}.md` (e.g., `2026-05-19-general-primary.md`)

**Replaces:** Legacy overview files with no format version, no ID, and calendar dates in prose format.

### Metadata Table Additions

Add these rows to the existing metadata table, in this order, at the top:

| Row | Value | Source |
|-----|-------|--------|
| `ID` | *(empty -- to be backfilled)* | Leave blank |
| `Format Version` | `1` | Literal |
| `Name (SOS)` | *(empty -- to be populated from SOS data)* | Leave blank |
| `Type` | `{election_type}` from [election-types vocabulary](../vocabularies/election-types.md) | Infer from filename: `general-primary` -> `general_primary`, `general` -> `general`, `special` -> `special`, `special-primary` -> `special_primary`, `municipal` -> `municipal` |
| `Stage` | `election` | Literal (default; runoffs and recounts are separate files) |

### Election Calendar Migration

Convert the Election Calendar table from prose dates to ISO format with Source column:

**Before:**
```markdown
| Milestone | Date |
|-----------|------|
| Qualifying Period | March 2-6, 2026 |
| Voter Registration Deadline | April 20, 2026 |
| Early Voting | April 27 - May 15, 2026 |
```

**After:**
```markdown
| Milestone | Date | Source |
|-----------|------|--------|
| Qualifying Start | 2026-03-02 | SOS |
| Qualifying End | 2026-03-06 | SOS |
| Voter Registration Deadline | 2026-04-20 | SOS |
| Early Voting Start | 2026-04-27 | SOS |
| Early Voting End | 2026-05-15 | SOS |
| Absentee Ballot Application Deadline | 2026-05-08 | SOS |
| Election Day | 2026-05-19 | SOS |
```

**Transformation rules:**
- Split range dates into separate Start/End rows: "March 2-6, 2026" becomes two rows (Start: 2026-03-02, End: 2026-03-06)
- Parse all dates to ISO 8601 format (YYYY-MM-DD)
- Add `Source` column with value `SOS` for all dates from SOS data
- Rename milestones to match JSONL schema field names: "Qualifying Period" -> "Qualifying Start" + "Qualifying End", "Early Voting" -> "Early Voting Start" + "Early Voting End"
- If a date cannot be parsed (e.g., "TBD", empty), emit warning and set value to `TBD`

### Data Sources Section

Add a `## Data Sources` section at the bottom of the file:

```markdown
## Data Sources

| Source | URL | Notes |
|--------|-----|-------|
| SOS Results Feed | TBD | Set when results feed URL is available |
```

## Statewide/Federal Contest Files (Single-Contest)

**Location:** `data/elections/{date}/{date}-{contest-slug}.md` (e.g., `2026-05-19-governor.md`)

**Replaces:** Legacy single-contest files with no format version, no Body/Seat metadata.

### Metadata Table Additions

Add these rows to the existing metadata table, in this order, at the top:

| Row | Value | Source |
|-----|-------|--------|
| `ID` | *(empty -- to be backfilled)* | Leave blank |
| `Format Version` | `1` | Literal |
| `Body` | `{body-id}` | Deterministic mapping from contest name (see Body/Seat Inference below) |
| `Seat` | `{seat-id}` | Deterministic mapping from contest name (see Body/Seat Inference below) |
| `Stage` | `election` | Literal |

### Body/Seat Inference for Statewide/Federal Contests

Map contest filenames to Body/Seat values using these exact rules:

| Contest Filename Pattern | Body | Seat |
|--------------------------|------|------|
| `*-governor.md` | `ga-governor` | `sole` |
| `*-lieutenant-governor.md` | `ga-lt-governor` | `sole` |
| `*-secretary-of-state.md` | `ga-sos` | `sole` |
| `*-attorney-general.md` | `ga-ag` | `sole` |
| `*-state-school-superintendent.md` | `ga-school-superintendent` | `sole` |
| `*-agriculture-commissioner.md` | `ga-agriculture` | `sole` |
| `*-labor-commissioner.md` | `ga-labor` | `sole` |
| `*-insurance-commissioner.md` | `ga-insurance` | `sole` |
| `*-us-senate.md` | `ga-us-senate` | `sole` |
| `*-us-house-district-NN.md` | `ga-us-house` | `district-N` (unpadded: `02` -> `2`) |
| `*-state-senate-district-NN.md` | `ga-state-senate` | `district-N` |
| `*-state-house-district-NN.md` | `ga-state-house` | `district-N` |
| `*-psc-district-N.md` | `ga-psc` | `district-N` |

**Unrecognized contest filename:** If the filename does not match any pattern above, emit warning: `BODY_SEAT_UNKNOWN: {file_path} - Cannot infer Body/Seat from filename. Set manually.` Leave Body and Seat rows empty.

### Candidate Table Column Changes

Remove the `Email` and `Website` columns from the candidate table:

**Before (7 columns):**
```markdown
| Candidate | Status | Incumbent | Occupation | Qualified | Email | Website |
```

**After (5 columns):**
```markdown
| Candidate | Status | Incumbent | Occupation | Qualified Date |
```

**Transformation rules:**
- Drop `Email` column entirely (email moves to candidate file)
- Drop `Website` column entirely (website moves to candidate file)
- Rename `Qualified` to `Qualified Date`
- Candidate name remains as plain text (not linked) until candidate files are created

## County Files (Multi-Contest)

**Location:** `data/elections/{date}/counties/{date}-{county}.md` (e.g., `2026-05-19-bibb.md`)

**Replaces:** Legacy county files with no format version, no Body/Seat metadata per contest.

### File-Level Metadata Additions

Add these rows to the existing file-level metadata table, at the top:

| Row | Value |
|-----|-------|
| `ID` | *(empty -- to be backfilled)* |
| `Format Version` | `1` |

### Per-Contest Body/Seat Metadata

Add a `**Body:** {body-id} | **Seat:** {seat-id}` line immediately below each `### Contest Name` heading, before the candidate table:

```markdown
### Board of Education At Large-Post 7

**Body:** bibb-boe | **Seat:** post-7

| Candidate | Status | Incumbent | Occupation | Qualified Date |
```

**Body/Seat inference for county contests:**

1. Look up the county reference file at `data/states/GA/counties/{county}.md`
2. Parse the Governing Bodies table to get all Body IDs for this county
3. Match each `### Contest Name` heading to a Body ID using these rules:

| Contest Name Pattern | Body ID | Seat ID |
|----------------------|---------|---------|
| `Board of Education At Large-Post N` | `{county}-boe` | `post-N` |
| `Board of Education District N` | `{county}-boe` | `district-N` |
| `Civil/Magistrate Court Judge` | `{county}-civil-magistrate` | `sole` |
| `Judge of Superior Court, * - {Surname}` | `{county}-superior-court` | `judge-{surname}` (lowercased) |
| `State Court Judge ({Surname})` | `{county}-state-court` | `judge-{surname}` (lowercased) |
| `{Authority}-At Large` | Look up by authority name in Governing Bodies | `at-large` |
| `{Authority}-District N` | Look up by authority name in Governing Bodies | `district-N` |
| `County Commission District N` | `{county}-commission` | `district-N` |

4. If the county reference file has no `## Governing Bodies` section: emit warning `NO_GOVERNING_BODIES: {county_ref_path} - No Governing Bodies table. Body/Seat will be blank for all contests in {contest_file_path}.` Leave Body and Seat blank.

5. If a contest name does not match any Body in the Governing Bodies table: emit warning `BODY_MATCH_FAILED: {contest_file_path}::{contest_name} - No matching Body ID in {county_ref_path}. Set manually.` Leave Body and Seat blank.

### Candidate Table Column Changes

Same rules as statewide/federal files:
- Drop `Email` column
- Drop `Website` column
- Rename `Qualified` to `Qualified Date`
- Candidate name remains as plain text (not linked) until candidate files are created

## Special Election Contest Files

**Location:** `data/elections/{date}/{date}-{contest-slug}.md` (same as single-contest)

Special election files merge into the single-contest format. Apply the same rules as statewide/federal single-contest files, plus:

### Additional Metadata Migration

If the legacy file has Purpose or Eligibility prose sections, move them to metadata table rows:

| Row | Value |
|-----|-------|
| `Purpose` | Text from the Purpose section (single line) |
| `Eligibility` | Text from the Eligibility section (single line) |

If these sections do not exist in the legacy file, do not add the rows.

### Body/Seat for Special Elections

Special elections use the same Body/Seat inference rules as their contest type:
- A special election for Governor -> `ga-governor` / `sole`
- A special election for U.S. House District 2 -> `ga-us-house` / `district-2`
- A special election for a county seat -> look up in county reference file

## Candidate File Creation

For each unique candidate name found across all contest files, create a stub candidate file:

**Location:** `data/candidates/{name-slug}-{8-char-placeholder}.md`

**Filename rules:**
- `{name-slug}`: Lowercase, hyphen-separated, ASCII-only version of the full name
  - "Kerry Warren Hatcher" -> `kerry-warren-hatcher`
  - "David Lafayette Mincey III" -> `david-lafayette-mincey-iii`
  - Remove accents (NFD decomposition + strip combining marks)
  - Replace spaces and non-alphanumeric chars with hyphens
  - Collapse consecutive hyphens
  - Strip leading/trailing hyphens
- `{8-char-placeholder}`: Literal string `00000000` (eight zeros). Replaced with the first 8 characters of the candidate's UUID during backfill.

**Stub file content:**

```markdown
# {Full Name}

## Metadata

| Field | Value |
|-------|-------|
| ID | |
| Format Version | 1 |
| Full Name | {Full Name} |

## Person

| Field | Value |
|-------|-------|
| Email | {email from contest file, or --} |
| Website | {website URL from contest file, or --} |
| Home County | {county name, if from a county contest file, or --} |
| Occupation | {occupation from contest file} |

## Elections

### {Election Display Name}

| Field | Value |
|-------|-------|
| Contest | {Contest Name} |
| Election File | [{election-file-slug}.md]({relative-path}) |
| Party | {party, or --} |
| Status | {status from contest file} |
| Incumbent | {Yes/No} |
| Qualified Date | {date} |
```

**Deduplication rules:**
- If the same candidate name appears in multiple contests (e.g., a candidate running in multiple elections), create only ONE candidate file with multiple election-keyed sections.
- Match candidate names exactly (case-sensitive). Slight name variations (e.g., "John Smith" vs "John Q Smith") create separate files; manual deduplication is a Phase 3+ concern.

## Files NOT Migrated

The following files are NOT touched by the migration script:

| File/Directory | Reason |
|----------------|--------|
| `data/states/GA/counties/*.md` (except Bibb) | County reference files are enhanced manually, county-by-county. Only Bibb is done in Phase 1. |
| `data/elections/formats/` | Legacy format spec files. Superseded by `docs/formats/` but kept for historical reference. NOT deleted. |
| `data/elections/*/README.md` | Election directory README files. No structural changes needed. |

## Migration Script CLI

```bash
# Migrate all files in an election directory
voter-api migrate data/elections/2026-05-19/

# Migrate with dry-run (show changes without writing)
voter-api migrate data/elections/2026-05-19/ --dry-run

# Migrate only county files
voter-api migrate data/elections/2026-05-19/counties/ --type county

# Migrate and create candidate files
voter-api migrate data/elections/2026-05-19/ --create-candidates
```

### Output Format

```
Migration Report: data/elections/2026-05-19/
  Overview files:     1 migrated
  Single-contest:    15 migrated (13 Body/Seat inferred, 2 warnings)
  Multi-contest:      4 migrated (48 contests, 45 Body/Seat inferred, 3 warnings)
  Candidate stubs:   87 created in data/candidates/
  Warnings:
    BODY_SEAT_UNKNOWN: data/elections/2026-05-19/2026-05-19-soil-water.md
    BODY_MATCH_FAILED: data/elections/2026-05-19/counties/2026-05-19-chatham.md::Harbor Commission
    NO_GOVERNING_BODIES: data/states/GA/counties/chatham.md

Total: 20 files migrated, 87 candidates created, 3 warnings, 0 errors
```

## Idempotency

Running the migration script twice on the same directory must produce the same result:
- Files already in enhanced format (have `Format Version` row) are skipped
- Candidate files that already exist (by name slug) are not recreated
- No data is lost or duplicated on repeated runs
