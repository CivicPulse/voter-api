"""JSON export writer for voter data."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any


class _JSONEncoder(json.JSONEncoder):
    """Custom encoder handling UUIDs, dates, and other non-serializable types."""

    def default(self, o: object) -> Any:
        import uuid
        from datetime import date, datetime

        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, date):
            return o.isoformat()
        return super().default(o)


def write_json(
    output_path: Path,
    records: Iterable[dict[str, Any]],
) -> int:
    """Write voter records to a JSON file as an array.

    Uses streaming-style writing to handle large datasets without
    holding all records in memory at once.

    Args:
        output_path: Path to write the JSON file.
        records: Iterable of voter record dicts.

    Returns:
        Number of records written.
    """
    count = 0

    with output_path.open("w", encoding="utf-8") as f:
        f.write("[\n")
        for i, record in enumerate(records):
            if i > 0:
                f.write(",\n")
            json.dump(record, f, cls=_JSONEncoder, indent=2)
            count += 1
        f.write("\n]\n")

    return count
