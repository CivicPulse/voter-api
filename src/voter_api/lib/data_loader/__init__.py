"""Data loader library — download and verify seed data files.

Public API for fetching the remote seed manifest and downloading
data files with checksum verification and skip-if-cached support.
"""

from voter_api.lib.data_loader.downloader import download_file, resolve_download_path
from voter_api.lib.data_loader.election_seeder import fetch_elections_from_api
from voter_api.lib.data_loader.manifest import fetch_manifest
from voter_api.lib.data_loader.types import (
    DataFileEntry,
    DownloadResult,
    FileCategory,
    SeedManifest,
    SeedResult,
)

__all__ = [
    "DataFileEntry",
    "DownloadResult",
    "FileCategory",
    "SeedManifest",
    "SeedResult",
    "download_file",
    "fetch_elections_from_api",
    "fetch_manifest",
    "resolve_download_path",
]
