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
- Q: Should the point-lookup endpoint (spatial point-in-polygon query for boundary districts) be included in this feature or split into a separate spec? → A: Include in this feature. All three endpoints (verify, geocode, point-lookup) ship together as a cohesive "address lookup" feature. The frontend (CivicPulse/voter-web) is building against this contract (issue #7).
- Q: When the geocode endpoint receives an unmatchable address, what HTTP status should be returned? → A: HTTP 404. Semantically correct ("location not found") and aligns with the frontend contract.
- Q: Should the endpoints use GET with query parameters or POST with JSON body? → A: GET with query parameters for all three endpoints. Semantically correct (read-only, idempotent), enables HTTP-level caching, and aligns with the frontend contract.
- Q: Should the geocode response include confidence_score, a metadata object, or both? → A: Both. Top-level `confidence` field (core to geocoding, useful for programmatic decisions) plus a `metadata` object for future extensibility.
- Q: Should the geocode response metadata include the provider name, given FR-002 says "MUST NOT be exposed"? → A: Yes. The intent of FR-002 is that consumers cannot choose/select a provider — there is no provider input parameter. Including the provider name in the response metadata for informational/debugging purposes is acceptable. FR-002 language updated accordingly.
- Q: Should there be a maximum allowed value for the accuracy parameter on the point-lookup endpoint? → A: Yes. Cap at 100 meters. Reject with HTTP 422 if the value exceeds 100.
- Q: When serving from cache, what should `formatted_address` contain? → A: Return the `normalized_address` directly from the cache as `formatted_address`. No title-casing or reformatting — the normalized form (uppercased, USPS-abbreviated) is the canonical representation.
- Q: How should the Georgia service area be defined for coordinate validation? → A: Static bounding box (lat/lng min/max rectangle enclosing Georgia). Simple, fast, and sufficient for rejecting obviously out-of-state coordinates.
- Q: Should cached geocoding results have a TTL / expiration policy? → A: No expiration for now — cached results persist indefinitely. The existing `cached_at` timestamp on `geocoder_cache` is sufficient for a future invalidation feature. No TTL logic needed in this iteration.
- Q: Should the system retry failed geocoding provider calls before returning 502? → A: Single retry with short timeout (~2s per attempt, ~4s total budget). Recovers from transient network blips while staying within the 5-second latency target.
- Q: How should the new dedicated `addresses` table relate to `geocoder_cache`? → A: FK reference. Keep geocoder_cache separate but add a FK to `addresses`. The address table stores the canonical address identity; geocoder_cache stores provider-specific geocoding results linked to it via foreign key. One address can have results from multiple providers.
- Q: Should voter records be updated to FK-reference the new `addresses` table in this feature? → A: Two-phase pipeline. Add `residence_address_id` FK to the voters table now (nullable), but always keep the inline address fields as well — they represent the government-sourced truth from the GA Secretary of State voter file. The inline fields are permanent, not a migration artifact. The FK is NOT set during CSV import (phase 1) because raw voter data is frequently malformed and the `addresses` table is a canonical, validated store. Instead, the FK is set during post-import processing (phase 2) after the address has been normalized and successfully geocoded. This prevents garbage/un-geocodable entries from polluting the addresses table.
- Q: What should the `addresses` table store — freeform string, parsed components, or both? → A: Both. Store parsed component fields (street_number, street_name, street_type, city, state, zip, etc.) plus a computed/stored `normalized_address` string for cache lookups and provider calls. The normalized string is derived from the components.
- Q: How should address uniqueness/deduplication be determined? → A: By normalized address string. UNIQUE constraint on `normalized_address`. The normalized form (uppercased, USPS-abbreviated, whitespace-collapsed) ensures variant spellings of the same address resolve to a single canonical row.
- Q: When should address rows be created from the geocode API endpoint? → A: On successful geocode only. The address row is upserted after the provider returns a successful result, then the geocoder_cache entry is linked to it. Failed/unmatchable addresses never get an address row, preventing junk/typo entries from polluting the table.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Geocode a Single Address (Priority: P1)

As an authenticated API consumer, I want to submit a street address and receive geographic coordinates with a confidence score so that I can determine the location of any arbitrary address without needing voter records in the database.

**Why this priority**: This is the core value of the feature. Without the ability to geocode a single address on demand, none of the other stories are relevant. Currently geocoding is only available as an internal batch operation on voter records — this story makes geocoding a first-class, user-facing capability.

**Independent Test**: Can be fully tested by sending a GET request with an address query parameter and verifying the response contains latitude, longitude, confidence score, and matched address.

**Acceptance Scenarios**:

1. **Given** an authenticated user with any role (viewer, analyst, or admin), **When** they submit a valid street address (e.g., "100 Peachtree St NW, Atlanta, GA 30303"), **Then** they receive a response containing `formatted_address`, `latitude`, `longitude`, `confidence`, and `metadata`.
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
2. **Given** an authenticated user, **When** they submit an address that the geocoding provider cannot match to a location, **Then** the system returns HTTP 404 with a message indicating the address could not be geocoded.
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

### User Story 5 - Point Lookup for Boundary Districts (Priority: P1)

As an authenticated API consumer, I want to submit geographic coordinates and receive a list of all boundary districts containing that point so that I can identify every district (precinct, county, congressional, state senate/house, commission, school) a location falls within.

**Why this priority**: This is co-P1 with geocoding because it completes the end-to-end "address lookup" flow. The frontend uses this for both address-based lookups (after geocoding) and GPS-based lookups (directly from browser geolocation). Without this endpoint, geocoded coordinates have no actionable context.

**Independent Test**: Can be fully tested by submitting a known Georgia coordinate (e.g., downtown Atlanta) and verifying the response contains the correct precinct, county, congressional district, state senate district, state house district, and any other boundary types that contain that point.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they submit valid coordinates within Georgia (e.g., lat=33.749, lng=-84.388), **Then** they receive a list of all boundary districts containing that point, each with boundary type, name, identifier, ID, and metadata.
2. **Given** an authenticated user, **When** they submit coordinates outside the Georgia service area, **Then** the system returns HTTP 422 indicating the location is outside the supported area.
3. **Given** an authenticated user using GPS with limited accuracy, **When** they submit coordinates with an accuracy radius that spans multiple boundaries of the same type, **Then** the system returns all potentially matching boundaries.
4. **Given** an authenticated user, **When** they submit coordinates that fall within no loaded boundaries, **Then** the system returns an empty districts list.
5. **Given** an unauthenticated request, **When** a point lookup is submitted, **Then** the system returns HTTP 401 Unauthorized.

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
- What happens when coordinates are on the exact edge of a boundary? The system uses standard PostGIS point-in-polygon containment rules (ST_Contains/ST_Within) — the point is included if it is on or inside the boundary.
- What happens when no boundaries have been loaded into the database? The point-lookup endpoint returns an empty districts list.
- What happens when the GPS accuracy radius exceeds 100 meters? The system returns HTTP 422 rejecting the request. The maximum allowed accuracy value is 100 meters.
- What happens when lat/lng parameters are missing or non-numeric? The system returns HTTP 422 with a validation error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All endpoints MUST use GET with query parameters. The geocode and verify endpoints accept an `address` query parameter; the point-lookup endpoint accepts `lat`, `lng`, and optional `accuracy` query parameters.
- **FR-002**: System MUST return `formatted_address`, `latitude`, `longitude`, `confidence` (score), and a flexible `metadata` object in the geocode response when geocoding succeeds. The consumer MUST NOT be able to select or influence which provider is used (no provider input parameter). The provider name MAY be included in the response `metadata` object for informational/debugging purposes.
- **FR-003**: System MUST require valid JWT authentication for all geocoding requests. Any authenticated role (viewer, analyst, admin) is permitted — no role-based restriction.
- **FR-004**: System MUST use the existing geocoder provider infrastructure to perform address geocoding. The provider is selected internally by the system — no consumer-facing provider parameter is exposed.
- **FR-005**: System MUST normalize the freeform address input (uppercase, trim whitespace, collapse multiple spaces) before cache lookup and provider calls. If a cached result exists for the normalized address, it MUST be returned without making an external call.
- **FR-006**: System MUST store new geocoding results in the cache after a successful provider call so that future lookups for the same address are served from cache. On a successful geocode, the system MUST upsert a canonical address row in the `addresses` table and link the geocoder_cache entry to it via FK. Failed or unmatchable addresses MUST NOT create address rows.
- **FR-007**: System MUST return HTTP 422 with a descriptive validation error when the submitted address is empty, whitespace-only, or exceeds 500 characters.
- **FR-008**: System MUST return HTTP 404 with a descriptive message when the provider cannot match the submitted address to a location.
- **FR-009**: System MUST retry once (single retry) with a ~2-second timeout per attempt before returning HTTP 502. If both attempts fail, the system MUST return HTTP 502 with a descriptive error message indicating a temporary upstream failure and suggesting a retry. Total provider call budget MUST NOT exceed ~4 seconds to stay within the 5-second latency target (SC-001).
- **FR-010**: System MUST respect the existing global rate limiting (60 requests per minute per IP) applied to all API endpoints.
- **FR-011**: System MUST expose a separate address verification endpoint that accepts a partial or malformed freeform address string and returns ranked address suggestions.
- **FR-012**: The verification endpoint MUST perform local validation to determine whether the submitted address is well-formed — checking for required components (street number, street name, city, state, ZIP) and reporting which are present, missing, or malformed.
- **FR-013**: The verification endpoint MUST normalize the submitted address using existing USPS Publication 28 rules (e.g., STREET→ST, ROAD→RD, NORTH→N) and return the normalized form in the response.
- **FR-014**: The verification endpoint MUST search the canonical address store (`addresses` table, joined with geocoder cache for coordinates) for addresses matching the submitted input and return up to 10 ranked suggestions.
- **FR-015**: The verification endpoint MUST be designed with a pluggable suggestion source so that a third-party autocomplete provider (e.g., Google Places) can be added in a future iteration without changing the consumer-facing API contract.
- **FR-016**: The verification endpoint MUST require valid JWT authentication, consistent with the geocoding endpoint.
- **FR-017**: The verification endpoint MUST require a minimum of 5 characters of input before returning suggestions. Inputs shorter than 5 characters MUST return only local validation feedback with an empty suggestions list.
- **FR-018**: System MUST expose a point-lookup endpoint that accepts latitude and longitude coordinates and returns all boundary districts containing that point (point-in-polygon spatial query).
- **FR-019**: The point-lookup response MUST include for each matching boundary: boundary type, name, boundary identifier, boundary ID, and a flexible metadata object with type-specific attributes (e.g., FIPS code for counties, precinct IDs for precincts).
- **FR-020**: The point-lookup endpoint MUST accept an optional accuracy parameter (in meters) representing GPS accuracy radius, with a maximum allowed value of 100 meters. Values exceeding 100 MUST be rejected with HTTP 422. When provided, the system MUST return all boundaries intersecting the accuracy circle, not just those containing the exact point.
- **FR-021**: The point-lookup endpoint MUST return HTTP 422 when coordinates fall outside the Georgia service area. The Georgia service area is defined as a static bounding box: latitude 30.36°N to 35.00°N, longitude 85.61°W to 80.84°W.
- **FR-022**: The point-lookup endpoint MUST require valid JWT authentication, consistent with the other endpoints.
- **FR-023**: The geocode endpoint MUST return HTTP 422 when a geocoded address resolves to coordinates outside the Georgia service area (static bounding box: lat 30.36–35.00°N, lng 85.61–80.84°W).

### Key Entities

- **Address** *(new)*: Dedicated canonical address store. Each unique address gets a single row in the `addresses` table, serving as the authoritative record for that address. Stores both parsed component fields (street_number, street_name, street_type, pre_direction, post_direction, apt_unit, city, state, zipcode) and a computed/stored `normalized_address` string for cache lookups and provider calls. Other entities (voters, geocoder cache) reference addresses via FK. Address data persists even if referencing entities are removed.
- **Voter** *(existing, modified)*: Adds a `residence_address_id` FK to the `addresses` table. The inline residence address fields (street_number, street_name, city, etc.) are permanently retained as the government-sourced truth from the GA Secretary of State voter file. The FK is NOT populated during CSV import — raw voter data is frequently malformed and the `addresses` table is a canonical, validated store. Instead, the FK is set during post-import processing after the address has been normalized and successfully geocoded. Voters with `residence_address_id IS NULL` indicate addresses that have not yet been validated/geocoded.
- **Geocoder Cache** *(existing, modified)*: Stores provider-specific geocoding results. Modified to add a FK to the `addresses` table, linking each cached result to a canonical address. Reused by the geocode and verify endpoints.
- **Boundary** *(existing)*: Geospatial boundary polygons with type, name, identifier, and metadata. The point-lookup endpoint queries boundaries using PostGIS spatial operations.

## Assumptions

- A new dedicated `addresses` table is introduced as the canonical address store. The existing `geocoder_cache` table is modified to reference it via FK. Cache lookup/store functions will be updated to work through the address entity.
- The system internally manages provider selection. If additional providers are added in the future, the system can switch or prioritize providers without any change to the consumer-facing API.
- Freeform address input is normalized (uppercase, trim, collapse whitespace) before cache lookup, ensuring consistent cache hits regardless of consumer input formatting. This normalization is compatible with the existing batch pipeline's cache keys.
- The existing global rate limit (60 req/min per IP) provides sufficient protection against abuse. Per-endpoint rate limiting is not required at this time.
- This endpoint is for single-address geocoding only. Batch geocoding of arbitrary addresses (not voter records) is out of scope and can be added in a future iteration if needed.
- Cached geocoding results do not expire in this iteration. The existing `cached_at` timestamp on `geocoder_cache` supports future time-based invalidation if needed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Authenticated users receive geocoding results within 5 seconds for uncached addresses (dependent on external provider response time).
- **SC-002**: Cached addresses return results in under 500 milliseconds.
- **SC-003**: 100% of geocoding requests from authenticated users either succeed with coordinates or return a clear, documented error response (no silent failures or ambiguous errors).
- **SC-004**: The endpoint handles at least 60 concurrent requests per minute without degradation, consistent with the global rate limit.
- **SC-005**: The verification endpoint returns suggestions and validation feedback within 500 milliseconds for any input.
- **SC-006**: Malformed addresses receive clear validation feedback identifying all missing or incorrect components.
- **SC-007**: The point-lookup endpoint returns all matching boundary districts within 1 second for any valid Georgia coordinate.
- **SC-008**: The point-lookup endpoint correctly identifies all boundary types (precinct, county, congressional, state senate, state house, commission, school) that contain a given point.
