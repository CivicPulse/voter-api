# SOS CSV Column Reference

This file documents the 11 columns in the Georgia Secretary of State qualified candidates CSV and
how each column maps to the enhanced markdown format.

**Full specification:** `docs/formats/markdown/single-contest.md`, `docs/formats/markdown/multi-contest.md`, `docs/formats/markdown/candidate-file.md`

## Column Mapping Table

| CSV Column | Markdown Target | Transformation Notes |
|-----------|-----------------|----------------------|
| CONTEST NAME | Body, Seat, Type, election display name | **AI-parsed** — not a direct mapping. Parse to infer body_id, seat_id, and election_type. See `contest-patterns.md` for examples. Strip party suffix `(R)`, `(D)`, `(L)`, `(I)` before parsing. |
| COUNTY | County file routing | Empty = statewide or federal (goes in election root). Non-empty = county contest (goes in `counties/` subdirectory). Multi-county contests span multiple rows — use COUNTY column to determine which county files reference this contest. |
| MUNICIPALITY | Body ID scoping | Non-empty = municipal contest. Municipality name prefixes the Body ID (e.g., `macon-` for Macon). Empty = county-level or statewide contest. |
| CANDIDATE NAME | Candidate column in contest tables | Apply smart title case — SOS data is ALL CAPS. See `format-rules.md` for title case rules. Link to candidate file in table. |
| CANDIDATE STATUS | Status column | Map values: `QUALIFIED` → `Qualified`, `WITHDRAWN` → `Withdrawn`, `DISQUALIFIED` → `Disqualified`, `WRITE-IN` → `Write-In`. |
| POLITICAL PARTY | Party column / party section grouping | Used to determine party sections in partisan primaries. Full values: `REPUBLICAN` → `Republican`, `DEMOCRAT` → `Democrat`, `LIBERTARIAN` → `Libertarian`, `INDEPENDENT` → `Independent`, `NON-PARTISAN` → `Non-Partisan`. Abbreviation for display: `(R)`, `(D)`, `(L)`, `(I)`, `(NP)`. |
| QUALIFIED DATE | Qualified Date column | Format: `MM/DD/YYYY` in contest tables. Already in date format — confirm and reformat if needed. |
| INCUMBENT | Incumbent column | `Y` or `YES` → `Yes`. Empty or any other value → `No`. |
| OCCUPATION | Occupation column in contest tables AND candidate file | Apply smart title case. Expand common abbreviations: `Ret` → `Retired`, `Mgr` → `Manager`, `Atty` → `Attorney`. Preserve uppercase acronyms: CEO, CFO, CPA, LLC, LLP. |
| EMAIL ADDRESS | Candidate file Links table | Do NOT include in contest tables. Goes in global candidate file under Links with type `email`. |
| WEBSITE | Candidate file Links table | Do NOT include in contest tables. Goes in global candidate file under Links with type `website`. Normalize: add `https://` prefix if no protocol is present; preserve original URL casing. |

## Multi-County Deduplication

The same candidate appears in **multiple rows** when they are running in a multi-county contest
(e.g., US House, State Senate, State House that spans multiple counties, or judicial circuits).

**Rule:** Two rows represent the same candidate if they share the same `CONTEST NAME` (after
stripping party suffix) and `CANDIDATE NAME`. Deduplicate before creating candidate stub files.

**County routing for multi-county contests:**
- The contest itself goes in the election root (as a single-contest file), not in county files
- Each county file that contains voters for the district gets a row in its Statewide & District Races section linking to the single-contest file
- Do NOT create duplicate contest tables per county for multi-county contests

## Data Quality Notes

- CANDIDATE NAME is always ALL CAPS in SOS data
- OCCUPATION is often ALL CAPS, abbreviated, or blank
- WEBSITE URLs may lack `https://` prefix or use HTTP
- EMAIL ADDRESS may be blank for many candidates
- CONTEST NAME formatting is wildly inconsistent across contests (see `contest-patterns.md`)
- INCUMBENT field is often blank even for actual incumbents (verify via research if enriching)
