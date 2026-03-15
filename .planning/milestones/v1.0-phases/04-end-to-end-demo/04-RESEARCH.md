# Phase 4: End-to-End Demo - Research

**Researched:** 2026-03-15
**Domain:** Pipeline integration (MD-to-JSONL conversion, DB import, API verification), documentation
**Confidence:** HIGH

## Summary

Phase 4 proves the full election data pipeline works end-to-end: starting from Phase 3's committed markdown, running the deterministic converter to produce JSONL, importing into a clean PostGIS database, and querying results through authenticated API endpoints. The primary deliverable is a reproducible walkthrough document at `docs/pipeline-walkthrough.md`.

Research uncovered one critical gap: the May 19 election files (the largest dataset with 185+ markdown files) are in the pre-migration format -- they lack the enhanced metadata (ID, Format Version, Body, Seat) that the converter requires. The March 10 and March 17 files are already in enhanced format. The walkthrough must include a `voter-api convert migrate-format` step for the May 19 data before conversion can proceed.

A second significant gap: the converter library currently only produces `election_events.jsonl` and `elections.jsonl`. It does NOT produce `candidates.jsonl` or `candidacies.jsonl`. The `election-data` import pipeline gracefully skips missing files ("Skipping candidates.jsonl (not found)"), but the CONTEXT.md explicitly requires verifying that "candidates are queryable via the API." This means Phase 4 can only demonstrate election event and election contest import through the converter pipeline. Candidate/candidacy conversion from markdown is not yet implemented and should be acknowledged as a limitation (or addressed if within scope).

**Primary recommendation:** Structure the walkthrough around the smallest election first (March 10, 5 files, already in enhanced format) for quick validation, then scale up to all three elections. Use `curl` for API verification (consistent with project conventions and minimal dependencies). Address the May 19 format migration as a documented step in the walkthrough.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **All three elections processed**: May 19 general primary (2,346 rows), March 17 special (9 rows), March 10 special (38 rows) -- proves pipeline works across election types
- **Start from existing markdown**: Use Phase 3's committed markdown output, not re-run AI skills. Git history documents skill execution. Demo picks up at converter step.
- **Include human-review checkpoint**: Walkthrough includes a step where the operator reviews markdown via `git diff` before proceeding to conversion. Documents the human-in-the-loop design.
- **Old file state unknown**: Planner should investigate whether pre-Phase 3 markdown files in `data/elections/2026-05-19/` were replaced by Phase 3 output or still exist alongside it. Handle any discrepancy before running the converter.
- **Format**: Step-by-step markdown document at `docs/pipeline-walkthrough.md`
- **Target audience**: Developer who has cloned the repo, has uv and PostGIS set up, and is familiar with CLI tools and git
- **Expected output**: Include real terminal output captured from the actual demo run as code blocks. Shows exactly what to expect at each step.
- **Four query types demonstrated**: (1) List elections by date, (2) Candidate lookup, (3) Election detail with candidates, (4) District-based query
- **Count assertions + spot checks**: Document expected record counts per election date AND spot-check specific candidates by name
- **Full auth flow**: Walkthrough shows login, JWT token retrieval, and authenticated API requests
- **Show and explain the report**: Include full terminal validation report output with annotations
- **Dry-run before import**: Run `--dry-run` first to show what would be imported, then run the real import
- **Local PostGIS via docker-compose**: Self-contained, reproducible
- **Clean database from scratch**: Walkthrough includes `docker compose up`, `alembic upgrade head`
- **Happy path only**: No error scenarios in the walkthrough
- **Both options documented**: Keep database running or `docker compose down`

### Claude's Discretion
- HTTP client tool choice for API verification (curl, httpie, or httpx -- whatever fits best with existing project conventions)
- Plan count and task sequencing
- Exact walkthrough section structure and flow
- How to handle old vs Phase 3 file discrepancy (once investigated)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DEM-01 | End-to-end demo: May 19 SOS CSV -> run skill -> review markdown -> convert to JSONL -> import -> query elections and candidates via API | All tooling exists: `voter-api convert directory`, `voter-api import election-data`, `voter-api user create`, `POST /auth/login`, `GET /api/v1/elections`. May 19 format migration needed. Candidate/candidacy JSONL gap identified. |
</phase_requirements>

## Standard Stack

### Core (all existing -- no new dependencies)

| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| `voter-api convert directory` | current | MD-to-JSONL conversion | Built in Phase 2, deterministic converter with validation reporting |
| `voter-api convert migrate-format` | current | Upgrade pre-migration files to enhanced format | Built in Phase 2, adds ID/Format Version/Body/Seat metadata |
| `voter-api import election-data` | current | Pipeline import (JSONL -> DB) in FK dependency order | Built in Phase 2, handles election-events, elections, candidates, candidacies |
| `voter-api user create` | current | Create admin user for API auth | Typer CLI, interactive user creation |
| `docker compose` | - | Local PostGIS database | Existing `docker-compose.yml` with `postgis/postgis:15-3.4` |
| `alembic upgrade head` | current | Apply all DB migrations | Standard Alembic via `voter-api db upgrade` |
| `curl` | system | API verification HTTP client | Zero extra dependencies, ubiquitous, project already uses CLI tools extensively |

### Supporting

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `voter-api normalize elections` | Normalize markdown after format migration | If May 19 files need normalization post-migration |
| `voter-api normalize candidates` | Normalize candidate files | If candidate files need UUID backfill |
| `voter-api convert backfill-uuids` | Assign UUIDs to migrated files | May 19 files have empty ID fields after migration |
| `jq` | JSON response formatting in walkthrough | Optional; `curl` output can be piped through `jq` for readability |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `curl` | `httpie` (`http`) | More readable syntax but adds a dependency; curl is universal |
| `curl` | Python `httpx` script | More Pythonic but walkthrough should use CLI tools for simplicity |
| Manual `voter-api import election-events` + `elections` etc. | `voter-api import election-data` pipeline | Pipeline command handles FK ordering automatically; use it |

**Recommendation:** Use `curl` for API verification. It requires no additional installation, every developer has it, and the walkthrough targets a CLI-comfortable audience.

## Architecture Patterns

### Pipeline Flow (What the Walkthrough Demonstrates)

```
Phase 3 output (committed markdown)
    |
    v
[1] git diff -- human reviews markdown          # Human-in-the-loop checkpoint
    |
    v
[2] voter-api convert migrate-format             # May 19 only: upgrade to enhanced format
    |
    v
[3] voter-api convert directory                  # MD -> JSONL (deterministic, no AI)
    |                                            # Produces: election_events.jsonl, elections.jsonl
    v                                            # NOTE: candidates.jsonl, candidacies.jsonl NOT produced
[4] voter-api import election-data --dry-run     # Validate JSONL, show counts
    |
    v
[5] voter-api import election-data               # Load into PostgreSQL/PostGIS
    |
    v
[6] curl API queries                             # Verify data accessible via REST API
```

### File Layout After Conversion

```
data/elections/
├── 2026-05-19/          # 185+ markdown files (overview + 27 statewide + 159 county)
├── 2026-03-17/          # 5 markdown files (overview + 4 contests)
├── 2026-03-10/          # 6 markdown files (overview + 4 statewide + 1 county)
│   └── counties/
│       └── 2026-03-10-whitfield.md
├── jsonl/               # Converter output directory (sibling of date dirs)
│   ├── election_events.jsonl    # ElectionEvent records (1 per overview file)
│   ├── elections.jsonl          # Election contest records (1+ per contest file)
│   └── conversion-report.json  # Machine-readable conversion report
└── formats/             # Format spec files (not converted)

data/candidates/         # 49 candidate markdown files (NOT converted to JSONL yet)
```

### JSONL Output Directory Convention

The converter writes JSONL to a sibling `jsonl/` directory by default:
- Input: `data/elections/2026-03-10/` -> Output: `data/elections/jsonl/`
- Or use `--output` flag to specify a custom output directory
- The `election-data` pipeline import command reads from a single directory containing all `.jsonl` files

**Critical insight:** Each election directory must be converted separately (`convert directory` operates on one election date directory at a time). All JSONL output must be collected into one directory for the `election-data` pipeline command, OR each converted separately.

### Auth Flow for API Verification

```bash
# 1. Create admin user (via CLI, not API)
uv run voter-api user create

# 2. Login to get JWT
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"<password>"}' | jq .

# 3. Store token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"<password>"}' | jq -r .access_token)

# 4. Use token for authenticated requests
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/elections | jq .
```

**Note:** POST `/auth/login` accepts JSON body (not form-data) per Phase 009 breaking change. Fields: `username`, `password`, optional `totp_code`.

### API Endpoints for Verification

| Query | Endpoint | Auth Required | Expected Behavior |
|-------|----------|---------------|-------------------|
| List elections by date | `GET /api/v1/elections?date_from=2026-05-19&date_to=2026-05-19` | No (public) | Returns paginated election list filtered by date |
| Election detail | `GET /api/v1/elections/{id}` | No (public) | Returns election with candidacies if populated |
| List candidates for election | `GET /api/v1/elections/{election_id}/candidates` | No (public) | Returns paginated candidates (requires candidates in DB) |
| Candidate detail | `GET /api/v1/candidates/{id}` | No (public) | Returns candidate with links and candidacy info |
| District-based query | `GET /api/v1/elections?district_type=state_house&district_identifier=district-130` | No (public) | Filters elections by boundary_type + district_identifier |

**Important:** Election list and detail endpoints are public. Candidate endpoints are public for read. The walkthrough still needs auth for the admin user creation step (proving the auth flow works), but the actual queries can be public.

### Anti-Patterns to Avoid

- **Running the full pipeline without checking format first:** May 19 files will fail conversion without `migrate-format`. Always verify Format Version exists before converting.
- **Assuming candidates.jsonl exists after conversion:** The converter does NOT produce candidate/candidacy JSONL. The `election-data` pipeline will skip missing files, which is correct behavior but means candidates won't be imported.
- **Using the API service container for the demo:** The `docker-compose.yml` has an `api` service, but the walkthrough should run the API locally via `uv run voter-api serve --reload` for better visibility into what's happening.
- **Importing without `--dry-run` first:** The CONTEXT.md explicitly requires showing dry-run output before real import. Always dry-run first.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Format migration | Custom script to add metadata | `voter-api convert migrate-format` | Already handles overview, single-contest, multi-contest file types with Body/Seat inference |
| UUID assignment | Manual UUID generation | `voter-api convert backfill-uuids` or `voter-api normalize elections/candidates` | Handles DB matching, collision detection, consistent naming |
| Import ordering | Manual file-by-file import | `voter-api import election-data` | Handles FK dependency order automatically, stops on first failure |
| Auth token generation | Custom JWT creation | `voter-api user create` + `POST /auth/login` | Production auth flow, proves the real system works |
| Database setup | Manual SQL | `docker compose up` + `voter-api db upgrade` | Existing Alembic migrations cover all tables |

**Key insight:** Every step of the pipeline already has a CLI command. The walkthrough is about demonstrating their use in sequence, not building new tooling.

## Common Pitfalls

### Pitfall 1: May 19 Files Not in Enhanced Format
**What goes wrong:** `voter-api convert directory data/elections/2026-05-19/` either fails or produces empty/malformed JSONL because the files lack ID, Format Version, Body, Seat metadata.
**Why it happens:** May 19 files were created before the enhanced format spec. Phase 3 processed them through the qualified-candidates skill but did NOT run format migration (the migration command was built in Phase 2 for exactly this purpose).
**How to avoid:** Run `voter-api convert migrate-format data/elections/2026-05-19/` before `convert directory`. Verify with `grep -l "Format Version" data/elections/2026-05-19/*.md | wc -l`.
**Warning signs:** Converter report shows 0 successes or all failures.

### Pitfall 2: Converter Does Not Produce Candidate/Candidacy JSONL
**What goes wrong:** After conversion, `data/elections/jsonl/` contains only `election_events.jsonl` and `elections.jsonl`. No `candidates.jsonl` or `candidacies.jsonl`. The `election-data` pipeline logs "Skipping candidates.jsonl (not found)" and "Skipping candidacies.jsonl (not found)".
**Why it happens:** The converter's `_write_records_to_disk` function only handles `FileType.OVERVIEW` -> `election_events.jsonl` and everything else -> `elections.jsonl`. There is no code path to extract person-entity candidate records or candidacy junction records from the parsed markdown.
**How to avoid:** Acknowledge this limitation in the walkthrough. The demo proves election events and election contests flow through the pipeline. Candidate/candidacy conversion is a future enhancement.
**Warning signs:** API queries for `/elections/{id}/candidates` return empty results even after import.

### Pitfall 3: JSONL Output Directory Structure
**What goes wrong:** Running `convert directory` on each election date creates separate `jsonl/` sibling directories. The `election-data` pipeline expects all four JSONL files in a single directory.
**Why it happens:** Default output is `data/elections/jsonl/` (sibling of each date directory). But each conversion run overwrites the files in that directory. The last conversion run's output replaces the previous one.
**How to avoid:** Either (a) convert all three elections into the same output directory using `--output`, or (b) run `election-data` after each individual conversion, or (c) merge JSONL files from separate runs. Option (a) is cleanest -- use `--output data/elections/jsonl/` for all three conversions, and the JSONL files append records (actually, they overwrite -- need to investigate if the writer appends or overwrites).
**Warning signs:** Only the last-converted election's data appears in the database.

### Pitfall 4: Converter Overwrites JSONL Files
**What goes wrong:** Converting three election directories sequentially into the same output directory means each run overwrites `election_events.jsonl` and `elections.jsonl`.
**Why it happens:** `write_jsonl()` opens the file with mode `"w"` (write/truncate), not `"a"` (append).
**How to avoid:** Convert each election directory into separate output directories, then import each separately. OR concatenate JSONL files manually. OR convert to separate dirs: `--output data/elections/2026-05-19/jsonl/`, `--output data/elections/2026-03-17/jsonl/`, etc. Then import each directory separately with `voter-api import election-data`.
**Warning signs:** Database shows only one election event when three are expected.

### Pitfall 5: DATABASE_URL Must Use asyncpg Driver
**What goes wrong:** `alembic upgrade head` or `voter-api import` fails with connection errors.
**Why it happens:** The async engine requires `postgresql+asyncpg://` URL prefix. Using `postgresql://` or `postgres://` won't work with the async SQLAlchemy setup.
**How to avoid:** Walkthrough explicitly shows the correct DATABASE_URL format: `postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api`.

### Pitfall 6: Empty ID Fields After Format Migration
**What goes wrong:** Files have `| ID | |` (empty) after `migrate-format`. The converter may produce JSONL with empty ID fields, which causes validation failures.
**Why it happens:** `migrate-format` adds the ID row but leaves it empty. UUIDs are assigned by `backfill-uuids` (requires DB) or `normalize elections` (generates new UUIDs).
**How to avoid:** After `migrate-format`, run `voter-api normalize elections data/elections/2026-05-19/` to generate UUIDs. Verify IDs are populated: `grep "| ID |" data/elections/2026-05-19/2026-05-19-general-primary.md`.

## Code Examples

### Convert a Single Election Directory

```bash
# Source: voter-api convert directory --help
uv run voter-api convert directory data/elections/2026-03-10/

# Output goes to data/elections/jsonl/ by default
# Or specify: --output data/elections/2026-03-10/jsonl/
```

### Import with Dry-Run

```bash
# Source: voter-api import election-data --help
# First: validate without writing
uv run voter-api import election-data data/elections/2026-03-10/jsonl/ --dry-run

# Then: real import
uv run voter-api import election-data data/elections/2026-03-10/jsonl/
```

### Login and Query API

```bash
# Login (JSON body, not form-data -- Phase 009 breaking change)
# Set DEMO_PASSWORD in your environment before running (do not hardcode credentials)
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"demo\",\"password\":\"$DEMO_PASSWORD\"}" | jq -r .access_token)

# List elections (public, no auth needed)
curl -s http://localhost:8000/api/v1/elections | jq '.items | length'

# Filter by date range
curl -s "http://localhost:8000/api/v1/elections?date_from=2026-03-10&date_to=2026-03-10" | jq .

# Election detail
curl -s http://localhost:8000/api/v1/elections/{election_id} | jq .

# District-based query (boundary_type + district_identifier from elections table)
curl -s "http://localhost:8000/api/v1/elections?district_type=state_house&district_identifier=district-130" | jq .
```

### Format Migration for May 19

```bash
# Source: voter-api convert migrate-format --help
# Check current state
grep -c "Format Version" data/elections/2026-05-19/*.md  # Should be 0

# Migrate
uv run voter-api convert migrate-format data/elections/2026-05-19/

# Verify
grep -c "Format Version" data/elections/2026-05-19/*.md  # Should be > 0

# Generate UUIDs
uv run voter-api normalize elections data/elections/2026-05-19/
```

### Create Demo User

```bash
# Interactive user creation
uv run voter-api user create
# Prompts: username, email, password, role (admin)
```

## State of the Art

### Current State of Data Files

| Election Date | Files | Enhanced Format? | UUIDs? | Converter-Ready? |
|---------------|-------|-----------------|--------|------------------|
| 2026-03-10 | 6 (overview + 4 statewide + 1 county) | YES | Empty (need normalization) | AFTER UUID generation |
| 2026-03-17 | 5 (overview + 4 contests) | YES | Empty (need normalization) | AFTER UUID generation |
| 2026-05-19 | 185+ (overview + 27 statewide + 159 county) | NO | N/A | AFTER migrate-format + normalize |

### Converter Coverage

| Data Type | Converter Support | Import Support | API Query Support |
|-----------|-------------------|----------------|-------------------|
| Election Events | YES (`election_events.jsonl`) | YES (`import election-events`) | YES (`GET /elections` filtered) |
| Elections (contests) | YES (`elections.jsonl`) | YES (`import elections`) | YES (`GET /elections/{id}`) |
| Candidates (persons) | NO (not implemented) | YES (`import candidates-jsonl`) | YES (`GET /candidates/{id}`) |
| Candidacies (junction) | NO (not implemented) | YES (`import candidacies`) | YES (via election detail) |

### What the Demo Can Prove

The demo can fully prove:
1. Election event data flows from markdown overview files through JSONL to the database and is queryable via `GET /api/v1/elections`
2. Election contest data (with boundary_type and district_identifier) flows through the full pipeline
3. The converter validation report explains successes, warnings, and failures
4. Dry-run mode validates without writing
5. Import is idempotent (re-importing produces no changes)
6. Auth flow works (login, JWT, authenticated queries)
7. District-based queries work (filtering by boundary_type + district_identifier)

The demo CANNOT prove (due to missing converter support):
- Candidate person-entity data flowing from `data/candidates/*.md` to the API
- Candidacy junction records linking candidates to elections

**Recommendation for handling the gap:** Document this as a known limitation. The walkthrough can still reference candidate data in the markdown files and explain that the candidate converter is planned. The pipeline architecture supports it (JSONL schemas exist, import commands exist, API endpoints exist) -- only the converter step is missing.

## Open Questions

1. **Empty UUIDs in March 10/17 files**
   - What we know: Enhanced format files have `| ID | |` (empty). The converter reads the ID field and passes it to JSONL output.
   - What's unclear: Does the JSONL validator accept empty string UUIDs? Or will conversion fail?
   - Recommendation: Run `voter-api normalize elections` on March 10/17 directories before conversion to generate UUIDs. Test conversion on March 10 first to validate.

2. **JSONL file overwrite behavior**
   - What we know: `write_jsonl()` uses `open("w")` which truncates. Each `convert directory` call overwrites `election_events.jsonl` and `elections.jsonl`.
   - What's unclear: Can we safely convert all three elections into a single output directory?
   - Recommendation: Convert each election to its own output subdirectory, then import each separately. Three `import election-data` calls in sequence.

3. **election_event_id placeholder in JSONL**
   - What we know: The converter writes `00000000-0000-0000-0000-000000000000` as `election_event_id` for all election records because it can't resolve the event ID at conversion time.
   - What's unclear: Does the import service resolve this placeholder to the actual ElectionEvent UUID?
   - Recommendation: Investigate `election_import_service.py` before the demo. If it doesn't resolve, elections will have an invalid FK reference. This could be a blocking issue.

4. **May 19 file ownership -- old vs Phase 3**
   - What we know: Git history shows `cec27f1` created original May 19 files, and `d8cd666` (Phase 3-05) updated 143 of them with minor formatting changes. NO Phase 3 commit added enhanced format metadata to May 19 files.
   - Resolved: May 19 files are original format, touched by Phase 3 for content normalization only. They need `migrate-format` before conversion. This is NOT a discrepancy -- it's the expected state.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pyproject.toml` ([tool.pytest.ini_options]) |
| Quick run command | `uv run pytest tests/unit/lib/test_converter/ -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEM-01 | Full pipeline: convert, import, query | manual walkthrough | Manual execution per `docs/pipeline-walkthrough.md` | Wave 0 |
| DEM-01 (sub) | Converter produces valid JSONL from enhanced-format MD | unit | `uv run pytest tests/unit/lib/test_converter/ -x` | YES |
| DEM-01 (sub) | Import service loads JSONL into DB | integration | `uv run pytest tests/integration/test_election_event_import.py -x` | YES |
| DEM-01 (sub) | API returns imported elections | e2e | `uv run pytest tests/e2e/ -k "TestElections" -x` | YES |

### Sampling Rate
- **Per task commit:** `uv run ruff check . && uv run ruff format --check .`
- **Per wave merge:** `uv run pytest tests/unit/lib/test_converter/ tests/integration/test_election_event_import.py -x`
- **Phase gate:** Walkthrough document is complete with real terminal output, all steps reproducible

### Wave 0 Gaps
- [ ] `docs/pipeline-walkthrough.md` -- the primary deliverable; does not exist yet
- No new test files needed -- DEM-01 is a documentation/demonstration requirement, not a code requirement. Existing tests validate the underlying components.

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection of `src/voter_api/cli/convert_cmd.py` -- converter CLI commands and migrate-format functionality
- Direct codebase inspection of `src/voter_api/cli/import_cmd.py` -- all import commands including `election-data` pipeline
- Direct codebase inspection of `src/voter_api/lib/converter/writer.py` -- confirmed converter only writes election_events.jsonl and elections.jsonl
- Direct codebase inspection of `src/voter_api/lib/converter/__init__.py` -- `_write_records_to_disk` only handles OVERVIEW and non-OVERVIEW types
- Direct codebase inspection of `src/voter_api/api/v1/elections.py` and `candidates.py` -- API endpoint signatures and query parameters
- Direct file inspection of `data/elections/2026-05-19/*.md` -- confirmed NO files have Format Version metadata
- Direct file inspection of `data/elections/2026-03-10/*.md` -- confirmed enhanced format IS present
- Direct file inspection of `data/candidates/*.md` -- confirmed 49 candidate files with enhanced format, some with empty IDs

### Secondary (MEDIUM confidence)
- Git log analysis (`d8cd666`, `cec27f1`) -- confirmed May 19 file history: original format from before better-imports, only content normalization in Phase 3
- CLI help output verification -- confirmed all commands exist and accept expected arguments

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all tools verified to exist via CLI help and source inspection
- Architecture: HIGH -- pipeline flow confirmed through source code reading
- Pitfalls: HIGH -- discovered through direct file inspection and code analysis (format gap, converter gap, overwrite behavior)
- Walkthrough content: MEDIUM -- auth flow confirmed from Phase 009 notes and code, but exact API response shapes not verified by running the commands

**Research date:** 2026-03-15
**Valid until:** 2026-04-15 (stable -- no external dependencies, all code in-repo)
