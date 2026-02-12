# Feature Specification: Voter Data Management

**Feature Branch**: `001-voter-data-management`
**Created**: 2026-02-11
**Status**: Draft
**Input**: User description: "Build an application that can help manage, store, update, and query voter data. Raw voter data from the secretary of state only contains addresses and not geospatial data. We need to be able to geocode the addresses and store the geospatial data in a way that allows for efficient querying. Further, geospatial data from the state and counties about districts and precincts will need to be ingested and stored in a way that allows for efficient querying. We will also need to be able to compare voters to the geospatial data to determine which voters are in which districts and precincts to then compare what a voter is registered for and what they physically reside in to determine if they are registered to vote in the correct location. We will also need to be able to query voters based on various parameters such as name, address, and voter ID. Bulk data exports will also be needed to ingest into other applications or share with other organizations."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Voter Data Ingestion (Priority: P1)

A data administrator imports a raw voter file received from the secretary of state into the system. The file contains voter records with personal information and street addresses but no geospatial coordinates. The system parses the file, validates each record, and stores the voter data. The administrator receives a summary report indicating how many records were successfully imported, how many failed validation, and details about any errors.

**Why this priority**: Without voter data in the system, no other feature has anything to operate on. This is the foundational data pipeline that every subsequent story depends on.

**Independent Test**: Can be fully tested by importing a sample voter file and verifying records appear in the system with correct data. Delivers the core data store that the entire application is built around.

**Acceptance Scenarios**:

1. **Given** a valid voter file from the secretary of state, **When** the administrator initiates an import, **Then** all valid records are stored and a summary report shows successful count, failed count, and error details.
2. **Given** a voter file with some malformed records (missing required fields, invalid formats), **When** the administrator initiates an import, **Then** valid records are imported successfully and malformed records are logged with specific error reasons without halting the entire import.
3. **Given** a voter file containing records that already exist in the system (by voter ID), **When** the administrator initiates an import, **Then** existing records are updated with the new data and the summary report distinguishes between new inserts and updates.
4. **Given** a very large voter file (hundreds of thousands of records), **When** the administrator initiates an import, **Then** the system processes the file in batches and provides progress feedback without running out of memory.

---

### User Story 2 - Address Geocoding (Priority: P2)

After voter data is imported, the system geocodes voter addresses to obtain geographic coordinates (latitude/longitude). The geocoding process runs on records that have addresses but lack geospatial data. The resulting coordinates are stored alongside the voter record for use in spatial queries. An administrator can trigger geocoding for all un-geocoded records or re-geocode specific records.

**Why this priority**: Geocoding transforms raw addresses into queryable geospatial data, which is the prerequisite for all location-based analysis (district matching, precinct verification). Without coordinates, the spatial features cannot function.

**Independent Test**: Can be tested by importing voter records (from US1), triggering geocoding, and verifying that coordinates are stored and are geographically reasonable for the given addresses.

**Acceptance Scenarios**:

1. **Given** voter records with addresses but no coordinates, **When** the administrator triggers geocoding, **Then** each address is geocoded and the resulting coordinates are stored with the voter record.
2. **Given** an address that cannot be geocoded (invalid or ambiguous), **When** geocoding is attempted, **Then** the record is flagged with a geocoding failure reason and the process continues with remaining records.
3. **Given** a voter record that was previously geocoded, **When** the administrator triggers re-geocoding for that record, **Then** the coordinates are updated with the new result.
4. **Given** a batch of un-geocoded records, **When** geocoding is triggered, **Then** the system processes records in batches, respects rate limits of the geocoding provider, and reports progress and success/failure counts.

---

### User Story 3 - District & Precinct Boundary Ingestion (Priority: P3)

A data administrator imports geospatial boundary data (shapefiles or GeoJSON) representing districts and precincts from state and county sources. The system parses the boundary files, validates the geometry, and stores the boundaries in a way that supports efficient spatial queries. The administrator can view a summary of imported boundaries and update them when new boundary data is released.

**Why this priority**: District and precinct boundaries are required for the voter-location comparison analysis. They must be loaded before any registration-correctness checks can be performed.

**Independent Test**: Can be tested by importing boundary files and verifying that boundaries are stored, queryable, and contain valid geometry. A point-in-polygon test with known coordinates confirms spatial queries work correctly.

**Acceptance Scenarios**:

1. **Given** a valid shapefile or GeoJSON file containing district boundaries, **When** the administrator initiates an import, **Then** all boundaries are stored with their associated metadata (district name, type, ID) and the system reports successful import count.
2. **Given** boundary data with invalid or self-intersecting geometry, **When** the import is attempted, **Then** the system reports which boundaries have invalid geometry and either repairs them automatically or skips them with a clear error message.
3. **Given** updated boundary data for a district that already exists in the system, **When** the administrator imports the new data, **Then** the existing boundary is replaced with the updated geometry and metadata.
4. **Given** boundary data from multiple sources (state-level districts, county-level precincts), **When** imported separately, **Then** each boundary type is stored and queryable independently and boundaries can overlap across types (a precinct can exist within a district).

---

### User Story 4 - Voter Registration Location Analysis (Priority: P4)

An analyst runs a comparison between a voter's geocoded residential address and the district/precinct boundaries in the system to determine where the voter physically resides. The system then compares this physical location against the voter's registered district and precinct to identify whether the voter is registered in the correct location. Results are available as a report showing matches and mismatches.

**Why this priority**: This is the core analytical value of the system — identifying voters whose registration does not match their physical location. It depends on voter data (US1), geocoding (US2), and boundary data (US3).

**Independent Test**: Can be tested by loading known voter records with geocoded addresses and known boundary data, running the analysis, and verifying that the system correctly identifies which voters are inside or outside their registered districts and precincts.

**Acceptance Scenarios**:

1. **Given** geocoded voter records and loaded district/precinct boundaries, **When** the analyst runs a location analysis, **Then** for each voter the system determines which district(s) and precinct(s) their residential coordinates fall within.
2. **Given** the spatial analysis results and the voter's registered district/precinct, **When** the comparison is performed, **Then** the system flags voters whose registered location does not match their physical location, categorizing mismatches by type (wrong district, wrong precinct, or both).
3. **Given** a voter whose geocoded address falls exactly on a boundary line, **When** the analysis runs, **Then** the system assigns the voter to one boundary deterministically and flags the record for manual review.
4. **Given** a voter whose address could not be geocoded, **When** the analysis runs, **Then** the voter is excluded from spatial analysis and included in a separate "unable to analyze" report with the reason.

---

### User Story 5 - Voter Search & Query (Priority: P5)

A user searches for voters by various parameters including name (first, last, partial), address (street, city, zip), voter ID, registration status, district, or precinct. The system returns matching records with relevant details. Searches support pagination for large result sets and can combine multiple parameters to narrow results.

**Why this priority**: Search and query is the primary day-to-day interaction model for users accessing the system. While it does not depend on geospatial features, it is lower priority than the analytical pipeline because the analytical pipeline is the unique value proposition.

**Independent Test**: Can be tested by loading voter records (from US1) and performing searches by each supported parameter, verifying correct results are returned with proper pagination.

**Acceptance Scenarios**:

1. **Given** voter records in the system, **When** a user searches by voter ID, **Then** the exact matching record is returned with all available details.
2. **Given** voter records in the system, **When** a user searches by partial last name, **Then** all voters whose last name contains the search term are returned, ordered by relevance.
3. **Given** voter records in the system, **When** a user searches by address components (street, city, or zip code), **Then** matching voters are returned.
4. **Given** a search that returns more than 100 results, **When** the results are returned, **Then** they are paginated with metadata indicating total count, current page, and total pages.
5. **Given** multiple search parameters (e.g., last name + city), **When** the user submits the query, **Then** results match all provided criteria (AND logic).

---

### User Story 6 - Bulk Data Export (Priority: P6)

An administrator exports voter data in bulk for use in external applications or to share with partner organizations. Exports support filtering (by district, precinct, registration status, or analysis results) and multiple output formats. Large exports are processed asynchronously and the administrator is notified when the export is ready for download.

**Why this priority**: Bulk export enables interoperability with external systems and is a common operational need. It is lowest priority because it is an output mechanism that depends on all other data being in the system first.

**Independent Test**: Can be tested by loading voter records and requesting an export with various filters, verifying the output file contains the correct records in the expected format.

**Acceptance Scenarios**:

1. **Given** voter records in the system, **When** an administrator requests a full export in CSV format, **Then** a CSV file is generated containing all voter records with all available fields.
2. **Given** voter records with analysis results, **When** an administrator requests an export filtered to voters with registration mismatches, **Then** only mismatched voters are included in the export.
3. **Given** a filter for a specific district or precinct, **When** the administrator requests an export, **Then** only voters within that district or precinct are included.
4. **Given** an export request for a dataset exceeding 50,000 records, **When** the export is initiated, **Then** the system processes it asynchronously and provides a download link when complete.
5. **Given** an export request, **When** the administrator selects an output format (CSV, JSON, or GeoJSON), **Then** the export is generated in the requested format with appropriate structure.

---

### Edge Cases

- What happens when a voter file uses an unexpected delimiter or encoding? The primary format is CSV (as used by Georgia SoS), but the system MUST detect common delimiters (comma, pipe, tab) and encodings (UTF-8, Latin-1) automatically, or reject the file with a descriptive error.
- What happens when a voter's residence address components are partially empty (e.g., no pre-direction, no apt/unit)? The system MUST gracefully reconstruct the address from whichever components are present and skip empty fields without injecting extra spaces or commas.
- What happens when the geocoding service is unavailable or rate-limited? The system MUST queue failed geocoding attempts for retry and report the outage without losing progress on already-geocoded records.
- What happens when boundary data overlaps unexpectedly (e.g., two districts claim the same area)? The system MUST store all boundaries as provided and flag overlapping regions for administrative review.
- What happens when a voter record has no address at all? The system MUST import the record but flag it as "un-geocodable" and exclude it from spatial analysis.
- What happens when an export is requested while a large import is in progress? The system MUST allow concurrent operations and export data as of the time the export was initiated (snapshot consistency).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST import voter data files from the secretary of state, with the Georgia SoS CSV format (53-column, comma-delimited) as the primary supported format. Additional delimiter formats (pipe, tab) MUST also be supported.
- **FR-002**: System MUST validate each voter record during import against required field rules and data format constraints, including voter registration number uniqueness, valid status values, and parseable date fields.
- **FR-003**: System MUST detect and handle duplicate voter records (by voter registration number) during import, updating existing records rather than creating duplicates.
- **FR-004**: System MUST reconstruct full street addresses from decomposed address components (street number, pre-direction, street name, street type, post-direction, apt/unit, city, zip) and geocode them to obtain latitude/longitude coordinates.
- **FR-005**: System MUST store geocoded coordinates as geospatial point data for efficient spatial querying.
- **FR-006**: System MUST support batch geocoding with rate limiting and progress tracking.
- **FR-007**: System MUST import geospatial boundary data for districts and precincts from standard GIS formats (shapefile, GeoJSON).
- **FR-008**: System MUST validate imported boundary geometry and report or repair invalid geometries.
- **FR-009**: System MUST perform point-in-polygon spatial queries to determine which district(s) and precinct(s) a voter's geocoded location falls within.
- **FR-010**: System MUST compare a voter's physically-determined district/precinct against their registered assignments (congressional, state senate, state house, judicial, county commission, school board, city council, municipal school board, water board, super council, super commissioner, super school board, fire district, county precinct, municipal precinct) and flag mismatches per boundary type.
- **FR-011**: System MUST support searching voters by name (first, last, partial match), address, voter ID, registration status, district, and precinct.
- **FR-012**: System MUST paginate search results for queries returning large result sets.
- **FR-013**: System MUST export voter data in CSV, JSON, and GeoJSON formats with support for filtering by any queryable parameter.
- **FR-014**: System MUST process large exports asynchronously and provide download access when complete.
- **FR-015**: System MUST provide a CLI for triggering imports, geocoding, analysis, and exports.
- **FR-016**: System MUST provide a REST API for querying voters, viewing analysis results, and triggering operations.
- **FR-017**: System MUST log all data operations (imports, geocoding runs, analysis runs, exports) with timestamps and summary statistics.
- **FR-018**: System MUST authenticate all API requests and authorize operations based on user roles.
- **FR-019**: System MUST validate all input data at the API boundary before processing.

### Key Entities

- **Voter**: Represents an individual voter record sourced from the Georgia Secretary of State voter file. Key attributes: county, voter registration number (unique identifier), status (ACTIVE/INACTIVE), status reason, last name, first name, middle name, suffix, birth year, residence address (street number, pre-direction, street name, street type, post-direction, apt/unit number, city, zip code), mailing address (street number, street name, apt/unit, city, zip, state, country), registration date, race, gender, last modified date, date of last contact, last party voted, last vote date, voter created date. Registered assignments: county precinct (code + description), municipal precinct (code + description), congressional district, state senate district, state house district, judicial district, county commission district, school board district, city council district, municipal school board district, water board district, super council district, super commissioner district, super school board district, fire district, municipality, combo, land lot, land district. Relationships: has one geocoded location (optional), falls within zero or more boundaries based on physical location.
- **GeocodedLocation**: Represents the geospatial coordinates derived from a voter's residence address. Key attributes: latitude, longitude, geocoding confidence score, geocoding source, geocoded timestamp, point geometry. The geocoder MUST reconstruct a full address from the component fields (street number + pre-direction + street name + street type + post-direction + apt/unit + city + state + zip). Relationships: belongs to one voter.
- **Boundary**: Represents a political or administrative district/precinct boundary. Key attributes: boundary name, boundary type (one of: congressional, state senate, state house, judicial, county commission, school board, city council, municipal school board, water board, super council, super commissioner, super school board, fire district, county precinct, municipal precinct), boundary identifier, source (state or county), geometry (polygon/multipolygon), effective date. The system MUST support all district types present in the Georgia SoS voter file. Relationships: contains zero or more voters based on spatial overlap.
- **ImportJob**: Represents a data import operation (voter file or boundary file). Key attributes: job ID, file name, file type, status (pending, running, completed, failed), records processed, records succeeded, records failed, started timestamp, completed timestamp, error log.
- **ExportJob**: Represents a bulk data export operation. Key attributes: job ID, requested filters, output format, status (pending, running, completed, failed), record count, file path, requested timestamp, completed timestamp.
- **AnalysisResult**: Represents the outcome of comparing a voter's physical location to their registration. Key attributes: voter reference, determined district(s), determined precinct(s), registered district, registered precinct, match status (match, mismatch-district, mismatch-precinct, mismatch-both, unable-to-analyze), analysis timestamp.

## Assumptions

- The primary data source is the Georgia Secretary of State voter file, delivered as a CSV with a header row containing 53 columns. The column layout is well-defined (see `docs/voter_data_sample_from_state.csv` for reference). The system will support configurable column mapping to accommodate format changes or other states.
- Voter addresses in the source file are decomposed into components (street number, pre-direction, street name, street type, post-direction, apt/unit). The system MUST reconstruct full addresses from these components for geocoding purposes.
- Voters have both a residence address and a mailing address. The residence address is used for geocoding and spatial analysis. The mailing address is stored but not geocoded.
- The voter file already contains registered district/precinct assignments as code values (e.g., congressional district "8", county precinct "HA2"). The system stores these as-is and compares them against spatially-determined assignments.
- All district types present in the Georgia SoS file MUST be supported: congressional, state senate, state house, judicial, county commission, school board, city council, municipal school board, water board, super council, super commissioner, super school board, and fire district. County precinct and municipal precinct are also included.
- The US Census Bureau Geocoder will be used as the default geocoding provider (free, no API key required for batch processing). The architecture will support pluggable geocoding providers to allow switching to commercial services (Google Maps, Mapbox) if higher accuracy or throughput is needed.
- District and precinct boundary data is available in standard GIS formats (shapefile or GeoJSON) from state and county GIS departments. This is the industry standard for government geospatial data distribution.
- The system will initially target Georgia data but the data model will not be hardcoded to Georgia's specific schema, allowing future expansion to other states.
- Export formats are CSV (for spreadsheet tools), JSON (for API consumers), and GeoJSON (for GIS tools).
- User roles will include at minimum: administrator (full access), analyst (read + analysis), and viewer (read-only).
- Voter status values include at minimum ACTIVE and INACTIVE, with optional status reason codes (e.g., "CROSS STATE", "NCOA").

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Administrators can import a voter file of 500,000+ records and receive a completion summary within 30 minutes.
- **SC-002**: 95% of valid addresses are successfully geocoded on the first attempt using the default geocoding provider.
- **SC-003**: District and precinct boundary data can be imported and spatially indexed within 10 minutes per boundary dataset.
- **SC-004**: The location analysis for 500,000 voters against all loaded boundaries completes within 60 minutes.
- **SC-005**: Voter search queries return results within 2 seconds for any combination of search parameters.
- **SC-006**: Bulk exports of up to 500,000 records complete within 15 minutes in any supported format.
- **SC-007**: Users can identify all voters with registration-location mismatches for a given district in a single query.
- **SC-008**: The system correctly assigns 99% of geocoded voters to their containing district and precinct (validated against a known-correct test dataset).
- **SC-009**: All data import, geocoding, and analysis operations are recoverable — a process interrupted mid-run can be resumed without re-processing completed records.
