"""Audit logging service.

Provides immutable audit trail recording and querying for data access events.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.audit_log import AuditLog


async def log_access(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    username: str,
    action: str,
    resource_type: str,
    resource_ids: list[str] | None = None,
    request_ip: str | None = None,
    request_endpoint: str | None = None,
    request_metadata: dict | None = None,
) -> AuditLog:
    """Create an immutable audit log record.

    Args:
        session: The database session.
        user_id: The acting user's ID.
        username: The acting user's username.
        action: The action performed (view, query, export, import, analyze, update).
        resource_type: The resource type affected.
        resource_ids: List of affected resource IDs.
        request_ip: The request IP address.
        request_endpoint: The API endpoint called.
        request_metadata: Additional context metadata.

    Returns:
        The created AuditLog record.
    """
    audit_log = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        resource_type=resource_type,
        resource_ids=resource_ids,
        request_ip=request_ip,
        request_endpoint=request_endpoint,
        request_metadata=request_metadata,
    )
    session.add(audit_log)
    await session.commit()
    return audit_log


async def query_audit_logs(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AuditLog], int]:
    """Query audit logs with optional filters.

    Args:
        session: The database session.
        user_id: Filter by user ID.
        action: Filter by action type.
        resource_type: Filter by resource type.
        start_time: Filter records after this timestamp.
        end_time: Filter records before this timestamp.
        page: Page number (1-based).
        page_size: Items per page.

    Returns:
        Tuple of (audit log records, total count).
    """
    from sqlalchemy import func

    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))

    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)
    if action is not None:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if resource_type is not None:
        query = query.where(AuditLog.resource_type == resource_type)
        count_query = count_query.where(AuditLog.resource_type == resource_type)
    if start_time is not None:
        query = query.where(AuditLog.timestamp >= start_time)
        count_query = count_query.where(AuditLog.timestamp >= start_time)
    if end_time is not None:
        query = query.where(AuditLog.timestamp <= end_time)
        count_query = count_query.where(AuditLog.timestamp <= end_time)

    total = (await session.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    query = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(page_size)
    result = await session.execute(query)
    logs = list(result.scalars().all())

    return logs, total
