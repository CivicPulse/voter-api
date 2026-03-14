# Filing Status Vocabulary

This document defines the controlled vocabulary for candidate filing status values. These indicate a candidate's qualification status for a specific contest.

**Authoritative source:** The canonical values are defined in `src/voter_api/schemas/candidate.py::FilingStatus` (a Python `StrEnum`).

## Values

| Value | Description | SOS CSV Values That Map Here |
|-------|-------------|------------------------------|
| `qualified` | Candidate has met all qualification requirements and will appear on the ballot. | "Qualified", "Qualified - Signatures Accepted", "Qualified - Signatures Required" |
| `withdrawn` | Candidate voluntarily withdrew from the contest after initially qualifying. | "Withdrawn" |
| `disqualified` | Candidate was removed from the ballot by election officials for failing to meet requirements. | "Disqualified" |
| `write_in` | Candidate is registered as a write-in candidate and will not appear on the printed ballot. | "Write-In", "Write In" |

## Mapping from SOS Data

The Georgia Secretary of State CSV files contain verbose status strings. The mapping to this vocabulary normalizes those strings:

| SOS CSV Status | Filing Status Value |
|----------------|---------------------|
| Qualified | `qualified` |
| Qualified - Signatures Accepted | `qualified` |
| Qualified - Signatures Required | `qualified` |
| Withdrawn | `withdrawn` |
| Disqualified | `disqualified` |
| Write-In | `write_in` |
| Write In | `write_in` |

Any SOS status value not listed above should be flagged as a validation error by the converter.

## Usage in Markdown Files

In contest file candidate tables, the **Status** column uses the human-readable form (title case) for readability:

```markdown
| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| Jane Doe | Qualified | No | Attorney | 03/02/2026 |
| John Smith | Withdrawn | No | Engineer | 03/01/2026 |
```

In JSONL output, the `filing_status` field uses the exact lowercase vocabulary value:

```json
{"filing_status": "qualified"}
```

## Notes

- All values are lowercase with underscores (snake_case)
- The converter normalizes SOS CSV status strings to these four values
- Unknown SOS status values produce a converter validation error
- The `qualified` value encompasses several SOS sub-statuses (signatures accepted, signatures required) because the distinction is not meaningful for downstream consumers
