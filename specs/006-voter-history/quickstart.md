# Quickstart: Voter History Ingestion

**Feature Branch**: `006-voter-history`

## Prerequisites

- PostgreSQL 15+ with PostGIS 3.x running
- Database migrated to head: `uv run voter-api db upgrade`
- Valid admin JWT token (for API access)

## CLI Usage

### Import Voter History

```bash
# Import a voter history CSV file
uv run voter-api import voter-history /path/to/2024.csv

# Import with custom batch size (default: 1000)
uv run voter-api import voter-history /path/to/2024.csv --batch-size 5000
```

**Output example**:

```text
Importing voter history from 2024.csv...
  Processing batch 1/50...
  Processing batch 2/50...
  ...
Import complete:
  Total records:     50000
  Succeeded:         49850
  Failed:            20
  Skipped (dupes):   100
  Unmatched voters:  30
  Elections created: 3
```

### Re-Import (File Replacement)

When the same file is imported again (e.g., after new election data is appended), all records from the previous import are atomically replaced:

```bash
# Re-import an updated file — replaces previous import's records
uv run voter-api import voter-history /path/to/2024.csv
```

## API Usage

### Import Voter History (POST)

```bash
# Upload voter history CSV (returns 202 with job ID)
curl -X POST https://voteapi.civpulse.org/api/v1/imports/voter-history \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@2024.csv"

# Check import status
curl https://voteapi.civpulse.org/api/v1/imports/{job_id} \
  -H "Authorization: Bearer $TOKEN"
```

### Query Voter History (GET)

```bash
# Get a voter's participation history
curl "https://voteapi.civpulse.org/api/v1/voters/12345678/history" \
  -H "Authorization: Bearer $TOKEN"

# Filter by date range
curl "https://voteapi.civpulse.org/api/v1/voters/12345678/history?date_from=2020-01-01&date_to=2024-12-31" \
  -H "Authorization: Bearer $TOKEN"

# Filter by election type
curl "https://voteapi.civpulse.org/api/v1/voters/12345678/history?election_type=GENERAL%20ELECTION" \
  -H "Authorization: Bearer $TOKEN"
```

### Election Participation (GET)

```bash
# List participants for an election
curl "https://voteapi.civpulse.org/api/v1/elections/{election_id}/participation" \
  -H "Authorization: Bearer $TOKEN"

# Filter by county
curl "https://voteapi.civpulse.org/api/v1/elections/{election_id}/participation?county=FULTON" \
  -H "Authorization: Bearer $TOKEN"

# Filter by voting method
curl "https://voteapi.civpulse.org/api/v1/elections/{election_id}/participation?absentee=true" \
  -H "Authorization: Bearer $TOKEN"
```

### Participation Statistics (GET)

```bash
# Get aggregate stats for an election
curl "https://voteapi.civpulse.org/api/v1/elections/{election_id}/participation/stats" \
  -H "Authorization: Bearer $TOKEN"
```

**Response example**:

```json
{
  "election_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_participants": 48500,
  "by_county": [
    {"county": "FULTON", "count": 12500},
    {"county": "DEKALB", "count": 8200},
    {"county": "COBB", "count": 7300}
  ],
  "by_ballot_style": [
    {"ballot_style": "GENERAL", "count": 45000},
    {"ballot_style": "PARTISAN", "count": 3500}
  ]
}
```

### Voter Detail (Enriched)

The existing voter detail endpoint now includes a `participation_summary`:

```bash
curl "https://voteapi.civpulse.org/api/v1/voters/{voter_id}" \
  -H "Authorization: Bearer $TOKEN"
```

**Response includes**:

```json
{
  "id": "...",
  "voter_registration_number": "12345678",
  "county": "FULTON",
  "participation_summary": {
    "total_elections": 8,
    "last_election_date": "2024-11-05"
  }
}
```

## CSV File Format

The GA SoS voter history CSV has 9 columns (comma-delimited, header row):

| Column                    | Example               | Notes                           |
| ------------------------- | --------------------- | ------------------------------- |
| County Name               | FULTON                | County where voter is registered |
| Voter Registration Number | 12345678              | Unique voter identifier          |
| Election Date             | 11/05/2024            | MM/DD/YYYY format                |
| Election Type             | GENERAL ELECTION      | Type of election                 |
| Party                     | REPUBLICAN            | Party ballot (primaries only)    |
| Ballot Style              | GENERAL               | Ballot style code                |
| Absentee                  | Y                     | Y/N (early/mail voting)          |
| Provisional               | N                     | Y/N (blank = N)                  |
| Supplemental              | N                     | Y/N (blank = N)                  |

## Development

### Run Tests

```bash
# Run all voter history tests
uv run pytest tests/ -k "voter_history"

# Run with coverage
uv run pytest tests/ -k "voter_history" --cov=voter_api --cov-report=term-missing
```

### Database Migration

```bash
# Apply the voter history migration
uv run voter-api db upgrade

# Rollback if needed
uv run voter-api db downgrade -1
```
