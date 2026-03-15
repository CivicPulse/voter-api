# Roadmap: Better Imports

## Overview

This roadmap delivers a three-stage data import pipeline for Georgia SOS election data. We start by defining the data contracts (markdown format specs and JSONL schemas), then build the deterministic converter and CLI import pipeline as a single delivery, then create the Claude Code skills that generate the markdown input, and finally prove the full pipeline end-to-end with a May 19 election demo.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Data Contracts** - Define the enhanced markdown format and JSONL schemas that every downstream component depends on
- [x] **Phase 2: Converter and Import Pipeline** - Build the deterministic MD-to-JSONL converter and CLI import commands so JSONL files reach the database (completed 2026-03-15)
- [ ] **Phase 3: Claude Code Skills** - Create the AI-assisted skills and deterministic normalizer that produce markdown from raw SOS data
- [ ] **Phase 4: End-to-End Demo** - Prove the full pipeline with May 19 SOS data from raw CSV through to API query results

## Phase Details

### Phase 1: Data Contracts
**Goal**: All intermediate data formats are fully specified so converter, importer, and skills can be built against stable contracts
**Depends on**: Nothing (first phase)
**Requirements**: FMT-01, FMT-02, FMT-03, FMT-04, FMT-05, FMT-06
**Success Criteria** (what must be TRUE):
  1. A markdown file following the enhanced format spec can represent any Georgia contest with its district linkage (boundary_type + district_identifier), and the format is documented with examples
  2. A markdown file following the enhanced format spec includes election metadata (early voting, registration deadline, absentee deadline) and candidate details (party, photo URL, bio, contact info, external IDs)
  3. JSONL schema definitions for elections and candidates exist with field-level documentation, and every field maps 1:1 to the corresponding DB model column
  4. JSONL files include a `_schema_version` field and the schema documents how version changes are handled
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Controlled vocabularies and enhanced markdown format specifications
- [x] 01-02-PLAN.md — JSONL Pydantic schema models with TDD tests
- [x] 01-03-PLAN.md — JSONL doc generation, Bibb example, and process specs (UUID, backfill, migration)

### Phase 2: Converter and Import Pipeline
**Goal**: Markdown files deterministically convert to validated JSONL, and JSONL files load into the database via CLI commands with idempotent, verifiable results
**Depends on**: Phase 1
**Requirements**: CNV-01, CNV-02, CNV-03, CNV-04, IMP-01, IMP-02, IMP-03, IMP-04
**Success Criteria** (what must be TRUE):
  1. Running the converter on an election markdown directory produces JSONL files that pass Pydantic validation against the schemas defined in Phase 1, with a report showing parse successes, failures, and missing fields
  2. Running `voter-api import elections <file.jsonl>` loads election records into the database and the elections appear in API query results
  3. Running `voter-api import candidates <file.jsonl>` loads candidate records into the database and the candidates appear in API query results
  4. Re-importing the same JSONL file a second time produces no duplicate records, no data changes, and no errors
  5. Running import with `--dry-run` reports what would be imported without writing any records to the database
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — DB migrations and model refactoring (candidacy junction table, ElectionEvent enhancement, API schema updates, E2E test fixes)
- [x] 02-02-PLAN.md — Converter library (lib/converter/ with mistune AST parser, JSONL writer, Body/Seat resolver, CLI command, 159 county reference files)
- [x] 02-03-PLAN.md — Import pipeline and file migration (4 JSONL import services + CLI commands, pipeline command, file migration script, UUID backfill)

### Phase 3: Claude Code Skills
**Goal**: A user working in Claude Code can process raw GA SOS data files into human-reviewable markdown that conforms to the enhanced format spec
**Depends on**: Phase 1
**Requirements**: SKL-01, SKL-02, SKL-03, SKL-04
**Success Criteria** (what must be TRUE):
  1. Running the qualified-candidates skill on a GA SOS CSV produces per-election markdown files with correct contest names, candidate details, and district linkage -- and the output passes the deterministic normalizer without structural changes
  2. Running the deterministic normalizer on AI-generated markdown enforces title case, URL normalization, occupation formatting, and field consistency, producing stable output across repeated runs
  3. Running the election-calendar skill on a GA SOS PDF produces election metadata (dates, deadlines) in the correct markdown format fields
  4. Running the candidate-enrichment skill adds bios, photo URLs, and contact info from web research to existing candidate markdown files
**Plans**: 4 plans

Plans:
- [ ] 03-01-PLAN.md — Normalizer library core: smart title case, URL/date/occupation rules, report generator (TDD)
- [ ] 03-02-PLAN.md — Normalizer file engine, UUID handler, CLI commands, golden files, and Hypothesis tests
- [ ] 03-03-PLAN.md — Skills infrastructure: shared includes, qualified-candidates skill, normalize skill, /election:process and /election:normalize commands
- [ ] 03-04-PLAN.md — Election calendar skill, candidate enrichment skill, pipeline orchestrator, remaining /election:* commands

### Phase 4: End-to-End Demo
**Goal**: The full pipeline is proven working from raw SOS source data to queryable API results, validating that all three stages integrate correctly
**Depends on**: Phase 2, Phase 3
**Requirements**: DEM-01
**Success Criteria** (what must be TRUE):
  1. Starting from a real May 19 GA SOS qualified candidates CSV, the full pipeline executes: skill produces markdown, markdown is reviewed in git, converter produces JSONL, import loads the database, and elections + candidates are queryable via the API
  2. The demo is documented as a reproducible walkthrough that another user could follow
**Plans**: TBD

Plans:
- [ ] 04-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4

Note: Phase 3 depends only on Phase 1 (not Phase 2), so phases 2 and 3 could theoretically execute in parallel. However, sequential execution is recommended for a solo developer.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Contracts | 3/3 | Complete | 2026-03-14 |
| 2. Converter and Import Pipeline | 3/3 | Complete   | 2026-03-15 |
| 3. Claude Code Skills | 0/4 | In progress | - |
| 4. End-to-End Demo | 0/? | Not started | - |
