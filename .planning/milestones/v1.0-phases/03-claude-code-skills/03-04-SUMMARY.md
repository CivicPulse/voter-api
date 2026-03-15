---
phase: 03-claude-code-skills
plan: 04
subsystem: skills
tags: [claude-skills, election-data, pdf-extraction, candidate-enrichment, pipeline-orchestration]

requires:
  - phase: 03-claude-code-skills
    provides: qualified-candidates skill, normalize skill, shared includes (csv-columns.md, format-rules.md, contest-patterns.md)
  - phase: 01-data-contracts
    provides: format specs at docs/formats/markdown/ referenced via @file in skill instructions

provides:
  - election-calendar skill: reads SOS calendar PDFs natively, extracts 9 date fields into election overview Calendar section
  - candidate-enrichment skill: researches 4 source types with confidence annotations, --depth levels, URL validation, agent team coordination
  - process-election skill: orchestrates full 6-step pipeline (CSV -> qualified-candidates -> normalize elections -> normalize candidates -> enrich -> review)
  - /election:calendar command: delegates to election-calendar/SKILL.md
  - /election:enrich command: delegates to candidate-enrichment/SKILL.md
  - /election:pipeline command: delegates to process-election/SKILL.md

affects:
  - 03-05 (if any)
  - phase-04 converter and import (pipeline produces normalized markdown for converter input)

tech-stack:
  added: []
  patterns:
    - "Skill frontmatter: name, description, argument-hint, disable-model-invocation, allowed-tools (for enrichment)"
    - "All skills reference format specs via @file paths -- no embedded format rules"
    - "Command files: YAML frontmatter with description, body delegates to SKILL.md"
    - "Confidence annotations: (source: ballotpedia), (source: campaign-website), (unverified) for all enriched data"
    - "Pipeline orchestrator: each step is independent, error recovery table shows manual resume commands"

key-files:
  created:
    - .claude/skills/election-calendar/SKILL.md
    - .claude/skills/candidate-enrichment/SKILL.md
    - .claude/skills/process-election/SKILL.md
    - .claude/commands/election.calendar.md
    - .claude/commands/election.enrich.md
    - .claude/commands/election.pipeline.md
  modified: []

key-decisions:
  - "election-calendar skill uses native PDF reading (Claude reads PDFs directly -- no library needed)"
  - "candidate-enrichment skill processes candidates sequentially by default for API rate limit safety; agent team coordination is optional and described in Section 10"
  - "process-election pipeline uses --depth basic for enrichment step (bio + party + office; skip social/education) to keep pipeline completion time reasonable"
  - "Pipeline uses --skip-enrich flag to defer enrichment for large elections; always run normalizer before enrichment so candidate files have real UUIDs"

patterns-established:
  - "URL validation pattern: WebFetch or curl, follow redirects, mark dead links with (dead link as of YYYY-MM-DD)"
  - "Checkpoint pattern for candidate enrichment: each written file is its own checkpoint; re-run skips populated fields"
  - "Enrichment depth levels: full (all fields), basic (bio + office), minimal (identity verification only)"

requirements-completed:
  - SKL-03
  - SKL-04

duration: 3min
completed: 2026-03-15
---

# Phase 3 Plan 04: Election Calendar, Candidate Enrichment, and Pipeline Orchestrator Summary

**Three skills (election-calendar, candidate-enrichment, process-election) and three commands (/election:calendar, /election:enrich, /election:pipeline) completing the 5-skill + 5-command Claude Code election data toolkit**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-15T05:09:36Z
- **Completed:** 2026-03-15T05:13:14Z
- **Tasks:** 2
- **Files modified:** 6 created

## Accomplishments

- Election-calendar skill reads GA SOS calendar PDFs natively (no parsing library), extracts 9 date fields (core, absentee, qualifying period) with source attribution, validates participating counties against disk
- Candidate-enrichment skill researches 4 source types in priority order (Ballotpedia, campaign sites, government sites, social media), marks all enriched data with confidence annotations, supports --depth flag (full/basic/minimal), validates URLs with dead-link marking, describes agent team coordinator + batch worker pattern
- Process-election orchestrator ties the full 6-step pipeline together with error recovery table, --skip-enrich flag for large elections, and calendar integration hint

## Task Commits

Each task was committed atomically:

1. **Task 1: Election calendar skill and candidate enrichment skill** - `c940b5e` (feat)
2. **Task 2: Pipeline orchestrator skill and remaining /election:* commands** - `1afe74f` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `.claude/skills/election-calendar/SKILL.md` - Reads SOS PDFs natively, extracts 9 date fields into election overview Calendar section, validates participating counties
- `.claude/skills/candidate-enrichment/SKILL.md` - Web research enrichment with 4 sources, confidence annotations, --depth levels, URL validation, agent team section
- `.claude/skills/process-election/SKILL.md` - Full 6-step pipeline orchestrator with error recovery and calendar integration hint
- `.claude/commands/election.calendar.md` - /election:calendar command, delegates to election-calendar/SKILL.md
- `.claude/commands/election.enrich.md` - /election:enrich command, delegates to candidate-enrichment/SKILL.md
- `.claude/commands/election.pipeline.md` - /election:pipeline command, delegates to process-election/SKILL.md

## Decisions Made

- election-calendar skill uses Claude's native PDF reading (no library) -- matches CONTEXT.md and prevents dependency on fragile PDF parsing libraries
- candidate-enrichment processes sequentially by default (safe for API rate limits); agent team coordination described in Section 10 for when cooperative team is explicitly enabled
- process-election uses --depth basic in the pipeline enrichment step to keep pipeline runs completion time manageable for large elections (e.g., 2,346-row May 19 CSV)
- Pipeline step ordering: normalize elections and candidates before enrichment so candidate files have real UUIDs when enrichment links to contest files

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness

- All 5 skills and 5 commands are now in place: qualified-candidates, normalize, election-calendar, candidate-enrichment, process-election + 5 election.* commands
- Phase 4 (converter and import) can consume the normalized markdown output from the full pipeline
- Operator can now run `/election:pipeline data/import/2026-05-19-qualified-candidates.csv` to process any of the three available SOS CSVs through the complete pipeline

---
*Phase: 03-claude-code-skills*
*Completed: 2026-03-15*
