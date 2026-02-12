"""Unit tests for precinct metadata service batch loading."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.services.precinct_metadata_service import get_precinct_metadata_batch


class TestGetPrecinctMetadataBatch:
    """Tests for get_precinct_metadata_batch."""

    @pytest.mark.asyncio
    async def test_returns_dict_keyed_by_boundary_id(self) -> None:
        """Batch lookup returns dict mapping boundary_id to metadata."""
        boundary_id_1 = uuid.uuid4()
        boundary_id_2 = uuid.uuid4()

        meta_1 = MagicMock()
        meta_1.boundary_id = boundary_id_1

        meta_2 = MagicMock()
        meta_2.boundary_id = boundary_id_2

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [meta_1, meta_2]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        result = await get_precinct_metadata_batch(mock_session, [boundary_id_1, boundary_id_2])

        assert len(result) == 2
        assert result[boundary_id_1] is meta_1
        assert result[boundary_id_2] is meta_2

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_dict(self) -> None:
        """Empty boundary_ids list returns empty dict without querying."""
        mock_session = AsyncMock()

        result = await get_precinct_metadata_batch(mock_session, [])

        assert result == {}
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_omits_boundaries_without_metadata(self) -> None:
        """Boundaries without metadata are omitted from result dict."""
        boundary_id_1 = uuid.uuid4()
        boundary_id_2 = uuid.uuid4()

        meta_1 = MagicMock()
        meta_1.boundary_id = boundary_id_1

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [meta_1]

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result

        result = await get_precinct_metadata_batch(mock_session, [boundary_id_1, boundary_id_2])

        assert len(result) == 1
        assert boundary_id_1 in result
        assert boundary_id_2 not in result
