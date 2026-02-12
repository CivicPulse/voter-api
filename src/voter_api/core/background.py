"""Background task runner abstraction.

Provides a protocol for submitting and tracking background tasks,
with an in-process FastAPI BackgroundTasks implementation for MVP.
Enables future swap to Celery/ARQ without service layer changes.
"""

import asyncio
import enum
import uuid
from collections.abc import Coroutine
from typing import Any, Protocol


class JobStatus(enum.StrEnum):
    """Status of a background job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BackgroundTaskRunner(Protocol):
    """Protocol for background task execution."""

    def submit_task(self, coro: Coroutine[Any, Any, Any]) -> str:
        """Submit an async task for background execution.

        Args:
            coro: The coroutine to execute.

        Returns:
            A job ID string for tracking.
        """
        ...

    def get_status(self, job_id: str) -> JobStatus:
        """Get the current status of a background job.

        Args:
            job_id: The job ID returned by submit_task.

        Returns:
            The current job status.
        """
        ...


class InProcessTaskRunner:
    """In-process background task runner using asyncio.

    Suitable for development and MVP. Tasks run in the same process
    as the API server using asyncio.create_task().
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobStatus] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def submit_task(self, coro: Coroutine[Any, Any, Any]) -> str:
        """Submit an async task for background execution.

        Args:
            coro: The coroutine to execute.

        Returns:
            A job ID string for tracking.
        """
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = JobStatus.PENDING

        async def _run() -> None:
            self._jobs[job_id] = JobStatus.RUNNING
            try:
                await coro
                self._jobs[job_id] = JobStatus.COMPLETED
            except Exception:
                self._jobs[job_id] = JobStatus.FAILED
                raise

        task = asyncio.create_task(_run())
        self._tasks[job_id] = task
        return job_id

    def get_status(self, job_id: str) -> JobStatus:
        """Get the current status of a background job.

        Args:
            job_id: The job ID returned by submit_task.

        Returns:
            The current job status.

        Raises:
            KeyError: If the job ID is not found.
        """
        return self._jobs[job_id]


# Singleton instance for the application
task_runner = InProcessTaskRunner()
