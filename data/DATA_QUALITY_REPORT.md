# Data Quality Report & Remediation Plan

**Generated**: 2026-03-12
**Database**: voter-api dev (localhost:5432/voter_api)
**Scope**: Bibb + Houston counties, 2026 voter history, all boundaries, SOS election feeds

---

## Team 1: Data Load Summary

| Table | Count | Notes |
|-------|------:|-------|
| voters | 242,312 | Bibb: 116,198 / Houston: 126,114 |
| voter_history | 10,201,848 | Spans 2024-01-02 to 2026-05-19 (37 dates) |
| elections | 22 | Only mid-2025 to 2026 specials |
| election_events | 0 | Failed to populate |
| boundaries | 3,153 | 8 types, all geometries valid |
| candidates | 84 | |
| county_districts | 769 | |
| precinct_crosswalk | 0 | `build-crosswalk` CLI command doesn't exist |
| import_jobs | 25 | 20 completed, 5 failed (old 2024 data + absentee) |

---

## Team 2: Data Quality Findings

### CRITICAL Issues

#### C1. 96.7% of voter history records unresolved (no election_id)
- **9,866,864 of 10,201,848** records have `election_id = NULL`
- **Root cause**: The `2026.zip` voter history file contains statewide data spanning 2024-2026, but only 22 elections exist in the DB — all are 2025-2026 special/runoff elections. Major elections missing:
  - 2024-11-05 General: 5,299,285 records (no election)
  - 2024-05-21 Primary: 1,280,250 records (no election)
  - 2024-03-12 Primary: 886,542 records (no election)
  - 2025-03-18 Special: 77,304 records (no election)
  - Plus 20+ other dates

#### C2. 97% of voter history has no matching voter
- **9,896,600 of 10,201,848** VH records don't match any voter by `voter_registration_number`
- **Root cause**: Only Bibb + Houston voters (242K) were loaded, but VH covers the entire state of Georgia

#### C3. 100% of elections missing election_event_id
- **22 of 22** elections have `election_event_id = NULL`
- **0 election_events** exist in the DB
- **Root cause**: Tier 0 resolution (`_resolve_tier0_event_matching`) should create events and link them, but the `resolve-elections` CLI output showed `tier0=0` — the Tier 0 step completed before Tier 1 ran, suggesting the distinct query returned empty results or the commit ordering failed

#### C4. 100% of elections missing boundary_id
- **22 of 22** elections have `boundary_id = NULL` despite all having `district_type` + `district_identifier` set
- **Root cause**: `backfill_election_district_fields()` only processes elections where `district_type IS NULL`. Since these elections were created with `district_type` already set (from SOS feed import), the boundary lookup in `link_election_to_boundary()` was never called. The boundary linking logic needs a separate pass for elections that have `district_type` but no `boundary_id`.

### HIGH Issues

#### H1. Election type mapping gaps
Three raw election types are incorrectly mapped:

| Raw Type | Current Mapping | Correct Mapping | Records |
|----------|----------------|-----------------|--------:|
| `GENERAL ELECTION RUNOFF` | `general` | `runoff` | 133,616 |
| `PPP` | `general` (default) | `primary` (Presidential Preference Primary) | 20 |
| `STATEWIDE` | `general` (default) | needs investigation | 2 |

**File**: `src/voter_api/lib/voter_history/parser.py`, `ELECTION_TYPE_MAP`

#### H2. Duplicate elections (F2)
Two pairs of true duplicates sharing `(date, district_type, district_identifier)`:
- **2025-06-17 PSC District 3**: 2 elections (both `primary`)
- **2025-06-17 PSC District 2**: 2 elections (both `primary`)

These are Dem/Rep party primary variants — `district_party` column differentiates them but the unique constraint doesn't include party.

#### H3. Voter district ↔ boundary identifier mismatch
Voters store districts unpadded (`"2"`, `"8"`, `"18"`), boundaries use 3-digit zero-padding (`"002"`, `"008"`, `"018"`). Exact string joins fail for:

| Type | Unmatched Districts | Affected Voters |
|------|-------------------|----------------:|
| Congressional | 2, 8 | 242,312 |
| State Senate | 18, 20, 25, 26 | 242,312 |

**Not a data error** — the resolution service handles padding internally. But any ad-hoc queries or future features doing direct joins will hit this.

#### H4. Precinct crosswalk empty
- 48 distinct voter precincts exist
- 0 crosswalk entries (the `build-crosswalk` CLI command doesn't exist in this codebase)

### MEDIUM Issues

#### M1. Election date clustering
Three dates have 3+ elections, which complicates Tier 2 resolution:
- 2025-06-17: 4 elections (PSC primaries)
- 2026-03-10: 4 elections (multi-district special)
- 2025-11-04: 3 elections (municipal general + PSC)

#### M2. Import job failures (non-blocking)
- 3 failed `2024.csv` voter_history imports (precede the successful one)
- 2 failed `STATEWIDE.csv` absentee imports
- 560 failed records in successful 2024 VH import, 8 in 2025

### LOW Issues

#### L1. December 2, 2025 runoff has 0 VH matches
- Election type is `runoff` but VH records for that date use `normalized_election_type = runoff` (91,211 records)
- Tier 1 assigned 91,211 records, so this is resolved. The 0 in the join was a LEFT JOIN artifact.

#### L2. Cross-district participation: None detected
No voters appear in elections outside their registered district. This is expected for recent special elections.

#### L3. Election-to-boundary type consistency: All consistent
No mismatches between `election.district_type` and `boundary.boundary_type`.

---

## Team 3: Root Cause Analysis & Remediation Plan

### P0: Quick Wins (Config/Mapping Changes)

#### P0-1. Fix ELECTION_TYPE_MAP gaps
**File**: `src/voter_api/lib/voter_history/parser.py` line 30

Add missing mappings:
```python
ELECTION_TYPE_MAP: dict[str, str] = {
    # ... existing entries ...
    "GENERAL ELECTION RUNOFF": "runoff",      # 133,616 records misclassified
    "PPP": "primary",                          # Presidential Preference Primary
    "PRESIDENTIAL PREFERENCE PRIMARY": "primary",  # already exists, but confirm
    # "STATEWIDE" needs investigation — only 2 records
}
```

**Impact**: Fixes 133,636 records on re-import/re-resolution.

#### P0-2. Add boundary linking for elections with district_type but no boundary_id
**File**: `src/voter_api/services/election_resolution_service.py` line 116

The `backfill_election_district_fields()` function filters on `district_type IS NULL`, but elections created from SOS feeds already have `district_type` set. Add a separate pass:

```python
async def backfill_election_boundary_ids(session: AsyncSession) -> int:
    """Link elections to boundaries when district_type is set but boundary_id is missing."""
    result = await session.execute(
        select(Election).where(
            Election.district_type.isnot(None),
            Election.district_identifier.isnot(None),
            Election.boundary_id.is_(None),
        )
    )
    elections = list(result.scalars().all())
    updated = 0
    for election in elections:
        boundary_type = DISTRICT_TYPE_TO_BOUNDARY_TYPE.get(election.district_type)
        if boundary_type and election.district_identifier:
            padded = pad_district_identifier(election.district_identifier)
            stmt = select(Boundary.id).where(
                Boundary.boundary_type == boundary_type,
                Boundary.boundary_identifier == padded,
            )
            result = await session.execute(stmt)
            boundary_row = result.first()
            if boundary_row:
                election.boundary_id = boundary_row[0]
                updated += 1
    await session.flush()
    return updated
```

Call this from `resolve_voter_history_elections()` after `backfill_election_district_fields()`.

**Impact**: Links all 22 elections to their boundaries immediately.

### P1: Data Fixes (Re-run with corrections)

#### P1-1. Create missing 2024-2025 elections
The database needs elections for 2024-2025 dates that appear in voter history. Options:
1. **Seed from production API** — if prod has these elections, `voter-api seed --category elections` should pull them (fix the duplicate key error first)
2. **Auto-create from VH dates** — add a CLI command that creates stub elections from distinct `(election_date, normalized_election_type)` pairs in voter_history
3. **Manual creation** — create the ~15 missing elections via API or SQL

**Priority order**: The Nov 5, 2024 General (5.3M records) and May 21, 2024 Primary (1.3M records) alone would resolve 65% of orphaned VH.

#### P1-2. Re-run election resolution with --force
After P0-1 and P0-2 are applied:
```bash
uv run voter-api import resolve-elections --force
```

This will:
- Create election events (Tier 0 — currently 0)
- Re-resolve with corrected type mappings
- Link boundaries via the new backfill function

#### P1-3. Fix election seed duplicate key error
**File**: `src/voter_api/lib/data_loader/election_seeder.py`

The seed command's `INSERT ... ON CONFLICT (id) DO UPDATE` fails when a new election has a different UUID but the same `(name, election_date)`. Change the ON CONFLICT target to `(name, election_date)` or use `ON CONFLICT DO NOTHING` + separate update.

### P2: Code Changes

#### P2-1. Add dedup guard for election creation
**File**: `src/voter_api/services/election_service.py`

Before creating an election, check for existing elections with the same `(election_date, district_type, district_identifier, district_party)`. Currently the PSC Dem/Rep primaries create apparent duplicates because `district_party` isn't part of the unique constraint check.

#### P2-2. Implement `build-crosswalk` CLI command
The plan references `voter-api import build-crosswalk` but this command doesn't exist. The `precinct_crosswalk` table was created by migration but has no import path.

#### P2-3. Fix Tier 0 event creation
**File**: `src/voter_api/services/election_resolution_service.py`

Tier 0 (`_resolve_tier0_event_matching`) produced 0 results despite matching (date, type) pairs existing. Investigate whether:
- The `WHERE election_event_id IS NULL` filter excluded records (unlikely — all are NULL)
- The `find_or_create_election_event` transaction was rolled back
- The commit in `resolve_voter_history_elections` at line 225 came before Tier 0 changes were flushed

#### P2-4. Normalize voter district identifiers at import time
**File**: `src/voter_api/services/import_service.py`

Consider zero-padding voter district fields (`congressional_district`, `state_senate_district`, `state_house_district`) to 3 digits at import time, matching boundary identifiers. This eliminates the need for padding logic throughout the codebase.

### P3: Future Work

#### P3-1. Temporal district tracking
Voters who moved or whose districts changed due to redistricting will show cross-district participation for pre-2022 elections. A `voter_district_history` table would track district assignments over time.

#### P3-2. Statewide voter import
Currently only Bibb + Houston (242K voters). Full Georgia has ~7M registered voters. The 9.9M orphaned VH records would mostly resolve with a statewide voter file.

#### P3-3. Auto-election creation from SOS calendar
Build a scraper/API client that creates election records from the GA SOS election calendar, eliminating the need for manual creation.

#### P3-4. Additional boundary sources
- Municipal boundaries (for municipal elections)
- Judicial circuits (for DA/judge elections)
- School district boundaries (separate from school board commission districts)

---

## Verification SQL

After applying P0 + P1 fixes, re-run these checks to verify improvement:

```sql
-- Should drop from 96.7% to <5% after adding 2024 elections
SELECT round(100.0 * count(*) FILTER (WHERE election_id IS NULL) / count(*), 2) AS pct_unresolved
FROM voter_history;

-- Should be >0 after Tier 0 fix
SELECT count(*) FROM election_events;

-- Should be 0 after boundary backfill
SELECT count(*) FROM elections WHERE deleted_at IS NULL AND boundary_id IS NULL AND district_type IS NOT NULL;

-- GENERAL ELECTION RUNOFF should map to 'runoff'
SELECT normalized_election_type, count(*) FROM voter_history
WHERE election_type = 'GENERAL ELECTION RUNOFF'
GROUP BY normalized_election_type;
```
