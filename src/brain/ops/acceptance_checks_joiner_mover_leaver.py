"""The install acceptance checks for a person joining, moving and leaving, through the objects the
nightly staff sync really writes.

`brain.identity.lifecycle` is the pure model of the three transitions and nothing calls it: the
real joiner, mover and leaver work is done by `brain.ops.staff_sync_run`, which gives each joiner
the Starter pack over their own department (`brain.ops.starter_pack_store`), retires and re-gives it
when somebody moves, ends it for a leaver, disables a leaver's agents (`stop_leavers_agents`) and
stops an automation whose owner has gone (`brain.ops.automation_owner`). **So these checks write
those objects with the functions the run calls, against the install's own schema, and read the
result the way the next request does**, rather than proving the in-memory twin.

**What a check does not do.** It calls no staff directory and no sign-in service, so nothing is
fetched and nobody is emailed; the staff list is a stand-in under the source name `acceptance`, the
people are reserved and every write is in the harness's transaction, which is rolled back.

**An install with no Starter pack says so.** The pack is written by the application's furnishing on
its first start, and an administrator may have retired it; either way the check cannot ask what the
pack gives, and it says it was not run rather than failing a decision somebody made.

Rejected: one check walking a person through all three, which would be one red row for nine leaves.
The starter-pack check is one flow (join, move, leave) because each step is the previous one's
state; the disable, the agent and the automation are each their own.

Task ids: M26.1.2, M26.1.3, M26.2.1, M26.2.4, M26.2.6, M26.3.1, M26.3.2, M26.3.3
"""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import insert, select

from brain.identity.staff_roster import digest_of
from brain.identity.staff_source import (
    DEFAULT_TRUST,
    EmploymentStatus,
    Roster,
    StaffRecord,
)
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import SET_UP_REACH, Harness
from brain.tables.audit import attributed_to

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1800

A, B = RESERVED_DEPARTMENTS

#: The staff source the check lists people from. No install chooses a source by this name.
SOURCE: Final = "acceptance"

# ------------------------------------------------------------------ written-down reasons
#: Said when the install has no Starter pack to give.
NO_STARTER_PACK_TO_GIVE: Final = (
    "this install has no live Starter pack the staff sync can give, which the application writes "
    "on its first start and an administrator may have retired, so what a joiner is given cannot "
    "be asked here"
)


def _address(h: Harness, principal_id: str) -> str:
    return f"{principal_id.replace('.', '-')}-{h.run}@acceptance.invalid"


def _listed(h: Harness, principal_id: str, department: str, *, left: bool = False) -> StaffRecord:
    return StaffRecord(
        _address(h, principal_id),
        "Acceptance check",
        department=department,
        active=not left,
        status=EmploymentStatus.LEFT if left else EmploymentStatus.ACTIVE,
    )


def _roster(*people: StaffRecord) -> Roster:
    return Roster(source=SOURCE, complete=True, asserts=DEFAULT_TRUST["lark"], people=tuple(people))


async def _packs(h: Harness, principals: list[str]) -> dict[str, str]:
    """The department each person's live Starter pack is over, by person, that a sync gave."""
    from brain.identity.starter_pack_sync import department_of
    from brain.ops.starter_pack_store import the_starter_pack
    from brain.tables.gate import CapabilityPackAssignmentRow

    found = (await h.execute(the_starter_pack())).first()
    if found is None:
        raise CheckNotRunError(NO_STARTER_PACK_TO_GIVE)
    from brain.core.scope import Scope

    rows = await h.execute(
        select(CapabilityPackAssignmentRow.principal_id, CapabilityPackAssignmentRow.scope).where(
            CapabilityPackAssignmentRow.pack_id == found[0],
            CapabilityPackAssignmentRow.principal_id.in_(principals),
            CapabilityPackAssignmentRow.deleted_at.is_(None),
            CapabilityPackAssignmentRow.granted_by == f"roster.{SOURCE}",
        )
    )
    return {str(who): department_of(Scope.model_validate(scope)) or "" for who, scope in rows.all()}


async def _give(h: Harness, roster: Roster) -> None:
    """The nightly run's Starter pack step, in the check's transaction."""
    from brain.ops.starter_pack_store import grant_starter_packs

    async with h.sessions() as session:
        # Attributed to the run, as every set-up write of a check is, so the ledger's entry for
        # each grant names the run rather than the placeholder.
        for statement in attributed_to(
            actor_id=h.actor, ent_hash=SET_UP_REACH, trace_id=h.trace_id
        ):
            await session.execute(statement)
        plan = await grant_starter_packs(session, roster, read_at=h.now)
        await session.commit()
    if plan.refusals:
        raise CheckNotRunError(NO_STARTER_PACK_TO_GIVE)


@check(
    leaves=("M26.1.2", "M26.1.3", "M26.2.1", "M26.2.4", "M26.2.6"),
    sentence=(
        "Through the staff sync's Starter pack step: a joiner is given the pack over their own "
        "department only; a person the list moves gets the new department's pack and loses the "
        "old one's, and a leaver loses theirs. With no reindex, the first department's document "
        "is readable to the mover before the move and not after, and their cache key changes."
    ),
)
async def a_joiner_gets_a_department_pack_and_a_mover_or_leaver_loses_it(
    h: Harness,
) -> None:
    from brain.gate.cache_key import key_for
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in
    from brain.ops.acceptance_checks_accounts import _joined
    from brain.ops.acceptance_checks_lifecycle import _added, _as, _live

    await h.found_departments()
    steward, joiner = h.principal(A, "steward"), h.principal(A, "joiner")
    mover, leaver = h.principal(A, "mover"), h.principal(B, "leaver")
    await h.person(steward, department=A, grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value))
    for pid, department in ((joiner, A), (mover, A), (leaver, B)):
        await h.person(pid, department=department)
        await _joined(h, pid)
    item = await _added(h, steward, h.word())

    await _give(h, _roster(_listed(h, joiner, A), _listed(h, mover, A), _listed(h, leaver, B)))
    if await _packs(h, [joiner, mover, leaver]) != {joiner: A, mover: A, leaver: B}:
        raise CheckFailedError("a joiner was not given the Starter pack over their own department")
    if await _live(h, await _as(h, mover), item) is None:
        raise CheckFailedError("a joiner could not read their own department's document")
    if await _live(h, await _as(h, leaver), item) is not None:
        raise CheckFailedError("a joiner in another department read a document that is not theirs")

    asked_before = (await h.reach(mover)).ent_hash()

    # The next night: the list moves one of them and marks another as having left. Nothing is
    # reindexed between the two runs.
    from brain.tables.staff import StaffMemberRow

    await h.execute(
        *h.attributed(),
        insert(StaffMemberRow).values(
            source=SOURCE,
            address_hash=digest_of(_address(h, leaver)),
            display_name="Acceptance check",
            first_listed_at=h.now,
            last_listed_at=h.now,
            left_at=h.now,
            left_because="source_says_left",
            status="left",
        ),
    )
    await _give(
        h,
        _roster(_listed(h, joiner, A), _listed(h, mover, B), _listed(h, leaver, B, left=True)),
    )
    if await _packs(h, [joiner, mover, leaver]) != {joiner: A, mover: B}:
        raise CheckFailedError(
            "a mover was not moved to the new department's pack, or a leaver kept"
        )
    if await _live(h, await _as(h, mover), item) is not None:
        raise CheckFailedError("a person who moved out still read the department they left")
    asked_after = (await h.reach(mover)).ent_hash()
    words = "What does my team do here"
    if asked_before == asked_after or key_for(words, asked_before, "agent", 1, {}) == key_for(
        words, asked_after, "agent", 1, {}
    ):
        raise CheckFailedError(
            "a person who moved would be served an answer cached before the move"
        )
    if await _live(h, await _as(h, joiner), item) is None:
        raise CheckFailedError("a person who did not move lost their department's document")


@check(
    leaves=("M26.3.1",),
    sentence=(
        "A Super Admin disables a person who is signed in: their session is ended and the gate "
        "refuses their next request on it, and they hold nothing; enabled again they sign in "
        "afresh."
    ),
)
async def a_disabled_person_is_refused_on_the_next_request_and_signed_out(
    h: Harness,
) -> None:
    from brain.ops.acceptance_people_console_2 import gate_refuses
    from brain.ops.acceptance_people_signed_in import administrator, console, everywhere
    from brain.principal_state_routes import StateAsked, disable_person, enable_person
    from brain.tables.identity import SessionRow

    await h.found_departments()
    c = await console(h)
    keeper, leaving = h.principal(A, "keeper"), h.principal(A, "leaving")
    await h.person(keeper, department=A, grants=everywhere(*administrator()))
    await h.person(leaving, department=A)
    session = c.session()
    await c.asked(leaving, strong=False, session=session)
    asked = await c.asked(keeper)
    with c.as_route():
        done = await disable_person(c.request(), StateAsked(principal_id=leaving), asked)
    if done.status_code != 200:
        raise CheckFailedError("a Super Admin could not disable a person")
    if not await gate_refuses(c, leaving, strong=False, session=session):
        raise CheckFailedError("a disabled person's next request was answered")
    live = await h.execute(
        select(SessionRow.id).where(
            SessionRow.principal_id == leaving, SessionRow.ended_at.is_(None)
        )
    )
    if live.first() is not None:
        raise CheckFailedError("a disabled person still has a session that is not ended")
    if (await h.reach(leaving)).grants:
        raise CheckFailedError("a disabled person still held grants")
    with c.as_route():
        back = await enable_person(c.request(), StateAsked(principal_id=leaving), asked)
    if back.status_code != 200 or await gate_refuses(c, leaving, strong=False):
        raise CheckFailedError("a person enabled again could not sign in afresh")


async def _owned_agent(h: Harness, owner: str, name: str) -> str:
    """An enabled agent of acceptance_a owned by `owner`, as the agent checks make one."""
    from brain.ops.acceptance_checks_agent_reach import _agent

    return str(await _agent(h, owner, name, ["read:knowledge"]))


@check(
    leaves=("M26.3.2",),
    sentence=(
        "A person the staff list marks as having left has their agent stopped by the sync's own "
        "statement, the agent is listed on Transfers for an administrator who may take it, and "
        "taking it gives it that administrator as owner and starts it again; an agent whose "
        "owner has not left is not stopped."
    ),
)
async def a_leaver_s_agent_stops_is_listed_for_adoption_and_is_taken_on(h: Harness) -> None:
    from datetime import timedelta

    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.acceptance_checks_accounts import _joined
    from brain.ops.acceptance_people_signed_in import administrator, console, within
    from brain.ops.staff_sync_store import stop_leavers_agents
    from brain.staff_source_routes import staff_transfers, take_transfer
    from brain.tables.agent import AgentRow
    from brain.tables.staff import StaffMemberRow

    await h.found_departments()
    c = await console(h)
    leaver, stays, admin = (
        h.principal(A, "leaver"),
        h.principal(A, "stays"),
        h.principal(A, "admin"),
    )
    for pid in (leaver, stays):
        await h.person(pid, department=A)
        await _joined(h, pid)
    await h.person(admin, department=A, grants=within(A, *administrator(), "read:knowledge"))
    gone, kept = await _owned_agent(h, leaver, "gone"), await _owned_agent(h, stays, "kept")
    await h.execute(
        *h.attributed(),
        insert(StaffMemberRow).values(
            source=SOURCE,
            address_hash=digest_of(_address(h, leaver)),
            display_name="Acceptance check",
            first_listed_at=h.now - timedelta(days=1),
            last_listed_at=h.now,
            left_at=h.now,
            left_because="source_says_left",
            status="left",
        ),
    )
    await h.execute(*h.attributed(), stop_leavers_agents(h.now))

    async def disabled(agent_id: str) -> bool:
        found = await h.execute(select(AgentRow.disabled_at).where(AgentRow.id == agent_id))
        return found.scalar_one() is not None

    if not await disabled(gone):
        raise CheckFailedError("a leaver's agent was not stopped")
    if await disabled(kept):
        raise CheckFailedError("an agent whose owner had not left was stopped")
    asked = await c.asked(admin)
    with c.as_route():
        listed = await staff_transfers(c.request(), asked)
    if gone not in {one.agent_id for one in listed.transfers}:
        raise CheckFailedError("a leaver's agent was not listed for adoption")
    if kept in {one.agent_id for one in listed.transfers}:
        raise CheckFailedError("an agent whose owner had not left was listed for adoption")
    with c.as_route():
        taken = await take_transfer(c.request(), gone, asked)
    if taken.owner_id != admin or await disabled(gone):
        raise CheckFailedError("taking a leaver's agent did not give it the new owner and start it")
    if await StoredPrincipals(h.sessions).live_principal(admin) is None:
        raise CheckFailedError("the administrator who took the agent was not a live person")


@check(
    leaves=("M26.3.3",),
    sentence=(
        "An automation whose owner is disabled is listed as awaiting an owner, is refused as an "
        "owner-less run and runs for nobody; another live person may adopt it and it runs again."
    ),
)
async def an_automation_waits_for_an_owner_when_its_owner_is_disabled(
    h: Harness,
) -> None:
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.core.scope import Scope
    from brain.identity.principal_state_store import StoredPrincipalStates
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.automation_owner import (
        AutomationRefusal,
        AutomationRefusedError,
        adopt,
        awaiting_owner,
        owner_of,
        register,
    )
    from brain.ops.automation_owner_store import StoredAutomations

    await h.found_departments()
    owner, successor = h.principal(A, "owner"), h.principal(A, "successor")
    await h.person(owner, department=A)
    await h.person(successor, department=A)
    principals = StoredPrincipals(h.sessions)
    live = await principals.live_principal(owner)
    if live is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    automation_id = f"acceptance-{h.run}-owned"
    issued = register(
        automation_id=automation_id,
        owner=live,
        declared_tools=frozenset({"knowledge.search_documents"}),
        ceiling=EntitlementSet(
            principal_id=automation_id,
            grants=(
                Grant(capability=Capability(value="read:knowledge"), scope=Scope.unrestricted()),
            ),
        ),
        now=h.now,
    )
    store = StoredAutomations(h.sessions)
    await store.put(issued.registration)
    if await awaiting_owner([issued.registration], principals=principals, now=h.now):
        raise CheckFailedError("an automation with a live owner was listed as awaiting one")
    if (await owner_of(issued.registration, principals=principals, now=h.now)).id != owner:
        raise CheckFailedError("a running automation did not run as its owner")

    await StoredPrincipalStates(h.sessions).set_disabled(
        owner,
        disabled=True,
        may=lambda _department: True,
        by=h.actor,
        ent_hash="0" * 32,
        trace_id=h.trace_id,
    )
    if await awaiting_owner([issued.registration], principals=principals, now=h.now) != (
        automation_id,
    ):
        raise CheckFailedError("an automation whose owner was disabled was not awaiting an owner")
    try:
        await owner_of(issued.registration, principals=principals, now=h.now)
    except AutomationRefusedError as refused:
        if refused.reason is not AutomationRefusal.OWNER_GONE:
            raise CheckFailedError(
                "a stopped automation was refused for another reason"
            ) from refused
    else:
        raise CheckFailedError("an automation whose owner was disabled still ran")
    new_owner = await principals.live_principal(successor)
    if new_owner is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    taken: Any = adopt(issued.registration, current_owner=None, new_owner=new_owner, now=h.now)
    if taken.owner_principal_id != successor:
        raise CheckFailedError("a live person could not adopt an automation awaiting an owner")
