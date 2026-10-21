"""Every task of ours has a deadline, and one that overruns fails its attempt (M17.1.4).

Over `brain.ops.queue.register_task` with a stand-in for the driver's application, because what is
asserted is what the task becomes when registered: a coroutine that is cancelled at its deadline.

Task ids: M17.1.4
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from brain.gate.context import TrafficClass
from brain.ops.heartbeat import HEARTBEAT_SECONDS, stale_after
from brain.ops.jobs import DEFAULT_TIMEOUT_SECONDS
from brain.ops.queue import (
    TASK_DEADLINE_SECONDS,
    QueueError,
    TaskDeadlineExceededError,
    register_task,
)


class FakeApp:
    """The part of the driver's application `register_task` touches."""

    def __init__(self) -> None:
        self.tasks: dict[str, Any] = {}

    def task(self, *, name: str, queue: str) -> Any:
        def decorate(fn: Any) -> Any:
            self.tasks[name] = SimpleNamespace(queue=queue, fn=fn)
            return fn

        return decorate


def _registered(run: Any, **more: Any) -> Any:
    app = FakeApp()
    register_task(app, "ours.work", run, traffic_class=TrafficClass.SYSTEM, **more)  # type: ignore[arg-type]
    return app.tasks["ours.work"].fn


def test_the_default_deadline_is_the_jobs_own_and_one_heartbeat_inside_the_window() -> None:
    """Delete this and the deadline a task is given and the one the job model states drift apart,
    or the deadline reaches the staleness window, where the recovery sweep acts first and starts a
    second copy of a job that was only slow."""
    assert TASK_DEADLINE_SECONDS == DEFAULT_TIMEOUT_SECONDS
    assert stale_after().total_seconds() - HEARTBEAT_SECONDS == TASK_DEADLINE_SECONDS
    assert 0 < TASK_DEADLINE_SECONDS < stale_after().total_seconds()


def test_a_task_that_overruns_is_cancelled_and_fails_its_attempt() -> None:
    """Delete this and a task that never returns holds its slot until the worker is restarted."""
    seen: list[str] = []

    async def hangs(reference: str) -> None:
        try:
            await asyncio.sleep(30)
        finally:
            seen.append("cancelled")

    bounded = _registered(hangs, timeout=0.05)
    with pytest.raises(TaskDeadlineExceededError, match=r"ours\.work"):
        asyncio.run(bounded("r1"))
    assert seen == ["cancelled"]


def test_a_task_inside_its_deadline_returns_what_it_returned_with_the_arguments_it_was_given() -> (
    None
):
    """Delete this and the deadline refuses every task, or swallows its result or its arguments."""

    async def adds(a: int, *, b: int) -> int:
        return a + b

    bounded = _registered(adds, timeout=5)
    assert asyncio.run(bounded(2, b=3)) == 5


def test_a_task_keeps_the_signature_the_driver_reads_its_arguments_from() -> None:
    """Delete this and the driver, which builds a task's arguments from its signature, sees `*args`
    and refuses every job."""

    async def work(reference: str, limit: int = 3) -> None:
        return None

    assert list(inspect.signature(_registered(work)).parameters) == ["reference", "limit"]


@pytest.mark.parametrize("timeout", [0, -1, 1e9])
def test_a_deadline_of_nothing_or_past_the_staleness_window_is_refused(timeout: float) -> None:
    """Delete this and a task is abandoned before it starts, or has a deadline that never fires."""

    async def work() -> None:
        return None

    with pytest.raises(QueueError, match="more than nothing"):
        _registered(work, timeout=timeout)
    assert _registered(work, timeout=1) is not None
