"""Golden file tests for the normalizer.

Proves before/after transformations for all four markdown file types
(overview, single-contest, multi-contest, candidate) and verifies
idempotency: running the normalizer on already-normalized output
produces zero changes.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from voter_api.lib.normalizer import normalize_file

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_GOLDEN_CASES = [
    pytest.param(
        "2026-05-19-general-primary.md",
        "2026-05-19-general-primary.md",
        id="overview",
    ),
    pytest.param(
        "2026-05-19-governor.md",
        "2026-05-19-governor.md",
        id="single-contest",
    ),
    pytest.param(
        "counties/2026-05-19-bibb.md",
        "counties/2026-05-19-bibb.md",
        id="multi-contest",
    ),
    pytest.param(
        "candidates/jane-doe-00000000.md",
        "candidates/jane-doe-00000000.md",
        id="candidate",
    ),
]


def _fixtures_dir() -> Path:
    """Return the path to the normalizer fixtures directory.

    Returns:
        Path to tests/fixtures/normalizer/.
    """
    return Path(__file__).parent.parent.parent.parent / "fixtures" / "normalizer"


# ---------------------------------------------------------------------------
# TestGoldenFiles
# ---------------------------------------------------------------------------


class TestGoldenFiles:
    """Before/after golden file tests with idempotency verification."""

    @pytest.mark.parametrize("before_rel,after_rel", _GOLDEN_CASES)
    def test_normalize_matches_expected(
        self,
        before_rel: str,
        after_rel: str,
        tmp_path: Path,
    ) -> None:
        """Normalizing the 'before' file produces the 'after' content exactly.

        Copies the before fixture to a temp directory (preserving the
        relative path so file type detection works), runs normalize_file,
        then compares output to the 'after' fixture.
        """
        fixtures = _fixtures_dir()
        before_src = fixtures / "before" / before_rel
        after_src = fixtures / "after" / after_rel

        # Copy before file to tmp_path preserving relative structure
        dest = tmp_path / before_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(before_src, dest)

        # Normalize in place
        result = normalize_file(dest)

        assert not result.errors, f"Unexpected errors: {result.errors}"

        # Compare to golden after content
        normalized_content = dest.read_text(encoding="utf-8")
        expected_content = after_src.read_text(encoding="utf-8")

        assert normalized_content == expected_content, (
            f"Normalized output does not match golden file for {before_rel}.\n"
            f"Changes made: {len(result.changes)}\n"
            f"First diff line: {_first_diff_line(normalized_content, expected_content)}"
        )

    @pytest.mark.parametrize("before_rel,after_rel", _GOLDEN_CASES)
    def test_idempotency(
        self,
        before_rel: str,
        after_rel: str,
        tmp_path: Path,
    ) -> None:
        """Running normalizer on 'after' (already normalized) produces zero changes.

        This verifies that the normalization rules are truly idempotent:
        applying them twice gives the same result as applying once.
        """
        fixtures = _fixtures_dir()
        after_src = fixtures / "after" / after_rel

        # Copy after file to tmp_path
        dest = tmp_path / after_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(after_src, dest)

        original_content = dest.read_text(encoding="utf-8")

        # Run normalizer on already-normalized file
        result = normalize_file(dest)

        assert not result.errors, f"Unexpected errors on already-normalized file: {result.errors}"
        assert len(result.changes) == 0, (
            f"Normalizing already-normalized {after_rel} produced {len(result.changes)} change(s):\n"
            + "\n".join(f"  [{c.field_name}] {c.original!r} -> {c.normalized!r}" for c in result.changes)
        )

        # Content should not change
        normalized_content = dest.read_text(encoding="utf-8")
        assert normalized_content == original_content, f"Content of already-normalized {after_rel} changed unexpectedly"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_diff_line(actual: str, expected: str) -> str:
    """Return a description of the first differing line between two strings.

    Args:
        actual: The actual normalized content.
        expected: The expected content from the golden file.

    Returns:
        Human-readable string describing the first difference.
    """
    actual_lines = actual.splitlines()
    expected_lines = expected.splitlines()
    for i, (a, e) in enumerate(zip(actual_lines, expected_lines, strict=False), 1):
        if a != e:
            return f"Line {i}: actual={a!r}, expected={e!r}"
    if len(actual_lines) != len(expected_lines):
        return f"Line count: actual={len(actual_lines)}, expected={len(expected_lines)}"
    return "No differences found (content is identical)"
