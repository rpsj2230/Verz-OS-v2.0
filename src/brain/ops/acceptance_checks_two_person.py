"""The install acceptance check that an action which cannot be taken back runs only after two
different people have approved it, and that the database says so as well as the route (M13.7.7).

**It holds a money action for a person and walks it through the approval the way the console
does.** With the `two_person_approval` switch on inside the check's rolled-back transaction, an
agent's money action is held for the person who asked. The check reads the queue as three people.
The asker is offered nothing, because the person an action runs as never approves it. The first
approver is offered it, and approving it decides nothing: the row stays pending, still holds no
decision and no ledger entry, and is not offered to that approver again. The second approver is
offered it as the second of two, and approving it decides it, naming a decider who is neither the
asker nor the first approver. Every call is `brain.approval_routes.take_decision`, the function the
decision route and a card press both call.

**Then the database is asked on its own.** `0221`'s checks are the rule beneath the route, and a
check that only drove the route would pass with them deleted. Four statements are tried as the
application role in a savepoint each and must be refused by name: approving a row nobody has
endorsed, deciding it as the person who endorsed it, deciding it as the person who asked, and
endorsing it as the person who asked. A fifth, the legitimate second approval, is accepted, so a
database that refused everything does not pass.

**The switch is the owner's and the check leaves it as it found it.** It is turned on in the
check's own transaction, which is rolled back with everything else, so an install that has it off
is left off. Whether an action needs two is fixed when it is raised (`put_suspension` writes it),
so the check raises its own.

**What this is not.** It does not prove the Lark card draws a first approval differently, and it
proves the rule for a money action only, because `needs_second_person` is where the owner's answer
to needs-rupash 192 decides which other effects join it.

Task ids: M13.7.7
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_people_signed_in import within
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1710

A, B = RESERVED_DEPARTMENTS

#: What the action the check holds requires, and what its approvers decide with.
ACTION_CAPABILITY: Final = "write:invoice.record"

#: The constraints of `0221` the check expects the database to refuse with, by their own names.
TWO_OTHERS: Final = "a_two_person_row_is_approved_by_two_others"
ASKER_DOES_NOT: Final = "the_asker_does_not_endorse"


async def _held(h: Harness, asker: str, number: int) -> str:
    """One money action of an agent held for a person, as the gate holds it, and its id."""
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.envelope import SideEffect, ToolDefinition
    from brain.core.field_policy import FieldPolicy
    from brain.core.scope import Scope
    from brain.gate.injection import AutonomyTier, RiskAssessment
    from brain.gate.leash import Action, Leash, LeashEntry, decide, suspend
    from brain.gate.suspension_store import StoredSuspensions, put_suspension

    agent = f"acceptance_{h.run}_agent"
    target = f"acceptance_{h.run}.record_invoice"
    action = Action(
        agent_id=agent,
        tool=ToolDefinition(
            name=target,
            description="The acceptance check's own action, which changes nothing anywhere",
            entity="invoice",
            required_capability=ACTION_CAPABILITY,
            side_effect=SideEffect.MONEY,
        ),
        target=target,
        row={"department": A},
    )
    asking = await h.reach(asker)
    decided = decide(
        action,
        caller=asking,
        agent_ceiling=EntitlementSet(
            principal_id=agent,
            grants=(
                Grant(capability=Capability(value=ACTION_CAPABILITY), scope=Scope.unrestricted()),
            ),
        ),
        policy=FieldPolicy(rules=()),
        leash=Leash(
            entries=(
                LeashEntry(
                    agent_id=agent,
                    target=target,
                    scope=Scope.unrestricted(),
                    rung=AutonomyTier.ASSISTED,
                ),
            )
        ),
        assessment=RiskAssessment(score=0, matched=()),
        now=h.now,
    )
    raised = suspend(
        action,
        decided,
        principal_id=asker,
        trace_id=h.trace_id,
        now=h.now,
        suspension_id=f"acceptance_{h.run}_two_{number}",
    )
    async with StoredSuspensions(h.sessions).holding(asking, h.now) as rows:
        await put_suspension(rows.session, raised)
    return raised.id


async def _offered(h: Harness, reader: str, one: str) -> bool:
    """Whether the Approvals queue offers this reader this suspension."""
    from brain.approval_routes import queue
    from brain.gate.suspension_store import StoredSuspensions

    reach = await h.reach(reader)
    waiting = await StoredSuspensions(h.sessions).reading_as(reach, h.now).open_suspensions()
    return any(card.suspension_id == one for card in queue(waiting, reach, h.now).items)


async def _row(h: Harness, one: str) -> dict[str, object]:
    found = (
        (
            await h.execute(
                text(
                    "SELECT state, two_person, endorsed_by, decided_by FROM gate.suspension "
                    "WHERE id = :id"
                ).bindparams(id=one)
            )
        )
        .mappings()
        .one()
    )
    return dict(found)


async def _database_says(h: Harness, as_whom: str, one: str, statement: str) -> str | None:
    """The check constraint the database refused this statement with, or None when it accepted it.

    Tried as the application role at `as_whom`'s reach, in a savepoint that is undone."""
    from brain.gate.suspension_store import StoredSuspensions

    reach = await h.reach(as_whom)
    async with StoredSuspensions(h.sessions).holding(reach, h.now) as rows:
        nested = await rows.session.begin_nested()
        try:
            await rows.session.execute(text(statement).bindparams(who=as_whom, id=one, at=h.now))
        except DBAPIError as exc:
            diag = getattr(exc.orig, "diag", None)
            return str(getattr(diag, "constraint_name", None) or "refused")
        finally:
            await nested.rollback()
    return None


@check(
    leaves=("M13.7.7",),
    sentence=(
        "With the two-person switch on, a money action held for a person is not offered to the "
        "person it runs as, a first approval decides nothing and is not offered again to its "
        "giver, a second person's approval decides it, and the database refuses an approval "
        "nobody endorsed, one by the endorser or the asker, and an endorsement by the asker."
    ),
)
async def a_money_action_runs_only_after_two_other_people_approve_it(h: Harness) -> None:
    from brain.approval_routes import (
        DecidableVerdict,
        DecisionAsked,
        take_decision,
    )
    from brain.console.approvals import Decided, Endorsed
    from brain.core.errors import Absent
    from brain.gate.suspension_store import StoredSuspensions
    from brain.ops.acceptance_run import SET_UP_REACH
    from brain.ops.features import TWO_PERSON_APPROVAL, switch
    from brain.tables.audit import attributed_to

    await h.found_departments()
    asker, first, second = (h.principal(A, role) for role in ("asker", "first", "second"))
    for one in (asker, first, second):
        await h.person(one, department=A, grants=within(A, ACTION_CAPABILITY, "approve:action"))
    async with h.sessions() as session:
        for statement in attributed_to(
            actor_id=h.actor, ent_hash=SET_UP_REACH, trace_id=h.trace_id
        ):
            await session.execute(statement)
        await switch(session, TWO_PERSON_APPROVAL, on=True, by=h.actor)
        await session.commit()

    store = StoredSuspensions(h.sessions)
    approve = DecisionAsked(verdict=DecidableVerdict.APPROVED)
    held = await _held(h, asker, 1)
    if not (await _row(h, held))["two_person"]:
        raise CheckFailedError("a money action was held as needing one person with the switch on")
    if await _offered(h, asker, held):
        raise CheckFailedError("the person an action runs as was offered it to approve")
    if not await _offered(h, first, held):
        raise CheckFailedError("an approver was not offered a two-person action")

    async def pressed(who: str, one: str) -> Decided | Endorsed:
        return await take_decision(
            store,
            one,
            await h.reach(who),
            approve,
            trace_id=h.trace_id,
            now=h.now,
        )

    if not isinstance(await pressed(first, held), Endorsed):
        raise CheckFailedError("the first approval of a two-person action decided it")
    row = await _row(h, held)
    if (row["state"], row["endorsed_by"], row["decided_by"]) != ("pending", first, None):
        raise CheckFailedError("a first approval did not leave the row pending and name its giver")
    if await _offered(h, first, held):
        raise CheckFailedError("the first approver was offered the action for the second approval")
    try:
        await pressed(first, held)
    except Absent:
        pass
    else:
        raise CheckFailedError("the first approver gave the second approval as well")
    try:
        await pressed(asker, held)
    except Absent:
        pass
    else:
        raise CheckFailedError("the person an action runs as approved it")
    if not await _offered(h, second, held):
        raise CheckFailedError("a second approver was not offered an endorsed action")
    if not isinstance(await pressed(second, held), Decided):
        raise CheckFailedError("a second person's approval did not decide the action")
    row = await _row(h, held)
    if (row["state"], row["endorsed_by"], row["decided_by"]) != ("approved", first, second):
        raise CheckFailedError("the decision did not name two different people")

    # The database, asked on its own. A fresh action, so each statement meets a pending row.
    fresh = await _held(h, asker, 2)
    decide_as = (
        "UPDATE gate.suspension SET state = 'approved', verdict = 'approved', decided_by = :who, "
        "decided_at = :at WHERE id = :id"
    )
    endorse_as = "UPDATE gate.suspension SET endorsed_by = :who, endorsed_at = :at WHERE id = :id"
    if not (await _database_says(h, second, fresh, decide_as) or "").endswith(TWO_OTHERS):
        raise CheckFailedError("the database allowed a two-person action approved by one person")
    if not (await _database_says(h, asker, fresh, endorse_as) or "").endswith(ASKER_DOES_NOT):
        raise CheckFailedError("the database allowed the person an action runs as to endorse it")
    await pressed(first, fresh)
    if not (await _database_says(h, first, fresh, decide_as) or "").endswith(TWO_OTHERS):
        raise CheckFailedError("the database allowed the endorser to decide the action")
    if not (await _database_says(h, asker, fresh, decide_as) or "").endswith(TWO_OTHERS):
        raise CheckFailedError("the database allowed the person it runs as to decide the action")
    if await _database_says(h, second, fresh, decide_as) is not None:
        raise CheckFailedError("the database refused the second person's approval")
