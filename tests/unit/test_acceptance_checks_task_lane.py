"""The task lane's install checks: registered, passing on a real schema, and able to fail.

The database half runs the module as the worker would, against a database at head: both checks pass
and leave nothing (the run rows and `ops.operation` included). Then each is shown failing with the
product broken the way it would plausibly break: the door making an effect twice, a lost answer
settled as failed on no evidence, and a connector that can write and cannot be read back.

Task ids: M17.3.1, M17.3.2, M17.3.3, M17.3.4, M17.3.5
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, PASSED, Check, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, checks_in, counts

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_task_lane"
ONCE = "a_keyed_effect_is_made_once_and_a_lost_answer_is_read_back"
READ_BACK = "every_connector_that_can_write_can_be_read_back"

WRITTEN_HERE = ("ops.operation",)


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_each_check_names_the_leaves_it_proves_and_every_one_is_a_leaf() -> None:
    """Delete this and a check can close a leaf it does not exercise, or name an id no task has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        ONCE: ("M17.3.1", "M17.3.2", "M17.3.5"),
        READ_BACK: ("M17.3.3", "M17.3.4"),
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert {leaf for one in mine().values() for leaf in one.leaves} <= leaves


def test_the_task_lane_checks_are_listed_in_their_page_order() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row."""
    assert checks_in(MODULE) == [ONCE, READ_BACK]


def test_the_module_stands_inside_its_assigned_order_range() -> None:
    """Held to the range this package was given, so a later package cannot collide with it. Delete
    this and two modules can claim one place on the Install page."""
    from brain.ops import acceptance_checks_task_lane as module

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
def test_on_a_real_database_both_checks_pass_and_leave_nothing_behind() -> None:
    """**The checks as the worker runs them, against PostgreSQL at head.** Both pass and the
    operation ledger holds what it held before. Delete this and a check that cannot pass on the
    real schema, or one that commits an operation record to a client's install, reaches the
    owner's server first."""
    with at_head("brain_acceptance_task_lane") as url:
        before = (counts(url), written(url))
        outcomes = run_checks(url, tuple(mine().values()))
        after = (counts(url), written(url))

    assert outcomes == {ONCE: (PASSED, ""), READ_BACK: (PASSED, "")}
    assert after == before


@pytest.mark.needs_db
@pytest.mark.usefixtures("issuer")
@pytest.mark.parametrize(
    ("broken", "name", "reason"),
    [
        (
            "win_always",
            ONCE,
            "a record moved by somebody else was settled as if unmoved",
        ),
        (
            "lost_answer_failed",
            ONCE,
            "an effect whose answer was lost was not left unknown",
        ),
        (
            "refusal_is_absence",
            READ_BACK,
            "a refusal, a quota or an outage was read as the effect absent",
        ),
    ],
)
def test_each_check_fails_where_the_product_is_wrong(
    monkeypatch: pytest.MonkeyPatch, broken: str, name: str, reason: str
) -> None:
    """Three breaks, each the way it happens: a ledger whose win is given to every caller, so a
    repeat issues again; an effect that raised recorded as failed, so a lost answer invites a
    second attempt; and a read-back that reads a refusal as an absence, so a permission lost
    becomes a duplicated write. Delete this and the checks are satisfied by a door that does
    the one thing each exists to prevent."""
    from brain.connectors import write_verification
    from brain.connectors.write_verification import Reading
    from brain.ops import acceptance_checks_task_lane as module
    from brain.ops import idempotency
    from brain.ops.idempotency import OperationState, Verification

    if broken == "win_always":
        monkeypatch.setattr(module._InstallLedger, "win", lambda self, key: True)
    elif broken == "lost_answer_failed":
        real = module._InstallLedger.settle
        doubts: list[str] = []

        def settle(
            self: Any, key: str, *, frm: OperationState, to: OperationState
        ) -> idempotency.Operation:
            # The first move to unknown is the walk's own; the second is the lost answer's.
            if to is OperationState.UNKNOWN and frm is OperationState.SENT:
                doubts.append(key)
                if len(doubts) == 2:
                    to = OperationState.FAILED
            return real(self, key, frm=frm, to=to)

        monkeypatch.setattr(module._InstallLedger, "settle", settle)
    else:
        real_verdict = write_verification.verdict

        def generous(reading: Reading) -> Verification:
            from brain.connectors.throttle import CallOutcome

            if reading.outcome in (CallOutcome.OK, CallOutcome.TRUNCATED):
                return real_verdict(reading)
            return Verification.ABSENT

        monkeypatch.setattr(write_verification, "verdict", generous)
    with at_head("brain_acceptance_task_lane") as url:
        assert run_checks(url, (mine()[name],)) == {name: (FAILED, reason)}
