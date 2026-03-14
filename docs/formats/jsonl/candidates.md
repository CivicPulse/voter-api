# CandidateJSONL JSONL Schema

<!-- Auto-generated from Pydantic model. Do not edit manually. Regenerate with: uv run python tools/generate_jsonl_docs.py -->

JSONL record for a candidate (person entity).

All records include a `schema_version` field (default: `1`) for forward compatibility. Increment on breaking changes.

## Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `schema_version` | integer | No | `1` | Schema version integer. Increment on breaking changes. |
| `id` | uuid | Yes | -- | UUID from candidate file metadata table. Required. |
| `full_name` | string | Yes | -- | Full name of the candidate as it appears on the ballot. |
| `bio` | string or null | No | `null` | Biographical text for the candidate. |
| `photo_url` | string or null | No | `null` | URL to the candidate's photo. |
| `email` | string or null | No | `null` | Contact email address for the candidate. |
| `home_county` | string or null | No | `null` | County of residence. |
| `municipality` | string or null | No | `null` | Municipality of residence. |
| `links` | array[CandidateLinkJSONL] | No | -- | List of external links (website, social media, etc.). |
| `external_ids` | object or null | No | `null` | External IDs for cross-referencing (e.g. ballotpedia, open_states, vpap). |

## Enum Definitions

### LinkType

Allowed candidate link types.

| Value | Description |
|-------|-------------|
| `website` | Website |
| `campaign` | Campaign |
| `facebook` | Facebook |
| `twitter` | Twitter |
| `instagram` | Instagram |
| `youtube` | Youtube |
| `linkedin` | Linkedin |
| `other` | Other |

## Embedded Models

### CandidateLinkJSONL

Embedded model for a candidate's external link.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `link_type` | LinkType enum | Yes | -- | Link type. One of: website, campaign, facebook, twitter, instagram, youtube, linkedin, other. |
| `url` | string | Yes | -- | Full URL of the external link. |
| `label` | string or null | No | `null` | Optional display label for the link. |

## Example JSONL Record

Minimal record showing all required fields with realistic sample values:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "full_name": "Jane A Smith"
}
```
