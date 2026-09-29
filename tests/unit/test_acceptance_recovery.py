"""The recovery sweeps' acceptance checks: registered, passing on a real schema, and able to fail.

Both checks read the worker's own record of the schedule first, so the database half writes that
record as a worker would have: one run of each sweep, finished, acting, a minute ago. Then the
checks pass and leave every table as they found it. Without the record they say they were not run,
and with an old one they fail, because a schedule that stopped is the thing the first half exists
to catch. Then the product is broken where each check proves it, the way it would break in
practice: the control run declared safe to run twice, a read-back's answer ignored, and the list
shown to a reader with no grant. Each is a failed check with its own sentence.

Task ids: M23.3.1
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from brain.ops import acceptance_checks_recovery as recovery
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_recovery"
QUEUE = "a_stopped_worker_s_job_is_put_back_only_when_its_task_is_safe"
EFFECTS = "an_interrupted_action_is_read_back_or_listed_before_any_retry"

#: The tables these checks write that `WRITTEN_BY_CHECKS` does not list, plus the run record.
WRITTEN_HERE = ("ops.operation", "ops.control_run")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_both_checks_are_registered_with_the_leaf_they_prove() -> None:
    """Delete this and a check can close a leaf it does not exercise, or name an id no task has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        QUEUE: ("M23.3.1",),
        EFFECTS: ("M23.3.1",),
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert "M23.3.1" in leaves


def test_the_recovery_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them: the queue's
    sweep, then the effects'. Held here since 2026-09-30, so a package adding a check edits its own
    file and never a list every package appends to. Delete this and a check can drop out of the
    module with the page simply listing one fewer row."""
    assert checks_in(MODULE) == [QUEUE, EFFECTS]


def test_the_evidence_window_is_wider_than_the_sweeps_own_cadence() -> None:
    """Delete this and the window could be narrowed below the sweep's cadence, and the check would
    fail a schedule that is running exactly as it should."""
    from brain.ops.heartbeat import stale_after

    assert 3 * stale_after() < recovery.SCHEDULE_EVIDENCE_WINDOW
    assert stale_after() < recovery.LEFT_BEHIND


def run_checks(url: str, checks: Sequence[Check]) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url
    from brain.ops.acceptance_run import run_suite
    from brain.session import make_app_engine

    async def run() -> Any:
        engine = make_app_engine(normalise_database_url(url))
        try:
            return await run_suite(
                engine,
                checks,
                settings=settings_from({"BRAIN_DATABASE_URL": url, **INSTALL}),
                stream=sys.stderr,
            )
        finally:
            await engine.dispose()

    return {one.name: (one.outcome, one.reason) for one in asyncio.run(run())}


def written(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    return {
        one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0])  # noqa: S608
        for one in WRITTEN_HERE
    }


def scheduled(url: str, *, ago: timedelta = timedelta(minutes=1)) -> None:
    """One finished, acting run of each sweep, as the worker's tick records it."""
    from tests.fixtures.scratch_postgres import sql

    for name, detail in (
        ("queue_redrive", "0 job(s) looked at: 0 re-driven, 0 set aside for a person"),
        ("side_effect_resume", "0 interrupted operation(s) looked at: 0 settled"),
    ):
        sql(
            url,
            "INSERT INTO ops.control_run (id, name, started_at, finished_at, outcome, "
            "report_only, detail) VALUES (gen_random_uuid(), %s, now() - %s, now() - %s, 'ok', "
            "false, %s)",
            name,
            ago,
            ago,
            detail,
        )


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_on_a_real_database_both_checks_pass_and_leave_nothing_behind() -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** Both pass, and every
    table they wrote to holds what it held before. Delete this and a check that cannot pass on the
    real schema, or one that commits an operation record to a client's install, reaches the
    owner's server first."""
    with at_head("brain_acceptance_recovery") as url:
        scheduled(url)
        before = (counts(url), written(url))
        outcomes = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))

    assert outcomes == {QUEUE: (PASSED, ""), EFFECTS: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_with_no_scheduled_run_recorded_both_checks_say_they_were_not_run() -> None:
    """Delete this and an install whose worker has not ticked yet could be recorded as passing a
    check about the schedule, or failing one about code that has had no chance to run."""
    with at_head("brain_acceptance_recovery") as url:
        outcomes = run_checks(url, tuple(mine().values()))

    assert outcomes == {
        QUEUE: (NOT_RUN, recovery.NO_SCHEDULED_RUN_YET),
        EFFECTS: (NOT_RUN, recovery.NO_SCHEDULED_RUN_YET),
    }


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_a_schedule_that_stopped_running_the_sweeps_fails_both_checks() -> None:
    """Delete this and a worker whose schedule stopped an hour ago passes on the strength of a run
    it made before stopping."""
    with at_head("brain_acceptance_recovery") as url:
        scheduled(url, ago=timedelta(hours=1))
        outcomes = run_checks(url, tuple(mine().values()))

    stopped = "the schedule has not run the sweep recently, so nothing sweeps"
    assert outcomes == {QUEUE: (FAILED, stopped), EFFECTS: (FAILED, stopped)}


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
@pytest.mark.parametrize(
    ("broken", "name", "reason"),
    [
        ("control_safe", QUEUE, "a job that may not run twice was not set aside for a person"),
        (
            "answer_ignored",
            EFFECTS,
            "an action its connector answered for was not settled on the answer",
        ),
        ("list_open", EFFECTS, "the list showed an interrupted action to a reader with no grant"),
    ],
)
def test_each_check_fails_where_its_sweep_is_wrong(
    monkeypatch: pytest.MonkeyPatch, broken: str, name: str, reason: str
) -> None:
    """Three breaks, each the way it happens: the control run declared safe to run twice, so a
    crashed control is put back rather than shown to a person; a read-back whose answer is
    ignored, so an absent effect is recorded as done; and a list that answers a reader the
    sweep's job does not, so an install's interrupted actions reach anybody signed in. Delete this
    and the checks are satisfied by sweeps that do the one thing each exists to prevent."""
    from brain import operation_routes
    from brain.ops import recovery_run
    from brain.ops.idempotency import Operation, OperationState
    from brain.ops.queue import Redrive
    from brain.ops.worker import CONTROL_TASK

    if broken == "control_safe":
        declared = cast(dict[str, Redrive], recovery_run.REDRIVE_BY_TASK)
        monkeypatch.setitem(declared, CONTROL_TASK, Redrive.SAFE)
    elif broken == "answer_ignored":

        def done(one: Operation, _read_back: Any) -> Operation:
            return one.advanced(OperationState.SUCCEEDED)

        monkeypatch.setattr(recovery_run, "verify_once", done)
    else:
        monkeypatch.setattr(operation_routes, "may_see_job", lambda *_: True)
    with at_head("brain_acceptance_recovery") as url:
        scheduled(url)
        assert run_checks(url, (mine()[name],)) == {name: (FAILED, reason)}
