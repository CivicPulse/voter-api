# Bibb County

## Metadata

| Field | Value |
|-------|-------|
| County | Bibb |
| State | [Georgia](../georgia.md) |
| County Seat | Macon |
| Consolidated Government | Macon-Bibb County |
| Official Website | [maconbibb.us](https://www.maconbibb.us/) |

## Governing Bodies

| Body ID | Name | boundary_type | Seat Pattern | Notes |
|---------|------|---------------|--------------|-------|
| `bibb-boe` | Bibb County Board of Education | `school_board` | `at-large` (posts 7-8), `district-N` (1-6) | At-large seats use county boundary; districts use school_district boundary |
| `bibb-civil-magistrate` | Civil/Magistrate Court of Bibb County | `judicial` | `sole` | Single judge |
| `bibb-superior-court` | Superior Court, Macon Judicial Circuit | `judicial` | `judge-{surname}` (e.g., judge-mincey, judge-raymond, judge-smith, judge-williford) | Multi-judge court; seat ID = incumbent surname slug |
| `bibb-state-court` | State Court of Bibb County | `judicial` | `judge-{surname}` (e.g., judge-hanson, judge-lewis) | Multi-judge court; seat ID = incumbent surname slug |
| `macon-water-authority` | Macon Water Authority | `water_board` | `at-large`, `district-N` (e.g., district-1, district-4) | At-large seat uses county boundary |
