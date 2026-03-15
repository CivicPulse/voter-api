"""Generate candidates.jsonl and candidacies.jsonl from candidate markdown files.

Reads all data/candidates/*.md files, parses candidate metadata and election
sections, resolves election_id from contest file UUIDs, and writes output
to per-election jsonl/ directories.

Usage:
    uv run python scripts/generate_candidate_jsonl.py

Output:
    data/elections/<date>/jsonl/candidates.jsonl
    data/elections/<date>/jsonl/candidacies.jsonl
"""

import json
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

# Add project root to path so we can import from voter_api
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from voter_api.schemas.jsonl.candidate import CandidateJSONL, CandidateLinkJSONL
from voter_api.schemas.jsonl.candidacy import CandidacyJSONL
from voter_api.schemas.jsonl.enums import FilingStatus, LinkType

CANDIDATES_DIR = PROJECT_ROOT / "data" / "candidates"
ELECTIONS_DIR = PROJECT_ROOT / "data" / "elections"

# Namespace UUID for deterministic candidacy IDs (v5)
_CANDIDACY_NAMESPACE = uuid.UUID("c0ffee00-dead-beef-cafe-000000000000")

# Em-dash variants to treat as None
_EMPTY_VALUES = {"—", "-", "--", ""}


def _is_empty(value: str) -> bool:
    """Return True if value is an em-dash or empty placeholder."""
    return value.strip() in _EMPTY_VALUES


def _extract_metadata_table(content: str) -> dict[str, str]:
    """Extract key-value pairs from the ## Metadata table.

    Args:
        content: Full markdown file content.

    Returns:
        Dict of field name -> value string.
    """
    result: dict[str, str] = {}
    # Find the Metadata section
    meta_match = re.search(r"## Metadata\s*\n", content)
    if not meta_match:
        return result

    # Find the table rows after the header separator
    table_section = content[meta_match.end() :]
    # Match table rows: | Field | Value |
    for line in table_section.split("\n"):
        row = re.match(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|?\s*$", line)
        if row:
            field = row.group(1).strip()
            value = row.group(2).strip()
            # Skip header and separator rows
            if field in ("Field", "---", "-------", "----") or "---" in field:
                continue
            result[field] = value
        elif line.startswith("##") and line != "## Metadata":
            break
    return result


def _extract_section_content(content: str, section_heading: str) -> str:
    """Extract the content of a markdown section by heading.

    Args:
        content: Full markdown file content.
        section_heading: The ## heading text to find (e.g., "## Bio").

    Returns:
        Content between the heading and next ## heading, stripped.
    """
    pattern = re.compile(
        rf"{re.escape(section_heading)}\s*\n(.*?)(?=\n##|\Z)",
        re.DOTALL,
    )
    match = pattern.search(content)
    if match:
        return match.group(1).strip()
    return ""


def _extract_bio(content: str) -> str | None:
    """Extract bio text from ## Bio section."""
    bio = _extract_section_content(content, "## Bio")
    return None if _is_empty(bio) else bio


def _extract_external_ids(content: str) -> dict[str, str] | None:
    """Extract external IDs from ## External IDs table."""
    section = _extract_section_content(content, "## External IDs")
    if not section:
        return None

    result: dict[str, str] = {}
    for line in section.split("\n"):
        row = re.match(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|?\s*$", line)
        if row:
            source = row.group(1).strip()
            ext_id = row.group(2).strip()
            # Skip header/separator rows
            if source in ("Source", "---", "------") or "---" in source:
                continue
            if not _is_empty(ext_id):
                # Normalize source name to lowercase key
                key = source.lower().replace(" ", "_")
                result[key] = ext_id

    return result if result else None


def _extract_links(content: str) -> list[CandidateLinkJSONL]:
    """Extract links from ## Links table.

    Maps 'email' link type to 'other' since email is not a valid LinkType.
    """
    section = _extract_section_content(content, "## Links")
    if not section:
        return []

    links: list[CandidateLinkJSONL] = []
    for line in section.split("\n"):
        row = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|?\s*$", line)
        if row:
            link_type_raw = row.group(1).strip().lower()
            url = row.group(2).strip()
            label = row.group(3).strip() or None

            # Skip header/separator rows
            if link_type_raw in ("type", "---", "----") or "---" in link_type_raw:
                continue
            if not url or _is_empty(url):
                continue

            # Map 'email' to 'other' -- email is NOT a valid LinkType
            if link_type_raw == "email":
                link_type_raw = "other"

            try:
                link_type = LinkType(link_type_raw)
            except ValueError:
                # Unknown link type -> other
                link_type = LinkType.OTHER

            links.append(CandidateLinkJSONL(link_type=link_type, url=url, label=label))

    return links


def _extract_election_sections(content: str) -> list[dict[str, str]]:
    """Extract election subsections from ## Elections section.

    Returns:
        List of dicts with keys: heading, election_id, contest_file,
        party, occupation, filing_status, qualified_date, is_incumbent.
    """
    elections_match = re.search(r"## Elections\s*\n", content)
    if not elections_match:
        return []

    elections_content = content[elections_match.end() :]

    # Find all ### sub-headings
    sections = re.split(r"(?=^### )", elections_content, flags=re.MULTILINE)

    result = []
    for section in sections:
        heading_match = re.match(r"^### (.+)$", section, re.MULTILINE)
        if not heading_match:
            continue

        heading = heading_match.group(1).strip()

        # Extract table rows from the section
        fields: dict[str, str] = {}
        for line in section.split("\n"):
            row = re.match(r"^\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|?\s*$", line)
            if row:
                field = row.group(1).strip()
                value = row.group(2).strip()
                if field in ("Field", "---", "-------") or "---" in field:
                    continue
                fields[field] = value

        # Extract Contest File path from markdown link
        contest_file_raw = fields.get("Contest File", "")
        contest_file_match = re.search(r"\[.*?\]\((.*?)\)", contest_file_raw)
        contest_file = contest_file_match.group(1) if contest_file_match else ""

        result.append(
            {
                "heading": heading,
                "election_id": fields.get("Election ID", ""),
                "contest_file": contest_file,
                "party": fields.get("Party", ""),
                "occupation": fields.get("Occupation", ""),
                "filing_status": fields.get("Filing Status", "qualified"),
                "qualified_date": fields.get("Qualified Date", ""),
                "is_incumbent": fields.get("Is Incumbent", "No"),
            }
        )

    return result


def _resolve_election_id(contest_file: str) -> tuple[str | None, str | None]:
    """Resolve election_id by reading the contest file's ID field.

    Args:
        contest_file: Relative path from data/candidates/ to the contest file.

    Returns:
        Tuple of (election_id_str, election_date_prefix) or (None, None) if
        the file can't be read or ID is empty.
    """
    if not contest_file:
        return None, None

    # Resolve relative to data/candidates/
    contest_path = CANDIDATES_DIR / contest_file
    if not contest_path.exists():
        return None, None

    content = contest_path.read_text(encoding="utf-8")

    # Extract ID from metadata table
    id_match = re.search(r"\|\s*ID\s*\|\s*(.*?)\s*\|", content)
    if not id_match:
        return None, None

    id_val = id_match.group(1).strip()
    if _is_empty(id_val):
        return None, None

    # Validate it's a UUID
    try:
        uuid.UUID(id_val)
    except ValueError:
        return None, None

    # Extract election date from filename prefix (e.g., 2026-03-17)
    date_match = re.match(r"(\d{4}-\d{2}-\d{2})", contest_path.stem)
    election_date = date_match.group(1) if date_match else None

    return id_val, election_date


def _parse_filing_status(raw: str) -> FilingStatus:
    """Parse filing status string to FilingStatus enum."""
    try:
        return FilingStatus(raw.lower().strip())
    except ValueError:
        return FilingStatus.QUALIFIED


def _parse_qualified_date(raw: str) -> str | None:
    """Convert MM/DD/YYYY to YYYY-MM-DD or return None."""
    if _is_empty(raw):
        return None
    mm_dd_yyyy = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", raw.strip())
    if mm_dd_yyyy:
        return f"{mm_dd_yyyy.group(3)}-{mm_dd_yyyy.group(1)}-{mm_dd_yyyy.group(2)}"
    # Try ISO format already
    iso_match = re.match(r"^\d{4}-\d{2}-\d{2}$", raw.strip())
    if iso_match:
        return raw.strip()
    return None


def _parse_is_incumbent(raw: str) -> bool:
    """Parse Yes/No string to bool."""
    return raw.strip().lower() == "yes"


def main() -> None:
    """Parse candidate markdown files and write JSONL output per election date."""
    candidate_files = sorted(CANDIDATES_DIR.glob("*.md"))

    # Track output per election date
    # election_date -> {"candidates": [...], "candidacies": [...]}
    by_election: defaultdict[str, dict[str, list]] = defaultdict(lambda: {"candidates": [], "candidacies": []})

    # Track stats
    total_candidates = 0
    total_candidacies = 0
    validation_errors: list[str] = []
    skipped_no_id: list[str] = []
    skipped_no_election_id: list[str] = []

    # Track candidate IDs we've already added per election date to avoid duplicates
    added_candidate_ids: defaultdict[str, set] = defaultdict(set)

    for md_file in candidate_files:
        content = md_file.read_text(encoding="utf-8")
        meta = _extract_metadata_table(content)

        # Extract required fields
        candidate_id_raw = meta.get("ID", "")
        if _is_empty(candidate_id_raw):
            skipped_no_id.append(md_file.name)
            continue

        try:
            candidate_id = uuid.UUID(candidate_id_raw)
        except ValueError:
            validation_errors.append(f"{md_file.name}: Invalid candidate ID: {candidate_id_raw!r}")
            continue

        full_name = meta.get("Name", "")
        photo_url_raw = meta.get("Photo URL", "")
        email_raw = meta.get("Email", "")

        photo_url = None if _is_empty(photo_url_raw) else photo_url_raw
        email = None if _is_empty(email_raw) else email_raw

        bio = _extract_bio(content)
        external_ids = _extract_external_ids(content)
        links = _extract_links(content)

        # Build CandidateJSONL (validated below per election)
        candidate_data = {
            "schema_version": 1,
            "id": candidate_id,
            "full_name": full_name,
            "bio": bio,
            "photo_url": photo_url,
            "email": email,
            "links": [lnk.model_dump() for lnk in links],
            "external_ids": external_ids,
        }

        # Process election sections
        election_sections = _extract_election_sections(content)

        for section in election_sections:
            contest_file = section["contest_file"]
            election_id_str, election_date = _resolve_election_id(contest_file)

            if not election_id_str or not election_date:
                skipped_no_election_id.append(f"{md_file.name} -> {contest_file} (UUID not populated)")
                continue

            try:
                election_id = uuid.UUID(election_id_str)
            except ValueError:
                validation_errors.append(f"{md_file.name}: Invalid election ID in {contest_file}: {election_id_str!r}")
                continue

            # Generate deterministic candidacy ID from candidate + election
            candidacy_id = uuid.uuid5(
                _CANDIDACY_NAMESPACE,
                f"{candidate_id}:{election_id}",
            )

            # Parse contest-specific fields
            party_raw = section["party"]
            party = None if _is_empty(party_raw) else party_raw

            occupation_raw = section["occupation"]
            occupation = None if _is_empty(occupation_raw) else occupation_raw

            filing_status = _parse_filing_status(section["filing_status"])
            qualified_date_str = _parse_qualified_date(section["qualified_date"])
            is_incumbent = _parse_is_incumbent(section["is_incumbent"])

            # Validate CandidacyJSONL
            try:
                candidacy = CandidacyJSONL.model_validate(
                    {
                        "schema_version": 1,
                        "id": candidacy_id,
                        "candidate_id": candidate_id,
                        "election_id": election_id,
                        "party": party,
                        "filing_status": filing_status,
                        "is_incumbent": is_incumbent,
                        "occupation": occupation,
                        "qualified_date": qualified_date_str,
                        "contest_name": section["heading"],
                    }
                )
            except Exception as e:
                validation_errors.append(f"{md_file.name} candidacy validation error: {e}")
                continue

            # Add candidate to election bucket (once per election date)
            if candidate_id not in added_candidate_ids[election_date]:
                try:
                    candidate = CandidateJSONL.model_validate(candidate_data)
                    by_election[election_date]["candidates"].append(json.loads(candidate.model_dump_json()))
                    added_candidate_ids[election_date].add(candidate_id)
                    total_candidates += 1
                except Exception as e:
                    validation_errors.append(f"{md_file.name} candidate validation error: {e}")

            by_election[election_date]["candidacies"].append(json.loads(candidacy.model_dump_json()))
            total_candidacies += 1

    # Write output per election date
    print("\nWriting JSONL output...")
    for election_date, data in sorted(by_election.items()):
        jsonl_dir = ELECTIONS_DIR / election_date / "jsonl"
        jsonl_dir.mkdir(parents=True, exist_ok=True)

        # Write candidates.jsonl
        candidates_path = jsonl_dir / "candidates.jsonl"
        with candidates_path.open("w", encoding="utf-8") as f:
            for record in data["candidates"]:
                f.write(json.dumps(record) + "\n")
        print(f"  {candidates_path}: {len(data['candidates'])} candidates")

        # Write candidacies.jsonl
        candidacies_path = jsonl_dir / "candidacies.jsonl"
        with candidacies_path.open("w", encoding="utf-8") as f:
            for record in data["candidacies"]:
                f.write(json.dumps(record) + "\n")
        print(f"  {candidacies_path}: {len(data['candidacies'])} candidacies")

    # Summary
    print("\nSummary:")
    print(f"  Total candidates processed: {total_candidates}")
    print(f"  Total candidacies processed: {total_candidacies}")
    print(f"  Election dates: {', '.join(sorted(by_election.keys()))}")

    if skipped_no_id:
        print(f"\nSkipped (no candidate ID): {len(skipped_no_id)}")
        for s in skipped_no_id:
            print(f"  - {s}")

    if skipped_no_election_id:
        print(f"\nSkipped (contest file UUID not populated): {len(skipped_no_election_id)}")
        for s in skipped_no_election_id:
            print(f"  - {s}")

    if validation_errors:
        print(f"\nValidation errors: {len(validation_errors)}")
        for e in validation_errors:
            print(f"  ERROR: {e}")
        sys.exit(1)
    else:
        print("\nAll records validated successfully.")


if __name__ == "__main__":
    main()
