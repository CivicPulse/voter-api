#!/usr/bin/env python3
"""Generate markdown documentation from JSONL Pydantic model schemas.

Reads model_json_schema() output from each JSONL Pydantic model and
renders field-level documentation as markdown files. Designed to be
idempotent -- running twice produces identical output.

Usage:
    uv run python tools/generate_jsonl_docs.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure the project root is on sys.path so voter_api is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from voter_api.schemas.jsonl import (  # noqa: E402
    CandidacyJSONL,
    CandidateJSONL,
    ElectionEventJSONL,
    ElectionJSONL,
)

# Model-to-filename mapping (deterministic order)
MODELS: list[tuple[type, str]] = [
    (ElectionEventJSONL, "election-events"),
    (ElectionJSONL, "elections"),
    (CandidateJSONL, "candidates"),
    (CandidacyJSONL, "candidacies"),
]

OUTPUT_DIR = PROJECT_ROOT / "docs" / "formats" / "jsonl"

# Sample values for example records, keyed by field name
SAMPLE_VALUES: dict[str, str] = {
    # ElectionEventJSONL
    "schema_version": "1",
    "id": '"550e8400-e29b-41d4-a716-446655440000"',
    "event_date": '"2026-05-19"',
    "event_name": '"May 19, 2026 - General Primary Election"',
    "event_type": '"general_primary"',
    "registration_deadline": '"2026-04-20"',
    "early_voting_start": '"2026-04-27"',
    "early_voting_end": '"2026-05-15"',
    "absentee_request_deadline": '"2026-05-08"',
    "qualifying_start": '"2026-03-02"',
    "qualifying_end": '"2026-03-06"',
    "data_source_url": '"https://results.enr.clarityelections.com/GA/..."',
    "last_refreshed_at": '"2026-05-19T20:00:00Z"',
    "refresh_interval_seconds": "300",
    # ElectionJSONL
    "election_event_id": '"660e8400-e29b-41d4-a716-446655440001"',
    "name": '"Governor - Republican Primary"',
    "name_sos": '"Governor - REP - 2026"',
    "election_date": '"2026-05-19"',
    "election_type": '"general_primary"',
    "election_stage": '"election"',
    "district": '"Statewide"',
    "boundary_type": '"state"',
    "district_identifier": '"GA"',
    "boundary_id": '"770e8400-e29b-41d4-a716-446655440002"',
    "district_party": '"R"',
    "source_name": '"Georgia Secretary of State"',
    "source": '"sos_feed"',
    "ballot_item_id": '"12345"',
    "status": '"active"',
    "eligible_county": "null",
    "eligible_municipality": "null",
    # CandidateJSONL
    "full_name": '"Jane A Smith"',
    "bio": '"Former state representative with 10 years of public service."',
    "photo_url": '"https://example.com/photos/jane-smith.jpg"',
    "email": '"jane@example.com"',
    "home_county": '"Fulton"',
    "municipality": '"Atlanta"',
    "links": '[{"link_type": "website", "url": "https://janesmith.com"}]',
    "external_ids": '{"ballotpedia": "Jane_A._Smith"}',
    # CandidacyJSONL
    "candidate_id": '"880e8400-e29b-41d4-a716-446655440003"',
    "election_id": '"990e8400-e29b-41d4-a716-446655440004"',
    "party": '"Republican"',
    "filing_status": '"qualified"',
    "is_incumbent": "false",
    "occupation": '"Attorney"',
    "qualified_date": '"2026-03-02"',
    "ballot_order": "1",
    "sos_ballot_option_id": '"OPT-67890"',
    "contest_name": '"Governor - REP - 2026"',
    # CandidateLinkJSONL (embedded)
    "link_type": '"website"',
    "url": '"https://janesmith.com"',
    "label": '"Official Campaign Site"',
}


def resolve_type(prop: dict[str, Any], defs: dict[str, Any]) -> str:
    """Resolve a JSON Schema property to a human-readable type string."""
    # Handle $ref (enum references)
    if "$ref" in prop:
        ref_name = prop["$ref"].split("/")[-1]
        ref_def = defs.get(ref_name, {})
        if "enum" in ref_def:
            return f"{ref_name} enum"
        return ref_name

    # Handle anyOf (optional types: T | null)
    if "anyOf" in prop:
        types = []
        for variant in prop["anyOf"]:
            if variant.get("type") == "null":
                continue
            if "$ref" in variant:
                ref_name = variant["$ref"].split("/")[-1]
                ref_def = defs.get(ref_name, {})
                if "enum" in ref_def:
                    types.append(f"{ref_name} enum")
                else:
                    types.append(ref_name)
            elif variant.get("type") == "string" and variant.get("format") == "uuid":
                types.append("uuid")
            elif variant.get("type") == "string" and variant.get("format") == "date":
                types.append("date")
            elif variant.get("type") == "string" and variant.get("format") == "date-time":
                types.append("datetime")
            elif variant.get("type") == "integer":
                types.append("integer")
            elif variant.get("type") == "object":
                types.append("object")
            else:
                types.append(variant.get("type", "unknown"))
        base = types[0] if types else "unknown"
        return f"{base} or null"

    # Handle array types
    if prop.get("type") == "array":
        items = prop.get("items", {})
        if "$ref" in items:
            item_name = items["$ref"].split("/")[-1]
            return f"array[{item_name}]"
        return "array"

    # Handle simple types with formats
    prop_type = prop.get("type", "unknown")
    fmt = prop.get("format")
    if fmt == "uuid":
        return "uuid"
    if fmt == "date":
        return "date"
    if fmt == "date-time":
        return "datetime"

    return prop_type


def format_default(prop: dict[str, Any], defs: dict[str, Any]) -> str:
    """Format the default value for display."""
    if "default" not in prop:
        return "--"

    default = prop["default"]
    if default is None:
        return "`null`"
    if isinstance(default, bool):
        return f"`{str(default).lower()}`"
    if isinstance(default, list):
        return "`[]`"
    if isinstance(default, str):
        # Check if it's an enum value -- look for $ref or anyOf with $ref
        ref = prop.get("$ref")
        if not ref and "anyOf" in prop:
            for variant in prop["anyOf"]:
                if "$ref" in variant:
                    ref = variant["$ref"]
                    break
        if ref:
            ref_name = ref.split("/")[-1]
            ref_def = defs.get(ref_name, {})
            if "enum" in ref_def:
                return f"`{default}`"
        return f"`{default}`"
    return f"`{default}`"


def build_example(schema: dict[str, Any], required_fields: set[str]) -> dict[str, str]:
    """Build example values dict for required fields only."""
    example: dict[str, str] = {}
    props = schema.get("properties", {})
    for field_name in props:
        if field_name in required_fields:
            example[field_name] = SAMPLE_VALUES.get(field_name, '"..."')
    return example


def generate_doc(model: type, slug: str) -> str:
    """Generate markdown documentation for a single Pydantic model."""
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})
    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    # Model name and description
    title = schema.get("title", model.__name__)
    description = schema.get("description", "")
    # Clean up description: replace literal \n with space for single paragraph
    desc_lines = description.strip().split("\n")
    # Take the first paragraph (up to first blank line)
    first_para = []
    for line in desc_lines:
        stripped = line.strip()
        if not stripped:
            break
        first_para.append(stripped)
    short_desc = " ".join(first_para)

    lines: list[str] = []

    # Header
    lines.append(f"# {title} JSONL Schema")
    lines.append("")
    lines.append(
        "<!-- Auto-generated from Pydantic model. Do not edit manually. "
        "Regenerate with: uv run python tools/generate_jsonl_docs.py -->"
    )
    lines.append("")

    # Description
    lines.append(short_desc)
    lines.append("")

    # Schema version note
    lines.append(
        "All records include a `schema_version` field (default: `1`) for "
        "forward compatibility. Increment on breaking changes."
    )
    lines.append("")

    # Field table
    lines.append("## Fields")
    lines.append("")
    lines.append("| Field | Type | Required | Default | Description |")
    lines.append("|-------|------|----------|---------|-------------|")

    for field_name, prop in props.items():
        field_type = resolve_type(prop, defs)
        is_required = field_name in required
        req_str = "Yes" if is_required else "No"
        default_str = format_default(prop, defs) if not is_required else "--"
        desc = prop.get("description", "")

        lines.append(f"| `{field_name}` | {field_type} | {req_str} | {default_str} | {desc} |")

    lines.append("")

    # Enum definitions (if any)
    if defs:
        lines.append("## Enum Definitions")
        lines.append("")
        for def_name, def_schema in sorted(defs.items()):
            if "enum" not in def_schema:
                continue
            enum_desc = def_schema.get("description", "")
            # Take first line of enum description
            enum_short = enum_desc.split("\n")[0].strip() if enum_desc else ""
            lines.append(f"### {def_name}")
            lines.append("")
            if enum_short:
                lines.append(enum_short)
                lines.append("")
            lines.append("| Value | Description |")
            lines.append("|-------|-------------|")
            for val in def_schema["enum"]:
                lines.append(f"| `{val}` | {val.replace('_', ' ').title()} |")
            lines.append("")

    # Embedded models (like CandidateLinkJSONL)
    embedded_models = {name: defn for name, defn in defs.items() if "enum" not in defn and "properties" in defn}
    if embedded_models:
        lines.append("## Embedded Models")
        lines.append("")
        for emb_name, emb_schema in sorted(embedded_models.items()):
            emb_desc = emb_schema.get("description", "")
            emb_short = emb_desc.split("\n")[0].strip() if emb_desc else ""
            emb_props = emb_schema.get("properties", {})
            emb_required = set(emb_schema.get("required", []))
            lines.append(f"### {emb_name}")
            lines.append("")
            if emb_short:
                lines.append(emb_short)
                lines.append("")
            lines.append("| Field | Type | Required | Default | Description |")
            lines.append("|-------|------|----------|---------|-------------|")
            for emb_field, emb_prop in emb_props.items():
                emb_type = resolve_type(emb_prop, defs)
                emb_is_req = emb_field in emb_required
                emb_req_str = "Yes" if emb_is_req else "No"
                emb_default = format_default(emb_prop, defs) if not emb_is_req else "--"
                emb_field_desc = emb_prop.get("description", "")
                lines.append(f"| `{emb_field}` | {emb_type} | {emb_req_str} | {emb_default} | {emb_field_desc} |")
            lines.append("")

    # Example JSONL record
    lines.append("## Example JSONL Record")
    lines.append("")
    lines.append("Minimal record showing all required fields with realistic sample values:")
    lines.append("")
    lines.append("```json")

    example = build_example(schema, required)
    # Build JSON-like string manually for deterministic output
    parts: list[str] = []
    for k, v in example.items():
        parts.append(f'  "{k}": {v}')
    lines.append("{")
    lines.append(",\n".join(parts))
    lines.append("}")

    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Generate all JSONL doc files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for model, slug in MODELS:
        doc = generate_doc(model, slug)
        output_path = OUTPUT_DIR / f"{slug}.md"
        output_path.write_text(doc)
        print(f"Generated: {output_path}")

    print(f"\nDone. {len(MODELS)} JSONL doc files generated in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
