# Quickstart: 010-election-info

## Prerequisites

- Python 3.13+ (managed by `uv`)
- PostgreSQL 15+ with PostGIS 3.x
- Running dev database (via `docker compose up -d db` or local PostGIS)
- `uv sync` completed

## Setup

```bash
# 1. Install dependencies
uv sync

# 2. Apply migrations (includes new candidates tables + election metadata columns)
DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api \
  JWT_SECRET_KEY=test-secret-key-minimum-32-characters \
  uv run alembic upgrade head

# 3. Start dev server
uv run voter-api serve --reload
```

## New Endpoints

### Candidate Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/elections/{election_id}/candidates` | Public | List candidates for an election (paginated, filterable by status) |
| POST | `/api/v1/elections/{election_id}/candidates` | Admin | Create a candidate |
| GET | `/api/v1/candidates/{candidate_id}` | Public | Get candidate detail with links |
| PATCH | `/api/v1/candidates/{candidate_id}` | Admin | Update candidate fields |
| DELETE | `/api/v1/candidates/{candidate_id}` | Admin | Delete a candidate |
| POST | `/api/v1/candidates/{candidate_id}/links` | Admin | Add a link to a candidate |
| DELETE | `/api/v1/candidates/{candidate_id}/links/{link_id}` | Admin | Remove a link |

### Election Metadata (Extended Existing Endpoints)

| Method | Path | Auth | What Changed |
|--------|------|------|--------------|
| PATCH | `/api/v1/elections/{id}` | Admin | Now accepts: description, purpose, eligibility_description, registration_deadline, early_voting_start, early_voting_end, absentee_request_deadline, qualifying_start, qualifying_end |
| GET | `/api/v1/elections/{id}` | Public | Response now includes above fields (all nullable) |
| GET | `/api/v1/elections` | Public | New filters: registration_open, early_voting_active, district_type, district_identifier |

## Example: Create a Candidate

```bash
# Get an admin JWT first
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "..."}' | jq -r '.access_token')

# Create a candidate for an election
curl -X POST http://localhost:8000/api/v1/elections/{ELECTION_ID}/candidates \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Andrea C. Cooke",
    "filing_status": "qualified",
    "is_incumbent": false,
    "links": [
      {"link_type": "campaign", "url": "https://www.cookeforcommission.com", "label": "Campaign Website"}
    ]
  }'
```

## Example: Enrich Election Metadata

```bash
curl -X PATCH http://localhost:8000/api/v1/elections/{ELECTION_ID} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Special election to fill the unexpired term of Seth Clark, resigned, for Macon-Bibb County Commission District 5.",
    "purpose": "Fill vacant Commission District 5 seat",
    "eligibility_description": "Registered voters in Macon-Bibb County Commission District 5",
    "registration_deadline": "2026-02-16",
    "qualifying_start": "2026-02-11T12:00:00-05:00",
    "qualifying_end": "2026-02-13T17:30:00-05:00"
  }'
```

## Running Tests

```bash
# Unit + integration tests
uv run pytest tests/unit/ tests/integration/ -v

# E2E tests (requires PostGIS)
DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api \
  JWT_SECRET_KEY=test-secret-key-minimum-32-characters \
  ELECTION_REFRESH_ENABLED=false \
  uv run pytest tests/e2e/ -v

# Lint
uv run ruff check . && uv run ruff format --check .
```

## New Files

### Models
- `src/voter_api/models/candidate.py` — Candidate + CandidateLink ORM models

### Schemas
- `src/voter_api/schemas/candidate.py` — Request/response Pydantic schemas

### Services
- `src/voter_api/services/candidate_service.py` — Candidate CRUD + list logic

### API Routes
- `src/voter_api/api/v1/candidates.py` — Candidate endpoints (new router)

### Migrations
- `alembic/versions/037_add_candidates.py` — Creates candidates + candidate_links tables
- `alembic/versions/038_add_election_metadata.py` — Adds metadata columns to elections table

### Modified Files
- `src/voter_api/models/election.py` — New nullable columns + candidates relationship
- `src/voter_api/schemas/election.py` — Extended ElectionUpdateRequest + response schemas
- `src/voter_api/api/v1/elections.py` — New milestone date filter parameters
- `src/voter_api/main.py` — Register candidates router

### Tests
- `tests/unit/test_candidate_schemas.py` — Schema validation tests
- `tests/integration/test_candidate_service.py` — Service layer tests
- `tests/integration/test_candidate_api.py` — API route tests
- `tests/e2e/test_smoke.py` — New TestCandidates class + updated TestElections
