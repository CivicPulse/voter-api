"""Unit tests for publisher S3/R2 storage operations."""

import json
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from voter_api.lib.publisher.storage import (
    create_r2_client,
    fetch_manifest,
    upload_file,
    upload_manifest,
    validate_config,
)

_BUCKET = "test-bucket"


@pytest.fixture
def s3_client():
    """Create a moto-mocked S3 client and bucket."""
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=_BUCKET)
        yield client


class TestCreateR2Client:
    """Tests for create_r2_client."""

    def test_returns_configured_client(self) -> None:
        """create_r2_client returns a boto3 S3 client."""
        client = create_r2_client("test-account", "test-key", "test-secret")
        assert client is not None
        assert hasattr(client, "put_object")


class TestUploadFile:
    """Tests for upload_file."""

    def test_uploads_with_correct_content_type(self, s3_client, tmp_path: Path) -> None:
        """upload_file uploads the file with correct content-type and key."""
        test_file = tmp_path / "test.geojson"
        test_file.write_text('{"type": "FeatureCollection", "features": []}')

        size = upload_file(s3_client, _BUCKET, "boundaries/test.geojson", test_file)

        assert size == test_file.stat().st_size
        obj = s3_client.get_object(Bucket=_BUCKET, Key="boundaries/test.geojson")
        assert obj["ContentType"] == "application/geo+json"

    def test_returns_file_size(self, s3_client, tmp_path: Path) -> None:
        """upload_file returns the file size in bytes."""
        test_file = tmp_path / "test.geojson"
        content = '{"type": "FeatureCollection", "features": []}'
        test_file.write_text(content)

        size = upload_file(s3_client, _BUCKET, "test.geojson", test_file)

        assert size == len(content.encode("utf-8"))


class TestUploadManifest:
    """Tests for upload_manifest."""

    def test_uploads_valid_json(self, s3_client) -> None:
        """upload_manifest uploads valid JSON to the specified key."""
        manifest = {"version": "1", "datasets": {}}

        upload_manifest(s3_client, _BUCKET, "manifest.json", manifest)

        obj = s3_client.get_object(Bucket=_BUCKET, Key="manifest.json")
        body = json.loads(obj["Body"].read().decode("utf-8"))
        assert body["version"] == "1"
        assert obj["ContentType"] == "application/json"


class TestFetchManifest:
    """Tests for fetch_manifest."""

    def test_returns_none_for_missing_manifest(self, s3_client) -> None:
        """fetch_manifest returns None when manifest doesn't exist."""
        result = fetch_manifest(s3_client, _BUCKET, "manifest.json")
        assert result is None

    def test_parses_valid_manifest(self, s3_client) -> None:
        """fetch_manifest parses a valid manifest.json."""
        manifest = {
            "version": "1",
            "published_at": "2026-02-12T15:30:00+00:00",
            "publisher_version": "0.1.0",
            "datasets": {
                "congressional": {
                    "key": "boundaries/congressional.geojson",
                    "public_url": "https://geo.example.com/boundaries/congressional.geojson",
                    "content_type": "application/geo+json",
                    "record_count": 14,
                    "file_size_bytes": 2340500,
                    "boundary_type": "congressional",
                    "filters": {"boundary_type": "congressional"},
                    "published_at": "2026-02-12T15:30:00+00:00",
                }
            },
        }
        s3_client.put_object(
            Bucket=_BUCKET,
            Key="manifest.json",
            Body=json.dumps(manifest).encode(),
        )

        result = fetch_manifest(s3_client, _BUCKET, "manifest.json")

        assert result is not None
        assert result.version == "1"
        assert result.publisher_version == "0.1.0"
        assert "congressional" in result.datasets
        ds = result.datasets["congressional"]
        assert ds.name == "congressional"
        assert ds.record_count == 14
        assert ds.file_size_bytes == 2340500


class TestValidateConfig:
    """Tests for validate_config."""

    def test_succeeds_for_valid_bucket(self, s3_client) -> None:
        """validate_config succeeds when the bucket exists."""
        validate_config(s3_client, _BUCKET)

    def test_raises_for_missing_bucket(self, s3_client) -> None:
        """validate_config raises when the bucket doesn't exist."""
        from botocore.exceptions import ClientError

        with pytest.raises(ClientError):
            validate_config(s3_client, "nonexistent-bucket")


class TestMultipartConfig:
    """Tests for TransferConfig multipart threshold."""

    def test_multipart_threshold_is_25mb(self) -> None:
        """TransferConfig uses 25 MB multipart threshold."""
        from voter_api.lib.publisher.storage import _MULTIPART_THRESHOLD

        assert _MULTIPART_THRESHOLD == 25 * 1024 * 1024
