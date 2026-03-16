# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — Better Imports

**Shipped:** 2026-03-15
**Phases:** 5 | **Plans:** 15 | **Sessions:** ~16

### What Was Built
- Three-stage election data pipeline: SOS CSV/PDF → human-reviewable markdown → validated JSONL → PostgreSQL database
- Four Claude Code skills for AI-assisted data processing (qualified-candidates, normalizer, election-calendar, candidate-enrichment)
- Deterministic mistune AST converter with 159 county reference files for Body/Seat district resolution
- Idempotent JSONL import pipeline with 4 services, dry-run mode, and migration/backfill tools
- Candidacy junction table refactoring (candidate-election many-to-many)
- End-to-end demo with 3 Georgia 2026 elections imported and documented walkthrough

### What Worked
- **Library-first architecture** — each lib/ module (converter, normalizer, importer) was independently testable before integration
- **Coarse phase granularity** — combining converter + import into one phase reduced coordination overhead
- **TDD for normalizer** — failing tests first caught edge cases (Mac prefix detection, single-letter initials) that would have been missed
- **Fail-fast election ordering** — processing smallest election (March 10) first validated the skill pipeline before the large May 19 batch
- **Human checkpoint gate** — blocking review after skill output caught data quality issues before import

### What Was Inefficient
- **Phase 1 scope creep** — started as "format specs" but grew to include all data contracts, UUIDs, migration rules, backfill rules. Should have been scoped more precisely upfront
- **Phase 2 scope grew** — model refactoring (candidacy junction, ElectionEvent enhancement) wasn't anticipated during roadmap planning
- **Nyquist validation deferred** — all 4 original phases shipped without Nyquist compliance, requiring Phase 5 cleanup
- **Milestone audit revealed stale traceability** — DEM-01 showed "In Progress" despite both plans being complete; walkthrough had inaccuracies

### Patterns Established
- **Body/Seat reference system** — county reference files provide deterministic district linkage for all 159 GA counties
- **JSONL mirrors DB models** — zero mapping code in import services, Pydantic validation at every boundary
- **State machine for markdown parsing** — table context tracking in normalizer avoids regex fragility
- **Shared skill includes** — DRY CSV column mapping, format rules, and contest patterns across all Claude Code skills
- **Golden file testing** — generate "after" fixtures by running normalizer on "before" fixtures for guaranteed round-trip consistency

### Key Lessons
1. **Scope contracts early, not just format specs** — Phase 1 was labeled "Data Contracts" but the real scope was broader (UUID strategy, migration rules, backfill rules). Name phases for what they actually deliver.
2. **Run milestone audit before the last phase** — the audit found 6 tech debt items that required a new Phase 5. Running it earlier would have caught stale traceability sooner.
3. **Placeholder UUIDs create downstream debt** — the election_event_id placeholder approach works but leaves NULL FKs that require a separate resolve step. Consider alternatives for future entity types.
4. **Skill output quality depends on input ordering** — processing elections smallest-to-largest provides natural validation progression.

### Cost Observations
- Model mix: ~70% opus, ~25% sonnet, ~5% haiku (quality profile)
- Sessions: ~16 across 32 days
- Notable: Phase 1-3 averaged 7.5 min/plan; Phase 4 jumped to 20.5 min/plan due to integration complexity and live data issues

---

## Milestone: v1.1 — Election Search

**Shipped:** 2026-03-16
**Phases:** 3 | **Plans:** 5 | **Sessions:** ~3

### What Was Built
- Capabilities endpoint (`GET /elections/capabilities`) with route ordering pattern and 1-hour cache
- Free-text search, race category, county, and exact date filters on elections list endpoint
- ILIKE wildcard escaping utility for safe user input handling
- Dynamic filter-options endpoint (`GET /elections/filter-options`) with soft-delete exclusion
- 19 new E2E tests with diverse seed data (185 total E2E)

### What Worked
- **Zero-migration approach** — all features built on existing indexed columns (`district_type`, `eligible_county`, `election_date`), no schema changes needed
- **Single-day execution** — 3 phases, 5 plans, 10 tasks completed in one session (~23 min total execution)
- **TDD for filter logic** — tests-first approach for escape utility and filter-options caught edge cases (NULL district_type, title-case normalization)
- **Route ordering pattern** — establishing static routes before `/{election_id}` in Phase 6 prevented shadowing issues in all subsequent phases
- **Audit before completion** — milestone audit confirmed 11/11 requirements satisfied before archival

### What Was Inefficient
- **Nyquist validation still incomplete** — all 3 phases have VALIDATION.md but none finalized (same pattern as v1.0)
- **ROADMAP.md checkbox not updated for Phase 6** — minor tracking gap caught by audit
- **Summary one-liners not populated** — `summary-extract --fields one_liner` returned null for all 5 summaries, suggesting frontmatter doesn't include that field

### Patterns Established
- **Category mapping pattern** — constant dict maps user-facing categories to DB column values (RACE_CATEGORY_MAP)
- **Filter options pattern** — DISTINCT queries with soft-delete exclusion, mapped through constants, title-case normalization
- **Discovery endpoint pattern** — static JSON responses with Cache-Control headers, registered before parameterized routes
- **E2E seed data diversity** — multiple election types (federal, state_senate, state_house, local, soft-deleted) for comprehensive filter testing

### Key Lessons
1. **Zero-new-dependency features ship fastest** — v1.1 required zero new libraries and zero migrations, enabling single-day delivery
2. **Route ordering is a first-class concern in FastAPI** — static routes must be declared before parameterized catch-alls; establishing this in Phase 6 prevented issues throughout
3. **Alias query params to avoid response model shadowing** — `election_date_exact` with `alias="election_date"` cleanly separates query input from response output
4. **Nyquist validation needs to be part of the execution flow, not a post-hoc step** — two milestones now with incomplete Nyquist compliance

### Cost Observations
- Model mix: ~80% opus, ~20% sonnet (quality profile)
- Sessions: ~3 in 1 day
- Notable: Average 4.6 min/plan — significantly faster than v1.0's 7.5 min/plan due to zero-migration scope and well-established patterns

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | ~16 | 5 | First milestone; established GSD workflow with coarse granularity |
| v1.1 | ~3 | 3 | Single-day delivery; zero-migration feature set |

### Cumulative Quality

| Milestone | Tests | Coverage | New Libraries |
|-----------|-------|----------|---------------|
| v1.0 | 2,323 | 90%+ | converter, normalizer, JSONL schemas |
| v1.1 | +83 (185 E2E) | 90%+ | none (zero new deps) |

### Top Lessons (Verified Across Milestones)

1. Library-first architecture enables confident integration — test each piece independently before wiring together
2. Human checkpoints in AI-assisted pipelines are essential — skill output is good but not perfect
3. Nyquist validation needs workflow integration — incomplete across both milestones, suggesting it should be automated into plan execution
4. Zero-dependency features ship fastest — building on existing columns and patterns eliminates migration/coordination overhead
