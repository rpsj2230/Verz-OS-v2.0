"""The install check for a two-person approval, passing on PostgreSQL at head and failing with the
product broken the way it would plausibly break.

The pure half holds the module's place, the rule for which tools need two people and the in-memory
flow of a first and a second approval. The database half runs the check as the worker would and
then shows it failing with each half of the rule removed: the route letting the first approval
decide, the queue offering the action to the person it runs as, and `0218`'s check missing.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M13.7.7
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.console.role_surfaces import pending_for
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.scope import Scope
from brain.gate.leash import Action, ApprovalState, SuspendedAction, render_artefact
from brain.gate.suspension_store import needs_second_person
from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_two_person"
CHECK = "a_money_action_runs_only_after_two_other_people_approve_it"
NOW = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)


def tool(effect: SideEffect, *, sensitive: bool = False) -> ToolDefinition:
    return ToolDefinition(
        name="acc.record_thing",
        description="a thing",
        entity="ticket",
        required_capability="write:ticket.status",
        side_effect=effect,
        sensitive=sensitive,
    )


def test_the_module_declares_its_one_check_for_its_one_leaf() -> None:
    """Delete this and the check can lose M13.7.7 with the Install page showing the same rows."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(CHECK, ("M13.7.7",))]
    assert checks_in(MODULE) == [CHECK]


def test_only_a_tool_that_changes_something_outside_can_need_two_people() -> None:
    """Both halves, outside the function. Delete this and a read or a draft is held for two
    people, or a send and a money tool is held for one."""
    assert not needs_second_person(tool(SideEffect.NONE))
    assert not needs_second_person(tool(SideEffect.DRAFT, sensitive=True))
    assert needs_second_person(tool(SideEffect.MONEY))
    assert needs_second_person(tool(SideEffect.SEND))
    assert needs_second_person(tool(SideEffect.WRITE, sensitive=True))
    assert not needs_second_person(tool(SideEffect.WRITE))


WRITE = "write:ticket.status"
LATER = datetime(2999, 6, 1, 8, 0, tzinfo=UTC)


def reach_of(person: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id=person,
        grants=(Grant(capability=Capability(value=WRITE), scope=Scope.unrestricted()),),
    )


def two_person_action(*, two_person: bool = True, **extra: Any) -> SuspendedAction:
    """One suspension raised in 2999, as `suspend` builds one, run as `u_asker`."""
    action = Action(
        agent_id="agent_test",
        tool=tool(SideEffect.MONEY),
        target="ticket",
        row={"department": "web"},
    )
    return SuspendedAction(
        id="m_1",
        trace_id="trace_test",
        action=action,
        principal_id="u_asker",
        ent_hash="e" * 32,
        artefact=render_artefact(action),
        action_digest=action.digest(),
        raised_at=LATER,
        expires_at=LATER + timedelta(hours=4),
        two_person=two_person,
        **extra,
    )


def test_the_person_it_runs_as_and_the_first_approver_are_not_offered_a_two_person_action() -> None:
    """The queue's rule, on the model, with the one-person action beside it. Delete this and the
    asker or the first approver is offered the second approval, and the database is the only thing
    between them and a one-person run; or an action needing one person loses its asker's approval
    where the rung allows it."""
    when = LATER + timedelta(minutes=1)
    fresh = two_person_action()
    assert pending_for(reach_of("u_asker"), [fresh], when) == ()
    assert pending_for(reach_of("u_first"), [fresh], when) == (fresh,)
    first = fresh.endorsed("u_first", when)
    assert pending_for(reach_of("u_first"), [first], when) == ()
    assert pending_for(reach_of("u_second"), [first], when) == (first,)
    one = two_person_action(two_person=False)
    assert pending_for(reach_of("u_second"), [one], when) == (one,)


def test_a_two_person_action_is_approved_only_after_a_first_approval_by_somebody_else() -> None:
    """Every refusal of `approved_by` and `endorsed`, and the one acceptance. Delete this and the
    model approves with no first approval, by the endorser, or by the asker."""
    when = LATER + timedelta(minutes=1)
    fresh = two_person_action()
    with pytest.raises(ValueError, match="needs two people"):
        fresh.approved_by("u_second", when)
    first = fresh.endorsed("u_first", when)
    assert first.state is ApprovalState.PENDING and first.endorsed_by == "u_first"
    for refused in ("u_first", "u_asker"):
        with pytest.raises(ValueError, match="needs two people"):
            first.approved_by(refused, when)
    decided = first.approved_by("u_second", when)
    assert (decided.state, decided.decided_by, decided.endorsed_by) == (
        ApprovalState.APPROVED,
        "u_second",
        "u_first",
    )
    with pytest.raises(ValueError, match="first approval"):
        fresh.endorsed("u_asker", when)
    with pytest.raises(ValueError, match="first approval"):
        first.endorsed("u_second", when)
    with pytest.raises(ValueError, match="first approval"):
        two_person_action(two_person=False).endorsed("u_first", when)


def test_a_two_person_action_cannot_be_built_approved_without_two_others() -> None:
    """The model's own refusal, for a row loaded or a copy made some other way. Delete this and an
    approved two-person action built from a row nobody endorsed constructs."""
    with pytest.raises(ValueError, match=r"needs two people|first approver"):
        two_person_action(
            state=ApprovalState.APPROVED, decided_by="u_second", decided_at=LATER, endorsed_by=""
        )
    with pytest.raises(ValueError, match="endorse"):
        two_person_action(endorsed_by="u_asker", endorsed_at=LATER)


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_two_person") as url:
        yield url


def run_check(url: str) -> tuple[str, str]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    [only] = results
    return only.outcome, only.reason


@pytest.mark.needs_db
def test_the_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The check as the worker runs it.** It passes, and no suspension, setting or ledger entry
    is left. Delete this and a check that can never pass on a real schema, or that leaves the
    switch on, reaches the owner's server."""
    from tests.fixtures.scratch_postgres import sql

    before = (counts(install), sql(install, "SELECT count(*) FROM gate.suspension"))
    assert run_check(install) == (PASSED, "")
    assert (counts(install), sql(install, "SELECT count(*) FROM gate.suspension")) == before
    assert not sql(install, "SELECT 1 FROM ops.setting WHERE key = 'feature.two_person_approval'")


@pytest.mark.needs_db
def test_a_first_approval_that_decides_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route treating every approval as a decision. Delete this and M13.7.7 closes on a
    route that lets one person approve."""
    from brain import approval_routes

    monkeypatch.setattr(approval_routes, "endorse", lambda *args, **kwargs: None)
    outcome, _ = run_check(install)
    assert outcome == FAILED


@pytest.mark.needs_db
def test_a_queue_that_offers_the_action_to_whoever_it_runs_as_fails_the_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The queue's exclusion removed. Delete this and the person an action runs as is offered it
    to approve, and M13.7.7 closes on a rule only the database holds."""
    from brain.console import role_surfaces

    real = role_surfaces._may_approve

    def anybody(suspension: Any, entitlement: Any, now: Any) -> bool:
        return real(suspension.model_copy(update={"two_person": False}), entitlement, now)

    monkeypatch.setattr(role_surfaces, "_may_approve", anybody)
    outcome, reason = run_check(install)
    assert outcome == FAILED and "runs as" in reason


@pytest.mark.needs_db
def test_a_database_without_the_checks_fails_the_check(install: str) -> None:
    """`0218`'s approval check dropped. Delete this and the check passes on a database that holds
    the rule nowhere, which is the half it exists to prove."""
    from tests.fixtures.scratch_postgres import sql

    name = sql(
        install,
        "SELECT conname FROM pg_constraint WHERE conrelid = 'gate.suspension'::regclass "
        "AND conname LIKE '%a_two_person_row_is_approved_by_two_others'",
    )[0][0]
    sql(install, f'ALTER TABLE gate.suspension DROP CONSTRAINT "{name}"')
    try:
        outcome, reason = run_check(install)
        assert outcome == FAILED and "database allowed" in reason
    finally:
        sql(
            install,
            f'ALTER TABLE gate.suspension ADD CONSTRAINT "{name}" CHECK (NOT two_person OR '
            "state <> 'approved' OR (endorsed_by IS NOT NULL AND decided_by <> endorsed_by "
            "AND decided_by <> principal_id))",
        )


def test_the_states_a_decision_can_take_are_unchanged() -> None:
    """A first approval adds no fourth state. Delete this and an endorsed row gets a state of its
    own, which `resume` and every verdict check would then have to know about."""
    assert {one.value for one in ApprovalState} == {"pending", "approved", "rejected"}
