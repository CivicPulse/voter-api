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
| `early_voting_end` | March 17 special | PDF only gives start date; derivable from GA law (O.C.G.A. § 21-2-385) as 2026-03-13 but not explicitly stated |
| `description` | All contests | Prose description of the contest — would need to be authored |
| `eligibility_description` | All contests | Who is eligible to vote — not in any SOS data |
| `purpose` | Clayton Probate Judge, Bibb Commission Dist. 5 | Why the special election was called; Wadley contest states it (fill unexpired term) but the others do not |
| Candidate `bio` | All candidates | Not in SOS data |
| Candidate `photo_url` | All candidates | Not in SOS data |
| Candidate `ballot_order` | All candidates | Not in SOS data |

### Potentially fillable with additional research

| Gap | How it could be filled |
|-----|----------------------|
| Elbert & Haralson contest files | SOS election calendar lists 5 participating counties for March 17 but the CSV only has candidates for 3 (Bibb, Clayton, Jefferson); Elbert and Haralson contests may have been resolved or data is not yet published |
| `purpose` for Clayton/Bibb | Research local news or county commission minutes for the triggering vacancy |
| May 19 contest-level files | Overview exists but no individual contest markdown files yet (2,319 candidates across hundreds of contests) |

## Data Sources

Raw candidate CSVs are in `data/new/`:
- `MARCH_17_2026-SPECIAL_ELECTION_Qualified_Candidates.csv`
- `MAY_19_2026-GENERAL_AND_PRIMARY_ELECTION_Qualified_Candidates.csv`

SOS election calendar PDFs are in `data/new/`:
- `MARCH_17_2026-SPECIAL_ELECTION_DATA.pdf`
- `MAY_19_2026-GENERAL_AND_PRIMARY_ELECTION_DATA.pdf`
- `2026 Short Calendar .pdf`
