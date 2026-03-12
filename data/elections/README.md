# Upcoming Georgia Elections

This directory tracks upcoming Georgia elections with candidate and contest details sourced from the Secretary of State qualified candidates feed.

## Elections

| Date | Type | Candidates | Details |
|------|------|-----------|---------|
| March 17, 2026 | [Special Election](2026-03-17-special-election.md) | 10 | Clayton Probate Judge, Bibb County Commission Dist. 5, Wadley Council |
| May 19, 2026 | [General and Primary](2026-05-19-general-primary.md) | 2,319 | Governor, Lt. Governor, Secretary of State, U.S. Senate, all 14 U.S. House districts, 299 State House + 93 State Senate races, local offices |

## Known Data Gaps

### Not available from SOS sources

| Field | Applies to | Notes |
|-------|-----------|-------|
| `description` | All contests | Prose description of the contest — would need to be authored |
| Candidate `photo_url` | All candidates | Not in SOS data; campaign websites likely have photos but URLs not confirmed |
| Candidate `ballot_order` | All candidates | Not in SOS data |

### Filled via research (March 17 special election)

| Field | Status | Source |
|-------|--------|--------|
| `early_voting_end` | **Filled** — 2026-03-13 | O.C.G.A. § 21-2-385 (Friday before Election Day) |
| `purpose` (Clayton) | **Filled** — Retirement of Chief Probate Judge Pamela P. Ferguson | Clayton News Daily, Ballotpedia |
| `purpose` (Bibb) | **Filled** — Commissioner Seth Clark resigned to run for Lt. Governor | 13WMAZ, 41NBC |
| `eligibility` | **Filled** for all 3 SOS contests | Derived from contest scope |
| Candidate `bio` | **Filled** — brief bios for all 10 SOS candidates | Local news, campaign websites, City of Wadley |
| Candidate websites | **Filled** — Pryor, Sheppard, Cooke | Campaign websites |
| Haralson County | **Explained** — City of Buchanan mayor/council (municipal qualifying, not SOS) | 11Alive, Atlanta News First |
| Elbert County | **Unresolvable** — likely unopposed candidate declared elected under O.C.G.A. § 21-2-291 | No news coverage found |

### Remaining gaps requiring additional research

| Gap | How it could be filled |
|-----|----------------------|
| May 19 contest-level files | Overview exists but no individual contest markdown files yet (2,319 candidates across hundreds of contests) |

## Data Sources

Raw candidate CSVs are in `data/new/`:
- `MARCH_17_2026-SPECIAL_ELECTION_Qualified_Candidates.csv`
- `MAY_19_2026-GENERAL_AND_PRIMARY_ELECTION_Qualified_Candidates.csv`

SOS election calendar PDFs are in `data/new/`:
- `MARCH_17_2026-SPECIAL_ELECTION_DATA.pdf`
- `MAY_19_2026-GENERAL_AND_PRIMARY_ELECTION_DATA.pdf`
- `2026 Short Calendar .pdf`
