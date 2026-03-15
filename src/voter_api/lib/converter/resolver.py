"""Body/Seat to boundary_type resolver.

Resolves Body IDs to boundary_type values using either the built-in
statewide mapping or county reference file lookup. The resolver is
the bridge between human-readable Body/Seat references in markdown
and machine-readable boundary_type values in JSONL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# Built-in mapping of statewide/federal Body IDs to boundary_type values.
# These resolve without needing a county reference file.
STATEWIDE_BODIES: dict[str, str | None] = {
    # Statewide constitutional officers -- no boundary_type in BoundaryType enum;
    # these are statewide offices without a specific boundary polygon.
    "ga-governor": None,
    "ga-lt-governor": None,
    "ga-sos": None,
    "ga-ag": None,
    "ga-insurance": None,
    "ga-labor": None,
    "ga-school-superintendent": None,
    "ga-agriculture": None,
    # Federal
    "ga-us-senate": "us_senate",
    "ga-us-house": "congressional",
    # State legislative
    "ga-state-senate": "state_senate",
    "ga-state-house": "state_house",
    # State commissions and courts
    "ga-psc": "psc",
    "ga-supreme-court": "judicial",
    "ga-court-of-appeals": "judicial",
    "ga-superior-court": "judicial",
}


def resolve_body(body_id: str, county_refs: dict[str, dict[str, str]]) -> str | None:
    """Resolve a Body ID to its boundary_type value.

    Checks the statewide mapping first, then searches county references.
    Returns None if the Body ID cannot be resolved.

    Args:
        body_id: The Body ID to resolve (e.g., 'ga-governor', 'bibb-boe').
        county_refs: County reference data from load_county_references().

    Returns:
        The boundary_type string, or None if unresolved.
    """
    # Check statewide bodies first
    if body_id in STATEWIDE_BODIES:
        return STATEWIDE_BODIES[body_id]

    # Search county references
    for _county, bodies in county_refs.items():
        if body_id in bodies:
            return bodies[body_id]

    return None


def parse_governing_bodies(file_path: Path) -> dict[str, str]:
    """Parse the Governing Bodies table from a county reference markdown file.

    Extracts the Body ID to boundary_type mapping from the table.
    The table format is:
        | Body Name | Body ID | Boundary Type | Election Type | Seats |

    Also handles the Bibb format with backtick-wrapped values:
        | Body ID | Name | boundary_type | Seat Pattern | Notes |

    Args:
        file_path: Path to the county reference markdown file.

    Returns:
        Dict mapping body_id to boundary_type.
    """
    text = file_path.read_text(encoding="utf-8")
    bodies: dict[str, str] = {}

    # Find the Governing Bodies section
    in_gb_section = False
    in_table = False
    header_parsed = False
    body_id_col = -1
    boundary_type_col = -1

    for line in text.splitlines():
        stripped = line.strip()

        # Detect section start
        if stripped.startswith("##") and "Governing Bodies" in stripped:
            in_gb_section = True
            continue

        # Detect next section (end of Governing Bodies)
        if in_gb_section and stripped.startswith("##") and "Governing Bodies" not in stripped:
            break

        if not in_gb_section:
            continue

        # Skip empty lines
        if not stripped:
            continue

        # Parse table rows
        if stripped.startswith("|"):
            if not in_table:
                in_table = True
                # Parse header to find column indices
                cols = [c.strip() for c in stripped.split("|")]
                # Remove empty first/last from leading/trailing |
                cols = [c for c in cols if c]

                for i, col in enumerate(cols):
                    col_lower = col.lower().strip()
                    if col_lower in ("body id", "`body id`"):
                        body_id_col = i
                    elif col_lower in (
                        "boundary type",
                        "boundary_type",
                        "`boundary_type`",
                    ):
                        boundary_type_col = i

                header_parsed = True
                continue

            # Skip separator row (|---|---|...)
            if stripped.replace("|", "").replace("-", "").replace(" ", "") == "":
                continue

            if header_parsed and body_id_col >= 0 and boundary_type_col >= 0:
                cols = [c.strip() for c in stripped.split("|")]
                cols = [c for c in cols if c]

                if len(cols) > max(body_id_col, boundary_type_col):
                    body_id = cols[body_id_col].strip().strip("`")
                    boundary_type = cols[boundary_type_col].strip().strip("`")
                    if body_id and boundary_type:
                        bodies[body_id] = boundary_type

    return bodies


def load_county_references(
    counties_dir: Path,
) -> dict[str, dict[str, str]]:
    """Load all county reference files from a directory.

    Parses each .md file in the directory and extracts governing body
    mappings. Returns a dict keyed by county slug (filename without .md).

    Args:
        counties_dir: Path to the counties directory.

    Returns:
        Dict mapping county_slug to {body_id: boundary_type} dict.
    """
    refs: dict[str, dict[str, str]] = {}

    if not counties_dir.exists():
        return refs

    for md_file in sorted(counties_dir.glob("*.md")):
        county_slug = md_file.stem
        bodies = parse_governing_bodies(md_file)
        if bodies:
            refs[county_slug] = bodies

    return refs
