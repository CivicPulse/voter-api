---
name: qualified-candidates
description: Process a GA SOS qualified candidates CSV into per-election structured markdown files. Use when importing new election data from the Georgia Secretary of State.
argument-hint: <csv-file-path> [--direct]
disable-model-invocation: true
---

# Qualified Candidates Skill

Process a Georgia Secretary of State qualified candidates CSV file into structured markdown files
following the enhanced format specification. Produces an election overview file, per-contest
files (statewide/federal), county multi-contest files, and candidate stub files.

## 1. Input Validation

Parse `$ARGUMENTS` to extract:
- `$0` — path to the SOS qualified candidates CSV file (required)
- `--direct` flag — if present, skip interactive confirmation and write files directly

**Validate the CSV before any processing:**

1. Open the CSV file and read the header row
2. Expected columns (exactly): `CONTEST NAME`, `COUNTY`, `MUNICIPALITY`, `CANDIDATE NAME`, `CANDIDATE STATUS`, `POLITICAL PARTY`, `QUALIFIED DATE`, `INCUMBENT`, `OCCUPATION`, `EMAIL ADDRESS`, `WEBSITE`
3. If column count or names do not match:
   - Print: `ERROR: Unexpected CSV columns.`
   - Print: `Expected: CONTEST NAME, COUNTY, MUNICIPALITY, CANDIDATE NAME, CANDIDATE STATUS, POLITICAL PARTY, QUALIFIED DATE, INCUMBENT, OCCUPATION, EMAIL ADDRESS, WEBSITE`
   - Print: `Found: {actual column headers}`
   - Exit with error — do not continue processing

4. Load all CSV rows into memory. Count total rows. Print: `Loaded {N} rows from {filename}.`

## 2. Format References

Before generating any output, read these format specifications:

- @docs/formats/markdown/election-overview.md
- @docs/formats/markdown/single-contest.md
- @docs/formats/markdown/multi-contest.md
- @docs/formats/markdown/candidate-file.md
- @docs/formats/vocabularies/election-types.md
- @docs/formats/vocabularies/boundary-types.md
- @docs/formats/vocabularies/seat-ids.md

These specs define the exact structure, field names, and content rules for all output files.
**Do not guess** at format details — read the specs.

## 3. CSV Column Reference

Read the full column mapping guide:

- @.claude/skills/includes/csv-columns.md

Key rules from the mapping:
- `CONTEST NAME` is AI-parsed — not a direct field mapping
- `COUNTY` empty = statewide/federal; non-empty = county-level
- `MUNICIPALITY` non-empty = municipal contest
- Multi-county contests appear as multiple rows with different COUNTY values — deduplicate candidates

## 4. Contest Name Parsing

Read the contest name parsing guide:

- @.claude/skills/includes/contest-patterns.md

This is the **core AI value-add**. Parse each unique `CONTEST NAME` (after stripping party suffix)
into: `body_id`, `seat_id`, `election_type`.

**Rules:**
- Strip party suffix `(R)`, `(D)`, `(L)`, `(I)`, `(NP)` (with or without leading space) BEFORE parsing
- Record stripped party separately for grouping
- Use AI pattern matching against the examples in `contest-patterns.md` — NEVER use only deterministic string matching
- Handle ALL CAPS, mixed case, various separators (dash, comma, parentheses)
- When a contest name is genuinely unparseable: log a warning, skip the contest, continue

## 5. Diff-Aware Updates

Before generating output, check if the target election directory already exists.

**Step 1:** Determine the election date from the CSV filename or QUALIFIED DATE column values.
Derive the target directory: `data/elections/{date}/`

**Step 2:** Check if `data/elections/{date}/` exists and contains files.

**If directory does NOT exist:** Proceed with fresh generation (skip to Section 7).

**If directory EXISTS with files:**
1. Report: `Election directory data/elections/{date}/ already exists with {N} files.`
2. If `--direct` flag is set: automatically use **Regenerate mode** (print: `Using regenerate mode (--direct flag set).`)
3. Otherwise, ask the operator:
   ```
   Choose mode:
   [1] Regenerate from scratch — overwrite all files (clean slate from CSV)
   [2] Update mode — add new candidates, update changed fields, preserve manual edits

   Enter 1 or 2:
   ```

**Regenerate mode:**
- Delete any checkpoint file first: `data/elections/{date}/.checkpoint.jsonl`
- Delete all files in the existing directory
- Proceed with fresh generation from Section 7

**Update mode:**
1. Load existing markdown files, extract current candidate lists per contest
2. Compare CSV candidates against existing candidates (match by candidate name + party + contest)
3. Plan: add new candidates not in existing files; update changed status/party/qualified date
4. Preserve fields NOT in the CSV (bio, photo, enrichment data, links, manual edits)
5. After processing: report `Added {X} new candidates, updated {Y} fields, {Z} files unchanged.`

## 6. Checkpoint & Resume

Use a JSONL checkpoint file to enable resumable processing of large CSVs.

**Checkpoint file location:** `data/elections/{date}/.checkpoint.jsonl`

Note: Add `.checkpoint.jsonl` to the election directory's `.gitignore` if one exists, or document
it as a temporary file that is deleted on successful completion.

### Detecting an Existing Checkpoint

Before processing begins (after diff-aware check):
1. Check if `data/elections/{date}/.checkpoint.jsonl` exists
2. If it exists, read all lines and build a set of already-processed contest names
3. Report: `Found checkpoint with {N} contests already processed. Resuming from contest {N+1}.`
4. Skip contests whose `contest_name` appears in the checkpoint set
5. Continue processing remaining contests, appending new lines to the checkpoint file

### Writing Checkpoint Entries

After each contest is fully processed (contest file written + candidate stubs created),
append a JSONL line to `data/elections/{date}/.checkpoint.jsonl`:

```json
{"contest_name": "Board of Education District 3", "file_written": "2026-05-19-fulton-boe-district-3.md", "candidates_created": 4, "timestamp": "2026-03-15T10:30:00Z"}
```

### Checkpoint Cleanup

When all contests are processed successfully:
- Delete `data/elections/{date}/.checkpoint.jsonl`
- A completed run needs no checkpoint file

### Checkpoint + Regenerate Interaction

If the user chooses regenerate mode and a checkpoint exists:
- Delete the checkpoint file first (starting completely fresh)
- Then proceed with normal fresh generation

## 7. Processing Steps

Work through the CSV in this order:

**Step 1: Determine election date**
- Parse from CSV filename (e.g., `2026-05-19-qualified-candidates.csv` → `2026-05-19`)
- Or derive from the dominant QUALIFIED DATE value if filename is not date-prefixed
- Confirm: print `Processing election date: {date}`

**Step 2: Group rows by CONTEST NAME**
- Strip party suffix from each CONTEST NAME
- Group all rows by the stripped contest name
- This creates one contest group per office (e.g., "Governor" groups all Governor rows)

**Step 3: Check for checkpoint and load already-processed contests**
- See Section 6 — skip contests already in the checkpoint set

**Step 4: Parse each contest group**
For each unprocessed contest group:
- Infer `body_id`, `seat_id`, `election_type` from contest name (see Section 4)
- Classify contest type:
  - Statewide/federal: COUNTY column is empty (or all rows have different counties = multi-county)
  - County-specific: single COUNTY value, MUNICIPALITY empty
  - Municipal: MUNICIPALITY column non-empty

**Step 5: Deduplicate candidates within each contest**
- Two rows represent the same candidate if they share `CONTEST NAME` (stripped) + `CANDIDATE NAME`
- Deduplicate across county rows for multi-county contests
- Apply smart title case to CANDIDATE NAME (see `format-rules.md`)

**Step 6: Create election directory**
- `data/elections/{date}/` — create if it does not exist
- `data/elections/{date}/counties/` — create subdirectory for county files

**Step 7: Create election overview file**
- Path: `data/elections/{date}/{date}-{type-slug}.md`
- Metadata table: ID empty (normalizer fills), Format Version 1, Type, Stage `election`
- Sections: Statewide Races, Federal Races, State Legislative Races, Local Elections (as applicable)
- Counts per section are derived from the processed contest groups

**Step 8: Create statewide and federal single-contest files**
- Path: `data/elections/{date}/{date}-{contest-slug}.md`
- For partisan primaries: group candidates by party into `## Republican Primary` / `## Democrat Primary` sections
- For non-partisan/special: use single `## Candidates` section
- Metadata: ID empty, Format Version 1, Election (link to overview), Type, Stage, Body, Seat, Name (SOS)

**Step 9: Create county multi-contest files**
- Path: `data/elections/{date}/counties/{date}-{county}.md`
- One file per county, grouping all that county's local contests
- Each contest in the file has a `**Body:** {body-id} | **Seat:** {seat-id}` metadata line
- Metadata: ID empty, Format Version 1, Election (link to overview), Type, Contests count, Candidates count
- Include `## Statewide & District Races` section listing which statewide/federal contests voters in that county will also see

**Step 10: Create candidate stub files**
- Path: `data/candidates/{name-slug}-00000000.md`
- One file per unique person (deduplicated across all contests)
- Stub content: Metadata table (ID empty, Format Version 1, Name, Photo URL `--`, Email from CSV or `--`), Bio section `--`, External IDs table (all `--`), Links table (email + website from CSV), Elections section with this contest
- Placeholder filename uses `00000000` — normalizer renames to real UUID hash
- If two candidates share the same name slug: append sequence number (`jane-doe-00000000-2.md`)

**Step 11: Write checkpoint entry per contest**
After completing each contest's files (contest file + any candidate stubs):
Append JSONL line to checkpoint file (see Section 6)

**Step 12: Delete checkpoint file on completion**
After all contests are processed successfully, delete `.checkpoint.jsonl`

## 8. Output Structure

```
data/elections/{date}/
├── {date}-{type}.md              # Election overview
├── {date}-governor.md            # Statewide contest (example)
├── {date}-us-house-district-01.md  # Federal contest (example)
├── .checkpoint.jsonl             # Temporary — deleted on successful completion
└── counties/
    ├── {date}-bibb.md            # County multi-contest file
    └── {date}-fulton.md          # County multi-contest file
data/candidates/
├── jane-doe-00000000.md          # Candidate stub (normalizer renames with UUID hash)
└── john-smith-00000000.md        # Candidate stub
```

## 9. Interactive Mode

**Default (no --direct flag):**
- Before writing each file, display the file's full content
- Ask: `Write this file to {path}? [y/n/a(all)/q(quit)]`
  - `y` — write this file, continue to next
  - `n` — skip this file, continue to next
  - `a` — write all remaining files without confirmation
  - `q` — quit without writing remaining files
- Show progress: `Processing contest {X} of {Y}: {contest_name}`

**Direct mode (--direct flag):**
- Write all files without confirmation
- Show progress: `Writing {path}...`
- After completion: `Done. Review changes with: git diff --stat data/elections/{date}/`

## 10. Error Handling

| Error | Action |
|-------|--------|
| Missing or renamed CSV columns | Immediate failure — print expected vs. found, exit |
| Unparseable contest name | Log warning, skip contest, continue; report skipped contests at end |
| Duplicate candidate name slug | Append sequence number: `jane-doe-00000000-2.md` |
| File write error | Print error, continue to next file, report failures at end |
| Interrupted processing | Checkpoint file preserves progress — re-invocation resumes automatically |
| Update mode: candidate field conflict | Prefer CSV value for status/party/date; preserve all other fields |

## 11. Quality Checks

After all files are generated, report:

```
Generation complete.
  Election date: {date}
  Contest files created: {N}
  County files created: {N}
  Candidate stubs created: {N}
  Contests skipped (unparseable): {N}

Quality check:
  Unique (CANDIDATE, PARTY) pairs in CSV: {N}
  Candidate stubs created: {N}
```

If stub count does not match unique candidate pairs: print warning about potential deduplication issues.

Remind the operator:
```
Next steps:
  1. Review output: git diff --stat data/elections/{date}/
  2. Run normalizer: /election:normalize elections data/elections/{date}/
  3. Commit reviewed files: git add data/elections/{date}/ data/candidates/ && git commit
```
