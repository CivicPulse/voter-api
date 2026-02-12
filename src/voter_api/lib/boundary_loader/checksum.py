"""SHA512 checksum verification for boundary data files."""

import hashlib
from pathlib import Path

from loguru import logger

# Read buffer size for hashing large files
_CHUNK_SIZE = 8192


def verify_sha512(file_path: Path) -> bool:
    """Verify a file's SHA512 checksum against its companion checksum file.

    Looks for ``<file_path>.sha512.txt`` containing a line in the format
    ``<hash>  <filename>`` (GNU coreutils style).

    Args:
        file_path: Path to the file to verify.

    Returns:
        True if the checksum matches or no checksum file exists.

    Raises:
        ValueError: If the checksum does not match.
    """
    checksum_path = file_path.parent / f"{file_path.name}.sha512.txt"

    if not checksum_path.exists():
        logger.warning(f"No checksum file found for {file_path.name}, skipping verification")
        return True

    checksum_text = checksum_path.read_text().strip()
    expected_hash = checksum_text.split()[0].lower()

    sha512 = hashlib.sha512()
    with file_path.open("rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            sha512.update(chunk)

    actual_hash = sha512.hexdigest().lower()

    if actual_hash != expected_hash:
        msg = f"SHA512 mismatch for {file_path.name}: expected {expected_hash[:16]}..., got {actual_hash[:16]}..."
        raise ValueError(msg)

    logger.debug(f"SHA512 verified for {file_path.name}")
    return True
