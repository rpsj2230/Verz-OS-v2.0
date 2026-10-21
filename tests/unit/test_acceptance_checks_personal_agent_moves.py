"""The personal-agent-follows-its-owner install check, passing at head and failing when broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M26.2.2
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, registered
from tests.fixtures.console_proof import counts, run_module
from tests.unit.test_acceptance import INSTALL, at_head, checks_in
from tests.unit.test_acceptance_checks_joiner_mover_leaver import furnish

MODULE = "brain.ops.acceptance_checks_personal_agent_moves"
CHECK = "a_personal_agent_reaches_the_new_department_when_its_owner_moves"


def test_the_module_declares_the_leaf_its_check_proves() -> None:
    """Delete this and the check can lose its leaf, or gain one it does not prove, with the
    Install page unchanged."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {CHECK: ("M26.2.2",)}
    assert checks_in(MODULE) == [CHECK]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_personal_agent_moves") as url:
        yield url


@pytest.fixture
def issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


@pytest.mark.needs_db
def test_the_check_passes_on_a_furnished_install_and_leaves_nothing(
    install: str, issuer: None
) -> None:
    """**The check as the worker runs it, on a furnished install.** It passes and leaves no agent,
    person, pack assignment or ledger entry. Delete this and a check that commits, or one that
    cannot pass on a real schema, reaches the owner's server first."""
    furnish(install)
    before = counts(install)
    assert run_module(install, MODULE) == {CHECK: (PASSED, "")}
    assert counts(install) == before


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
def test_a_personal_agent_anybody_can_see_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The audience question answered yes for everybody. Delete this and the check passes on a
    personal agent offered to the owner's whole department."""
    from brain.agents import model

    furnish(install)
    monkeypatch.setattr(model, "visible_to", lambda audience, viewer: True)
    outcome, reason = run_module(install, MODULE)[CHECK]
    assert outcome == FAILED, reason
    assert "besides its owner" in reason


@pytest.mark.needs_db
def test_a_run_that_reaches_nothing_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run's reach narrowed to nothing before and after: the agent follows nobody. Delete this
    and the check passes on an agent that never reached its owner's department at all."""
    from brain.console import workspace_capabilities
    from brain.core.entitlement import EntitlementSet

    furnish(install)
    monkeypatch.setattr(
        workspace_capabilities,
        "run_reach",
        lambda caller, record: EntitlementSet(principal_id=caller.principal_id, grants=()),
    )
    outcome, reason = run_module(install, MODULE)[CHECK]
    assert outcome == FAILED, reason
    assert "own department first" in reason


@pytest.mark.needs_db
def test_a_move_that_edits_the_agent_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second sync step rewriting the personal agent's row, as a move that touched agents would.
    Delete this and the check passes on a product that edits the owner's agent when they move,
    which is how an agent ends up with the wrong department."""
    from sqlalchemy import update

    from brain.ops import acceptance_checks_joiner_mover_leaver as moving
    from brain.tables.agent import AgentRow

    furnish(install)
    real = moving._give
    calls = {"n": 0}

    async def giving(h: object, roster: object) -> None:
        await real(h, roster)  # type: ignore[arg-type]
        calls["n"] += 1
        if calls["n"] == 2:
            await h.execute(  # type: ignore[attr-defined]
                *h.attributed(),  # type: ignore[attr-defined]
                update(AgentRow).values(display_name="Edited by the move"),
            )

    monkeypatch.setattr(moving, "_give", giving)
    outcome, reason = run_module(install, MODULE)[CHECK]
    assert outcome == FAILED, reason
    assert "record was changed" in reason


def _after_the_move(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """A flag that turns true once the check's second sync step has run, for breaking the product
    only after the move."""
    from brain.ops import acceptance_checks_joiner_mover_leaver as moving

    real = moving._give
    state = {"moved": 0, "calls": 0}

    async def giving(h: object, roster: object) -> None:
        await real(h, roster)  # type: ignore[arg-type]
        state["calls"] += 1
        state["moved"] = int(state["calls"] >= 2)

    monkeypatch.setattr(moving, "_give", giving)
    return state


@pytest.mark.needs_db
def test_an_agent_that_keeps_the_old_departments_reach_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the move the run's reach is the old reach and the new one together. Delete this and
    the check passes on an agent that keeps what its owner left."""
    from brain.console import workspace_capabilities
    from brain.core.entitlement import EntitlementSet, Grant
    from brain.core.scope import Scope
    from brain.knowledge.search import KNOWLEDGE_READ

    furnish(install)
    state = _after_the_move(monkeypatch)
    real = workspace_capabilities.run_reach

    def keeping(caller: EntitlementSet, record: object) -> EntitlementSet:
        if not state["moved"]:
            return real(caller, record)  # type: ignore[arg-type]
        # Everything, as an agent that kept the old department beside the new would read.
        everything = Grant(capability=KNOWLEDGE_READ, scope=Scope.unrestricted())
        return EntitlementSet(principal_id=caller.principal_id, grants=(everything,))

    monkeypatch.setattr(workspace_capabilities, "run_reach", keeping)
    outcome, reason = run_module(install, MODULE)[CHECK]
    assert outcome == FAILED, reason
    assert "did not follow" in reason


@pytest.mark.needs_db
def test_an_agent_offered_to_everybody_once_its_owner_moves_fails_the_check(
    install: str, issuer: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Visibility widening only after the move. Delete this and the check passes on a move that
    offers the owner's personal agent to the department they left."""
    from brain.agents import model

    furnish(install)
    state = _after_the_move(monkeypatch)
    real = model.visible_to
    monkeypatch.setattr(
        model,
        "visible_to",
        lambda audience, viewer: True if state["moved"] else real(audience, viewer),
    )
    outcome, reason = run_module(install, MODULE)[CHECK]
    assert outcome == FAILED, reason
    assert "changed when its owner moved" in reason
