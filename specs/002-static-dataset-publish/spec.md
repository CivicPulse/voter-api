# Feature Specification: Static Dataset Publishing

**Feature Branch**: `002-static-dataset-publish`
**Created**: 2026-02-12
**Status**: Draft
**Input**: User description: "For publicly available datasets such as the boundary GeoJSON feature export, create a way to generate those and upload them to a service like R2. That way, those datasets can be consumed even if this API is offline and at extreme load."

## Clarifications

### Session 2026-02-12

- Q: Should the API redirect (302) to the static file, proxy the content, or support both? → A: HTTP redirect (302) to static file URL on object storage.
- Q: How does the API know which datasets are published (for redirect lookup)? → A: Manifest file on object storage. The publish command writes a `manifest.json` alongside the datasets; the API fetches and caches it periodically.
- Q: Should the publish system be scoped to boundary GeoJSON only or designed generically for any dataset type? → A: Boundaries only for now. Other dataset types can be added in future iterations.
- Q: How often should the API refresh the cached manifest to pick up newly published datasets? → A: 5-minute TTL. Newly published datasets are picked up within 5 minutes without API restart.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate and Publish Boundary Datasets (Priority: P1)

As an administrator, I want to generate static GeoJSON files from boundary data and upload them to S3-compatible object storage so that consumers can access boundary datasets without depending on the API server's availability or capacity.

**Why this priority**: This is the core value of the feature. Without the ability to generate and upload files, nothing else matters. The boundary GeoJSON endpoint already exists and serves data live from the database, but it creates load on the API and is unavailable when the API is down.

**Independent Test**: Can be fully tested by running a CLI command that generates boundary GeoJSON files and uploads them to a configured S3-compatible bucket. Success is verified by confirming the files exist in the bucket and contain valid GeoJSON matching the database contents.

**Acceptance Scenarios**:

1. **Given** boundaries have been imported into the database, **When** an admin runs the publish command, **Then** GeoJSON files are generated for each boundary type and uploaded to the configured object storage bucket.
2. **Given** boundaries exist for multiple types (e.g., congressional, state_senate, county_precinct), **When** the publish command runs, **Then** each boundary type is exported as a separate GeoJSON file, plus one combined file containing all boundaries.
3. **Given** no boundaries exist in the database, **When** the publish command runs, **Then** the system reports that no datasets are available to publish and does not upload empty files.
4. **Given** the object storage service is unreachable, **When** the publish command runs, **Then** the system reports a clear error indicating the upload destination is unavailable.

---

### User Story 2 - Filter Published Datasets (Priority: P2)

As an administrator, I want to selectively publish datasets by boundary type, county, or source so that I can update only the datasets that have changed without republishing everything.

**Why this priority**: Boundary data may be updated incrementally (e.g., only county precincts change after redistricting). Being able to publish selectively avoids unnecessary work and reduces upload time.

**Independent Test**: Can be tested by running the publish command with filter flags and verifying only the matching datasets are regenerated and uploaded.

**Acceptance Scenarios**:

1. **Given** boundaries exist for multiple types, **When** an admin publishes with a boundary type filter, **Then** only datasets matching that type are generated and uploaded.
2. **Given** boundaries exist for multiple counties, **When** an admin publishes with a county filter, **Then** only datasets for that county are generated and uploaded.
3. **Given** an admin publishes with a source filter ("state" or "county"), **When** boundaries exist from both sources, **Then** only boundaries matching the selected source are included.

---

### User Story 3 - Track Published Dataset Metadata (Priority: P3)

As an administrator, I want to see when datasets were last published and what they contain so that I can verify the published data is current and decide when to republish.

**Why this priority**: Without visibility into what has been published, administrators cannot confidently manage published datasets. This supports operational awareness but is not required for core publishing functionality.

**Independent Test**: Can be tested by publishing datasets and then running a status command that displays the last publish timestamp, record counts, and file sizes for each published dataset.

**Acceptance Scenarios**:

1. **Given** datasets have been published, **When** an admin runs the publish status command, **Then** the system displays a summary showing each published dataset, its record count, file size, and last-published timestamp.
2. **Given** no datasets have been published, **When** an admin runs the publish status command, **Then** the system indicates that no datasets have been published yet.
3. **Given** datasets were published and then boundary data was updated in the database, **When** an admin runs the publish status command, **Then** the system shows the last-published timestamp (which will be before the data update, alerting the admin to republish).

---

### User Story 4 - API Redirects to Static Files (Priority: P1)

As a consumer of the boundary GeoJSON endpoint, I want the API to automatically redirect my request to the pre-published static file on object storage so that my request is served without database load and remains available even when the API is under heavy load.

**Why this priority**: This is co-P1 with publishing because it completes the end-to-end value proposition. Publishing files alone is useful, but the real benefit is that existing API consumers are transparently offloaded to the static files via HTTP 302 redirect without changing their client code.

**Independent Test**: Can be tested by publishing a dataset, then requesting the existing `/api/v1/boundaries/geojson` endpoint and verifying the response is an HTTP 302 redirect to the static file URL on object storage.

**Acceptance Scenarios**:

1. **Given** boundary datasets have been published to object storage, **When** a consumer requests `/api/v1/boundaries/geojson` without filters, **Then** the API responds with an HTTP 302 redirect to the combined `all-boundaries.geojson` file URL.
2. **Given** a boundary type dataset has been published, **When** a consumer requests `/api/v1/boundaries/geojson?boundary_type=congressional`, **Then** the API responds with an HTTP 302 redirect to the `congressional.geojson` file URL.
3. **Given** no datasets have been published (or object storage is not configured), **When** a consumer requests `/api/v1/boundaries/geojson`, **Then** the API serves the response directly from the database as it does today (fallback behavior).
4. **Given** a consumer requests the GeoJSON endpoint with filters that do not map to a pre-published static file, **When** no matching static file exists, **Then** the API falls back to serving directly from the database.

---

### Edge Cases

- What happens when a dataset file is too large for a single upload? The system should use multipart uploads for files exceeding 100 MB.
- What happens when an upload is interrupted midway? The system should not leave partial or corrupt files in object storage; uploads should be atomic (upload to a temporary key, then move/copy to the final key).
- What happens when object storage credentials are missing or invalid? The system should fail with a clear error message before attempting any generation or upload work.
- What happens when boundary data contains invalid geometries? The system should skip invalid records, log warnings, and include only valid geometries in the published files.
- What happens when the publish command is run concurrently? The system should handle concurrent runs gracefully without producing corrupt files (last-write-wins is acceptable).
- What happens when a published static file is deleted from object storage but the system still thinks it's published? The API should detect the stale state (e.g., via the status check) and fall back to database serving.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST generate GeoJSON FeatureCollection files from boundary data stored in the database.
- **FR-002**: System MUST produce one GeoJSON file per boundary type (e.g., `congressional.geojson`, `state_senate.geojson`) containing all boundaries of that type.
- **FR-003**: System MUST produce a combined GeoJSON file (`all-boundaries.geojson`) containing every boundary regardless of type.
- **FR-004**: System MUST upload generated files to an S3-compatible object storage service (supporting Cloudflare R2, AWS S3, MinIO, and similar services).
- **FR-005**: System MUST expose the publish operation as a CLI command (e.g., `voter-api publish datasets`).
- **FR-006**: System MUST support filtering by boundary type, county, and source when publishing.
- **FR-007**: System MUST set appropriate content-type metadata (`application/geo+json`) on uploaded files.
- **FR-008**: System MUST set uploaded files as publicly readable.
- **FR-009**: Generated GeoJSON files MUST use the same feature structure and properties as the existing `/api/v1/boundaries/geojson` endpoint to maintain compatibility with existing consumers.
- **FR-010**: System MUST report progress during generation and upload (number of records processed, files uploaded, total size).
- **FR-011**: System MUST validate object storage configuration (endpoint, bucket, credentials) before beginning dataset generation.
- **FR-012**: System MUST expose a CLI command to check the status of previously published datasets (e.g., `voter-api publish status`).
- **FR-013**: System MUST use atomic uploads (write to a temporary key, then copy to the final key) to prevent consumers from reading partial files.
- **FR-014**: System MUST use multipart upload for files exceeding 100 MB.
- **FR-015**: The existing `/api/v1/boundaries/geojson` endpoint MUST respond with an HTTP 302 redirect to the corresponding static file URL when a matching published dataset exists on object storage.
- **FR-016**: When the GeoJSON endpoint receives a `boundary_type` filter that matches a published per-type file, the redirect MUST point to that specific type's file.
- **FR-017**: When the GeoJSON endpoint receives filters (e.g., county, source) that do not map to a pre-published static file, the system MUST fall back to serving the response directly from the database.
- **FR-018**: When object storage is not configured or no datasets have been published, the GeoJSON endpoint MUST continue serving responses directly from the database (backward-compatible fallback).
- **FR-019**: The publish command MUST generate and upload a `manifest.json` file alongside the dataset files, containing metadata (storage key, public URL, record count, file size, publish timestamp) for each published dataset.
- **FR-020**: The API MUST fetch and cache the manifest from object storage to determine redirect targets for the GeoJSON endpoint.
- **FR-021**: The API MUST periodically refresh the cached manifest with a 5-minute TTL so that newly published datasets are picked up within 5 minutes without requiring an API restart.

### Key Entities

- **Published Dataset**: Represents a generated static file uploaded to object storage. Attributes include: dataset name, boundary type filter, record count, file size, storage key/path, content type, and publish timestamp.
- **Manifest**: A JSON file (`manifest.json`) stored alongside the published datasets in object storage. Contains metadata for all published datasets (keys, record counts, file sizes, timestamps, public URLs). The API fetches and caches this manifest to determine redirect targets.
- **Storage Configuration**: The connection details for the S3-compatible object storage service, including endpoint URL, bucket name, access credentials, and public URL prefix.

## Assumptions

- The target object storage service is S3-compatible (supporting the S3 API protocol), which covers Cloudflare R2, AWS S3, MinIO, DigitalOcean Spaces, and similar services.
- Boundary data is already imported into the database before publishing. This feature does not handle data ingestion.
- Published files follow a predictable key structure (e.g., `boundaries/{boundary_type}.geojson`) so consumers can construct URLs without needing a directory listing.
- The administrator is responsible for configuring any CDN or custom domain in front of object storage; this feature only handles generation and upload.
- Object storage credentials are provided via environment variables, consistent with the project's 12-factor configuration approach.
- The combined "all boundaries" file is manageable in size (Georgia has ~31 boundary types with moderate geometry complexity). If this assumption proves wrong, the combined file can be removed in a future iteration.
- This feature is scoped to boundary GeoJSON datasets only. The publish/manifest/redirect pattern is inherently reusable, so other public dataset types (e.g., voter exports, analytics) can be added in future iterations without rearchitecting.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Administrators can publish all boundary datasets with a single CLI command in under 5 minutes for a full Georgia dataset.
- **SC-002**: Published GeoJSON files are accessible from object storage without requiring API authentication or the API server to be running.
- **SC-003**: Published GeoJSON files produce identical feature structures to the existing `/api/v1/boundaries/geojson` endpoint, ensuring zero consumer migration effort.
- **SC-004**: The system successfully uploads files to any S3-compatible storage service when provided valid credentials.
- **SC-005**: Consumers can retrieve published boundary files by constructing predictable URLs based on boundary type (e.g., `{base_url}/boundaries/congressional.geojson`).
- **SC-006**: Failed uploads produce clear error messages that enable administrators to diagnose and resolve issues without additional support.
- **SC-007**: Within 5 minutes of publishing, the existing GeoJSON endpoint automatically redirects matching requests to the static files without API restart or manual intervention.
- **SC-008**: When no published datasets exist or object storage is not configured, the GeoJSON endpoint continues to work identically to its current behavior (zero breaking changes).
