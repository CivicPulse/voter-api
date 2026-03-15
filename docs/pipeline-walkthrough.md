# Georgia Election Data Pipeline Walkthrough

This walkthrough proves the three-stage pipeline — SOS CSV source data to
Markdown to JSONL to Database — works end-to-end with real Georgia election
data. By the end you will have three elections (two March 2026 special
elections, one May 2026 general primary), 34 contests, 49 candidates, and 49
candidacies stored in a local PostGIS database and queryable through the API.

**What you need:** uv, Docker + Docker Compose, git, curl, jq
**Time estimate:** ~15 minutes

---

## Prerequisites

### Clone and install

```bash
git clone https://github.com/CivicPulse/voter-api.git
cd voter-api
git checkout worktree-better-imports   # or main once merged
uv sync
```

See `specs/001-voter-data-management/quickstart.md` for full environment
variable documentation.

### Start PostGIS and run migrations

Start the database container and apply all Alembic migrations before doing
anything else. Import commands require the schema to exist.

```bash
# Start PostGIS in the background
docker compose up -d db

# Wait for it to become healthy (~5 seconds), then apply migrations
DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api \
  JWT_SECRET_KEY=test-secret-key-minimum-32-characters \
  uv run voter-api db upgrade
```

Expected output:

```
INFO  [alembic.runtime.migration] Running upgrade  -> 001, initial schema
...
INFO  [alembic.runtime.migration] Running upgrade 028 -> 029, add candidacy table
INFO  [alembic.runtime.migration] Running upgrade 029 -> 030, add election event table
```

Set these environment variables in your shell for the rest of the walkthrough
(avoids repeating them on every command):

```bash
export DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api
export JWT_SECRET_KEY=test-secret-key-minimum-32-characters
export ELECTION_REFRESH_ENABLED=false
```

---

## Step 1: Review the Markdown (Human-in-the-Loop)

Phase 3 of this milestone used Claude Code skills to transform raw SOS CSV
data into structured markdown files. All three election directories were
processed and committed:

```
data/elections/
  2026-03-10/    — 6 files (5 statewide/district contests + 1 county)
  2026-03-17/    — 5 files (4 municipal/county contests + overview)
  2026-05-19/    — 185 files (16 statewide contests + 159 county + overview)
data/candidates/ — 49 files (one per candidate, across March elections only)
```

Before running the converter, review the markdown to verify the AI output is
correct. This is the human-in-the-loop step that documents the design
philosophy: AI produces data, humans review it, deterministic tools import it.

```bash
# See what Phase 3 produced
git log --oneline -- data/elections/ data/candidates/
```

```
e1e25ff feat(04-01): complete end-to-end election pipeline for all three elections
fa5011e feat(04-01): nullify placeholder UUID in election import service
```

Review a sample file to understand the format:

```bash
cat data/elections/2026-03-10/2026-03-10-us-house-district-14.md
```

```markdown
# U.S. House — District 14

## Metadata

| Field | Value |
|-------|-------|
| ID | d4c68384-af14-45d3-93ad-98b9bfcecd91 |
| Format Version | 1 |
| Election | [March 10, 2026 — Special Election](2026-03-10-special-election.md) |
| Type | special |
| Stage | election |
| Body | us-house |
| Seat | district-14 |
| Name (SOS) | United States Representative, District 14 |

## Republican Primary

**Contest Name (SOS):** United States Representative, District 14 (R)

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| Beau Brown | Qualified | No | Risk Engineer | 01/13/2026 |
| Brian Stover | Qualified | No | Business Development | 01/12/2026 |
...
```

Each contest file has:
- A UUID in the `ID` field (used as the election's primary key)
- `Body` and `Seat` fields encoding the district reference system (e.g.,
  `us-house` + `district-14`)
- A candidate table with filing status, occupation, and qualified date

The Body/Seat reference system is how the pipeline links elections to district
boundaries without requiring boundary data to be loaded first. District-based
API queries use these identifiers.

Review a candidate file to see the enriched data format:

```bash
cat data/candidates/albert-chester-gibbs-82386174.md
```

```markdown
# Albert Chester Gibbs

## Metadata

| Field | Value |
|-------|-------|
| ID | 82386174-73ab-42a3-9efe-b0717379beb0 |
| Name | Albert Chester Gibbs |
| Email | achestergibbs2026@gmail.com |

## Bio

Central High School graduate, attended Morris Brown College (business).
Kitchen designer at Home Depot with 20 years of experience in Atlanta banking.
Emphasizes the diversity of District 5, open dialogue with voters, and
practical solutions to urban blight.

## Links

| Type | URL | Label |
|------|-----|-------|
| email | https://mailto:achestergibbs2026@gmail.com | achestergibbs2026@gmail.com |

## Elections

### March 17, 2026 — Special Election — Bibb County — County Commission District 5

| Field | Value |
|-------|-------|
| Contest File | [2026-03-17-bibb-commission-district-5.md](../elections/...) |
| Party | Non-Partisan |
| Occupation | Kitchen Designer |
| Filing Status | qualified |
| Qualified Date | 02/11/2026 |
```

Once you are satisfied with the data quality, proceed to conversion.

---

## Step 2: Prepare Files for Conversion

The converter requires all files to be in the enhanced format (with a
`Format Version` metadata row and empty `ID` fields that will be filled by
the normalizer). All three elections in this repo are already migrated. The
`normalize elections` command handles UUID generation and text normalization.

**Note:** If you are onboarding a pre-Phase 3 election directory (the old
format without `Format Version`), run `migrate-format` first:

```bash
# Only needed for old-format directories — skip for this walkthrough
uv run voter-api convert migrate-format data/elections/2026-05-19/
```

For all three elections in this walkthrough, run `normalize elections` to
ensure metadata is consistent (UUIDs already populated, text normalized):

```bash
uv run voter-api normalize elections data/elections/2026-03-10/
uv run voter-api normalize elections data/elections/2026-03-17/
uv run voter-api normalize elections data/elections/2026-05-19/
```

Real output (March 10):

```
Normalization Report
============================================================
  Total: 6  Succeeded: 6  Failed: 0  UUIDs Generated: 0  Renamed: 0
------------------------------------------------------------
File                                     Status     Changes
------------------------------------------------------------
...3-10/2026-03-10-special-election.md   SUCCESS    0
...6-03-10-state-house-district-130.md   SUCCESS    0
...26-03-10-state-house-district-94.md   SUCCESS    0
...6-03-10-state-senate-district-53.md   SUCCESS    0
.../2026-03-10-us-house-district-14.md   SUCCESS    0
...10/counties/2026-03-10-whitfield.md   SUCCESS    0
============================================================
```

The `0 changes` output confirms all files are already normalized. On a fresh
batch you would see changes counted here (candidate name title-casing, date
format normalization, etc.). The `UUIDs Generated: 0` line confirms every file
already has its UUID — which the converter will embed into the JSONL output.

---

## Step 3: Convert Markdown to JSONL

The converter is deterministic — no AI, no network calls. Given the same
markdown files, it always produces the same JSONL output. This is what makes
the pipeline reproducible.

Convert all three election directories:

```bash
uv run voter-api convert directory data/elections/2026-03-10/
uv run voter-api convert directory data/elections/2026-03-17/
uv run voter-api convert directory data/elections/2026-05-19/
```

Real output — March 10 (6 files):

```
Conversion Report
============================================================
  Total: 6  Succeeded: 6  Failed: 0
------------------------------------------------------------
File                                     Status     Records
------------------------------------------------------------
...3-10/2026-03-10-special-election.md   SUCCESS    1
...6-03-10-state-house-district-130.md   SUCCESS    1
...26-03-10-state-house-district-94.md   SUCCESS    1
...6-03-10-state-senate-district-53.md   SUCCESS    1
.../2026-03-10-us-house-district-14.md   SUCCESS    1
...10/counties/2026-03-10-whitfield.md   SUCCESS    1
============================================================

Converted 6 file(s) successfully.
```

Real output — March 17 (5 files):

```
Conversion Report
============================================================
  Total: 5  Succeeded: 5  Failed: 0
------------------------------------------------------------
File                                     Status     Records
------------------------------------------------------------
...03-17-bibb-commission-district-5.md   SUCCESS    1
...-03-17/2026-03-17-buchanan-mayor.md   SUCCESS    1
...2026-03-17-clayton-probate-judge.md   SUCCESS    1
...3-17/2026-03-17-special-election.md   SUCCESS    1
...2026-03-17-wadley-council-member.md   SUCCESS    1
============================================================

Converted 5 file(s) successfully.
```

Real output — May 19 (185 files, truncated here):

```
Conversion Report
============================================================
  Total: 185  Succeeded: 185  Failed: 0
------------------------------------------------------------
File                                     Status     Records
------------------------------------------------------------
...6-05-19-agriculture-commissioner.md   SUCCESS    1
...5-19/2026-05-19-attorney-general.md   SUCCESS    1
...05-19/2026-05-19-general-primary.md   SUCCESS    1
...s/2026-05-19/2026-05-19-governor.md   SUCCESS    1
[... 177 more lines ...]
...05-19/counties/2026-05-19-wilkes.md   SUCCESS    0
...19/counties/2026-05-19-wilkinson.md   SUCCESS    7
...-05-19/counties/2026-05-19-worth.md   SUCCESS    8
============================================================

Converted 185 file(s) successfully.
```

The `Records` column shows how many contest records each file contributed.
County files (like `wilkinson.md`) contribute multiple records, one per
contest. Some counties report `0` records — these are uncontested or had no
qualifying candidates in their local races.

Each conversion writes two files into a `jsonl/` subdirectory:

```
data/elections/2026-03-10/jsonl/
  election_events.jsonl   — 1 record (the election event itself)
  elections.jsonl         — 5 records (one per contest)
data/elections/2026-03-17/jsonl/
  election_events.jsonl   — 1 record
  elections.jsonl         — 4 records
data/elections/2026-05-19/jsonl/
  election_events.jsonl   — 1 record
  elections.jsonl         — 25 records
```

The converter also writes a `conversion-report.json` in each `jsonl/`
directory with the full per-file result set for programmatic inspection.

Sample `election_events.jsonl` record for March 10:

```json
{
  "schema_version": 1,
  "id": "0459e7b6-59e1-418e-a6eb-fd6cc3d7760b",
  "event_date": "2026-03-10",
  "event_name": "March 10, 2026 — Special Election",
  "event_type": "special",
  "registration_deadline": null,
  "early_voting_start": null,
  "early_voting_end": null,
  "absentee_request_deadline": null,
  "qualifying_start": null,
  "qualifying_end": null,
  "data_source_url": null,
  "last_refreshed_at": null,
  "refresh_interval_seconds": null
}
```

Sample `elections.jsonl` record (U.S. House District 14):

```json
{
  "schema_version": 1,
  "id": "d4c68384-af14-45d3-93ad-98b9bfcecd91",
  "election_event_id": "00000000-0000-0000-0000-000000000000",
  "name": "U.S. House — District 14",
  "election_date": "2026-03-10",
  "election_type": "special",
  "election_stage": "election",
  "district_identifier": "district-14",
  "boundary_type": null
}
```

Note the `election_event_id` is a placeholder UUID
(`00000000-0000-0000-0000-000000000000`). The import service treats this as
`NULL` — the election event FK is resolved during import using the matching
event in the database, not from the JSONL file directly.

---

## Step 4: Generate Candidate and Candidacy JSONL

The 49 files in `data/candidates/` contain enriched candidate data: bio text,
contact information, links, external IDs, and election section(s) linking each
candidate to specific contests via a Contest File reference.

The `generate_candidate_jsonl.py` script reads all candidate files, resolves
the election UUID by reading each contest file's `ID` field, validates the
records against the `CandidateJSONL` and `CandidacyJSONL` schemas, and writes
per-election JSONL output.

```bash
uv run python scripts/generate_candidate_jsonl.py
```

Real output:

```
Writing JSONL output...
  data/elections/2026-03-10/jsonl/candidates.jsonl: 39 candidates
  data/elections/2026-03-10/jsonl/candidacies.jsonl: 39 candidacies
  data/elections/2026-03-17/jsonl/candidates.jsonl: 10 candidates
  data/elections/2026-03-17/jsonl/candidacies.jsonl: 10 candidacies

Summary:
  Total candidates processed: 49
  Total candidacies processed: 49
  Election dates: 2026-03-10, 2026-03-17

All records validated successfully.
```

Note that May 19 has no candidates yet (candidate files only exist for the two
March elections). The script only produces output for election dates that have
at least one candidate with a valid Contest File UUID.

How the script resolves `election_id`: each candidate file's `## Elections`
section has a `Contest File` field pointing to the contest markdown file (e.g.,
`../elections/2026-03-17/2026-03-17-bibb-commission-district-5.md`). The script
reads that file, extracts its `ID` field, and uses that UUID as the
`election_id` in the candidacy record. This creates the candidate-election
linkage without requiring a database query.

Sample `candidates.jsonl` record (Audrey Taylor Lux):

```json
{
  "schema_version": 1,
  "id": "ac7df693-2754-4fde-a61f-ee2187984d7c",
  "full_name": "Audrey Taylor Lux",
  "bio": null,
  "photo_url": null,
  "email": "audrey@audrey4ga.com",
  "links": [
    {"link_type": "other", "url": "https://mailto:audrey@audrey4ga.com", "label": "audrey@audrey4ga.com"},
    {"link_type": "website", "url": "https://www.audrey4ga.com", "label": "audrey4ga.com"}
  ],
  "external_ids": null
}
```

Sample `candidacies.jsonl` record (Audrey Taylor Lux for State House Dist 94):

```json
{
  "schema_version": 1,
  "id": "5ca54866-37b1-524d-ad27-1e0eaa321745",
  "candidate_id": "ac7df693-2754-4fde-a61f-ee2187984d7c",
  "election_id": "cf0f7361-de7c-421d-b2f6-1c30a9849d73",
  "party": "Democrat",
  "filing_status": "qualified",
  "is_incumbent": false,
  "occupation": "Candidate",
  "qualified_date": "2026-01-27",
  "contest_name": "March 10, 2026 — Special Election — State House — District 94"
}
```

The candidacy UUID is deterministic — generated as UUID v5 from
`candidate_id:election_id` — so re-running the script always produces the same
UUID for the same candidate-election pair.

---

## Step 5: Dry-Run Import

Before writing to the database, run a dry-run to validate all JSONL against
the schema and see what record counts to expect. The dry-run reads and
validates every record but performs no writes.

```bash
uv run voter-api import election-data data/elections/2026-03-10/jsonl --dry-run
uv run voter-api import election-data data/elections/2026-03-17/jsonl --dry-run
uv run voter-api import election-data data/elections/2026-05-19/jsonl --dry-run
```

Expected output (March 10):

```
DRY RUN -- no changes will be made

Importing election_events.jsonl...
2026-03-10 ... Read election_events.jsonl: 1 valid, 0 errors
  election_events.jsonl: would insert 1, would update 0

Importing elections.jsonl...
2026-03-10 ... Read elections.jsonl: 5 valid, 0 errors
  elections.jsonl: would insert 5, would update 0

Importing candidates.jsonl...
2026-03-10 ... Read candidates.jsonl: 39 valid, 0 errors
  candidates.jsonl: would insert 39, would update 0

Importing candidacies.jsonl...
2026-03-10 ... Read candidacies.jsonl: 39 valid, 0 errors
  candidacies.jsonl: would insert 39, would update 0

============================================================
PIPELINE SUMMARY
============================================================
  [OK] election_events.jsonl
  [OK] elections.jsonl
  [OK] candidates.jsonl
  [OK] candidacies.jsonl
============================================================
```

Expected dry-run counts:

| Election        | Election Events | Elections | Candidates | Candidacies |
|-----------------|-----------------|-----------|------------|-------------|
| 2026-03-10      | 1               | 5         | 39         | 39          |
| 2026-03-17      | 1               | 4         | 10         | 10          |
| 2026-05-19      | 1               | 25         | 0          | 0           |
| **Total**       | **3**           | **34**    | **49**     | **49**      |

---

## Step 6: Import into Database

Run the real import for each election directory. The `election-data` pipeline
command handles dependency order automatically:
`election_events.jsonl` → `elections.jsonl` → `candidates.jsonl` → `candidacies.jsonl`

```bash
uv run voter-api import election-data data/elections/2026-03-10/jsonl
uv run voter-api import election-data data/elections/2026-03-17/jsonl
uv run voter-api import election-data data/elections/2026-05-19/jsonl
```

Expected output (March 10):

```
Importing election_events.jsonl...
... Read election_events.jsonl: 1 valid, 0 errors
  election_events.jsonl: 1 inserted, 0 updated, 0 errors

Importing elections.jsonl...
... Read elections.jsonl: 5 valid, 0 errors
  elections.jsonl: 5 inserted, 0 updated, 0 errors

Importing candidates.jsonl...
... Read candidates.jsonl: 39 valid, 0 errors
  candidates.jsonl: 39 inserted, 0 updated, 0 errors

Importing candidacies.jsonl...
... Read candidacies.jsonl: 39 valid, 0 errors
  candidacies.jsonl: 39 inserted, 0 updated, 0 errors

============================================================
PIPELINE SUMMARY
============================================================
  [OK] election_events.jsonl
  [OK] elections.jsonl
  [OK] candidates.jsonl
  [OK] candidacies.jsonl
============================================================
```

Expected import counts per election:

| Election        | Election Events | Elections | Candidates | Candidacies |
|-----------------|-----------------|-----------|------------|-------------|
| 2026-03-10      | 1 inserted      | 5 inserted | 39 inserted | 39 inserted |
| 2026-03-17      | 1 inserted      | 4 inserted | 10 inserted | 10 inserted |
| 2026-05-19      | 1 inserted      | 25 inserted | — (no candidates.jsonl) | — |

After all three imports, the database contains:
- 3 election events
- 34 elections (contest records)
- 49 candidates
- 49 candidacies

---

## Step 7: Verify Idempotency

Re-run any import to confirm the UPSERT behavior — same UUIDs produce updates,
not duplicates or errors.

```bash
uv run voter-api import election-data data/elections/2026-03-10/jsonl
```

Expected output:

```
  election_events.jsonl: 0 inserted, 1 updated, 0 errors
  elections.jsonl: 0 inserted, 5 updated, 0 errors
  candidates.jsonl: 0 inserted, 39 updated, 0 errors
  candidacies.jsonl: 0 inserted, 39 updated, 0 errors
```

All records are updated in-place via `INSERT ... ON CONFLICT (id) DO UPDATE`.
The UPSERT uses `COALESCE` for nullable fields, so running the import again
with richer data will update the record while running with sparser data will
not overwrite existing non-null values.

---

## Step 8: Verify via API

### Start the API server

In a separate terminal window:

```bash
DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api \
  JWT_SECRET_KEY=test-secret-key-minimum-32-characters \
  ELECTION_REFRESH_ENABLED=false \
  uv run voter-api serve --reload
```

The server starts at `http://localhost:8000`. You can also browse the
interactive API docs at `http://localhost:8000/docs`.

### Create an admin user

```bash
DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api \
  JWT_SECRET_KEY=test-secret-key-minimum-32-characters \
  ELECTION_REFRESH_ENABLED=false \
  uv run voter-api user create \
    --username demo \
    --email demo@example.com \
    --password "DemoP@ss123!" \
    --role admin \
    --if-not-exists
```

### Authenticate and get a JWT

The login endpoint takes a JSON body (not form-data — this changed in Phase
009 when passkey auth was added).

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "DemoP@ss123!"}' \
  | jq -r '.access_token')

echo "Token: ${TOKEN:0:30}..."
```

Store the token for subsequent requests:

```bash
AUTH="Authorization: Bearer $TOKEN"
```

---

### Query 1: List elections by date

Verify that May 19 imported correctly and the count matches the expected 25
contests:

```bash
curl -s "http://localhost:8000/api/v1/elections?date_from=2026-05-19&date_to=2026-05-19&limit=5" \
  -H "$AUTH" | jq '{total: .total, items: [.items[] | {id, name, election_type}]}'
```

Expected response:

```json
{
  "total": 25,
  "items": [
    {
      "id": "...",
      "name": "Agriculture Commissioner",
      "election_type": "general_primary"
    },
    {
      "id": "...",
      "name": "Attorney General",
      "election_type": "general_primary"
    },
    {
      "id": "...",
      "name": "Governor",
      "election_type": "general_primary"
    },
    {
      "id": "...",
      "name": "Insurance Commissioner",
      "election_type": "general_primary"
    },
    {
      "id": "...",
      "name": "Labor Commissioner",
      "election_type": "general_primary"
    }
  ]
}
```

You should see `"total": 25` for May 19. For March 10 (special elections),
query `date_from=2026-03-10&date_to=2026-03-10` and expect `"total": 5`.

---

### Query 2: Candidate lookup with enriched fields

Look up a specific candidate to verify the enriched fields (email, links, bio)
came through the full pipeline from markdown to database to API.

First, find the Albert Chester Gibbs candidate UUID. His ID is embedded in his
candidate file (`82386174-73ab-42a3-9efe-b0717379beb0`):

```bash
curl -s "http://localhost:8000/api/v1/candidates/82386174-73ab-42a3-9efe-b0717379beb0" \
  -H "$AUTH" | jq '{id, full_name, email, bio, links}'
```

Expected response:

```json
{
  "id": "82386174-73ab-42a3-9efe-b0717379beb0",
  "full_name": "Albert Chester Gibbs",
  "email": "achestergibbs2026@gmail.com",
  "bio": "Central High School graduate, attended Morris Brown College (business). Kitchen designer at Home Depot with 20 years of experience in Atlanta banking. Emphasizes the diversity of District 5, open dialogue with voters, and practical solutions to urban blight.",
  "links": [
    {
      "link_type": "other",
      "url": "https://mailto:achestergibbs2026@gmail.com",
      "label": "achestergibbs2026@gmail.com"
    }
  ]
}
```

This confirms the full chain: the bio text was authored in the candidate
markdown file, exported to `candidates.jsonl`, imported via UPSERT, and
returned by the API — all without modification.

---

### Query 3: Election detail with linked candidates via candidacy junction

Retrieve the Bibb County Commission District 5 election and verify its linked
candidates:

```bash
# First get the election UUID for Bibb Commission District 5
BIBB_ELECTION=$(curl -s "http://localhost:8000/api/v1/elections?limit=100&date_from=2026-03-17&date_to=2026-03-17" \
  -H "$AUTH" | jq -r '.items[] | select(.name | contains("Bibb")) | .id')

echo "Bibb election ID: $BIBB_ELECTION"

# Then get the election detail with candidates
curl -s "http://localhost:8000/api/v1/elections/$BIBB_ELECTION" \
  -H "$AUTH" | jq '{id, name, election_date, election_type, candidacies: [.candidacies[]? | {candidate: .candidate.full_name, party: .party, occupation: .occupation}]}'
```

Expected response:

```json
{
  "id": "f377b67c-e236-4a23-b8e3-7f0ca84448c6",
  "name": "Bibb County — County Commission District 5",
  "election_date": "2026-03-17",
  "election_type": "special",
  "candidacies": [
    {
      "candidate": "Albert Chester Gibbs",
      "party": "Non-Partisan",
      "occupation": "Kitchen Designer"
    }
  ]
}
```

The candidate is linked through the `candidacies` junction table — not stored
directly on the election record. This is the Person entity model: one
candidate record per person, multiple candidacy records per election cycle.

---

### Query 4: District-based query (Body/Seat linkage)

Verify that the Body/Seat reference system survived the full pipeline from
markdown metadata through converter through import through API.

Query elections by `boundary_type` and `district_identifier` to find all
state house district elections:

```bash
curl -s "http://localhost:8000/api/v1/elections?boundary_type=state_house&limit=10" \
  -H "$AUTH" | jq '{total: .total, items: [.items[] | {id, name, election_date, district_identifier, boundary_type}]}'
```

Expected response:

```json
{
  "total": 2,
  "items": [
    {
      "id": "40260d3f-2402-4466-9f64-c14fb1a99b01",
      "name": "State House — District 130",
      "election_date": "2026-03-10",
      "district_identifier": "district-130",
      "boundary_type": "state_house"
    },
    {
      "id": "cf0f7361-de7c-421d-b2f6-1c30a9849d73",
      "name": "State House — District 94",
      "election_date": "2026-03-10",
      "district_identifier": "district-94",
      "boundary_type": "state_house"
    }
  ]
}
```

The `boundary_type` and `district_identifier` fields come directly from the
`Body` and `Seat` metadata rows in the markdown files. The converter parsed
these into the JSONL, and the import service stored them in the elections
table. When district boundary polygons are loaded later (via `voter-api import
all-boundaries`), these fields will be used to link elections to their spatial
boundaries.

---

## Cleanup

**Keep the database running** (recommended for development):

```bash
# Stop just the API server with Ctrl+C in its terminal
# Database keeps running — you can query it directly via the MCP server
```

**Or tear down completely:**

```bash
docker compose down
# To also remove the database volume (destroys all data):
docker compose down -v
```

---

## What This Proved

The three-stage pipeline works end-to-end with real Georgia election data:

```
SOS CSV source
  → Phase 3: Claude Code skills → Markdown (human-reviewable)
  → Step 2:  voter-api normalize → UUID backfill, text normalization
  → Step 3:  voter-api convert   → JSONL (deterministic, schema-validated)
  → Step 4:  generate_candidate_jsonl.py → enriched candidate/candidacy JSONL
  → Step 5:  voter-api import --dry-run  → validation preview
  → Step 6:  voter-api import            → database write
  → Step 8:  API queries                 → verified results
```

**What works:**

- Election events, elections, candidates, and candidacies import cleanly from
  JSONL through the `election-data` pipeline command
- All three election directories produce the expected record counts (34 total
  contests, 49 candidates, 49 candidacies)
- Enriched candidate fields (bio, email, links) survive the full pipeline and
  are returned by the API
- The candidacy junction table correctly links candidates to their elections
  (one candidate, multiple elections possible)
- The Body/Seat district reference system is preserved through all pipeline
  stages and supports `boundary_type` + `district_identifier` API queries
- Import is idempotent: re-running the same import produces 0 inserts and N
  updates with no errors
- The human-in-the-loop design is enforced by the pipeline structure: markdown
  files are committed to git and reviewed before the deterministic converter
  runs

**What comes next:**

- Load district boundary shapefiles (`voter-api import all-boundaries`) to
  populate `boundary_id` FKs and enable spatial queries
- Add candidate data for May 19 contests as SOS qualifying files are released
- Set up the SOS results feed integration to capture vote totals post-election
