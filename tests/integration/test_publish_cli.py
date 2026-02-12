"""Integration tests for the publish CLI command."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import boto3
import pytest
from moto import mock_aws

_BUCKET = "test-bucket"
_PUBLIC_URL = "https://geo.example.com"


def _make_mock_boundary(
    boundary_id: str = "test-id",
    name: str = "District 1",
    boundary_type: str = "congressional",
    boundary_identifier: str = "01",
    source: str = "state",
    county: str | None = None,
) -> MagicMock:
    """Create a mock Boundary ORM object."""
    mock = MagicMock()
    mock.id = boundary_id
    mock.name = name
    mock.boundary_type = boundary_type
    mock.boundary_identifier = boundary_identifier
    mock.source = source
    mock.county = county
    mock.geometry = MagicMock()
    return mock


@pytest.fixture
def s3_client():
    """Create a moto-mocked S3 client and bucket."""
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=_BUCKET)
        yield client


@pytest.fixture
def mock_settings():
    """Create mock settings for R2 configuration."""
    settings = MagicMock()
    settings.r2_enabled = True
    settings.r2_account_id = "test-account"
    settings.r2_access_key_id = "test-key"
    settings.r2_secret_access_key = "test-secret"
    settings.r2_bucket = _BUCKET
    settings.r2_public_url = _PUBLIC_URL
    settings.r2_prefix = ""
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    return settings


class TestPublishDatasetsIntegration:
    """Integration tests for the publish datasets command."""

    @pytest.mark.asyncio
    async def test_publish_uploads_all_files_and_manifest(self, s3_client) -> None:
        """Full publish creates per-type files, combined file, and manifest."""
        from voter_api.services.publish_service import publish_datasets

        boundaries = [
            _make_mock_boundary("id-1", "District 1", "congressional", "01"),
            _make_mock_boundary("id-2", "District 2", "congressional", "02"),
            _make_mock_boundary("id-3", "Senate 1", "state_senate", "01"),
        ]

        mock_shape = MagicMock()
        mock_mapping = {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]],
        }

        with (
            patch(
                "voter_api.services.publish_service.list_boundaries",
                new_callable=AsyncMock,
                return_value=(boundaries, 3),
            ),
            patch("voter_api.services.publish_service.to_shape", return_value=mock_shape),
            patch("voter_api.services.publish_service.mapping", return_value=mock_mapping),
        ):
            session = AsyncMock()
            result = await publish_datasets(
                session,
                s3_client,
                _BUCKET,
                _PUBLIC_URL,
                "",
                publisher_version="0.1.0",
            )

        # Should have per-type + combined datasets
        assert len(result.datasets) == 3  # congressional, state_senate, all-boundaries
        dataset_names = {ds.name for ds in result.datasets}
        assert "congressional" in dataset_names
        assert "state_senate" in dataset_names
        assert "all-boundaries" in dataset_names

        # Verify files exist in bucket
        objects = s3_client.list_objects_v2(Bucket=_BUCKET)
        keys = {obj["Key"] for obj in objects.get("Contents", [])}
        assert "boundaries/congressional.geojson" in keys
        assert "boundaries/state_senate.geojson" in keys
        assert "boundaries/all-boundaries.geojson" in keys
        assert "manifest.json" in keys

    @pytest.mark.asyncio
    async def test_uploaded_geojson_has_correct_structure(self, s3_client) -> None:
        """Uploaded GeoJSON files contain valid FeatureCollection with correct structure."""
        from voter_api.services.publish_service import publish_datasets

        boundaries = [
            _make_mock_boundary("id-1", "District 1", "congressional", "01", county="Fulton"),
        ]

        mock_shape = MagicMock()
        mock_mapping = {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]],
        }

        with (
            patch(
                "voter_api.services.publish_service.list_boundaries",
                new_callable=AsyncMock,
                return_value=(boundaries, 1),
            ),
            patch("voter_api.services.publish_service.to_shape", return_value=mock_shape),
            patch("voter_api.services.publish_service.mapping", return_value=mock_mapping),
        ):
            session = AsyncMock()
            await publish_datasets(session, s3_client, _BUCKET, _PUBLIC_URL, "", publisher_version="0.1.0")

        # Read and verify GeoJSON structure
        obj = s3_client.get_object(Bucket=_BUCKET, Key="boundaries/congressional.geojson")
        geojson = json.loads(obj["Body"].read().decode("utf-8"))

        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1

        feature = geojson["features"][0]
        assert feature["type"] == "Feature"
        assert feature["id"] == "id-1"
        assert feature["geometry"]["type"] == "MultiPolygon"
        props = feature["properties"]
        assert props["name"] == "District 1"
        assert props["boundary_type"] == "congressional"
        assert props["boundary_identifier"] == "01"
        assert props["source"] == "state"
        assert props["county"] == "Fulton"

    @pytest.mark.asyncio
    async def test_manifest_contains_correct_entries(self, s3_client) -> None:
        """Manifest contains entries for all uploaded datasets with correct metadata."""
        from voter_api.services.publish_service import publish_datasets

        boundaries = [
            _make_mock_boundary("id-1", "District 1", "congressional", "01"),
        ]

        mock_shape = MagicMock()
        mock_mapping = {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]],
        }

        with (
            patch(
                "voter_api.services.publish_service.list_boundaries",
                new_callable=AsyncMock,
                return_value=(boundaries, 1),
            ),
            patch("voter_api.services.publish_service.to_shape", return_value=mock_shape),
            patch("voter_api.services.publish_service.mapping", return_value=mock_mapping),
        ):
            session = AsyncMock()
            await publish_datasets(session, s3_client, _BUCKET, _PUBLIC_URL, "", publisher_version="0.1.0")

        # Read and verify manifest
        obj = s3_client.get_object(Bucket=_BUCKET, Key="manifest.json")
        manifest = json.loads(obj["Body"].read().decode("utf-8"))

        assert manifest["version"] == "1"
        assert manifest["publisher_version"] == "0.1.0"
        assert "congressional" in manifest["datasets"]
        assert "all-boundaries" in manifest["datasets"]

        entry = manifest["datasets"]["congressional"]
        assert entry["record_count"] == 1
        assert entry["file_size_bytes"] > 0
        assert entry["content_type"] == "application/geo+json"

    @pytest.mark.asyncio
    async def test_no_boundaries_reports_nothing_to_publish(self, s3_client) -> None:
        """When no boundaries exist, nothing is uploaded."""
        from voter_api.services.publish_service import publish_datasets

        with patch(
            "voter_api.services.publish_service.list_boundaries",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            session = AsyncMock()
            result = await publish_datasets(session, s3_client, _BUCKET, _PUBLIC_URL, "", publisher_version="0.1.0")

        assert result.datasets == []
        assert result.total_records == 0

        # Verify nothing was uploaded
        objects = s3_client.list_objects_v2(Bucket=_BUCKET)
        assert "Contents" not in objects

    @pytest.mark.asyncio
    async def test_storage_unreachable_reports_error(self) -> None:
        """Invalid credentials cause an error before generating files."""
        from botocore.exceptions import ClientError

        from voter_api.lib.publisher.storage import validate_config

        mock_client = MagicMock()
        mock_client.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "403", "Message": "Forbidden"}},
            "HeadBucket",
        )

        with pytest.raises(ClientError):
            validate_config(mock_client, _BUCKET)
