"""The install checks for weighing a multi-agent plan, each passing on PostgreSQL at head and
failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M18.1.3, M18.2.1, M18.2.2, M18.2.3, M18.2.4, M18.4.1, M18.4.2, M18.4.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_orchestration_rehearsal"
GATE = "the_gate_splits_a_plan_or_keeps_one_loop_and_keeps_its_decision"
MERGE = "results_are_checked_and_merged_with_a_stated_gap"
WRITTEN = ("ops.fanout_gate", "ops.setting")


def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Delete this and a check can lose a leaf with the Install page showing the same rows, and the
    leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (GATE, ("M18.2.1", "M18.2.2", "M18.2.3", "M18.2.4")),
        (MERGE, ("M18.1.3", "M18.4.1", "M18.4.2", "M18.4.3")),
    ]
    assert checks_in(MODULE) == [GATE, MERGE]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_orchestration_rehearsal") as url:
        yield url


def run_module(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update({one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN})  # noqa: S608
    return both


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** Both pass and no decision or switch is left behind.
    Delete this and a check that can never pass on a real schema, or that leaves rows in a table
    nothing can delete from, reaches the owner's install."""
    before = _counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2
    assert _counts(install) == before


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_gate_that_never_fails_a_condition_fails_the_gate_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every condition read as holding. Delete this and M18.2.2 and M18.2.3 close on a gate that
    splits a plan with nothing to run at once."""
    from brain.ops import acceptance_checks_orchestration_rehearsal as module
    from brain.orchestration import fanout

    monkeypatch.setattr(fanout, "failures", lambda *_a, **_k: ())
    assert _failed(install, GATE) == module.A_CHAIN_WAS_SPLIT


@pytest.mark.needs_db
def test_a_decision_that_is_not_kept_fails_the_gate_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store's write removed. Delete this and M18.2.4 closes on a record nothing keeps."""
    from brain.ops import acceptance_checks_orchestration_rehearsal as module
    from brain.ops import fanout_gate_store

    async def nothing(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(fanout_gate_store, "keep", nothing)
    assert _failed(install, GATE) == module.A_DECISION_WAS_NOT_KEPT


@pytest.mark.needs_db
def test_a_switch_that_is_ignored_fails_the_gate_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch read as always on. Delete this and a feature that ships off is on for every
    install the day it arrives."""
    from brain import orchestration_routes
    from brain.ops import acceptance_checks_orchestration_rehearsal as module

    async def always(_session: Any, _feature: Any) -> bool:
        return True

    monkeypatch.setattr(orchestration_routes, "is_on", always)
    assert _failed(install, GATE) == module.WEIGHED_WITH_THE_SWITCH_OFF


@pytest.mark.needs_db
def test_a_notice_that_says_nothing_fails_the_merge_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The notice of what is missing removed. Delete this and M18.4.3 closes on an answer that
    reads as complete with a subtask missing (the merge's own refusals, which this does not touch,
    stop a gap being dropped silently, and `brain.orchestration.merge` tests them)."""
    from brain.ops import acceptance_checks_orchestration_rehearsal as module
    from brain.orchestration.merge import MergedAnswer

    monkeypatch.setattr(MergedAnswer, "notice", lambda _self, *, disclosable: "")
    assert _failed(install, MERGE) == module.A_GAP_WAS_NOT_STATED


@pytest.mark.needs_db
def test_a_total_that_is_not_the_rows_fails_the_merge_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A total carried beside the rows. Delete this and M18.4.2 closes on a cost that can
    disagree with the lines above it."""
    from brain.ops import acceptance_checks_orchestration_rehearsal as module
    from brain.orchestration.merge import MergedAnswer

    monkeypatch.setattr(MergedAnswer, "total_minor", property(lambda _self: 0))
    assert _failed(install, MERGE) == module.THE_TOTAL_WAS_NOT_THE_ROWS
