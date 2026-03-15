# Contest Name Parsing Examples

This file provides real-world SOS contest name examples and their parsed outputs.
Use these patterns when parsing CONTEST NAME values from SOS qualified candidates CSVs.

**Core task:** Parse wildly inconsistent SOS contest names into structured `body_id`, `seat_id`,
and `election_type` values. This is AI pattern matching — not deterministic rules.

**Input columns used:**
- `CONTEST NAME` — primary parsing target
- `COUNTY` — empty = statewide/federal; non-empty = county-level
- `MUNICIPALITY` — non-empty = municipal contest

**Party suffix stripping:** Always strip `(R)`, `(D)`, `(L)`, `(I)`, `(NP)` (with or without space)
before parsing. Record the party separately.

---

## Statewide Offices

These exact (or near-exact) contest name strings map to known statewide bodies.

| Raw Contest Name | body_id | seat_id | election_type | Notes |
|-----------------|---------|---------|---------------|-------|
| `Governor` | `ga-governor` | `sole` | `general_primary` | |
| `GOVERNOR` | `ga-governor` | `sole` | `general_primary` | All-caps variant |
| `Lieutenant Governor` | `ga-lt-governor` | `sole` | `general_primary` | |
| `Secretary of State` | `ga-sos` | `sole` | `general_primary` | |
| `Attorney General` | `ga-ag` | `sole` | `general_primary` | |
| `State School Superintendent` | `ga-school-superintendent` | `sole` | `general_primary` | |
| `Commissioner of Agriculture` | `ga-agriculture` | `sole` | `general_primary` | |
| `Commissioner of Labor` | `ga-labor` | `sole` | `general_primary` | |
| `Insurance Commissioner` | `ga-insurance` | `sole` | `general_primary` | |
| `Public Service Commissioner District 1` | `ga-psc` | `district-1` | `general_primary` | PSC uses district seats |
| `Public Service Commissioner District 3` | `ga-psc` | `district-3` | `general_primary` | |

---

## Federal Offices — US House

The US House contest name has many formatting variants. All map to `ga-us-house` with a district seat.

| Raw Contest Name | body_id | seat_id | election_type | Notes |
|-----------------|---------|---------|---------------|-------|
| `US House of Representatives - District 11` | `ga-us-house` | `district-11` | `general_primary` | Dash separator |
| `US House Of Representatives - District 1` | `ga-us-house` | `district-1` | `general_primary` | Mixed case "Of" |
| `US House of Representatives District 5` | `ga-us-house` | `district-5` | `general_primary` | No separator |
| `U.S. House of Representatives - District 3` | `ga-us-house` | `district-3` | `general_primary` | With periods |
| `United States House of Representatives - District 7` | `ga-us-house` | `district-7` | `general_primary` | Spelled out |
| `Congressional District 4` | `ga-us-house` | `district-4` | `general_primary` | Abbreviated form |

---

## State Legislative — State Senate

| Raw Contest Name | body_id | seat_id | election_type | Notes |
|-----------------|---------|---------|---------------|-------|
| `State Senate District 14 (D)` | `ga-state-senate` | `district-14` | `general_primary` | Party suffix present |
| `State Senate - District 3` | `ga-state-senate` | `district-3` | `general_primary` | Dash separator |
| `Senate District 9` | `ga-state-senate` | `district-9` | `general_primary` | Abbreviated |
| `SENATE DISTRICT 22` | `ga-state-senate` | `district-22` | `general_primary` | All-caps |
| `Georgia State Senate District 45` | `ga-state-senate` | `district-45` | `general_primary` | Full name prefix |

---

## State Legislative — State House

| Raw Contest Name | body_id | seat_id | election_type | Notes |
|-----------------|---------|---------|---------------|-------|
| `State House Of Representatives - District 149` | `ga-state-house` | `district-149` | `general_primary` | Mixed case "Of" |
| `State House of Representatives District 100` | `ga-state-house` | `district-100` | `general_primary` | No separator |
| `House District 12` | `ga-state-house` | `district-12` | `general_primary` | Abbreviated |
| `HOUSE OF REPRESENTATIVES - DISTRICT 78` | `ga-state-house` | `district-78` | `general_primary` | All-caps |
| `State Representative District 55` | `ga-state-house` | `district-55` | `general_primary` | "Representative" variant |

---

## County Level — Board of Education

COUNTY column is non-empty. Use `{county}-boe` as body_id (county name in lowercase).

| Raw Contest Name | body_id | seat_id | election_type | Notes |
|-----------------|---------|---------|---------------|-------|
| `Board of Education At Large-Post 7` | `{county}-boe` | `post-7` | `general_primary` | Hyphen before number |
| `Board of Education At Large - Post 8` | `{county}-boe` | `post-8` | `general_primary` | Dash with spaces |
| `BOARD OF EDUCATION AT LARGE-POST 7` | `{county}-boe` | `post-7` | `general_primary` | All-caps variant |
| `Board of Education D3` | `{county}-boe` | `district-3` | `general_primary` | Abbreviated "D" = district |
| `Board of Education, District 1` | `{county}-boe` | `district-1` | `general_primary` | Comma separator |
| `Board of Education District 2` | `{county}-boe` | `district-2` | `general_primary` | No separator |
| `Board of Education - District 4` | `{county}-boe` | `district-4` | `general_primary` | Dash separator |
| `BOE District 5` | `{county}-boe` | `district-5` | `general_primary` | Acronym form |

---

## County Level — Board of Commissioners / County Commission

| Raw Contest Name | body_id | seat_id | election_type | Notes |
|-----------------|---------|---------|---------------|-------|
| `Board of Commissioner District 2(R)` | `{county}-commission` | `district-2` | `general_primary` | No space before party |
| `Board of Commissioners - District 2 (R)` | `{county}-commission` | `district-2` | `general_primary` | Plural + dash |
| `Board of Commissioners District 3` | `{county}-commission` | `district-3` | `general_primary` | Plural, no sep |
| `County Commissioner District 1` | `{county}-commission` | `district-1` | `general_primary` | "County Commissioner" |
| `Commissioner District 4` | `{county}-commission` | `district-4` | `general_primary` | Abbreviated |
| `BOC District 2` | `{county}-commission` | `district-2` | `general_primary` | Acronym form |

---

## County Level — Courts

Judicial seat_id uses lowercase incumbent surname: `judge-{surname}`.

| Raw Contest Name | body_id | seat_id | election_type | Notes |
|-----------------|---------|---------|---------------|-------|
| `Judge of Superior Court - Stone Mountain Judicial Circuit - Bagley` | `{county}-superior-court` | `judge-bagley` | `general_primary` | Surname at end after dash |
| `Judge of Superior Court, Macon Judicial Circuit - Mincey` | `bibb-superior-court` | `judge-mincey` | `general_primary` | Comma + dash |
| `State Court Judge (Smith)` | `{county}-state-court` | `judge-smith` | `general_primary` | Parenthetical surname |
| `State Court Judge (Hanson)` | `{county}-state-court` | `judge-hanson` | `general_primary` | |
| `Civil/Magistrate Court Judge` | `{county}-magistrate-court` | `sole` | `general_primary` | Single-judge court |
| `Civil Court of Magistrate Court` | `{county}-magistrate-court` | `sole` | `general_primary` | Alternate wording |
| `Magistrate Court Judge` | `{county}-magistrate-court` | `sole` | `general_primary` | Short form |
| `Probate Court Judge` | `{county}-probate-court` | `sole` | `general_primary` | Probate is sole-seat |

---

## County Level — Other County Offices

| Raw Contest Name | body_id | seat_id | election_type | Notes |
|-----------------|---------|---------|---------------|-------|
| `Sheriff` | `{county}-sheriff` | `sole` | `general_primary` | |
| `Tax Commissioner` | `{county}-tax-commissioner` | `sole` | `general_primary` | |
| `Clerk of Superior Court` | `{county}-clerk-superior-court` | `sole` | `general_primary` | |
| `Coroner` | `{county}-coroner` | `sole` | `general_primary` | |
| `Surveyor` | `{county}-surveyor` | `sole` | `general_primary` | |

---

## Municipal Contests

MUNICIPALITY column is non-empty. Use `{municipality}-{body}` as body_id with municipality name
in lowercase slug form. The COUNTY column may also be present.

| Raw Contest Name | MUNICIPALITY | body_id | seat_id | election_type | Notes |
|-----------------|-------------|---------|---------|---------------|-------|
| `City Council District 2` | `MACON` | `macon-city-council` | `district-2` | `general_primary` | |
| `Mayor` | `ATLANTA` | `atlanta-mayor` | `sole` | `municipal` | |
| `City School Board District 1` | `SAVANNAH` | `savannah-city-school-board` | `district-1` | `general_primary` | |
| `Macon Water Authority-At Large` | `MACON` | `macon-water-authority` | `at-large` | `general_primary` | |
| `City Commissioner Post 2` | `VALDOSTA` | `valdosta-city-commission` | `post-2` | `general_primary` | |

---

## Special Election Contests

CONTEST NAME typically identifies the specific office and location. election_type = `special`.

| Raw Contest Name | body_id | seat_id | election_type | Notes |
|-----------------|---------|---------|---------------|-------|
| `Bibb County Commission District 5` | `bibb-commission` | `district-5` | `special` | Special election |
| `US House of Representatives - District 6` | `ga-us-house` | `district-6` | `special` | Federal special election |
| `State Senate District 3` | `ga-state-senate` | `district-3` | `special` | State legislative special |

---

## Parsing Tips

1. **Check COUNTY and MUNICIPALITY columns first** — they determine the scope (statewide, county, municipal)
2. **Strip party suffix before all parsing** — `(R)`, `(D)`, `(L)`, `(I)`, `(NP)` with or without leading space
3. **Normalize case for pattern matching** — compare lowercase versions to known patterns
4. **Look for district number last** — appears after "District", "D", "-", or "," with a number
5. **"At Large" + "Post N"** = `post-N` seat (numbered at-large post)
6. **"At Large"** without a post number = `at-large` seat
7. **Judicial circuits** — extract surname from end of string (after last `-` or inside parentheses)
8. **Single-judge courts** (Magistrate, Probate) = `sole` seat
9. **When unsure**: log a warning and skip the contest rather than guessing wrong
