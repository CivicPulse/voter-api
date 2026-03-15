# Phase 3: Claude Code Skills - Context

**Gathered:** 2026-03-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Create AI-assisted Claude Code skills and a deterministic Python normalizer that produce human-reviewable markdown from raw GA SOS data files (qualified candidates CSVs and election calendar PDFs). Skills generate markdown conforming to the enhanced format spec (Phase 1). Normalizer enforces consistency and generates UUIDs. Phase 3 also processes all three available election CSVs (May 19, March 17, March 10) to produce demo-ready markdown.

</domain>

<decisions>
## Implementation Decisions

### Skill Packaging & Invocation

- **Both skills + commands**: Skills in `.claude/skills/` for auto-triggering AND commands in `.claude/commands/` for explicit `/slash` invocation
- **Namespaced commands**: `/election:process`, `/election:enrich`, `/election:normalize`, `/election:calendar`, `/election:pipeline` — following the existing hatchkit/speckit namespace pattern
- **Interactive confirmation by default**: Skill shows each file's content and asks for approval before writing. `--direct` flag skips confirmation and writes directly (review via git diff)
- **Format specs referenced, not embedded**: Skills point Claude to `docs/formats/markdown/` files at runtime — no duplication of format rules in skill prompts
- **Shared includes**: Common prompt fragments in `.claude/skills/includes/` (e.g., `csv-columns.md`, `format-rules.md`) referenced via `@file` syntax. DRY — update once, all skills stay in sync
- **Normalizer is a separate explicit step**: User runs normalizer independently after skill output. Not auto-invoked by skills. User can review AI output before normalization.

### Skill Count & Boundaries

- **5 skills total** (1:1 mapping to requirements + orchestrator):
  1. **qualified-candidates** (SKL-01) — processes SOS CSV into election directory + candidate stubs
  2. **normalize** (SKL-02) — also a CLI tool (`voter-api normalize elections <dir>` / `voter-api normalize candidates <dir>`)
  3. **election-calendar** (SKL-03) — processes SOS PDFs into election metadata
  4. **candidate-enrichment** (SKL-04) — adds bios, photos, contact info from web research
  5. **process-election** (orchestrator) — runs full pipeline: CSV → skill → normalize → review
- **Candidate stub creation is part of SKL-01**: Qualified-candidates skill creates both contest files AND candidate stub files in `data/candidates/`. Dedup verification happens during stub creation.

### Normalizer Design

- **Location**: New `lib/normalizer/` package following library-first pattern
- **CLI commands**: `voter-api normalize elections <dir>` and `voter-api normalize candidates <dir>` — separate commands per file type
- **Enforcement scope** (all four categories):
  - Text formatting: Smart title case (handles III, Jr, Sr, McDonald, etc.), occupation casing, date formats (MM/DD/YYYY), URL normalization (lowercase + https://)
  - Structural consistency: Table alignment, section ordering, required fields present, metadata field names match spec
  - Content validation: Flag ALL CAPS remnants, duplicate candidates, missing qualified dates. Report warnings, don't auto-fix ambiguous cases
  - Idempotency guarantee: Running normalizer twice produces identical output. Normalized files produce no diff on re-run.
- **UUID generation**: Normalizer generates UUIDs for records missing an ID row in their metadata table. For candidate files, normalizer also renames the file from placeholder name (`jane-doe-00000000.md`) to final name with UUID hash (`jane-doe-a3f2e1b4.md`)
- **Smart title case**: Not Python `str.title()` — handles suffixes (III, Jr, Sr, II, IV), Scottish prefixes (Mc, Mac), compound names (De, La, Van), and other edge cases
- **Report format**: Terminal table (human-readable) + JSON report file (machine-readable) — same pattern as converter from Phase 2

### Candidate Enrichment

- **Sources** (all four):
  1. Ballotpedia (primary source) — structured profiles, photos, bios
  2. Campaign websites — bio, photo, platform (URLs from SOS CSV)
  3. Official government sites — GA SOS, state legislature, county sites for incumbents
  4. Social media profiles — LinkedIn, Twitter/X, Facebook for photos and background
- **Uncertainty handling**: Mark confidence inline with `(unverified)` or `(source: ballotpedia)` annotations. Normalizer strips annotations before converter runs. Human reviewer sees provenance.
- **URL validation**: Skill validates URLs are live (checks if they respond). Dead links are marked.
- **Enrichment depth**: User-configurable via `--depth` flag (full/basic/minimal). User decides per invocation.
- **Two-pass approach**:
  1. **Stub creation** (part of SKL-01): Deterministic extraction from SOS CSV + AI-assisted dedup verification (web search to confirm identity for same-name candidates)
  2. **Deep enrichment** (SKL-04): Parallel agent swarm fills in stubs with web research

### Agent Team Coordination

- **Coordinator + batch workers**: One coordinator agent assigns batches of candidates to worker agents. Workers report results back. Coordinator handles dedup conflicts and final assembly
- **Partitioning**: By candidate count — coordinator pre-scans files, balances workload across workers evenly
- **Concurrency**: 4 parallel worker agents (default). Balanced throughput vs. API rate limits
- **Cooperative agent team**: Uses Claude Code's cooperative team support when enabled

### Output & File Handling

- **Full election directory per invocation**: One SKL-01 run processes an entire SOS CSV → overview file + all statewide/federal contest files + all 159 county files
- **Raw source file location**: `data/import/` (flat directory, not per-election-date subdirectories). Gitignored — SOS files are public but large. Not committed.
- **Diff-aware updates**: When re-processing (e.g., updated SOS CSV with new candidates), skill compares new CSV against existing markdown. Only adds/modifies changed candidates. Preserves manual edits and enrichment.
- **Regenerate vs. update**: Operator chooses at execution time whether to regenerate from scratch or update existing files per-election

### SOS CSV Column Mapping

- **11 columns**: CONTEST NAME, COUNTY, MUNICIPALITY, CANDIDATE NAME, CANDIDATE STATUS, POLITICAL PARTY, QUALIFIED DATE, INCUMBENT, OCCUPATION, EMAIL ADDRESS, WEBSITE
- **Direct mapping**: 7 columns map directly to markdown fields (Candidate Name, Status, Party, Qualified Date, Incumbent, Occupation, Email, Website)
- **AI-parsed**: CONTEST NAME parsed by AI to infer Body ID, Seat ID, and election type — this is the core AI value-add. Contest name formatting is wildly inconsistent in the SOS data
- **Municipality column**: Non-empty = municipal contest. Municipality name feeds Body ID scoping. Empty = county-level or statewide
- **Multi-county contests**: Grouped by contest, placed in single-contest files (statewide/federal/judicial). COUNTY column determines county file cross-references. Candidates deduplicated across county rows.
- **Name handling**: AI applies smart title case from ALL CAPS. Normalizer validates result isn't still ALL CAPS.
- **URL handling**: Skill lowercases, adds https://, AND validates URL is live. Dead links marked.
- **Column mapping documented**: Full mapping in `.claude/skills/includes/csv-columns.md` — skills and normalizer both reference this

### Election Calendar PDF Handling

- **AI reads PDFs directly**: Claude reads PDF files natively. No PDF parsing library needed.
- **Both PDFs processed**: Master calendar (`2026 Short Calendar .pdf`) for full election cycle view + per-election PDFs (`MAY_19_2026-...DATA.pdf`) for specific dates
- **Fields extracted** (all four categories):
  - Core dates: Election Day, Registration Deadline, Early Voting Start/End, Absentee Ballot Application Deadline
  - Absentee dates: Earliest Day to Mail Absentee Ballot, Earliest Day Voter Can Request Mail Ballot
  - Qualifying period: From master calendar (applies to full election cycle)
  - Participating counties list: For validation

### Error Handling & Recovery

- **Dual checkpointing**: DB entry in `import_jobs` table (reusing existing job tracking) + local JSONL checkpoint file for detailed file-level progress
- **Resume from checkpoint**: Skill detects checkpoint and resumes from where it left off
- **Strict CSV column validation**: Validate expected column headers at start. Missing/renamed columns = immediate failure with clear message listing expected vs. found columns.

### Testing Strategy

- **AI skills tested via pipeline**: Skill output → normalizer (must pass without structural errors) → converter (must produce valid JSONL). Downstream tools ARE the tests.
- **Normalizer tested comprehensively** (all three approaches):
  - Golden file tests: Before/after fixture files. Normalizer runs on 'before', asserts output matches 'after'. Tests idempotency by running twice.
  - Property-based tests: Hypothesis-generated markdown inputs. Assert normalizer output is always valid and idempotent.
  - Unit tests per rule: Individual tests for each normalization rule (title case, URLs, dates, etc.)
- **Synthetic CSV fixture**: Small fake CSV (~20 candidates, 3-4 contests) exercising edge cases (ALL CAPS, suffixes, special characters, duplicate names). Used for normalizer golden file tests and manual skill testing.

### Data Processing Scope

- **All three available CSVs processed**: May 19 general primary (2,346 rows), March 17 special election (9 rows), March 10 special election (38 rows)
- **May 19 existing files regenerated**: Run skill from scratch on SOS CSV. Compare against existing ~200 files via git diff. Validates skill produces equivalent or better output.
- **Phase 3 produces demo-ready data**: Both tools AND processed markdown for all three elections. Phase 4 runs converter + import + API validation.

### Plan Splitting

- **Claude's discretion**: Planner determines optimal plan count, sequencing, and build order based on dependency analysis and scope sizing
- **No sequencing constraints**: Planner decides whether normalizer comes first or skills ship first

### Claude's Discretion

- Plan count and sequencing
- Normalizer internal architecture (submodule breakdown within lib/normalizer/)
- Skill prompt engineering details and structure
- Shared include file organization and content
- Agent team implementation details
- Checkpoint file format
- Synthetic CSV fixture content and edge cases

</decisions>

<specifics>
## Specific Ideas

- The SOS CSV CONTEST NAME column is wildly inconsistent: "Board of Commissioner District 2(R)" (no space), "Board of Commissioners - District 2 (R)" (dash separator), "BOARD OF EDUCATION AT LARGE-POST 7" (all caps). This is where AI parsing earns its keep.
- Same candidate appears in multiple county rows for multi-county contests (US House, State House/Senate, judicial circuits). Deduplication across rows is essential.
- The `data/candidates/` directory is empty — Phase 3 creates it. Candidate files use placeholder filenames during skill creation, normalizer renames with UUID hash.
- The existing ~200 markdown files in `data/elections/2026-05-19/` were created by Claude without formalized skills. Phase 3 formalizes that workflow and regenerates from CSV to validate.
- The 2,346-row May 19 CSV confirms thousands of candidates per election — agent team coordination is necessary for enrichment at scale.
- March 10 special election has no existing markdown files (March 17 has 4). All three elections exercise different contest types (general primary, special election with US House + local races).
- SOS qualified candidates CSV uses same 11-column format across all elections — skill handles them identically.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docs/formats/markdown/` — 5 format specs (single-contest, multi-contest, election-overview, candidate-file, county-reference) defining target output format
- `docs/formats/vocabularies/` — 5 controlled vocabulary specs (boundary-types, election-types, filing-status, link-types, seat-ids)
- `docs/formats/specs/` — 3 process specs (backfill-rules, migration-rules, uuid-strategy)
- `data/states/GA/counties/` — All 159 county reference files with governing body structures (Body IDs, Seat patterns, boundary_types)
- `data/elections/2026-05-19/` — ~200 existing markdown files (27 statewide + ~170 county files) as baseline comparison
- `data/elections/2026-03-17/` — 4 existing special election files
- `data/new/` (worktree) — 3 SOS CSVs, 3 PDFs, absentee data (A-12599.zip), voter history (2026.csv)
- `src/voter_api/schemas/jsonl/` — 4 JSONL Pydantic schema models for validation
- `src/voter_api/lib/converter/` — Existing converter library (normalizer output must be compatible with converter input)
- `src/voter_api/cli/import_cmd.py` — CLI patterns: Typer app, asyncio.run wrapper, summary table printing
- `.claude/commands/` — 12 existing commands (hatchkit, speckit) showing command file patterns
- `import_jobs` table — Existing job tracking with status lifecycle (reused for normalizer/skill checkpointing)

### Established Patterns
- Library-first architecture: `lib/` subpackages with `__init__.py` public API + `__all__` list
- CLI commands: Typer app in `cli/{command}_cmd.py`, registered in `cli/app.py:_register_subcommands()`
- Terminal table + JSON report for validation output (used by converter)
- Ruff linting and formatting (must pass before commit)
- Google-style docstrings on all public APIs
- Type hints on all functions

### Integration Points
- `lib/normalizer/` — New library, output consumed by `lib/converter/`
- `cli/normalize_cmd.py` — New CLI module with `elections` and `candidates` subcommands
- `.claude/skills/` — New directory for skill files
- `.claude/commands/election.*.md` — New namespaced commands
- `.claude/skills/includes/` — New directory for shared prompt fragments
- `data/candidates/` — Currently empty, populated by skills
- `data/import/` — New directory (gitignored) for SOS source files, replacing `data/new/`

</code_context>

<deferred>
## Deferred Ideas

- **Absentee ballot data processing** — A-12599.zip contains per-county absentee ballot application data (voter PII, ballot status, precinct assignments). Different data type requiring its own skill and import pipeline. Future milestone.
- **Voter history import via skill** — 2026.csv (11MB) contains voter history records. Existing ZIP import works; JSONL import is a v2 requirement (EXT-02).
- **SOS results URL scraper** — Automated discovery of results feed URLs when they become available. Future capability.
- **Historical election backfill** (2024-2025) — Separate effort, different data source.
- **Skill for populating county reference files** — County reference files are already populated (Phase 2). Future elections may need new governing bodies added.
- **Round-trip validation** (MD → JSONL → DB → export matches original) — v2 requirement (EXT-04).

</deferred>

---

*Phase: 03-claude-code-skills*
*Context gathered: 2026-03-15*
