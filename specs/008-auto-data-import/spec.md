# Feature Specification: Automated Data Download & Import

**Feature Branch**: `008-auto-data-import`
**Created**: 2026-02-20
**Status**: Draft
**Input**: User description: "I want to update the import system to include a function to download data from a fqdn (Data Root) and import all that data. This will be used to auto load data into testing/dev environments as well as to update prod when needed. This new CLI function will wrap the existing imports with download and automation, not replace anything."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bootstrap a Dev/Test Environment (Priority: P1)

A developer setting up a new development or testing environment needs all reference data (boundary shapefiles, county-district mappings) downloaded from the central data store and imported into their local database in a single command. Today this requires manually downloading files, placing them in the correct directory, and running multiple import commands in sequence.

**Why this priority**: This is the core use case — reducing a multi-step manual process to a single automated command. Without this, every new environment setup is error-prone and time-consuming.

**Independent Test**: Can be fully tested by running the command against an empty database and verifying that all boundary and reference data is downloaded, checksummed, and imported correctly.

**Acceptance Scenarios**:

1. **Given** a fresh environment with an empty database and no local data files, **When** the operator runs the auto-import command with the data root URL, **Then** all boundary shapefiles, county-district mappings, and voter CSVs are downloaded to a local directory, verified against their SHA512 checksums, and imported into the database using the existing import pipelines.
2. **Given** a data root URL that is unreachable, **When** the operator runs the auto-import command, **Then** the system reports a clear connection error and exits without partial changes.
3. **Given** some files already exist locally and are up to date, **When** the operator runs the auto-import command, **Then** already-downloaded files with matching checksums are not re-downloaded (saving bandwidth), but the database import is still re-run for all files to ensure the database stays in sync.

---

### User Story 2 - Selective Import by Data Type (Priority: P2)

An operator wants to refresh only a specific category of data (e.g., only boundaries, only voter files, or only county-district mappings) without re-downloading and re-importing everything.

**Why this priority**: In production and testing, operators often need to update just one category of data — for example, refreshing voter files after a new export, or updating boundaries after redistricting. Forcing a full download+import when only one category changed is wasteful.

**Independent Test**: Can be tested by running the command with a category filter and verifying only matching files are downloaded and imported.

**Acceptance Scenarios**:

1. **Given** the operator specifies a data type filter (e.g., "boundaries only"), **When** the auto-import runs, **Then** only files matching that category are downloaded and imported; other categories are untouched.
2. **Given** the operator specifies "voters only", **When** the auto-import runs, **Then** only voter CSV files are downloaded and imported using the existing voter import pipeline.

---

### User Story 3 - Download Only (No Import) (Priority: P3)

An operator wants to download all data files from the remote data store to a local directory without performing any database imports. This is useful for staging files before a planned import window, or for archiving data.

**Why this priority**: Separating download from import gives operators more control, especially in production environments where imports need to be timed carefully.

**Independent Test**: Can be tested by running the download-only command and verifying all files are present locally with correct checksums, without any database interaction.

**Acceptance Scenarios**:

1. **Given** the operator runs the command with a "download only" flag, **When** the downloads complete, **Then** all files are saved locally with checksums verified, and no database import is attempted.

---

### Edge Cases

- What happens when a downloaded file fails checksum verification? The file is discarded, the failure is reported, and the operator can choose to continue or abort (consistent with existing `--fail-fast` behavior).
- What happens when the remote data store has a file not listed in the known manifest? Unknown files are ignored — only files registered in the data manifest are downloaded.
- What happens when a download is interrupted mid-file? Partial downloads are cleaned up. The next run re-downloads the incomplete file.
- What happens when there is insufficient disk space? The system reports a clear error before or during download and does not leave the database in an inconsistent state.
- What happens when a voter CSV file is downloaded? The file is passed directly to the existing `import voters` command. No county mapping from the filename is needed — each record within the CSV contains the county as a data field.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a CLI command that downloads data files from a configurable remote URL (the "Data Root") and imports them using the existing import pipelines.
- **FR-002**: System MUST download and parse a remote data manifest hosted at the Data Root URL. The manifest lists all available files, their expected checksums, and how each file should be imported (boundary, voter, county-district, or reference-only). The manifest is fetched fresh on every run.
- **FR-003**: System MUST verify each downloaded file's SHA512 checksum against the manifest before attempting import. Operator MAY override via `--skip-checksum` flag for debugging, consistent with existing `import all-boundaries --skip-checksum` behavior.
- **FR-004**: System MUST skip re-downloading files that already exist locally and pass checksum verification. The database import is always re-run regardless of download status, since the existing import commands are idempotent (upsert).
- **FR-005**: System MUST support filtering by data category (boundaries, voters, county-districts) so operators can selectively download and import.
- **FR-006**: System MUST support a "download only" mode that fetches files without importing.
- **FR-007**: System MUST report progress during download and import, including file sizes, download status, and import results.
- **FR-008**: System MUST reuse the existing import commands (`import all-boundaries`, `import voters`, `import county-districts`) for database ingestion — it orchestrates, not replaces, those commands.
- **FR-009**: System MUST support a `--fail-fast` option to stop on first error, consistent with the existing `import all-boundaries` behavior.
- **FR-010**: System MUST read the Data Root URL from the application's environment configuration (`.env` file), with the ability to override it via a CLI argument.
- **FR-011**: System MUST clean up partial downloads on failure — no half-written files should remain in the data directory.
- **FR-012**: System MUST enforce a fixed import order based on data dependencies: county-district mappings first, then boundaries, then voter files. This order is not configurable by the operator.

### Key Entities

- **Data Manifest**: A machine-readable JSON file hosted at the Data Root URL that lists all available data files. For each file, the manifest includes: filename, SHA512 checksum, file category (boundary, voter, county-district, reference), and file size in bytes. The manifest controls **what gets downloaded**; import-specific metadata (boundary type, county, source) is managed by the existing code-level `BOUNDARY_MANIFEST` which controls **how files get imported**. The remote manifest is the single source of truth for what files exist and their integrity checksums.
- **Data Root**: The base URL from which the manifest and all data files are downloaded. Currently `https://data.hatchtech.dev/`. Configured via environment variable, overridable per CLI invocation.

## Clarifications

### Session 2026-02-20

- Q: When a file already exists locally with a matching checksum, should the system also skip the database import? → A: Skip download only — always re-run the import even if the file hasn't changed locally. The existing import commands handle upserts, so re-importing is safe and ensures the database stays in sync.
- Q: How should the data manifest be maintained? → A: The Data Root URL is configured in the `.env` file. A manifest file is hosted at the root of that URL and is downloaded first at runtime, then parsed to determine which files to download and import. No local code-level manifest needed for file listings.
- Q: Should the system enforce a fixed import order? → A: Yes. Fixed order based on data dependencies: county-districts → boundaries → voters. The system enforces this automatically.

## Assumptions

- The Data Root URL serves files directly (no authentication required) — files are publicly accessible via HTTPS.
- The remote manifest at the Data Root URL is the source of truth for file listings and checksums. The existing local `.sha512.txt` companion files remain useful for standalone verification but are not required by the auto-import command — it relies on the manifest checksums.
- The existing import commands (`import all-boundaries`, `import voters`, `import county-districts`) remain unchanged — this feature wraps them, not modifies them.
- Non-importable files (PDFs, reference documents) may be downloaded for completeness but are not imported into the database.
- The county-districts CSV (`counties-by-districts-2023.csv`) should be imported before boundaries, as it populates the mapping table used during boundary queries.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can fully populate an empty database with all reference data (boundaries, county-districts, voter files) using a single CLI command, completing in under 10 minutes on a typical internet connection.
- **SC-002**: Re-running the command on an already-populated environment skips file downloads for unchanged files (saving bandwidth), and re-runs all imports. The download phase completes in under 30 seconds when all files are cached locally.
- **SC-003**: The command provides clear progress feedback — the operator can see which files are being downloaded, their sizes, and the import status for each file.
- **SC-004**: Any download or import failure produces a clear, actionable error message identifying the failed file and the reason for failure.
