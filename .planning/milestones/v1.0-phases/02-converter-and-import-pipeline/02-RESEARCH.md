# Phase 2: Converter and Import Pipeline - Research

**Researched:** 2026-03-15
**Domain:** Markdown parsing, JSONL pipeline, Alembic data migration, CLI tooling
**Confidence:** HIGH

## Summary

Phase 2 builds the runtime pipeline that converts human-reviewed markdown election files into validated JSONL and loads them into the database. It spans three plans: (1) DB migrations to support the new candidate/candidacy model and ElectionEvent enhancements, (2) a `lib/converter/` library using mistune AST parsing to deterministically transform markdown to JSONL, and (3) import CLI commands that upsert JSONL records into the database plus a file migration script for the ~200 existing legacy markdown files.

The codebase has mature patterns for all required components. CLI commands follow the Typer pattern in `cli/import_cmd.py` (asyncio.run wrapper, init_engine/dispose_engine lifecycle). Import services use PostgreSQL bulk UPSERT (`INSERT ON CONFLICT DO UPDATE`) with sub-batching. Libraries follow the `lib/` package pattern with `__init__.py` public API. Alembic migrations have 50 existing revisions as precedent. The four JSONL Pydantic schemas from Phase 1 (`ElectionEventJSONL`, `ElectionJSONL`, `CandidateJSONL`, `CandidacyJSONL`) are the validation targets.

The converter is the novel component. It must parse markdown AST via mistune 3.2.0 (with table plugin), extract metadata tables, candidate tables, and heading structure, then map Body/Seat references to boundary_type/district_identifier using county reference file lookups. The 159 county reference files currently exist as metadata-only stubs (no Governing Bodies tables except Bibb); all must be populated before the converter can fully process county contest files.

**Primary recommendation:** Follow the three-plan split from CONTEXT.md. Plan 02-01 handles migrations first (unblocking the model changes). Plan 02-02 builds `lib/converter/` and populates county reference files. Plan 02-03 builds import services and the file migration script.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Converter CLI Design**: Directory-first invocation (`voter-api convert <dir>`), output to sibling `jsonl/` subdirectory, validation report (terminal table + JSON file), continue-and-report default with `--fail-fast` flag.
- **Converter Library Design**: New `lib/converter/` package. Body/Seat resolution via county reference file lookup. Statewide/federal bodies use built-in mapping. Unresolved = validation error. MD-to-JSONL only; import (JSONL-to-DB) lives in services.
- **Import Command Granularity**: Four individual commands (`import election-events`, `import elections`, `import candidates`, `import candidacies`) plus one pipeline command (`import election-data <dir>`). Dry-run mode. Idempotent upsert by UUID.
- **DB Migration Sequencing**: Additive-first approach. Add candidacies table alongside existing candidates. Alembic migration copies existing candidate data to candidacy records. API schemas updated in Phase 2. Four migrations bundled into one deploy. Data migration in Alembic SQL. Existing candidate import updated in Plan 02-01.
- **Existing File Migration**: Fully automated CLI command (`voter-api convert migrate-format <dir>`). UUID backfill matches by natural key. Git commit strategy: one per file type. Candidate stubs deferred to Phase 3.
- **County Reference Files**: Populate all 159 counties in Phase 2 using Claude skill approach. Included in Plan 02-02.
- **Plan Splitting**: Three plans -- 02-01 (DB Migrations & Model Refactoring), 02-02 (Converter Library), 02-03 (Import Pipeline & File Migration).
- **mistune AST parsing**: Deterministic markdown parser (CNV-01).

### Claude's Discretion
- Converter internal architecture (submodule breakdown within lib/converter/)
- mistune AST parsing implementation details
- Exact Alembic migration SQL for data migration
- Import batch size defaults and performance tuning
- Error message formatting in validation reports
- County reference file population order and batching

### Deferred Ideas (OUT OF SCOPE)
- Candidate stub file creation -- deferred to Phase 3
- Round-trip validation (MD -> JSONL -> DB -> export matches original) -- v2 requirement (EXT-04)
- API import endpoints (HTTP wrappers around CLI) -- v2 requirement (INF-03)
- Import progress reporting (WebSocket/polling) -- v2 requirement (INF-04)
- R2 signed URL upload -- v2 requirement (INF-02)
- Procrastinate job queue -- v2 requirement (INF-01)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CNV-01 | Deterministic markdown parser using mistune AST converts election markdown files to JSONL without AI | mistune 3.2.0 with table plugin provides AST parsing. `renderer=None` or `renderer='ast'` returns token lists. Verified in official docs. |
| CNV-02 | Parsed output is validated against Pydantic models matching the JSONL schema before writing | Four Pydantic v2 models exist at `schemas/jsonl/` -- ElectionEventJSONL, ElectionJSONL, CandidateJSONL, CandidacyJSONL. Validate with `model_validate()`. |
| CNV-03 | Batch conversion processes an entire election directory in a single command | Directory walking + file type detection by path pattern. Overview at root, single-contest at root, multi-contest in `counties/` subdirectory. |
| CNV-04 | Conversion produces a validation report summarizing parse successes, failures, and missing fields | Established pattern in `import all-boundaries` (summary table, exit code 1 on failures). JSON report file is new but straightforward. |
| IMP-01 | CLI command `voter-api import elections <file.jsonl>` loads election records into the database | Follow existing `import candidates` CLI pattern. New service with `pg_insert().on_conflict_do_update()`. |
| IMP-02 | CLI command `voter-api import candidates <file.jsonl>` loads candidate records into the database | Existing `import candidates` command must be updated for new person+candidacy model, plus new `import candidacies` command. |
| IMP-03 | Import is idempotent -- re-importing produces no duplicates or data changes | UPSERT on UUID primary key. Existing pattern uses `RETURNING (xmax = 0)::int` to distinguish inserts from updates. |
| IMP-04 | Import supports dry-run mode | Existing pattern in `import election-results --dry-run`: validate without writing, report counts. New imports follow same approach. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mistune | 3.2.0 | Markdown AST parsing | Locked decision (CNV-01). Fast pure-Python parser with table plugin. AST mode returns structured tokens. |
| Pydantic v2 | (existing) | JSONL validation | Four schemas already defined in Phase 1. `model_validate()` for validation. |
| SQLAlchemy 2.x async | (existing) | ORM + database ops | Project standard. Async session pattern. |
| Alembic | (existing) | Database migrations | 50 existing migrations as precedent. |
| Typer | (existing) | CLI framework | Established pattern in `cli/` directory. |
| asyncpg | (existing) | PostgreSQL driver | Required for `pg_insert().on_conflict_do_update()` dialect. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Loguru | (existing) | Structured logging | All service and library code. |
| uuid (stdlib) | -- | UUID generation | Backfill command generates UUID v4 for unmatched records. |
| pathlib (stdlib) | -- | File path handling | Directory traversal, file type detection. |
| json (stdlib) | -- | JSONL writing | One JSON object per line, `json.dumps()`. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| mistune | markdown-it-py | mistune is faster and simpler for AST-only use. markdown-it-py is closer to CommonMark spec but heavier. mistune is the locked decision. |
| Manual JSONL writing | jsonlines library | stdlib `json.dumps()` is sufficient for writing one object per line. No need for external dependency. |

**Installation:**
```bash
uv add mistune
```

## Architecture Patterns

### Recommended Project Structure
```
src/voter_api/
├── lib/
│   └── converter/              # NEW: MD -> JSONL conversion library
│       ├── __init__.py          # Public API: convert_directory(), convert_file()
│       ├── parser.py            # mistune AST parsing, metadata/table extraction
│       ├── writer.py            # JSONL file writing with Pydantic validation
│       ├── resolver.py          # Body/Seat -> boundary_type resolution
│       ├── report.py            # Validation report generation (terminal + JSON)
│       └── types.py             # Internal dataclasses (ParseResult, ConversionReport, etc.)
├── services/
│   ├── election_event_import_service.py    # NEW: ElectionEvent JSONL -> DB
│   ├── election_import_service.py          # NEW: Election JSONL -> DB
│   ├── candidate_import_service.py         # UPDATED: for new person model
│   └── candidacy_import_service.py         # NEW: Candidacy JSONL -> DB
├── cli/
│   ├── convert_cmd.py           # NEW: voter-api convert
│   └── import_cmd.py            # UPDATED: new import subcommands
└── models/
    ├── candidate.py             # UPDATED: person-level fields, remove election_id (optional)
    ├── candidacy.py             # NEW: candidacy junction table model
    ├── election.py              # UPDATED: add election_stage, remove calendar fields
    └── election_event.py        # UPDATED: add calendar/feed fields
```

### Pattern 1: Markdown AST Parsing with mistune
**What:** Parse markdown to structured token list, extract metadata tables and headings.
**When to use:** All converter parsing operations.
**Example:**
```python
# Source: mistune official docs (https://mistune.lepture.com/en/latest/guide.html)
import mistune

md = mistune.create_markdown(renderer=None, plugins=['table'])

# Parse returns list of token dicts
tokens = md(markdown_text)

# Token structure:
# {'type': 'heading', 'attrs': {'level': 1}, 'children': [...]}
# {'type': 'table', 'children': [{'type': 'table_head', ...}, {'type': 'table_body', ...}]}
```

### Pattern 2: Metadata Table Extraction
**What:** Extract key-value pairs from markdown `| Field | Value |` tables.
**When to use:** Reading ID, Format Version, Type, Body, Seat, etc. from metadata sections.
**Example:**
```python
def extract_metadata_table(tokens: list[dict]) -> dict[str, str]:
    """Extract first metadata table (| Field | Value |) from AST tokens."""
    metadata = {}
    for token in tokens:
        if token['type'] == 'table':
            # table has table_head (header row) and table_body (data rows)
            head = token['children'][0]  # table_head
            body = token['children'][1]  # table_body
            for row in body['children']:
                cells = row['children']
                if len(cells) >= 2:
                    field = _extract_text(cells[0])
                    value = _extract_text(cells[1])
                    metadata[field.strip()] = value.strip()
            break  # first table only for metadata
    return metadata
```

### Pattern 3: JSONL Import Service (UPSERT by UUID)
**What:** Read JSONL file, validate each line against Pydantic model, bulk upsert to DB by UUID.
**When to use:** All four import commands.
**Example:**
```python
# Follows existing pattern from candidate_import_service.py and import_service.py
from sqlalchemy.dialects.postgresql import insert as pg_insert

async def upsert_election_event_batch(session: AsyncSession, records: list[dict]) -> tuple[int, int]:
    """Bulk upsert ElectionEvent records using INSERT ... ON CONFLICT DO UPDATE."""
    stmt = pg_insert(ElectionEvent).values(records)
    update_set = {col: stmt.excluded[col] for col in UPDATE_COLUMNS}
    stmt = stmt.on_conflict_do_update(
        index_elements=["id"],  # upsert on UUID primary key
        set_=update_set,
    )
    stmt = stmt.returning(
        ElectionEvent.__table__.c.id,
        literal_column("(xmax = 0)::int").label("is_insert"),
    )
    result = await session.execute(stmt)
    rows = result.all()
    inserted = sum(row.is_insert for row in rows)
    return inserted, len(rows) - inserted
```

### Pattern 4: CLI Command Registration
**What:** Add new subcommand groups to the Typer app.
**When to use:** `convert` command group and new import subcommands.
**Example:**
```python
# In cli/app.py, add to _register_subcommands():
from voter_api.cli.convert_cmd import convert_app
app.add_typer(convert_app, name="convert", help="Markdown to JSONL conversion")

# In cli/convert_cmd.py:
convert_app = typer.Typer()

@convert_app.command("directory")
def convert_directory(
    directory: Path = typer.Argument(..., help="Election directory", exists=True),
    output: Path | None = typer.Option(None, "--output", help="Output directory"),
    fail_fast: bool = typer.Option(False, "--fail-fast"),
) -> None:
    """Convert election markdown directory to JSONL files."""
    # No asyncio.run needed -- converter is synchronous (no DB access)
    ...
```

### Anti-Patterns to Avoid
- **AI in the converter:** CNV-01 explicitly requires "without AI." The converter must be deterministic -- same input always produces same output. No LLM calls.
- **UUID generation in the converter:** Per uuid-strategy.md, the converter MUST NOT generate UUIDs. It reads them from markdown. Missing/invalid UUID = validation error.
- **Calendar fields on Election model:** Calendar dates are moving to ElectionEvent. The converter must emit them on ElectionEventJSONL, not ElectionJSONL.
- **Mixing converter and import:** lib/converter/ handles MD-to-JSONL only. It has no database dependency. Import services are separate.
- **Non-idempotent imports:** Every import must use UPSERT on UUID. Re-importing same JSONL = same DB state.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Markdown parsing | Custom regex-based parser | mistune 3.2.0 with table plugin | Markdown has edge cases (nested tables, escaped pipes, multiline cells). mistune handles CommonMark correctly. |
| Pydantic validation | Manual field checking | `model_validate()` on JSONL schemas | Schemas already defined in Phase 1. Pydantic gives typed errors with field paths. |
| PostgreSQL UPSERT | SELECT-then-INSERT/UPDATE | `pg_insert().on_conflict_do_update()` | Atomic, no race conditions, returns insert/update distinction via xmax. Established project pattern. |
| UUID validation | Regex matching | `uuid.UUID(value)` in stdlib | Handles all UUID formats, raises ValueError on invalid. |
| File path resolution | String manipulation | `pathlib.Path` | Cross-platform, handles relative paths, `.resolve()` for absolute. |

**Key insight:** The project already has every infrastructure pattern needed (CLI, services, models, migrations). The converter library is the only genuinely new component, and mistune provides the hard part (AST parsing).

## Common Pitfalls

### Pitfall 1: mistune Table Token Structure
**What goes wrong:** Assuming table tokens have a flat cell structure. mistune 3 nests cells within rows within head/body sections.
**Why it happens:** Token structure is not obvious from the docs.
**How to avoid:** Parse with `renderer=None`, print the raw token tree for a sample table, and build extraction logic from actual output structure. Write unit tests against known markdown inputs.
**Warning signs:** `KeyError` or empty results when extracting table data.

### Pitfall 2: Candidate Model Refactoring Breaks Existing Tests
**What goes wrong:** Changing the Candidate model (removing election_id, adding person fields) breaks 162+ E2E tests and many unit tests.
**Why it happens:** The current model has `election_id` as NOT NULL with a unique constraint on `(election_id, full_name)`. The new model changes this relationship.
**How to avoid:** Use additive-first migration: add new columns and tables FIRST, keep old columns, update tests incrementally. The CONTEXT.md specifies this approach.
**Warning signs:** E2E test failures after migration. Seed data in conftest.py using the old model shape.

### Pitfall 3: County Reference File Stub State
**What goes wrong:** Converter attempts Body/Seat resolution but 158 of 159 county reference files lack Governing Bodies tables.
**Why it happens:** Only Bibb county was fully populated in Phase 1. The rest are metadata-only stubs.
**How to avoid:** Populate all 159 county reference files in Plan 02-02 BEFORE converter testing against real data. The converter should handle missing Governing Bodies gracefully (validation warning, not crash).
**Warning signs:** Converter works for Bibb but fails for all other counties.

### Pitfall 4: Legacy Format Variations in Existing Files
**What goes wrong:** The ~200 existing markdown files have inconsistencies: different column counts, mixed date formats, em-dash vs hyphen, missing sections.
**Why it happens:** Files were created manually or by different AI sessions with slightly different formatting.
**How to avoid:** The migration script must be defensive: detect the actual column count (5 or 7), handle both date formats (ISO and "Month D, YYYY"), normalize em-dashes. Write the migration script to process all files and report issues rather than crashing on the first malformed file.
**Warning signs:** Migration works on Bibb/Governor test files but fails on lesser-known counties.

### Pitfall 5: Multi-Contest County Files Have No Per-Contest UUIDs
**What goes wrong:** In multi-contest county files, the file-level `| ID |` identifies the county grouping, not individual contests. Individual contests need separate Election UUIDs.
**Why it happens:** Per uuid-strategy.md, contest-level UUIDs in multi-contest files "are resolved during conversion via the contest name + election event pairing."
**How to avoid:** The converter needs to handle multi-contest files differently: the file-level ID is for the county grouping, each `### Contest Name` heading generates a separate ElectionJSONL record. The Election UUID for each contest comes from the contest's own identity, not the file ID.
**Warning signs:** All contests in a county file sharing the same UUID.

### Pitfall 6: asyncpg Parameter Limit
**What goes wrong:** Bulk UPSERT with too many rows exceeds asyncpg's 32,767 parameter limit.
**Why it happens:** Each row adds N parameters where N is the column count. ElectionEvent has ~14 columns, so 32767/14 = ~2340 max rows per batch.
**How to avoid:** Sub-batch at 500 rows (matching existing `_UPSERT_SUB_BATCH = 500` pattern). This gives a safe margin: 500 * 20 columns = 10,000 params.
**Warning signs:** `asyncpg.TooManyParametersError` during import.

### Pitfall 7: Overview File Format Already Partially Migrated
**What goes wrong:** The existing 2026-05-19 overview file already has some enhanced format features (Calendar table with Source column, ISO dates) but lacks others (no ID, no Format Version, no Type/Stage).
**Why it happens:** The overview was manually updated during Phase 1 development.
**How to avoid:** Migration script must detect whether specific features are already present (check for `Format Version` row) and only add what's missing. Idempotency is critical.
**Warning signs:** Migration produces duplicate metadata rows or corrupts already-migrated sections.

## Code Examples

### JSONL File Reading with Pydantic Validation
```python
# Pattern for reading JSONL with per-line validation
import json
from pathlib import Path
from pydantic import ValidationError
from voter_api.schemas.jsonl import ElectionEventJSONL

def read_jsonl(path: Path, model_class: type) -> tuple[list, list[dict]]:
    """Read JSONL file, validate each line. Returns (valid_records, errors)."""
    valid = []
    errors = []
    with path.open() as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                record = model_class.model_validate(data)
                valid.append(record.model_dump())
            except (json.JSONDecodeError, ValidationError) as e:
                errors.append({"line": line_num, "error": str(e)})
    return valid, errors
```

### JSONL File Writing
```python
# Pattern for writing validated JSONL output
import json
from pathlib import Path

def write_jsonl(path: Path, records: list[dict]) -> int:
    """Write records as JSONL. Returns count written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for record in records:
            f.write(json.dumps(record, default=str) + "\n")
    return len(records)
```

### Alembic Data Migration Pattern
```python
# Pattern for data migration within Alembic (SQL, not ORM)
# Source: project precedent in existing migrations
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    # 1. Create new table
    op.create_table("candidacies", ...)

    # 2. Copy data from old columns to new table
    op.execute("""
        INSERT INTO candidacies (id, candidate_id, election_id, party, filing_status, ...)
        SELECT gen_random_uuid(), c.id, c.election_id, c.party, c.filing_status, ...
        FROM candidates c
        WHERE c.election_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)

    # 3. Make old FK nullable (don't drop yet -- additive-first)
    op.alter_column("candidates", "election_id", nullable=True)
```

### Body/Seat Resolution from County Reference Files
```python
# Pattern for reading county reference files and resolving Body -> boundary_type
from pathlib import Path

def load_county_reference(county_file: Path) -> dict[str, str]:
    """Parse county reference file, return {body_id: boundary_type} mapping."""
    # Uses same mistune AST parsing as the converter
    # Finds the Governing Bodies table and extracts Body ID -> boundary_type
    ...

# Built-in statewide/federal mapping (no county file needed)
STATEWIDE_BODIES: dict[str, str] = {
    "ga-governor": "county",        # statewide = county boundary_type
    "ga-lt-governor": "county",
    "ga-sos": "county",
    "ga-ag": "county",
    "ga-us-senate": "us_senate",
    "ga-us-house": "congressional",
    "ga-state-senate": "state_senate",
    "ga-state-house": "state_house",
    "ga-psc": "psc",
    # ... etc
}
```

### Dry-Run Mode Pattern
```python
# Pattern from existing import election-results --dry-run
async def import_with_dry_run(
    session: AsyncSession,
    records: list[dict],
    dry_run: bool,
) -> dict:
    """Validate and optionally import records."""
    # Check for existing records (would-insert vs would-update)
    existing_ids = set()
    result = await session.execute(
        select(Model.id).where(Model.id.in_([r["id"] for r in records]))
    )
    existing_ids = {row.id for row in result.all()}

    would_insert = [r for r in records if r["id"] not in existing_ids]
    would_update = [r for r in records if r["id"] in existing_ids]

    if dry_run:
        return {"would_insert": len(would_insert), "would_update": len(would_update)}

    # Real import
    inserted, updated = await upsert_batch(session, records)
    return {"inserted": inserted, "updated": updated}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Candidate tied to election (election_id FK) | Candidate = person entity, Candidacy = junction | Phase 2 | Model refactoring, API schema changes, migration |
| Calendar dates on Election model | Calendar dates on ElectionEvent | Phase 2 | Fields move via Alembic migration |
| Manual candidate CSV preprocessing | MD -> JSONL -> DB pipeline | Phase 2 | Deterministic, version-controlled, reproducible |
| 7-column candidate tables (with Email/Website) | 5-column tables (Email/Website on candidate files) | Phase 1 spec, Phase 2 migration | Existing files need column drop |

**Deprecated/outdated:**
- `import preprocess-candidates` / `import preprocess-all-candidates`: These commands use the old candidate CSV-to-JSONL path. They remain functional but the new pipeline replaces them for structured election data.
- Current `import candidates` command: Works with old model shape. Must be updated in Plan 02-01 for new person+candidacy model.

## Open Questions

1. **Multi-contest county file Election UUID resolution**
   - What we know: File-level ID = county grouping. Per-contest UUIDs resolved "during conversion via contest name + election event pairing."
   - What's unclear: The exact mechanism. Does each `### Contest Name` in a county file get a separate Election UUID from the backfill step? Or does the converter generate them deterministically?
   - Recommendation: Per uuid-strategy.md, the converter NEVER generates UUIDs. The backfill command must handle multi-contest files: each contest gets its own UUID written to an auxiliary mapping file. Alternatively, the migration script creates individual single-contest files for each county contest. Implement whichever approach the planner chooses, but the converter must read UUIDs, not generate them.

2. **Statewide body boundary_type values**
   - What we know: Statewide offices (Governor, AG, etc.) don't have a per-county boundary_type. The boundary_type should represent the geographic scope.
   - What's unclear: What boundary_type value maps to statewide offices? There's no "statewide" in the BoundaryType enum.
   - Recommendation: Use `county` boundary_type for statewide offices (voters are scoped by county registration) or leave `boundary_type` null for statewide races. The built-in mapping in the converter should document this decision.

3. **ElectionEvent model enhancement scope**
   - What we know: ElectionEvent currently has only `event_date`, `event_name`, `event_type` in the DB. The JSONL schema has calendar fields and feed fields.
   - What's unclear: How many new columns need to be added to the DB model via migration.
   - Recommendation: Add all calendar/feed fields from ElectionEventJSONL to the ORM model and DB table: `registration_deadline`, `early_voting_start`, `early_voting_end`, `absentee_request_deadline`, `qualifying_start`, `qualifying_end`, `data_source_url`, `last_refreshed_at`, `refresh_interval_seconds`. Plus move corresponding fields OFF the Election model.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (existing) |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/unit/lib/test_converter/ -x` |
| Full suite command | `uv run pytest --cov=voter_api --cov-report=term-missing` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CNV-01 | mistune AST parsing produces correct JSONL from markdown | unit | `uv run pytest tests/unit/lib/test_converter/ -x` | Wave 0 |
| CNV-02 | Parsed output validates against Pydantic JSONL models | unit | `uv run pytest tests/unit/lib/test_converter/test_writer.py -x` | Wave 0 |
| CNV-03 | Batch conversion processes entire election directory | unit + integration | `uv run pytest tests/unit/lib/test_converter/test_directory.py -x` | Wave 0 |
| CNV-04 | Conversion produces validation report | unit | `uv run pytest tests/unit/lib/test_converter/test_report.py -x` | Wave 0 |
| IMP-01 | `import elections` loads JSONL into DB | integration | `uv run pytest tests/integration/test_election_import.py -x` | Wave 0 |
| IMP-02 | `import candidates` loads JSONL into DB | integration | `uv run pytest tests/integration/test_candidate_import.py -x` | Wave 0 |
| IMP-03 | Re-import produces no duplicates | integration | `uv run pytest tests/integration/ -k "idempotent" -x` | Wave 0 |
| IMP-04 | Dry-run validates without writing | integration | `uv run pytest tests/integration/ -k "dry_run" -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/lib/test_converter/ -x` (converter tasks) or `uv run pytest tests/integration/ -k "import" -x` (import tasks)
- **Per wave merge:** `uv run pytest --cov=voter_api --cov-report=term-missing`
- **Phase gate:** Full suite green + E2E green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/lib/test_converter/` -- entire test directory for new converter library
- [ ] `tests/unit/lib/test_converter/test_parser.py` -- covers CNV-01 (mistune AST parsing)
- [ ] `tests/unit/lib/test_converter/test_writer.py` -- covers CNV-02 (Pydantic validation)
- [ ] `tests/unit/lib/test_converter/test_resolver.py` -- covers Body/Seat resolution
- [ ] `tests/unit/lib/test_converter/test_directory.py` -- covers CNV-03 (batch processing)
- [ ] `tests/unit/lib/test_converter/test_report.py` -- covers CNV-04 (validation report)
- [ ] `tests/integration/test_election_event_import.py` -- covers IMP-01 (election event import)
- [ ] `tests/integration/test_election_import.py` -- covers IMP-01 (election import)
- [ ] `tests/integration/test_candidacy_import.py` -- covers IMP-02 (candidacy import)
- [ ] Framework install: `uv add mistune` -- mistune not yet in dependencies
- [ ] E2E tests need seed data updates for new candidacy model after migration

## Sources

### Primary (HIGH confidence)
- **Codebase inspection** -- All existing patterns (CLI, services, models, migrations) verified by reading source files
- **Phase 1 deliverables** -- JSONL schemas at `src/voter_api/schemas/jsonl/`, format specs at `docs/formats/`, process specs at `docs/formats/specs/`
- **02-CONTEXT.md** -- All locked decisions verified against codebase feasibility
- **mistune official docs** -- https://mistune.lepture.com/en/latest/guide.html (AST mode, table plugin)
- **mistune PyPI** -- https://pypi.org/project/mistune/ (version 3.2.0, Python 3.8+)

### Secondary (MEDIUM confidence)
- **mistune token structure** -- AST token nesting for tables (table -> table_head/table_body -> rows -> cells) confirmed by docs but exact attribute names should be verified by running test parse

### Tertiary (LOW confidence)
- None. All findings verified against codebase or official sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- mistune 3.2.0 verified on PyPI, all other libraries already in project
- Architecture: HIGH -- all patterns (CLI, services, lib/) have established precedent in the codebase
- Pitfalls: HIGH -- identified from actual codebase state (158 stub county files, 7-column legacy tables, E2E test coupling)
- Migration: HIGH -- Alembic patterns well-established with 50 existing migrations

**Research date:** 2026-03-15
**Valid until:** 2026-04-15 (stable domain, no fast-moving dependencies)
