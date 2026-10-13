"""The joiner, mover and leaver install checks, passing on PostgreSQL at head, leaving nothing, and
failing with the product broken the way it would plausibly break.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M26.1.2, M26.1.3, M26.2.6, M26.3.1, M26.3.2, M26.3.3, M26.3.4
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import INSTALL, at_head, checks_in

MODULE = "brain.ops.acceptance_checks_joiner_mover_leaver"
PACKS = "a_joiner_gets_a_department_pack_and_a_mover_or_leaver_loses_it"
DISABLE = "a_disabled_person_is_refused_on_the_next_request_and_signed_out"
AGENT = "a_leaver_s_agent_stops_is_listed_for_adoption_and_is_taken_on"
AUTOMATION = "an_automation_waits_for_an_owner_when_its_owner_is_disabled"
PERSONAL = "a_leaver_s_personal_document_stays_and_nobody_else_reaches_it"

#: Tables the checks write that `counts` does not hold.
ALSO_WRITTEN = ("gate.capability_pack_assignment", "gate.automation_owner")


def test_the_module_declares_the_leaves_each_check_proves() -> None:
    """The checks and the leaves each closes. Delete this and a check can lose a leaf, or gain one
    it does not prove, with the page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        PACKS: ("M26.1.2", "M26.1.3", "M26.2.1", "M26.2.4", "M26.2.6"),
        DISABLE: ("M26.3.1",),
        AGENT: ("M26.3.2",),
        AUTOMATION: ("M26.3.3",),
        PERSONAL: ("M26.3.4",),
    }
    assert checks_in(MODULE) == [PACKS, DISABLE, AGENT, AUTOMATION, PERSONAL]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_jml") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def held(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    return {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608


def furnish(url: str) -> None:
    from brain.ops.starter import PACKS as FURNISHED
    from brain.ops.starter_store import furnish_packs
    from tests.unit.test_starter_pack_sync import furnished

    furnished(url, furnish_packs(FURNISHED))


@pytest.mark.needs_db
def test_the_checks_pass_on_a_furnished_install_and_leave_nothing(
    install: str, issuer: None
) -> None:
    """**The checks as the worker runs them, on an install that has been furnished.** They pass and
    leave no person, pack assignment, automation, session or ledger entry. Delete this and a check
    that commits, or one that cannot pass on a real schema, reaches the owner's server first."""
    furnish(install)
    before, also = counts(install), held(install)
    results = run_module(install, MODULE)
    assert results == dict.fromkeys((PACKS, DISABLE, AGENT, AUTOMATION, PERSONAL), (PASSED, ""))
    assert counts(install) == before
    assert held(install) == also


@pytest.mark.needs_db
def test_without_a_starter_pack_the_pack_check_says_it_was_not_run(
    install: str, issuer: None
) -> None:
    """An install whose Starter pack was never furnished or was retired cannot be asked what a
    joiner is given, and says so rather than failing. Delete this and such an install shows a red
    row for a decision somebody made."""
    from tests.fixtures.scratch_postgres import sql

    sql(install, "UPDATE gate.capability_pack SET deleted_at = now() WHERE name = 'starter'")
    try:
        outcome, reason = run_module(install, MODULE)[PACKS]
    finally:
        sql(install, "UPDATE gate.capability_pack SET deleted_at = NULL WHERE name = 'starter'")
    assert outcome == NOT_RUN, reason


@pytest.mark.needs_db
def test_a_sync_that_never_ends_a_leavers_pack_fails_the_pack_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A staff sync that gives packs and never ends a leaver's leaves them reading the company
    after they have gone. Delete this and M26.1.3 closes on a sync that only ever adds."""
    from brain.ops import starter_pack_store

    furnish(install)
    real = starter_pack_store.writes_for

    def keeps_leavers(plan: Any, pack_id: Any) -> list[Any]:
        return [
            one
            for one in real(plan, pack_id)
            if not ("leaver" in str(one.compile().params) and str(one).startswith("UPDATE"))
        ]

    monkeypatch.setattr(starter_pack_store, "writes_for", keeps_leavers)
    outcome, reason = run_module(install, MODULE)[PACKS]
    assert outcome == FAILED, reason
    assert "leaver kept" in reason


@pytest.mark.needs_db
def test_an_agent_that_is_not_stopped_when_its_owner_leaves_fails_the_agent_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leaver's agent that keeps running answers to nobody. Delete this and M26.3.2 closes on a
    sync that marks a person as having left and leaves their agent running."""
    from sqlalchemy import update

    from brain.ops import staff_sync_store
    from brain.tables.agent import AgentRow

    monkeypatch.setattr(
        staff_sync_store,
        "stop_leavers_agents",
        lambda now: update(AgentRow).where(AgentRow.id == "none").values(disabled_at=now),
    )
    outcome, reason = run_module(install, MODULE)[AGENT]
    assert outcome == FAILED, reason
    assert "was not stopped" in reason


@pytest.mark.needs_db
def test_a_personal_document_placed_at_the_department_fails_the_personal_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A document the person kept to themselves that the product places at department level is
    read by their colleagues. Delete this and M26.3.4 closes on a personal level that is not."""
    from brain.knowledge import uploads
    from brain.knowledge.visibility import Visibility

    real = uploads.placement_for_upload

    def widened(level: Any, **kwargs: Any) -> Any:
        return real(Visibility.DEPARTMENT if level is Visibility.PERSONAL else level, **kwargs)

    monkeypatch.setattr(uploads, "placement_for_upload", widened)
    outcome, reason = run_module(install, MODULE)[PERSONAL]
    assert outcome == FAILED, reason
    assert "somebody else" in reason
