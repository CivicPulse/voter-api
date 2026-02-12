"""S3/R2 storage operations for static dataset publishing.

Provides boto3 client creation, file upload, manifest upload/download,
and bucket validation for Cloudflare R2 (S3-compatible) storage.
"""

import json
from datetime import UTC
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from loguru import logger

from voter_api.lib.publisher.types import DatasetEntry, ManifestData

# 25 MB multipart threshold per research.md Decision 4
_MULTIPART_THRESHOLD = 25 * 1024 * 1024
_MULTIPART_CHUNKSIZE = 25 * 1024 * 1024


def create_r2_client(
    account_id: str,
    access_key_id: str,
    secret_access_key: str,
) -> Any:
    """Create a boto3 S3 client configured for Cloudflare R2.

    Applies R2-specific configuration including the checksum workaround
    for boto3 v1.36.0+ (research.md Decision 2).

    Args:
        account_id: Cloudflare R2 account ID.
        access_key_id: R2 API token access key.
        secret_access_key: R2 API token secret key.

    Returns:
        Configured boto3 S3 client.
    """
    config = Config(
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    )

    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
        config=config,
    )


def upload_file(
    client: Any,
    bucket: str,
    key: str,
    file_path: Path,
    content_type: str = "application/geo+json",
) -> int:
    """Upload a file to R2/S3.

    Uses TransferConfig with 25 MB multipart threshold for large files.

    Args:
        client: boto3 S3 client.
        bucket: Bucket name.
        key: S3 object key.
        file_path: Local file path to upload.
        content_type: MIME type for the uploaded file.

    Returns:
        File size in bytes.
    """
    from boto3.s3.transfer import TransferConfig

    transfer_config = TransferConfig(
        multipart_threshold=_MULTIPART_THRESHOLD,
        multipart_chunksize=_MULTIPART_CHUNKSIZE,
        max_concurrency=4,
        use_threads=True,
    )

    file_size = file_path.stat().st_size
    logger.info("Uploading {} ({} bytes) to s3://{}/{}", file_path.name, file_size, bucket, key)

    client.upload_file(
        str(file_path),
        bucket,
        key,
        Config=transfer_config,
        ExtraArgs={"ContentType": content_type},
    )

    return file_size


def upload_manifest(client: Any, bucket: str, key: str, manifest_data: dict[str, Any]) -> None:
    """Upload manifest JSON to R2/S3.

    Args:
        client: boto3 S3 client.
        bucket: Bucket name.
        key: S3 object key for the manifest.
        manifest_data: Manifest dict to serialize as JSON.
    """
    body = json.dumps(manifest_data, indent=2, default=str)
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body.encode("utf-8"),
        ContentType="application/json",
    )
    logger.info("Uploaded manifest to s3://{}/{}", bucket, key)


def fetch_manifest(client: Any, bucket: str, key: str) -> ManifestData | None:
    """Download and parse manifest.json from R2/S3.

    Args:
        client: boto3 S3 client.
        bucket: Bucket name.
        key: S3 object key for the manifest.

    Returns:
        Parsed ManifestData, or None if not found.
    """
    from datetime import datetime

    try:
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read().decode("utf-8")
        data = json.loads(body)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            logger.debug("No manifest found at s3://{}/{}", bucket, key)
            return None
        raise

    datasets: dict[str, DatasetEntry] = {}
    for name, entry_data in data.get("datasets", {}).items():
        published_at_str = entry_data.get("published_at", "")
        try:
            published_at = datetime.fromisoformat(published_at_str)
        except (ValueError, TypeError):
            published_at = datetime.now(tz=UTC)

        datasets[name] = DatasetEntry(
            name=name,
            key=entry_data.get("key", ""),
            public_url=entry_data.get("public_url", ""),
            content_type=entry_data.get("content_type", "application/geo+json"),
            record_count=entry_data.get("record_count", 0),
            file_size_bytes=entry_data.get("file_size_bytes", 0),
            boundary_type=entry_data.get("boundary_type"),
            filters=entry_data.get("filters", {}),
            published_at=published_at,
        )

    published_at_str = data.get("published_at", "")
    try:
        manifest_published_at = datetime.fromisoformat(published_at_str)
    except (ValueError, TypeError):
        manifest_published_at = datetime.now(tz=UTC)

    return ManifestData(
        version=data.get("version", "1"),
        published_at=manifest_published_at,
        publisher_version=data.get("publisher_version", ""),
        datasets=datasets,
    )


def validate_config(client: Any, bucket: str) -> None:
    """Verify bucket access before publishing.

    Args:
        client: boto3 S3 client.
        bucket: Bucket name to validate.

    Raises:
        ClientError: If the bucket doesn't exist or credentials are invalid.
    """
    try:
        client.head_bucket(Bucket=bucket)
        logger.debug("Bucket s3://{} is accessible", bucket)
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "404":
            msg = f"Bucket '{bucket}' not found. Verify R2_BUCKET is correct."
            raise ClientError(exc.response, "HeadBucket") from ValueError(msg)
        if error_code in ("403", "401"):
            msg = f"Access denied to bucket '{bucket}'. Verify R2 credentials."
            raise ClientError(exc.response, "HeadBucket") from PermissionError(msg)
        raise
