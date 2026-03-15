---
phase: 01-data-contracts
plan: 01
subsystem: docs
tags: [markdown, vocabulary, election-types, boundary-types, filing-status, link-types, seat-ids, data-contracts]

# Dependency graph
requires:
  - phase: none
    provides: first plan in first phase
provides:
  - five controlled vocabulary documents (election-types, boundary-types, filing-status, link-types, seat-ids)
  - five enhanced markdown format specifications (election-overview, single-contest, multi-contest, candidate-file, county-reference)
  - Body/Seat reference system documented with worked Bibb County example
  - candidate table reduced to 5 columns (Email/Website dropped to candidate file)
affects: [01-02-PLAN, 01-03-PLAN, phase-2-converter, phase-3-skills]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Body/Seat metadata for district linkage in contest files"
    - "Per-contest metadata line format: **Body:** {id} | **Seat:** {id}"
    - "UUID + Format Version required in all markdown file metadata tables"
    - "Two-field election classification: election_type + election_stage"
    - "Governing Bodies table in county reference files for Body ID to boundary_type resolution"

key-files:
  created:
    - docs/formats/vocabularies/election-types.md
    - docs/formats/vocabularies/boundary-types.md
    - docs/formats/vocabularies/filing-status.md
    - docs/formats/vocabularies/link-types.md
    - docs/formats/vocabularies/seat-ids.md
    - docs/formats/markdown/election-overview.md
    - docs/formats/markdown/single-contest.md
    - docs/formats/markdown/multi-contest.md
    - docs/formats/markdown/candidate-file.md
    - docs/formats/markdown/county-reference.md
  modified: []

key-decisions:
  - "Seat ID patterns decided: sole, at-large, post-N, district-N, judge-{surname} -- all lowercase with hyphens, unpadded numbers"
  - "Body ID naming: {scope}-{body} with ga- prefix for statewide, county name for county-level, municipality name for municipal-level"
  - "Judicial seat IDs use incumbent surname (judge-hanson) -- expected to change when judges change, matching SOS conventions"
  - "Bibb magistrate court uses sole seat pattern (single-judge court)"

patterns-established:
  - "Vocabulary docs reference authoritative code source and state they reflect Phase 1 snapshot"
  - "Format specs include validation checklists for human/automated review"
  - "Format specs cross-reference vocabulary docs via relative links"

requirements-completed: [FMT-01, FMT-02, FMT-03]

# Metrics
duration: 5min
completed: 2026-03-14
---

# Phase 1 Plan 01: Controlled Vocabularies and Markdown Format Specs Summary

**Five controlled vocabularies and five enhanced markdown format specifications defining all human-readable data contracts for the election data pipeline**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-14T00:49:55Z
- **Completed:** 2026-03-14T00:55:28Z
- **Tasks:** 2
- **Files created:** 10

## Accomplishments

- Defined all five controlled vocabularies matching existing DB constraints and CONTEXT decisions: election types (5 types + 3 stages), boundary types (18 values), filing status (4 values with SOS mapping), link types (8 values), and seat ID patterns (5 slug patterns + Body ID naming convention)
- Created five enhanced markdown format specs that replace the four existing specs in `data/elections/formats/`, adding UUID/Format Version requirements, Body/Seat district linkage, calendar date fields, and reduced candidate table columns
- Documented the complete Body/Seat resolution flow with a worked Bibb County example covering all 12 contest types (BOE at-large, BOE district, commission, superior court, state court, magistrate court, water authority at-large, water authority district)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create controlled vocabulary documentation** - `4383a38` (docs)
2. **Task 2: Create enhanced markdown format specifications** - `2e99c8d` (docs)

## Files Created/Modified

- `docs/formats/vocabularies/election-types.md` - Election type + stage two-field vocabulary with priority rule
- `docs/formats/vocabularies/boundary-types.md` - All 18 boundary types grouped by scope
- `docs/formats/vocabularies/filing-status.md` - Filing status values with SOS CSV mapping
- `docs/formats/vocabularies/link-types.md` - Candidate link type vocabulary with usage guidance
- `docs/formats/vocabularies/seat-ids.md` - Seat ID slug patterns and Body ID naming convention
- `docs/formats/markdown/election-overview.md` - Unified overview format with calendar dates and SOS feed URL
- `docs/formats/markdown/single-contest.md` - Unified statewide + special election format with Body/Seat
- `docs/formats/markdown/multi-contest.md` - County-grouped format with per-contest Body/Seat metadata line
- `docs/formats/markdown/candidate-file.md` - Global candidate file format with External IDs, Links, election sections
- `docs/formats/markdown/county-reference.md` - County reference with Governing Bodies table and Bibb example

## Decisions Made

- **Seat ID patterns locked down:** `sole` (single-seat), `at-large` (unnumbered at-large), `post-N` (numbered post), `district-N` (district seat), `judge-{surname}` (judicial by incumbent name). All lowercase, hyphens, unpadded numbers.
- **Bibb magistrate court uses `sole` seat pattern:** The Civil/Magistrate Court of Bibb County is a single-judge court, unlike the multi-judge Superior Court and State Court.
- **Body ID scoping convention:** `ga-` prefix for statewide/federal, county name for county-level (e.g., `bibb-boe`), municipality name for municipal-level (e.g., `macon-water-authority`).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All controlled vocabularies are defined and ready for use by Plan 01-02 (JSONL Pydantic schema models) and Plan 01-03 (Bibb example, process specs)
- Format specs are complete and can serve as the contract for the Phase 2 converter and Phase 3 Claude skills
- The existing format specs in `data/elections/formats/` remain in place for reference until Phase 2 migration

## Self-Check: PASSED

All 10 created files verified present. Both task commits (4383a38, 2e99c8d) verified in git history.

---
*Phase: 01-data-contracts*
*Completed: 2026-03-14*
