# Phase 5: Milestone Cleanup & Traceability - Research

**Researched:** 2026-03-15
**Domain:** Documentation cleanup, traceability fixes, Nyquist validation
**Confidence:** HIGH

## Summary

Phase 5 is a documentation and traceability cleanup phase with no new code, no new libraries, and no architectural changes. The work breaks into two distinct categories: (1) fixing documentation inaccuracies and stale traceability identified in the v1.0 milestone audit, and (2) running Nyquist validation for phases that are missing it.

The audit identified 6 tech debt items. Four require text edits to existing files (walkthrough corrections, REQUIREMENTS.md checkbox, ROADMAP.md scope update). One requires running an existing CLI command (`voter-api import resolve-elections`) and capturing its output for the walkthrough. The final item (Nyquist validation) requires running `validate-phase` for phases 3 and 4 (phases 1 and 2 are already validated).

**Primary recommendation:** This is a straightforward editing phase. The only risk is the resolve-elections step, which requires a running PostGIS database with imported demo data. Plan should ensure the database is up and data is loaded before capturing terminal output.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **election_event_id FK Resolution**: Fix it in the walkthrough by adding a `voter-api import resolve-elections` step to docs/pipeline-walkthrough.md after the import step. Run against local dev DB (docker-compose PostGIS) with the imported demo data to capture real terminal output. Add API verification query showing election detail with non-null election_event_id.
- **Walkthrough Corrections**: Full walkthrough review -- read the entire document and fix any inaccuracies found, not just the known issues. Line 366: fix inaccurate claim. Branch reference (line 21): remove branch checkout instruction entirely, assume pipeline code is on main, plain clone instruction.
- **REQUIREMENTS.md Update**: Just fix DEM-01 -- update from "In Progress" to "Complete". No full re-verification.
- **Nyquist Validation**: Run validate-phase for all 4 completed phases sequentially (1->2->3->4). Separate plan (Plan 2) from documentation fixes (Plan 1).
- **Plan Structure**: Two plans -- 05-01 (documentation fixes) and 05-02 (Nyquist validation).
- **ROADMAP.md Updates**: Update Phase 5 success criteria to reflect expanded scope.
- **Planning Artifacts**: Commit v1.0-MILESTONE-AUDIT.md and 03-CONTEXT.md as part of Phase 5.
- **Commit Strategy**: One commit per logical change -- separate commits for walkthrough fixes, REQUIREMENTS.md fix, audit file, 03-CONTEXT.md, each Nyquist phase validation.
- **STATE.md**: Leave for /gsd:complete-milestone -- Phase 5 does content work only.

### Claude's Discretion
- Exact walkthrough text corrections (beyond the known issues)
- resolve-elections step placement within the walkthrough flow
- Nyquist validation test selection per phase
- Commit message wording for each logical change

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DEM-01 | End-to-end demo: May 19 SOS CSV through full pipeline to API query results | Traceability fix: REQUIREMENTS.md checkbox update from "In Progress" to "Complete". Walkthrough corrections make the demo documentation accurate. resolve-elections step closes the election_event_id FK gap in the documented pipeline. |
</phase_requirements>

## Standard Stack

No new libraries or dependencies are needed. This phase modifies only existing documentation and planning files.

### Core Tools Used
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| docker-compose | existing | Run PostGIS for resolve-elections output capture | Already configured in project |
| voter-api CLI | existing | `import resolve-elections` command | Already implemented in src/voter_api/cli/import_cmd.py |
| curl + jq | existing | API verification in walkthrough | Walkthrough pattern uses these universally |
| pytest | existing | Nyquist validation test runs | Project test framework |

## Architecture Patterns

### Files Being Modified

```
docs/
  pipeline-walkthrough.md       # Full review + corrections + new resolve-elections section

.planning/
  REQUIREMENTS.md               # DEM-01 checkbox: "In Progress" -> "Complete" (already done per audit)
  ROADMAP.md                    # Phase 5 success criteria expansion
  v1.0-MILESTONE-AUDIT.md       # Commit untracked file (already exists)
  phases/
    03-claude-code-skills/
      03-CONTEXT.md             # Commit untracked file (already exists)
    03-claude-code-skills/
      03-VALIDATION.md          # Nyquist validation update
    04-end-to-end-demo/
      04-VALIDATION.md          # Nyquist validation update
```

### Walkthrough Edit Pattern

The walkthrough follows a consistent structure:
1. Each step has a heading (`## Step N: ...`)
2. Commands shown in fenced bash blocks with explicit env vars
3. Expected output in plain fenced blocks
4. Explanatory prose between blocks

The resolve-elections section should follow this exact pattern. It logically fits after the import step (Step 5/6) and before the API verification step.

### Walkthrough Known Issues

| Location | Issue | Fix |
|----------|-------|-----|
| Line 21 | `git checkout worktree-better-imports   # or main once merged` | Remove entirely -- just `git clone` + `cd voter-api` + `uv sync` |
| Lines 364-367 | Claims election_event_id "is resolved during import using the matching event in the database" | Rewrite to explain it's stored as NULL, then resolved by the new resolve-elections step documented later |
| Full document | Unknown inaccuracies | Thorough read-through during execution |

### REQUIREMENTS.md Current State

The audit found DEM-01 traceability row says "In Progress" but the current file actually shows:
```
| DEM-01 | Phase 4 | Complete |
```
This was already updated per the audit note: "Last updated: 2026-03-15 after v1.0 milestone audit gap closure". However, the CONTEXT.md decision says to update it, so the planner should verify current state and update if still stale.

### Nyquist Validation Current State

| Phase | VALIDATION.md Status | nyquist_compliant | Action Needed |
|-------|---------------------|-------------------|---------------|
| 01-data-contracts | validated | **true** | Already done -- skip or verify only |
| 02-converter-and-import-pipeline | complete | **true** | Already done -- skip or verify only |
| 03-claude-code-skills | draft | **false** | Needs full validation |
| 04-end-to-end-demo | draft | **false** | Needs full validation |

Key finding: Phases 1 and 2 are already Nyquist-compliant (validated during a previous audit pass). The CONTEXT.md says "run validate-phase for all 4 completed phases" but phases 1 and 2 are already done. The planner should note this -- only phases 3 and 4 actually need work.

### Phase 3 Validation Gaps

Phase 3 VALIDATION.md has:
- All Wave 0 items unchecked (test files listed as missing)
- All per-task verification statuses at "pending"
- All sign-off checkboxes unchecked

However, these tests likely exist now (they were created during phase 3 execution). The validation just needs to be run and the VALIDATION.md updated to reflect actual state.

### Phase 4 Validation Gaps

Phase 4 VALIDATION.md has:
- All per-task statuses at "pending"
- All sign-off checkboxes unchecked
- DEM-01 tasks are manual-only (walkthrough execution)

Phase 4 is primarily a documentation/demo requirement, so its validation is mostly manual sign-off that the walkthrough was executed and reviewed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| election_event_id resolution | Custom SQL or script | `voter-api import resolve-elections` | CLI command already exists and handles the three-tier matching logic |
| Nyquist validation | Manual checklist work | `/gsd:validate-phase N` workflow | Standard GSD validation workflow |

## Common Pitfalls

### Pitfall 1: Running resolve-elections Without Imported Data
**What goes wrong:** The resolve-elections command needs elections already imported into the database. Running it on an empty or freshly-migrated DB produces no useful output.
**Why it happens:** The walkthrough output capture requires the full pipeline to have been run first.
**How to avoid:** Follow walkthrough steps 1-6 first (docker compose up, migrations, import election-data), then run resolve-elections.
**Warning signs:** "0 records resolved" in output.

### Pitfall 2: Walkthrough Line Numbers Shifting
**What goes wrong:** References to specific line numbers (366, 21) may be stale if previous edits have shifted content.
**Why it happens:** Line numbers are fragile references in living documents.
**How to avoid:** Search for the actual text content rather than relying on line numbers. The key phrases are: "is resolved during import" (line 366 area) and "git checkout worktree-better-imports" (line 21 area).

### Pitfall 3: REQUIREMENTS.md Already Updated
**What goes wrong:** Attempting to fix something that's already been fixed, creating a no-op commit.
**Why it happens:** The audit was run, then the REQUIREMENTS.md was updated (per the "Last updated" timestamp), but the CONTEXT.md still lists it as needing fixing.
**How to avoid:** Read current state before editing. If DEM-01 already shows "Complete", verify and skip.

### Pitfall 4: Nyquist Validation for Already-Validated Phases
**What goes wrong:** Re-running validate-phase for phases 1 and 2 that are already nyquist_compliant: true.
**Why it happens:** CONTEXT.md says "all 4 phases" but phases 1 and 2 were validated during a previous audit pass.
**How to avoid:** Check frontmatter of each VALIDATION.md before running. Skip phases that are already compliant.

## Code Examples

### resolve-elections CLI Command

Source: `src/voter_api/cli/import_cmd.py` line 614

```python
@import_app.command("resolve-elections")
def resolve_elections_cmd(
    date_str: str | None = typer.Option(None, "--date", help="Resolve only this date (YYYY-MM-DD)"),
    force: bool = typer.Option(False, "--force", help="Re-resolve records that already have election_id"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be resolved without making changes"),
) -> None:
    """Resolve voter_history.election_id by linking records to elections."""
```

### Running resolve-elections for Walkthrough

```bash
DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api \
  JWT_SECRET_KEY=test-secret-key-minimum-32-characters \
  uv run voter-api import resolve-elections
```

### API Verification Pattern (from existing walkthrough)

```bash
DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api \
  JWT_SECRET_KEY=test-secret-key-minimum-32-characters \
  uv run voter-api serve &

# Query election detail to verify election_event_id is populated
curl -s http://localhost:8000/api/v1/elections | jq '.[0].election_event_id'
```

### Walkthrough Branch Fix

Current (line 18-22):
```bash
git clone https://github.com/CivicPulse/voter-api.git
cd voter-api
git checkout worktree-better-imports   # or main once merged
uv sync
```

Fixed:
```bash
git clone https://github.com/CivicPulse/voter-api.git
cd voter-api
uv sync
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | `pyproject.toml` ([tool.pytest.ini_options]) |
| Quick run command | `uv run pytest tests/unit/lib/test_normalizer/ -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEM-01 | Traceability checkbox accurate | manual | N/A -- documentation fix | N/A |
| DEM-01 | Walkthrough accurately documents pipeline | manual | N/A -- documentation fix | N/A |
| DEM-01 | resolve-elections step documented with real output | manual | N/A -- requires running PostGIS | N/A |

### Sampling Rate
- **Per task commit:** `uv run ruff check . && uv run ruff format --check .` (no code changes, but lint check ensures no accidental code edits)
- **Per wave merge:** `uv run pytest` (full suite -- verify nothing broken)
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
None -- Phase 5 is documentation-only. No new test infrastructure needed. Nyquist validation for phases 3 and 4 uses existing test infrastructure.

## Sources

### Primary (HIGH confidence)
- `.planning/v1.0-MILESTONE-AUDIT.md` -- full audit identifying all 6 tech debt items
- `.planning/phases/05-milestone-cleanup/05-CONTEXT.md` -- user decisions locking implementation approach
- `docs/pipeline-walkthrough.md` -- the primary file being corrected (874 lines)
- `src/voter_api/cli/import_cmd.py` -- resolve-elections command implementation (line 614)
- `.planning/phases/*/VALIDATION.md` -- current Nyquist validation state for all 4 phases

### Secondary (MEDIUM confidence)
- None needed -- all information sourced from project files

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all tools already in project
- Architecture: HIGH -- pure documentation edits to known files
- Pitfalls: HIGH -- all issues documented in audit with specific line references

**Research date:** 2026-03-15
**Valid until:** 2026-04-15 (stable -- documentation cleanup, no API changes)
