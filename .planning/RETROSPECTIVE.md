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

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | ~16 | 5 | First milestone; established GSD workflow with coarse granularity |

### Cumulative Quality

| Milestone | Tests | Coverage | New Libraries |
|-----------|-------|----------|---------------|
| v1.0 | 2,323 | 90%+ | converter, normalizer, JSONL schemas |

### Top Lessons (Verified Across Milestones)

1. Library-first architecture enables confident integration — test each piece independently before wiring together
2. Human checkpoints in AI-assisted pipelines are essential — skill output is good but not perfect
