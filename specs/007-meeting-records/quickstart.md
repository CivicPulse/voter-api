# Quickstart: Meeting Records API

**Branch**: `007-meeting-records` | **Date**: 2026-02-19

## Prerequisites

- PostgreSQL 15+ with PostGIS 3.x (existing database)
- Python 3.13+ (via `uv`)
- Existing voter-api environment set up per project README

## Setup

```bash
# Switch to the feature branch
git checkout 007-meeting-records

# Install dependencies (if new packages were added)
uv sync

# Run database migration
uv run voter-api db upgrade

# Create upload directory for meeting attachments
mkdir -p uploads/meetings
```

## Configuration

Add to `.env` (or set via environment):

```bash
# Meeting attachment storage (optional — defaults shown)
MEETING_UPLOAD_DIR=./uploads/meetings
MEETING_MAX_FILE_SIZE_MB=50
```

## API Endpoints

All endpoints require JWT authentication. Base URL: `/api/v1/`

### Governing Body Types (admin only for writes)

| Method | Path                          | Description           | Auth        |
|--------|-------------------------------|-----------------------|-------------|
| GET    | /governing-body-types         | List all types        | Any role    |
| POST   | /governing-body-types         | Create new type       | Admin       |

### Governing Bodies (admin only for writes)

| Method | Path                          | Description           | Auth        |
|--------|-------------------------------|-----------------------|-------------|
| GET    | /governing-bodies             | List (paginated)      | Any role    |
| POST   | /governing-bodies             | Create                | Admin       |
| GET    | /governing-bodies/{id}        | Detail                | Any role    |
| PATCH  | /governing-bodies/{id}        | Update                | Admin       |
| DELETE | /governing-bodies/{id}        | Soft delete           | Admin       |

### Meetings

| Method | Path                          | Description           | Auth             |
|--------|-------------------------------|-----------------------|------------------|
| GET    | /meetings                     | List (paginated)      | Any role         |
| POST   | /meetings                     | Create                | Admin/Contributor|
| GET    | /meetings/{id}                | Detail (with counts)  | Any role         |
| PATCH  | /meetings/{id}                | Update                | Admin/Contributor|
| DELETE | /meetings/{id}                | Soft delete (cascade) | Admin            |
| POST   | /meetings/{id}/approve        | Approve pending       | Admin            |
| POST   | /meetings/{id}/reject         | Reject pending        | Admin            |

### Agenda Items (sub-resource of meeting)

| Method | Path                                              | Description    | Auth             |
|--------|---------------------------------------------------|----------------|------------------|
| GET    | /meetings/{mid}/agenda-items                      | List (ordered) | Any role         |
| POST   | /meetings/{mid}/agenda-items                      | Create         | Admin/Contributor|
| GET    | /meetings/{mid}/agenda-items/{id}                 | Detail         | Any role         |
| PATCH  | /meetings/{mid}/agenda-items/{id}                 | Update         | Admin/Contributor|
| DELETE | /meetings/{mid}/agenda-items/{id}                 | Soft delete    | Admin            |
| PUT    | /meetings/{mid}/agenda-items/reorder              | Bulk reorder   | Admin/Contributor|

### Attachments

| Method | Path                                                           | Description        | Auth             |
|--------|----------------------------------------------------------------|--------------------|------------------|
| POST   | /meetings/{mid}/attachments                                    | Upload to meeting  | Admin/Contributor|
| GET    | /meetings/{mid}/attachments                                    | List for meeting   | Any role         |
| POST   | /meetings/{mid}/agenda-items/{aid}/attachments                 | Upload to item     | Admin/Contributor|
| GET    | /meetings/{mid}/agenda-items/{aid}/attachments                 | List for item      | Any role         |
| GET    | /attachments/{id}                                              | Metadata           | Any role         |
| GET    | /attachments/{id}/download                                     | Download file      | Any role         |
| DELETE | /attachments/{id}                                              | Soft delete        | Admin            |

### Video Embeds

| Method | Path                                                           | Description        | Auth             |
|--------|----------------------------------------------------------------|--------------------|------------------|
| POST   | /meetings/{mid}/video-embeds                                   | Create for meeting | Admin/Contributor|
| GET    | /meetings/{mid}/video-embeds                                   | List for meeting   | Any role         |
| POST   | /meetings/{mid}/agenda-items/{aid}/video-embeds                | Create for item    | Admin/Contributor|
| GET    | /meetings/{mid}/agenda-items/{aid}/video-embeds                | List for item      | Any role         |
| GET    | /video-embeds/{id}                                             | Detail             | Any role         |
| PATCH  | /video-embeds/{id}                                             | Update             | Admin/Contributor|
| DELETE | /video-embeds/{id}                                             | Soft delete        | Admin            |

### Search

| Method | Path                          | Description                       | Auth     |
|--------|-------------------------------|-----------------------------------|----------|
| GET    | /meetings/search              | Full-text search (q, page, size)  | Any role |

## Query Parameters

### Pagination (all list endpoints)

| Param     | Type | Default | Max | Description          |
|-----------|------|---------|-----|----------------------|
| page      | int  | 1       | —   | Page number (1-based)|
| page_size | int  | 20      | 100 | Items per page       |

### Meeting Filters

| Param             | Type   | Description                    |
|-------------------|--------|--------------------------------|
| governing_body_id | UUID   | Filter by governing body       |
| date_from         | date   | Start of date range (inclusive)|
| date_to           | date   | End of date range (inclusive)  |
| meeting_type      | string | Filter by meeting type         |
| status            | string | Filter by status               |

### Search Parameters

| Param     | Type   | Description                      |
|-----------|--------|----------------------------------|
| q         | string | Search query (min 2 characters)  |
| page      | int    | Page number (default 1)          |
| page_size | int    | Items per page (default 20)      |

## Example Usage

```bash
# Create a governing body (admin)
curl -X POST /api/v1/governing-bodies \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Fulton County Commission", "type_id": "<uuid>", "jurisdiction": "Fulton County"}'

# Create a meeting
curl -X POST /api/v1/meetings \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"governing_body_id": "<uuid>", "meeting_date": "2026-02-19T18:00:00-05:00", "meeting_type": "regular", "status": "scheduled"}'

# Upload an attachment
curl -X POST /api/v1/meetings/<meeting_id>/attachments \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@agenda.pdf"

# Search across meetings
curl "/api/v1/meetings/search?q=zoning+variance&page=1&page_size=20" \
  -H "Authorization: Bearer $TOKEN"
```

## CLI Commands (planned)

```bash
# Seed default governing body types
uv run voter-api meetings seed-types

# List governing bodies
uv run voter-api meetings list-bodies
```
