"""Preprocessor for GA SoS Qualified Candidates CSV.

Reads the raw CSV, resolves contest names into structured district
components (via regex then optionally AI), and outputs a JSONL template
file ready for import.
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from loguru import logger

from voter_api.lib.candidate_importer.ai_resolver import resolve_contest_names_batch
from voter_api.lib.csv_utils import detect_delimiter, detect_encoding, parse_date_mdy
from voter_api.lib.district_parser import ParsedDistrict, parse_contest_name

# Mapping from raw filing status values to normalized values
_FILING_STATUS_MAP: dict[str, str] = {
    "qualified": "qualified",
    "withdrew": "withdrawn",
    "withdrawn": "withdrawn",
    "disqualified": "disqualified",
    "deceased": "deceased",
}


@dataclass
class PreprocessResult:
    """Result of preprocessing candidates CSV.

    Attributes:
        total_records: Total number of records processed.
        resolved_regex: Number of contest names resolved by regex.
        resolved_ai: Number of contest names resolved by AI.
        needs_review: Number of records needing manual review.
        output_path: Path to the generated JSONL output file.
    """

    total_records: int
    resolved_regex: int
    resolved_ai: int
    needs_review: int
    output_path: Path


def preprocess_candidates_csv(
    input_path: Path,
    output_path: Path,
    election_date: date,
    election_type: str,
    api_key: str | None = None,
) -> PreprocessResult:
    """Preprocess a GA SoS Qualified Candidates CSV into a JSONL template.

    Reads the raw CSV, normalizes fields, resolves contest names into
    structured district components using regex-based parsing (and
    optionally AI for unresolved names), and writes a JSONL file with
    one JSON object per line.

    Args:
        input_path: Path to the raw Qualified Candidates CSV.
        output_path: Path for the output JSONL file.
        election_date: Date of the election.
        election_type: Type of election (e.g. "general_primary").
        api_key: Optional Anthropic API key for AI-based contest name
            resolution. If not provided, unresolved names are marked
            for manual review.

    Returns:
        PreprocessResult with counts and output path.
    """
    delimiter = detect_delimiter(input_path)
    encoding = detect_encoding(input_path)

    logger.info(f"Reading candidates CSV: {input_path} (encoding={encoding}, delimiter={delimiter!r})")

    df = pd.read_csv(
        input_path,
        delimiter=delimiter,
        encoding=encoding,
        dtype=str,
        keep_default_na=False,
    )

    # Normalize column names (strip whitespace, uppercase)
    df.columns = [col.strip().upper() for col in df.columns]

    records: list[dict] = []
    for _, row in df.iterrows():
        record = _normalize_row(row, election_date, election_type)
        records.append(record)

    total_records = len(records)
    logger.info(f"Preprocessor: {total_records} candidate records read")

    # Resolve contest names via regex
    unique_contests = _collect_unique_contests(records)
    regex_results, unresolved_names = _resolve_regex(unique_contests)

    resolved_regex = len(regex_results)
    logger.info(
        f"Contest names: {len(unique_contests)} unique, "
        f"{resolved_regex} resolved by regex, {len(unresolved_names)} unresolved"
    )

    # AI resolution for unresolved names
    resolved_ai = 0
    ai_results: dict[str, dict] = {}
    if unresolved_names and api_key:
        ai_records = [{"contest_name": name} for name in unresolved_names]
        resolved_records = resolve_contest_names_batch(ai_records, api_key)
        for rec in resolved_records:
            name = rec.get("contest_name", "")
            if not rec.get("_needs_manual_review"):
                ai_results[name] = rec
                resolved_ai += 1

    # Apply district fields to all records
    needs_review = 0
    for record in records:
        contest_name = record.get("contest_name", "")
        if contest_name in regex_results:
            parsed = regex_results[contest_name]
            record["district_type"] = parsed.district_type
            record["district_identifier"] = parsed.district_identifier
            record["district_party"] = parsed.party
        elif contest_name in ai_results:
            ai_rec = ai_results[contest_name]
            record["district_type"] = ai_rec.get("district_type")
            record["district_identifier"] = ai_rec.get("district_identifier")
            record["district_party"] = ai_rec.get("district_party")
        else:
            record["district_type"] = None
            record["district_identifier"] = None
            record["district_party"] = None
            record["_needs_manual_review"] = True
            needs_review += 1

    # Write JSONL output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, default=str) + "\n")

    logger.info(
        f"Preprocessor output: {output_path} "
        f"({total_records} records, {resolved_regex} regex, "
        f"{resolved_ai} AI, {needs_review} needs review)"
    )

    return PreprocessResult(
        total_records=total_records,
        resolved_regex=resolved_regex,
        resolved_ai=resolved_ai,
        needs_review=needs_review,
        output_path=output_path,
    )


def _normalize_row(row: pd.Series, election_date: date, election_type: str) -> dict:
    """Normalize a single CSV row into a candidate record dict.

    Args:
        row: Pandas Series representing one CSV row.
        election_date: Election date to attach.
        election_type: Election type to attach.

    Returns:
        Normalized record dictionary.
    """
    contest_name = str(row.get("CONTEST NAME", "")).strip()
    filing_status_raw = str(row.get("CANDIDATE STATUS", "")).strip().lower()
    qualified_date_raw = str(row.get("QUALIFIED DATE", "")).strip()
    is_incumbent_raw = str(row.get("INCUMBENT", "")).strip().upper()
    email_raw = str(row.get("EMAIL ADDRESS", "")).strip()
    website_raw = str(row.get("WEBSITE", "")).strip()

    # Parse qualified date
    qualified_date = parse_date_mdy(qualified_date_raw)
    qualified_date_str = qualified_date.isoformat() if qualified_date else None

    # Normalize filing status
    filing_status = _FILING_STATUS_MAP.get(filing_status_raw, filing_status_raw or None)

    # Normalize incumbent flag
    is_incumbent = is_incumbent_raw == "YES" if is_incumbent_raw in ("YES", "NO") else None

    # Normalize email
    email = email_raw.lower() if email_raw else None

    # Normalize website (ensure https:// prefix, validate length and hostname)
    website: str | None = None
    if website_raw:
        website = website_raw
        if website.lower().startswith("http://"):
            website = f"https://{website[len('http://') :]}"
        elif not website.lower().startswith("https://"):
            website = f"https://{website}"
        # Validate URL: must be <= 2048 chars and hostname must contain at least one dot
        if len(website) > 2048:
            logger.warning(f"Website URL exceeds 2048 characters, discarding: {website[:80]}...")
            website = None
        else:
            parsed_url = urlparse(website)
            hostname = parsed_url.hostname or ""
            if "." not in hostname:
                logger.warning(f"Website URL has invalid hostname (no dot): {website}")
                website = None

    return {
        "election_name": contest_name,
        "election_date": election_date.isoformat(),
        "election_type": election_type,
        "candidate_name": str(row.get("CANDIDATE NAME", "")).strip(),
        "party": str(row.get("POLITICAL PARTY", "")).strip() or None,
        "filing_status": filing_status,
        "is_incumbent": is_incumbent,
        "qualified_date": qualified_date_str,
        "occupation": str(row.get("OCCUPATION", "")).strip() or None,
        "email": email,
        "website": website,
        "county": str(row.get("COUNTY", "")).strip().upper() or None,
        "municipality": str(row.get("MUNICIPALITY", "")).strip() or None,
        "contest_name": contest_name,
    }


def _collect_unique_contests(records: list[dict]) -> dict[str, dict]:
    """Collect unique contest names with their first record's county/municipality.

    Args:
        records: List of candidate record dicts.

    Returns:
        Dict mapping contest name to context dict with county and municipality.
    """
    unique: dict[str, dict] = {}
    for record in records:
        name = record.get("contest_name", "")
        if name and name not in unique:
            unique[name] = {
                "county": record.get("county"),
                "municipality": record.get("municipality"),
            }
    return unique


def _resolve_regex(
    unique_contests: dict[str, dict],
) -> tuple[dict[str, ParsedDistrict], list[str]]:
    """Resolve contest names using regex-based parsing.

    Args:
        unique_contests: Dict mapping contest name to context with
            county and municipality.

    Returns:
        Tuple of (resolved_map, unresolved_names) where resolved_map
        maps contest name to ParsedDistrict and unresolved_names is a
        list of contest names that could not be parsed.
    """
    resolved: dict[str, ParsedDistrict] = {}
    unresolved: list[str] = []

    for name, context in unique_contests.items():
        parsed = parse_contest_name(
            name,
            county=context.get("county"),
            municipality=context.get("municipality"),
        )
        if parsed.district_type is not None:
            resolved[name] = parsed
        else:
            unresolved.append(name)

    return resolved, unresolved
