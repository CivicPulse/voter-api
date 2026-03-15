---
name: process-election
description: Full election data pipeline - process SOS CSV through skills, normalize, and prepare for review
argument-hint: <csv-file-path> [--direct] [--skip-enrich]
disable-model-invocation: true
---

# Process Election Skill

Orchestrate the full election data processing pipeline from a raw SOS qualified candidates
CSV file to normalized, enriched, human-reviewable markdown. This skill coordinates the
other election skills in the correct order.

## 1. Pipeline Overview

This skill runs these steps in sequence:

```
SOS CSV
  -> Step 1: Validate input
  -> Step 2: qualified-candidates skill (CSV -> election dir + candidate stubs)
  -> Step 3: normalize elections (enforce formatting, generate UUIDs for election files)
  -> Step 4: normalize candidates (generate UUIDs, rename stubs to final filenames)
  -> Step 5: candidate-enrichment skill (fill bios, photos, contact info) [optional]
  -> Step 6: Review via git diff
```

## 2. Input

Parse `$ARGUMENTS` to extract:
- `$0` — path to the SOS qualified candidates CSV file (required)
- `--direct` flag — pass through to sub-skills; skip interactive confirmation at each step
- `--skip-enrich` flag — skip Step 5 (candidate enrichment); useful for large elections or when enrichment is deferred

Print the effective configuration at start:
```
Election pipeline starting.
  CSV: {csv-path}
  Direct mode: {yes/no}
  Enrichment: {enabled/skipped}
```

## 3. Pipeline Steps

### Step 1: Validate Input

1. Verify the CSV file exists and is readable
2. Determine the election date from the CSV filename:
   - Pattern: `{date}-qualified-candidates.csv` (e.g., `2026-05-19-qualified-candidates.csv`)
   - If date cannot be parsed from filename: read the first data row and derive from QUALIFIED DATE column
   - Print: `Election date: {date}`
3. Confirm the expected output directory: `data/elections/{date}/`
4. If the CSV does not exist: print error and stop immediately

### Step 2: Process Qualified Candidates

Run the qualified-candidates skill on the CSV:

```
Read and execute .claude/skills/qualified-candidates/SKILL.md with arguments: {csv-path} [--direct]
```

- Pass `--direct` flag if it was provided
- Wait for the skill to complete
- Verify the output directory was created: `data/elections/{date}/`
- Verify candidate stub files were created: `data/candidates/*.md`
- If output directory was not created: print error, stop pipeline

Print progress: `Step 2 complete: {N} contest files, {N} county files, {N} candidate stubs created.`

### Step 3: Normalize Election Files

Run the normalizer CLI on the election directory:

```bash
uv run voter-api normalize elections data/elections/{date}/
```

- Display the full normalizer output
- Check the report for errors (not just warnings):
  - Errors (missing required fields, invalid structure) = stop the pipeline, report the issue
  - Warnings (ALL CAPS remnants, empty optional fields) = log, continue
- If errors are found: print `Pipeline stopped at Step 3 — normalize errors must be resolved before continuing.` and stop

Print progress: `Step 3 complete: {N} election files normalized, {N} UUIDs generated.`

### Step 4: Normalize Candidate Files

Run the normalizer CLI on the candidates directory:

```bash
uv run voter-api normalize candidates data/candidates/
```

- This generates UUIDs for each candidate record
- This renames placeholder stub files from `{name}-00000000.md` to `{name}-{uuid-hash}.md`
- Display the full normalizer output
- Check for errors; stop on errors (same policy as Step 3)

Print progress: `Step 4 complete: {N} candidate files normalized, {N} files renamed with UUID hash.`

### Step 5: Enrich Candidates (unless --skip-enrich)

If `--skip-enrich` was provided, skip this step and print:
```
Step 5 skipped: candidate enrichment disabled (--skip-enrich flag).
Run manually: /election:enrich data/candidates/ --depth basic
```

Otherwise, run the candidate-enrichment skill:

```
Read and execute .claude/skills/candidate-enrichment/SKILL.md with arguments: data/candidates/ --depth basic [--direct]
```

- Use `--depth basic` for pipeline runs (bio + party + office; skip social media and education)
- Pass `--direct` flag if it was provided
- This is the longest step for large elections — provide progress updates as the skill runs
- If enrichment is interrupted, already-enriched candidates are preserved (checkpoint behavior)

Print progress: `Step 5 complete: {N} candidates enriched.`

### Step 6: Review

Show a summary of all changes made during the pipeline:

```bash
git diff --stat
```

Display the diff stat output. Then print:

```
Pipeline complete.
  Election date: {date}
  Election files: data/elections/{date}/ ({N} files)
  Candidate files: data/candidates/ ({N} files)
  Enriched candidates: {N}

Review all changes with: git diff
Commit when satisfied:
  git add data/elections/{date}/ data/candidates/
  git commit -m "data: process {date} election from SOS CSV"
```

## 4. Error Recovery

Each pipeline step is independent. If a step fails, all output from preceding steps is
preserved on disk. The user can correct the issue and re-run a specific step manually:

| Step Failed | How to Resume |
|-------------|---------------|
| Step 2 (qualified-candidates) | Fix CSV or skill issue, then re-run `/election:pipeline {csv}` |
| Step 3 (normalize elections) | Fix election file issues, then run `/election:normalize elections data/elections/{date}/` |
| Step 4 (normalize candidates) | Fix candidate file issues, then run `/election:normalize candidates data/candidates/` |
| Step 5 (enrichment) | Re-run `/election:enrich data/candidates/ --depth basic`; already-enriched files are skipped |

When a step fails, print which step failed and the exact commands for manual recovery.

## 5. Election Calendar Integration

The pipeline does NOT process election calendar PDFs (that is a separate manual step). After
the pipeline completes, if SOS calendar PDFs are available in `data/import/`, suggest:

```
Optional: Update election calendar dates
  If you have SOS calendar PDFs in data/import/, run:
  /election:calendar data/import/ {date}

  This extracts Registration Deadline, Early Voting dates, and other deadlines
  into the election overview file.
```

Only show this suggestion if `data/import/` exists and contains `.pdf` files.
