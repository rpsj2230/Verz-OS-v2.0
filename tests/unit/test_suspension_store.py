"""A suspended action is kept once, read back against its own digest, read by an approver only
through what their reach holds, decided once under a lock, and resumed at the reach as it is now.

The first half is decisions over a row's values and runs anywhere. The second builds
`gate.suspension` through `0042` and drives it as the application role, through
`brain.gate.suspension_store.StoredSuspensions` itself; it skips when there is no server, as every
file using `tests.fixtures.scratch_postgres` does. A test near the top of that half proves the
store's connection really is the application role, because a store connected as the superuser
passes every row-level security test here by bypassing the policies.

The clock is 2999, for the reason CLAUDE.md records about fixtures that go off.

Task ids: M35.3.1.1, M33.6.1.3
"""

from __future__ import annotations

import asyncio
import importlib.util
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from brain.approval_routes import (
    DecidableVerdict,
    DecisionAsked,
    RejectionReason,
    decide_once,
    queue,
)
from brain.audit.ledger import AuditChain
from brain.audit.record import AuditRecorder
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.field_policy import Classification, FieldPolicy, FieldRule
from brain.core.scope import Clause, Op, Scope
from brain.db import normalise_database_url
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.gate.leash import (
    Action,
    ApprovalState,
    Leash,
    LeashEntry,
    ResumeRefusal,
    SuspendedAction,
    render_artefact,
)
from brain.gate.suspension_store import (
    HeldRows,
    StoredSuspensions,
    SuspensionStoreError,
    approvable,
    put_suspension,
    resume_stored,
    row_values,
    stored_from,
)
from brain.session import make_session_factory
from tests.fixtures.operation_ledger import MemoryLedger
from tests.fixtures.scratch_postgres import (
    ROOT,
    drop,
    fresh,
    migrate,
    modelled,
    present,
    run,
    secured,
    shape,
    sql,
)

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
TABLES: tuple[str, ...] = ("gate.suspension",)
MIGRATION = ROOT / "migrations" / "versions" / "0042_suspension.py"

WRITE_STATUS = "write:ticket.status"
READ_STATUS = "read:ticket.status"
MAINTENANCE = "maintenance"
FINANCE = "finance"
ASKER = "u_asker"


class Ticket(Entity):
    status: str = ""


STATUS_TOOL = ToolDefinition(
    name="ticket.update_status",
    description="Set the status of a support ticket",
    entity="ticket",
    required_capability=WRITE_STATUS,
    side_effect=SideEffect.WRITE,
    identity_mode=IdentityMode.DELEGATED,
)

INVOICE_TOOL = ToolDefinition(
    name="books.create_invoice",
    description="Raise an invoice",
    entity="invoice",
    required_capability="write:invoice.amount",
    side_effect=SideEffect.MONEY,
)

POLICY = FieldPolicy(
    rules=(FieldRule.of("ticket", "status", READ_STATUS, Classification.INTERNAL),)
)
CLEAN = RiskAssessment(score=0, matched=())


def in_department(department: str) -> Scope:
    return Scope(clauses=(Clause(field="department", op=Op.EQ, value=department),))


def reach(
    principal_id: str,
    *capabilities: str,
    scope: Scope | None = None,
    not_after: datetime | None = None,
) -> EntitlementSet:
    where = scope if scope is not None else Scope.unrestricted()
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(Grant(capability=Capability(value=one), scope=where) for one in capabilities),
        not_after=not_after,
    )


#: The principal the actions run as, and the agent's ceiling. The suspension's `ent_hash` is
#: their intersection, which is what `resume` compares against.
ASKER_REACH = reach(ASKER, WRITE_STATUS, READ_STATUS)
CEILING = reach("agent_test", WRITE_STATUS, READ_STATUS)
APPROVER = reach("u_narrow", WRITE_STATUS, scope=in_department(MAINTENANCE))


def an_action(department: str = MAINTENANCE, tool: ToolDefinition = STATUS_TOOL) -> Action:
    return Action(
        agent_id="agent_test",
        tool=tool,
        target="ticket.update_status" if tool is STATUS_TOOL else "invoice",
        touched_fields=("status",) if tool is STATUS_TOOL else (),
        row={"department": department},
        args={"status": "closed"} if tool is STATUS_TOOL else {},
    )


def raised(
    ident: str,
    *,
    department: str = MAINTENANCE,
    tool: ToolDefinition = STATUS_TOOL,
    principal_id: str = ASKER,
) -> SuspendedAction:
    """One suspension, built the way `suspend` builds one, at the asker's run reach."""
    action = an_action(department, tool)
    return SuspendedAction(
        id=ident,
        trace_id="trace_test",
        action=action,
        principal_id=principal_id,
        ent_hash=ASKER_REACH.intersect(CEILING, NOW).ent_hash(),
        artefact=render_artefact(action),
        action_digest=action.digest(),
        raised_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(hours=3),
    )


def as_row(suspension: SuspendedAction, **overrides: Any) -> dict[str, Any]:
    return row_values(suspension) | {"decided_by": None, "decided_at": None} | overrides


def recorder_for(ledger: AuditChain, who: EntitlementSet) -> AuditRecorder:
    return AuditRecorder(
        ledger,
        actor_id=who.principal_id,
        ent_hash=who.ent_hash(),
        trace_id="trace_test",
        clock=lambda: NOW,
    )


APPROVE = DecisionAsked(verdict=DecidableVerdict.APPROVED)


# ------------------------------------------------------------------------ the row


def test_a_stored_suspension_reads_back_as_the_suspension_that_was_raised() -> None:
    """Delete this and a row can lose a field on the way in and every refusal below still pass."""
    one = raised("m_1")

    assert stored_from(as_row(one)) == one


def test_a_row_whose_action_was_edited_after_it_was_raised_is_refused_on_read() -> None:
    """An argument changed, and a capability column that no longer names the action's, are
    both refused; the unedited row beside them is read.

    Delete this and an approver can approve an action other than the one the artefact shows."""
    one = raised("m_1")
    edited = as_row(one)
    edited["action"] = dict(edited["action"], args={"status": "deleted"})
    refiled = as_row(one, required_capability="write:ticket.priority")

    with pytest.raises(SuspensionStoreError, match="no longer matches its digest"):
        stored_from(edited)
    with pytest.raises(SuspensionStoreError, match="does not require"):
        stored_from(refiled)
    with pytest.raises(SuspensionStoreError, match="does not construct"):
        stored_from(as_row(one, action={"agent_id": "agent_test"}))
    assert stored_from(as_row(one)).id == "m_1"


def test_a_suspension_stored_already_decided_is_refused_and_a_pending_one_is_not() -> None:
    """Delete this and a decision can be stored with no ledger entry behind it."""
    one = raised("m_1")

    with pytest.raises(SuspensionStoreError, match="decided before it was stored"):
        row_values(one.approved_by("u_narrow", NOW))
    assert row_values(one)["state"] == "pending"
    assert row_values(one)["required_capability"] == WRITE_STATUS


def test_what_a_reach_may_approve_is_asked_of_the_reach_wildcards_and_expiry_included() -> None:
    """Exact and wildcard grants are held, an unheld capability and a name that is no capability
    are dropped, an expired reach holds nothing, and the answer is sorted.

    Delete this and the setting the policy reads can admit what the reach does not hold, or
    hide what it does."""
    pending = [
        "write:ticket.status",
        "write:invoice.amount",
        "not a capability",
        "write:ticket.priority",
    ]
    wildcard = reach("u_w", "write:ticket.*")

    assert approvable(pending, APPROVER, NOW) == ("write:ticket.status",)
    assert approvable(pending, wildcard, NOW) == ("write:ticket.priority", "write:ticket.status")
    assert approvable(pending, reach("u_x", "write:ticket.*", not_after=NOW), NOW) == ()
    assert approvable(pending, reach("u_none"), NOW) == ()


def test_recording_a_decision_nobody_took_is_refused_before_anything_is_written() -> None:
    """Delete this and a pending suspension can be recorded, which writes a decision with no
    decider."""
    nothing = cast(AsyncSession, None)

    with pytest.raises(SuspensionStoreError, match="has not been decided"):
        run(lambda: HeldRows(nothing).record(raised("m_1")))


# ------------------------------------------------------------------ against the database


def predecessor() -> str:
    """The revision `0042` names as the one before it, read off the migration."""
    spec = importlib.util.spec_from_file_location("migration_0042_predecessor", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.down_revision)


@contextmanager
def suspensions(database: str) -> Iterator[str]:
    """A fresh database holding `gate.suspension`, built by `0042` itself."""
    scratch = fresh(database)
    try:
        migrate(database, "stamp", predecessor())
        migrate(database, "upgrade", "0042")
        yield scratch
    finally:
        drop(database)


def app_engine(url: str) -> AsyncEngine:
    """An engine whose every connection is the application role, so the policies apply."""
    return create_async_engine(
        normalise_database_url(url),
        poolclass=NullPool,
        connect_args={"options": "-c role=brain_app"},
    )


def with_store[T](url: str, work: Callable[[StoredSuspensions, AuditChain], Awaitable[T]]) -> T:
    """One store over the application role and an in-memory ledger, for one test's coroutine."""

    async def go() -> T:
        engine = app_engine(url)
        ledger = AuditChain()
        try:
            return await work(StoredSuspensions(make_session_factory(engine), ledger), ledger)
        finally:
            await engine.dispose()

    return run(go)


async def put(store: StoredSuspensions, *held: SuspendedAction) -> None:
    for one in held:
        async with store.holding(reach(one.principal_id), NOW) as rows:
            await put_suspension(rows.session, one)


def test_the_store_connects_as_the_application_role() -> None:
    """Delete this and every policy test below can pass on a superuser connection that bypasses
    row-level security entirely."""
    with suspensions("brain_ap_role") as url:

        async def work(store: StoredSuspensions, _: AuditChain) -> tuple[Any, ...]:
            async with store.sessions() as session:
                return tuple((await session.execute(text("SELECT current_user"))).one())

        assert with_store(url, work) == ("brain_app",)


def test_an_approver_is_handed_only_what_their_reach_holds_and_card_decides_the_rest() -> None:
    """The approver holding the ticket capability in maintenance is handed both ticket
    suspensions and not the invoice one; `queue` then shows the maintenance card alone. A reader
    holding nothing is handed nothing, and a connection with no settings reads no row at all.

    Delete this and the read policy can be `USING (true)` with every queue still looking right."""
    held = (
        raised("m_1"),
        raised("f_1", department=FINANCE),
        raised("inv_1", tool=INVOICE_TOOL),
    )
    with suspensions("brain_ap_reads") as url:

        async def work(store: StoredSuspensions, _: AuditChain) -> tuple[Any, ...]:
            await put(store, *held)
            handed = await store.reading_as(APPROVER, NOW).open_suspensions()
            nobody = await store.reading_as(reach("u_none"), NOW).open_suspensions()
            one = await store.reading_as(APPROVER, NOW).suspension("inv_1")
            async with store.sessions() as session:
                bare = (
                    await session.execute(text("SELECT count(*) FROM gate.suspension"))
                ).scalar()
            return handed, nobody, one, bare

        handed, nobody, one, bare = with_store(url, work)

    assert sorted(s.id for s in handed) == ["f_1", "m_1"]
    assert [c.suspension_id for c in queue(handed, APPROVER, NOW).items] == ["m_1"]
    assert list(nobody) == []
    assert one is None
    assert bare == 0


def test_a_wildcard_grant_is_answered_by_the_reach_and_an_expired_reach_is_handed_nothing() -> None:
    """Delete this and the setting can be computed by string equality, which hides every approval
    from an approver who holds the capability through a wildcard."""
    with suspensions("brain_ap_wildcard") as url:

        async def work(store: StoredSuspensions, _: AuditChain) -> tuple[list[str], list[str]]:
            await put(store, raised("m_1"))
            live = await store.reading_as(reach("u_w", "write:ticket.*"), NOW).open_suspensions()
            lapsed = await store.reading_as(
                reach("u_w", "write:ticket.*", not_after=NOW), NOW
            ).open_suspensions()
            return [s.id for s in live], [s.id for s in lapsed]

        assert with_store(url, work) == (["m_1"], [])


def test_a_suspension_is_raised_only_in_the_name_of_the_principal_it_runs_as() -> None:
    """Delete this and a request can put another person's reach on a card they never raised."""
    with suspensions("brain_ap_raise") as url:

        async def mallory(store: StoredSuspensions, _: AuditChain) -> None:
            async with store.holding(reach("mallory"), NOW) as rows:
                await put_suspension(rows.session, raised("m_1"))

        with pytest.raises(DBAPIError, match="row-level security"):
            with_store(url, mallory)

        async def asker(store: StoredSuspensions, _: AuditChain) -> None:
            await put(store, raised("m_1"))

        with_store(url, asker)
        assert sql(url, "SELECT id, principal_id FROM gate.suspension") == [("m_1", ASKER)]


def test_a_suspension_is_written_once() -> None:
    """Delete this and `put_suspension` can become an upsert, rewriting an action after its card
    was shown."""
    with suspensions("brain_ap_once") as url:

        async def twice(store: StoredSuspensions, _: AuditChain) -> None:
            await put(store, raised("m_1"))
            await put(store, raised("m_1"))

        with pytest.raises(IntegrityError):
            with_store(url, twice)


def test_a_decision_is_written_once_under_the_deciders_name_with_one_ledger_entry() -> None:
    """Decided through `decide_once` on a held row: approved under the approver's name, the
    ledger holds one entry, and a second decision finds nothing to decide.

    Delete this and the store's lock and guarded write can both be missing with the in-memory
    route tests still green."""
    with suspensions("brain_ap_decide") as url:

        async def work(store: StoredSuspensions, ledger: AuditChain) -> tuple[Any, ...]:
            await put(store, raised("m_1"))
            recorder = recorder_for(ledger, APPROVER)
            async with store.holding(APPROVER, NOW) as rows:
                first = await decide_once(rows, "m_1", APPROVER, recorder, asked=APPROVE, now=NOW)
            async with store.holding(APPROVER, NOW) as rows:
                second = await decide_once(rows, "m_1", APPROVER, recorder, asked=APPROVE, now=NOW)
            return first, second, len(ledger)

        first, second, entries = with_store(url, work)
        stored = sql(url, "SELECT state, decided_by FROM gate.suspension WHERE id = 'm_1'")

    assert first is not None and first.suspension.state is ApprovalState.APPROVED
    assert second is None
    assert entries == 1
    assert stored == [("approved", "u_narrow")]


def test_two_approvers_deciding_one_suspension_at_once_write_one_decision() -> None:
    """Two transactions decide the same suspension concurrently. One waits on the row lock, then
    finds it decided and gets nothing, and the ledger holds one entry.

    Delete this and `FOR UPDATE` can be dropped from the lock, after which both find it pending
    and both write an entry."""
    other = reach("u_other", WRITE_STATUS, scope=in_department(MAINTENANCE))
    rejected = DecisionAsked(
        verdict=DecidableVerdict.REJECTED, reason_code=RejectionReason.WRONG_TARGET
    )
    with suspensions("brain_ap_race") as url:

        async def work(store: StoredSuspensions, ledger: AuditChain) -> tuple[Any, ...]:
            await put(store, raised("m_1"))
            first_has_it = asyncio.Event()

            async def one(who: EntitlementSet, asked: DecisionAsked, lead: bool) -> Any:
                async with store.holding(who, NOW) as rows:
                    if not lead:
                        await first_has_it.wait()
                    decided = await decide_once(
                        rows, "m_1", who, recorder_for(ledger, who), asked=asked, now=NOW
                    )
                    if lead:
                        first_has_it.set()
                        # Hold the transaction open so the other blocks on the lock, not on nothing.
                        await asyncio.sleep(0.5)
                    return decided

            first, second = await asyncio.gather(
                one(APPROVER, APPROVE, True), one(other, rejected, False)
            )
            return first, second, len(ledger)

        first, second, entries = with_store(url, work)
        stored = sql(url, "SELECT state, decided_by FROM gate.suspension")

    assert first is not None and second is None
    assert stored == [("approved", "u_narrow")]
    assert entries == 1


def test_a_decided_row_is_not_decided_again_and_a_decision_names_only_the_session() -> None:
    """A decision written under somebody else's name is refused by the policy; written by the
    decider it lands; written again the row is no longer pending and nothing changes.

    Delete this and one connection can write another person's approval, or overwrite one."""
    with suspensions("brain_ap_decider") as url:

        async def work(store: StoredSuspensions, _: AuditChain) -> tuple[bool, bool]:
            await put(store, raised("m_1"))
            async with store.holding(APPROVER, NOW) as rows:
                landed = await rows.record(raised("m_1").approved_by("u_narrow", NOW))
            async with store.holding(APPROVER, NOW) as rows:
                again = await rows.record(raised("m_1").rejected_by("u_narrow", NOW))
            return landed, again

        async def impostor(store: StoredSuspensions, _: AuditChain) -> None:
            await put(store, raised("m_2"))
            async with store.holding(APPROVER, NOW) as rows:
                await rows.record(raised("m_2").approved_by("u_somebody_else", NOW))

        async def raiser_naming_another(store: StoredSuspensions, _: AuditChain) -> None:
            # The raiser holds the capability and reads their own row whatever its state, so
            # only the update policy's own check stops them writing somebody else's name on it.
            # Found by mutation: without this case that check could be removed unnoticed.
            await put(store, raised("m_4"))
            async with store.holding(ASKER_REACH, NOW) as rows:
                await rows.record(raised("m_4").approved_by("u_somebody_else", NOW))

        with pytest.raises(DBAPIError, match="row-level security"):
            with_store(url, impostor)
        with pytest.raises(DBAPIError, match="row-level security"):
            with_store(url, raiser_naming_another)
        assert with_store(url, work) == (True, False)
        with_store(url, lambda store, _: put(store, raised("m_3")))

        # The policy on its own, without the store's `state = 'pending'` clause: the same
        # statement changes the pending row and leaves the decided one alone.
        def overwrite(ident: str) -> int:
            with psycopg.connect(url) as conn:
                conn.execute("SET ROLE brain_app")
                conn.execute("SELECT set_config('app.principal_id', 'u_narrow', false)")
                conn.execute("SELECT set_config('app.approvable', %s, false)", (WRITE_STATUS,))
                changed = conn.execute(
                    "UPDATE gate.suspension SET state = 'rejected', decided_by = 'u_narrow', "
                    "decided_at = %s WHERE id = %s",
                    (NOW, ident),
                ).rowcount
                conn.commit()
                return changed

        assert overwrite("m_1") == 0
        assert overwrite("m_3") == 1
        assert sql(
            url, "SELECT id, state FROM gate.suspension WHERE id IN ('m_1', 'm_3') ORDER BY id"
        ) == [
            ("m_1", "approved"),
            ("m_3", "rejected"),
        ]


def test_the_app_role_cannot_edit_the_action_and_a_row_edited_anyway_is_absent() -> None:
    """The column grant stops the application role; a superuser's edit is caught by the digest,
    and the edited row is absent from the queue and the single read while its neighbour is not.

    Delete this and `0042` can grant UPDATE on the whole row with every other test still green."""
    with suspensions("brain_ap_sealed") as url:
        with_store(url, lambda store, _: put(store, raised("m_1"), raised("m_2")))
        with psycopg.connect(url) as conn:
            conn.execute("SET ROLE brain_app")
            with pytest.raises(psycopg.errors.InsufficientPrivilege, match="permission denied"):
                conn.execute("UPDATE gate.suspension SET action = '{}'::jsonb")
            conn.rollback()
        sql(
            url,
            "UPDATE gate.suspension SET action = jsonb_set(action, '{args,status}', %s::jsonb) "
            "WHERE id = 'm_1'",
            '"deleted"',
        )

        async def work(store: StoredSuspensions, _: AuditChain) -> tuple[Any, ...]:
            source = store.reading_as(APPROVER, NOW)
            return [s.id for s in await source.open_suspensions()], await source.suspension("m_1")

        assert with_store(url, work) == (["m_2"], None)


def test_the_raiser_reads_their_approved_suspension_and_resumes_at_the_reach_now() -> None:
    """Approved by an approver, the suspension is read back by the principal it runs as and resumed
    through `leash.resume` at the reach `reach_now` returns: the reach it was raised at resumes,
    a reach that has changed since is refused, and somebody else's id is nothing.

    Delete this and a resume can use the reach remembered at approval, which is the Monday grant
    running on Friday."""
    leash = Leash(
        entries=(
            LeashEntry(
                agent_id="agent_test",
                target="ticket.update_status",
                scope=Scope.unrestricted(),
                rung=AutonomyTier.ASSISTED,
            ),
        )
    )
    # Narrowed to maintenance since the approval: the row is still in scope, so only the reach
    # having moved can refuse it, and the intersection with the ceiling carries the change.
    changed = reach(ASKER, WRITE_STATUS, READ_STATUS, scope=in_department(MAINTENANCE))

    def executed(_: Action) -> TypedResult[Ticket]:
        return TypedResult[Ticket](records=(Ticket(entity="ticket", id="t_9", status="closed"),))

    with suspensions("brain_ap_resume") as url:

        async def work(store: StoredSuspensions, ledger: AuditChain) -> tuple[Any, ...]:
            await put(store, raised("m_1"))
            async with store.holding(APPROVER, NOW) as rows:
                await decide_once(
                    rows, "m_1", APPROVER, recorder_for(ledger, APPROVER), asked=APPROVE, now=NOW
                )
            asked: list[str] = []

            async def attempt(now_reach: EntitlementSet, ident: str, principal: str) -> Any:
                def reach_now(pid: str) -> EntitlementSet:
                    asked.append(pid)
                    return now_reach

                return await resume_stored(
                    store,
                    ident,
                    principal,
                    reach_now=reach_now,
                    agent_ceiling=CEILING,
                    policy=POLICY,
                    leash=leash,
                    assessment=CLEAN,
                    trace_id="trace_resume",
                    now=NOW,
                    execute=executed,
                    ledger=MemoryLedger(),
                )

            same = await attempt(ASKER_REACH, "m_1", ASKER)
            moved = await attempt(changed, "m_1", ASKER)
            decider = await attempt(reach("u_narrow", WRITE_STATUS, READ_STATUS), "m_1", "u_narrow")
            stranger = await attempt(
                reach("u_stranger", WRITE_STATUS, READ_STATUS), "m_1", "u_stranger"
            )
            return same, moved, decider, stranger, asked

        same, moved, decider, stranger, asked = with_store(url, work)

    assert same is not None and same.resumed
    assert moved is not None and moved.refusal is ResumeRefusal.ENTITLEMENT_CHANGED
    # The decider reads the row they decided, and `resume` refuses to run it as them.
    assert decider is not None and decider.refusal is ResumeRefusal.PRINCIPAL_CHANGED
    assert stranger is None
    assert asked == [ASKER, ASKER, "u_narrow", "u_stranger"]


def test_the_table_refuses_a_decision_with_nobody_on_it_or_a_window_past_the_leashs_bound() -> None:
    """Approved with no decider, pending with one, and a window a minute past twenty-four hours
    are refused; an approved row with a decider and a time is accepted.

    Delete this and a row can say approved without saying by whom, or stand for a week."""
    one = raised("m_1")
    insert = (
        "INSERT INTO gate.suspension (id, trace_id, principal_id, agent_id, required_capability, "
        "action, ent_hash, artefact, action_digest, raised_at, expires_at, state, decided_by, "
        "decided_at) VALUES (%s, 'trace_test', 'u_asker', 'agent_test', 'write:ticket.status', "
        "'{}'::jsonb, %s, 'shown', %s, %s, %s, %s, %s, %s)"
    )
    ends = NOW + timedelta(hours=4)
    with suspensions("brain_ap_constraints") as url:
        for ident, state, ending, by, at in (
            ("a", "approved", ends, None, None),
            ("b", "pending", ends, "u_narrow", NOW),
            ("c", "pending", NOW + timedelta(hours=24, minutes=1), None, None),
        ):
            with pytest.raises(psycopg.errors.CheckViolation):
                sql(url, insert, ident, one.ent_hash, one.action_digest, NOW, ending, state, by, at)
        sql(
            url,
            insert,
            "d",
            one.ent_hash,
            one.action_digest,
            NOW,
            ends,
            "approved",
            "u_narrow",
            NOW,
        )
        stored = sql(url, "SELECT id FROM gate.suspension")

    assert stored == [("d",)]


def test_the_migration_builds_exactly_what_the_model_declares() -> None:
    """Every constraint, index and column, compared between `0042` and the model, with row-level
    security on.

    Delete this and the migration and the model can disagree about a constraint or the index."""
    with (
        suspensions("brain_ap_shape") as url,
        modelled("brain_ap_shape_modelled", TABLES) as from_models,
    ):
        assert shape(url, TABLES) == shape(from_models, TABLES)
        assert secured(url, TABLES) == dict.fromkeys(TABLES, True)


def test_the_migration_comes_down_and_goes_back_up() -> None:
    """Delete this and a downgrade that leaves the table or the view behind is found at the next
    upgrade."""
    with suspensions("brain_ap_round_trip") as url:
        migrate("brain_ap_round_trip", "downgrade", predecessor())
        gone = present(url, TABLES)
        view_gone = sql(url, "SELECT to_regclass('gate.suspension_capability')")
        migrate("brain_ap_round_trip", "upgrade", "0042")
        back = present(url, TABLES)

    assert gone == set()
    assert view_gone == [(None,)]
    assert back == set(TABLES)
