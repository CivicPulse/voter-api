"""Tests for the background task runner module."""

import asyncio

import pytest

from voter_api.core.background import InProcessTaskRunner, JobStatus


class TestJobStatus:
    """Tests for JobStatus enum."""

    def test_status_values(self) -> None:
        assert JobStatus.PENDING == "pending"
        assert JobStatus.RUNNING == "running"
        assert JobStatus.COMPLETED == "completed"
        assert JobStatus.FAILED == "failed"

    def test_all_statuses_are_strings(self) -> None:
        for status in JobStatus:
            assert isinstance(status.value, str)


class TestInProcessTaskRunner:
    """Tests for InProcessTaskRunner."""

    @pytest.mark.asyncio
    async def test_submit_task_returns_job_id(self) -> None:
        runner = InProcessTaskRunner()

        async def noop() -> None:
            pass

        job_id = runner.submit_task(noop())
        assert isinstance(job_id, str)
        assert len(job_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_successful_task_completes(self) -> None:
        runner = InProcessTaskRunner()
        completed = False

        async def simple_task() -> None:
            nonlocal completed
            completed = True

        job_id = runner.submit_task(simple_task())
        await asyncio.sleep(0.1)  # Let the task complete

        assert runner.get_status(job_id) == JobStatus.COMPLETED
        assert completed is True

    @pytest.mark.asyncio
    async def test_failed_task_marks_status(self) -> None:
        runner = InProcessTaskRunner()

        async def failing_task() -> None:
            msg = "Task failed"
            raise RuntimeError(msg)

        job_id = runner.submit_task(failing_task())
        await asyncio.sleep(0.1)  # Let the task fail

        assert runner.get_status(job_id) == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_get_status_unknown_job_raises(self) -> None:
        runner = InProcessTaskRunner()

        with pytest.raises(KeyError):
            runner.get_status("nonexistent-job-id")

    @pytest.mark.asyncio
    async def test_initial_status_is_pending(self) -> None:
        runner = InProcessTaskRunner()
        started = asyncio.Event()

        async def blocking_task() -> None:
            await started.wait()

        job_id = runner.submit_task(blocking_task())
        # The task starts as PENDING before the event loop processes it
        # Note: it may transition to RUNNING very quickly
        status = runner.get_status(job_id)
        assert status in (JobStatus.PENDING, JobStatus.RUNNING)
        started.set()
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_multiple_tasks(self) -> None:
        runner = InProcessTaskRunner()
        results: list[int] = []

        async def task(n: int) -> None:
            results.append(n)

        job_ids = [runner.submit_task(task(i)) for i in range(5)]
        await asyncio.sleep(0.2)

        for job_id in job_ids:
            assert runner.get_status(job_id) == JobStatus.COMPLETED

        assert sorted(results) == [0, 1, 2, 3, 4]
