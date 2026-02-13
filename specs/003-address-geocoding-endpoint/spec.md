# Feature Specification: Single-Address Geocoding Endpoint

**Feature Branch**: `003-address-geocoding-endpoint`
**Created**: 2026-02-13
**Status**: Draft
**Input**: User description: "Expose a public API endpoint that accepts a street address string and returns geographic coordinates with confidence score"

## Clarifications

### Session 2026-02-13

- Q: Should the endpoint allow consumers to choose a geocoding provider, or always use the system default? → A: Provider-agnostic. The endpoint abstracts away provider selection entirely — no provider parameter. The system internally decides the best provider and returns the most accurate result. The consumer only sends an address and receives coordinates.
- Q: Should freeform address input be normalized before cache lookup, or used as-is? → A: Normalize before cache lookup — uppercase, trim whitespace, collapse multiple spaces. This ensures consistent cache hits regardless of consumer input formatting.
- Q: What should the maximum address length be? → A: 500 characters.
- Q: Where should address verification/autocomplete suggestions come from? → A: Initially from the existing geocoder cache (prefix-match against previously geocoded addresses). Third-party API (e.g., Google Places) will be added later. Additionally, local validation logic MUST check whether the address is well-formed (has all required fields) and normalize abbreviations (road→RD, street→ST, etc.) using existing USPS Pub 28 rules.
- Q: Should the verification endpoint require JWT authentication or be public for autocomplete use? → A: Require JWT authentication, same as the geocoding endpoint. Prevents abuse and data exposure from the voter address cache.
- Q: What is the maximum acceptable response time for the verification endpoint? → A: 500 milliseconds.
- Q: How many address suggestions should the verification endpoint return at most? → A: 10.
- Q: What is the minimum number of characters required before the verification endpoint returns suggestions? → A: 5 characters.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Geocode a Single Address (Priority: P1)

As an authenticated API consumer, I want to submit a street address and receive geographic coordinates with a confidence score so that I can determine the location of any arbitrary address without needing voter records in the database.

**Why this priority**: This is the core value of the feature. Without the ability to geocode a single address on demand, none of the other stories are relevant. Currently geocoding is only available as an internal batch operation on voter records — this story makes geocoding a first-class, user-facing capability.

**Independent Test**: Can be fully tested by sending a POST request with a valid address string and verifying the response contains latitude, longitude, confidence score, and matched address.

**Acceptance Scenarios**:

1. **Given** an authenticated user with any role (viewer, analyst, or admin), **When** they submit a valid street address (e.g., "100 Peachtree St NW, Atlanta, GA 30303"), **Then** they receive a response containing latitude, longitude, confidence score, and the matched/normalized address.
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

### User Story 4 - Verify and Autocomplete an Address (Priority: P2)

As an API consumer, I want to submit a partial or malformed address and receive ranked suggestions of matching addresses so that I can verify address correctness, present autocomplete options to end users as they type, and correct malformed input before geocoding.

**Why this priority**: Address verification complements the geocoding endpoint and enables a better user experience. Developers building forms can offer autocomplete suggestions, and programmatic consumers can validate and correct addresses before submitting them for geocoding.

**Independent Test**: Can be fully tested by sending a partial address string (e.g., "100 Peach") and verifying the response contains a ranked list of matching address suggestions. Can also be tested by sending a malformed address (e.g., missing ZIP code) and verifying the response includes validation feedback indicating which fields are missing or malformed.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they submit a partial address string (e.g., "100 Peachtree"), **Then** they receive a ranked list of matching address suggestions from previously geocoded addresses in the cache.
2. **Given** an authenticated user, **When** they submit a malformed address (e.g., "100 main street" with unabbreviated street type and no city/state/ZIP), **Then** the response includes the normalized form ("100 MAIN ST") and indicates which address components are missing.
3. **Given** an authenticated user, **When** they submit an address that has no matches in the cache, **Then** the response returns an empty suggestions list along with any local validation feedback.
4. **Given** an authenticated user, **When** they submit a well-formed complete address, **Then** the response confirms the address is well-formed, returns the normalized version, and includes any matching cached suggestions.

---

### Edge Cases

- What happens when the address string contains only whitespace or special characters? The system returns HTTP 422 with a validation error.
- What happens when the geocoding provider returns a match with very low confidence? The system returns the result as-is with the low confidence score — it is the consumer's responsibility to interpret confidence thresholds.
- What happens when the geocoding provider returns multiple candidate matches? The system returns the top/best match (highest confidence), consistent with existing batch geocoding behavior.
- What happens when the address is extremely long (thousands of characters)? The system rejects it with HTTP 422 if it exceeds 500 characters.
- What happens when the same address is submitted concurrently by multiple users? Both requests may call the provider, and both will attempt to cache the result. The second cache write is idempotent and does not cause errors.
- What happens when the JWT token has expired? The system returns HTTP 401 Unauthorized, consistent with all other authenticated endpoints.
- What happens when a verification request contains fewer than 5 characters? The system returns only local validation feedback with an empty suggestions list.
- What happens when a verification request contains only a street number with no street name? The system returns validation feedback indicating the street name is required, with no suggestions.
- What happens when the cache contains thousands of potential matches for a very short prefix? The system returns only the top 10 ranked results.
- What happens when the cache is empty (no previously geocoded addresses)? The verification endpoint returns only local validation feedback with an empty suggestions list.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a single freeform address string as input (e.g., "123 Main St, Atlanta, GA 30303").
- **FR-002**: System MUST return latitude, longitude, confidence score, and matched/normalized address in the response when geocoding succeeds. The provider used is an internal implementation detail and MUST NOT be exposed to the consumer.
- **FR-003**: System MUST require valid JWT authentication for all geocoding requests. Any authenticated role (viewer, analyst, admin) is permitted — no role-based restriction.
- **FR-004**: System MUST use the existing geocoder provider infrastructure to perform address geocoding. The provider is selected internally by the system — no consumer-facing provider parameter is exposed.
- **FR-005**: System MUST normalize the freeform address input (uppercase, trim whitespace, collapse multiple spaces) before cache lookup and provider calls. If a cached result exists for the normalized address, it MUST be returned without making an external call.
- **FR-006**: System MUST store new geocoding results in the cache after a successful provider call so that future lookups for the same address are served from cache.
- **FR-007**: System MUST return HTTP 422 with a descriptive validation error when the submitted address is empty, whitespace-only, or exceeds 500 characters.
- **FR-008**: System MUST return HTTP 200 with null coordinates and an explanatory message when the provider cannot match the submitted address.
- **FR-009**: System MUST return HTTP 502 with a descriptive error message when the external geocoding provider is unreachable or returns an unexpected error.
- **FR-010**: System MUST respect the existing global rate limiting (60 requests per minute per IP) applied to all API endpoints.
- **FR-011**: System MUST expose a separate address verification endpoint that accepts a partial or malformed freeform address string and returns ranked address suggestions.
- **FR-012**: The verification endpoint MUST perform local validation to determine whether the submitted address is well-formed — checking for required components (street number, street name, city, state, ZIP) and reporting which are present, missing, or malformed.
- **FR-013**: The verification endpoint MUST normalize the submitted address using existing USPS Publication 28 rules (e.g., STREET→ST, ROAD→RD, NORTH→N) and return the normalized form in the response.
- **FR-014**: The verification endpoint MUST search the existing geocoder cache for addresses matching the submitted input and return up to 10 ranked suggestions.
- **FR-015**: The verification endpoint MUST be designed with a pluggable suggestion source so that a third-party autocomplete provider (e.g., Google Places) can be added in a future iteration without changing the consumer-facing API contract.
- **FR-016**: The verification endpoint MUST require valid JWT authentication, consistent with the geocoding endpoint.
- **FR-017**: The verification endpoint MUST require a minimum of 5 characters of input before returning suggestions. Inputs shorter than 5 characters MUST return only local validation feedback with an empty suggestions list.

### Key Entities

- **Geocoder Cache** *(existing)*: Stores previously geocoded results keyed by provider name and normalized address. This feature reuses the existing cache — no new database entities are introduced.

## Assumptions

- The existing geocoder cache table and cache lookup/store functions are sufficient for this feature without modification.
- The system internally manages provider selection. If additional providers are added in the future, the system can switch or prioritize providers without any change to the consumer-facing API.
- Freeform address input is normalized (uppercase, trim, collapse whitespace) before cache lookup, ensuring consistent cache hits regardless of consumer input formatting. This normalization is compatible with the existing batch pipeline's cache keys.
- The existing global rate limit (60 req/min per IP) provides sufficient protection against abuse. Per-endpoint rate limiting is not required at this time.
- This endpoint is for single-address geocoding only. Batch geocoding of arbitrary addresses (not voter records) is out of scope and can be added in a future iteration if needed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Authenticated users receive geocoding results within 5 seconds for uncached addresses (dependent on external provider response time).
- **SC-002**: Cached addresses return results in under 500 milliseconds.
- **SC-003**: 100% of geocoding requests from authenticated users either succeed with coordinates or return a clear, documented error response (no silent failures or ambiguous errors).
- **SC-004**: The endpoint handles at least 60 concurrent requests per minute without degradation, consistent with the global rate limit.
- **SC-005**: The verification endpoint returns suggestions and validation feedback within 500 milliseconds for any input.
- **SC-006**: Malformed addresses receive clear validation feedback identifying all missing or incorrect components.
