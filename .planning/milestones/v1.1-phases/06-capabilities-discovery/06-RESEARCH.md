# Phase 6: Capabilities Discovery - Research

**Researched:** 2026-03-16
**Domain:** FastAPI route ordering, Pydantic response models, static endpoint patterns
**Confidence:** HIGH

## Summary

Phase 6 adds a single static endpoint (`GET /api/v1/elections/capabilities`) to the existing elections router. The endpoint returns a hardcoded JSON response describing which filter parameters the elections API supports. No database queries, no new dependencies, no migrations.

The primary technical risk is FastAPI route ordering: the new `/capabilities` path must be registered before the existing `/{election_id}` path parameter route (line 171 of `elections.py`), or FastAPI will try to parse "capabilities" as a UUID and return a 422 validation error. This is a well-documented FastAPI behavior.

**Primary recommendation:** Add the `/capabilities` route handler immediately after the `list_elections` handler (after line 92) and before any `/{election_id}` routes. Define a `CapabilitiesResponse` Pydantic model in `schemas/election.py`. Set `Cache-Control: public, max-age=3600` on the response.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Response shape: Minimal response with version field, flat list of filter names, endpoint flags. Ship all 5 filters (`q`, `race_category`, `county`, `district`, `election_date`) + `filter_options: true` with `version: 1` from day one.
- Response schema: Define a `CapabilitiesResponse` Pydantic model in `schemas/election.py` with `response_model=` on the decorator.
- Auth and caching: Public endpoint (no auth). `Cache-Control: public, max-age=3600`.
- Test coverage: Unit test for response shape, integration test for 200 + expected JSON, integration test proving `/capabilities` isn't swallowed by `/{election_id}`, parameterized regression test for existing endpoints. E2E deferred to Phase 8.

### Claude's Discretion
- Exact placement of the capabilities route within `elections.py` (before `/{election_id}` is the only requirement)
- Whether to define the supported filters list as a module-level constant or inline
- Test file organization (new file vs. added to existing election test file)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DISC-01 | API consumer can discover which filter parameters are currently supported via a capabilities endpoint (`GET /elections/capabilities`) | Static endpoint returning `CapabilitiesResponse` Pydantic model with `supported_filters` list and `endpoints` dict. Contract defined in `docs/election-search-api-report.md` Section 1. |
| INTG-01 | New endpoints use correct FastAPI route ordering (registered before `/{election_id}` catch-all) | Route must be declared before line 171 in `elections.py`. FastAPI matches routes in declaration order; path params consume all strings including "capabilities". |

</phase_requirements>

## Standard Stack

No new libraries needed. This phase uses only existing project dependencies.

### Core (existing)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | existing | Route handler, `Response` object for headers | Already in use |
| Pydantic v2 | existing | `CapabilitiesResponse` model | All endpoints use `response_model=` |

No new packages to install.

## Architecture Patterns

### Recommended Changes
```
src/voter_api/
├── schemas/
│   └── election.py          # ADD: CapabilitiesResponse model
└── api/v1/
    └── elections.py          # ADD: /capabilities route handler
tests/
├── unit/
│   └── test_schemas/
│       └── test_capabilities_schema.py  # ADD: unit test for response shape
└── integration/
    └── test_api/
        └── test_capabilities_api.py     # ADD: integration tests
```

### Pattern 1: Static Endpoint with Cache-Control
**What:** A route handler that returns a hardcoded response with cache headers, no DB interaction.
**When to use:** Discovery/metadata endpoints that don't change between requests.
**Example:**
```python
# Source: existing pattern in elections.py (get_election_results, line 266-268)
@elections_router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities(response: Response) -> CapabilitiesResponse:
    """Discover supported filter parameters and endpoints. Public endpoint."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return CapabilitiesResponse(
        supported_filters=["q", "race_category", "county", "district", "election_date"],
        endpoints={"filter_options": True},
    )
```

### Pattern 2: Pydantic Response Model
**What:** Define a named Pydantic model so the response appears in OpenAPI docs.
**When to use:** Every endpoint in this codebase uses `response_model=`.
**Example:**
```python
# Source: follows ElectionResultsResponse pattern in schemas/election.py
class CapabilitiesResponse(BaseModel):
    """Capabilities discovery response for the elections API."""
    supported_filters: list[str] = Field(
        description="Filter parameter names accepted by GET /elections"
    )
    endpoints: dict[str, bool] = Field(
        description="Available sub-endpoints and their status"
    )
```

### Pattern 3: Integration Test with make_test_app
**What:** Mount just the elections_router in a minimal FastAPI app with mocked dependencies.
**When to use:** All integration tests in `tests/integration/test_api/`.
**Example:**
```python
# Source: tests/integration/test_api/conftest.py pattern
from tests.integration.test_api.conftest import make_test_app

@pytest.fixture
def app(mock_session):
    return make_test_app(elections_router, mock_session)
```

### Anti-Patterns to Avoid
- **Declaring `/capabilities` after `/{election_id}`:** FastAPI will never reach the capabilities handler because `{election_id}` matches all strings. This is the single most important thing to get right.
- **Making the endpoint async with DB access:** The response is static. No session dependency needed.
- **Omitting `response_model=`:** Every endpoint in this codebase declares one. Skipping it breaks the OpenAPI docs convention.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Response serialization | Custom dict construction | Pydantic `CapabilitiesResponse` model | Consistent with codebase, auto-generates OpenAPI schema |
| Route ordering | Manual path matching logic | FastAPI declaration order | FastAPI handles this natively; just declare static routes first |

## Common Pitfalls

### Pitfall 1: Route Shadowing by Path Parameters
**What goes wrong:** `/{election_id}` consumes the string "capabilities" and FastAPI tries to parse it as UUID, returning 422.
**Why it happens:** FastAPI matches routes in declaration order. Path parameter routes match any string.
**How to avoid:** Declare `/capabilities` route before any `/{election_id}` route in the same router file.
**Warning signs:** `422 Unprocessable Entity` with "value is not a valid uuid" when hitting `/capabilities`.

### Pitfall 2: Forgetting Cache-Control Header
**What goes wrong:** Clients re-fetch on every page load unnecessarily.
**Why it happens:** FastAPI doesn't set caching headers by default.
**How to avoid:** Inject `Response` parameter and set `response.headers["Cache-Control"]` (existing pattern at line 268 of elections.py).

### Pitfall 3: Response Shape Drift from Contract
**What goes wrong:** The capabilities response doesn't match what `docs/election-search-api-report.md` Section 1 specifies.
**Why it happens:** Implementing from memory instead of the contract document.
**How to avoid:** The exact response is defined in the report: `{"supported_filters": ["q", "race_category", "county", "district", "election_date"], "endpoints": {"filter_options": true}}`. Tests should assert this exact shape.

## Code Examples

### Capabilities Response (from contract)
```json
// Source: docs/election-search-api-report.md Section 1
{
  "supported_filters": ["q", "race_category", "county", "district", "election_date"],
  "endpoints": {
    "filter_options": true
  }
}
```

### Cache-Control Pattern (existing codebase)
```python
# Source: src/voter_api/api/v1/elections.py lines 266-268
cache_ttl = 60 if result.status == "active" else 86400
response.headers["Cache-Control"] = f"public, max-age={cache_ttl}"
```

### Integration Test Pattern (existing codebase)
```python
# Source: tests/integration/test_api/test_election_api.py pattern
@pytest.fixture
def app(mock_session):
    return make_test_app(elections_router, mock_session)

@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
    ) as c:
        yield c
```

## State of the Art

No changes needed. This phase uses stable, well-understood patterns:

| Aspect | Approach | Status |
|--------|----------|--------|
| FastAPI route ordering | Declaration order determines match priority | Stable since FastAPI 0.1 |
| Pydantic response_model | `response_model=` on decorator | Standard practice |
| Cache-Control headers | Set on Response object | HTTP standard, already used in codebase |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (with pytest-asyncio) |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/unit/test_schemas/test_capabilities_schema.py tests/integration/test_api/test_capabilities_api.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DISC-01 | `/capabilities` returns correct JSON shape | unit | `uv run pytest tests/unit/test_schemas/test_capabilities_schema.py -x` | No -- Wave 0 |
| DISC-01 | `/capabilities` returns 200 with expected body | integration | `uv run pytest tests/integration/test_api/test_capabilities_api.py::test_capabilities_returns_200 -x` | No -- Wave 0 |
| INTG-01 | `/capabilities` not swallowed by `/{election_id}` | integration | `uv run pytest tests/integration/test_api/test_capabilities_api.py::test_capabilities_not_shadowed -x` | No -- Wave 0 |
| INTG-01 | Existing election endpoints still work | integration | `uv run pytest tests/integration/test_api/test_capabilities_api.py::test_existing_endpoints_unchanged -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/test_schemas/test_capabilities_schema.py tests/integration/test_api/test_capabilities_api.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_schemas/test_capabilities_schema.py` -- covers DISC-01 (schema shape validation)
- [ ] `tests/integration/test_api/test_capabilities_api.py` -- covers DISC-01, INTG-01 (endpoint behavior + route ordering)

## Open Questions

None. This phase is fully specified by the CONTEXT.md decisions and the contract document.

## Sources

### Primary (HIGH confidence)
- `src/voter_api/api/v1/elections.py` -- current router with `/{election_id}` at line 171
- `src/voter_api/schemas/election.py` -- existing response model patterns
- `docs/election-search-api-report.md` Section 1 -- exact capabilities response contract
- `tests/integration/test_api/conftest.py` -- `make_test_app` helper pattern
- `tests/integration/test_api/test_election_api.py` -- existing election test patterns

### Secondary (MEDIUM confidence)
- FastAPI documentation on route ordering (path operations are evaluated in declaration order)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all existing patterns
- Architecture: HIGH -- single static endpoint following established codebase conventions
- Pitfalls: HIGH -- route shadowing is well-documented and the CONTEXT.md already identifies it

**Research date:** 2026-03-16
**Valid until:** 2026-04-16 (stable patterns, no version sensitivity)
