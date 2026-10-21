"""The mover's-automation install check, passing on PostgreSQL at head, leaving nothing, and
failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M26.2.3
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import INSTALL, at_head, checks_in
from tests.unit.test_acceptance_checks_joiner_mover_leaver import furnish

MODULE = "brain.ops.acceptance_checks_mover_automations"
CHECK = "a_mover_s_automation_is_paused_and_a_stayer_s_is_not"

#: Tables the check writes that `counts` does not hold.
ALSO_WRITTEN = ("agent.automation", "agent.automation_schedule", "gate.capability_pack_assignment")


def test_the_module_declares_the_leaf_its_check_proves() -> None:
    """Delete this and the check can lose its leaf, or gain one it does not prove, with the
    Install page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {CHECK: ("M26.2.3",)}
    assert checks_in(MODULE) == [CHECK]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_mover_automations") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def held(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608


@pytest.mark.needs_db
def test_the_check_passes_on_a_furnished_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """**The check as the worker runs it, on an install that has been furnished.** It passes and
    leaves no automation, schedule row, pack assignment, setting or ledger entry. Delete this and a
    check that commits its switch, or one that cannot pass on a real schema, reaches the owner's
    server first."""
    furnish(install)
    before, also = counts(install), held(install)
    assert run_module(install, MODULE) == {CHECK: (PASSED, "")}
    assert counts(install) == before
    assert held(install) == also


@pytest.mark.needs_db
def test_without_a_starter_pack_the_check_says_it_was_not_run(install: str, issuer: None) -> None:
    """Delete this and an install whose Starter pack was retired shows a red row for a decision
    somebody made."""
    from tests.fixtures.scratch_postgres import sql

    sql(install, "UPDATE gate.capability_pack SET deleted_at = now() WHERE name = 'starter'")
    try:
        outcome, reason = run_module(install, MODULE)[CHECK]
    finally:
        sql(install, "UPDATE gate.capability_pack SET deleted_at = NULL WHERE name = 'starter'")
    assert outcome == NOT_RUN, reason


@pytest.mark.needs_db
def test_a_pause_that_never_happens_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A decision that never sees a loss leaves the mover's automation running at the department
    they moved to. Delete this and the check passes on a product that narrows silently."""
    from brain.ops import mover_automations

    furnish(install)
    monkeypatch.setattr(mover_automations, "lost_reach", lambda before, after, *, now: False)
    outcome, reason = run_module(install, MODULE)[CHECK]
    assert outcome == FAILED, reason
    assert "kept running" in reason


@pytest.mark.needs_db
def test_a_pause_of_everybody_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive sibling: a decision that sees a loss for everybody stops the person who did
    not move. Delete this and the check passes on a pause that stops every automation every
    night."""
    from brain.ops import mover_automations

    furnish(install)
    monkeypatch.setattr(mover_automations, "lost_reach", lambda before, after, *, now: True)
    outcome, reason = run_module(install, MODULE)[CHECK]
    assert outcome == FAILED, reason
    assert "did not move was paused" in reason
