# Research Summary: Better Imports

**Domain:** Three-stage data import pipeline (SOS -> Markdown -> JSONL -> DB)
**Researched:** 2026-03-13
**Overall confidence:** HIGH

## Executive Summary

The three-stage import pipeline (AI-assisted SOS extraction -> human-reviewable markdown -> deterministic JSONL -> database) is well-supported by the current Python ecosystem and fits naturally into the existing voter-api architecture. The project requires only three new dependencies: mistune (markdown parser), procrastinate (PostgreSQL job queue), and psycopg (PostgreSQL driver for procrastinate). Everything else -- R2 presigned URLs, JSONL validation, bulk UPSERT, CLI commands -- uses libraries already in the stack.

The most significant architectural decision is adding procrastinate alongside the existing asyncpg-based SQLAlchemy stack. This means two PostgreSQL drivers (asyncpg for the ORM, psycopg for the job queue) connecting to the same database through independent connection pools. This is a common and well-understood pattern, but it requires explicit connection budget planning to avoid pool exhaustion.

The markdown format is the pipeline's unique strength and its primary risk. The existing ~200 markdown files and 4 format specs in `data/elections/formats/` demonstrate the format works at scale. The critical pitfall is AI-generated formatting drift between runs, which can create spurious duplicates. The mitigation is a deterministic Python normalizer that runs after AI output, enforcing the same rules programmatically that the format specs define in prose.

Claude Code skills are the right mechanism for Stage 1 because the user already works in Claude Code and the skill system supports exactly this use case: prompt-driven data extraction with supporting files, templates, and shell command injection for dynamic context. No runtime dependency is needed -- skills are markdown instruction files.

## Key Findings

**Stack:** Three new dependencies (mistune >= 3.2.0, procrastinate >= 3.7.2, psycopg[pool] >= 3.3.2). All other functionality uses existing libraries (boto3 for R2, Pydantic v2 for validation, SQLAlchemy pg_insert for UPSERT).

**Architecture:** New code follows the existing library-first pattern. Two new libraries (`lib/converter/` for MD->JSONL, `lib/uploader/` or extend `lib/publisher/` for R2 presigned URLs), one new service (`services/jsonl_import_service.py`), one new core module (`core/jobs.py` for procrastinate), new CLI commands and API endpoint extensions.

**Critical pitfall:** AI-generated markdown drift between runs creates duplicate elections. Mitigate with deterministic post-processing normalizer and round-trip validation tests.

## Implications for Roadmap

Based on research, suggested phase structure:

1. **Foundation: JSONL Schemas + Enhanced Markdown Format** - Define the data contracts first
   - Addresses: JSONL schema definitions, enhanced markdown format with district linkage
   - Avoids: Building converter or import against undefined schemas (Pitfall 3: FK ordering)
   - Rationale: Everything downstream depends on these contracts

2. **Stage 2: Deterministic MD-to-JSONL Converter** - Build and test the converter library
   - Addresses: mistune-based parser, Pydantic validation, JSONL generation
   - Avoids: Table parsing edge cases (Pitfall 4) via proper AST parser + round-trip tests
   - Rationale: Must work before Stage 3 can be tested; pure library, independently testable

3. **Stage 1: Claude Code Skills + Normalizer** - Formalize AI-assisted extraction
   - Addresses: Skills for SOS CSV processing, deterministic normalizer
   - Avoids: AI drift (Pitfall 1), hallucination (Pitfall 2) via normalizer + source-fidelity constraints
   - Rationale: Can run in parallel with Phase 2; format specs from Phase 1 inform skill instructions

4. **Stage 3: JSONL Import Pipeline (CLI-first)** - Prove end-to-end flow
   - Addresses: JSONL -> DB import for elections and candidates via CLI
   - Avoids: Attempting API + job queue before the core pipeline works
   - Rationale: CLI-first demonstrates the full flow; May 19 election demo target

5. **Infrastructure: Procrastinate + R2 Presigned URLs** - Production-grade background processing
   - Addresses: Job queue, retry logic, presigned URL upload, API import endpoints
   - Avoids: Running large imports through InProcessTaskRunner (Pitfall 7: crash recovery)
   - Rationale: Not needed for small election/candidate files via CLI; critical for future voter imports

**Phase ordering rationale:**
- Phases 1-2 (schemas + format) must come first because converter, skills, and importer all depend on these contracts
- Phase 3 (converter) and the skills portion of Phase 3 are independent and could be built in parallel
- Phase 4 (CLI import) depends on Phase 3 (converter produces the JSONL that import consumes)
- Phase 5 (procrastinate + R2) is additive infrastructure that wraps the working CLI pipeline in production-grade tooling

**Research flags for phases:**
- Phase 2 (converter): Needs deeper testing on all 4 markdown format variants; round-trip validation is critical
- Phase 5 (procrastinate): Needs careful connection pool budgeting; Alembic migration wrapping needs attention
- Phase 3 (skills): Standard Claude Code skill patterns; unlikely to need additional research

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All libraries verified via PyPI/official docs; versions confirmed current |
| Features | HIGH | Feature scope well-defined in PROJECT.md; existing patterns cover most implementation |
| Architecture | HIGH | Follows established library-first pattern; existing UPSERT patterns directly reusable |
| Pitfalls | HIGH | Grounded in documented data quality issues and existing codebase limitations |
| Procrastinate integration | MEDIUM | Two-driver pattern is sound but needs connection pool planning; no asyncpg connector means psycopg is required |
| R2 presigned URLs | HIGH | Existing boto3 R2 client; standard S3 API; constraints well-documented by Cloudflare |
| Claude Code skills | HIGH | Verified via official docs; skill system is production-ready and matches use case |

## Gaps to Address

- **Procrastinate + Alembic migration wrapping**: No official guide for wrapping procrastinate SQL migrations in Alembic revisions. Needs to be solved during implementation (straightforward `op.execute()` approach, but needs testing).
- **Connection pool sizing in production**: Need to know PostgreSQL `max_connections` on the piku server to properly budget between asyncpg and psycopg pools.
- **Markdown format completeness**: Current format specs cover county, statewide, special election, and overview files. Candidate enrichment fields (photo URL, bio, external IDs) are not yet specified. These need to be added to format specs before converter handles them.
- **Procrastinate worker deployment on piku**: Need to verify that the procrastinate worker runs correctly within piku's uwsgi emperor deployment model (worker as asyncio task within FastAPI lifespan, not as a separate process).

---

*Research summary: 2026-03-13*
