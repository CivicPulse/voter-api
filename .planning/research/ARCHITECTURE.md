# Architecture Patterns

**Domain:** Three-stage data import pipeline (SOS -> Markdown -> JSONL -> DB)
**Researched:** 2026-03-13

## Recommended Architecture

The pipeline adds three new components to the existing library-first architecture. Each stage is independently testable and can be run separately via CLI.

### High-Level Flow

```
Stage 1: AI-Assisted (Claude Code)        Stage 2: Deterministic (Python)        Stage 3: Import (Python + PostgreSQL)
+------------------------+                 +------------------------+              +------------------------+
| SOS CSV/PDF            |                 | Markdown files         |              | JSONL files            |
|   (raw government data)|                 |   (git-tracked)        |              |   (validated)          |
|                        |                 |                        |              |                        |
| /process-sos-candidates| ----human-----> | voter-api convert      | ----------> | voter-api import jsonl  |
| (Claude Code skill)    |     review      |   md-to-jsonl          |              |   (CLI or API)         |
|                        |     + commit    |   (mistune + Pydantic) |              |   (procrastinate job)  |
+------------------------+                 +------------------------+              +------------------------+
        ^                                          |                                        |
        |                                          v                                        v
   .claude/skills/                          lib/converter/                           services/jsonl_import_service.py
   (prompt templates)                       (new library)                            (calls existing UPSERT patterns)
                                                                                            |
                                                                                            v
                                                                                    PostgreSQL (elections, candidates)
```

### Component Boundaries

| Component | Responsibility | Location | Communicates With |
|-----------|---------------|----------|-------------------|
| Claude Code Skills | AI-assisted SOS data extraction into markdown | `.claude/skills/process-sos-*/` | User (interactive); reads SOS files, writes markdown |
| Markdown Normalizer | Deterministic post-processing of AI output | `lib/normalizer/` | Skills (post-process); format specs (rules) |
| Format Specs | Define markdown structure for each entity type | `data/elections/formats/` | Skills (instructions); converter (parsing rules) |
| MD-to-JSONL Converter | Parse markdown tables into validated JSONL | `lib/converter/` | Format specs; JSONL schemas; filesystem |
| JSONL Schemas | Pydantic models mirroring DB columns 1:1 | `schemas/jsonl/` | Converter (validation); import service (mapping) |
| R2 Upload Service | Generate presigned URLs; verify uploads | `lib/uploader/` or extend `lib/publisher/` | R2 (boto3); import service (trigger) |
| Procrastinate App | Job queue management | `core/jobs.py` | PostgreSQL (psycopg); import services (task execution) |
| JSONL Import Service | Stream JSONL, validate, bulk UPSERT | `services/jsonl_import_service.py` | JSONL schemas; ORM models; import_jobs table |
| Import CLI Commands | CLI interface for all pipeline stages | `cli/convert_cmd.py`, `cli/jsonl_import_cmd.py` | Services; converter library |
| Import API Routes | HTTP endpoints for upload + import | `api/v1/imports.py` (extend) | Services; R2 upload; procrastinate |

### Where New Code Lives

Following the existing library-first architecture:

```
src/voter_api/
├── lib/
│   ├── converter/           # NEW: MD -> JSONL conversion
│   │   ├── __init__.py      # Public API: convert_elections(), convert_candidates()
│   │   ├── parser.py        # mistune AST parsing of markdown tables
│   │   ├── election.py      # Election-specific extraction logic
│   │   ├── candidate.py     # Candidate-specific extraction logic
│   │   └── normalizer.py    # Deterministic text normalization (Title Case, etc.)
│   ├── uploader/            # NEW: R2 presigned URL generation (or extend publisher/)
│   │   ├── __init__.py
│   │   └── presigned.py     # generate_upload_url(), verify_upload()
│   └── ... (existing)
├── schemas/
│   └── jsonl/               # NEW: JSONL validation schemas
│       ├── __init__.py
│       ├── election.py      # ElectionJsonl Pydantic model
│       └── candidate.py     # CandidateJsonl Pydantic model
├── core/
│   └── jobs.py              # NEW: Procrastinate app + connector setup
├── services/
│   └── jsonl_import_service.py  # NEW: JSONL import orchestration
├── cli/
│   ├── convert_cmd.py       # NEW: `voter-api convert` commands
│   └── ... (extend import_cmd.py for JSONL import)
└── api/v1/
    └── imports.py           # EXTEND: presigned URL + JSONL import endpoints
```

### Data Flow

**Stage 1 (Interactive, Claude Code):**

1. User invokes `/process-sos-candidates data/new/candidates.csv` in Claude Code
2. Skill reads CSV, processes rows according to format spec in supporting files
3. Skill writes markdown files to `data/elections/YYYY-MM-DD/counties/`
4. User reviews output, runs normalizer script for deterministic cleanup
5. User commits markdown files to git

**Stage 2 (Deterministic, CLI):**

1. User runs `voter-api convert md-to-jsonl data/elections/2026-05-19/`
2. CLI calls `lib/converter/` which:
   a. Reads each markdown file
   b. Parses with `mistune.create_markdown(renderer='ast')`
   c. Walks AST to extract table data
   d. Validates each record against JSONL schema (Pydantic model)
   e. Writes validated records to JSONL file (one JSON object per line)
   f. Computes SHA256 checksum of output file
3. Output: `data/elections/2026-05-19/elections.jsonl`, `candidates.jsonl`

**Stage 3 (Import, CLI or API):**

CLI path:
1. User runs `voter-api import jsonl elections.jsonl`
2. CLI creates ImportJob record (status=pending)
3. CLI streams JSONL line-by-line, validates each line
4. Bulk UPSERT in sub-batches of 500 records
5. Updates ImportJob with counts and status

API path:
1. Client calls `POST /api/v1/imports/upload-url` with filename and content_type
2. API creates ImportJob, generates presigned PUT URL, returns both
3. Client uploads JSONL directly to R2
4. Client calls `POST /api/v1/imports/{job_id}/process`
5. API enqueues procrastinate job
6. Worker downloads from R2, streams JSONL, validates, bulk UPSERTs
7. Client polls `GET /api/v1/imports/{job_id}` for status

## Patterns to Follow

### Pattern 1: Library-First with Explicit Public API

**What:** Every new capability is a library in `lib/` with `__init__.py` exports before integration.
**When:** All new pipeline components.
**Why:** Existing architecture mandates this. Libraries must be usable without the rest of the application.

```python
# lib/converter/__init__.py
from voter_api.lib.converter.election import convert_elections
from voter_api.lib.converter.candidate import convert_candidates

__all__ = ["convert_elections", "convert_candidates"]
```

### Pattern 2: Streaming JSONL Processing

**What:** Never load entire JSONL files into memory. Process line-by-line with generators.
**When:** Any JSONL file that could grow beyond election/candidate size (voter reg, voter history in future).

```python
async def stream_jsonl(path: Path, schema: type[BaseModel]) -> AsyncIterator[dict]:
    """Stream and validate JSONL records one at a time."""
    async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
        line_num = 0
        async for line in f:
            line_num += 1
            line = line.strip()
            if not line:
                continue
            try:
                record = schema.model_validate_json(line)
                yield record.model_dump()
            except ValidationError as e:
                yield {"_error": True, "_line": line_num, "_errors": e.errors()}
```

### Pattern 3: Procrastinate Task with BackgroundTaskRunner Compatibility

**What:** Define procrastinate tasks alongside the existing BackgroundTaskRunner Protocol.
**When:** Transitioning from InProcessTaskRunner to procrastinate.

```python
# core/jobs.py
import procrastinate

procrastinate_app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(
        conninfo=settings.database_url.replace("+asyncpg", ""),
    ),
)

@procrastinate_app.task(
    name="import_jsonl",
    retry=procrastinate.RetryStrategy(max_retries=3, exponential_wait=60),
    queueing_lock="import_{file_type}",
)
async def import_jsonl_task(job_id: str, file_path: str, file_type: str):
    """Process JSONL import as a procrastinate job."""
    # ... import logic
```

### Pattern 4: Sub-Batch UPSERT with Checkpoint

**What:** Bulk UPSERT in sub-batches, updating import job progress after each batch.
**When:** All JSONL imports.
**Why:** Already proven in import_service.py. asyncpg's 32,767 parameter limit drives batch sizing.

```python
_UPSERT_SUB_BATCH = 500  # existing constant

async def _upsert_batch(session: AsyncSession, model: type, records: list[dict]):
    for i in range(0, len(records), _UPSERT_SUB_BATCH):
        sub = records[i:i + _UPSERT_SUB_BATCH]
        stmt = pg_insert(model).values(sub)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={col: stmt.excluded[col] for col in update_cols},
        )
        await session.execute(stmt)
    await session.commit()
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: AI in Stage 2

**What:** Using an LLM to parse markdown into JSONL.
**Why bad:** Non-deterministic; same markdown input could produce different JSONL; defeats the purpose of the three-stage design.
**Instead:** Use mistune AST parser. If the parser can't handle the markdown, the markdown format is wrong -- fix the format spec.

### Anti-Pattern 2: Single Transaction for Entire Import

**What:** Wrapping the full JSONL import in one database transaction.
**Why bad:** Transaction log bloat; holds locks for the entire duration; crash loses ALL progress.
**Instead:** Commit per sub-batch (500 records); checkpoint `last_processed_line` on ImportJob.

### Anti-Pattern 3: Random UUIDs for JSONL Entity IDs

**What:** Generating new UUIDs each time a JSONL file is created.
**Why bad:** Re-generating JSONL from the same markdown produces different IDs; re-import creates duplicates; cross-file FK references break.
**Instead:** Deterministic IDs from natural key hash: `uuid5(NAMESPACE, f"{date}|{district}|{party}")`.

### Anti-Pattern 4: Sharing Connection Pools Between SQLAlchemy and Procrastinate

**What:** Trying to make procrastinate use SQLAlchemy's asyncpg connection pool.
**Why bad:** procrastinate requires psycopg; driver mismatch. Mixing transaction semantics is fragile.
**Instead:** Separate pools with explicit connection budgets. Both connect to the same database independently.

## Scalability Considerations

| Concern | Elections/Candidates (now) | Voter History (next) | Statewide Voter Reg (future) |
|---------|---------------------------|---------------------|------------------------------|
| File size | <5MB JSONL | 50-100MB JSONL | 200-500MB JSONL |
| Record count | Hundreds | Millions | 7+ million |
| Import time | Seconds | Minutes | 10-30 minutes |
| Memory strategy | Can load all records | Stream line-by-line | Stream line-by-line |
| Batch size | 500 records | 500 records | 500 records (proven) |
| Job queue | Optional (CLI fine) | Required (too slow for API) | Required |
| R2 upload | Optional (small files) | Recommended | Required |
| Index management | Not needed | Drop/rebuild GIN indexes | Drop/rebuild all indexes |
| Concurrency | Single job fine | Single job fine | Single job (lock contention) |

## Sources

- Existing architecture in `.planning/codebase/ARCHITECTURE.md`
- Existing `import_service.py` bulk UPSERT patterns
- Existing `background.py` BackgroundTaskRunner Protocol
- [Procrastinate FastAPI worker integration](https://procrastinate.readthedocs.io/en/stable/howto/basics/worker.html)
- [Claude Code Skills docs](https://code.claude.com/docs/en/skills)
- [Mistune AST renderer](https://mistune.lepture.com/en/latest/guide.html)
- [Mistune table AST tokens](https://mistune.lepture.com/en/latest/advanced.html)

---

*Architecture research: 2026-03-13*
