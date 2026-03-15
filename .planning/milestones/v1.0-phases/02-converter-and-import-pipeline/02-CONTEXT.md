# Phase 2: Converter and Import Pipeline - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the deterministic MD-to-JSONL converter and CLI import commands so JSONL files reach the database. Includes DB migrations to support the new candidate/candidacy model and ElectionEvent enhancements defined in Phase 1 contracts. Also includes populating all 159 county reference files (needed by the converter) and migrating existing ~200 markdown files to the enhanced format.

</domain>

<decisions>
## Implementation Decisions

### Converter CLI Design
- **Directory-first invocation**: Primary command converts an entire election directory (`voter-api convert <dir>`). Single-file mode available via flag.
- **Output location**: Defaults to sibling `jsonl/` subdirectory next to markdown files, with `--output` flag to override.
- **Validation report**: Both terminal table (human-readable) and JSON report file (machine-readable) written to the output directory.
- **Partial failure handling**: Default is continue-and-report (skip failures, non-zero exit if any failed). `--fail-fast` flag available for strict mode. Follows the same pattern as `import all-boundaries`.

### Converter Library Design
- **Location**: New `lib/converter/` package following established library-first pattern (`__init__.py` with public API, submodules for parser/writer/resolver).
- **Body/Seat resolution**: Reference file lookup — converter reads county reference files (`data/states/GA/counties/`) to resolve Body IDs to boundary_type. Statewide/federal bodies use a built-in mapping. Unresolved = validation error.
- **Scope**: lib/converter/ handles MD → JSONL only. Import (JSONL → DB) lives in services/ following the existing pattern. Clean separation of concerns.

### Import Command Granularity
- **Both individual + pipeline**: Four individual commands (`voter-api import election-events`, `import elections`, `import candidates`, `import candidacies`) plus one pipeline command (`import election-data <dir>`) that runs all four in correct order.
- **Dry-run mode**: Parse JSONL, validate against Pydantic schemas, check for existing DB records (would-insert vs would-update), report counts. No writes. Matches existing `--dry-run` pattern.
- **Idempotent upsert**: Records matched by UUID — if exists, update all fields to match JSONL. JSONL is the source of truth. Matches existing voter import pattern (`INSERT ON CONFLICT DO UPDATE`).
- **Pipeline failure behavior**: Stop on failure — if election-events import fails, don't attempt subsequent imports (FK dependencies would cause failures anyway). Report what succeeded and what didn't.

### DB Migration Sequencing
- **Additive-first approach**: Add new tables (candidacies) alongside existing candidates table. Add person-level fields to candidates. Alembic migration copies contest-specific fields to candidacies. Drop old columns later.
- **API schemas updated in Phase 2**: Change API response schemas to reflect person + candidacy model. Breaking change — existing API consumers will need to update.
- **Same deployment**: All four migrations (candidacies table, ElectionEvent enhancement, election_stage field, calendar field move) bundled into one deploy.
- **Data migration in Alembic**: The Alembic migration itself copies existing candidate rows to candidacy records using SQL. No separate CLI command needed. Atomic with schema migration.
- **Existing candidate import updated in Plan 02-01**: The existing `candidate_import_service.py` and `import candidates` CLI command are updated to work with the new model so nothing breaks during Phase 2 development.

### Existing File Migration
- **Fully automated**: CLI command (`voter-api convert migrate-format <dir>`) rewrites all files in-place: adds Format Version, infers Body/Seat from contest names, restructures to unified overview format. Files that fail validation are skipped with errors in the report.
- **UUID backfill**: Match existing DB records by natural key (election name + date), write DB UUID into markdown. For files with no DB match, generate new UUID. Backfill is a prerequisite to running the converter.
- **Git commit strategy**: One commit per file type — overview files, contest files separately. Each commit is reviewable and revertable independently. Conventional commit messages.
- **Candidate stubs deferred to Phase 3**: Don't create `data/candidates/` stub files during migration. Let the Phase 3 Claude skill create them with enrichment data.

### County Reference Files
- **Populate all 159 counties in Phase 2**: Complete coverage needed for converter to work with any Georgia election data.
- **Population method**: Claude skill (Phase 3 pull-forward) — AI-assisted research and population, human-reviewed. Faster than pure manual, committed in batches.
- **Included in Plan 02-02**: Part of the converter plan since the converter depends on reference files and can't be fully tested without them.

### Plan Splitting
- **Three plans**:
  - **02-01: DB Migrations & Model Refactoring** — Alembic migrations (candidacies table, ElectionEvent enhancement, election_stage, calendar field move, data migration), ORM model updates, API schema updates, E2E test fixes, update existing candidate import service.
  - **02-02: Converter Library** — `lib/converter/` (parser, writer, resolver), `cli/convert_cmd.py`, unit tests, populate all 159 county reference files.
  - **02-03: Import Pipeline & File Migration** — Import services (JSONL → DB), import CLI commands (4 individual + 1 pipeline), file migration script, UUID backfill command, E2E tests for new import commands.

### Claude's Discretion
- Converter internal architecture (submodule breakdown within lib/converter/)
- mistune AST parsing implementation details
- Exact Alembic migration SQL for data migration
- Import batch size defaults and performance tuning
- Error message formatting in validation reports
- County reference file population order and batching

</decisions>

<specifics>
## Specific Ideas

- Pipeline command (`import election-data`) is sugar over the four individual commands — stops on failure due to FK dependency chain (events → elections → candidates → candidacies).
- Converter validation report serves dual purpose: human-readable table in terminal (like existing import summaries) + machine-readable JSON file for CI/automation.
- County reference population using Claude skill is a Phase 3 capability pulled forward — the skill doesn't need to be formalized, just the data generation approach.
- Additive-first DB migration means the old candidate model stays intact alongside the new candidacy junction until the pipeline is proven working.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/voter_api/schemas/jsonl/` — Four Pydantic JSONL schema models (ElectionEventJSONL, ElectionJSONL, CandidateJSONL, CandidacyJSONL) from Phase 1. Converter validates against these.
- `src/voter_api/cli/import_cmd.py` — Established CLI patterns: asyncio.run wrapper, init_engine/dispose_engine lifecycle, Typer options, summary table printing. New commands follow this pattern.
- `src/voter_api/services/candidate_import_service.py` — Existing candidate import service with job creation + batch processing. Needs updating for new model.
- `src/voter_api/services/import_service.py` — Bulk UPSERT pattern (`INSERT ON CONFLICT DO UPDATE`) with sub-batching. Import services for JSONL follow this approach.
- `docs/formats/` — 17 format spec files (5 markdown formats, 4 JSONL docs, 5 vocabularies, 3 process specs) defining the contracts the converter must implement.
- `data/states/GA/counties/` — 159 county reference file stubs (metadata only, no governing bodies yet).
- `data/elections/` — ~200 existing markdown files needing migration.

### Established Patterns
- Library-first architecture: `lib/` subpackages with `__init__.py` public API + `__all__` list.
- Service layer: async functions taking `session: AsyncSession` as first parameter. No classes.
- CLI commands: Typer app in `cli/{command}_cmd.py`, registered in `cli/app.py:_register_subcommands()`.
- Error handling: service layer raises domain exceptions; API layer converts to HTTPException.
- Import jobs tracked in `import_jobs` table with status lifecycle.

### Integration Points
- `src/voter_api/models/candidate.py` — Needs refactoring: election_id FK becomes optional/removed, person-level fields stay, contest-specific fields move to candidacy.
- `src/voter_api/models/election_event.py` — Needs enhancement: calendar dates, feed URL, refresh fields added.
- `src/voter_api/models/election.py` — Calendar dates and feed URL fields removed (moved to ElectionEvent). election_stage field added.
- `src/voter_api/api/v1/candidates.py` — API schema updates for person + candidacy model.
- `tests/e2e/conftest.py` — Seed data needs updating for new model structure.
- `cli/app.py` — New `convert` subcommand registration.

</code_context>

<deferred>
## Deferred Ideas

- **Candidate stub file creation** — Deferred to Phase 3. Claude skill will create candidate files with enrichment data rather than empty stubs.
- **Round-trip validation** (MD → JSONL → DB → export matches original) — v2 requirement (EXT-04).
- **API import endpoints** (HTTP wrappers around CLI) — v2 requirement (INF-03).
- **Import progress reporting** (WebSocket/polling) — v2 requirement (INF-04).
- **R2 signed URL upload** — v2 requirement (INF-02).
- **Procrastinate job queue** — v2 requirement (INF-01).

</deferred>

---

*Phase: 02-converter-and-import-pipeline*
*Context gathered: 2026-03-14*
