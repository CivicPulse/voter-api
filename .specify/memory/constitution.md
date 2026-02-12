<!--
  Sync Impact Report
  ==================
  Version change: N/A (initial) → 1.0.0
  Bump rationale: MAJOR — initial constitution ratification

  Added principles:
    - I. Library-First Architecture
    - II. Code Quality (NON-NEGOTIABLE)
    - III. Testing Discipline (NON-NEGOTIABLE)
    - IV. Twelve-Factor Configuration
    - V. Developer Experience
    - VI. API Documentation
    - VII. Security by Design
    - VIII. CI/CD & Version Control

  Added sections:
    - Technology Stack & Tooling
    - Development Workflow & Quality Gates
    - Governance

  Removed sections: none (initial)

  Templates requiring updates:
    - .specify/templates/plan-template.md — Constitution Check
      section is generic placeholder ✅ (compatible, no update needed)
    - .specify/templates/spec-template.md — Requirements section
      compatible ✅ (no update needed)
    - .specify/templates/tasks-template.md — Phase structure
      compatible ✅ (no update needed; testing phase aligns with
      Principle III)

  Follow-up TODOs: none
-->

# voter-api Constitution

## Core Principles

### I. Library-First Architecture

All features MUST be implemented as standalone libraries before
integration into the application layer.

- Libraries MUST be self-contained, independently importable, and
  independently testable.
- Each library MUST have a clear, singular purpose — no
  organizational-only packages.
- The project MUST be distributable as a package on PyPI.
- Public API surfaces MUST be explicitly defined via `__init__.py`
  exports.

**Rationale**: Library-first forces clean boundaries, enables reuse
across projects, and ensures each component can be validated in
isolation before composition.

### II. Code Quality (NON-NEGOTIABLE)

All production and test code MUST meet the following standards
without exception:

- All functions, classes, and modules MUST include type hints.
- All public functions, classes, and modules MUST include
  docstrings (Google-style preferred).
- Code MUST include inline comments where logic is non-obvious.
- All code MUST pass `ruff check` and `ruff format` with zero
  violations before merge.
- Linting and formatting MUST be run before every commit.

**Rationale**: Consistent type hints enable static analysis and
IDE support. Docstrings and comments reduce onboarding friction.
Ruff enforcement eliminates style debates and catches errors early.

### III. Testing Discipline (NON-NEGOTIABLE)

Test coverage MUST be 90% or higher across the entire codebase.

- `pytest` MUST be used as the test framework.
- Tests MUST be organized into `unit/`, `integration/`, and
  `contract/` directories.
- All new code MUST include corresponding tests before merge.
- Coverage MUST be measured and reported on every CI run.
- Coverage drops below 90% MUST block the merge.

**Rationale**: High test coverage catches regressions early and
provides confidence for refactoring. The 90% threshold balances
thoroughness with pragmatism.

### IV. Twelve-Factor Configuration

The project MUST follow the
[12 Factor App](https://12factor.net/) methodology for
configuration management.

- Configuration MUST be stored in environment variables, never
  hardcoded.
- Secrets MUST NOT appear in source code, config files, or
  version control.
- A `.env.example` file MUST document all required environment
  variables with placeholder values.
- Pydantic Settings MUST be used for configuration validation
  and type-safe access.

**Rationale**: Environment-based configuration enables identical
code to run across development, staging, and production without
modification, and prevents secret leakage.

### V. Developer Experience

The project MUST prioritize ease of local development and
operation.

- `uv` MUST be used for all Python operations: running commands
  (`uv run`), adding packages (`uv add`), and environment
  management. System Python MUST NOT be used directly.
- The project MUST provide a CLI (via `typer`) for common
  operations including: database migrations, running tests,
  starting the development server, and seeding data.
- The project MUST be containerized via Docker with a
  `Dockerfile` and `docker-compose.yml`.
- The project MUST be equally easy to run locally without Docker
  using `uv` alone.
- Setup from clone to running server MUST require no more than
  3 commands.

**Rationale**: Low-friction developer experience accelerates
onboarding, reduces "works on my machine" issues, and encourages
contribution.

### VI. API Documentation

The API MUST use OpenAPI standards for documentation.

- All API endpoints MUST be documented via OpenAPI/Swagger
  specifications generated from FastAPI route definitions.
- Request and response models MUST be defined as Pydantic
  schemas that auto-generate OpenAPI documentation.
- The interactive Swagger UI (`/docs`) and ReDoc (`/redoc`)
  endpoints MUST be available in development and staging
  environments.
- API versioning strategy MUST be documented and enforced.

**Rationale**: OpenAPI-first documentation ensures API consumers
have accurate, always-up-to-date references and enables
automated client generation.

### VII. Security by Design

Security MUST be a first-class concern, not an afterthought.

- All user input MUST be validated at the boundary using
  Pydantic models before processing.
- Authentication MUST be implemented and enforced on all
  protected endpoints.
- Authorization MUST be role-based and checked on every
  protected request.
- SQL injection MUST be prevented by using SQLAlchemy ORM/Core
  exclusively — no raw SQL string interpolation.
- CORS, rate limiting, and request size limits MUST be
  configured.
- Security headers MUST be set on all responses.
- Dependency vulnerabilities MUST be scanned in CI.

**Rationale**: Voter data is sensitive. Defense-in-depth ensures
no single failure compromises the system.

### VIII. CI/CD & Version Control

The project MUST use GitHub Actions for continuous integration
and deployment, and Conventional Commits for version control
history.

- All commit messages MUST follow the
  [Conventional Commits](https://www.conventionalcommits.org/)
  specification.
- GitHub Actions MUST run on every push and pull request:
  linting (`ruff`), type checking, tests (`pytest`), and
  coverage reporting.
- Merges to `main` MUST require passing CI and code review.
- Releases MUST be tagged with semantic versions derived from
  commit history.

**Rationale**: Automated CI catches issues before merge.
Conventional Commits enable automated changelogs and semantic
version bumps. Branch protection prevents accidental breakage.

## Technology Stack & Tooling

The following technology choices are binding for all
contributors:

| Category | Tool | Constraint |
|---|---|---|
| Language | Python 3.13+ | Minimum version |
| Framework | FastAPI | Async-first web framework |
| ORM | SQLAlchemy 2.x + GeoAlchemy2 | Async session support required |
| Database | PostgreSQL + PostGIS | Geospatial queries |
| Migrations | Alembic | All schema changes via migrations |
| Validation | Pydantic v2 | All data boundaries |
| CLI | Typer | All management commands |
| Logging | Loguru | Structured logging only |
| Templating | Jinja2 | Where templating is needed |
| Data | Pandas | Data processing pipelines |
| Package Manager | uv | Replaces pip/poetry/pipenv |
| Linter/Formatter | Ruff | Single tool for both |
| Testing | pytest | With pytest-cov, pytest-asyncio |
| Containers | Docker + docker-compose | Multi-service orchestration |
| CI/CD | GitHub Actions | All automation pipelines |

Additions or replacements to this stack MUST be proposed as a
constitution amendment.

## Development Workflow & Quality Gates

### Branch Strategy

- All work MUST be done on feature branches, never directly on
  `main`.
- Branch names MUST follow the pattern:
  `<type>/<short-description>` (e.g., `feat/voter-lookup`).
- Pull requests MUST reference the related issue or spec.

### Commit Cadence

Work MUST be committed to git after completing each task, user
story, or implementation phase. Large uncommitted changesets MUST
be avoided. This ensures incremental progress is preserved and
enables effective code review.

### Pre-Commit Quality Gates

Before any commit, the following MUST pass:

1. `ruff check .` — zero linting violations
2. `ruff format --check .` — zero formatting violations
3. `uv run pytest` — all tests passing
4. Coverage >= 90%

### Code Review Standards

- All pull requests MUST receive at least one approving review.
- Reviewers MUST verify compliance with this constitution.
- Complexity MUST be justified — default to the simplest
  solution.

### Definition of Done

A feature is complete when:

1. All acceptance criteria from the spec are met.
2. All quality gates pass.
3. Documentation (docstrings, OpenAPI, README if applicable)
   is updated.
4. No `TODO` or `FIXME` markers remain in the delivered code.

## Governance

This constitution is the supreme governing document for the
voter-api project. It supersedes all other practices,
conventions, or informal agreements.

### Amendment Procedure

1. Propose changes via a pull request modifying this file.
2. Amendments MUST include rationale and impact analysis.
3. All active contributors MUST be notified of proposed changes.
4. Amendments require approval before merge.
5. Upon merge, dependent templates and documentation MUST be
   updated within the same PR or a follow-up PR within 48 hours.

### Versioning Policy

This constitution follows semantic versioning:

- **MAJOR**: Principle removal, redefinition, or
  backward-incompatible governance change.
- **MINOR**: New principle or section added, or existing
  guidance materially expanded.
- **PATCH**: Clarifications, typo fixes, non-semantic
  refinements.

### Compliance Review

- Every pull request review MUST include a constitution
  compliance check.
- Quarterly reviews SHOULD assess whether principles remain
  relevant and sufficient.
- Non-compliance discovered post-merge MUST be addressed in the
  next sprint.

**Version**: 1.0.0 | **Ratified**: 2026-02-11 | **Last Amended**: 2026-02-11
