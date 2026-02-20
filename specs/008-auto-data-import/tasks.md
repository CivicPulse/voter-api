# Tasks: Automated Data Download & Import

**Input**: Design documents from `/specs/008-auto-data-import/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included — the spec explicitly requires unit tests and integration tests (90% coverage threshold).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Configuration and shared data types for the data_loader library

- [x] T001 Add `data_root_url` setting to `src/voter_api/core/config.py` with default `https://data.hatchtech.dev/`, HTTPS validation
- [x] T002 [P] Add `DATA_ROOT_URL` entry to `.env.example` in the Optional section
- [x] T003 [P] Create data type definitions (DataFileEntry, SeedManifest, DownloadResult, SeedResult dataclasses) in `src/voter_api/lib/data_loader/types.py` per data-model.md
- [x] T004 [P] Create `src/voter_api/lib/data_loader/__init__.py` with public API exports for types only (SeedManifest, DataFileEntry, DownloadResult, SeedResult) — function re-exports added later in T013 after library modules exist

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core library modules that MUST be complete before ANY user story CLI work can begin

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Implement manifest fetcher in `src/voter_api/lib/data_loader/manifest.py` — async function `fetch_manifest(data_root_url: str) -> SeedManifest` using httpx.AsyncClient with streaming, parse JSON, validate against manifest schema, return SeedManifest
- [x] T006 Implement file downloader in `src/voter_api/lib/data_loader/downloader.py` — async function `download_file(url: str, dest: Path, expected_sha512: str, size_bytes: int) -> DownloadResult` with: streaming download via httpx, tqdm progress bar, SHA512 checksum verification during download, atomic writes (.part file + rename per R3), skip-if-cached (check existing file checksum), partial file cleanup on failure (FR-011). Also implement `resolve_download_path(entry: DataFileEntry, data_dir: Path) -> Path` helper that routes voter-category files to `data_dir/voter/{filename}` and all others to `data_dir/{filename}` per data-model.md
- [x] T007 [P] Write unit tests for types in `tests/unit/lib/test_data_loader/test_types.py` — DataFileEntry validation, SeedManifest construction, DownloadResult states, category enum values
- [x] T008 [P] Write unit tests for manifest fetcher in `tests/unit/lib/test_data_loader/test_manifest.py` — successful parse, invalid JSON, missing required fields, network error, non-200 response, manifest version validation
- [x] T009 Write unit tests for downloader in `tests/unit/lib/test_data_loader/test_downloader.py` — successful download with checksum, checksum mismatch (file discarded), skip-if-cached, partial download cleanup, atomic write (.part rename), network error handling, progress callback

**Checkpoint**: Library layer complete — all data_loader modules tested independently, no CLI or DB interaction yet

---

## Phase 3: User Story 1 — Bootstrap a Dev/Test Environment (Priority: P1) 🎯 MVP

**Goal**: An operator can fully populate an empty database with all reference data using `voter-api seed`, downloading files from the Data Root URL, verifying checksums, and importing in dependency order (county-districts → boundaries → voters).

**Independent Test**: Run the command against an empty database and verify all boundary and reference data is downloaded, checksummed, and imported correctly. Re-run and verify skip-if-cached works (download phase < 30s).

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T010 [P] [US1] Write integration tests for `voter-api seed` in `tests/integration/cli/test_seed_cmd.py` — test full seed (download + import), test unreachable URL error, test skip-if-cached behavior, test `--fail-fast` stops on first error, test import order enforcement (county-districts before boundaries before voters)

### Implementation for User Story 1

- [x] T011 [US1] Create `src/voter_api/cli/seed_cmd.py` with `seed` command — options: `--data-root` (override URL), `--data-dir` (default: `data`), `--fail-fast`, `--skip-checksum`; implement full workflow: fetch manifest → download all files → import county-districts → import all-boundaries → import voters; call existing async import functions directly (`_import_county_districts`, `_import_all_boundaries`, `_import_voters`); report progress via tqdm + typer.echo; handle errors (connection failure, checksum mismatch, import failure) with clear messages; respect `--fail-fast`
- [x] T012 [US1] Register `seed` command in `src/voter_api/cli/app.py` — import `seed` from `seed_cmd` and add via `app.command("seed")(seed)` in `_register_subcommands()`
- [x] T013 [US1] Update `src/voter_api/lib/data_loader/__init__.py` to add function re-exports (`fetch_manifest` from `manifest`, `download_file` from `downloader`) alongside existing type exports

**Checkpoint**: User Story 1 complete — `voter-api seed` downloads all files, verifies checksums, imports in correct order. Full bootstrap from empty DB works.

---

## Phase 4: User Story 2 — Selective Import by Data Type (Priority: P2)

**Goal**: An operator can filter downloads and imports by category (`--category boundaries`, `--category voters`, `--category county-districts`).

**Independent Test**: Run `voter-api seed --category boundaries` and verify only boundary files are downloaded and imported; voter and county-district files are untouched.

### Tests for User Story 2 ⚠️

- [x] T014 [P] [US2] Add category filter tests to `tests/integration/cli/test_seed_cmd.py` — test `--category boundaries` downloads/imports only boundary files, test `--category voters` downloads/imports only voter files, test `--category county-districts` downloads/imports only county-district files, test invalid category value error

### Implementation for User Story 2

- [x] T015 [US2] Add `--category` option to the `seed` command in `src/voter_api/cli/seed_cmd.py` — repeatable option that filters manifest entries by category before download and filters import phases to only matching categories; map CLI category names to manifest category values (`boundaries` → `boundary`, `voters` → `voter`, `county-districts` → `county_district`)

**Checkpoint**: User Story 2 complete — `--category` filtering works independently. Combined with US1, operators can do full or selective imports.

---

## Phase 5: User Story 3 — Download Only (Priority: P3)

**Goal**: An operator can download all data files without performing any database imports, useful for staging files or archiving.

**Independent Test**: Run `voter-api seed --download-only` and verify all files are present locally with correct checksums, with no database interaction.

### Tests for User Story 3 ⚠️

- [x] T016 [P] [US3] Add download-only tests to `tests/integration/cli/test_seed_cmd.py` — test `--download-only` downloads files without database import, test `--download-only --category voters` downloads only voter files without import

### Implementation for User Story 3

- [x] T017 [US3] Add `--download-only` flag to the `seed` command in `src/voter_api/cli/seed_cmd.py` — when set, skip all import phases after downloads complete; still verify checksums; output summary of downloaded files

**Checkpoint**: All user stories complete — full seed, selective category, and download-only modes all work independently.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Code quality, documentation, and validation

- [x] T018 [P] Run `uv run ruff check .` and `uv run ruff format --check .` — fix any lint or formatting issues in all new files
- [x] T019 [P] Run full test suite `uv run pytest --cov=voter_api --cov-report=term-missing` — verify 90% coverage threshold passes
- [x] T020 Run quickstart.md validation — execute the commands from `specs/008-auto-data-import/quickstart.md` and verify they work as documented

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on T003 (types) from Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2) completion
- **User Story 2 (Phase 4)**: Depends on User Story 1 (Phase 3) — extends the same `seed` command
- **User Story 3 (Phase 5)**: Depends on User Story 1 (Phase 3) — extends the same `seed` command
- **Polish (Phase 6)**: Depends on all user stories being complete

### Within Each Phase

- Tests MUST be written and FAIL before implementation
- Types/models before library modules
- Library modules before CLI commands
- CLI commands before integration tests pass

### Parallel Opportunities

- **Phase 1**: T002, T003, T004 can all run in parallel (different files)
- **Phase 2**: T007, T008 can run in parallel with each other (different test files); T005 and T006 can run in parallel (different library files)
- **Phase 3**: T010 (write failing tests) before T011 (implement)
- **Phase 4–5**: US2 and US3 are independent of each other and could theoretically run in parallel, but both modify the same file (`seed_cmd.py`), so sequential is safer
- **Phase 6**: T018 and T019 can run in parallel

---

## Parallel Example: Phase 2 (Foundational)

```bash
# Launch library modules in parallel (different files):
Task: "Implement manifest fetcher in src/voter_api/lib/data_loader/manifest.py"
Task: "Implement file downloader in src/voter_api/lib/data_loader/downloader.py"

# Launch unit tests in parallel (different test files):
Task: "Unit tests for types in tests/unit/lib/test_data_loader/test_types.py"
Task: "Unit tests for manifest in tests/unit/lib/test_data_loader/test_manifest.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (config + types)
2. Complete Phase 2: Foundational (manifest + downloader + unit tests)
3. Complete Phase 3: User Story 1 (seed CLI + integration tests)
4. **STOP and VALIDATE**: Test `voter-api seed` against a real database
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Library layer ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test `--category` filter → Deploy/Demo
4. Add User Story 3 → Test `--download-only` → Deploy/Demo
5. Each story adds a CLI option without breaking previous behavior

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- The `seed` command calls existing async import functions directly — no subprocess spawning
- Import order is fixed: county-districts → boundaries → voters (FR-012)
- All downloads are sequential (not parallel) per design decision R1
- Atomic writes (.part file + rename) prevent partial file corruption (FR-011)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
