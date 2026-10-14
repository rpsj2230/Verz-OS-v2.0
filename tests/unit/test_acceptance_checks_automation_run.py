"""The automation run's install check: registered, passing on a real schema, and able to fail.

The database half installs an automation, asks the worker's own decision with the owner holding what
the task reads and again after the grant is revoked, and leaves nothing. Then the product is broken
where the check proves it: a run admitted at a reach kept from before the revocation, and a refusal
that leaves the automation scheduled.

Task ids: M17.4.3, M17.4.4
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_automation_run"
RUNS = "an_automation_runs_at_its_owner_s_reach_and_stops_without_it"
WRITTEN_HERE = ("agent.automation", "agent.automation_schedule")


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_names_the_leaves_it_proves_and_every_one_is_a_leaf() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {RUNS: ("M17.4.3", "M17.4.4")}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {"M17.4.3", "M17.4.4"} <= leaves


def test_the_automation_checks_are_listed_in_their_page_order() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [RUNS]


def test_the_module_stands_inside_its_assigned_order_range() -> None:
    """Delete this and two modules can claim one place on the Install page."""
    from brain.ops import acceptance_checks_automation_run as module

    assert 2000 <= module.CHECK_ORDER <= 2099


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


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
def test_on_a_real_database_the_check_passes_and_leaves_nothing_behind() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes and every table
    it wrote holds what it held before. Delete this and a check that cannot pass on the real
    schema, or one that commits an automation to a client's install, reaches the owner's server."""
    with at_head("brain_acceptance_automation_run") as url:
        before = (counts(url), written(url))
        outcomes = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))

    assert outcomes == {RUNS: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("reach_kept", "an automation whose owner lost what it reads was not refused"),
        (
            "refusal_keeps_schedule",
            "a refused run did not leave the automation paused with its reason",
        ),
    ],
)
def test_the_check_fails_where_the_product_is_wrong(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Two breaks, each the way it happens: a decision that never asks the owner's reach, so an
    automation keeps running at what its owner no longer holds; and a refusal that schedules the
    next slot, so a refused automation is refused on every slot for ever. Delete this and the
    check is satisfied by a runner that ignores the one thing it exists to ask."""
    from brain.ops import automation_run
    from brain.ops.automation_run import Afterwards, PausedBecause

    if broken == "reach_kept":
        real = automation_run.admitted_run

        # An admission that never refuses for a lost reach: it admits at the reach it has.
        def never_refuses(*args: Any, **kwargs: Any) -> Any:
            found = real(*args, **kwargs)
            if found is PausedBecause.OWNER_LOST_REACH:
                return automation_run.Admitted(
                    reach=kwargs["owner_entitlements"], declaration=automation_run.TASKS[0]
                )
            return found

        monkeypatch.setattr(automation_run, "admitted_run", never_refuses)
    else:

        def keeps_schedule(*_: Any, **kwargs: Any) -> Afterwards:
            return Afterwards(next_run_at=kwargs["at"] + timedelta(days=1), paused_because=None)

        monkeypatch.setattr(automation_run, "afterwards", keeps_schedule)
    with at_head("brain_acceptance_automation_run") as url:
        assert run_checks(url, tuple(mine().values())) == {RUNS: (FAILED, reason)}
