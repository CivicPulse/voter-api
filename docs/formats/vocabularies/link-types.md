# Link Types Vocabulary

This document defines the controlled vocabulary for candidate link types. Links are URLs associated with a candidate (person) and appear only in candidate files -- not in contest tables.

**Authoritative source:** The canonical values are defined in `src/voter_api/schemas/candidate.py::LinkType` (a Python `StrEnum`) and enforced by the database constraint on the `candidate_links.link_type` column.

## Values

| Value | Description | Usage Guidance |
|-------|-------------|----------------|
| `website` | Personal website or professional homepage. | Use for a candidate's personal site that is not campaign-specific. |
| `campaign` | Campaign-specific website for this election cycle. | Use for dedicated campaign sites (e.g., `votesmith.com`, `janeforgovernor.com`). |
| `facebook` | Facebook profile or page. | Use the canonical page URL, not a post URL. |
| `twitter` | Twitter/X profile. | Use the profile URL (e.g., `https://twitter.com/handle`), not a tweet URL. |
| `instagram` | Instagram profile. | Use the profile URL, not a post URL. |
| `youtube` | YouTube channel. | Use the channel URL, not a video URL. |
| `linkedin` | LinkedIn profile. | Use the public profile URL. |
| `other` | Any link that does not fit the above categories. | Use sparingly. Include a descriptive `Label` value to clarify the link's purpose. |

## Usage in Candidate Files

Links appear in the `## Links` table within a candidate file:

```markdown
## Links

| Type | URL | Label |
|------|-----|-------|
| campaign | https://votesmith.com | votesmith.com |
| facebook | https://facebook.com/votesmith | Facebook |
| twitter | https://twitter.com/janesmith | @janesmith |
| other | https://ballotpedia.org/Jane_Smith | Ballotpedia |
```

## Design Decisions

- **Links live in candidate files only.** Email and Website columns were dropped from contest tables (per CONTEXT decision). Person-level contact information belongs in the global candidate file, not duplicated across every contest the candidate appears in.
- **One link per type per candidate is not enforced.** A candidate may have multiple `other` links or even multiple `website` links if appropriate.
- **The `campaign` type is distinct from `website`** to differentiate election-cycle-specific sites from permanent personal/professional sites.

## Notes

- All values are lowercase (no underscores needed -- single words)
- Future link types (e.g., `tiktok`, `threads`, `bluesky`, `donate`, `ballotpedia`) may be added by updating the database constraint and the `LinkType` StrEnum. This vocabulary document should be updated accordingly.
