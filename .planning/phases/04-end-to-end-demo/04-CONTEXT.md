# Phase 4: End-to-End Demo - Context

**Gathered:** 2026-03-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Prove the full import pipeline works from raw SOS source data to queryable API results by running the converter and import on Phase 3's demo-ready markdown for all three elections, then verifying data via authenticated API queries. Document the pipeline as a reproducible walkthrough that a developer with the repo could follow from scratch.

</domain>

<decisions>
## Implementation Decisions

### Demo Election Scope
- **All three elections processed**: May 19 general primary (2,346 rows), March 17 special (9 rows), March 10 special (38 rows) — proves pipeline works across election types
- **Start from existing markdown**: Use Phase 3's committed markdown output, not re-run AI skills. Git history documents skill execution. Demo picks up at converter step.
- **Include human-review checkpoint**: Walkthrough includes a step where the operator reviews markdown via `git diff` before proceeding to conversion. Documents the human-in-the-loop design.
- **Old file state unknown**: Planner should investigate whether pre-Phase 3 markdown files in `data/elections/2026-05-19/` were replaced by Phase 3 output or still exist alongside it. Handle any discrepancy before running the converter.

### Walkthrough Documentation
- **Format**: Step-by-step markdown document at `docs/pipeline-walkthrough.md`
- **Target audience**: Developer who has cloned the repo, has uv and PostGIS set up, and is familiar with CLI tools and git
- **Expected output**: Include real terminal output captured from the actual demo run as code blocks. Shows exactly what to expect at each step.

### API Verification
- **Four query types demonstrated**:
  1. List elections by date — `GET /api/v1/elections?date=2026-05-19`, verify count matches expected
  2. Candidate lookup — `GET /api/v1/candidates/{id}`, verify enriched fields (bio, photo, contact info) came through
  3. Election detail with candidates — `GET /api/v1/elections/{id}`, show contest with linked candidates via candidacy junction
  4. District-based query — query by boundary_type + district_identifier, prove Body/Seat district linkage survives the full pipeline
- **Count assertions + spot checks**: Document expected record counts per election date (elections, candidates, candidacies) AND spot-check specific candidates by name to verify data accuracy
- **Full auth flow**: Walkthrough shows login, JWT token retrieval, and authenticated API requests

### Converter Validation
- **Show and explain the report**: Include full terminal validation report output in the walkthrough with annotations explaining what each section means (successes, warnings, failures)
- **Dry-run before import**: Run `--dry-run` first to show what would be imported (counts, validation status), then run the real import. Demonstrates the safety feature.

### Target Environment
- **Local PostGIS via docker-compose**: Self-contained, reproducible, no risk to shared environments
- **Clean database from scratch**: Walkthrough includes `docker compose up`, `alembic upgrade head`. Import into empty tables so counts are predictable and results unambiguous.
- **Happy path only**: No error scenarios in the walkthrough. Error handling documented elsewhere.

### Post-Demo
- **Both options documented**: Walkthrough mentions keeping the database running for ongoing development OR `docker compose down` to clean up. Operator chooses.

### Claude's Discretion
- HTTP client tool choice for API verification (curl, httpie, or httpx — whatever fits best with existing project conventions)
- Plan count and task sequencing
- Exact walkthrough section structure and flow
- How to handle old vs Phase 3 file discrepancy (once investigated)

</decisions>

<specifics>
## Specific Ideas

- The walkthrough is the final deliverable for the entire "Better Imports" milestone — it proves the three-stage pipeline (SOS → MD → JSONL → DB) works end-to-end with real Georgia election data.
- Phase 3 already produced markdown for all three elections. The demo validates that converter + import + API layer integrates correctly with that output.
- The human-review step (git diff) documents the design philosophy: AI produces data, humans review it, deterministic tools import it.
- Count assertions tied to real SOS CSV row counts let the operator verify nothing was lost in the pipeline.
- Spot-checking specific candidates (e.g., Governor race candidates) catches data corruption that aggregate counts would miss.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/voter_api/lib/converter/` — Deterministic MD-to-JSONL converter with validation reporting (parser, writer, resolver, report modules)
- `src/voter_api/lib/normalizer/` — Normalizer library for post-processing markdown (already run during Phase 3)
- `src/voter_api/cli/convert_cmd.py` — CLI: `voter-api convert <dir>` converts election directories to JSONL
- `src/voter_api/cli/import_cmd.py` — CLI: `voter-api import election-events`, `elections`, `candidates-jsonl`, `candidacies`, and `election-data` pipeline command
- `data/elections/` — Three election directories with Phase 3 markdown output (2026-05-19, 2026-03-17, 2026-03-10)
- `data/candidates/` — 49 candidate files with enrichment data from Phase 3
- `data/states/GA/counties/` — 159 county reference files needed by converter's Body/Seat resolver
- `docker-compose.yml` — PostGIS service definition for local development
- `specs/001-voter-data-management/quickstart.md` — Existing setup instructions (walkthrough can reference for prerequisites)

### Established Patterns
- CLI commands follow Typer pattern with asyncio.run wrapper, init_engine/dispose_engine lifecycle
- Validation reports use terminal table + JSON file dual output
- Import uses bulk UPSERT (`INSERT ON CONFLICT DO UPDATE`) for idempotency
- JWT auth with role-based access (admin/analyst/viewer)
- E2E tests in `tests/e2e/` demonstrate API query patterns that the walkthrough can mirror

### Integration Points
- `docs/pipeline-walkthrough.md` — New walkthrough document (the primary Phase 4 deliverable)
- Converter output → Import input: JSONL files in election directory's `jsonl/` subdirectory
- Import → API: Data lands in `election_events`, `elections`, `candidates`, `candidacies` tables
- API queries verify the full chain: markdown fields → JSONL fields → DB columns → API response fields

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-end-to-end-demo*
*Context gathered: 2026-03-15*
