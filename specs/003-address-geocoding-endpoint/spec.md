# Feature Specification: Single-Address Geocoding Endpoint

**Feature Branch**: `003-address-geocoding-endpoint`
**Created**: 2026-02-13
**Status**: Draft
**Input**: User description: "Expose a public API endpoint that accepts a street address string and returns geographic coordinates with confidence score"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Geocode a Single Address (Priority: P1)

As an authenticated API consumer, I want to submit a street address and receive geographic coordinates with a confidence score so that I can determine the location of any arbitrary address without needing voter records in the database.

**Why this priority**: This is the core value of the feature. Without the ability to geocode a single address on demand, none of the other stories are relevant. Currently geocoding is only available as an internal batch operation on voter records — this story makes geocoding a first-class, user-facing capability.

**Independent Test**: Can be fully tested by sending a POST request with a valid address string and verifying the response contains latitude, longitude, confidence score, matched address, and provider name.

**Acceptance Scenarios**:

1. **Given** an authenticated user with any role (viewer, analyst, or admin), **When** they submit a valid street address (e.g., "100 Peachtree St NW, Atlanta, GA 30303"), **Then** they receive a response containing latitude, longitude, confidence score, the matched/normalized address, and the geocoding provider name.
2. **Given** an authenticated user, **When** they submit a valid address that the provider successfully matches, **Then** the response status is HTTP 200 and the coordinates are non-null.
3. **Given** an unauthenticated request (no JWT or invalid JWT), **When** a geocoding request is submitted, **Then** the system returns HTTP 401 Unauthorized.

---

### User Story 2 - Cached Results Returned Instantly (Priority: P2)

As an API consumer, I want repeat geocoding requests for the same address to return results instantly from the cache so that I get fast responses and the system avoids unnecessary calls to external geocoding providers.

**Why this priority**: Caching is essential for performance and cost control. The geocoding provider (Census Bureau) has rate limits, and many applications will geocode the same addresses repeatedly. This story ensures the system leverages the existing cache infrastructure.

**Independent Test**: Can be tested by geocoding an address, then submitting the same address again and verifying the second response is significantly faster and that no additional external provider call was made.

**Acceptance Scenarios**:

1. **Given** an address has been previously geocoded (result exists in the cache), **When** the same address is submitted again, **Then** the cached result is returned without calling the external geocoding provider.
2. **Given** an address has never been geocoded, **When** it is submitted for the first time, **Then** the result from the external provider is stored in the cache for future lookups.

---

### User Story 3 - Graceful Geocoding Failure Handling (Priority: P3)

As an API consumer, I want to receive clear, actionable error responses when geocoding fails so that I can handle failures programmatically and communicate issues to my users.

**Why this priority**: Robust error handling ensures the API is production-ready. Without clear error responses, consumers cannot distinguish between bad input, unmatchable addresses, and provider outages, making the API unreliable for integration.

**Independent Test**: Can be tested by submitting various invalid inputs (empty string, unmatchable address, etc.) and verifying each returns an appropriate HTTP status code and descriptive error message.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they submit an empty or whitespace-only address string, **Then** the system returns HTTP 422 with a validation error explaining the address field is required and must not be blank.
2. **Given** an authenticated user, **When** they submit an address that the geocoding provider cannot match to a location, **Then** the system returns HTTP 200 with null coordinates and a message indicating the address could not be geocoded.
3. **Given** an authenticated user, **When** the external geocoding provider is unavailable or times out, **Then** the system returns HTTP 502 with a message indicating a temporary upstream failure and suggesting a retry.

---

### Edge Cases

- What happens when the address string contains only whitespace or special characters? The system returns HTTP 422 with a validation error.
- What happens when the geocoding provider returns a match with very low confidence? The system returns the result as-is with the low confidence score — it is the consumer's responsibility to interpret confidence thresholds.
- What happens when the geocoding provider returns multiple candidate matches? The system returns the top/best match (highest confidence), consistent with existing batch geocoding behavior.
- What happens when the address is extremely long (thousands of characters)? The system rejects it with HTTP 422 if it exceeds a reasonable length limit.
- What happens when the same address is submitted concurrently by multiple users? Both requests may call the provider, and both will attempt to cache the result. The second cache write is idempotent and does not cause errors.
- What happens when the JWT token has expired? The system returns HTTP 401 Unauthorized, consistent with all other authenticated endpoints.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a single freeform address string as input (e.g., "123 Main St, Atlanta, GA 30303").
- **FR-002**: System MUST return latitude, longitude, confidence score, matched/normalized address, and provider name in the response when geocoding succeeds.
- **FR-003**: System MUST require valid JWT authentication for all geocoding requests. Any authenticated role (viewer, analyst, admin) is permitted — no role-based restriction.
- **FR-004**: System MUST use the existing geocoder provider infrastructure to perform address geocoding, with Census as the default provider.
- **FR-005**: System MUST check the existing geocoder cache before calling the external provider. If a cached result exists for the normalized address and provider, it MUST be returned without making an external call.
- **FR-006**: System MUST store new geocoding results in the cache after a successful provider call so that future lookups for the same address are served from cache.
- **FR-007**: System MUST return HTTP 422 with a descriptive validation error when the submitted address is empty, whitespace-only, or exceeds a reasonable length.
- **FR-008**: System MUST return HTTP 200 with null coordinates and an explanatory message when the provider cannot match the submitted address.
- **FR-009**: System MUST return HTTP 502 with a descriptive error message when the external geocoding provider is unreachable or returns an unexpected error.
- **FR-010**: System MUST respect the existing global rate limiting (60 requests per minute per IP) applied to all API endpoints.

### Key Entities

- **Geocoder Cache** *(existing)*: Stores previously geocoded results keyed by provider name and normalized address. This feature reuses the existing cache — no new database entities are introduced.

## Assumptions

- The existing geocoder cache table and cache lookup/store functions are sufficient for this feature without modification.
- The Census geocoder provider is available and operational. If additional providers are added in the future, this endpoint will automatically support them via the existing provider registry.
- Address normalization (if any) is handled consistently between this endpoint and the existing batch geocoding pipeline, ensuring cache hits across both paths.
- The existing global rate limit (60 req/min per IP) provides sufficient protection against abuse. Per-endpoint rate limiting is not required at this time.
- This endpoint is for single-address geocoding only. Batch geocoding of arbitrary addresses (not voter records) is out of scope and can be added in a future iteration if needed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Authenticated users receive geocoding results within 5 seconds for uncached addresses (dependent on external provider response time).
- **SC-002**: Cached addresses return results in under 500 milliseconds.
- **SC-003**: 100% of geocoding requests from authenticated users either succeed with coordinates or return a clear, documented error response (no silent failures or ambiguous errors).
- **SC-004**: The endpoint handles at least 60 concurrent requests per minute without degradation, consistent with the global rate limit.
