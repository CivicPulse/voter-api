---
phase: 04-end-to-end-demo
plan: 01
subsystem: converter, import-pipeline, candidate-api
tags: [pipeline, jsonl, converter, import, candidates, election-events, elections]
dependency_graph:
  requires: []
  provides:
    - "Working markdown-to-database pipeline for three election directories"
    - "candidates.jsonl + candidacies.jsonl generation from candidate markdown"
    - "Nullified placeholder UUID in election import service"
  affects:
    - election_import_service
    - candidate_import_service
    - candidacy_import_service
    - candidate_service
    - converter (parser, writer, __init__)
    - election_tracker ingester (ElectionType expansion)
tech_stack:
  added:
    - scripts/generate_candidate_jsonl.py (standalone candidate JSONL generator)
  patterns:
    - "dict.fromkeys(all_keys) | r pattern for uniform UPSERT column normalization"
    - "_normalize_date() handling MM/DD/YYYY + em-dash placeholder -> None"
    - "_normalize_election_type() normalizing old markdown type strings to enum values"
    - "Accumulated record writing in convert_directory (single write vs per-file overwrite)"
key_files:
  created:
    - scripts/generate_candidate_jsonl.py
    - data/elections/2026-03-10/jsonl/election_events.jsonl
    - data/elections/2026-03-10/jsonl/elections.jsonl
    - data/elections/2026-03-10/jsonl/candidates.jsonl
    - data/elections/2026-03-10/jsonl/candidacies.jsonl
    - data/elections/2026-03-17/jsonl/election_events.jsonl
    - data/elections/2026-03-17/jsonl/elections.jsonl
    - data/elections/2026-03-17/jsonl/candidates.jsonl
    - data/elections/2026-03-17/jsonl/candidacies.jsonl
    - data/elections/2026-05-19/jsonl/election_events.jsonl
    - data/elections/2026-05-19/jsonl/elections.jsonl
    - tests/unit/test_services/test_election_import_service.py
  modified:
    - src/voter_api/services/election_import_service.py
    - src/voter_api/services/candidate_import_service.py
    - src/voter_api/services/candidacy_import_service.py
    - src/voter_api/services/candidate_service.py
    - src/voter_api/lib/converter/__init__.py
    - src/voter_api/lib/converter/parser.py
    - src/voter_api/lib/converter/writer.py
    - src/voter_api/lib/election_tracker/ingester.py
    - src/voter_api/cli/convert_cmd.py
    - src/voter_api/cli/import_cmd.py
    - pyproject.toml (per-file ruff ignores for scripts/)
    - data/elections/2026-03-10/*.md (UUID backfill)
    - data/elections/2026-03-17/*.md (UUID backfill)
    - data/elections/2026-05-19/*.md (format migration + UUID backfill, 185 files)
decisions:
  - "Normalized all batch upsert functions to use dict.fromkeys(all_keys)|r pattern ensuring uniform column sets for PostgreSQL ON CONFLICT DO UPDATE"
  - "Expanded ElectionType literal in election_tracker/ingester.py to include JSONL pipeline types (general_primary, special_primary, municipal) rather than creating a separate type"
  - "Candidate links from JSONL are imported inline in import_candidates_jsonl via existing _upsert_candidate_links helper"
  - "Scripts directory gets T201/E402/I001 ruff ignores rather than restructuring generate script"
metrics:
  duration_minutes: 36
  completed_date: "2026-03-15"
  tasks_completed: 2
  files_changed: 18
  files_data: 223
---

# Phase 4 Plan 01: End-to-End Election Pipeline Summary

**One-liner:** Full markdown-to-database pipeline for three Georgia election directories with placeholder UUID nullification, date normalization, type string normalization, and candidate/candidacy JSONL generation.

## What Was Built

Task 1 (TDD) fixed the `election_event_id` placeholder UUID (`00000000-0000-0000-0000-000000000000`) being treated as a real FK reference during election import. The import service now skips the placeholder and stores `NULL` instead, preventing FK violations.

Task 2 executed the full pipeline end-to-end:
- Format-migrated May 19 general primary (185 files) and UUID-backfilled all three elections (2026-03-10: 6 files, 2026-03-17: 5 files, 2026-05-19: 185 files)
- Converted all three election directories to JSONL: 1+5=6 March 10, 1+4=5 March 17, 1+25=26 May 19 records
- Generated candidates.jsonl (39 for Mar 10, 10 for Mar 17) and candidacies.jsonl from 49 candidate markdown files
- Imported all JSONL into a local PostGIS database with zero errors
- Verified idempotency: re-import shows 0 inserted, N updated, 0 errors
- Confirmed GET /api/v1/candidates/{id} returns candidate with email, links, and candidacy data

## Final State

```
Election Events:  3 (one per election directory)
Elections:       34 total (5 Mar 10, 4 Mar 17, 25 May 19)
Candidates:      49 (39 Mar 10 + 10 Mar 17)
Candidacies:     49 (one per candidate-election pair)
Candidate Links: ~74 (website + email-mapped-to-other links)
```

API verified:
- GET /api/v1/elections?limit=5 returns elections with `general_primary` type
- GET /api/v1/elections?election_type=special returns 9 special elections across both March dates
- GET /api/v1/candidates/{id} returns candidate with email, links, and candidacy

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed _extract_metadata_value regex matching trailing pipe**
- **Found during:** Task 2, step 2 (UUID backfill)
- **Issue:** Regex `(.+?)` matched trailing `|` in empty cells like `| ID | |`
- **Fix:** Changed to `(.*?)` allowing empty match
- **Files modified:** src/voter_api/cli/convert_cmd.py
- **Commit:** e1e25ff

**2. [Rule 1 - Bug] Fixed convert_directory overwriting JSONL on each file**
- **Found during:** Task 2, step 4 (conversion)
- **Issue:** Each file called `write_jsonl` with open("w"), overwriting previous records; last file determined final output
- **Fix:** Rewrote convert_directory to accumulate all records then write once
- **Files modified:** src/voter_api/lib/converter/__init__.py
- **Commit:** e1e25ff

**3. [Rule 1 - Bug] Fixed election type validation failure for "Partisan Primary" values**
- **Found during:** Task 2, step 4 (conversion of May 19)
- **Issue:** May 19 contest files used human-readable "Partisan Primary" which failed ElectionType enum validation silently
- **Fix:** Added `_ELECTION_TYPE_NORMALIZE` dict and `_normalize_election_type()` in writer.py
- **Files modified:** src/voter_api/lib/converter/writer.py
- **Commit:** e1e25ff

**4. [Rule 1 - Bug] Fixed import pipeline filename (hyphen vs underscore)**
- **Found during:** Task 2, step 6 (import)
- **Issue:** Pipeline looked for `election-events.jsonl` but converter outputs `election_events.jsonl`
- **Fix:** Changed filename in pipeline tuple
- **Files modified:** src/voter_api/cli/import_cmd.py
- **Commit:** e1e25ff

**5. [Rule 1 - Bug] Fixed mixed column sets in batch upsert (ON CONFLICT error)**
- **Found during:** Task 2, step 6 (election import)
- **Issue:** Records with different column sets caused `INSERT value explicitly rendered as boundparameter` error
- **Fix:** Applied `dict.fromkeys(all_keys) | r` normalization pattern to election_import_service, candidate_import_service, and candidacy_import_service
- **Files modified:** src/voter_api/services/election_import_service.py, candidate_import_service.py, candidacy_import_service.py
- **Commit:** e1e25ff

**6. [Rule 1 - Bug] Fixed election_date string-to-date type conversion**
- **Found during:** Task 2, step 6 (election import)
- **Issue:** `election_date` passed as string `'2026-03-10'` but PostgreSQL required `date` object
- **Fix:** Added `date.fromisoformat(val)` conversion in `_prepare_record`
- **Files modified:** src/voter_api/services/election_import_service.py
- **Commit:** e1e25ff

**7. [Rule 1 - Bug] Fixed contest double-append on level-2 heading termination**
- **Found during:** Task 2, step 6 (import - CardinalityViolation)
- **Issue:** Whitfield county file produced 2 identical records; parser appended last contest twice when level-2 heading ended the contests section
- **Fix:** Set `current_contest = None` before `break` in `_extract_contests`
- **Files modified:** src/voter_api/lib/converter/parser.py
- **Commit:** e1e25ff

**8. [Rule 1 - Bug] Fixed softbreak token rendering in text extraction**
- **Found during:** Task 2, step 6 (seat_id parsed as "ward-2Name" instead of "ward-2")
- **Issue:** `_extract_text_from_children` ignored softbreak tokens, causing adjacent lines to concatenate without separator
- **Fix:** Added softbreak/linebreak/hardbreak handling to append "\n"
- **Files modified:** src/voter_api/lib/converter/parser.py
- **Commit:** e1e25ff

**9. [Rule 1 - Bug] Fixed ElectionType literal too narrow for JSONL types**
- **Found during:** Task 2, step 8 (API verification)
- **Issue:** API response model's ElectionType was `Literal["special","general","primary","runoff"]` -- rejected `general_primary` from DB causing serialization error
- **Fix:** Expanded literal in election_tracker/ingester.py to include JSONL types
- **Files modified:** src/voter_api/lib/election_tracker/ingester.py
- **Commit:** e1e25ff

**10. [Rule 2 - Missing functionality] Added link import in JSONL candidate pipeline**
- **Found during:** Task 2, step 8 (candidate API verification showed 0 links)
- **Issue:** `import_candidates_jsonl` imported person fields but not candidate links from JSONL
- **Fix:** Added link extraction loop in `import_candidates_jsonl` calling existing `_upsert_candidate_links`
- **Files modified:** src/voter_api/services/candidate_import_service.py
- **Commit:** e1e25ff

**11. [Rule 1 - Bug] Fixed email field missing from candidate detail API response**
- **Found during:** Task 2, step 8 (candidate API returned email=None despite DB having value)
- **Issue:** `build_candidate_detail_response` passed all candidate fields to response model except `email`
- **Fix:** Added `email=candidate.email` to `CandidateDetailResponse` constructor call
- **Files modified:** src/voter_api/services/candidate_service.py
- **Commit:** e1e25ff

**12. [Rule 1 - Bug] Fixed mock candidate missing email in tests**
- **Found during:** Post-fix test run
- **Issue:** Test mock factories in unit and integration tests didn't set `email=None`, causing MagicMock → ValidationError when email was added to response
- **Fix:** Added `email: None` to both mock factory defaults
- **Files modified:** tests/unit/test_services/test_candidate_service.py, tests/integration/test_api/test_candidate_api.py
- **Commit:** e1e25ff

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 76b9c7b | test(04-01) | add failing test for election_event_id placeholder handling |
| fa5011e | feat(04-01) | nullify placeholder UUID in election import service |
| e1e25ff | feat(04-01) | complete end-to-end election pipeline for all three elections |

## Self-Check: PASSED
