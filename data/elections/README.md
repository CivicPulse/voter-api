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
| `purpose` (Clayton) | **Filled** — Retirement of Chief Probate Judge Pamela P. Ferguson | [Clayton News Daily](https://www.news-daily.com/news/two-qualify-for-probate-judge-special-election/article_ff5f78c9-af74-4bd9-b9db-051e0f1c7f6f.html), [Ballotpedia](https://ballotpedia.org/Clayton_County_Probate_Court,_Georgia) |
| `purpose` (Bibb) | **Filled** — Commissioner Seth Clark resigned to run for Lt. Governor | [13WMAZ](https://www.13wmaz.com/article/news/local/macon-bibb-county-commissioner-mayor-pro-tem-seth-clark-resigns/93-96066c4b-2a5c-476a-a2e3-3c8ad544fef6), [41NBC](https://www.41nbc.com/seth-clark-resigns-macon-bibb-commission/) |
| `eligibility` | **Filled** for all 3 SOS contests | Derived from contest scope |
| Candidate `bio` | **Filled** — brief bios for all 10 SOS candidates | Local news, campaign websites, [City of Wadley](https://wadleyga.gov/city-council) |
| Candidate websites | **Filled** — Pryor, Sheppard, Cooke | Campaign websites |
| Haralson County | **Explained** — City of Buchanan mayor/council (municipal qualifying, not SOS) | [11Alive](https://www.11alive.com/article/news/local/special-election-march-2026-buchanan-mayor-conviction-deadly-2015-crash/85-085664b5-646a-4d0e-a63d-7e52e059c0e7), [Atlanta News First](https://www.atlantanewsfirst.com/2026/01/30/date-set-special-election-replace-ex-trooper-mayor-convicted-vehicular-homicide/) |
| Elbert County | **Unresolvable** — likely unopposed candidate declared elected under O.C.G.A. § 21-2-291 | No news coverage found |

### Filled via generation (May 19 general primary — local elections)

| Field | Status | Source |
|-------|--------|--------|
| Local contest files | **Filled** — 159 county files with 1,070 contests and 1,645 candidates | Generated from SOS qualified candidates CSV |

### Remaining gaps requiring additional research

| Gap | How it could be filled |
|-----|----------------------|
| May 19 state legislative contest files | State House (299 contests) and State Senate (93 contests) files are not yet created |

## Data Sources

Raw candidate CSVs are in `data/new/`:
- `MARCH_17_2026-SPECIAL_ELECTION_Qualified_Candidates.csv`
- `MAY_19_2026-GENERAL_AND_PRIMARY_ELECTION_Qualified_Candidates.csv`

SOS election calendar PDFs are in `data/new/`:
- `MARCH_17_2026-SPECIAL_ELECTION_DATA.pdf`
- `MAY_19_2026-GENERAL_AND_PRIMARY_ELECTION_DATA.pdf`
- `2026 Short Calendar .pdf`
