"""The install checks for the delegation table, each passing on PostgreSQL at head and failing with
the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M18.3.1, M18.3.2, M18.3.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, CheckFailedError, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_delegation_rows"
REACH = "the_database_computes_a_childs_reach_as_the_rule_does"
REFUSES = "the_database_refuses_a_delegation_row_that_widens_its_parent"
NO_VERB = "the_orchestrator_holds_no_verb_that_grants_reach"


def test_the_module_declares_one_check_per_leaf() -> None:
    """Delete this and a check can lose a leaf with the Install page showing the same rows, and the
    leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (REACH, ("M18.3.1",)),
        (REFUSES, ("M18.3.2",)),
        (NO_VERB, ("M18.3.3",)),
    ]
    assert checks_in(MODULE) == [REACH, REFUSES, NO_VERB]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_delegation_rows") as url:
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


def _delegation_rows(url: str) -> int:
    from tests.fixtures.scratch_postgres import sql

    return int(sql(url, "SELECT count(*) FROM gate.delegation")[0][0])


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All three pass and no delegation row or reserved
    department is left behind. Delete this and a check that can never pass on a real schema, or
    that leaves a row in a table nothing can delete from, reaches the owner's install."""
    before, rows = counts(install), _delegation_rows(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 3
    assert counts(install) == before
    assert _delegation_rows(install) == rows


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_database_function_that_computes_another_reach_fails_the_reach_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Python rule computing something else than the database does. Delete this and M18.3.1
    closes on a SQL function that disagrees with the rule it is a second copy of."""
    from brain.ops import acceptance_checks_delegation_rows as module

    real = module._Chain

    class Disagreeing(real):  # type: ignore[valid-type, misc]
        def __init__(self, h: Any, tag: str) -> None:
            super().__init__(h, tag)
            self.child = self.agent

    monkeypatch.setattr(module, "_Chain", Disagreeing)
    assert _failed(install, REACH) == module.THE_DATABASE_REACH_DIFFERED


@pytest.mark.needs_db
def test_a_trigger_that_admits_a_widening_row_fails_the_refusal_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal asked of a row the rule would admit: the check sees a row stored where it
    expected a refusal. Delete this and M18.3.2 closes on a trigger that refuses nothing."""
    from brain.ops import acceptance_checks_delegation_rows as module

    real = module._Chain

    class Wide(real):  # type: ignore[valid-type, misc]
        def __init__(self, h: Any, tag: str) -> None:
            super().__init__(h, tag)
            # A child claiming the reach the parent itself holds is not a widening of it.
            self.child = self.parent

    monkeypatch.setattr(module, "_Chain", Wide)
    assert _failed(install, REFUSES) == module.A_NARROWING_ROW_WAS_REFUSED


def test_a_scan_that_finds_nothing_in_a_granting_source_fails_the_verb_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scan blinded. Delete this and M18.3.3 passes over a scan that can no longer see a
    grant, which is the check every other test of the leaf would also pass."""
    from brain.ops import acceptance_checks_delegation_rows as module
    from brain.orchestration import delegation

    monkeypatch.setattr(delegation, "grant_verbs_in", lambda *_a, **_k: ())
    with pytest.raises(CheckFailedError) as raised:
        asyncio.run(module.the_orchestrator_holds_no_verb_that_grants_reach(None))  # type: ignore[arg-type]
    assert raised.value.reason == module.THE_SCAN_FOUND_NOTHING_IN_A_GRANTING_SOURCE


def test_the_orchestration_package_as_shipped_holds_no_verb_that_grants_reach() -> None:
    """The check's positive half, run without a database: every shipped module passes the scan.
    Delete this and the verb check can be satisfied by a scan that refuses everything."""
    from brain.ops import acceptance_checks_delegation_rows as module

    asyncio.run(module.the_orchestrator_holds_no_verb_that_grants_reach(None))  # type: ignore[arg-type]
