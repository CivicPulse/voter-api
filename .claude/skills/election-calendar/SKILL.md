---
name: election-calendar
description: Extract election dates and deadlines from GA SOS calendar PDF files into election overview metadata
argument-hint: <pdf-file-or-directory> <election-date>
disable-model-invocation: true
---

# Election Calendar Skill

Read Georgia Secretary of State election calendar PDF files and extract structured date metadata
into the Calendar section of an existing election overview file. Claude reads PDFs natively --
no PDF parsing library is needed.

## 1. Input

Parse `$ARGUMENTS` to extract:
- `$0` — path to a PDF file or a directory containing PDF files (required)
- `$1` — election date in YYYY-MM-DD format (required — identifies which overview file to update)
- `--direct` flag — if present, write without showing a diff or asking for confirmation

**Validate inputs before processing:**
1. Verify the PDF path or directory exists
2. Verify the election date is in YYYY-MM-DD format
3. Verify the target overview file exists: `data/elections/{date}/{date}-*.md`
   - The glob must resolve to exactly one file. If multiple files match, print: `ERROR: Multiple overview files found at data/elections/{date}/ — expected exactly one` and stop.
   - If not found, print: `ERROR: No election overview file found at data/elections/{date}/`
   - Stop — do not continue

## 2. Format Reference

Before extracting any dates, read the format specification for the Calendar section:

- @docs/formats/markdown/election-overview.md

Focus on the **Calendar Table** format: three columns (Field, Date, Source), all dates in
YYYY-MM-DD format, Source column attributes each date to its origin PDF or statute.

## 3. PDF Types

The GA SOS publishes two PDF types with complementary data:

**Master calendar PDF** (filename contains "Short Calendar" or "Master"):
- Contains the full election cycle view across all elections in the year
- Extract from it: Qualifying Period Start, Qualifying Period End
- These dates apply to the specific election identified by `$1` (match by election date)

**Per-election PDF** (filename contains the election date, e.g., "MAY_19_2026"):
- Contains specific deadlines for one election
- Extract from it: all core dates and absentee dates listed below

**If directory provided as `$0`:** Process all PDFs found in the directory. Identify each PDF's
type by filename. Correlate extracted dates to the target election (identified by `$1`).

## 4. Extraction Fields

Extract these fields from the PDF(s). Leave a field blank in the output if not found; do not
invent dates.

**Core dates** (from per-election PDF):
- Election Day — the election date itself (should match `$1`; warn if different)
- Registration Deadline — last day to register to vote
- Early Voting Start — first day of early/advance in-person voting
- Early Voting End — last day of early/advance in-person voting
- Absentee Request Deadline — last day to request an absentee ballot

**Absentee dates** (from per-election PDF):
- Earliest Day to Mail Absentee Ballot — first day SOS may mail ballots
- Earliest Day Voter Can Request Mail Ballot — first eligible day for absentee request

**Qualifying period** (from master calendar PDF):
- Qualifying Period Start — first day candidates may qualify
- Qualifying Period End — last day candidates may qualify

**Participating counties list** (from either PDF):
- List of counties participating in this election — used for cross-validation against the
  `data/states/GA/counties/` directory; report any counties in the PDF not present on disk

## 5. PDF Reading

Claude reads PDF files natively — use the Read tool with the PDF path. No PDF parsing
library is needed.

When a PDF contains multiple elections:
- Identify the section corresponding to `$1` (match by election date column or section heading)
- If multiple elections share the same date: print which elections were found and ask the user
  which one to extract dates for before proceeding

## 6. Output

Update the existing election overview file at `data/elections/{date}/{date}-{type}.md`.

**Add or update the Calendar section** with extracted dates:

```markdown
## Calendar

| Field | Date | Source |
|-------|------|--------|
| Registration Deadline | {YYYY-MM-DD} | {source} |
| Early Voting Start | {YYYY-MM-DD} | {source} |
| Early Voting End | {YYYY-MM-DD} | {source} |
| Absentee Request Deadline | {YYYY-MM-DD} | {source} |
| Qualifying Period Start | {YYYY-MM-DD} | {source} |
| Qualifying Period End | {YYYY-MM-DD} | {source} |
| Election Day | {YYYY-MM-DD} | {source} |
```

Source values:
- For dates from a per-election PDF: `SOS Election Calendar PDF ({filename})`
- For dates from the master calendar: `SOS Master Calendar PDF ({filename})`
- For Election Day (known from `$1`): `$1 argument`

**If the Calendar section already exists in the file:**
- Update existing rows with newly extracted dates
- Preserve any rows with dates already filled in (do not blank out previously set values)
- Add new rows for any fields not yet present

**Confirmation flow (unless `--direct`):**
1. Show a diff of the Calendar section changes
2. Ask: `Write these changes to {path}? [y/n]`
3. Only write if user confirms

**Direct mode (`--direct`):**
- Write the updated file without confirmation
- Print: `Updated Calendar section in {path}`

## 7. Error Handling

| Error | Action |
|-------|--------|
| PDF not readable / corrupted | Print: `ERROR: Cannot read {filename}` — skip that PDF, continue with others |
| Date not found in PDF | Leave the field blank in the output, print: `WARNING: {field} not found in {filename}` |
| Election date mismatch | If Election Day in PDF differs from `$1`: print `WARNING: PDF election date is {pdf-date}, argument is $1` — use `$1` for file path, note discrepancy in Source column |
| Multiple elections in PDF | Prompt user to select which election to extract before proceeding |
| Target overview file missing | Print error, stop — user must run qualified-candidates skill first |
| County not found in counties/ | Report counties in PDF not present at `data/states/GA/counties/` |

## 8. Completion Report

After writing the updated file:

```
Election calendar extraction complete.
  Target file: data/elections/{date}/{date}-{type}.md
  PDFs processed: {N}
  Dates extracted: {N}
  Dates missing (left blank): {N}
  County validation: {N} counties matched, {N} warnings

Next steps:
  1. Review: git diff data/elections/{date}/{date}-{type}.md
  2. Run normalizer if UUIDs or other fields need fixing: /election:normalize elections data/elections/{date}/
  3. Commit when satisfied: git add data/elections/{date}/ && git commit
```
