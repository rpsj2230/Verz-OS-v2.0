"""A suspended action is kept once, read back against its own digest, read by an approver only
through what their reach holds, decided once under a lock with one ledger entry the database keeps,
and resumed at the reach as it is now.

The first half is decisions over a row's values and runs anywhere. The second builds
`gate.suspension` through the migrations that ship it and drives it as the application role,
through `brain.gate.suspension_store.StoredSuspensions` itself and through the application's own
lifespan and routes; it skips when there is no server, as every file using
`tests.fixtures.scratch_postgres` does. A test near the top of that half proves the store's
connection really is the application role, because a store connected as the superuser passes every
row-level security test here by bypassing the policies.

**Two chains, and each runs only what it needs.** `0042` alone for the table's own constraints and
round trip. For a decision, `0002` and `0003` for the ledger and its hash, `0023` for the `approval`
action, `0042` for the table and `0083` for the verdict, the reason and the trigger, each run for
real after a stamp of the revision before it, because `0001` needs pgvector and nothing between
these builds anything a decision touches.

The store's clock is 2999, for the reason CLAUDE.md records about fixtures that go off. The tests
that drive the routes use the wall clock, for the reason `tests/unit/test_approval_routes.py` gives.

Task ids: M35.3.1.1, M33.6.1.3, M27.9.3
"""

from __future__ import annotations

import asyncio
import importlib.util
import re
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.approval_routes import (
    DecidableVerdict,
    DecisionAsked,
    RejectionReason,
    decide_once,
    queue,
)
from brain.audit.ledger import AuditChain, AuditEntry
from brain.audit.record import REASON_CODE, ApprovalVerdict, AuditRecorder
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.errors import Absent
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
    recorded_differently,
    resume_stored,
    row_values,
    stored_from,
)
from brain.session import make_session_factory
from brain.tables import suspension as table_module
from brain.tables.identity import one_of
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
from tests.unit.test_approval_decisions import (
    Store,
    _wiring,
    a_suspension,
    headers,
)

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
TABLES: tuple[str, ...] = ("gate.suspension",)
VERSIONS = ROOT / "migrations" / "versions"
MIGRATION = VERSIONS / "0042_suspension.py"
DECISION_MIGRATION = VERSIONS / "0083_suspension_decision.py"
LEDGER_MIGRATION = VERSIONS / "0003_resolver_and_tables.py"
APPROVAL_ACTION_MIGRATION = VERSIONS / "0023_approval_action.py"

APPROVALS = f"{API_PREFIX}/approvals"

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


def drafting_for(who: EntitlementSet) -> AuditRecorder:
    """A recorder over a chain nobody keeps, as `brain.approval_routes.decide_approval` builds."""
    return AuditRecorder(
        AuditChain(),
        actor_id=who.principal_id,
        ent_hash=who.ent_hash(),
        trace_id="trace_test",
        clock=lambda: NOW,
    )


def drafted(
    suspension: SuspendedAction,
    by: EntitlementSet,
    verdict: ApprovalVerdict = ApprovalVerdict.APPROVED,
    reason_code: str = "",
) -> tuple[SuspendedAction, AuditEntry]:
    """A suspension decided by `by` and the entry its recorder drafts, without asking `card`."""
    entry = drafting_for(by).approval(
        suspension_id=suspension.id,
        verdict=verdict,
        digest=suspension.action_digest,
        reason_code=reason_code,
    )
    moved = (
        suspension.approved_by(by.principal_id, NOW)
        if verdict is ApprovalVerdict.APPROVED
        else suspension.rejected_by(by.principal_id, NOW)
    )
    return moved, entry


APPROVE = DecisionAsked(verdict=DecidableVerdict.APPROVED)
REJECT = DecisionAsked(verdict=DecidableVerdict.REJECTED, reason_code=RejectionReason.WRONG_TARGET)


def migration_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}_suspension", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    _, entry = drafted(raised("m_1"), APPROVER)

    with pytest.raises(SuspensionStoreError, match="has not been decided"):
        run(lambda: HeldRows(nothing).record(raised("m_1"), entry))


def test_a_kept_entry_is_the_draft_in_everything_but_what_the_ledger_assigns() -> None:
    """The same entry at another sequence, instant and parent is not different; another actor,
    subject, reach, trace or detail is.

    Delete this and the store's comparison can ignore the one field a drifted trigger gets wrong,
    and a decision is kept under an entry that says something the recorder never drafted."""
    _, draft = drafted(raised("m_1"), APPROVER)
    placed = draft.model_copy(
        update={"seq": 41, "at": NOW + timedelta(seconds=3), "prev_hash": "a" * 64}
    )

    assert not recorded_differently(placed, draft)
    for changed in (
        {"actor_id": "u_somebody_else"},
        {"subject": "leash:m_2"},
        {"ent_hash": "0" * 32},
        {"trace_id": "tx.1"},
        {"details": {**draft.details, "reason_code": "wrong_target"}},
    ):
        assert recorded_differently(draft.model_copy(update=changed), draft), changed


def test_the_decision_migration_holds_the_grammars_and_widths_it_copied() -> None:
    """`0083` copies the reason code's grammar and the verdicts the row can keep, for the reason
    `0009` gives. Delete this and one side changes alone: a reason code the recorder writes and the
    table refuses, which fails every rejection on a running install, or a verdict the table admits
    and the trigger would record against the wrong digest."""
    migration = migration_module(DECISION_MIGRATION)

    assert migration.REASON_CODE_PATTERN == REASON_CODE
    assert one_of("verdict", table_module.RECORDED_VERDICTS) == migration.VERDICT_IN
    assert migration.VERDICT_CHARS == table_module.VERDICT_CHARS
    assert migration.REASON_CODE_CHARS == table_module.REASON_CODE_CHARS
    assert max(len(one.value) for one in ApprovalVerdict) <= migration.VERDICT_CHARS
    # The longest code the grammar admits fits the column: one letter and sixty more.
    longest = re.sub(r"\D", " ", REASON_CODE).split()
    assert 1 + int(longest[-1]) <= migration.REASON_CODE_CHARS
    assert ApprovalVerdict.AMENDED not in table_module.RECORDED_VERDICTS
    assert {one.value for one in DecidableVerdict} <= set(table_module.RECORDED_VERDICTS)
    assert migration.down_revision == "0082"


# ------------------------------------------------------------------ against the database


def predecessor(path: Path) -> str:
    """The revision a migration names as the one before it, read off the migration."""
    return str(migration_module(path).down_revision)


def revision(path: Path) -> str:
    return str(migration_module(path).revision)


def upgraded(database: str, *paths: Path) -> None:
    """Each migration run for real, after a stamp of the revision before it."""
    for path in paths:
        migrate(database, "stamp", predecessor(path))
        migrate(database, "upgrade", revision(path))


@contextmanager
def the_table_alone(database: str) -> Iterator[str]:
    """A fresh database holding `gate.suspension` as `0042` built it, and nothing else."""
    scratch = fresh(database)
    try:
        upgraded(database, MIGRATION)
        yield scratch
    finally:
        drop(database)


@contextmanager
def suspensions(database: str) -> Iterator[str]:
    """A fresh database holding the ledger and `gate.suspension` with `0083`'s decision on it."""
    scratch = fresh(database)
    try:
        migrate(database, "stamp", "0001")
        migrate(database, "upgrade", revision(LEDGER_MIGRATION))
        upgraded(database, APPROVAL_ACTION_MIGRATION, MIGRATION, DECISION_MIGRATION)
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


def with_store[T](url: str, work: Callable[[StoredSuspensions], Awaitable[T]]) -> T:
    """One store over the application role, for one test's coroutine, on an engine of its own."""

    async def go() -> T:
        engine = app_engine(url)
        try:
            return await work(StoredSuspensions(make_session_factory(engine)))
        finally:
            await engine.dispose()

    return run(go)


async def put(store: StoredSuspensions, *held: SuspendedAction) -> None:
    for one in held:
        async with store.holding(reach(one.principal_id), NOW) as rows:
            await put_suspension(rows.session, one)


def entries(url: str) -> list[AuditEntry]:
    """Every ledger entry, in order, read as the superuser and loaded through `AuditEntry`."""
    names = (
        "seq",
        "at",
        "actor_id",
        "action",
        "subject",
        "ent_hash",
        "trace_id",
        "details",
        "prev_hash",
        "entry_hash",
    )
    rows = sql(
        url,
        "SELECT seq, at, actor_id, action, subject, ent_hash, trace_id, details, prev_hash,"
        " entry_hash FROM obs.audit_entry ORDER BY seq",
    )
    return [AuditEntry(**dict(zip(names, row, strict=True))) for row in rows]


def through_the_application[T](url: str, calls: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    """One application process over this database: its own lifespan, its own store, its routes.

    The gate is the token machinery `tests/unit/test_approval_decisions.py` borrows, attached after
    the lifespan has run, and nothing else is: `app.state.suspensions` is what the lifespan built.
    """
    app: FastAPI = create_app(
        Settings(env="development", database_url=url, run_migrations=False, valkey_url="")
    )

    async def go() -> T:
        async with app.router.lifespan_context(app):
            assert isinstance(app.state.suspensions, StoredSuspensions)
            app.state.gate = _wiring()
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await calls(client)

    return run(go)


def bare(response: httpx.Response) -> dict[str, object]:
    """A response's body without the per-request reference, so two refusals can be compared."""
    return {key: value for key, value in response.json().items() if key != "trace_id"}


async def deciding(client: httpx.AsyncClient, pid: str, ident: str, body: object) -> httpx.Response:
    return await client.post(f"{APPROVALS}/{ident}/decision", json=body, headers=headers(pid))


def put_now(url: str, *held: SuspendedAction) -> None:
    """Suspensions raised relative to the wall clock, stored as their principal."""

    async def work(store: StoredSuspensions) -> None:
        for one in held:
            async with store.holding(reach(one.principal_id), datetime.now(UTC)) as rows:
                await put_suspension(rows.session, one)

    with_store(url, work)


def test_the_store_connects_as_the_application_role() -> None:
    """Delete this and every policy test below can pass on a superuser connection that bypasses
    row-level security entirely."""
    with suspensions("brain_ap_role") as url:

        async def work(store: StoredSuspensions) -> tuple[Any, ...]:
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

        async def work(store: StoredSuspensions) -> tuple[Any, ...]:
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

        async def work(store: StoredSuspensions) -> tuple[list[str], list[str]]:
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

        async def mallory(store: StoredSuspensions) -> None:
            async with store.holding(reach("mallory"), NOW) as rows:
                await put_suspension(rows.session, raised("m_1"))

        with pytest.raises(DBAPIError, match="row-level security"):
            with_store(url, mallory)

        async def asker(store: StoredSuspensions) -> None:
            await put(store, raised("m_1"))

        with_store(url, asker)
        assert sql(url, "SELECT id, principal_id FROM gate.suspension") == [("m_1", ASKER)]


def test_a_suspension_is_written_once() -> None:
    """Delete this and `put_suspension` can become an upsert, rewriting an action after its card
    was shown."""
    with suspensions("brain_ap_once") as url:

        async def twice(store: StoredSuspensions) -> None:
            await put(store, raised("m_1"))
            await put(store, raised("m_1"))

        with pytest.raises(IntegrityError):
            with_store(url, twice)


def test_a_decided_approval_leaves_one_ledger_entry_that_survives_a_restart() -> None:
    """M27.9.3's proof. One application process approves one suspension and rejects another
    through its routes, and stops. A second process started over the same database finds the two
    decisions and exactly two `approval` entries: each naming its suspension, the approver, the
    verdict, the action's digest, the reason on the rejection alone, the approver's reach digest
    and the trace its response carried, in a chain that verifies. The rows carry the verdicts the
    entries record, and neither approval is offered again.

    Delete this and the deployed process can go back to reading approvals and refusing every
    decision, or keep a decision in a ledger that a restart empties, with every in-process route
    test green."""
    approved, rejected = a_suspension("m_1"), a_suspension("r_1")
    with suspensions("brain_ap_restart") as url:
        put_now(url, approved, rejected)

        async def first(client: httpx.AsyncClient) -> tuple[httpx.Response, httpx.Response]:
            yes = await deciding(client, "u_narrow", "m_1", {"verdict": "approved"})
            no = await deciding(
                client, "u_narrow", "r_1", {"verdict": "rejected", "reason_code": "wrong_target"}
            )
            return yes, no

        yes, no = through_the_application(url, first)

        async def second(client: httpx.AsyncClient) -> tuple[Any, ...]:
            offered = await client.get(APPROVALS, headers=headers("u_narrow"))
            card = await client.get(f"{APPROVALS}/m_1", headers=headers("u_narrow"))
            return offered.json()["items"], card.status_code

        offered, card_status = through_the_application(url, second)
        kept = entries(url)
        rows = sql(
            url,
            "SELECT id, state, decided_by, verdict, reason_code FROM gate.suspension ORDER BY id",
        )

    assert (yes.status_code, no.status_code) == (200, 200), (yes.text, no.text)
    assert [(one.subject, one.actor_id) for one in kept] == [
        ("leash:m_1", "u_narrow"),
        ("leash:r_1", "u_narrow"),
    ]
    assert [one.action.value for one in kept] == ["approval", "approval"]
    assert kept[0].details == {"verdict": "approved", "action_digest": approved.action_digest}
    assert kept[1].details == {
        "verdict": "rejected",
        "action_digest": rejected.action_digest,
        "reason_code": "wrong_target",
    }
    assert {one.ent_hash for one in kept} == {_approver_hash()}
    assert [one.trace_id for one in kept] == [yes.headers["x-trace-id"], no.headers["x-trace-id"]]
    assert AuditChain(kept).verify() is None
    assert rows == [
        ("m_1", "approved", "u_narrow", "approved", None),
        ("r_1", "rejected", "u_narrow", "rejected", "wrong_target"),
    ]
    assert (offered, card_status) == ([], 404)


def _approver_hash() -> str:
    """`u_narrow`'s reach digest as the routes' entitlement store answers it."""
    return run(lambda: Store().load("u_narrow", datetime.now(UTC))).ent_hash()


def test_a_second_decision_is_refused_in_words_and_leaves_no_second_entry() -> None:
    """Approved once through the route, then approved again and rejected with a reason by the same
    approver, who can still see nothing else about it: both later answers are the 404 an invented id
    gets, with its sentence, the row still says approved, and the ledger holds one entry. An
    operator's statement that touches the decided row appends nothing either. Another approver
    arriving at the same instant is `test_two_approvers_deciding_one_suspension_at_once_write_one_
    decision`.

    Delete this and one card pressed twice on a slow phone is two approvals in the ledger, or a
    trigger that fires on every update of a decided row records decisions nobody took."""
    with suspensions("brain_ap_twice") as url:
        put_now(url, a_suspension("m_1"))

        async def calls(client: httpx.AsyncClient) -> list[httpx.Response]:
            return [
                await deciding(client, "u_narrow", "m_1", {"verdict": "approved"}),
                await deciding(client, "u_narrow", "m_1", {"verdict": "approved"}),
                await deciding(
                    client,
                    "u_narrow",
                    "m_1",
                    {"verdict": "rejected", "reason_code": "wrong_target"},
                ),
                await deciding(client, "u_narrow", "nothing_here", {"verdict": "approved"}),
            ]

        first, again, other, invented = through_the_application(url, calls)
        sql(url, "UPDATE gate.suspension SET updated_at = now() WHERE id = 'm_1'")
        kept = entries(url)
        row = sql(url, "SELECT state, decided_by, verdict FROM gate.suspension")

    assert first.status_code == 200, first.text
    assert invented.status_code == 404
    assert invented.json()["message"] == Absent.public_message
    for late in (again, other):
        assert late.status_code == 404
        assert bare(late) == bare(invented)
    assert [one.subject for one in kept] == ["leash:m_1"]
    assert row == [("approved", "u_narrow", "approved")]


def test_an_approver_outside_reach_is_answered_as_for_a_suspension_that_does_not_exist() -> None:
    """Holding the capability in finance, an approver asking for and deciding a maintenance
    suspension gets exactly the answers an invented id gets, and nothing is written; the approver
    in maintenance is then answered and decides it.

    Delete this and a caller trying ids against a real database learns which pending actions exist
    in departments they cannot see, whatever the in-process tests say."""
    with suspensions("brain_ap_elsewhere") as url:
        put_now(url, a_suspension("m_1"))

        async def calls(client: httpx.AsyncClient) -> list[httpx.Response]:
            return [
                await client.get(f"{APPROVALS}/m_1", headers=headers("u_wide")),
                await client.get(f"{APPROVALS}/nothing_here", headers=headers("u_wide")),
                await deciding(client, "u_wide", "m_1", {"verdict": "approved"}),
                await deciding(client, "u_wide", "nothing_here", {"verdict": "approved"}),
            ]

        read_out, read_invented, decided_out, decided_invented = through_the_application(url, calls)
        untouched = (sql(url, "SELECT state FROM gate.suspension"), entries(url))

        async def in_reach(client: httpx.AsyncClient) -> httpx.Response:
            return await deciding(client, "u_narrow", "m_1", {"verdict": "approved"})

        answered = through_the_application(url, in_reach)

    assert read_out.status_code == read_invented.status_code == 404
    assert bare(read_out) == bare(read_invented)
    assert decided_out.status_code == decided_invented.status_code == 404
    assert bare(decided_out) == bare(decided_invented)
    assert untouched == ([("pending",)], [])
    assert answered.status_code == 200, answered.text


def test_on_a_fresh_install_the_queue_is_empty_and_no_approvals_route_faults() -> None:
    """A process started over a database with no suspension in it holds the store, the queue answers
    200 with nothing in it, and the card and the decision answer the 404 and sentence an approval
    that does not exist gets. None of the three is a 500.

    Delete this and the Approvals screen on a new install can go back to "Something went wrong."
    for everybody, which is what a staging install showed, or to refusing every decision."""
    with suspensions("brain_ap_fresh") as url:

        async def calls(client: httpx.AsyncClient) -> list[httpx.Response]:
            return [
                await client.get(APPROVALS, headers=headers("u_narrow")),
                await client.get(f"{APPROVALS}/m_1", headers=headers("u_narrow")),
                await deciding(client, "u_narrow", "m_1", {"verdict": "approved"}),
            ]

        listed, card, decision = through_the_application(url, calls)

    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == []
    assert listed.json()["truncated"] is False
    for absent in (card, decision):
        assert absent.status_code == 404, absent.text
        assert absent.json()["message"] == Absent.public_message


def test_the_entry_a_decision_returns_is_the_one_the_ledger_kept_and_not_its_draft() -> None:
    """Two decisions through `decide_once` on the store: each returns the entry read back from
    `obs.audit_entry`, at the sequence the ledger gave it, and not the draft its recorder built on a
    chain of its own, which starts at nothing every time.

    Delete this and `decide_once` can hand back the draft, whose sequence, instant and digests are
    a link in no chain, and anything that anchors or cites it cites an entry that does not exist."""
    with suspensions("brain_ap_kept") as url:

        async def work(store: StoredSuspensions) -> list[Any]:
            await put(store, raised("m_1"), raised("r_1"))
            decided = []
            for ident, asked in (("m_1", APPROVE), ("r_1", REJECT)):
                async with store.holding(APPROVER, NOW) as rows:
                    decided.append(
                        await decide_once(
                            rows, ident, APPROVER, drafting_for(APPROVER), asked=asked, now=NOW
                        )
                    )
            return decided

        first, second = with_store(url, work)
        kept = entries(url)

    assert first is not None and second is not None
    assert [first.entry, second.entry] == kept
    assert [one.seq for one in kept] == [0, 1]
    assert second.suspension.state is ApprovalState.REJECTED


def test_a_kept_entry_that_differs_from_its_draft_stops_the_decision() -> None:
    """A decision handed a draft by somebody other than its decider, and one about another
    suspension, each raise inside the transaction, and the row stays pending with nothing in the
    ledger; the right draft is kept.

    Delete this and a trigger and a recorder that have drifted apart record a decision under an
    entry that says something else, or under no entry at all."""
    with suspensions("brain_ap_drift") as url:

        async def mismatched(store: StoredSuspensions) -> list[str]:
            await put(store, raised("m_1"), raised("m_2"))
            moved, _ = drafted(raised("m_1"), APPROVER)
            _, by_another = drafted(raised("m_1"), reach("u_other", WRITE_STATUS))
            _, about_another = drafted(raised("m_2"), APPROVER)
            refused: list[str] = []
            for entry in (by_another, about_another):
                try:
                    async with store.holding(APPROVER, NOW) as rows:
                        await rows.record(moved, entry)
                except SuspensionStoreError as exc:
                    refused.append(str(exc))
            return refused

        refused = with_store(url, mismatched)
        after_refusals = (
            sql(url, "SELECT id, state FROM gate.suspension ORDER BY id"),
            entries(url),
        )

        async def matched(store: StoredSuspensions) -> AuditEntry | None:
            moved, entry = drafted(raised("m_1"), APPROVER)
            async with store.holding(APPROVER, NOW) as rows:
                return await rows.record(moved, entry)

        kept = with_store(url, matched)
        ledger = entries(url)

    assert len(refused) == 2
    assert all("does not hold the entry its recorder drafted" in one for one in refused)
    assert after_refusals == ([("m_1", "pending"), ("m_2", "pending")], [])
    assert kept is not None and ledger == [kept]


def test_two_approvers_deciding_one_suspension_at_once_write_one_decision() -> None:
    """Two transactions decide the same suspension concurrently. One waits on the row lock, then
    finds it decided and gets nothing, and the ledger holds one entry.

    Delete this and `FOR UPDATE` can be dropped from the lock, after which both find it pending
    and both write an entry."""
    other = reach("u_other", WRITE_STATUS, scope=in_department(MAINTENANCE))
    with suspensions("brain_ap_race") as url:

        async def work(store: StoredSuspensions) -> tuple[Any, ...]:
            await put(store, raised("m_1"))
            first_has_it = asyncio.Event()

            async def one(who: EntitlementSet, asked: DecisionAsked, lead: bool) -> Any:
                async with store.holding(who, NOW) as rows:
                    if not lead:
                        await first_has_it.wait()
                    decided = await decide_once(
                        rows, "m_1", who, drafting_for(who), asked=asked, now=NOW
                    )
                    if lead:
                        first_has_it.set()
                        # Hold the transaction open so the other blocks on the lock, not on nothing.
                        await asyncio.sleep(0.5)
                    return decided

            return tuple(
                await asyncio.gather(one(APPROVER, APPROVE, True), one(other, REJECT, False))
            )

        first, second = with_store(url, work)
        stored = sql(url, "SELECT state, decided_by FROM gate.suspension")
        kept = entries(url)

    assert first is not None and second is None
    assert stored == [("approved", "u_narrow")]
    assert len(kept) == 1


def test_a_decided_row_is_not_decided_again_and_a_decision_names_only_the_session() -> None:
    """A decision written under somebody else's name is refused by the policy; written by the
    decider it lands; written again the row is no longer pending and nothing changes.

    Delete this and one connection can write another person's approval, or overwrite one."""
    with suspensions("brain_ap_decider") as url:

        async def work(store: StoredSuspensions) -> tuple[bool, bool]:
            await put(store, raised("m_1"))
            async with store.holding(APPROVER, NOW) as rows:
                landed = await rows.record(*drafted(raised("m_1"), APPROVER))
            async with store.holding(APPROVER, NOW) as rows:
                again = await rows.record(
                    *drafted(raised("m_1"), APPROVER, ApprovalVerdict.REJECTED, "wrong_target")
                )
            return landed is not None, again is None

        async def impostor(store: StoredSuspensions) -> None:
            await put(store, raised("m_2"))
            async with store.holding(APPROVER, NOW) as rows:
                await rows.record(*drafted(raised("m_2"), reach("u_somebody_else")))

        async def raiser_naming_another(store: StoredSuspensions) -> None:
            # The raiser holds the capability and reads their own row whatever its state, so
            # only the update policy's own check stops them writing somebody else's name on it.
            # Found by mutation: without this case that check could be removed unnoticed.
            await put(store, raised("m_4"))
            async with store.holding(ASKER_REACH, NOW) as rows:
                await rows.record(*drafted(raised("m_4"), reach("u_somebody_else")))

        with pytest.raises(DBAPIError, match="row-level security"):
            with_store(url, impostor)
        with pytest.raises(DBAPIError, match="row-level security"):
            with_store(url, raiser_naming_another)
        assert with_store(url, work) == (True, True)
        with_store(url, lambda store: put(store, raised("m_3")))

        # The policy on its own, without the store's `state = 'pending'` clause: the same
        # statement changes the pending row and leaves the decided one alone.
        def overwrite(ident: str) -> int:
            with psycopg.connect(url) as conn:
                conn.execute("SET ROLE brain_app")
                conn.execute("SELECT set_config('app.principal_id', 'u_narrow', false)")
                conn.execute("SELECT set_config('app.approvable', %s, false)", (WRITE_STATUS,))
                changed = conn.execute(
                    "UPDATE gate.suspension SET state = 'rejected', decided_by = 'u_narrow', "
                    "decided_at = %s, verdict = 'rejected', reason_code = 'wrong_target' "
                    "WHERE id = %s",
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


def test_the_table_refuses_a_decision_the_recorder_would_refuse() -> None:
    """Inserted already decided, as only an operator can: a rejection with no reason, an approval
    with one, a reason in prose, an amendment, a verdict the state contradicts and a pending row
    with a verdict are refused. An approval, a rejection with a code and a take-over with a code are
    kept, and each is recorded in the ledger as its decision.

    Delete this and the trigger can copy prose, or a reason on an approval, into a ledger
    `redact_details` never saw, or record an approval whose row `resume` reads as rejected."""
    one = raised("m_1")
    insert = (
        "INSERT INTO gate.suspension (id, trace_id, principal_id, agent_id, required_capability, "
        "action, ent_hash, artefact, action_digest, raised_at, expires_at, state, decided_by, "
        "decided_at, verdict, reason_code) VALUES (%s, 'trace_test', 'u_asker', 'agent_test', "
        "'write:ticket.status', '{}'::jsonb, %s, 'shown', %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    ends = NOW + timedelta(hours=4)

    def write(ident: str, state: str, verdict: str | None, reason: str | None) -> None:
        decider = None if state == "pending" else "u_narrow"
        at = None if state == "pending" else NOW
        sql(
            url,
            insert,
            ident,
            one.ent_hash,
            one.action_digest,
            NOW,
            ends,
            state,
            decider,
            at,
            verdict,
            reason,
        )

    with suspensions("brain_ap_checks") as url:
        for ident, state, verdict, reason in (
            ("a", "rejected", "rejected", None),
            ("b", "approved", "approved", "wrong_target"),
            ("c", "rejected", "rejected", "because I said so"),
            ("d", "rejected", "amended", "wrong_target"),
            ("e", "rejected", "approved", None),
            ("f", "approved", "rejected", "wrong_target"),
            ("g", "pending", "approved", None),
            ("h", "approved", None, None),
        ):
            with pytest.raises(psycopg.errors.CheckViolation):
                write(ident, state, verdict, reason)
        write("k1", "approved", "approved", None)
        write("k2", "rejected", "rejected", "wrong_target")
        write("k3", "rejected", "taken_over", "no_longer_needed")
        stored = sql(url, "SELECT id FROM gate.suspension ORDER BY id")
        kept = entries(url)

    assert stored == [("k1",), ("k2",), ("k3",)]
    assert [(entry.subject, entry.details.get("verdict")) for entry in kept] == [
        ("leash:k1", "approved"),
        ("leash:k2", "rejected"),
        ("leash:k3", "taken_over"),
    ]
    assert kept[2].details["reason_code"] == "no_longer_needed"


def test_the_app_role_cannot_edit_the_action_and_a_row_edited_anyway_is_absent() -> None:
    """The column grant stops the application role; a superuser's edit is caught by the digest,
    and the edited row is absent from the queue and the single read while its neighbour is not.

    Delete this and `0042` can grant UPDATE on the whole row with every other test still green."""
    with suspensions("brain_ap_sealed") as url:
        with_store(url, lambda store: put(store, raised("m_1"), raised("m_2")))
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

        async def work(store: StoredSuspensions) -> tuple[Any, ...]:
            source = store.reading_as(APPROVER, NOW)
            return [s.id for s in await source.open_suspensions()], await source.suspension("m_1")

        assert with_store(url, work) == (["m_2"], None)


def _resuming(
    store: StoredSuspensions, ident: str, now_reach: EntitlementSet, ran: list[str]
) -> Awaitable[Any]:
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

    def executed(action: Action) -> TypedResult[Ticket]:
        ran.append(ident)
        return TypedResult[Ticket](records=(Ticket(entity="ticket", id="t_9", status="closed"),))

    return resume_stored(
        store,
        ident,
        now_reach.principal_id,
        reach_now=lambda _: now_reach,
        agent_ceiling=CEILING,
        policy=POLICY,
        leash=leash,
        assessment=CLEAN,
        trace_id="trace_resume",
        now=NOW,
        execute=executed,
        ledger=MemoryLedger(),
    )


def test_an_approved_suspension_is_what_resume_reads_and_a_rejected_one_is_not_run() -> None:
    """Decided through `decide_once` on the store, one approved and one rejected, then read by a
    store on another connection, as a process started later reads it: `resume` runs the approved
    action once and refuses the rejected one as not approved without running it.

    Delete this and the decision can be kept somewhere `resume` does not read, in a verdict column
    the state never follows, so an approval is recorded and its action never runs."""
    with suspensions("brain_ap_resumes") as url:

        async def decide_both(store: StoredSuspensions) -> None:
            await put(store, raised("m_1"), raised("r_1"))
            for ident, asked in (("m_1", APPROVE), ("r_1", REJECT)):
                async with store.holding(APPROVER, NOW) as rows:
                    await decide_once(
                        rows, ident, APPROVER, drafting_for(APPROVER), asked=asked, now=NOW
                    )

        with_store(url, decide_both)
        ran: list[str] = []

        async def resume_both(store: StoredSuspensions) -> tuple[Any, Any]:
            return (
                await _resuming(store, "m_1", ASKER_REACH, ran),
                await _resuming(store, "r_1", ASKER_REACH, ran),
            )

        approved, rejected = with_store(url, resume_both)

    assert approved is not None and approved.resumed
    assert rejected is not None and rejected.refusal is ResumeRefusal.NOT_APPROVED
    assert ran == ["m_1"]


def test_the_raiser_reads_their_approved_suspension_and_resumes_at_the_reach_now() -> None:
    """Approved by an approver, the suspension is read back by the principal it runs as and resumed
    through `leash.resume` at the reach `reach_now` returns: the reach it was raised at resumes,
    a reach that has changed since is refused, and somebody else's id is nothing.

    Delete this and a resume can use the reach remembered at approval, which is the Monday grant
    running on Friday."""
    # Narrowed to maintenance since the approval: the row is still in scope, so only the reach
    # having moved can refuse it, and the intersection with the ceiling carries the change.
    changed = reach(ASKER, WRITE_STATUS, READ_STATUS, scope=in_department(MAINTENANCE))

    with suspensions("brain_ap_resume") as url:

        async def work(store: StoredSuspensions) -> tuple[Any, ...]:
            await put(store, raised("m_1"))
            async with store.holding(APPROVER, NOW) as rows:
                await decide_once(
                    rows, "m_1", APPROVER, drafting_for(APPROVER), asked=APPROVE, now=NOW
                )
            ran: list[str] = []
            same = await _resuming(store, "m_1", ASKER_REACH, ran)
            moved = await _resuming(store, "m_1", changed, ran)
            decider = await _resuming(
                store, "m_1", reach("u_narrow", WRITE_STATUS, READ_STATUS), ran
            )
            stranger = await _resuming(
                store, "m_1", reach("u_stranger", WRITE_STATUS, READ_STATUS), ran
            )
            return same, moved, decider, stranger

        same, moved, decider, stranger = with_store(url, work)

    assert same is not None and same.resumed
    assert moved is not None and moved.refusal is ResumeRefusal.ENTITLEMENT_CHANGED
    # The decider reads the row they decided, and `resume` refuses to run it as them.
    assert decider is not None and decider.refusal is ResumeRefusal.PRINCIPAL_CHANGED
    assert stranger is None


def test_the_table_refuses_a_decision_with_nobody_on_it_or_a_window_past_the_leashs_bound() -> None:
    """Approved with no decider, pending with one, and a window a minute past twenty-four hours
    are refused; an approved row with a decider and a time is accepted. On `0042` alone, so each
    refusal is that migration's own check and not `0083`'s verdict.

    Delete this and a row can say approved without saying by whom, or stand for a week."""
    one = raised("m_1")
    insert = (
        "INSERT INTO gate.suspension (id, trace_id, principal_id, agent_id, required_capability, "
        "action, ent_hash, artefact, action_digest, raised_at, expires_at, state, decided_by, "
        "decided_at) VALUES (%s, 'trace_test', 'u_asker', 'agent_test', 'write:ticket.status', "
        "'{}'::jsonb, %s, 'shown', %s, %s, %s, %s, %s, %s)"
    )
    ends = NOW + timedelta(hours=4)
    with the_table_alone("brain_ap_constraints") as url:
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


def test_the_migrations_build_exactly_what_the_model_declares() -> None:
    """Every constraint, index and column, compared between `0042` with `0083` and the model, with
    row-level security on.

    Delete this and the migrations and the model can disagree about a constraint, a column or the
    index."""
    with (
        suspensions("brain_ap_shape") as url,
        modelled("brain_ap_shape_modelled", TABLES) as from_models,
    ):
        assert shape(url, TABLES) == shape(from_models, TABLES)
        assert secured(url, TABLES) == dict.fromkeys(TABLES, True)


def test_the_table_migration_comes_down_and_goes_back_up() -> None:
    """Delete this and a downgrade that leaves the table or the view behind is found at the next
    upgrade."""
    with the_table_alone("brain_ap_round_trip") as url:
        migrate("brain_ap_round_trip", "downgrade", predecessor(MIGRATION))
        gone = present(url, TABLES)
        view_gone = sql(url, "SELECT to_regclass('gate.suspension_capability')")
        migrate("brain_ap_round_trip", "upgrade", revision(MIGRATION))
        back = present(url, TABLES)

    assert gone == set()
    assert view_gone == [(None,)]
    assert back == set(TABLES)


def test_the_decision_migration_comes_down_and_back_up_and_refuses_an_unrecorded_decision() -> None:
    """Down, the two columns, the trigger and its function are gone and a decision written the old
    way lands with no entry. Up again is refused while that row is there, because it names no
    verdict and none can be supplied for it; with the row gone, all three are back.

    Delete this and a downgrade that leaves the trigger behind fails on its first update, because
    the function reads a column that is no longer there, or the upgrade can invent a verdict for a
    decision the ledger never recorded."""
    database = "brain_ap_decision_round_trip"

    def built() -> tuple[Any, ...]:
        return (
            sql(
                url,
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'gate' "
                "AND table_name = 'suspension' AND column_name IN ('verdict', 'reason_code') "
                "ORDER BY 1",
            ),
            sql(
                url,
                "SELECT count(*) FROM pg_trigger WHERE tgname = 'suspension_decision_is_audited'",
            ),
            sql(url, "SELECT to_regprocedure('gate.record_suspension_decision()') IS NOT NULL"),
        )

    with suspensions(database) as url:
        migrate(database, "downgrade", predecessor(DECISION_MIGRATION))
        down = built()
        with_store(url, lambda store: put(store, raised("m_1")))
        sql(
            url,
            "UPDATE gate.suspension SET state = 'approved', decided_by = 'u_narrow', "
            "decided_at = now() WHERE id = 'm_1'",
        )
        unrecorded = entries(url)
        with pytest.raises(IntegrityError, match="a_decided_suspension_names_its_verdict"):
            migrate(database, "upgrade", revision(DECISION_MIGRATION))
        refused = built()
        sql(url, "DELETE FROM gate.suspension WHERE id = 'm_1'")
        migrate(database, "upgrade", revision(DECISION_MIGRATION))
        up = built()

    assert down == refused == ([], [(0,)], [(False,)])
    assert unrecorded == []
    assert up == ([("reason_code",), ("verdict",)], [(1,)], [(True,)])
