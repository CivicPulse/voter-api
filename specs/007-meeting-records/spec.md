# Feature Specification: Meeting Records API

**Feature Branch**: `007-meeting-records`
**Created**: 2026-02-19
**Status**: Draft
**Input**: User description: "Build the core API for storing, retrieving, and searching local government meeting records. This is the foundational data layer for the CivicPulse civic transparency platform."

## Clarifications

### Session 2026-02-19

- Q: Should approval apply at the meeting level (batch) or per-record independently? → A: Meeting-level. Approving a meeting approves all its child records (agenda items, attachments, video embeds) as a batch.
- Q: Can contributors view and edit their own pending/rejected records? → A: Yes. Contributors can view and edit their own pending and rejected records.
- Q: Should governing body type be a fixed enum, admin-extensible enum, or free-text? → A: Fixed enum, admin-extensible. A predefined list of types ships by default; admins can add new types via the API.
- Q: Should meeting detail responses include child records inline or via separate endpoints? → A: Summary + links. Meeting detail includes child counts (agenda items, attachments, video embeds) and dedicated sub-endpoints for each collection.
- Q: Should deleted records be soft-deleted or hard-deleted? → A: Soft delete. All records are marked as inactive/archived and hidden from normal queries but preserved in the system for audit and recovery.
- Q: Can contributors create governing bodies, or is that admin-only? → A: Admin-only. Governing body creation and editing is restricted to admins. Contributors can only create meetings under existing approved governing bodies.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Manage Governing Bodies (Priority: P1)

An administrator registers local governing bodies (county commissions, city councils, school boards, etc.) in the system so that meetings can be organized under the correct jurisdiction. They provide the body's name, type, jurisdiction, and optional metadata such as a website URL and description. They can later update details or deactivate a body that is no longer tracked.

**Why this priority**: Governing bodies are the top-level organizational entity. No meetings, agenda items, or attachments can exist without at least one governing body in the system.

**Independent Test**: Can be fully tested by creating, listing, updating, and deleting governing bodies. Delivers the organizational foundation for all subsequent data entry.

**Acceptance Scenarios**:

1. **Given** the system has no governing bodies, **When** an admin creates a governing body with name, type, and jurisdiction, **Then** the system stores the record and returns it with a unique identifier.
2. **Given** a governing body exists, **When** an admin updates its name or description, **Then** the changes are persisted and reflected on subsequent retrieval.
3. **Given** a governing body has no active meetings, **When** an admin soft-deletes it, **Then** the record is marked inactive and hidden from normal queries.
4. **Given** a governing body has active (non-deleted) meetings, **When** an admin attempts to soft-delete it, **Then** the system prevents deletion and returns an error explaining the dependency.
5. **Given** multiple governing bodies exist, **When** a user lists them with optional filters for type or jurisdiction, **Then** the system returns a paginated list matching the criteria.

---

### User Story 2 - Record and Browse Meetings (Priority: P1)

An administrator creates meeting records for a governing body, capturing the meeting date and time, location, type (regular, special, work session, emergency, public hearing), status (scheduled, completed, cancelled, postponed), and an optional link to the official government meeting page. Users can browse meetings filtered by governing body, date range, type, and status.

**Why this priority**: Meetings are the central entity of the system. They connect governing bodies to agenda items, documents, and recordings. Without meetings, no civic transparency data can be captured.

**Independent Test**: Can be fully tested by creating meetings under a governing body and verifying list/filter/pagination behavior. Delivers the core data browsing experience.

**Acceptance Scenarios**:

1. **Given** a governing body exists, **When** an admin creates a meeting with date, time, location, type, and status, **Then** the meeting is stored and associated with that governing body.
2. **Given** meetings exist across multiple governing bodies, **When** a user filters by a specific governing body, **Then** only meetings for that body are returned.
3. **Given** meetings exist across various dates, **When** a user filters by a date range, **Then** only meetings within that range are returned.
4. **Given** meetings exist with different types and statuses, **When** a user filters by type "special" and status "completed", **Then** only matching meetings are returned.
5. **Given** a meeting exists with an external source URL, **When** a user retrieves the meeting details, **Then** the external link is included so they can cross-reference the official government page.
6. **Given** a meeting is in status "scheduled", **When** an admin updates it to "cancelled", **Then** the status change is persisted.
7. **Given** more than one page of meetings exist, **When** a user requests page 2 with a page size of 20, **Then** the system returns the correct slice with pagination metadata (total count, page count, current page).

---

### User Story 3 - Manage Agenda Items (Priority: P1)

An administrator adds ordered agenda items to a meeting, each with a title, optional description, action taken, and disposition (approved, denied, tabled, no action, informational). Items maintain their display order within a meeting. Users can retrieve all agenda items for a given meeting.

**Why this priority**: Agenda items are the primary unit of civic transparency — they represent the specific actions a governing body discusses and votes on. They are also the main target for full-text search.

**Independent Test**: Can be fully tested by adding agenda items to a meeting, reordering them, and verifying CRUD operations. Delivers the ability to record what happened at each meeting.

**Acceptance Scenarios**:

1. **Given** a meeting exists, **When** an admin creates an agenda item with title, description, order position, and disposition, **Then** the item is stored and linked to the meeting.
2. **Given** a meeting has multiple agenda items, **When** a user retrieves the meeting's agenda, **Then** items are returned in their specified display order.
3. **Given** an agenda item exists, **When** an admin updates its disposition from "no action" to "approved", **Then** the change is persisted.
4. **Given** an agenda item exists, **When** an admin soft-deletes it, **Then** it is hidden from normal queries and the remaining items' display order is preserved.
5. **Given** a meeting has 5 agenda items, **When** an admin reorders item 4 to position 2, **Then** all items reflect the updated order on retrieval.

---

### User Story 4 - Upload and Download File Attachments (Priority: P2)

An administrator uploads document files (PDFs, Word documents, Excel spreadsheets, CSVs, images) and associates them with either a meeting or an individual agenda item. Users can list attachments for a meeting or agenda item and download any attachment. File metadata (name, size, content type, upload date) is stored alongside the file.

**Why this priority**: Supporting document attachments is essential for transparency (agendas, minutes, supporting materials), but the core meeting/agenda structure must exist first.

**Independent Test**: Can be fully tested by uploading files to a meeting, listing them, and downloading them. Delivers the ability to preserve and share official meeting documents.

**Acceptance Scenarios**:

1. **Given** a meeting exists, **When** an admin uploads a PDF file associated with the meeting, **Then** the file is stored and metadata (filename, size, content type, upload timestamp) is recorded.
2. **Given** an agenda item exists, **When** an admin uploads a supporting document for that item, **Then** the file is associated with the specific agenda item.
3. **Given** attachments exist for a meeting, **When** a user lists attachments for that meeting, **Then** all meeting-level and agenda-item-level attachments are returned with metadata.
4. **Given** an attachment exists, **When** a user requests to download it, **Then** the file is returned with the correct content type and original filename.
5. **Given** an admin uploads a file with an unsupported format (e.g., `.exe`), **When** the upload is processed, **Then** the system rejects the file with a clear error message listing allowed formats.
6. **Given** an attachment is linked to an agenda item, **When** the attachment is deleted, **Then** the agenda item remains unaffected.

---

### User Story 5 - Add Video Embeds for Meeting Recordings (Priority: P2)

An administrator associates video recordings with meetings or specific agenda items by providing a video URL (YouTube or Vimeo). Optional start and end timestamps can be specified to link directly to the portion of the recording covering a particular agenda item discussion. Users can retrieve video information alongside meeting and agenda item details.

**Why this priority**: Video recordings are important for transparency and engagement, but they depend on meetings and agenda items existing first.

**Independent Test**: Can be fully tested by adding video embeds to a meeting and agenda items, then retrieving them. Delivers the ability to link meeting recordings to their agenda context.

**Acceptance Scenarios**:

1. **Given** a meeting exists, **When** an admin adds a YouTube video URL for the full meeting recording, **Then** the video embed is stored and linked to the meeting.
2. **Given** an agenda item exists, **When** an admin adds a Vimeo video URL with start timestamp 01:23:45, **Then** the embed is stored with the timestamp so users can jump to the relevant discussion.
3. **Given** a video embed has both start and end timestamps, **When** a user retrieves the agenda item, **Then** the video information includes both timestamps for the segment.
4. **Given** an admin provides a URL that is not from YouTube or Vimeo, **When** the embed is submitted, **Then** the system rejects it with an error specifying allowed video platforms.
5. **Given** a meeting has a full recording and individual agenda items have timestamped segments, **When** a user views the meeting details, **Then** both the full recording and per-item video segments are accessible.

---

### User Story 6 - Search Across Meeting Records (Priority: P2)

A user searches for specific topics across all meeting records. The search examines agenda item titles and descriptions as well as attachment filenames. Results are returned with relevance ranking and include enough context (meeting date, governing body, agenda item title) for the user to identify the most relevant records.

**Why this priority**: Full-text search is the primary discovery mechanism for civic transparency users. However, it requires meetings and agenda items to exist first.

**Independent Test**: Can be fully tested by creating meetings with agenda items and attachments, then searching for known terms. Delivers topic-based discovery across the full meeting archive.

**Acceptance Scenarios**:

1. **Given** agenda items exist with various titles and descriptions, **When** a user searches for "zoning variance", **Then** results include all agenda items containing that phrase, ranked by relevance.
2. **Given** attachments exist with descriptive filenames, **When** a user searches for "budget report", **Then** results include matches from both agenda item text and attachment filenames.
3. **Given** search results span multiple governing bodies and meetings, **When** results are displayed, **Then** each result includes the governing body name, meeting date, and agenda item title for context.
4. **Given** a search returns more results than one page, **When** the user requests subsequent pages, **Then** results are paginated consistently.
5. **Given** a user searches for a term with no matches, **When** results are returned, **Then** the system returns an empty result set with zero total count (not an error).

---

### Edge Cases

- What happens when a meeting is soft-deleted that has agenda items, attachments, and video embeds? Soft-deleting a meeting cascades to soft-delete all child records. All records remain in the system for audit and recovery.
- What happens when an admin uploads a file that exceeds the maximum allowed size? The system rejects the upload with a clear error indicating the size limit. **Assumption**: Maximum file size is 50 MB per upload.
- What happens when two agenda items are assigned the same order position? The system either rejects the duplicate or auto-adjusts subsequent items. **Assumption**: The system enforces unique ordering per meeting and auto-adjusts when items are inserted or reordered.
- What happens when a video platform URL format changes? The system stores the raw URL and performs lightweight validation (domain check only), so format changes do not break existing records.
- What happens when a user searches with an empty or single-character query? The system requires a minimum query length of 2 characters and returns a validation error otherwise.
- What happens when a governing body's jurisdiction overlaps with another? The system allows overlapping jurisdictions (e.g., a county commission and a city council within the same county) since this reflects real-world government structure.

## Requirements *(mandatory)*

### Functional Requirements

**Governing Bodies**

- **FR-001**: System MUST allow creation of governing body records with name (required), type (required), jurisdiction (required, e.g., county name or city name), description (optional), and website URL (optional). Governing body type MUST be selected from a predefined enumeration. Default types MUST include: county commission, city council, school board, planning commission, water authority, housing authority, and transit authority. Admins MUST be able to add new types via the API.
- **FR-002**: System MUST support listing governing bodies with pagination and optional filters for type and jurisdiction.
- **FR-003**: System MUST support updating and soft-deleting governing body records. Soft deletion MUST mark the record as inactive and hide it from normal queries while preserving it in the system. Soft deletion MUST be prevented if the body has active (non-deleted) meetings.

**Meetings**

- **FR-004**: System MUST allow creation of meeting records associated with a governing body, including date/time (required), location (optional), meeting type (required: regular, special, work session, emergency, public hearing), status (required: scheduled, completed, cancelled, postponed), and external source URL (optional).
- **FR-005**: System MUST support listing meetings with pagination and filtering by governing body, date range (start and end), meeting type, and status. Filters MUST be combinable. The single-meeting detail response MUST include summary counts of child records (agenda items, attachments, video embeds) rather than embedding them inline. Child collections MUST be accessible via dedicated sub-endpoints.
- **FR-006**: System MUST support updating meeting records (all mutable fields) and soft-deleting meetings. Soft-deleting a meeting MUST cascade to soft-delete all its child records (agenda items, attachments, video embeds). Soft-deleted records MUST be hidden from normal queries but preserved in the system.

**Agenda Items**

- **FR-007**: System MUST allow creation of agenda items within a meeting, including title (required), description (optional), action taken (optional, free text), disposition (optional: approved, denied, tabled, no action, informational), and display order position (required).
- **FR-008**: System MUST maintain unique ordering of agenda items within a meeting. When an item is inserted or reordered, the system MUST auto-adjust positions of other items.
- **FR-009**: System MUST support listing all agenda items for a meeting in display order, as well as updating and deleting individual items.

**File Attachments**

- **FR-010**: System MUST allow file uploads associated with either a meeting or an individual agenda item. Supported formats MUST include: PDF (.pdf), Microsoft Word (.doc, .docx), Microsoft Excel (.xls, .xlsx), CSV (.csv), PNG (.png), JPEG (.jpg, .jpeg), GIF (.gif), and TIFF (.tif, .tiff).
- **FR-011**: System MUST store file metadata including original filename, file size, content type, and upload timestamp.
- **FR-012**: System MUST support downloading files with the correct content type and original filename. System MUST support listing all attachments for a meeting or agenda item.
- **FR-013**: System MUST reject uploads of unsupported file formats with a clear error message listing allowed formats.
- **FR-014**: System MUST enforce a maximum file size of 50 MB per upload and reject oversized files with a descriptive error.

**Video Embeds**

- **FR-015**: System MUST allow associating video URLs with a meeting or individual agenda item. Only YouTube and Vimeo URLs MUST be accepted.
- **FR-016**: System MUST support optional start and end timestamps (in seconds) on video embeds for linking to specific discussion segments.
- **FR-017**: System MUST validate that submitted URLs are from YouTube or Vimeo domains before storing.

**Search**

- **FR-018**: System MUST provide a full-text search endpoint that searches across agenda item titles, agenda item descriptions, and attachment filenames simultaneously.
- **FR-019**: Search results MUST include contextual information: governing body name, meeting date, meeting type, and agenda item title.
- **FR-020**: Search results MUST be paginated and ranked by relevance.
- **FR-021**: Search queries MUST be at least 2 characters long; shorter queries MUST return a validation error.

**Pagination**

- **FR-022**: All list endpoints MUST support pagination with configurable page size (default 20, maximum 100) and return total count, total pages, and current page in the response.

**Authorization**

- **FR-023**: System MUST support a "contributor" role in addition to existing admin/analyst/viewer roles. Contributors MUST be able to create and edit meeting records (meetings, agenda items, attachments, video embeds) under existing approved governing bodies. Governing body creation and editing MUST be restricted to admin users. Contributor-submitted meetings MUST be saved in a "pending" state and MUST NOT be visible to non-admin users until an admin approves them. **Exception**: Contributors MUST be able to view and edit their own pending and rejected records. Approval operates at the **meeting level**: approving or rejecting a meeting applies to all its child records (agenda items, attachments, video embeds) as a batch.
- **FR-024**: System MUST allow admins to review, approve, or reject pending meetings submitted by contributors. Approving a meeting makes the meeting and all its child records visible to all authenticated users. Rejecting a meeting MUST include a reason and returns the entire meeting (with children) to the contributor for revision.
- **FR-025**: System MUST allow admin users to create, update, and delete all records directly without an approval step.
- **FR-026**: System MUST allow read and search operations for all authenticated users. Search and list results MUST only include approved records for non-admin users; admins MUST see all records with their approval status.

### Key Entities

- **Governing Body**: Represents a local government entity (county commission, city council, school board, etc.). Attributes: name, type, jurisdiction, description, website URL, active status. A governing body has many meetings.
- **Meeting**: A specific session of a governing body. Attributes: date/time, location, meeting type, status, external source URL. Belongs to one governing body. Has many agenda items, attachments, and video embeds.
- **Agenda Item**: An ordered item on a meeting's agenda. Attributes: title, description, action taken, disposition, display order. Belongs to one meeting. May have attachments and video embeds.
- **File Attachment**: A document file associated with a meeting or agenda item. Attributes: original filename, stored filename/path, file size, content type, upload timestamp. Belongs to one meeting or one agenda item (polymorphic association).
- **Video Embed**: A link to a video recording on YouTube or Vimeo. Attributes: video URL, platform (YouTube/Vimeo), start timestamp, end timestamp. Belongs to one meeting or one agenda item (polymorphic association).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can create a complete meeting record (governing body, meeting, 10 agenda items, 3 attachments, 1 video embed) in under 5 minutes of cumulative data entry time.
- **SC-002**: Users can find any meeting topic via search and navigate to the relevant agenda item within 30 seconds.
- **SC-003**: All list and search endpoints return results within 2 seconds under normal load (up to 100,000 meetings in the system).
- **SC-004**: The system supports at least 5 years of historical meeting data per governing body without degraded browsing or search performance.
- **SC-005**: File uploads and downloads complete successfully for all supported document formats up to 50 MB.
- **SC-006**: 95% of first-time users can locate a specific governing body's recent meetings without assistance.
- **SC-007**: Search relevance returns the correct meeting record in the top 5 results for 90% of keyword queries tested against known data.

## Assumptions

- The existing JWT-based authentication with admin/analyst/viewer roles will be extended to cover meeting record operations.
- File storage location and mechanism are implementation decisions outside this spec. The spec only requires upload, download, and metadata tracking.
- "Jurisdiction" for governing bodies is a free-text field (e.g., "Fulton County", "City of Atlanta") rather than a structured geographic reference — this keeps the initial implementation simple while allowing future enrichment.
- Video embed URLs are stored as-is; the system does not fetch or verify that the video actually exists on the platform.
- Meeting date/time includes timezone information to handle governing bodies across different time zones.
- All deletions are soft deletes (records marked inactive, hidden from normal queries, preserved for audit). No full versioning or change history audit trail is required in this initial implementation; this can be added in a future feature.

## Out of Scope

- Automated scraping or sync from government meeting platforms
- Live streaming of meetings
- OCR or AI-powered document extraction from uploaded files
- Calendar integration (iCal export, Google Calendar sync)
- Audio-only recording upload
- Notification or subscription system for meeting updates
- Public (unauthenticated) access to meeting records
- Bulk import of historical meeting data from external formats
