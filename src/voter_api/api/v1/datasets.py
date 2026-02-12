"""Dataset discovery endpoint for published static datasets."""

from fastapi import APIRouter

from voter_api.core.config import get_settings
from voter_api.schemas.publish import DatasetDiscoveryResponse, DiscoveredDataset

datasets_router = APIRouter(prefix="/datasets", tags=["datasets"])


@datasets_router.get(
    "",
    response_model=DatasetDiscoveryResponse,
)
async def get_published_datasets() -> DatasetDiscoveryResponse:
    """Discover published static datasets.

    Returns the base URL for public static files and a list of
    currently published datasets with their full public URLs.
    No authentication required.
    """
    from voter_api.api.v1.boundaries import _get_manifest_cache

    settings = get_settings()

    if not settings.r2_enabled:
        return DatasetDiscoveryResponse(base_url=None, datasets=[])

    cache = _get_manifest_cache()
    manifest = cache.get_data_unchecked()

    datasets: list[DiscoveredDataset] = []
    if manifest:
        for ds in manifest.datasets.values():
            datasets.append(
                DiscoveredDataset(
                    name=ds.name,
                    url=ds.public_url,
                    boundary_type=ds.boundary_type,
                    record_count=ds.record_count,
                )
            )

    return DatasetDiscoveryResponse(
        base_url=settings.r2_public_url,
        datasets=datasets,
    )
