"""Tests for the audit logging service module."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.services.audit_service import log_access, query_audit_logs


class TestLogAccess:
    """Tests for log_access."""

    @pytest.mark.asyncio
    async def test_creates_audit_log_record(self) -> None:
        session = AsyncMock()
        user_id = uuid.uuid4()

        await log_access(
            session,
            user_id=user_id,
            username="admin",
            action="view",
            resource_type="voter",
        )

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        added_obj = session.add.call_args[0][0]
        assert added_obj.user_id == user_id
        assert added_obj.username == "admin"
        assert added_obj.action == "view"
        assert added_obj.resource_type == "voter"

    @pytest.mark.asyncio
    async def test_with_optional_fields(self) -> None:
        session = AsyncMock()
        user_id = uuid.uuid4()

        await log_access(
            session,
            user_id=user_id,
            username="analyst",
            action="export",
            resource_type="voter",
            resource_ids=["id1", "id2"],
            request_ip="192.168.1.1",
            request_endpoint="/api/v1/exports",
            request_metadata={"format": "csv"},
        )

        added_obj = session.add.call_args[0][0]
        assert added_obj.resource_ids == ["id1", "id2"]
        assert added_obj.request_ip == "192.168.1.1"
        assert added_obj.request_endpoint == "/api/v1/exports"
        assert added_obj.request_metadata == {"format": "csv"}


class TestQueryAuditLogs:
    """Tests for query_audit_logs."""

    @pytest.mark.asyncio
    async def test_returns_logs_and_count(self) -> None:
        session = AsyncMock()
        mock_log = MagicMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [mock_log]
        session.execute.side_effect = [count_result, select_result]

        logs, total = await query_audit_logs(session)
        assert total == 1
        assert len(logs) == 1

    @pytest.mark.asyncio
    async def test_filter_by_user_id(self) -> None:
        session = AsyncMock()
        user_id = uuid.uuid4()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        logs, total = await query_audit_logs(session, user_id=user_id)
        assert total == 0
        assert logs == []

    @pytest.mark.asyncio
    async def test_filter_by_action(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        logs, total = await query_audit_logs(session, action="export")
        assert total == 0

    @pytest.mark.asyncio
    async def test_filter_by_resource_type(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        logs, total = await query_audit_logs(session, resource_type="voter")
        assert total == 0

    @pytest.mark.asyncio
    async def test_filter_by_time_range(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 12, 31, tzinfo=UTC)
        logs, total = await query_audit_logs(session, start_time=start, end_time=end)
        assert total == 0

    @pytest.mark.asyncio
    async def test_pagination(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 50
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        logs, total = await query_audit_logs(session, page=3, page_size=10)
        assert total == 50

    @pytest.mark.asyncio
    async def test_all_filters_combined(self) -> None:
        session = AsyncMock()
        user_id = uuid.uuid4()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        logs, total = await query_audit_logs(
            session,
            user_id=user_id,
            action="view",
            resource_type="voter",
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
            end_time=datetime(2024, 12, 31, tzinfo=UTC),
        )
        assert total == 0
