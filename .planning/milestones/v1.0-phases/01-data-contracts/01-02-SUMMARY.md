---
phase: 01-data-contracts
plan: 02
subsystem: schemas
tags: [pydantic-v2, jsonl, strenum, data-contracts, tdd]

# Dependency graph
requires:
  - phase: none
    provides: n/a
provides:
  - ElectionEventJSONL Pydantic model (election day grouping with calendar/feed fields)
  - ElectionJSONL Pydantic model (individual contest with election_type + election_stage)
  - CandidateJSONL Pydantic model (person entity, no election_id)
  - CandidacyJSONL Pydantic model (candidate-election junction with contest fields)
  - CandidateLinkJSONL embedded model (typed URLs)
  - StrEnum definitions for ElectionType, ElectionStage, FilingStatus, LinkType, BoundaryType
  - model_json_schema() support on all 4 models for doc auto-generation
affects: [01-03, 02-converter, 02-importer, 03-skills]

# Tech tracking
tech-stack:
  added: []
  patterns: [self-contained JSONL schema package in src/voter_api/schemas/jsonl/, StrEnum for controlled vocabularies, Field(description=...) on every field for doc generation]

key-files:
  created:
    - src/voter_api/schemas/jsonl/__init__.py
    - src/voter_api/schemas/jsonl/enums.py
    - src/voter_api/schemas/jsonl/election_event.py
    - src/voter_api/schemas/jsonl/election.py
    - src/voter_api/schemas/jsonl/candidate.py
    - src/voter_api/schemas/jsonl/candidacy.py
    - tests/unit/test_schemas/test_jsonl_schemas.py
  modified: []

key-decisions:
  - "JSONL schemas mirror target DB model (post-Phase 2 migration), not current DB model"
  - "Self-contained enums in schemas/jsonl/enums.py rather than importing from schemas/candidate.py"
  - "schema_version field (no underscore prefix) for Pydantic v2 compatibility"
  - "ElectionJSONL includes all Election model columns except calendar fields (moved to ElectionEventJSONL)"
  - "boundary_type on ElectionJSONL is a plain string, not BoundaryType enum, for flexibility with future boundary types"

patterns-established:
  - "JSONL Pydantic model pattern: BaseModel with Field(description=...) on every field, schema_version defaulting to 1"
  - "Self-contained schema package: all imports within src/voter_api/schemas/jsonl/ without depending on other schema modules"
  - "TDD for data contract models: write failing tests first, then implement, verify with ruff lint"

requirements-completed: [FMT-04, FMT-05, FMT-06]

# Metrics
duration: 4min
completed: 2026-03-14
---

# Phase 1 Plan 2: JSONL Schema Models Summary

**Four Pydantic v2 JSONL data contract models (ElectionEvent, Election, Candidate, Candidacy) with 5 StrEnum vocabularies and 68 TDD tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-14T00:49:52Z
- **Completed:** 2026-03-14T00:54:48Z
- **Tasks:** 2 (TDD RED + GREEN)
- **Files created:** 7

## Accomplishments

- Created 4 JSONL Pydantic models defining the machine-readable data contracts for election data import
- Created 5 StrEnum definitions (ElectionType, ElectionStage, FilingStatus, LinkType, BoundaryType) as controlled vocabulary source of truth
- Wrote 68 comprehensive tests covering valid records, defaults, enum validation, optional fields, model_json_schema() output, and cross-cutting schema_version behavior
- All models produce valid JSON Schema via model_json_schema() with descriptions on every field, ready for plan 03 doc auto-generation

## Task Commits

Each task was committed atomically:

1. **TDD RED: Failing tests** - `a3bcd16` (test)
2. **TDD GREEN: Implementation** - `c948359` (feat)

_TDD plan: tests written first (RED), then implementation to make them pass (GREEN). No refactor step needed._

## Files Created/Modified

- `src/voter_api/schemas/jsonl/__init__.py` - Public API exports for all JSONL schema models and enums
- `src/voter_api/schemas/jsonl/enums.py` - StrEnum definitions: ElectionType (5), ElectionStage (3), FilingStatus (4), LinkType (8), BoundaryType (18)
- `src/voter_api/schemas/jsonl/election_event.py` - ElectionEventJSONL model with calendar and feed fields
- `src/voter_api/schemas/jsonl/election.py` - ElectionJSONL model with election_type + election_stage, no calendar fields
- `src/voter_api/schemas/jsonl/candidate.py` - CandidateJSONL (person entity, no election_id) + CandidateLinkJSONL
- `src/voter_api/schemas/jsonl/candidacy.py` - CandidacyJSONL (candidate-election junction with contest fields)
- `tests/unit/test_schemas/test_jsonl_schemas.py` - 68 unit tests for all models, enums, and cross-cutting behavior

## Decisions Made

- **Target model, not current model:** JSONL schemas define the post-Phase 2 data model. CandidateJSONL has no election_id (person entity), CandidacyJSONL is the junction. ElectionJSONL has no calendar fields (moved to ElectionEventJSONL).
- **Self-contained package:** Enums defined independently in schemas/jsonl/enums.py rather than importing from schemas/candidate.py, keeping the JSONL package usable without the rest of the application.
- **String boundary_type:** ElectionJSONL uses `str | None` for boundary_type instead of BoundaryType enum, providing flexibility if new boundary types are added before the enum is updated.
- **schema_version naming:** Named `schema_version` (no underscore) per Pydantic v2 requirements. Underscore-prefixed fields are private attributes excluded from serialization and JSON Schema.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- JSONL schema models ready for plan 03 (doc auto-generation from model_json_schema())
- JSONL schema models ready for Phase 2 converter (validates JSONL output) and importer (deserializes JSONL input)
- All 4 models have complete Field descriptions enabling automatic markdown documentation generation
- BoundaryType enum mirrors BOUNDARY_TYPES from models/boundary.py for vocabulary consistency

## Self-Check: PASSED

- All 7 created files verified on disk
- Both task commits (a3bcd16, c948359) verified in git log
- 68 tests pass, lint clean

---
*Phase: 01-data-contracts*
*Completed: 2026-03-14*
