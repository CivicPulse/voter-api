# Format Rules Reference

Common formatting rules applied by all skills. This file documents conventions so they stay
consistent across skill output. Full format specifications live in `docs/formats/markdown/`.

**Full specifications:**
- `docs/formats/markdown/election-overview.md`
- `docs/formats/markdown/single-contest.md`
- `docs/formats/markdown/multi-contest.md`
- `docs/formats/markdown/candidate-file.md`

## Smart Title Case

**Do NOT use Python `str.title()` or naive title casing.** Use AI judgment for proper title case:

| Rule | Example Input | Correct Output |
|------|--------------|----------------|
| Capitalize first word always | `of education` (at start) | `Of Education` |
| Lowercase articles/prepositions mid-phrase | `BOARD OF EDUCATION` | `Board of Education` |
| Lowercase: of, at, for, in, to, the, and, or, a, an | `JUDGE OF SUPERIOR COURT` | `Judge of Superior Court` |
| Capitalize after hyphen | `AT LARGE-POST 7` | `At Large-Post 7` |
| Suffixes: III, II, IV, Jr, Sr — capitalize as-is | `DAVID MINCEY III` | `David Mincey III` |
| Scottish prefixes: Mc, Mac | `MCDONALD` → `McDonald`, `MACINTYRE` → `MacIntyre` | Be careful: `MACHINIST` stays `Machinist` (Mac only if > 4 chars and followed by capital-candidate name) |
| Compound names: De, La, Van, Von, Di | `DE LA CRUZ` | `De La Cruz` |
| O' prefix | `O'BRIEN` | `O'Brien` |
| Hyphenated names | `SMITH-JONES` | `Smith-Jones` |
| Single-letter middle initial stays capitalized | `JOHN A SMITH` | `John A Smith` |
| Uppercase acronyms: CEO, CFO, CPA, LLC, LLP, BOE, BOC, PSC | preserve | preserve |
| Occupation expansions | `Ret Educator` | `Retired Educator`; `Mgr` → `Manager`; `Atty` → `Attorney` |

## Date Formats

| Context | Format | Example |
|---------|--------|---------|
| Contest candidate tables | MM/DD/YYYY | `03/02/2026` |
| Election overview Calendar section | YYYY-MM-DD (ISO 8601) | `2026-03-02` |
| Candidate file Elections section (Qualified Date) | MM/DD/YYYY | `03/02/2026` |
| File naming | YYYY-MM-DD | `2026-05-19-governor.md` |

## URL Normalization

- Always use `https://` — add if missing, upgrade `http://` to `https://`
- Always lowercase the full URL
- Remove trailing slashes for consistency
- Validate URL is live (mark as `(dead link)` if not responding)

## Empty Values

- Use em-dash `—` (U+2014) for all missing or unavailable field values
- Never use: `(none)`, `N/A`, `-` (hyphen), `--` (double hyphen), or blank cells in metadata tables

## Metadata Table Format

```markdown
| Field | Value |
|-------|-------|
| ID | {uuid or empty for new records} |
| Format Version | 1 |
```

- Two-column table: `Field` and `Value`
- Left-aligned pipes: `|-------|-------|`
- Required fields vary by file type — see full spec for each file type

## Candidate Table Format (5 columns)

```markdown
| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
```

- Exactly 5 columns — no more, no less
- Email and Website do NOT appear in contest tables (they go in the candidate file)
- Candidate name must link to global candidate file: `[Name](../../candidates/{slug}-{hash}.md)`
- For stub phase: use unlinked name if candidate file does not yet exist

## File Naming Conventions

| File Type | Pattern | Example |
|-----------|---------|---------|
| Election overview | `{date}-{type-slug}.md` | `2026-05-19-general-primary.md` |
| Statewide/federal contest | `{date}-{contest-slug}.md` | `2026-05-19-governor.md` |
| County multi-contest | `{date}-{county}.md` | `2026-05-19-bibb.md` |
| Candidate stub | `{name-slug}-00000000.md` | `jane-doe-00000000.md` |
| Candidate final | `{name-slug}-{8-char-hash}.md` | `jane-doe-a3f2e1b4.md` |

**Slug rules:**
- All lowercase
- Hyphens as word separators (no underscores, no spaces)
- Numbers unpadded in body/seat IDs (`district-1`, `post-7`)
- Numbers zero-padded only in filenames for federal districts (`us-house-district-01`)
- Strip punctuation (apostrophes, periods, commas)

## H1 Heading Format

| File Type | H1 Format |
|-----------|-----------|
| Election overview | `{Month D, YYYY} — {Election Display Name}` |
| Single-contest (statewide/federal) | `{Contest Display Name}` |
| Single-contest (special election) | `{Locality} — {Office Title}` |
| County multi-contest | `{County Name} County — Local Elections` |
| Candidate file | `{Full Name}` |

- Em-dash (U+2014) separator, not hyphen or double-hyphen
- Month spelled out in full: `May 19, 2026` (not `05/19/2026`)

## Partisan Primary Sections

For partisan primary contests, group candidates by party into named H2 sections:

```markdown
## Republican Primary

**Contest Name (SOS):** {SOS Contest Name} (R)

| Candidate | Status | Incumbent | Occupation | Qualified Date |
...

## Democrat Primary

**Contest Name (SOS):** {SOS Contest Name} (D)

| Candidate | Status | Incumbent | Occupation | Qualified Date |
...
```

- Non-partisan and special elections use a single `## Candidates` section
- Each party section includes the `**Contest Name (SOS):**` line before the table
