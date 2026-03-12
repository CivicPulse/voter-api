"""AI-powered contest name resolution using Anthropic Claude.

Resolves unrecognized GA SoS contest names into structured district
components when regex-based parsing fails. Provides graceful degradation
when the API is unavailable.
"""

import json
import re
import time

from loguru import logger

# Import anthropic exception types with guard for environments where
# the package is not installed (e.g. lightweight test images).
try:
    from anthropic import (
        APIConnectionError as AnthropicConnectionError,
    )
    from anthropic import (
        AuthenticationError as AnthropicAuthError,
    )
    from anthropic import (
        BadRequestError as AnthropicBadRequestError,
    )
    from anthropic import (
        RateLimitError as AnthropicRateLimitError,
    )

    _HAS_ANTHROPIC_ERRORS = True
except ImportError:  # pragma: no cover
    _HAS_ANTHROPIC_ERRORS = False

_BATCH_SIZE = 50

_SYSTEM_PROMPT = """You are a Georgia elections data expert. Given a list of contest names \
from the GA Secretary of State Qualified Candidates CSV, classify each into a structured \
district type.

Return a JSON array where each element has:
- "contest_name": the original contest name (exactly as given)
- "district_type": one of: congressional, us_senate, state_senate, state_house, psc, \
statewide, judicial, board_of_education, county_commission, county_office, municipal
- "district_identifier": the district/seat/post number as a string, or null if not applicable
- "district_party": full party name (e.g. "Republican", "Democrat", "Nonpartisan") or null

IMPORTANT: Return ONLY the JSON array, no other text.

Examples:
Input: ["U.S House of Representatives, District 11 (R)", "Governor (D)", \
"Superior Court Judge, Blue Ridge Judicial Circuit (NP)", \
"Bibb County Commission, District 2 (R)", "State School Superintendent (R)"]

Output:
[
  {"contest_name": "U.S House of Representatives, District 11 (R)", \
"district_type": "congressional", "district_identifier": "11", "district_party": "Republican"},
  {"contest_name": "Governor (D)", "district_type": "statewide", \
"district_identifier": null, "district_party": "Democrat"},
  {"contest_name": "Superior Court Judge, Blue Ridge Judicial Circuit (NP)", \
"district_type": "judicial", "district_identifier": null, "district_party": "Nonpartisan"},
  {"contest_name": "Bibb County Commission, District 2 (R)", \
"district_type": "county_commission", "district_identifier": "2", \
"district_party": "Republican"},
  {"contest_name": "State School Superintendent (R)", "district_type": "statewide", \
"district_identifier": null, "district_party": "Republican"}
]"""


def _sanitize_contest_name(name: str) -> str:
    """Sanitize a contest name for safe inclusion in AI prompts.

    Truncates to 200 characters and strips control characters to prevent
    prompt injection or malformed API requests.

    Args:
        name: Raw contest name string.

    Returns:
        Sanitized contest name.
    """
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", name)
    return cleaned[:200]


def resolve_contest_names_batch(
    unresolved: list[dict],
    api_key: str,
) -> list[dict]:
    """Resolve unrecognized contest names using the Anthropic Claude API.

    Deduplicates contest names, batches API calls (up to 50 unique names
    per request), and maps results back to all matching records. Falls back
    gracefully by marking records with ``_needs_manual_review: True`` if
    the API call fails.

    Args:
        unresolved: List of record dicts, each containing at least a
            ``contest_name`` key.
        api_key: Anthropic API key for authentication.

    Returns:
        The same list of record dicts with ``district_type``,
        ``district_identifier``, and ``district_party`` fields added.
        Records that could not be resolved have
        ``_needs_manual_review: True``.
    """
    if not unresolved:
        return unresolved

    # Deduplicate and sanitize contest names
    unique_names: list[str] = list(
        dict.fromkeys(_sanitize_contest_name(r["contest_name"]) for r in unresolved if r.get("contest_name"))
    )

    if not unique_names:
        return _mark_needs_review(unresolved)

    # Resolve in batches
    resolution_map: dict[str, dict] = {}
    for i in range(0, len(unique_names), _BATCH_SIZE):
        batch = unique_names[i : i + _BATCH_SIZE]
        batch_results = _call_api(batch, api_key)
        if batch_results is not None:
            for result in batch_results:
                name = result.get("contest_name", "")
                resolution_map[name] = result

    # Apply resolutions back to records
    for record in unresolved:
        contest_name = record.get("contest_name", "")
        if contest_name in resolution_map:
            resolved = resolution_map[contest_name]
            record["district_type"] = resolved.get("district_type")
            record["district_identifier"] = resolved.get("district_identifier")
            record["district_party"] = resolved.get("district_party")
        else:
            record["_needs_manual_review"] = True

    return unresolved


_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = [2, 4, 8]


def _call_api(contest_names: list[str], api_key: str) -> list[dict] | None:
    """Call the Anthropic API to resolve a batch of contest names.

    Handles specific Anthropic error types:
    - Authentication / bad request errors: log and return None (no retry).
    - Rate limit / connection errors: retry up to 3 times with exponential backoff.
    - Other exceptions: log warning and return None.

    Args:
        contest_names: List of unique contest name strings.
        api_key: Anthropic API key.

    Returns:
        Parsed list of resolution dicts, or None on failure.
    """
    import anthropic  # noqa: PLC0415

    for attempt in range(_MAX_RETRIES):
        try:
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(contest_names),
                    }
                ],
            )

            # Extract text content from response
            response_text = ""
            for block in message.content:
                if hasattr(block, "text"):
                    response_text += block.text

            # Parse JSON response
            results = json.loads(response_text)
            if isinstance(results, list):
                return results

            logger.warning(f"AI resolver returned non-list response: {type(results)}")
            return None

        except Exception as exc:
            # Route to specific handlers when anthropic types are available
            if _HAS_ANTHROPIC_ERRORS:
                if isinstance(exc, (AnthropicAuthError, AnthropicBadRequestError)):
                    logger.error(
                        f"AI resolver authentication/request error: {exc}. "
                        "Check your Anthropic API key and request parameters."
                    )
                    return None

                if isinstance(exc, (AnthropicRateLimitError, AnthropicConnectionError)):
                    backoff = (
                        _RETRY_BACKOFF_SECONDS[attempt]
                        if attempt < len(_RETRY_BACKOFF_SECONDS)
                        else _RETRY_BACKOFF_SECONDS[-1]
                    )
                    logger.warning(
                        f"AI resolver transient error (attempt {attempt + 1}/{_MAX_RETRIES}): "
                        f"{exc}. Retrying in {backoff}s..."
                    )
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(backoff)
                        continue
                    logger.error(f"AI resolver failed after {_MAX_RETRIES} retries: {exc}")
                    return None

            # Unknown / unexpected exception
            logger.warning(f"AI resolver unexpected error: {exc}")
            return None

    return None  # pragma: no cover


def _mark_needs_review(records: list[dict]) -> list[dict]:
    """Mark all records as needing manual review.

    Args:
        records: List of record dicts.

    Returns:
        The same records with ``_needs_manual_review: True`` set.
    """
    for record in records:
        record["_needs_manual_review"] = True
    return records
