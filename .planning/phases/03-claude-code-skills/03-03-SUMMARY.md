---
phase: 03-claude-code-skills
plan: "03"
subsystem: skills
tags: [claude-skills, csv-processing, markdown, election-data, georgia-sos, checkpointing]

# Dependency graph
requires:
  - phase: 03-01-normalizer-library
    provides: voter-api normalize CLI commands that the normalize skill wraps
  - phase: 01-data-contracts
    provides: format specs in docs/formats/markdown/ referenced by qualified-candidates skill

provides:
  - .claude/skills/includes/csv-columns.md — SOS CSV column mapping for all skills
  - .claude/skills/includes/format-rules.md — formatting conventions (title case, dates, URLs, tables)
  - .claude/skills/includes/contest-patterns.md — 25+ GA SOS contest name parsing examples
  - .claude/skills/qualified-candidates/SKILL.md — core AI skill for CSV-to-markdown processing with checkpoint/resume
  - .claude/skills/normalize/SKILL.md — normalizer CLI wrapper skill
  - .claude/commands/election.process.md — /election:process command
  - .claude/commands/election.normalize.md — /election:normalize command
  - data/import/ — gitignored directory for SOS source files

affects:
  - phase 03-04 (election processing runs that use the qualified-candidates skill)
  - phase 04 (converter/import uses markdown output produced by these skills)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Claude Code SKILL.md with YAML frontmatter (disable-model-invocation, argument-hint)
    - Shared includes in .claude/skills/includes/ referenced via @file paths — DRY skill fragments
    - JSONL checkpoint file for resumable long-running skill processing
    - Diff-aware update mode (regenerate vs. update) for re-processing existing elections
    - Command files in .claude/commands/ delegating to skill files

key-files:
  created:
    - .claude/skills/includes/csv-columns.md
    - .claude/skills/includes/format-rules.md
    - .claude/skills/includes/contest-patterns.md
    - .claude/skills/qualified-candidates/SKILL.md
    - .claude/skills/normalize/SKILL.md
    - .claude/commands/election.process.md
    - .claude/commands/election.normalize.md
    - data/import/.gitkeep
    - data/import/.gitignore
  modified: []

key-decisions:
  - "Shared includes in .claude/skills/includes/ keep CSV column mapping, format rules, and contest patterns DRY — referenced via @file by skills, not embedded"
  - "JSONL checkpoint file at data/elections/{date}/.checkpoint.jsonl provides resumability without DB dependency — deleted on successful completion"
  - "Diff-aware update mode: operator chooses regenerate (clean slate) vs. update (preserve enrichment) when re-processing an existing election"
  - "--direct flag skips interactive confirmation and defaults to regenerate mode for scripted use"
  - "contest-patterns.md covers 25+ real SOS examples across all contest types (statewide, federal, state legislative, county boards/courts, municipal, special)"

patterns-established:
  - "SKILL.md pattern: YAML frontmatter with disable-model-invocation + numbered instruction sections"
  - "Skills reference format specs via @file paths, never embed spec content (DRY, always current)"
  - "Command files (.claude/commands/election.*.md) are thin delegators to SKILL.md files"
  - "data/import/ as the standard drop location for SOS source files (gitignored, gitkeep preserved)"

requirements-completed:
  - SKL-01
  - SKL-02

# Metrics
duration: 5min
completed: 2026-03-15
---

# Phase 03 Plan 03: Claude Code Skills Infrastructure Summary

**Shared skill includes (CSV mapping, format rules, 25+ contest patterns), qualified-candidates SKILL.md with JSONL checkpoint/resume and diff-aware update mode, normalize SKILL.md wrapper, and /election:process + /election:normalize commands**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-15T04:51:28Z
- **Completed:** 2026-03-15T04:56:00Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- Created three shared include files (csv-columns.md 44 lines, format-rules.md 128 lines, contest-patterns.md 174 lines with 25+ real SOS examples) in .claude/skills/includes/ — referenced via @file by all skills
- Created qualified-candidates/SKILL.md (284 lines) covering the full CSV-to-markdown pipeline: input validation, contest name parsing AI guidance, diff-aware update/regenerate mode, JSONL checkpoint/resume, 12-step processing flow, interactive/direct mode, error handling, quality checks
- Created normalize/SKILL.md wrapping the voter-api normalize CLI commands, and two /election:* command files delegating to their respective skills

## Task Commits

Each task was committed atomically:

1. **Task 1: Shared includes and data/import/ directory** - `046dd90` (feat)
2. **Task 2: Qualified-candidates skill, normalize skill, and commands** - `aed5509` (feat)

**Plan metadata:** (this SUMMARY commit)

## Files Created/Modified

- `.claude/skills/includes/csv-columns.md` — 11-column SOS CSV mapping with transformation notes and multi-county deduplication rules
- `.claude/skills/includes/format-rules.md` — Smart title case rules (Mc/Mac prefix, suffixes, compounds), date formats, URL normalization, empty values, file naming conventions, partisan primary section structure
- `.claude/skills/includes/contest-patterns.md` — 25+ contest name parsing examples: statewide offices, US House (6 variant formats), State Senate/House, county BOE/BOC, courts (superior/state/magistrate/probate), county offices, municipal contests, special elections
- `.claude/skills/qualified-candidates/SKILL.md` — Complete processing skill with 11 numbered sections including JSONL checkpoint file at data/elections/{date}/.checkpoint.jsonl
- `.claude/skills/normalize/SKILL.md` — Thin wrapper: parse args, run `uv run voter-api normalize elections|candidates <dir>`, display output, summarize warnings
- `.claude/commands/election.process.md` — Delegates to qualified-candidates skill via @file reference
- `.claude/commands/election.normalize.md` — Delegates to normalize skill via @file reference
- `data/import/.gitkeep` — Preserves directory in git
- `data/import/.gitignore` — Ignores all files except .gitkeep and .gitignore

## Decisions Made

- Shared includes in .claude/skills/includes/ keep CSV column mapping, format rules, and contest patterns DRY — referenced via @file paths in skills so updating once keeps all skills in sync
- JSONL checkpoint file at data/elections/{date}/.checkpoint.jsonl provides resumability for long-running CSV processing without requiring a DB connection — deleted on successful completion
- Diff-aware update mode: operator chooses at invocation time between regenerate (clean slate from CSV) and update (add new candidates, update changed fields, preserve enrichment and manual edits)
- --direct flag skips interactive confirmation and defaults to regenerate mode for scripted/batch use
- contest-patterns.md covers 25+ real GA SOS examples across all contest types using a table format for quick AI pattern matching

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- qualified-candidates skill ready to process all three available SOS CSVs (May 19, March 17, March 10)
- normalize skill ready for use after skill output is reviewed
- /election:process and /election:normalize commands available via Claude Code slash commands
- data/import/ directory ready to receive SOS source CSV files

---
*Phase: 03-claude-code-skills*
*Completed: 2026-03-15*
