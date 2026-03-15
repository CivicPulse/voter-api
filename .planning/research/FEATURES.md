# Feature Landscape

**Domain:** Three-stage data import pipeline (SOS -> Markdown -> JSONL -> DB)
**Researched:** 2026-03-13

## Table Stakes

Features users expect. Missing = pipeline feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Claude Code skill for SOS CSV -> markdown | Core Stage 1 purpose; user's existing workflow | Med | Skill + supporting templates + format validation script |
| Deterministic markdown -> JSONL converter | Core Stage 2 purpose; reproducible conversion | Med | mistune AST parser + Pydantic validation; must handle all format variants (county, statewide, special election, overview) |
| JSONL schema definitions (elections, candidates) | Validate data before DB load; serve as contract | Low | Pydantic models mirroring Election and Candidate ORM columns |
| JSONL -> DB bulk import (elections) | Core Stage 3 purpose for elections | Med | Reuse existing pg_insert/on_conflict_do_update pattern |
| JSONL -> DB bulk import (candidates) | Core Stage 3 purpose for candidates | Med | Same pattern; candidates link to elections by external key |
| Import job tracking in database | Users need to know import status | Low | Existing import_jobs table and pattern; extend for JSONL imports |
| CLI commands for each pipeline stage | Operators run pipeline from command line | Low | `voter-api convert md-to-jsonl`, `voter-api import jsonl` |
| API endpoints for upload + import trigger | Programmatic access to pipeline | Med | Presigned URL generation, import kick-off, job status |
| Error reporting per-record | Must know which records failed and why | Med | JSONB error_log on import job; Pydantic validation errors captured per line |
| Idempotent imports | Re-importing same JSONL must not create duplicates | Low | ON CONFLICT DO UPDATE is already idempotent; JSONL records include unique keys |
| Per-line validation with error collection | Single bad record must not abort entire file | Low | Existing pattern in candidate importer; formalize as `{line: N, errors: [...]}` |
| SHA256 checksums on JSONL files | Enable "skip if unchanged" logic; import idempotency | Low | Compute at generation time; store in import_jobs; skip if matches previous |

## Differentiators

Features that set product apart. Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| R2 presigned URL upload for large files | Files bypass API server; supports 100MB+ voter reg files in future | Med | New endpoint + boto3 presigned URL generation; existing R2 config |
| Procrastinate job queue with retries | Import survives server restart; automatic retry on transient failure | High | New dependency; schema migration; lifespan integration; worker management |
| Human-reviewable markdown intermediate format | Every import is auditable in git diffs; AI errors caught before DB | Low | This is the design itself, not a feature to build |
| District linkage in markdown (boundary_type + district_identifier) | Candidates linked to geographic boundaries in the DB | Med | Enhanced format spec; converter must extract and validate linkage fields |
| Election metadata in markdown (early voting, registration deadlines) | Calendar data flows into election records | Low | Additional markdown sections parsed into JSONL fields |
| Candidate enrichment fields (party, photo, bio, contact, external IDs) | Richer candidate data from day one | Med | More columns in markdown tables; more fields in JSONL schema |
| JSONL as portable backup format | JSONL files serve as database-independent snapshots | Low | Natural consequence of JSONL mirroring DB models 1:1 |
| Dry-run mode for imports | Preview what would change without committing to DB | Med | Generate diff (new/updated/unchanged counts) without executing UPSERT |
| Pipeline provenance chain | Each DB record traces back through import_job -> JSONL (SHA256) -> markdown (git commit) -> SOS source | Med | Full audit trail from API response to government source |
| Progress percentage reporting | For large imports, report progress_pct based on records processed / estimated total | Low | Better UX than just "running" status |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| AI in Stage 2 (markdown -> JSONL) | Defeats deterministic conversion; non-reproducible | Use mistune AST parser; if parsing fails, fix the markdown format spec |
| Real-time SOS feed integration | Existing auto-refresh handles live SOS JSON feeds | This pipeline is for batch imports from downloaded CSVs/PDFs |
| Frontend/UI for reviewing markdown | Over-engineering; git diffs serve this purpose | Users review in git (GitHub PR diffs) or their editor |
| Generic file upload endpoint (non-presigned) | Large files (50-200MB) would choke the API server | Always use presigned URL for large files; keep direct upload for small CLI use |
| Multi-state support | Scope creep; Georgia only for now | Design for extensibility but don't build |
| Voter registration JSONL import | Different data shape; out of scope | Future milestone after election/candidate pipeline is proven |
| Automatic import on source file change | Removes human review gate; violates pipeline design | Import is always explicitly triggered |
| Resumable/chunked uploads | R2 supports up to 5GB single PUT; our files are well under that | Single presigned PUT with 1-hour expiry |
| Dead letter queue | Procrastinate retry + failed state is sufficient | Failed jobs stay in procrastinate_jobs with full error context |
| JSONL streaming response for export | Election/candidate dataset is small; JSON array is simpler | JSONL for import/backup files only, not API responses |

## Feature Dependencies

```
Format Specs (enhanced)
  -> Claude Code Skills (encode specs as instructions)
  -> Structured markdown files

JSONL Schema Definitions (Pydantic models)
  -> Deterministic MD -> JSONL Parser (targets specific models)
  -> JSONL -> DB Import (drives UPSERT column mapping)

R2 Presigned URL Endpoint
  -> Import Job Creation (job tracks upload lifecycle)
  -> Procrastinate Job (triggered when upload completes)

Procrastinate Integration
  -> Schema Migration (procrastinate tables)
  -> FastAPI Lifespan Changes (worker startup/shutdown)

Election Import (JSONL -> DB)
  -> Candidate Import (candidates reference elections via FK)
```

Key chain: Format specs -> Skills -> Markdown -> Parser -> JSONL -> Import -> DB

Election import MUST precede candidate import (FK dependency).

## MVP Recommendation

Prioritize:
1. **JSONL schema definitions** -- foundation for everything in Stages 2-3
2. **Enhanced markdown format spec** with district linkage -- defines what Stage 1 produces
3. **Claude Code skill** for SOS candidate CSV processing -- enables Stage 1
4. **Deterministic markdown -> JSONL converter** -- enables Stage 2
5. **JSONL -> DB import for elections** via CLI -- enables Stage 3
6. **JSONL -> DB import for candidates** via CLI -- completes pipeline

Defer:
- **R2 presigned URL upload**: election/candidate JSONL files are small (<5MB); CLI import sufficient for MVP
- **Procrastinate job queue**: CLI-driven imports don't need background processing; add when API endpoints are built
- **Dry-run mode**: useful but not blocking
- **API import endpoints**: CLI proves the pipeline first; API wraps it later

## Sources

- Project context from `.planning/PROJECT.md`
- Existing markdown format specs in `data/elections/formats/`
- Existing import patterns in `src/voter_api/services/import_service.py`
- Existing background task runner in `src/voter_api/core/background.py`

---

*Feature landscape research: 2026-03-13*
