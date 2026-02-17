# Implementation Plan: Voter History Ingestion

**Branch**: `006-voter-history` | **Date**: 2026-02-17 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/006-voter-history/spec.md`

## Summary

Import and query voter participation history from GA Secretary of State CSV files. Each record links a voter registration number to an election event, tracking ballot style, voting method flags (absentee/provisional/supplemental), and party. The system supports re-import (file replacement), auto-creates missing election records, enriches the voter detail endpoint with a participation summary, and provides aggregate participation statistics per election.

## Technical Context

**Language/Version**: Python 3.13 (see `.python-version`)
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x (async) + GeoAlchemy2, Pydantic v2, Pandas, Typer, Loguru, Alembic
**Storage**: PostgreSQL 15+ / PostGIS 3.x (existing `voters`, `elections`, `import_jobs` tables; new `voter_history` table)
**Testing**: pytest with pytest-asyncio, pytest-cov (90% coverage threshold)
**Target Platform**: Linux server (piku deployment)
**Project Type**: single (API + CLI, no frontend)
**Performance Goals**: Import 50,000+ records in <5 minutes (SC-001); query voter history in <2 seconds (SC-006); aggregate stats in <3 seconds for 50k records (SC-007)
**Constraints**: Batch processing to avoid excessive memory; atomic re-import (old records removed only after new import succeeds)
**Scale/Scope**: Files with 100,000+ records across multiple counties and elections

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle                          | Status | Notes                                                                                                       |
| ---------------------------------- | ------ | ----------------------------------------------------------------------------------------------------------- |
| I. Library-First Architecture      | PASS   | New `lib/voter_history/` library for CSV parsing; service layer orchestrates                                 |
| II. Code Quality (NON-NEGOTIABLE)  | PASS   | Type hints, Google-style docstrings, ruff compliance on all new code                                        |
| III. Testing Discipline (NON-NEG.) | PASS   | Unit tests for parser lib, integration tests for import service + API, contract tests for OpenAPI           |
| IV. Twelve-Factor Configuration    | PASS   | No new config required beyond existing DATABASE_URL and JWT settings                                        |
| V. Developer Experience            | PASS   | New CLI command `import voter-history`; follows existing Typer patterns                                     |
| VI. API Documentation              | PASS   | All endpoints documented via Pydantic schemas + OpenAPI auto-generation                                     |
| VII. Security by Design            | PASS   | Import restricted to admin role; queries restricted to authenticated users; Pydantic validation on all inputs |
| VIII. CI/CD & Version Control      | PASS   | Conventional Commits; feature branch; Alembic migration for schema changes                                  |

No violations. All principles satisfied by design.

**Post-Design Re-evaluation (Phase 1 complete)**: All gates still PASS. The library-first parser (`lib/voter_history/`), OpenAPI contract (`contracts/openapi.yaml`), data model (`data-model.md`), and security boundaries (admin-only import, authenticated queries) satisfy all eight constitutional principles. No complexity violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/006-voter-history/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── openapi.yaml     # OpenAPI 3.1 spec for voter history endpoints
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/voter_api/
├── models/
│   └── voter_history.py          # VoterHistory ORM model
├── schemas/
│   └── voter_history.py          # Pydantic v2 request/response schemas
├── api/v1/
│   └── voter_history.py          # FastAPI route handlers
├── services/
│   └── voter_history_service.py  # Business logic orchestration
├── lib/
│   └── voter_history/            # Standalone CSV parsing library
│       ├── __init__.py           # Public API exports
│       └── parser.py             # GA SoS 9-column CSV parser
└── cli/
    └── voter_history_cmd.py      # Typer CLI commands

# Modified existing files:
├── models/election.py            # Add creation_method column
├── models/import_job.py          # Add records_skipped, records_unmatched columns
├── schemas/voter.py              # Add ParticipationSummary to VoterDetailResponse
├── services/voter_service.py     # Enrich voter detail with participation summary
├── api/router.py                 # Register voter_history router
└── cli/app.py                    # Register voter_history_cmd

alembic/versions/
└── 022_voter_history.py          # Migration: voter_history table + election.creation_method + import_job counters

tests/
├── unit/
│   ├── lib/test_voter_history/   # Parser unit tests
│   └── test_schemas/test_voter_history_schemas.py
├── integration/
│   ├── test_voter_history_import.py
│   ├── test_voter_history_api.py
│   └── test_voter_history_cli.py
└── contract/
    └── test_voter_history_contract.py
```

**Structure Decision**: Single-project layout following the existing library-first architecture. The new `lib/voter_history/` parser is independently testable. Service layer orchestrates the parser, ORM models, and election auto-creation. API endpoints nest under existing URL patterns (`/api/v1/imports/voter-history`, `/api/v1/voters/{reg_num}/history`, `/api/v1/elections/{id}/participation`).

## Complexity Tracking

No complexity violations to justify. The design follows existing patterns with no additional abstractions beyond the standard library-first structure.
