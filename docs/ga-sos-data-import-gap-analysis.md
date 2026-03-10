# GA SoS Data Import: Gap Analysis & Field Mapping Report

**Date:** 2026-03-10
**Data Directory:** `data/new/`
**Files Analyzed:** 5 data sources (2026.csv, A-12599.zip, Qualified Candidates.csv, election_info.html, 2026 Short Calendar.pdf)

---

## Gap Analysis Summary

### Data Source 1: `2026.csv` — Voter Participation History

**Status: FULLY SUPPORTED — No changes needed**

The existing voter history import pipeline handles this exact 9-column GA SoS format end-to-end:
- **Parser**: `lib/voter_history/parser.py` — `GA_SOS_VOTER_HISTORY_COLUMN_MAP` matches all 9 columns
- **Service**: `services/voter_history_service.py` — bulk UPSERT with 2000-row sub-batches, index drop/rebuild optimization
- **CLI**: `voter-api import voter-history <file>`
- **API**: `POST /imports/voter-history` (100MB limit)
- **Model**: `VoterHistory` with unique constraint on `(voter_registration_number, election_date, election_type)`

**To import**: `uv run voter-api import voter-history data/new/extracted/2026/2026.csv`

---

### Data Source 2: `A-12599.zip` — Absentee Ballot Applications

**Status: NOT SUPPORTED — Entirely new domain**

Nothing exists in the codebase for absentee ballot application data. This requires:

| Layer | What's Needed | Exists? |
|-------|--------------|---------|
| Model | `AbsenteeBallotApplication` table (38 columns) | No |
| Migration | New Alembic migration (041) | No |
| Parser | `lib/absentee/parser.py` — CSV column mapping, date/boolean parsing | No |
| Service | `services/absentee_service.py` — bulk UPSERT, query, stats | No |
| Schema | Pydantic request/response models | No |
| CLI | `voter-api import absentee <file>` | No |
| API | CRUD + query + stats endpoints under `/api/v1/absentee` | No |
| Tests | Unit (parser), integration (service), E2E (endpoints) | No |

**Effort**: Largest gap. ~15 new files across all layers. The voter history pipeline (`parser.py` → `service.py` → `cli/cmd.py`) is the closest existing pattern to follow.

---

### Data Source 3: `Qualified Candidates.csv` — Candidate Qualifications

**Status: PARTIALLY SUPPORTED — Model exists but missing fields + no CSV import**

**What exists:**
- `Candidate` model with `full_name`, `party`, `filing_status`, `is_incumbent`, `election_id`
- `CandidateLink` model for website URLs
- CRUD API endpoints under `/api/v1/elections/{id}/candidates`
- Pydantic schemas for create/update/response

**What's missing:**

| Layer | What's Needed | Exists? |
|-------|--------------|---------|
| Model fields | `contest_name`, `qualified_date`, `occupation`, `email`, `home_county`, `municipality` | No (6 missing columns) |
| Migration | Add 6 nullable columns to `candidates` table (042) | No |
| Parser | `lib/candidate_importer/parser.py` — CSV parsing + contest name resolution | No |
| Contest resolver | Parse "U.S House of Representatives, District 11 (R)" → election lookup | Partial — `lib/district_parser/parser.py` handles some patterns but not the SoS qualifying list format |
| Service | `services/candidate_import_service.py` — CSV import with election resolution | No |
| CLI | `voter-api import candidates <file>` | No |
| Schema updates | Add new fields to create/update/response schemas | No |

**Contest name parsing gap**: The existing `district_parser.py` handles SoS election feed formats like `"State Senate - District 18"` but the qualifying list uses different formats like `"U.S House of Representatives, District 11 (R)"` and highly variable local race names like `"BERRIEN COUNTY COMMISSIONER DISTRICT 2"`. The parser needs extension for these patterns.

**Effort**: Moderate. ~8 new/modified files. The contest-to-election resolution is the trickiest part.

---

### Data Source 4: `election_info.html` — Election Detail Page

**Status: SCHEMA READY — No parser exists**

**What exists:**
- `Election` model already has all relevant fields: `registration_deadline`, `early_voting_start`, `early_voting_end`, `absentee_request_deadline`, `qualifying_start`, `qualifying_end` (added in migration 038)
- `ElectionUpdateRequest` schema accepts all these fields
- `PATCH /api/v1/elections/{id}` can set them manually

**What's missing:**

| Layer | What's Needed | Exists? |
|-------|--------------|---------|
| HTML parser | `lib/election_calendar/html_parser.py` — extract dates from Salesforce SLDS markup | No |
| CLI | `voter-api election import-calendar <file>` | No |

**Effort**: Small. ~2 new files. The HTML is structured with predictable label/value div pairs.

---

### Data Source 5: `2026 Short Calendar.pdf` — Full Election Calendar

**Status: SCHEMA READY — No parser exists**

Same model fields as Data Source 4. Covers 4 elections with advance voting date ranges.

| Layer | What's Needed | Exists? |
|-------|--------------|---------|
| PDF parser | Would need a PDF text extraction library (e.g., `pdfplumber`) | No |
| CLI | Could share the same CLI as Data Source 4 | No |

**Effort**: Small but lower priority — the HTML source (Data Source 4) contains the same data in a more parseable format. The PDF is useful as a cross-reference but not the primary import source.

---

## Detailed Field Mappings

### Mapping 1: `2026.csv` → `VoterHistory` Model

All 9 columns map 1:1 via `GA_SOS_VOTER_HISTORY_COLUMN_MAP` in `lib/voter_history/parser.py`:

| CSV Column | Model Field | Type Conversion | Notes |
|---|---|---|---|
| `County Name` | `county` | String, as-is | e.g., "CHEROKEE" |
| `Voter Registration Number` | `voter_registration_number` | `lstrip('0') or '0'` | "03223241" → "3223241" |
| `Election Date` | `election_date` | `pd.to_datetime(format="%m/%d/%Y").date` | "01/06/2026" → `date(2026,1,6)` |
| `Election Type` | `election_type` | String, as-is (raw) | "SPECIAL ELECTION RUNOFF" |
| *(derived)* | `normalized_election_type` | `ELECTION_TYPE_MAP` lookup | "SPECIAL ELECTION RUNOFF" → "runoff" |
| `Party` | `party` | String or None if empty | Almost entirely blank |
| `Ballot Style` | `ballot_style` | String or None if empty | "ABSENTEE BY MAIL" |
| `Absentee` | `absentee` | `str.upper() == "Y"` | "Y" → True |
| `Provisional` | `provisional` | `str.upper() == "Y"` | blank → False |
| `Supplemental` | `supplemental` | `str.upper() == "Y"` | "N" → False |

**Auto-populated fields**: `id` (UUID), `import_job_id` (from job), `created_at` (server default), `election_id` (resolved post-import by `election_resolution_service`)

---

### Mapping 2: `A-12599/STATEWIDE.csv` → New `AbsenteeBallotApplication` Model

38 CSV columns → new model. No existing model or parser handles this.

| # | CSV Column | Proposed Model Field | Type | Conversion Notes |
|---|---|---|---|---|
| 1 | `County` | `county` | String(100), NOT NULL | As-is, uppercase |
| 2 | `Voter Registration #` | `voter_registration_number` | String(20), NOT NULL | Strip leading zeros (match voter history pattern) |
| 3 | `Last Name` | `last_name` | String(100), NOT NULL | As-is |
| 4 | `First Name` | `first_name` | String(100), NOT NULL | As-is |
| 5 | `Middle Name` | `middle_name` | String(100), nullable | Empty → None |
| 6 | `Suffix` | `suffix` | String(20), nullable | Empty → None |
| 7 | `Street #` | `residence_street_number` | String(20), nullable | As-is |
| 8 | `Street Name` | `residence_street_name` | String(200), nullable | Combined field (no decomposition possible) |
| 9 | `Apt/Unit` | `residence_apt_unit` | String(50), nullable | Empty → None |
| 10 | `City` | `residence_city` | String(100), nullable | As-is |
| 11 | `State` | `residence_state` | String(2), nullable | Always "GA" for residence |
| 12 | `Zip Code` | `residence_zip_code` | String(20), nullable | ZIP+4 format preserved ("31554-3841") |
| 13 | `Mailing Street #` | `mailing_street_number` | String(20), nullable | As-is |
| 14 | `Mailing Street Name` | `mailing_street_name` | String(200), nullable | May be international address |
| 15 | `Mailing Apt/Unit` | `mailing_apt_unit` | String(50), nullable | Empty → None |
| 16 | `Mailing City` | `mailing_city` | String(100), nullable | Includes "KUWAIT CITY", "SCEAUX" |
| 17 | `Mailing State` | `mailing_state` | String(20), nullable | Includes "NA" for international; wider than 2 chars |
| 18 | `Mailing Zip Code` | `mailing_zip_code` | String(20), nullable | Includes "00000" for international |
| 19 | `Application Status` | `application_status` | String(10), NOT NULL | "A" or "R" (1 corrupted row: "BS6-6QW") |
| 20 | `Ballot Status` | `ballot_status` | String(10), nullable | "A", "R", or blank |
| 21 | `Status Reason` | `status_reason` | String(200), nullable | Free text: "APPLICATION ACCEPTED", "APPLICATION REJECTED", etc. |
| 22 | `Application Date` | `application_date` | Date, nullable | MM/DD/YYYY → `date` |
| 23 | `Ballot Issued Date` | `ballot_issued_date` | Date, nullable | MM/DD/YYYY → `date`; mostly blank |
| 24 | `Ballot Return Date` | `ballot_return_date` | Date, nullable | MM/DD/YYYY → `date`; mostly blank |
| 25 | `Ballot Style` | `ballot_style` | String(100), nullable | "ABSENTEE BY MAIL", "ELECTRONIC BALLOT DELIVERY", "EARLY IN-PERSON" |
| 26 | `Ballot Assisted` | `ballot_assisted` | Boolean | "YES"→True, "NO"→False |
| 27 | `Challenged/Provisional` | `challenged_provisional` | Boolean | "YES"→True, "NO"→False |
| 28 | `ID Required` | `id_required` | Boolean | "YES"→True, "NO"→False |
| 29 | `Municipal Precinct` | `municipal_precinct` | String(50), nullable | Blank for most rows |
| 30 | `County Precinct` | `county_precinct` | String(100), nullable | Precinct name string |
| 31 | `CNG` | `congressional_district` | String(10), nullable | 3-digit zero-padded ("001") |
| 32 | `SEN` | `state_senate_district` | String(10), nullable | 3-digit zero-padded ("019") |
| 33 | `HOUSE` | `state_house_district` | String(10), nullable | 3-digit zero-padded ("178") |
| 34 | `JUD` | `judicial_district` | String(10), nullable | 4-letter code ("WAYC") |
| 35 | `Combo #` | `combo_number` | String(10), nullable | 5-digit zero-padded ("00005") |
| 36 | `Vote Center ID` | `vote_center_id` | String(50), nullable | Mostly blank |
| 37 | `Ballot ID` | `ballot_id` | String(50), nullable | Unique ballot identifier |
| 38 | `Party` | `party` | String(50), nullable | "REPUBLICAN", "DEMOCRAT", "NON-PARTISAN" |

**Auto-populated fields**: `id` (UUID), `import_job_id` (from job), `created_at` (server default)

**Suggested unique constraint**: `(voter_registration_number, import_job_id)` — one row per voter per import snapshot.

**Key incompatibility**: The address fields (columns 7-8) use a simplified `Street # + Street Name` format that cannot be decomposed into the `Voter` model's 6-field address structure (`street_number`, `pre_direction`, `street_name`, `street_type`, `post_direction`, `apt_unit_number`). These should be stored as-is in the absentee model, not mapped to the voter address format.

**Join key to existing data**: `voter_registration_number` links to `voters.voter_registration_number` and `voter_history.voter_registration_number`. Note that the absentee file preserves leading zeros ("00468991") while the voter history parser strips them ("468991"). The absentee parser must apply the same `lstrip('0')` normalization.

---

### Mapping 3: `Qualified Candidates.csv` → `Candidate` Model (existing + extensions)

11 CSV columns. 5 map to existing fields, 6 require new columns.

| # | CSV Column | Model Field | Status | Type Conversion |
|---|---|---|---|---|
| 1 | `CONTEST NAME` | `contest_name` | **NEW** String(500), nullable | As-is; also used to resolve `election_id` |
| 2 | `COUNTY` | `home_county` | **NEW** String(100), nullable | As-is, uppercase |
| 3 | `MUNICIPALITY` | `municipality` | **NEW** String(100), nullable | Empty → None |
| 4 | `CANDIDATE NAME` | `full_name` | EXISTS String(200) | Direct match |
| 5 | `CANDIDATE STATUS` | `filing_status` | EXISTS String(20) | "Qualified" → "qualified" (lowercase) |
| 6 | `POLITICAL PARTY` | `party` | EXISTS String(50) | "Republican" → "Republican" (as-is) |
| 7 | `QUALIFIED DATE` | `qualified_date` | **NEW** Date, nullable | MM/DD/YYYY → `date` |
| 8 | `INCUMBENT` | `is_incumbent` | EXISTS Boolean | "YES" → True, "NO" → False |
| 9 | `OCCUPATION` | `occupation` | **NEW** String(200), nullable | As-is |
| 10 | `EMAIL ADDRESS` | `email` | **NEW** String(200), nullable | Empty → None |
| 11 | `WEBSITE` | *(CandidateLink)* | EXISTS (via link table) | Create `CandidateLink(link_type="website", url=...)` with "https://" prefix if missing |

**Critical derived field**: `election_id` — must be resolved from `CONTEST NAME` by:
1. Parsing the contest name into `(district_type, district_identifier, party)`
2. Matching to an existing `Election` record, or creating one

**Contest name parsing examples and their resolution**:

| Contest Name | district_type | district_id | party | Election Lookup |
|---|---|---|---|---|
| `U.S House of Representatives, District 11 (R)` | `congressional` | `11` | `Republican` | Match election with `district_type=congressional`, `district_identifier=11` |
| `State Senate District 42 (D)` | `state_senate` | `42` | `Democrat` | Match election with `district_type=state_senate`, `district_identifier=42` |
| `State House District 98 (R)` | `state_house` | `98` | `Republican` | Match election |
| `Agriculture Commissioner (D)` | `statewide` | None | `Democrat` | New pattern — not in current parser |
| `Board of Commissioners District 2 (D)` | `county_commission` | `2` | `Democrat` | Partially supported by existing parser |
| `BERRIEN COUNTY COMMISSIONER DISTRICT 2` | `county_commission` | `2` | None | Mixed casing — needs fuzzy match |
| `Associate State Court Judge` | `judicial` | None | None | New pattern — not in current parser |

The existing `district_parser.py` handles state senate/house/congressional/PSC/county_commission patterns. It does **not** handle:
- Statewide offices (Agriculture Commissioner, Attorney General, etc.)
- Judicial races (State Court Judge, etc.)
- The `(R)`/`(D)` party suffix format (it only handles `- Dem`/`- Rep`)
- Municipality-specific races
- Inconsistent casing/punctuation across counties

---

### Mapping 4: `election_info.html` → `Election` Model (existing fields)

All target fields already exist on the `Election` model (added in migration 038).

| HTML Label | Model Field | Type | Extraction Notes |
|---|---|---|---|
| Election day date + name | `election_date` + `name` | Date + String | Used to locate the election to update |
| "Registration Deadline" | `registration_deadline` | Date, nullable | MM/DD/YYYY in div text |
| "Early In-Person Voting Begins" | `early_voting_start` | Date, nullable | MM/DD/YYYY in div text |
| *(not in HTML)* | `early_voting_end` | Date, nullable | Would need to be inferred or sourced from PDF |
| "Last day...absentee application" | `absentee_request_deadline` | Date, nullable | MM/DD/YYYY in div text |
| *(Qualifying period from Candidates CSV)* | `qualifying_start` / `qualifying_end` | DateTime, nullable | Derivable: all candidates have "03/02/2026"–"03/06/2026" |

**HTML structure**: Salesforce SLDS grid layout with `<div class="text-muted">Label</div>` / `<div class="textwebsiteColor">Value</div>` pairs. Parseable with BeautifulSoup or similar.

---

### Mapping 5: `2026 Short Calendar.pdf` → `Election` Model (same fields as #4)

| PDF Field | Model Field | Elections Covered |
|---|---|---|
| Election Date | `election_date` | 05/19, 06/16, 11/03, 12/01/2026 |
| Registration Deadline | `registration_deadline` | All 4 elections |
| Advance Voting Start | `early_voting_start` | All 4 elections |
| Advance Voting End | `early_voting_end` | All 4 elections (this is the one field HTML doesn't provide) |
| Candidate Qualifying | `qualifying_start` / `qualifying_end` | 03/02–03/06/2026 (applies to all) |

The PDF is the only source that provides `early_voting_end` dates. All other calendar fields are also available from the HTML (Data Source 4).

---

## Cross-Source Join Key Compatibility

| Join | Key Field | Source A Format | Source B Format | Compatible? |
|---|---|---|---|---|
| Absentee → Voter | `voter_registration_number` | Leading zeros ("00468991") | Stripped ("468991") | **Needs normalization** — apply same `lstrip('0')` |
| VoterHistory → Voter | `voter_registration_number` | Already stripped | Already stripped | Yes |
| Absentee → VoterHistory | `voter_registration_number` | Leading zeros | Already stripped | **Needs normalization** |
| Candidates → Election | contest_name → election lookup | Free text | `(name, election_date)` | **Needs parsing + fuzzy matching** |
| Calendar → Election | election_date + name | Date + text | `(name, election_date)` | Manual matching needed |

---

## File Inventory

| File | Size | Records | Columns | Import Ready? |
|---|---|---|---|---|
| `2026.csv` (in `extracted/2026/`) | ~4.6 MB | 120,027 | 9 | YES |
| `A-12599/STATEWIDE.csv` (in `extracted/`) | ~1.8 MB | 4,853 | 38 | NO |
| `A-12599/*.csv` (89 county files) | varies | varies | 38 | NO |
| `Qualified Candidates.csv` | 349 KB | 2,329 | 11 | NO (partial) |
| `election_info.html` | 31 KB | 1 election | ~8 fields | NO |
| `2026 Short Calendar.pdf` | 176 KB | 4 elections | ~5 fields each | NO |
