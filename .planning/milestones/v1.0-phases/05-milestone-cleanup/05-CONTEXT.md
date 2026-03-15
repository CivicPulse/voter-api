# Phase 5: Milestone Cleanup & Traceability - Context

**Gathered:** 2026-03-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix all tech debt identified in the v1.0 milestone audit: documentation inaccuracies in the pipeline walkthrough, stale traceability in REQUIREMENTS.md, the election_event_id FK gap, untracked planning artifacts, and Nyquist validation gaps across all 4 completed phases. Phase 5 is the final phase before milestone archival.

</domain>

<decisions>
## Implementation Decisions

### election_event_id FK Resolution
- **Fix it in the walkthrough**: Add a `voter-api import resolve-elections` step to docs/pipeline-walkthrough.md after the import step
- **Run against local dev DB** (docker-compose PostGIS) with the imported demo data to capture real terminal output
- **Add API verification query**: Include a curl showing election detail with non-null election_event_id to prove resolve-elections worked — consistent with walkthrough's verification pattern
- **Real terminal output required**: Capture actual output from running resolve-elections, same as all other walkthrough steps

### Walkthrough Corrections
- **Full walkthrough review**: Read the entire document and fix any inaccuracies found, not just the known issues (line 366, line 21)
- **Line 366**: Fix inaccurate claim that election_event_id "is resolved during import" — it's NULL after import, resolved by the new resolve-elections step
- **Branch reference (line 21)**: Remove the branch checkout instruction entirely. Assume pipeline code is on main. Plain clone instruction.
- **No specific pre-defined worry list**: Thorough read-through during execution; fix whatever is found

### REQUIREMENTS.md Update
- **Just fix DEM-01**: Update the traceability row from "In Progress" to "Complete". Trust the audit's 18/19 finding for other requirements — no full re-verification needed.

### Nyquist Validation
- **Added to Phase 5 scope**: Run validate-phase for all 4 completed phases to fill Nyquist validation gaps
- **Sequential execution**: Run phases 1→2→3→4 in order (not parallel). Safer for context window management.
- **Separate plan**: Nyquist is Plan 2, isolated from documentation fixes in Plan 1

### Plan Structure
- **Two plans**:
  - **05-01**: Documentation fixes — walkthrough full review + corrections, resolve-elections step with real output, REQUIREMENTS.md DEM-01 fix, ROADMAP.md success criteria update, audit file commit, 03-CONTEXT.md commit
  - **05-02**: Nyquist validation — run validate-phase sequentially for phases 1, 2, 3, 4

### ROADMAP.md Updates
- **Update Phase 5 success criteria** to reflect expanded scope (Nyquist validation, full walkthrough review, audit file, 03-CONTEXT.md)

### Planning Artifacts
- **Commit v1.0-MILESTONE-AUDIT.md** as part of Phase 5 — provides traceability for why these changes were made
- **Commit 03-CONTEXT.md** from Phase 3 — planning artifact that was created but never committed

### Commit Strategy
- **One commit per logical change**: Separate commits for walkthrough fixes, REQUIREMENTS.md fix, audit file, 03-CONTEXT.md, each Nyquist phase validation. Granular, reviewable, revertable.

### STATE.md
- **Leave for /gsd:complete-milestone**: Phase 5 does the content work; milestone completion workflow handles STATE.md finalization to 100%

### Claude's Discretion
- Exact walkthrough text corrections (beyond the known issues)
- resolve-elections step placement within the walkthrough flow
- Nyquist validation test selection per phase
- Commit message wording for each logical change

</decisions>

<specifics>
## Specific Ideas

- The walkthrough is the final deliverable for the "Better Imports" milestone — it needs to be accurate and complete before archival
- Adding resolve-elections + API verification closes the loop on the full pipeline: SOS CSV → markdown → JSONL → import → resolve FKs → queryable API results
- Sequential Nyquist validation is preferred over parallel because each phase builds on the previous and context management is simpler
- The audit file itself is documentation of what Phase 5 is fixing — committing it creates a self-documenting trail

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `voter-api import resolve-elections` CLI command: Already exists, resolves election_event_id FKs by matching elections to events. Just needs to be run and documented.
- `docs/pipeline-walkthrough.md`: The primary document being corrected — ~900 lines of step-by-step pipeline documentation with real terminal output
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md`: Untracked audit artifact documenting all 6 tech debt items that Phase 5 addresses
- `.planning/milestones/v1.0-phases/03-claude-code-skills/03-CONTEXT.md`: Untracked context file from Phase 3 discussion
- `.planning/milestones/v1.0-phases/*/VALIDATION.md`: Existing stubs with `nyquist_compliant: false` in all 4 phases

### Established Patterns
- Walkthrough uses curl for all API verification (zero dependencies, universal)
- All walkthrough commands show explicit env vars: DATABASE_URL, JWT_SECRET_KEY
- Conventional commit messages with scope prefix: `docs(phase-05):`, `test(phase-02):`, etc.
- VALIDATION.md files follow GSD Nyquist validation format with wave-based structure

### Integration Points
- `docs/pipeline-walkthrough.md` — corrections and new resolve-elections section
- `.planning/REQUIREMENTS.md` — DEM-01 checkbox update
- `.planning/ROADMAP.md` — Phase 5 success criteria expansion
- `.planning/milestones/v1.0-phases/*/VALIDATION.md` — Nyquist validation updates for phases 1-4
- docker-compose PostGIS — needed for running resolve-elections to capture real output

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-milestone-cleanup*
*Context gathered: 2026-03-15*
