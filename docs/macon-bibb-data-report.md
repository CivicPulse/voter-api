# Macon-Bibb Board of Elections — Data Availability Report

**Source**: [https://www.maconbibb.us/board-of-elections/](https://www.maconbibb.us/board-of-elections/)
**Date**: 2026-02-24
**Method**: Website scrape + 8 PDF documents downloaded and text-extracted via PyMuPDF

---

## Part 1: Data Currently Supported by the API

### 1.1 Elections

The `Election` model stores: `name`, `election_date`, `election_type`, `district`, `status`, `data_source_url`, `ballot_item_id`, `creation_method`.

**Elections identified on the Macon-Bibb BoE website (8 from 2026 schedule + historical):**

| Date | Type | Race | API Mapping |
|---|---|---|---|
| 2026-01-20 | Special Election | State Senator District 18 | `election_type="special"`, `district="State Senator District 18"` |
| 2026-02-17 | Special Election Runoff | State Senator District 18 | `election_type="special_runoff"`, same district |
| 2026-03-17 | Special Election | Commission District 5 | `election_type="special"`, `district="Commission District 5"` |
| 2026-04-14 | Special Election Runoff | Commission District 5 | `election_type="special_runoff"` |
| 2026-05-19 | General Primary / NP General | Federal/State/Local offices | `election_type="general_primary"` |
| 2026-06-16 | General Primary Runoff / NP General | Federal/State/Local offices | `election_type="general_primary_runoff"` |
| 2026-11-03 | General Election | Federal/State/Special offices | `election_type="general"` |
| 2026-12-01 | General Election Runoff | Federal/State/Special Runoff | `election_type="general_runoff"` |

**Historical elections with results data available on the site:**

| Date | Type | Race |
|---|---|---|
| 2025-03-18 | Special Election (SPLOST) | SPLOST referendum |
| 2025-06-17 | Special Primary (PSC) | Public Service Commission |
| 2025-07-15 | Special Primary Runoff (PSC) | Public Service Commission |
| 2025-11-04 | General Election (PSC) | Public Service Commission |

**Fit**: All of these can be created via `POST /api/v1/elections` today. The `name`, `election_date`, `election_type`, `district`, and `status` fields map directly.

### 1.2 Election Results

The `ElectionResult` model stores: `precincts_participating`, `precincts_reporting`, `results_data` (JSONB), `fetched_at`.

**Example from the Feb 17, 2026 results PDF (State Senate District 18 Runoff):**

| Candidate | Party | Election Day | Advance Voting | Absentee by Mail | Provisional | Total |
|---|---|---|---|---|---|---|
| LeMario Nicholas Brown | Dem | 2,121 | 799 | 85 | 0 | 3,005 |
| Steven McNeel | Rep | 3,809 | 760 | 38 | 0 | 4,607 |

- Precincts Reporting: 10 of 10 (100.00%)
- Registered Voters: 108,508
- Ballots Cast: 7,615
- Turnout: 7.02%

**Fit**: The JSONB `results_data` column can store candidate vote counts, party affiliation, and voting-method breakdowns. The `precincts_participating` and `precincts_reporting` fields map directly. This data could be manually entered or parsed from the published PDFs.

### 1.3 Boundaries and Districts

The `Boundary` model supports these types relevant to Macon-Bibb data:

| Boundary Type | Already Loaded? | Macon-Bibb Data |
|---|---|---|
| `county_commission` | Yes | 9 commission districts (District 5 is the current vacancy) |
| `state_senate` | Yes | State senate districts (District 18 spans parts of Bibb County) |
| `state_house` | Yes | State house districts |
| `county_precinct` | Yes | County precincts (Godfrey, Vineville, Hazzard, Howard, Rutland, Warrior) |
| `county` | Yes | Bibb County boundary |
| `school_board` | Yes | Board of Education districts |
| `water_board` | Yes | Water Authority districts |

The election schedule PDF shows specific precinct-to-election mappings:
- **Jan 20 / Feb 17 (SD-18)**: Hazzard 2, Hazzard 4, Howard 1/2/3/5/7, Rutland 1, Warrior 1/2 (10 precincts)
- **Mar 17 / Apr 14 (Commission D5)**: Godfrey 1, Vineville 1/2/3/5/6 (6 precincts)

**Fit**: District boundaries are already loaded. The precinct-to-election activation mapping (which precincts participate in which elections) is **not** directly modeled but could be inferred from voter history data.

### 1.4 Elected Officials

The `ElectedOfficial` model stores: `boundary_type`, `district_identifier`, `full_name`, `party`, `title`, term dates, contact info, and admin approval status.

**Relevant data from Macon-Bibb**:
- **Commission District 5**: Seat vacated by **Seth Clark** (resigned). Special election on March 17, 2026 to fill the unexpired term.
- **BoE Chair**: Robert Abbott (signs official notices)
- **Elections Supervisor**: Thomas Gillon (tgillon@maconbibb.us, 478-621-6622)

**Fit**: The Seth Clark vacancy context maps directly — an `ElectedOfficial` record for Commission District 5 with term end and vacancy info. The BoE administrative contacts (Abbott, Gillon) are administrative staff, not elected officials per se, so they don't fit the current model.

### 1.5 Voter History (Aggregate Turnout)

The `VoterHistory` model stores per-voter participation records: `voter_registration_number`, `election_date`, `election_type`, `party`, `absentee`, `provisional`.

**Cross-reference**: The Feb 17 results PDF shows 7,615 ballots cast out of 108,508 registered voters (7.02% turnout). Voter history records can be aggregated to verify or supplement these figures for Bibb County.

**Fit**: Aggregate turnout analysis is already supported via the `/api/v1/voter-history/participation-stats` endpoint. Individual voter participation records for Bibb County elections are importable from GA SoS voter history files.

---

## Part 2: Data Available But NOT Supported by the API

### 2.1 Candidates / Races on Ballot

**No `Candidate` model exists in the API.**

**March 17, 2026 Special Election — Commission District 5** (from sample ballot PDF):

| Candidate | Office |
|---|---|
| Andrea C. Cooke | County Commission District 5 |
| Edward C. Foster | County Commission District 5 |
| A. Chester Gibbs | County Commission District 5 |
| Ulisha Hill | County Commission District 5 |
| Landon A. Justice | County Commission District 5 |
| Stephanie Stephens-Lanham | County Commission District 5 |

(Plus write-in option. Race is to fill the unexpired term of Seth Clark, resigned.)

**Feb 17, 2026 Runoff — State Senate District 18** (from results PDF):

| Candidate | Party |
|---|---|
| LeMario Nicholas Brown | Democrat |
| Steven McNeel | Republican |

**2026 Full Cycle — 25+ Offices on the Ballot** (from races-list PDF):

Partisan races (May 19 primary / Nov 3 general):
- Governor, Lieutenant Governor, Secretary of State, Attorney General
- Commissioner of Agriculture, Commissioner of Insurance, Commissioner of Labor
- State School Superintendent, Public Service Commissioner
- State Senators, State Representatives
- US Representatives
- Proposed Constitutional Amendments
- Democratic Party Question, Republican Party Question

Non-partisan races (May 19 / June 16 runoff):
- Judge of Superior Court of Macon Judicial Court
- Judge of State Court
- Judge of Civil & Magistrate Court
- Court of Appeals Judge of Georgia
- Supreme Court Judge of Georgia
- Bibb County Board of Education Post 7 at Large
- Bibb County Board of Education Post 8 at Large
- Macon-Bibb Water Authority Chairman
- Macon-Bibb Water Authority District 1
- Macon-Bibb Water Authority District 4
- Soil & Water Conservation District Supervisor

**Gap**: Currently, candidate information can only be stored indirectly in the `ElectionResult.results_data` JSONB field *after* results are published. There is no way to store candidates *before* an election (pre-election ballot data), nor is there a dedicated model for races/contests as distinct from elections.

### 2.2 Polling Locations

**No `PollingLocation` model exists in the API.**

**Jan 20 / Feb 17 Special Election precincts** (10 locations, from general precinct list PDF):

| Precinct | Polling Location | Address | Room Directions |
|---|---|---|---|
| Hazzard 2 | Lake Wildwood Clubhouse | 100 Clubhouse Rd, Macon GA 31220 | West wing, right side of clubhouse bldg. |
| Hazzard 4 | Tabernacle Baptist Church | 6611 Zebulon Rd, Macon, GA 31220 | Worship Center |
| Howard 1 | Northway Church | 5915 Zebulon Rd, Macon GA 31210 | Church foyer, west wing next to Cathedral Coffee shop |
| Howard 2 | Howard Community Club | 5645 Forsyth Road, Macon, GA 31210 | Main meeting floor area |
| Howard 3 | North Macon Presbyterian Church | 5707 Rivoli Dr., Macon GA 31210 | Church west wing hallway |
| Howard 5 | Forest Hills Methodist Church | 1217 Forest Hill Road, Macon, GA 31210 | Fellowship hall, rear side via South entrance |
| Howard 7 | Northside Christian Church | 5024 Northside Dr, Macon GA 31210 | Family Life Fellowship Hall, adjacent left side |
| Rutland 1 | Mikado Baptist Church | 6751 Houston Rd, Macon GA 31216 | Fellowship hall/gymnasium, center of church complex |
| Warrior 1 | Lizella Baptist Church | 2950 S. Lizella Rd, Lizella GA 31052 | Christian Life Center, South wing |
| Warrior 2 | Macon Evangelistic Church | 5399 Hartley Bridge Rd, Macon GA 31216 | Church hall center, adjacent to main sanctuary |

**Mar 17 / Apr 14 Special Election precincts** (6 locations, from precinct list PDF):

| Precinct | Polling Location | Address | Room Directions |
|---|---|---|---|
| Godfrey 1 | Dr. Robert J. Williams Complex at Ballard Hudson | 1780 Anthony Rd., Macon, GA 31204 | Front Meeting Room B, #104, right side entrance |
| Vineville 1 | Professional Learning Center | 2003 Riverside Dr., Macon, GA 31204 | Welcome Center, Suite #2007-D |
| Vineville 2 | Vineville United Methodist Church | 2045 Vineville Ave., Macon, GA 31204 | Christian Life Center, lower level at parking lot |
| Vineville 3 | Glorious Hope Baptist Church | 3805 Napier Ave., Macon, GA 31204 | Fellowship hall, main parking lot area |
| Vineville 5 | Northminster Presbyterian Church | 565 Wimbish Rd, Macon GA 31210 | Fellowship hall, East Wing section |
| Vineville 6 | Lutheran Church of The Redeemer | 390 Pierce Ave, Macon GA 31204 | Annex hall classroom A & B, lower section |

Note: Vineville 2 was **recently changed** from First Christian Church to Vineville United Methodist Church.

**Gap**: Rich structured data (precinct name, location name, full address, room-level directions) that cannot be stored anywhere in the current data model. This is high-value public information that voters need to find their polling place.

### 2.3 Early Voting Sites and Schedules

**No early voting model exists in the API.**

**2025 early voting locations** (from voter information PDF):

| Site | Address |
|---|---|
| Macon-Bibb Co Board of Elections | 3661 Eisenhower Pkwy, Ste. MB101, Macon, GA 31206 |
| Elaine Lucas Senior Center | 132 Willie Smokie Glover Dr, Macon, GA 31201 |
| Theron Ussery Community Center | 815 N Macon Park Dr, Macon, GA 31210 |

**2026 early voting sites**:
- **Mar 17 Commission D5 election**: BoE Main Office + Theron Ussery Park Recreation Center (815 N. Macon Park Dr.) — 8:30 AM to 5:30 PM
- **Jan 20 SD-18 election**: BoE Main Office only — Mon-Fri Dec 29, 2025 to Jan 16, 2026 (8:30 AM-5:30 PM); Saturday voting Jan 3 & Jan 10 (9:00 AM-5:00 PM)

**2025 schedule by election** (from voter information PDF):

| Election | Early Voting Period | Sites Open | Weekend Voting |
|---|---|---|---|
| Mar 18 SPLOST | Feb 24 - Mar 14 | Macon Mall & Elaine Lucas only | Sat Mar 1 & 8 (9-5), Sun Mar 2 Macon Mall (1-5) |
| Jun 17 PSC Primary | May 27 - Jun 13 | Macon Mall & Elaine Lucas only | Sat May 31 & Jun 7 (9-5) |
| Jul 15 PSC Runoff | Jul 7 - Jul 11 | Macon Mall & Elaine Lucas only | No weekend voting |
| Nov 4 PSC General | Oct 14 - Oct 31 | All 3 locations | Sat Oct 18 & Oct 25 (9-5) |

**Gap**: The `Election` model only stores `election_date`. There are no fields for early voting start/end dates, early voting locations, weekend voting schedules, or site-specific hours. This is critical voter information that varies by election and by site.

### 2.4 Election Milestone Dates

**The `Election` model only stores `election_date` — no other date fields.**

**From the call for special election and voter information PDFs:**

| Milestone | Date (Mar 17 election) | Date (Jan 20 election) |
|---|---|---|
| Voter registration deadline | Feb 16, 2026 | Dec 22, 2025 |
| Candidate qualifying opens | Feb 11, 2026 (noon) | — |
| Candidate qualifying closes | Feb 13, 2026 (5:30 PM) | — |
| Early voting starts | — | Dec 29, 2025 |
| Early voting ends | — | Jan 16, 2026 |
| Absentee ballot request deadline | — | — |
| Election day | Mar 17, 2026 | Jan 20, 2026 |
| Polls open | 7:00 AM | 7:00 AM |
| Polls close | 7:00 PM | 7:00 PM |
| L&A testing date | Feb 19, 2026 | — |
| Runoff date (if needed) | Apr 14, 2026 | Feb 17, 2026 |

**Gap**: Critical voter-facing dates (registration deadline, early voting period, absentee deadline) and election administration dates (qualifying period, L&A testing) have no place in the current schema.

### 2.5 Qualifying Periods and Fees

**No qualifying / candidacy model exists in the API.**

**From the qualifying fees PDF (nonpartisan offices, May 19, 2026 election):**

| Office | Annual Salary | 3% Qualifying Fee |
|---|---|---|
| Judge of State Court | $169,274.56 | $5,078.24 |
| Judge of Civil/Magistrate Court | $154,227.84 | $4,626.84 |
| Board of Education Post 7 at Large | $7,200.00 | $216.00 |
| Board of Education Post 8 at Large | $7,200.00 | $216.00 |
| Macon Water Authority Chairman | $18,600.00 | $558.00 |
| Macon Water Authority District 1 & 4 | $13,200.00 | $396.00 |

Qualifying period: 9:00 AM Monday, March 2, 2026 to noon Friday, March 6, 2026.
Location: Macon-Bibb County Board of Elections, 3661 Eisenhower Pkwy, Suite MB101.

**Commission District 5 special election qualifying**: $450 fee (per O.C.G.A. section 21-2-131), Feb 11-13, 2026 at BoE main office.

**Gap**: No model for tracking which offices are up for election, their qualifying requirements, salary data, or filing periods.

### 2.6 Ballot Measures and Referenda

**No `BallotMeasure` model exists in the API.**

From the races list PDF, the following non-candidate items appear on the 2026 ballot:
- **Proposed Constitutional Amendments** (Nov 3, 2026)
- **Democratic Party Question** (May 19, 2026 primary)
- **Republican Party Question** (May 19, 2026 primary)

Historical: The March 18, 2025 election was a **SPLOST referendum** — a county-wide ballot measure, not a candidate race.

**Gap**: Ballot measures, referenda, and party questions are structurally different from candidate races but have no dedicated model.

### 2.7 BoE Administrative Contacts

**From multiple PDF documents:**

| Role | Name | Contact |
|---|---|---|
| Chair | Robert Abbott | Signs official notices |
| Elections Supervisor | Thomas Gillon | tgillon@maconbibb.us, 478-621-6622 |
| Office Address | — | 3661 Eisenhower Pkwy, Suite MB101, Macon, GA 31206 |
| Fax | — | 478-910-2365 |
| Absentee Email | — | absentee@maconbibb.us |
| Mailing Address | — | PO Box 6297, Macon, GA 31208 |

**Gap**: No model for election administration offices or contacts. These are distinct from elected officials.

### 2.8 Precinct-to-Election Activation Mapping

The election schedule PDF specifies exactly which precincts are activated for each special election:
- SD-18 elections use 10 specific precincts across 4 super-districts (Hazzard, Howard, Rutland, Warrior)
- Commission D5 elections use 6 specific precincts across 2 super-districts (Godfrey, Vineville)

This data is critical for determining which voters are eligible to vote in which elections. It is distinct from the boundary geometry (which precincts exist) and the polling location (where to vote).

**Gap**: No model linking elections to their active precincts. Currently the system has precinct boundaries but no way to express "Precinct X participates in Election Y."

### 2.9 Absentee Ballot Processing Notices

**From the early processing PDF:**

For the Feb 17, 2026 election:
- Early processing of mailed absentee ballots authorized per O.C.G.A. section 21-2-386(a)(3)
- Processing starts: 4:00 PM on Election Day
- Location: BoE Main Office
- Results not reported until after 7:00 PM
- Official monitor/observer rules documented

**Gap**: Administrative procedural notices have no model. Low priority for the API but relevant for election transparency tracking.

---

## Part 3: Summary and Priority Assessment

### What Can Be Populated Today

| Data Category | API Model | Records | Source Document | Effort |
|---|---|---|---|---|
| 2026 elections (8 dates) | `Election` | 8 | election-schedule.pdf | Low — manual or scripted creation |
| 2025 historical elections | `Election` | 4+ | voter information PDF, website | Low |
| Feb 17 election results | `ElectionResult` | 1 | feb2026-results PDF | Low — parse PDF into JSONB |
| District boundaries | `Boundary` | Already loaded | GA SoS shapefiles | None — already done |
| Commission D5 vacancy | `ElectedOfficial` | 1 update | call-special-election.pdf | Low — update existing record |
| Voter turnout aggregates | `VoterHistory` | Existing data | GA SoS voter history | None — already importable |

### High-Value Gaps (Recommended for Future Development)

| Data Category | Why It Matters | Data Volume | Suggested Model |
|---|---|---|---|
| **Candidates** | Voters need to know who is on their ballot *before* the election | 6 named (Mar 17) + 25+ offices (full cycle) | `Candidate` with FK to `Election`, name, party, office, status |
| **Polling locations** | Core voter information — "where do I vote?" | 16+ locations with addresses & room directions | `PollingLocation` with precinct FK, address, directions, geocode |
| **Early voting sites & schedules** | Increasingly important as early voting grows | 3 sites with varying hours per election | `EarlyVotingSite` with dates, hours, per-election activation |
| **Election milestone dates** | Registration deadlines and early voting periods drive voter engagement | 5-7 dates per election | Add fields to `Election`: `registration_deadline`, `early_voting_start`, `early_voting_end`, `absentee_request_deadline`, `qualifying_start`, `qualifying_end` |
| **Precinct-to-election mapping** | Determines which voters can participate in district-specific elections | ~10-30 precincts per election | `ElectionPrecinct` join table linking `Election` to `Boundary` (precinct type) |

### Lower-Priority Gaps

| Data Category | Why It's Lower Priority | Notes |
|---|---|---|
| Qualifying periods & fees | Relevant only during filing windows; useful for candidate-facing tools | Could be fields on a `Race` or `Candidate` model |
| Ballot measures / referenda | Less frequent than candidate races; can be partially stored in `Election.name` | Would benefit from a `BallotMeasure` model |
| BoE administrative contacts | Relatively static; more directory-like than election-data | Could be a simple `ElectionOffice` model or JSON config |
| Absentee processing notices | Administrative compliance data | Low demand; could be stored as election metadata |

---

## Appendix: Source Documents

| Document | Source URL | Content |
|---|---|---|
| Precinct List (Mar 17) | `wp-content/uploads/2026/02/AsPdf_Macon-Bibb-County-Precinct-List-March-17-2026-Special-Election.pdf` | 6 polling locations for Commission D5 election |
| Election Schedule | `wp-content/uploads/2026/02/AsPdf_2026-Election-Schedule-for-MBC-Updated-1-1.pdf` | 8 election dates, precinct-to-election mappings |
| Races List | `wp-content/uploads/2026/02/AsPdf_2026-ELECTIONS-LIST-OF-RACES-ON-THE-BALLOT-CALENDAR-revisedxlsx-1.pdf` | 25+ offices across partisan and non-partisan races |
| Sample Ballot (Mar 17) | `wp-content/uploads/2026/02/SAMPLE-BALLOT-Special-Election-for-March-17-2026.pdf` | 6 candidates for Commission D5 |
| Qualifying Fees | `wp-content/uploads/2026/02/AsPdf_2026-Candidates-Qualifying-Fees-01232026-1.pdf` | 6 offices with salary and fee data |
| Call for Special Election | `wp-content/uploads/2026/02/AsPdf_Call-for-Special-Election-Comm-District-5-01232026-1.pdf` | Election call, qualifying dates, voter registration deadline |
| Legal Notification | `wp-content/uploads/2026/02/AsPdf_L-A-Legal-Notification-2026-Special-Election-Commission-District-5-March-17-2026.pdf` | L&A testing date, public notice |
| Early Processing Notice | `wp-content/uploads/2026/02/AsPdf_Notice-of-Early-Processing-for-Mailed-ABS-Ballots-for-February-2026-Special-Election.pdf` | Absentee ballot processing schedule |
| Feb 17 Results | `wp-content/uploads/2026/02/Unofficial-and-Incomplete-Special-ElectionSummary-021726.pdf` | SD-18 runoff results with vote counts |
| 2025 Voter Information | `wp-content/uploads/2025/10/2025-VOTER-INFORMATION-updated-05132025-2.pdf` | Early voting locations, schedules, contact info |
| General Precinct List (Jan 20) | `wp-content/uploads/2025/12/AsPDfMacon-Bibb-County-Precinct-List-December-2025.pdf` | 10 polling locations for SD-18 election |

All URLs are relative to `https://www.maconbibb.us/`.
