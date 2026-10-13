"""The acceptance suite frees each check's garbage before the next check starts.

The suite runs every check in one process inside the worker's container. On 2026-10-13 that
container was killed about every half hour with one process at about 339 MB of anonymous memory,
and the run was lost each time. Nothing here proves the suite leaks: a cheap look found no
per-check state held across checks (results are small tuples and the harness goes out of scope
with each check). What it can do is stop a failed check's reference cycles, which hold the
harness and its connection through the exception's traceback, waiting for the collector's own
schedule. This test holds the collection to the suite, with the checks and the database
replaced so it needs neither.

Task ids: M38.5.1
"""

from __future__ import annotations

import asyncio
import gc
import io

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import Check, Result
from brain.settings import Settings


def test_each_check_s_garbage_is_collected_after_it_and_before_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The order is the property: collect after check one and before check two starts, so a failed
    check's cycle is freed while the next check is the only one holding memory. Delete this and the
    collection can move to the end of the suite, after every check has piled its garbage on the
    last, or be dropped, with the suite's outcome unchanged.

    The positive half: every check is still run and its outcome recorded in order."""
    events: list[str] = []

    async def no_reserved_names(engine: object, stream: object) -> bool:
        return False

    async def run_one(engine: object, one: Check, **_: object) -> tuple[str, str]:
        events.append(f"run {one.name}")
        return ("passed", "")

    async def body(harness: object) -> None:
        return None

    monkeypatch.setattr(acceptance_run, "in_use", no_reserved_names)
    monkeypatch.setattr(acceptance_run, "run_one", run_one)

    def collect() -> int:
        events.append("collect")
        return 0

    monkeypatch.setattr(gc, "collect", collect)
    checks = [
        Check(name=name, leaves=("M32.4.1.4",), sentence="runs.", run=body)
        for name in ("check_one", "check_two")
    ]

    results = asyncio.run(
        acceptance_run.run_suite(
            None,  # type: ignore[arg-type]
            checks,
            settings=Settings(),
            stream=io.StringIO(),
        )
    )

    assert events == ["run check_one", "collect", "run check_two", "collect"]
    assert [one.name for one in results] == ["check_one", "check_two"]
    assert all(isinstance(one, Result) for one in results)
