# Milestones

## v1.1 Election Search (Shipped: 2026-03-16)

**Phases completed:** 3 phases, 5 plans, 10 tasks
**Files modified:** 29 | **Lines:** +4,193 / -53
**Timeline:** 1 day (2026-03-16)
**Git range:** `0edf183..02a97dd`

**Delivered:** Election search, filtering, and discovery capabilities on the elections API — capabilities endpoint, free-text search, race category/county/date filters, and dynamic filter-options endpoint, all backward-compatible with existing consumers.

**Key accomplishments:**
1. Static capabilities endpoint (`GET /elections/capabilities`) with route ordering pattern and 1-hour cache
2. Free-text search, race category, county, and exact date filters with ILIKE wildcard escaping
3. 22 integration tests verifying all search/filter params via mock service pattern
4. Dynamic filter-options endpoint (`GET /elections/filter-options`) with soft-delete exclusion and 5-minute cache
5. 19 new E2E tests covering all three endpoints with diverse seed data (185 total E2E, up from 166)

**Tests:** 42 new unit + 22 integration + 19 E2E (185 E2E total)

---

## v1.0 Better Imports (Shipped: 2026-03-15)

**Phases completed:** 5 phases, 15 plans
**Commits:** 236 | **Files modified:** 1,294 | **LOC:** 94,760 Python
**Timeline:** 32 days (2026-02-11 → 2026-03-15)
**Git range:** `1f9ef0a..43d6f75`

**Delivered:** A three-stage election data pipeline (SOS→Markdown→JSONL→DB) with AI-assisted skills, deterministic conversion, and idempotent import — proven end-to-end with three Georgia 2026 elections.

**Key accomplishments:**
1. Defined data contracts: 10 markdown format specs, 4 JSONL Pydantic schemas, Body/Seat reference system for all 159 GA counties
2. Built deterministic MD→JSONL converter using mistune AST parser with Pydantic validation at conversion time
3. Built JSONL→DB import pipeline: 4 import services with idempotent UPSERT, dry-run mode, migration/backfill tools
4. Created 4 Claude Code skills: qualified-candidates (CSV→MD), normalizer, election-calendar (PDF→dates), candidate-enrichment
5. Proved full pipeline end-to-end: 3 GA elections (May 19, Mar 17, Mar 10) imported with documented walkthrough
6. Achieved full traceability: 19/19 requirements satisfied, Nyquist validation complete across all phases

**Tests:** 213 new unit + 7 integration + 166 E2E (2,323 total passing)

---

