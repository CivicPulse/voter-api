---
phase: 01-data-contracts
verified: 2026-03-14T02:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 1: Data Contracts Verification Report

**Phase Goal:** All intermediate data formats are fully specified so converter, importer, and skills can be built against stable contracts
**Verified:** 2026-03-14
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A markdown file following the enhanced format spec can represent any Georgia contest with its district linkage (boundary_type + district_identifier), and the format is documented with examples | VERIFIED | `single-contest.md` has Body/Seat metadata in all three format variants; `multi-contest.md` has per-contest `**Body:** {id} \| **Seat:** {id}` lines; `county-reference.md` defines Governing Bodies table; `boundary-types.md` documents all 18 values and the Body/Seat resolution flow |
| 2 | A markdown file following the enhanced format spec includes election metadata (early voting, registration deadline, absentee deadline) and candidate details (party, photo URL, bio, contact info, external IDs) | VERIFIED | `election-overview.md` has Calendar table with Registration Deadline, Early Voting Start/End, Absentee Request Deadline, Qualifying Period Start/End; `candidate-file.md` has Photo URL, Email, Bio, External IDs table, Links table, and election-keyed sections with Party and Filing Status |
| 3 | JSONL schema definitions for elections and candidates exist with field-level documentation, and every field maps 1:1 to the corresponding DB model column | VERIFIED | 4 Pydantic models exist: `ElectionEventJSONL` (14 fields), `ElectionJSONL` (21 fields), `CandidateJSONL` (10 fields + embedded CandidateLinkJSONL), `CandidacyJSONL` (12 fields); every field has `description=` annotation; `docs/formats/jsonl/` auto-generated docs render field tables with type, required/optional, default, and description |
| 4 | JSONL files include a `schema_version` field and the schema documents how version changes are handled | VERIFIED | All 4 models have `schema_version: int = Field(default=1, ...)` present and serialized; REQUIREMENTS.md FMT-06 requires `schema_version` (no underscore, matching Pydantic v2 semantics); all 4 auto-generated JSONL docs state "All records include a `schema_version` field (default: `1`) for forward compatibility" |

**Score:** 4/4 success criteria verified

---

### Plan-Level Must-Haves

#### Plan 01-01: Controlled Vocabularies and Markdown Format Specs

| Truth | Status | Evidence |
|-------|--------|----------|
| Every contest type has a documented format with Body/Seat district linkage fields | VERIFIED | `single-contest.md` covers statewide/partisan, non-partisan/general, and special election variants — all include Body and Seat metadata table rows |
| Election overview format includes calendar date fields | VERIFIED | `election-overview.md` Calendar table has 7 rows: Registration Deadline, Early Voting Start/End, Absentee Request Deadline, Qualifying Period Start/End, Election Day |
| Candidate file format includes person-level fields | VERIFIED | `candidate-file.md` has Photo URL, Email, Bio, External IDs table, Links table (with LinkType vocabulary), and election-keyed sections |
| All five controlled vocabularies are documented with exact values matching DB constraints | VERIFIED | election-types.md (5 types + 3 stages), boundary-types.md (18 values from BOUNDARY_TYPES), filing-status.md (4 values from FilingStatus StrEnum), link-types.md (8 values from LinkType StrEnum), seat-ids.md (5 slug patterns + Body ID convention) |
| Every markdown file type requires ID (UUID) and Format Version rows | VERIFIED | `election-overview.md`, `single-contest.md`, `multi-contest.md`, `candidate-file.md`, `county-reference.md` all include `\| ID \| {uuid} \|` and `\| Format Version \| 1 \|` rows with "Converter error if missing" documented |

#### Plan 01-02: JSONL Pydantic Schema Models

| Truth | Status | Evidence |
|-------|--------|----------|
| ElectionEventJSONL validates a complete election event record with calendar date fields and schema_version | VERIFIED | Model exists in `election_event.py`; has registration_deadline, early_voting_start/end, absentee_request_deadline, qualifying_start/end as optional date fields; schema_version defaults to 1; 68 tests pass |
| ElectionJSONL validates a complete election contest record with election_type, election_stage, and boundary fields but NO calendar date fields | VERIFIED | Model exists in `election.py`; has election_type (required), election_stage (default: "election"), boundary_type, district_identifier; confirmed no calendar fields present; 68 tests pass |
| CandidateJSONL validates a person entity record (no election_id) with bio, photo_url, email, and external IDs | VERIFIED | Model exists in `candidate.py`; has bio, photo_url, email, home_county, municipality, links, external_ids; no election_id field; 68 tests pass |
| CandidacyJSONL validates a junction record linking a candidate UUID to an election UUID | VERIFIED | Model exists in `candidacy.py`; has candidate_id, election_id, party, filing_status (default: qualified), is_incumbent, occupation, qualified_date, ballot_order; 68 tests pass |
| All four models have a schema_version field (no underscore prefix) defaulting to 1 | VERIFIED | All 4 models have `schema_version: int = Field(default=1, ...)` — underscore-prefix would make it a private Pydantic v2 attribute excluded from serialization, a decision explicitly documented in the plan and summary |
| All four models reject invalid enum values | VERIFIED | enums.py defines ElectionType (5), ElectionStage (3), FilingStatus (4), LinkType (8), BoundaryType (18) as StrEnums; Pydantic validation enforced; tests confirm invalid values raise ValidationError |

#### Plan 01-03: Doc Generation, Bibb Example, Process Specs

| Truth | Status | Evidence |
|-------|--------|----------|
| Running the JSONL doc generation script produces markdown docs from model_json_schema() output | VERIFIED | `tools/generate_jsonl_docs.py` exists (342 lines); imports from `voter_api.schemas.jsonl`; 4 generated docs exist in `docs/formats/jsonl/` with auto-generated notice and field tables |
| Each JSONL doc lists every field with type, required/optional, default, and description | VERIFIED | election-events.md shows 14 rows with Field/Type/Required/Default/Description columns; elections.md shows schema_version + election_type + election_stage + boundary fields; all match Pydantic models |
| Bibb county reference file has a complete Governing Bodies table covering all 12 contests | VERIFIED | `data/states/GA/counties/bibb.md` has 5-row Governing Bodies table: bibb-boe (school_board), bibb-civil-magistrate (judicial/sole), bibb-superior-court (judicial/judge-{surname}), bibb-state-court (judicial/judge-{surname}), macon-water-authority (water_board) — covers all 12 Bibb contests |
| UUID strategy, backfill rules, and migration rules are concrete enough for Phase 2 | VERIFIED | uuid-strategy.md has 7 "validation error/emit error" phrases; backfill-rules.md has 5 "natural key" phrases and 3 "emit error" phrases; migration-rules.md has 4 "emit" error/warning phrases and 21 "Body" references with concrete per-file-type rules |
| The data/candidates/ directory exists for global candidate files | VERIFIED | `data/candidates/.gitkeep` exists |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `docs/formats/vocabularies/election-types.md` | election_type + election_stage vocabulary | VERIFIED | 5 election_type values, 3 election_stage values, priority rule, event vs contest semantics documented |
| `docs/formats/vocabularies/boundary-types.md` | boundary_type values from DB BOUNDARY_TYPES | VERIFIED | All 18 values present, grouped by scope (federal/state/county/municipal); Body/Seat resolution flow documented; `county_commission` present |
| `docs/formats/vocabularies/filing-status.md` | Filing status vocabulary | VERIFIED | 4 values (`qualified`, `withdrawn`, `disqualified`, `write_in`) with SOS CSV mapping table |
| `docs/formats/vocabularies/link-types.md` | Candidate link type vocabulary | VERIFIED | 8 values including `campaign`; usage guidance; design decision on candidate-file-only placement |
| `docs/formats/vocabularies/seat-ids.md` | Seat ID slug patterns | VERIFIED | 5 patterns (sole, at-large, post-N, district-N, judge-{surname}); Body ID naming convention; `post-N` pattern documented |
| `docs/formats/markdown/election-overview.md` | Unified overview format spec | VERIFIED | Contains `Format Version` row; Calendar section; all 7 date fields; optional sections list |
| `docs/formats/markdown/single-contest.md` | Statewide + special election format | VERIFIED | Contains `Body` and `Seat` metadata rows; 3 structure variants; 5-column candidate table with no Email/Website |
| `docs/formats/markdown/multi-contest.md` | County-grouped local races format | VERIFIED | Contains `Body` and `Seat` per-contest metadata line; Format Version row; 5-column candidate table |
| `docs/formats/markdown/candidate-file.md` | Global candidate file format | VERIFIED | Contains `External IDs` section; `Links` table; election-keyed sections; Photo URL, Email, Bio fields |
| `docs/formats/markdown/county-reference.md` | County reference with Governing Bodies | VERIFIED | Contains `Governing Bodies` table with Body ID, Name, boundary_type, Seat Pattern, Notes columns |
| `src/voter_api/schemas/jsonl/__init__.py` | Public API exports | VERIFIED | Exports ElectionEventJSONL, ElectionJSONL, CandidateJSONL, CandidacyJSONL, CandidateLinkJSONL, and all 5 enums |
| `src/voter_api/schemas/jsonl/enums.py` | StrEnum definitions | VERIFIED | ElectionType (5), ElectionStage (3), FilingStatus (4), LinkType (8), BoundaryType (18) |
| `src/voter_api/schemas/jsonl/election_event.py` | ElectionEventJSONL Pydantic model | VERIFIED | schema_version, id, event_date, event_name, event_type, 3 calendar fields, 3 feed fields; all with descriptions |
| `src/voter_api/schemas/jsonl/election.py` | ElectionJSONL Pydantic model | VERIFIED | schema_version, id, election_event_id, name, name_sos, election_date, election_type, election_stage, boundary fields; NO calendar fields |
| `src/voter_api/schemas/jsonl/candidate.py` | CandidateJSONL Pydantic model | VERIFIED | schema_version, id, full_name; person-level fields (bio, photo_url, email, home_county, municipality, links, external_ids); NO election_id |
| `src/voter_api/schemas/jsonl/candidacy.py` | CandidacyJSONL Pydantic model | VERIFIED | schema_version, id, candidate_id, election_id; contest fields (party, filing_status, is_incumbent, occupation, qualified_date, ballot_order, sos_ballot_option_id, contest_name) |
| `tests/unit/test_schemas/test_jsonl_schemas.py` | Unit tests for all four JSONL models | VERIFIED | 671 lines; 68 tests — all pass |
| `tools/generate_jsonl_docs.py` | Script generating markdown docs from Pydantic schemas | VERIFIED | 342 lines; imports from voter_api.schemas.jsonl; renders field tables with type/required/default/description |
| `docs/formats/jsonl/election-events.md` | Auto-generated ElectionEventJSONL field documentation | VERIFIED | `schema_version` field listed; all 14 fields with type/required/default/description; enum definitions section |
| `docs/formats/jsonl/elections.md` | Auto-generated ElectionJSONL field documentation | VERIFIED | `election_type` field listed; `election_stage` with default "election"; boundary_type and district_identifier present |
| `docs/formats/jsonl/candidates.md` | Auto-generated CandidateJSONL field documentation | VERIFIED | `full_name` field listed; all person-level fields; no election_id |
| `docs/formats/jsonl/candidacies.md` | Auto-generated CandidacyJSONL field documentation | VERIFIED | `candidate_id` field listed; `election_id` field listed; filing_status with default |
| `data/states/GA/counties/bibb.md` | Complete Bibb county reference with governing bodies | VERIFIED | Governing Bodies table with 5 rows covering all 12 Bibb contests; bibb-boe, bibb-civil-magistrate, bibb-superior-court, bibb-state-court, macon-water-authority |
| `docs/formats/specs/uuid-strategy.md` | UUID embedding and management rules | VERIFIED | "validation error" present 7 times; strict validation-error-on-missing rule; UUID lifecycle documented |
| `docs/formats/specs/backfill-rules.md` | Rules for matching DB records to markdown files | VERIFIED | "natural key" present 5 times; matching rules for ElectionEvent, Election, Candidate; backfill order documented |
| `docs/formats/specs/migration-rules.md` | Rules for migrating ~200 existing markdown files | VERIFIED | "Body" present 21 times; per-file-type rules (overview, single-contest, multi-contest, special, candidate stubs); references `multi-contest.md` format |
| `data/candidates/.gitkeep` | Directory placeholder for global candidate files | VERIFIED | File exists |

---

### Key Link Verification

#### Plan 01-01 Links

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `docs/formats/markdown/single-contest.md` | `docs/formats/vocabularies/boundary-types.md` | Body/Seat metadata references boundary_type values | VERIFIED | Pattern `boundary_type` found at lines 149 and 152 — references boundary-types vocabulary with direct link |
| `docs/formats/markdown/multi-contest.md` | `docs/formats/markdown/county-reference.md` | Body IDs resolved via county reference governing bodies | VERIFIED | Pattern `Body.*Seat` found in per-contest metadata line; cross-reference section links to county-reference |
| `docs/formats/markdown/election-overview.md` | `docs/formats/vocabularies/election-types.md` | Election type and stage values from vocabulary | VERIFIED | Pattern `election_type` found at lines 30 and 100 (validation checklist); Type field references election-types vocabulary via link |

#### Plan 01-02 Links

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `src/voter_api/schemas/jsonl/election.py` | `src/voter_api/schemas/jsonl/enums.py` | ElectionJSONL imports ElectionType and ElectionStage enums | VERIFIED | `from voter_api.schemas.jsonl.enums import ElectionStage, ElectionType` at line 15 |
| `src/voter_api/schemas/jsonl/candidacy.py` | `src/voter_api/schemas/jsonl/enums.py` | CandidacyJSONL imports FilingStatus enum | VERIFIED | `from voter_api.schemas.jsonl.enums import FilingStatus` at line 16 |
| `src/voter_api/schemas/jsonl/__init__.py` | `src/voter_api/schemas/jsonl/election_event.py` | Re-exports all four JSONL models | VERIFIED | `from voter_api.schemas.jsonl.election_event import ElectionEventJSONL` at line 13 |

#### Plan 01-03 Links

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tools/generate_jsonl_docs.py` | `src/voter_api/schemas/jsonl/__init__.py` | Imports all four JSONL models and calls model_json_schema() | VERIFIED | `from voter_api.schemas.jsonl import (  # noqa: E402` at line 22 |
| `docs/formats/specs/migration-rules.md` | `docs/formats/markdown/multi-contest.md` | Migration rules reference enhanced multi-contest format | VERIFIED | `multi-contest.md` found at line 10 of migration-rules.md |
| `data/states/GA/counties/bibb.md` | `docs/formats/markdown/county-reference.md` | Bibb file follows the county reference format spec | VERIFIED | Governing Bodies table at line 13 uses identical column structure as the county-reference format spec |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| FMT-01 | 01-01, 01-03 | Enhanced markdown format spec includes district linkage fields (boundary_type + district_identifier) for every contest | SATISFIED | Body/Seat metadata rows in single-contest.md and multi-contest.md; Governing Bodies table in county-reference.md; boundary-types.md documents the 18 DB values |
| FMT-02 | 01-01, 01-03 | Enhanced markdown format spec includes election metadata (early voting start/end, registration deadline, absentee deadline) per election | SATISFIED | election-overview.md Calendar table includes Registration Deadline, Early Voting Start, Early Voting End, Absentee Request Deadline, Qualifying Period Start/End, Election Day |
| FMT-03 | 01-01, 01-03 | Enhanced markdown format spec includes candidate details (party, photo URL, bio, contact info, external IDs) per candidate | SATISFIED | candidate-file.md includes Photo URL, Email, Bio, External IDs table, Links table (with link-types.md vocabulary); election-keyed sections include Party, Occupation, Filing Status, Is Incumbent |
| FMT-04 | 01-02, 01-03 | JSONL schema for elections mirrors the Election DB model with all required and optional fields documented | SATISFIED | ElectionJSONL has all DB Election columns as documented fields; auto-generated elections.md documents 21 fields; schema mirrors target Election DB model (post-Phase 2 migration) as specified in the plan |
| FMT-05 | 01-02, 01-03 | JSONL schema for candidates mirrors the Candidate DB model with all required and optional fields documented | SATISFIED | CandidateJSONL (person entity) + CandidacyJSONL (junction) together mirror the target Candidate/Candidacy model split; auto-generated candidates.md and candidacies.md document all fields |
| FMT-06 | 01-02, 01-03 | JSONL files include a `schema_version` field for forward compatibility | SATISFIED | All 4 JSONL models have `schema_version: int = Field(default=1, ...)` — named `schema_version` (no underscore) per Pydantic v2 requirements; note: REQUIREMENTS.md itself uses `schema_version` (no underscore), matching the implementation |

**Coverage:** 6/6 Phase 1 requirements satisfied. No orphaned requirements.

---

### Anti-Patterns Found

No anti-patterns detected in Phase 1 deliverables.

- Vocabulary docs are substantive (not placeholders): each documents all values with descriptions, examples, and usage guidance
- Markdown format specs are substantive: each includes complete structure examples, field reference tables, content rules, and validation checklists
- Pydantic models are substantive: all fields have `description=` annotations; no empty implementations
- JSONL doc generation script is substantive: 342 lines; reads model_json_schema(); renders complete field tables with enum definitions and example records
- Tests are substantive: 671 lines; 68 tests covering valid records, defaults, invalid enum rejection, optional fields, schema generation, and cross-cutting behavior

**One naming note (not a gap):** The ROADMAP success criterion 4 references `_schema_version` (with underscore) but the implementation uses `schema_version` (no underscore). This is correct: REQUIREMENTS.md FMT-06 says `schema_version` (no underscore), and Plan 02's implementation notes explicitly document that Pydantic v2 treats underscore-prefixed fields as private attributes excluded from serialization. The ROADMAP wording was a draft artifact that was superseded by the plan.

---

### Human Verification Required

None. All Phase 1 deliverables are documentation and Pydantic schema code — fully verifiable by reading files and running tests. No UI behavior, real-time behavior, or external service integration to verify.

---

## Gaps Summary

No gaps. All 9 plan must-haves are verified, all 4 ROADMAP success criteria are satisfied, all 6 requirements (FMT-01 through FMT-06) are satisfied. The phase goal is achieved: all intermediate data formats are fully specified with stable, complete contracts that the Phase 2 converter, importer, and Phase 3 skills can be built against.

**Total docs/formats artifacts:** 17 markdown files (5 vocabulary + 5 markdown format specs + 4 JSONL field docs + 3 process specs) — matches the expected count in Plan 03's success criteria.

**Test suite:** 68 tests, all passing, covering all four JSONL Pydantic models.

---

_Verified: 2026-03-14_
_Verifier: Claude (gsd-verifier)_
