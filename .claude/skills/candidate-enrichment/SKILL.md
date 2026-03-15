---
name: candidate-enrichment
description: Enrich candidate markdown files with bios, photo URLs, and contact info from web research
argument-hint: <candidates-dir> [--depth full|basic|minimal] [--direct]
disable-model-invocation: true
allowed-tools: Read, Write, Grep, Glob, Bash, WebFetch
---

# Candidate Enrichment Skill

Enrich candidate markdown stub files with biographical information, photo URLs, and contact
details gathered from web research. Produces human-reviewable updates with source annotations
for every enriched field.

## 1. Input

Parse `$ARGUMENTS` to extract:
- `$0` — path to the candidates directory (required, typically `data/candidates/`)
- `--depth` flag — research depth: `full` (default), `basic`, or `minimal`
- `--direct` flag — if present, write updates without showing diff or asking for confirmation

**Validate inputs before processing:**
1. Verify the candidates directory exists and contains `.md` files
2. If directory is empty: print `No candidate files found in {dir}` and stop
3. Default depth is `full` if `--depth` is not specified

## 2. Format References

Before processing any candidates, read:

- @docs/formats/markdown/candidate-file.md
- @.claude/skills/includes/format-rules.md

These define the exact structure for candidate files, required fields, empty value conventions
(em-dash U+2014), and URL formatting rules.

## 3. Depth Levels

**`minimal` depth:**
- Name verification only: confirm the candidate's identity via a quick web search
- No bio, no photo, no contact info added
- Mark uncertain identities with `(unverified)` annotation on the Name field
- Use case: large elections where full enrichment would be too slow; confirm identities first

**`basic` depth (subset of full):**
- Bio: one paragraph covering professional background and current office if incumbent
- Party affiliation confirmed (already in file from CSV — verify it matches web sources)
- Current office title if the candidate is an incumbent (from government website)
- Skip: photo URL, social media, campaign website validation, education, full career history

**`full` depth (all fields):**
- Everything in `basic` plus:
- Photo URL (from Ballotpedia, campaign site, or government site)
- Campaign website (validate it's live — see Section 8)
- Social media: LinkedIn, Twitter/X, Facebook links
- Contact info beyond what's in the CSV (additional email, office phone if incumbent)
- Education background
- Full career history (major positions, not exhaustive)

## 4. Research Sources

Research each candidate using these sources in priority order:

**a. Ballotpedia (primary source)**
- Search: `ballotpedia.org {candidate full name} {state} {office}`
- Use WebFetch to retrieve the Ballotpedia profile page if a URL is found
- Extract: biography, photo URL, prior offices, party, education, Ballotpedia ID (page slug)
- Annotate with: `(source: ballotpedia)`

**b. Campaign websites**
- If a campaign website URL exists in the candidate file, validate it first (see Section 8)
- Use WebFetch to retrieve the About page or homepage
- Extract: bio paragraph, photo URL, platform/issues summary, contact info
- Annotate with: `(source: campaign-website)`

**c. Official government sites**
- For incumbents: check GA SOS official candidate page, state legislature site, county websites
- Extract: official portrait URL, committee assignments, official bio
- Annotate with: `(source: {site-name})` e.g., `(source: ga-sos)`, `(source: ga-legislature)`

**d. Social media profiles**
- LinkedIn: search `linkedin.com/in/{name}` or `site:linkedin.com {name} Georgia {office}`
- Twitter/X: search `twitter.com/{handle}` if handle is findable
- Facebook: search for official campaign page
- Extract: profile photo URL, headline/bio text, profile links
- Annotate with: `(source: linkedin)`, `(source: twitter)`, `(source: facebook)`

**Source priority for photo URLs:**
1. Ballotpedia official photo (best quality, stable URL)
2. Government official portrait (for incumbents)
3. Campaign website headshot
4. LinkedIn profile photo

## 5. Confidence Annotations

ALL enriched data must include a source annotation inline:

```
Photo URL: https://ballotpedia.org/images/thumb/example.jpg (source: ballotpedia)
```

**Annotation formats:**
- `(source: ballotpedia)` — from Ballotpedia profile
- `(source: campaign-website)` — from candidate's campaign site
- `(source: ga-sos)` — from Georgia Secretary of State official site
- `(source: ga-legislature)` — from Georgia General Assembly site
- `(source: linkedin)` — from LinkedIn profile
- `(source: twitter)` — from Twitter/X profile
- `(source: facebook)` — from Facebook page
- `(unverified)` — source is ambiguous OR candidate identity is uncertain

**Rules:**
- Never omit a source annotation on enriched data
- Use `(unverified)` when you cannot confirm the web source is the correct person
- The normalizer strips annotations before the converter runs — they are for human review only
- Example for bio: `{bio text here} (source: ballotpedia)`

## 6. Processing Steps

Process candidates sequentially. Report progress for each one.

**Step 1: Scan candidates directory**
- Glob all `.md` files in the candidates directory
- Count total: `Found {N} candidate files to process`
- Identify which files have empty/missing fields (Photo URL, Bio, External IDs, Links)

**Step 2: For each candidate file:**

Print: `Enriching candidate {X} of {Y}: {name}`

a. Read the existing candidate file content
b. Identify which fields are missing or empty (show `—` or blank):
   - Photo URL
   - Bio section (currently `—`)
   - External IDs (Ballotpedia, Open States, VPAP)
   - Links table (campaign website, social media)
c. Skip fields that already have non-empty values (do not overwrite existing enrichment)

**Step 3: Research based on depth**
- Apply sources from Section 4 in priority order
- Stop after finding sufficient data for the requested depth level
- If candidate has multiple elections in their file: research the most recent one for context

**Step 4: Build the update**
- Only update fields that are currently empty (do not overwrite existing data)
- Add source annotations to all new data
- For external IDs: add Ballotpedia slug if found, others if discovered

**Step 5: Confirm and write**
- Default (no `--direct`): show the diff for this candidate file and ask:
  `Apply enrichment to {filename}? [y/n/a(all)/q(quit)]`
  - `y` — apply and continue
  - `n` — skip this candidate, continue
  - `a` — apply all remaining without confirmation
  - `q` — stop (already-saved candidates remain saved)
- Direct mode: write without prompting

**Step 6: Checkpoint after each write**
- Each candidate file is saved independently after confirmation
- If the skill is interrupted, already-enriched candidates are preserved
- Re-running the skill will skip candidates whose fields are already populated

**Step 7: URL validation** (after writing, or before in `full` depth)
- See Section 8 for URL validation details
- Dead links get marked inline in the file

**Step 8: Continue to next candidate**

## 7. Deduplication Handling

When two candidate files appear to represent the same person (same name, possibly different
contests):
- Check whether they share any identifiers (email, website) that confirm they are the same person
- If likely the same person: flag to the user — `WARNING: {file-a} and {file-b} may be the same person. Verify before merging.`
- Never automatically merge candidate files without user confirmation
- If uncertain: mark the relevant candidate files with `(unverified)` on the Name field

## 8. URL Validation

For every URL added to a candidate file:

**Validation check:**
- Use WebFetch or Bash `curl -s -o /dev/null -w "%{http_code}" {url}` to check the URL responds
- A 200 or 301/302 response = live
- Follow redirects: use the final URL (after all redirects) in the candidate file

**Dead link handling:**
- If URL returns 4xx, 5xx, or connection error: mark as `(dead link as of {YYYY-MM-DD})`
- Example: `https://example.com/photo.jpg (dead link as of 2026-03-15)`
- Do not remove dead links — the annotation tells reviewers what was attempted

**Redirect handling:**
- If a URL redirects to a canonical URL: use the final canonical URL
- Example: `http://example.com` → `https://www.example.com/` → store as `https://www.example.com`

## 9. Batch Processing

**Default (sequential):**
- Process one candidate at a time to avoid API rate limits
- Show progress: `Enriching candidate {X} of {Y}: {name}`
- If a single candidate fails (WebFetch error, network issue): log warning, skip, continue
  - Print: `WARNING: Could not enrich {filename} — {reason}. Skipping.`
- After completing all candidates: report summary (see Section 10)

**Checkpoint behavior:**
- Each written candidate file is its own checkpoint
- Re-running the skill on the same directory skips candidates with no empty fields remaining
- Use case: resume after interruption without re-enriching already-processed candidates

## 10. Agent Team Coordination

When operating as part of a Claude Code cooperative agent team (when explicitly enabled):

**Coordinator responsibilities:**
- Pre-scan all candidate files, count fields to enrich per file
- Partition candidates into balanced batches (aim for 4 roughly equal batches by file count)
- Assign one batch to each worker agent with the `--depth` flag and target directory subset
- Collect results from workers when they report completion
- Resolve any deduplication conflicts identified by workers (see Section 7)
- Produce the final completion report after all workers finish

**Worker responsibilities:**
- Process the assigned batch of candidate files sequentially
- Apply the same confidence annotation and URL validation rules as single-agent mode
- Report back: files enriched, fields added, URLs validated, dead links found, warnings

**Coordination protocol:**
- Workers do not coordinate with each other directly — only through the coordinator
- Each worker writes to its own subset of files (no file is assigned to two workers)
- Coordinator handles dedup conflicts: if two workers flag the same pair, resolve once
- Default batch count: 4 workers (balanced for throughput vs. API rate limits)

## 11. Completion Report

After all candidates are processed:

```
Enrichment complete.
  Candidates processed: {N}
  Candidates enriched: {N}
  Candidates skipped (already enriched): {N}
  Candidates skipped (error): {N}
  Fields added: {N}
  URLs added: {N}
  URLs validated: {N} live, {N} dead links marked
  Deduplication warnings: {N}

Next steps:
  1. Review changes: git diff data/candidates/
  2. Run normalizer: /election:normalize candidates data/candidates/
  3. Commit reviewed files: git add data/candidates/ && git commit
```
