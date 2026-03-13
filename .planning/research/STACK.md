# Technology Stack

**Project:** Better Imports (Three-Stage Data Import Pipeline)
**Researched:** 2026-03-13

## Recommended Stack

This covers only NEW dependencies needed for the import pipeline. The existing stack (FastAPI, SQLAlchemy 2.x async, asyncpg, Pydantic v2, boto3, Alembic) is retained as-is.

### Stage 1: AI-Assisted SOS Data Processing (Claude Code Skills)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Claude Code Skills | current | Slash commands that process raw SOS CSVs/PDFs into structured markdown | Already the user's primary workflow tool; skills are markdown files with YAML frontmatter in `.claude/skills/`; no runtime dependency -- skills are prompt instructions, not code |
| `$ARGUMENTS` substitution | current | Pass file paths and parameters to skills | Built-in string substitution in skill content; `$0`, `$1` syntax for positional args |

**Confidence:** HIGH -- verified via official Claude Code docs at code.claude.com/docs/en/skills

**Rationale:** Skills are the right fit because Stage 1 is inherently interactive and AI-assisted. The user runs `/process-sos-data data/new/candidates.csv` in Claude Code, reviews the generated markdown, and commits it to git. No server-side library needed. Skills support:

- `disable-model-invocation: true` to prevent auto-triggering
- Supporting files (templates, format specs, validation scripts) in the skill directory
- `!`command`` syntax for dynamic context injection (e.g., reading existing format specs)
- `allowed-tools` to restrict file operations

**Skill structure:**
```
.claude/skills/
  process-sos-candidates/
    SKILL.md                    # Main instructions
    templates/county.md         # Template for county files
    examples/sample-output.md   # Example output
  process-sos-elections/
    SKILL.md
    templates/overview.md
```

**Not using custom commands (`.claude/commands/`)** -- skills supersede commands and add frontmatter control, supporting files, and subagent execution. Existing commands in the project still work but new work should use skills.

### Stage 2: Markdown to JSONL Conversion

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| mistune | >= 3.2.0 | Parse structured markdown into AST | Zero external dependencies, fast (3.6s vs 9s for markdown-it-py in benchmarks), AST renderer mode gives dict-based token tree, table plugin built-in, actively maintained (v3.2.0 released Dec 2025) |
| Pydantic v2 | >= 2.0.0 (existing) | Validate JSONL records against DB model schemas | Already in stack; `model_validate_json()` for per-line validation; Rust core gives 5-50x v1 performance |

**Confidence:** HIGH for mistune (verified via PyPI, official docs). HIGH for Pydantic (already in stack).

**Rationale for mistune over alternatives:**

| Library | Why Not |
|---------|---------|
| markdown-it-py | 2.5x slower than mistune in benchmarks; CommonMark compliance is irrelevant for our deterministic format |
| python-markdown | Extension-based architecture adds complexity; no native AST mode |
| marko | Less mature ecosystem; fewer downloads |
| regex/manual parsing | Fragile; markdown edge cases in links, em-dashes, pipes within cells |

**How mistune AST works for our tables:**
```python
import mistune

md = mistune.create_markdown(renderer='ast')
tokens = md(content)
# Walk tokens looking for type='table'
# table -> table_head (cells with attrs['head']=True)
# table -> table_body -> table_row -> table_cell
# Each cell has children with type='text' containing raw values
```

The AST gives us typed dict tokens with `type`, `children`, and `attrs` fields. Table cells include alignment info via `attrs['align']`. This is deterministic -- same input always produces same AST, which is exactly what Stage 2 requires.

**JSONL output format:** One JSON object per line, fields mirror DB model columns 1:1. Each line validated by a Pydantic model before writing. Standard library `json.dumps()` for serialization -- no extra dependency needed.

### Stage 3a: File Upload (Cloudflare R2 Signed URLs)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| boto3 | >= 1.42.47 (existing) | Generate presigned PUT URLs for R2 | Already in stack for R2 publishing; `generate_presigned_url('put_object', ...)` works with R2's S3-compatible API |
| botocore | (transitive via boto3) | S3 client configuration | Handles SigV4 signing; `request_checksum_calculation="when_required"` already configured in `create_r2_client()` |

**Confidence:** HIGH -- existing `lib/publisher/storage.py` already has a working R2 client factory. Presigned URLs are standard S3 API, verified via Cloudflare R2 docs.

**Rationale:** No new library needed. The existing `create_r2_client()` returns a boto3 S3 client that supports `generate_presigned_url()`. The upload endpoint generates a presigned PUT URL, the client uploads directly to R2, then notifies the API that the upload is complete.

**Key constraints from R2 docs:**
- Max presigned URL expiry: 7 days (604,800 seconds); use 1 hour for uploads
- Presigned URLs only work on S3 API domain (`<ACCOUNT_ID>.r2.cloudflarestorage.com`), NOT custom domains
- PUT supported; POST multipart form NOT supported by R2 presigned URLs
- If `ContentType` is specified in signing, client MUST send matching `Content-Type` header or get 403
- Presigned URLs are bearer tokens -- anyone with the URL can upload until expiry

**Implementation pattern:**
```python
# API endpoint: POST /api/v1/imports/upload-url
url = client.generate_presigned_url(
    'put_object',
    Params={
        'Bucket': settings.r2_bucket,
        'Key': f'imports/{job_id}/{filename}',
        'ContentType': 'application/x-ndjson',
    },
    ExpiresIn=3600,  # 1 hour
)
# Return URL + job_id to client
# Client uploads directly to R2
# Client calls POST /api/v1/imports/{job_id}/complete to trigger processing
```

### Stage 3b: PostgreSQL Job Queue

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| procrastinate | >= 3.7.2 | Persistent async job queue for JSONL import processing | PostgreSQL-native (no Redis); async-first with psycopg v3; retries, locks, periodic tasks built-in; MIT licensed; actively maintained (v3.7.2 Jan 2026) |
| psycopg[pool] | >= 3.3.2 | Async PostgreSQL driver for procrastinate | Required by procrastinate's PsycopgConnector; provides AsyncConnectionPool |

**Confidence:** MEDIUM -- procrastinate is well-documented and actively maintained, but introducing psycopg alongside asyncpg adds a second PostgreSQL driver. This is architecturally acceptable because procrastinate manages its own connection pool independently of SQLAlchemy.

**Rationale for procrastinate over alternatives:**

| Library | Why Not |
|---------|---------|
| PGQueuer | Younger project (fewer releases); less documentation; no Django/framework integration to reference |
| Celery + Redis | Adds Redis infrastructure dependency; overkill for this use case; violates "PostgreSQL-native" constraint |
| ARQ + Redis | Same Redis problem as Celery |
| asyncio.create_task (existing) | No persistence, no retries, no crash recovery; lost on server restart; semaphore-limited to 2; adequate for current imports but insufficient for pipeline |
| Dramatiq + Redis/RabbitMQ | External broker dependency |

**Integration architecture:**

1. **Separate connection pool**: Procrastinate uses `PsycopgConnector` with its own `AsyncConnectionPool` connecting to the SAME PostgreSQL database. This is a separate pool from SQLAlchemy's asyncpg pool. Both connect to the same DB, but through different drivers.

2. **Schema management**: Procrastinate creates its own tables (`procrastinate_jobs`, `procrastinate_events`, `procrastinate_periodic_defers`). Initial schema applied via `procrastinate schema --apply` or wrapped in an Alembic migration using raw SQL (`op.execute()`). Future procrastinate schema updates are pure SQL scripts that can be wrapped in Alembic migrations.

3. **FastAPI lifespan integration**:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with procrastinate_app.open_async():
        worker_task = asyncio.create_task(
            procrastinate_app.run_worker_async(install_signal_handlers=False)
        )
        yield
        worker_task.cancel()
```

4. **Custom schema support**: Procrastinate supports PostgreSQL `search_path` via connector options (`-c search_path=myschema`), which aligns with the existing `DATABASE_SCHEMA` env var for PR preview environments.

**Why two PostgreSQL drivers is acceptable:**
- procrastinate requires psycopg v3 -- it has no asyncpg connector
- asyncpg remains the SQLAlchemy driver for all ORM/application queries
- psycopg is only used by procrastinate for job queue operations
- The two pools are independent; no connection sharing needed
- This is a common pattern in Python projects that mix ORMs with specialized PostgreSQL tooling

### Stage 3c: JSONL Processing and Bulk Database Loading

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| SQLAlchemy 2.x async | >= 2.0.0 (existing) | Bulk UPSERT via `insert().on_conflict_do_update()` | Already proven in `import_service.py` for voter imports; dialect-specific `pg_insert` supports `RETURNING` |
| asyncpg | >= 0.30.0 (existing) | Async PostgreSQL driver for SQLAlchemy | Already in stack; 32,767 parameter limit drives sub-batch sizing |
| Pydantic v2 | >= 2.0.0 (existing) | Per-record validation during JSONL ingestion | `model_validate_json()` for streaming line-by-line validation |

**Confidence:** HIGH -- this is the exact pattern already used in the existing voter import pipeline.

**No new dependencies needed.** The existing bulk UPSERT pattern from `import_service.py` is directly reusable:

```python
# Existing proven pattern:
from sqlalchemy.dialects.postgresql import insert as pg_insert

stmt = pg_insert(Election).values(records)
stmt = stmt.on_conflict_do_update(
    index_elements=["id"],
    set_={col: stmt.excluded[col] for col in update_columns},
)
result = await session.execute(stmt)
```

**JSONL processing pattern:**
```python
# Stream JSONL line-by-line (memory efficient)
async with aiofiles.open(jsonl_path) as f:
    batch = []
    async for line in f:
        record = ElectionJsonlSchema.model_validate_json(line)
        batch.append(record.model_dump())
        if len(batch) >= BATCH_SIZE:
            await _upsert_batch(session, batch)
            batch.clear()
    if batch:
        await _upsert_batch(session, batch)
```

**Sub-batch sizing:** asyncpg's 32,767 parameter limit means `floor(32767 / num_columns)` records per sub-batch. Election records (~20 columns) allow ~1,600 per sub-batch; candidate records (~15 columns) allow ~2,100. Use 500 as a safe default (matching existing voter import).

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Markdown parser | mistune 3.2.0 | markdown-it-py | 2.5x slower; CommonMark compliance unnecessary for our deterministic format |
| Markdown parser | mistune 3.2.0 | regex/manual | Fragile with markdown edge cases (pipes in cells, links, em-dashes) |
| Job queue | procrastinate 3.7.2 | PGQueuer | Less mature; fewer releases; less documentation |
| Job queue | procrastinate 3.7.2 | Celery | Requires Redis; violates PostgreSQL-only constraint |
| Job queue | procrastinate 3.7.2 | InProcessTaskRunner (existing) | No persistence, retries, or crash recovery |
| R2 upload | boto3 (existing) | r2-upload-lib or custom | boto3 already works with R2; presigned URLs are standard S3 API |
| JSONL validation | Pydantic v2 (existing) | jsonschema | Pydantic already in stack; faster (Rust core); better DX with model classes |
| AI skills | Claude Code Skills | LangChain/custom scripts | Skills integrate directly into user's Claude Code workflow; no runtime dependency |

## Installation

```bash
# New dependencies only (3 packages)
uv add "mistune>=3.2.0"
uv add "procrastinate>=3.7.2"
uv add "psycopg[pool]>=3.3.2"

# No new dev dependencies needed
# Existing test infrastructure (pytest, moto, aiosqlite) covers all new code
```

**Total new dependencies: 3** (mistune, procrastinate, psycopg with pool extra). All other functionality uses existing dependencies.

## Configuration (New Environment Variables)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `R2_UPLOAD_BUCKET` | No | Same as `R2_BUCKET` | Bucket for import uploads (can reuse existing publishing bucket) |
| `R2_UPLOAD_PREFIX` | No | `imports/` | Key prefix for uploaded JSONL files |
| `R2_UPLOAD_URL_EXPIRY` | No | `3600` | Presigned URL expiry in seconds |
| `PROCRASTINATE_MAX_JOBS` | No | `4` | Max concurrent procrastinate workers |

Procrastinate connects to the same `DATABASE_URL` (rewriting `asyncpg` to `postgresql` in the connection string for psycopg compatibility).

## Dependency Risk Assessment

| Dependency | Risk | Mitigation |
|------------|------|------------|
| mistune | LOW -- zero external deps, 14+ years old, actively maintained | Pure parser; easy to swap if needed |
| procrastinate | MEDIUM -- adds psycopg driver alongside asyncpg | Well-established (4+ years); separate connection pools; can fall back to InProcessTaskRunner if needed |
| psycopg[pool] | LOW -- official PostgreSQL adapter for Python | Only used by procrastinate; does not touch SQLAlchemy layer |

## Sources

- [Procrastinate GitHub](https://github.com/procrastinate-org/procrastinate) -- v3.7.2, Jan 2026
- [Procrastinate Docs -- Connectors](https://procrastinate.readthedocs.io/en/stable/howto/basics/connector.html) -- PsycopgConnector, AiopgConnector
- [Procrastinate Docs -- Worker](https://procrastinate.readthedocs.io/en/stable/howto/basics/worker.html) -- FastAPI lifespan integration
- [Procrastinate Docs -- Schema](https://procrastinate.readthedocs.io/en/stable/howto/production/schema.html) -- Custom PG schema support
- [Procrastinate Docs -- Migrations](https://procrastinate.readthedocs.io/en/stable/howto/production/migrations.html) -- Pure SQL migration scripts
- [Procrastinate PyPI](https://pypi.org/project/procrastinate/) -- v3.7.2 released Jan 22, 2026
- [Mistune PyPI](https://pypi.org/project/mistune/) -- v3.2.0 released Dec 23, 2025
- [Mistune Docs -- Guide](https://mistune.lepture.com/en/latest/guide.html) -- AST renderer mode
- [Mistune Docs -- Advanced](https://mistune.lepture.com/en/latest/advanced.html) -- Table AST token structure
- [Claude Code Skills Docs](https://code.claude.com/docs/en/skills) -- Skill creation, frontmatter, subagents
- [Cloudflare R2 Presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/) -- 7-day max expiry, S3 domain only
- [Cloudflare R2 boto3 Examples](https://developers.cloudflare.com/r2/examples/aws/boto3/) -- Client configuration
- [PGQueuer GitHub](https://github.com/janbjorge/pgqueuer) -- Alternative considered
- [SQLAlchemy 2.0 Async Docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) -- Async bulk operations
- [Pydantic Docs -- File Validation](https://docs.pydantic.dev/latest/examples/files/) -- JSONL validation patterns

---

*Stack research: 2026-03-13*
