# Tasks: Voter History Ingestion

**Input**: Design documents from `/specs/006-voter-history/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/openapi.yaml, quickstart.md

**Tests**: Required by constitution (Principle III: Testing Discipline, 90% coverage threshold).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Database migration and schema changes that enable all subsequent work.

- [X] T001 Create Alembic migration `022_voter_history.py` in `alembic/versions/` — creates `voter_history` table (all columns including `normalized_election_type` VARCHAR(20) NOT NULL, constraints, indexes per data-model.md), adds `creation_method` column (VARCHAR(20), NOT NULL, server_default `'manual'`) to `elections` table with index, adds `records_skipped` and `records_unmatched` nullable INTEGER columns to `import_jobs` table

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: ORM models and Pydantic schemas that ALL user stories depend on.

**CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Create `VoterHistory` ORM model in `src/voter_api/models/voter_history.py` — all columns from data-model.md (including `normalized_election_type` VARCHAR(20) NOT NULL), `UUIDMixin`/`TimestampMixin`, FK to `import_jobs.id` with CASCADE, unique constraint on `(voter_registration_number, election_date, election_type)`, all indexes (note: `idx_voter_history_date_type` uses `(election_date, normalized_election_type)` for election joins)
- [X] T003 [P] Add `creation_method` field to `Election` model in `src/voter_api/models/election.py` — `mapped_column(String(20), nullable=False, server_default="manual")`, add to `__table_args__` index
- [X] T004 [P] Add `records_skipped` and `records_unmatched` fields to `ImportJob` model in `src/voter_api/models/import_job.py` — nullable `Integer` columns matching existing counter pattern. Also ensure `'voter_history'` is a valid `file_type` value and `'superseded'` is a valid `status` value (check for any enum/validator constraints on these fields in the model and schema layers)
- [X] T005 [P] Create Pydantic v2 schemas in `src/voter_api/schemas/voter_history.py` — `VoterHistoryRecord`, `PaginatedVoterHistoryResponse`, `ElectionParticipationRecord`, `PaginatedElectionParticipationResponse`, `CountyBreakdown`, `BallotStyleBreakdown`, `ParticipationStatsResponse`, `ParticipationSummary` per contracts/openapi.yaml; all with `model_config = {"from_attributes": True}` (note: schema names match OpenAPI contract names exactly)
- [X] T006 Register `VoterHistory` model import in `src/voter_api/models/__init__.py`

**Checkpoint**: Foundation ready — all models and schemas in place, migration applied, user story implementation can begin.

---

## Phase 3: User Story 1 — Import Voter Participation History (Priority: P1) MVP

**Goal**: Admin imports a GA SoS voter history CSV; records are parsed, stored in `voter_history`, and an import summary is generated. Re-importing the same file atomically replaces previous records.

**Independent Test**: Import a sample voter history CSV via CLI or API and verify records appear in the database with correct field values; re-import the same file and verify old records are replaced.

**Acceptance criteria**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-012, FR-013, FR-014, FR-015, FR-016, FR-018, FR-019, FR-021

### Implementation for User Story 1

- [X] T007 [P] [US1] Create voter history CSV parser library in `src/voter_api/lib/voter_history/parser.py` — column map for 9-column GA SoS format, `parse_voter_history_chunks()` generator using Pandas `read_csv(chunksize=...)`, date parsing (MM/DD/YYYY), boolean coercion ("Y"→True, blank→False per FR-018/FR-019), `map_election_type()` to populate `normalized_election_type` per research.md section 7 mapping table, delimiter/encoding auto-detection following existing `lib/importer/parser.py` pattern
- [X] T008 [P] [US1] Create `__init__.py` public API exports in `src/voter_api/lib/voter_history/__init__.py` — export `parse_voter_history_chunks`, column map constant, and any validation helpers
- [X] T009 [US1] Implement `process_voter_history_import()` in `src/voter_api/services/voter_history_service.py` — chunk-by-chunk processing, batch upsert via ON CONFLICT on `(voter_registration_number, election_date, election_type)` (upsert updates `import_job_id` to the new job for matching records), unmatched voter detection (LEFT JOIN to `voters` table), duplicate tracking within file, progress tracking via `last_processed_offset`, error logging to `error_log` JSONB
- [X] T010 [US1] Implement atomic re-import logic in `src/voter_api/services/voter_history_service.py` — find previous completed import jobs by `file_name` + `file_type='voter_history'`, after successful import delete `voter_history` records still associated with old `import_job_id` (records that were in the previous file but not the new one — records with matching natural keys had their `import_job_id` updated to the new job during T009 upsert), mark old jobs as `'superseded'`; auto-created elections from previous imports are NOT deleted (FR-021)
- [X] T011 [US1] Add `POST /api/v1/imports/voter-history` endpoint in `src/voter_api/api/v1/imports.py` — `UploadFile` parameter, `require_role("admin")` auth, file size validation, write to temp file, create `ImportJob` with `file_type='voter_history'`, submit background task via `task_runner.submit_task()`, return 202 with `ImportJobResponse`
- [X] T012 [US1] Update `ImportJobResponse` schema in `src/voter_api/schemas/imports.py` to include `records_skipped` and `records_unmatched` fields
- [X] T013 [US1] Create CLI command `voter-history` in `src/voter_api/cli/voter_history_cmd.py` — Typer command accepting `file: Path` argument and `--batch-size` option, sync wrapper around async import, progress output via `typer.echo()`, summary display on completion, following `cli/import_cmd.py` pattern
- [X] T014 [US1] Register CLI command in `src/voter_api/cli/import_cmd.py` — add `voter_history_cmd.voter_history_app` as subcommand under `import` group via `app.add_typer()` in `_register_subcommands()`

### Tests for User Story 1

- [X] T015 [P] [US1] Write unit tests for parser in `tests/unit/lib/test_voter_history/test_parser.py` — test column mapping, date parsing (valid MM/DD/YYYY, invalid formats), boolean coercion ("Y"/"N"/blank), chunked reading, empty file handling, missing required fields, encoding detection
- [X] T016 [P] [US1] Write unit tests for schemas in `tests/unit/test_schemas/test_voter_history_schemas.py` — test all Pydantic schemas from_attributes, field defaults, nullable fields, computed fields if any
- [X] T017 [US1] Write integration tests for import service in `tests/integration/test_voter_history_import.py` — test successful import (verify DB records), re-import replacement (verify old records deleted, new records present, old job superseded), unmatched voter tracking, duplicate handling within file, large batch processing, error handling for corrupt records
- [X] T018 [US1] Write integration tests for import API endpoint in `tests/integration/test_voter_history_api.py` — test POST /imports/voter-history returns 202, auth enforcement (admin required), invalid file rejection, import job status tracking
- [X] T019 [US1] Write integration test for CLI import in `tests/integration/test_voter_history_cli.py` — test `import voter-history` command with sample file, verify output summary

**Checkpoint**: User Story 1 complete — admin can import voter history CSV via CLI or API, records are stored, re-import replaces previous records, summary reported.

---

## Phase 4: User Story 2 — Query a Voter's Participation History (Priority: P2)

**Goal**: Authorized users query a voter's participation history by registration number with filtering and pagination. The existing voter detail endpoint includes a participation summary.

**Independent Test**: Import voter history, then GET `/api/v1/voters/{reg_num}/history` and verify correct records; GET voter detail and verify `participation_summary` is populated.

**Acceptance criteria**: FR-007, FR-010, FR-011, FR-017, FR-020

### Implementation for User Story 2

- [X] T020 [US2] Implement `get_voter_history()` service function in `src/voter_api/services/voter_history_service.py` — query `voter_history` by `voter_registration_number`, order by `election_date DESC`, filter by `election_type`, `date_from`, `date_to`, `county`, `ballot_style` (FR-010: all history queries must support these filters); paginate with `page`/`page_size`; return `tuple[list[VoterHistory], int]`
- [X] T021 [US2] Add `GET /api/v1/voters/{voter_registration_number}/history` endpoint in `src/voter_api/api/v1/voter_history.py` — new router with prefix, `require_role("analyst", "admin")` auth (FR-017: viewers excluded), query params for `election_type`, `date_from`, `date_to`, `county`, `ballot_style`, `page`, `page_size` (FR-010); returns `PaginatedVoterHistoryResponse`
- [X] T022 [US2] Register voter history router in `src/voter_api/api/router.py` — add `from voter_api.api.v1.voter_history import ...` and `root_router.include_router(...)` in `create_router()`
- [X] T023 [US2] Add `ParticipationSummary` schema to `src/voter_api/schemas/voter.py` and add `participation_summary` field to `VoterDetailResponse` with `Field(default_factory=ParticipationSummary)`
- [X] T024 [US2] Enrich voter detail query in `src/voter_api/services/voter_service.py` — add subquery to count `voter_history` records and get `MAX(election_date)` by `voter_registration_number`, populate `ParticipationSummary` in the detail response builder

### Tests for User Story 2

- [X] T025 [P] [US2] Write integration tests for voter history query in `tests/integration/test_voter_history_api.py` — test GET history with results, empty result (no error), date range filtering, election type filtering, pagination, auth enforcement (analyst/admin allowed, viewer gets 403)
- [X] T026 [P] [US2] Write integration tests for voter detail enrichment in `tests/integration/test_voter_history_api.py` — test voter detail includes `participation_summary` with correct count and last date, test voter with no history returns zero/null summary

**Checkpoint**: User Stories 1 AND 2 complete — voter history can be imported and queried per voter with filtering; voter detail includes participation summary.

---

## Phase 5: User Story 3 — Auto-Create Election Events from Voter History (Priority: P3)

**Goal**: During voter history import, elections not yet in the system are automatically created from the date+type combination. Auto-created elections are distinguishable from manually created ones.

**Independent Test**: Import voter history referencing unknown elections, verify corresponding election records auto-created with `creation_method='voter_history'`.

**Acceptance criteria**: FR-006

### Implementation for User Story 3

- [X] T027 [P] [US3] Add `generate_election_name(raw_type: str, election_date: date) -> str` to `src/voter_api/lib/voter_history/parser.py` for auto-created election names (note: `map_election_type()` is already implemented in T007 and used to populate `normalized_election_type` during parsing)
- [X] T028 [US3] Implement `auto_create_elections()` in `src/voter_api/services/voter_history_service.py` — extract unique `(election_date, election_type)` combos from import batch, query existing elections, create missing elections with `creation_method='voter_history'`, `status='finalized'`, `district='Statewide'`, `data_source_url='n/a'`, generated name; return count of created elections
- [X] T029 [US3] Integrate `auto_create_elections()` into `process_voter_history_import()` in `src/voter_api/services/voter_history_service.py` — call before/during batch processing to ensure elections exist; existing elections are not duplicated

### Tests for User Story 3

- [X] T030 [P] [US3] Write unit tests for election type mapping in `tests/unit/lib/test_voter_history/test_parser.py` — test all mapping values from research.md table, unknown type defaults to "general", name generation format
- [X] T031 [US3] Write integration tests for election auto-creation in `tests/integration/test_voter_history_import.py` — test auto-creation of missing elections, no duplicates when election exists, `creation_method='voter_history'` set correctly, auto-created elections survive re-import (FR-021)

**Checkpoint**: User Stories 1, 2, AND 3 complete — import auto-creates elections, which are queryable and marked as voter-history-sourced.

---

## Phase 6: User Story 4 — Aggregate Participation Statistics (Priority: P3)

**Goal**: Authorized users query election participation data — list participants with filtering and get aggregate statistics (total, by county, by ballot style).

**Independent Test**: Import voter history, then GET `/api/v1/elections/{id}/participation` and `/participation/stats` and verify counts match imported data.

**Acceptance criteria**: FR-008, FR-009, FR-010, FR-011

### Implementation for User Story 4

- [X] T032 [US4] Implement `list_election_participants()` in `src/voter_api/services/voter_history_service.py` — look up election by ID to get `(election_date, election_type)`, query `voter_history` by `(election_date, normalized_election_type)` matching the election's type, filter by `county`, `ballot_style`, `absentee`, `provisional`, `supplemental`; paginate; return `tuple[list[VoterHistory], int]`
- [X] T033 [US4] Implement `get_participation_stats()` in `src/voter_api/services/voter_history_service.py` — look up election by ID, query `voter_history` by `(election_date, normalized_election_type)`, aggregate count of total participants, GROUP BY county, GROUP BY ballot_style; return `ParticipationStatsResponse`
- [X] T034 [P] [US4] Add `GET /api/v1/elections/{election_id}/participation` endpoint in `src/voter_api/api/v1/voter_history.py` — `require_role("analyst", "admin")` auth (FR-017: viewers excluded), query params for county/ballot_style/absentee/provisional/supplemental/page/page_size, 404 if election not found, returns `PaginatedElectionParticipationResponse`
- [X] T035 [P] [US4] Add `GET /api/v1/elections/{election_id}/participation/stats` endpoint in `src/voter_api/api/v1/voter_history.py` — `get_current_user` auth (FR-017: all authenticated users including viewers), 404 if election not found, returns `ParticipationStatsResponse`

### Tests for User Story 4

- [X] T036 [P] [US4] Write integration tests for participation endpoints in `tests/integration/test_voter_history_api.py` — test participant listing with filters (county, ballot_style, absentee), pagination, 404 for unknown election, auth enforcement (analyst/admin allowed, viewer gets 403)
- [X] T037 [P] [US4] Write integration tests for participation stats in `tests/integration/test_voter_history_api.py` — test total count, county breakdown, ballot style breakdown, 404 for unknown election, auth enforcement (all authenticated users including viewer allowed)

**Checkpoint**: All four user stories complete — voter history can be imported, queried per voter, auto-creates elections, and provides aggregate participation statistics.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates, contract verification, and final cleanup.

- [X] T038 Write contract tests for voter history OpenAPI spec in `tests/contract/test_voter_history_contract.py` — verify response schemas match contracts/openapi.yaml for all 4 endpoints
- [X] T039 Run `uv run ruff check .` and `uv run ruff format --check .` — fix any violations across all new and modified files
- [X] T040 Run `uv run pytest --cov=voter_api --cov-report=term-missing` — verify 90% coverage threshold met; add missing tests if needed
- [ ] T041 Validate quickstart.md scenarios — smoke-test CLI and API commands from quickstart.md against running dev environment
- [ ] T042 Performance smoke test — import a 50,000+ record file and verify completion within 5 minutes (SC-001); verify a single voter's history record is retrievable within 1 second (SC-002); query a voter's full participation history and verify response within 2 seconds (SC-006); query aggregate stats for an election with 50,000 participants and verify response within 3 seconds (SC-007); monitor peak memory during 100,000+ record import and verify it stays under 512MB (FR-005)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (migration must exist before models reference columns)
- **US1 Import (Phase 3)**: Depends on Phase 2 (models and schemas must exist)
- **US2 Query (Phase 4)**: Depends on Phase 2 (models/schemas); benefits from US1 data but independently implementable
- **US3 Auto-Create Elections (Phase 5)**: Depends on Phase 3 (enhances the import pipeline)
- **US4 Aggregate Stats (Phase 6)**: Depends on Phase 2 (models/schemas); benefits from US1 data but independently implementable
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

```text
Phase 1 (Setup) → Phase 2 (Foundational)
                       │
                       ├──→ US1 (Phase 3) ──→ US3 (Phase 5) ──┐
                       │                                       │
                       ├──→ US2 (Phase 4) ─────────────────────┼──→ Phase 7 (Polish)
                       │                                       │
                       └──→ US4 (Phase 6) ─────────────────────┘
```

- **US1 (P1)**: Foundation only — no dependencies on other stories
- **US2 (P2)**: Foundation only — independent of US3/US4; benefits from US1 test data
- **US3 (P3)**: Depends on US1 — enhances the import pipeline
- **US4 (P3)**: Foundation only — independent of US2/US3; benefits from US1 test data

### Within Each User Story

- Models before services
- Services before endpoints/CLI
- Core implementation before integration
- Tests can be written in parallel with implementation or after

### Parallel Opportunities

- T003, T004, T005 can all run in parallel (different files)
- T007, T008 can run in parallel with T005 (different directories)
- T015, T016 can run in parallel (different test files)
- T025, T026 can run in parallel (same file, different test classes)
- T034, T035 can run in parallel (different endpoints, same file)
- T036, T037 can run in parallel (different test functions)
- US2 and US4 can run in parallel after Phase 2 (independent stories)

---

## Parallel Example: User Story 1

```text
# Phase 2 parallel tasks:
Task T003: "Add creation_method to Election model in src/voter_api/models/election.py"
Task T004: "Add records_skipped/records_unmatched to ImportJob model in src/voter_api/models/import_job.py"
Task T005: "Create Pydantic schemas in src/voter_api/schemas/voter_history.py"

# US1 parallel tasks:
Task T007: "Create voter history CSV parser in src/voter_api/lib/voter_history/parser.py"
Task T008: "Create __init__.py exports in src/voter_api/lib/voter_history/__init__.py"

# US1 parallel test tasks:
Task T015: "Unit tests for parser in tests/unit/lib/test_voter_history/test_parser.py"
Task T016: "Unit tests for schemas in tests/unit/test_schemas/test_voter_history_schemas.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (migration)
2. Complete Phase 2: Foundational (models, schemas)
3. Complete Phase 3: User Story 1 (import pipeline + CLI + API + tests)
4. **STOP and VALIDATE**: Import a sample CSV, verify records in DB, re-import and verify replacement
5. Deploy/demo if ready — core data ingestion is functional

### Incremental Delivery

1. Phase 1 + Phase 2 → Foundation ready
2. Add US1 (Phase 3) → Test independently → Deploy (MVP: data ingestion works)
3. Add US2 (Phase 4) → Test independently → Deploy (voters can be queried for history)
4. Add US3 (Phase 5) → Test independently → Deploy (elections auto-created)
5. Add US4 (Phase 6) → Test independently → Deploy (aggregate stats available)
6. Phase 7 → Polish → Final validation

### Single Developer Strategy

Execute phases sequentially in order: 1 → 2 → 3 → 4 → 5 → 6 → 7. Within each phase, leverage parallel tasks where marked [P] to batch work.

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Commit after each task or logical group per constitution (Principle VIII)
- Run `ruff check .` and `ruff format --check .` before every commit per constitution (Principle II)
- 90% coverage threshold applies across the entire codebase per constitution (Principle III)
