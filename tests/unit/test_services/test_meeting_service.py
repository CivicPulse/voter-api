"""Unit tests for meeting service layer."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.models.meeting import ApprovalStatus
from voter_api.services.meeting_service import (
    approve_meeting,
    create_meeting,
    delete_meeting,
    get_child_counts,
    get_meeting,
    list_meetings,
    reject_meeting,
    update_meeting,
)


def _mock_user(role: str = "admin") -> MagicMock:
    """Create a mock user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = f"test{role}"
    user.role = role
    return user


def _mock_session(
    scalar_one_value=0,
    scalar_one_or_none_value=None,
    scalars_all_value=None,
) -> AsyncMock:
    """Create a mock async session."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = scalar_one_value
    mock_result.scalar_one_or_none.return_value = scalar_one_or_none_value
    mock_result.scalars.return_value.all.return_value = scalars_all_value or []
    session.execute.return_value = mock_result
    return session


def _mock_meeting(**overrides) -> MagicMock:
    """Create a mock Meeting."""
    defaults = {
        "id": uuid.uuid4(),
        "governing_body_id": uuid.uuid4(),
        "meeting_date": datetime.now(UTC),
        "location": "City Hall",
        "meeting_type": "regular",
        "status": "scheduled",
        "external_source_url": None,
        "approval_status": ApprovalStatus.APPROVED,
        "submitted_by": uuid.uuid4(),
        "approved_by": None,
        "approved_at": None,
        "rejection_reason": None,
        "deleted_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "governing_body": MagicMock(name="Test Body"),
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


class TestListMeetings:
    """Tests for list_meetings."""

    @pytest.mark.asyncio
    async def test_no_filters(self) -> None:
        session = _mock_session()
        meetings, total = await list_meetings(session)
        assert meetings == []
        assert total == 0
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_with_filters(self) -> None:
        session = _mock_session()
        await list_meetings(
            session,
            governing_body_id=uuid.uuid4(),
            meeting_type="regular",
            status="scheduled",
        )
        assert session.execute.call_count == 2


class TestGetMeeting:
    """Tests for get_meeting."""

    @pytest.mark.asyncio
    async def test_found(self) -> None:
        meeting = _mock_meeting()
        session = _mock_session(scalar_one_or_none_value=meeting)
        result = await get_meeting(session, meeting.id)
        assert result == meeting

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        session = _mock_session()
        result = await get_meeting(session, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_non_admin_cannot_see_others_pending(self) -> None:
        """Non-admin user cannot see another user's pending meeting."""
        viewer = _mock_user("viewer")
        meeting = _mock_meeting(
            approval_status=ApprovalStatus.PENDING,
            submitted_by=uuid.uuid4(),  # different user
        )
        session = _mock_session(scalar_one_or_none_value=meeting)
        result = await get_meeting(session, meeting.id, viewer)
        assert result is None

    @pytest.mark.asyncio
    async def test_contributor_can_see_own_pending(self) -> None:
        """Contributor can see their own pending meeting."""
        contributor = _mock_user("contributor")
        meeting = _mock_meeting(
            approval_status=ApprovalStatus.PENDING,
            submitted_by=contributor.id,
        )
        session = _mock_session(scalar_one_or_none_value=meeting)
        result = await get_meeting(session, meeting.id, contributor)
        assert result == meeting


class TestGetChildCounts:
    """Tests for get_child_counts."""

    @pytest.mark.asyncio
    async def test_returns_three_counts(self) -> None:
        session = AsyncMock()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.scalar_one.return_value = [3, 5, 2][call_count - 1]
            return result

        session.execute = mock_execute
        a, b, c = await get_child_counts(session, uuid.uuid4())
        assert a == 3
        assert b == 5
        assert c == 2


class TestCreateMeeting:
    """Tests for create_meeting."""

    @pytest.mark.asyncio
    async def test_admin_auto_approved(self) -> None:
        """Admin-created meetings are auto-approved."""
        admin = _mock_user("admin")
        gb = MagicMock()
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = gb
        session.execute.return_value = mock_result
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        data = {
            "governing_body_id": uuid.uuid4(),
            "meeting_date": datetime.now(UTC),
            "meeting_type": "regular",
            "status": "scheduled",
        }
        meeting = await create_meeting(session, data=data, current_user=admin)
        assert meeting.approval_status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_contributor_pending(self) -> None:
        """Contributor-created meetings are pending."""
        contributor = _mock_user("contributor")
        gb = MagicMock()
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = gb
        session.execute.return_value = mock_result
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        data = {
            "governing_body_id": uuid.uuid4(),
            "meeting_date": datetime.now(UTC),
            "meeting_type": "regular",
            "status": "scheduled",
        }
        meeting = await create_meeting(session, data=data, current_user=contributor)
        assert meeting.approval_status == ApprovalStatus.PENDING

    @pytest.mark.asyncio
    async def test_invalid_governing_body_raises(self) -> None:
        """Non-existent governing body raises ValueError."""
        session = _mock_session()
        data = {
            "governing_body_id": uuid.uuid4(),
            "meeting_date": datetime.now(UTC),
            "meeting_type": "regular",
            "status": "scheduled",
        }
        with pytest.raises(ValueError, match="Governing body not found"):
            await create_meeting(session, data=data, current_user=_mock_user())


class TestUpdateMeeting:
    """Tests for update_meeting."""

    @pytest.mark.asyncio
    async def test_updates_allowed_fields(self) -> None:
        meeting = _mock_meeting()
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = meeting
        session.execute.return_value = mock_result
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        admin = _mock_user("admin")
        result = await update_meeting(session, meeting.id, data={"status": "cancelled"}, current_user=admin)
        assert result.status == "cancelled"

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = _mock_session()
        admin = _mock_user("admin")
        with pytest.raises(ValueError, match="not found"):
            await update_meeting(session, uuid.uuid4(), data={"status": "cancelled"}, current_user=admin)

    @pytest.mark.asyncio
    async def test_contributor_cannot_update_others_meeting(self) -> None:
        """Contributor cannot edit a meeting they did not submit."""
        contributor = _mock_user("contributor")
        other_user_id = uuid.uuid4()
        meeting = _mock_meeting(
            approval_status=ApprovalStatus.APPROVED,
            submitted_by=other_user_id,  # different user
        )
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = meeting
        session.execute.return_value = mock_result

        with pytest.raises(PermissionError, match="Permission denied"):
            await update_meeting(session, meeting.id, data={"status": "cancelled"}, current_user=contributor)

    @pytest.mark.asyncio
    async def test_contributor_can_update_own_meeting(self) -> None:
        """Contributor can edit a meeting they submitted."""
        contributor = _mock_user("contributor")
        meeting = _mock_meeting(
            approval_status=ApprovalStatus.PENDING,
            submitted_by=contributor.id,
        )
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = meeting
        session.execute.return_value = mock_result
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        result = await update_meeting(session, meeting.id, data={"status": "cancelled"}, current_user=contributor)
        assert result.status == "cancelled"


class TestDeleteMeeting:
    """Tests for delete_meeting."""

    @pytest.mark.asyncio
    async def test_soft_deletes_with_cascade(self) -> None:
        admin = _mock_user("admin")
        meeting = _mock_meeting(submitted_by=admin.id)
        agenda_item = MagicMock(deleted_at=None)
        attachment = MagicMock(deleted_at=None)
        video_embed = MagicMock(deleted_at=None)

        session = AsyncMock()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = meeting
            elif call_count == 2:
                result.scalars.return_value.all.return_value = [agenda_item]
            elif call_count == 3:
                result.scalars.return_value.all.return_value = [attachment]
            else:
                result.scalars.return_value.all.return_value = [video_embed]
            return result

        session.execute = mock_execute
        session.commit = AsyncMock()
        await delete_meeting(session, meeting.id, current_user=admin)
        assert meeting.deleted_at is not None
        assert agenda_item.deleted_at is not None
        assert attachment.deleted_at is not None
        assert video_embed.deleted_at is not None

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = _mock_session()
        admin = _mock_user("admin")
        with pytest.raises(ValueError, match="not found"):
            await delete_meeting(session, uuid.uuid4(), current_user=admin)

    @pytest.mark.asyncio
    async def test_contributor_cannot_delete_others_meeting(self) -> None:
        """Contributor cannot delete a meeting they did not submit."""
        contributor = _mock_user("contributor")
        meeting = _mock_meeting(submitted_by=uuid.uuid4())
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = meeting
        session.execute.return_value = mock_result

        with pytest.raises(PermissionError, match="Permission denied"):
            await delete_meeting(session, meeting.id, current_user=contributor)


class TestApproveMeeting:
    """Tests for approve_meeting."""

    @pytest.mark.asyncio
    async def test_approves_pending(self) -> None:
        meeting = _mock_meeting(approval_status=ApprovalStatus.PENDING)
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = meeting
        session.execute.return_value = mock_result
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        admin = _mock_user("admin")
        result = await approve_meeting(session, meeting.id, admin)
        assert result.approval_status == ApprovalStatus.APPROVED
        assert result.approved_by == admin.id

    @pytest.mark.asyncio
    async def test_non_pending_raises(self) -> None:
        meeting = _mock_meeting(approval_status=ApprovalStatus.APPROVED)
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = meeting
        session.execute.return_value = mock_result

        admin = _mock_user("admin")
        with pytest.raises(ValueError, match="not in pending"):
            await approve_meeting(session, meeting.id, admin)


class TestRejectMeeting:
    """Tests for reject_meeting."""

    @pytest.mark.asyncio
    async def test_rejects_pending(self) -> None:
        meeting = _mock_meeting(approval_status=ApprovalStatus.PENDING)
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = meeting
        session.execute.return_value = mock_result
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        admin = _mock_user("admin")
        result = await reject_meeting(session, meeting.id, admin, "Duplicate entry")
        assert result.approval_status == ApprovalStatus.REJECTED
        assert result.rejection_reason == "Duplicate entry"

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = _mock_session()
        admin = _mock_user("admin")
        with pytest.raises(ValueError, match="not found"):
            await reject_meeting(session, uuid.uuid4(), admin, "reason")
