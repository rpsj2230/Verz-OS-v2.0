"""A sealed envelope is kept once, read back against its own digest, and decided once by name.

The first half is decisions over a row's values and runs anywhere. The second builds
`agent.browser_envelope` through `0041` and drives it as the application role; it skips when
there is no server, as every file using `tests.fixtures.scratch_postgres` does.

The clock is 2999, for the reason CLAUDE.md records about fixtures that go off.

Task ids: M19.2.3
"""

from __future__ import annotations

import importlib.util
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from brain.audit.ledger import AuditChain
from brain.audit.record import ApprovalVerdict, AuditRecorder
from brain.browsing.approval import raise_approval
from brain.browsing.enforcer import compile_policy
from brain.browsing.envelope import Envelope, compile_envelope
from brain.browsing.envelope_store import (
    EnvelopeStoreError,
    StoredEnvelope,
    load_envelope,
    put_envelope,
    record_decision,
    row_values,
    stored_from,
)
from brain.browsing.planning import Goal, PlanRequest, plan
from brain.browsing.sessions import ACT_ON_SURFACE_CAPABILITY, surface_scope
from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
from brain.console.approvals import decide
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.gate.leash import ApprovalState, SuspendedAction
from brain.session import make_app_engine, make_session_factory
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
READ = Capability(value="read:browser_surface")
WRITE = ACT_ON_SURFACE_CAPABILITY
ORIGIN = "https://books.example"
TABLES: tuple[str, ...] = ("agent.browser_envelope",)
MIGRATION = ROOT / "migrations" / "versions" / "0041_browser_envelope.py"


def books() -> Target:
    return Target(
        name="books",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="invoices",
                origin=ORIGIN,
                path="/invoices",
                verbs=frozenset({Verb.OPEN, Verb.READ}),
                capability=READ,
                reads=("number",),
            ),
            Surface(
                name="filing",
                origin=ORIGIN,
                path="/filing",
                verbs=frozenset({Verb.OPEN, Verb.SUBMIT}),
                capability=WRITE,
            ),
        ),
    )


def reach() -> EntitlementSet:
    return EntitlementSet(
        principal_id="alex",
        grants=(
            Grant(capability=READ, scope=Scope.department("finance")),
            Grant(capability=WRITE, scope=Scope.department("finance")),
        ),
    )


def compiled(*surfaces: str) -> Envelope:
    request = PlanRequest(
        goal=Goal(text="File this month's return", asked_by="alex"),
        target="books",
        surfaces=surfaces or ("invoices", "filing"),
    )
    return compile_envelope(
        plan(request, TargetRegistry(targets=(books(),))),
        books(),
        run_id="run-1",
        reach=reach(),
        ceiling=AutonomyTier.AUTONOMOUS,
    )


def raised(envelope: Envelope | None = None) -> SuspendedAction:
    return raise_approval(
        envelope or compiled(),
        books(),
        agent_id="agent_books",
        reach=reach(),
        trace_id="trace_test",
        now=NOW,
    )


def approve(suspension: SuspendedAction, *, at: datetime = NOW) -> SuspendedAction:
    approver = EntitlementSet(
        principal_id="u_approver",
        grants=(Grant(capability=WRITE, scope=surface_scope(books())),),
    )
    recorder = AuditRecorder(
        AuditChain(),
        actor_id="u_approver",
        ent_hash="e" * 32,
        trace_id="trace_test",
        clock=lambda: at,
    )
    return decide(
        suspension, approver, recorder, verdict=ApprovalVerdict.APPROVED, now=at
    ).suspension


def as_row(
    envelope: Envelope, suspension: SuspendedAction | None = None, **decision: object
) -> dict[str, Any]:
    """The columns a read would return, built through the store's own `row_values`."""
    row: dict[str, Any] = dict.fromkeys(
        ("approval_state", "raised_at", "expires_at", "decided_by", "decided_at")
    )
    row |= row_values(envelope, agent_id="agent_books", suspension=suspension)
    row |= decision
    return row


# ------------------------------------------------------------------ decisions over a row
def test_a_stored_envelope_reads_back_to_the_digest_it_was_sealed_with() -> None:
    """A read-only envelope and a waiting one both round-trip through the row's values, and
    neither is approved by being stored.

    Delete this and the sealed parts can be written in a shape the digest cannot be re-derived
    from, so every stored envelope is refused on read."""
    reading = compiled("invoices")
    waiting = compiled()

    quiet = stored_from(as_row(reading))
    pending = stored_from(as_row(waiting, raised(waiting)))

    assert quiet.envelope_digest == reading.digest()
    assert quiet.steps == tuple((step.surface, step.verb) for step in reading.steps)
    assert quiet.approval_state is None
    assert pending.envelope_digest == waiting.digest()
    assert pending.approval_state is ApprovalState.PENDING
    assert pending.approval_for(waiting) is None


def test_a_row_edited_after_it_was_sealed_is_refused_on_read() -> None:
    """A budget raised in the row, or a digest swapped for another, no longer matches.

    Delete this and a superuser's edit to the sealed parts starts a container on permissions
    nobody approved."""
    waiting = compiled()
    more = as_row(waiting, raised(waiting))
    more["sealed"]["budget"] = [["submit", 9]]
    swapped = as_row(waiting, raised(waiting), envelope_digest=compiled("filing").digest())

    with pytest.raises(EnvelopeStoreError, match="no longer matches its digest"):
        stored_from(more)
    with pytest.raises(EnvelopeStoreError, match="no longer matches its digest"):
        stored_from(swapped)


def test_the_store_refuses_an_envelope_and_an_approval_that_do_not_belong() -> None:
    """Five mismatches, each refused by name.

    Delete this and a waiting envelope can be stored with no card ever raised, which is a run
    nobody is asked about and nobody can start."""
    waiting = compiled()
    reading = compiled("invoices")

    with pytest.raises(EnvelopeStoreError, match="stored with no approval raised"):
        row_values(waiting, agent_id="agent_books", suspension=None)
    with pytest.raises(EnvelopeStoreError, match="waits for nobody"):
        row_values(reading, agent_id="agent_books", suspension=raised(waiting))
    with pytest.raises(EnvelopeStoreError, match="for another envelope"):
        row_values(waiting, agent_id="agent_books", suspension=raised(compiled("filing")))
    with pytest.raises(EnvelopeStoreError, match="for another envelope"):
        moved = raised(waiting).model_copy(update={"id": "run-2"})
        row_values(waiting, agent_id="agent_books", suspension=moved)
    with pytest.raises(EnvelopeStoreError, match="decided before the envelope was stored"):
        row_values(waiting, agent_id="agent_books", suspension=approve(raised(waiting)))


def test_a_stored_approval_approves_only_the_envelope_it_was_decided_for() -> None:
    """The row's decision goes through the same `approved` a suspension does.

    Delete this and `approval_for` can approve whatever envelope is handed to it."""
    waiting = compiled()
    decided = approve(raised(waiting), at=NOW + timedelta(minutes=1))
    stored = stored_from(
        as_row(
            waiting,
            raised(waiting),
            approval_state=decided.state.value,
            decided_by=decided.decided_by,
            decided_at=decided.decided_at,
        )
    )

    approval = stored.approval_for(waiting)

    assert approval is not None
    assert compile_policy(waiting, approval).may_write("filing", Verb.SUBMIT)
    assert stored.approval_for(compiled("filing")) is None


def test_recording_a_decision_nobody_took_is_refused_before_anything_is_written() -> None:
    """Delete this and a pending suspension can be recorded, which writes a decision with no
    decider."""
    nothing = cast(AsyncSession, None)

    with pytest.raises(EnvelopeStoreError, match="has not been decided"):
        run(lambda: record_decision(nothing, raised()))


# ------------------------------------------------------------------ against the database
def predecessor() -> str:
    """The revision `0041` names as the one before it, read off the migration."""
    spec = importlib.util.spec_from_file_location("migration_0041_predecessor", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.down_revision)


@contextmanager
def envelopes(database: str) -> Iterator[str]:
    """A fresh database holding `agent.browser_envelope`, built by `0041` itself."""
    scratch = fresh(database)
    try:
        migrate(database, "stamp", predecessor())
        migrate(database, "upgrade", "0041")
        yield scratch
    finally:
        drop(database)


def as_principal[T](url: str, principal: str, work: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """One transaction as the application role, with `app.principal_id` set, committed."""

    async def go() -> T:
        engine = make_app_engine(url)
        try:
            async with make_session_factory(engine)() as session:
                await session.execute(text("SET LOCAL ROLE brain_app"))
                await session.execute(
                    text("SELECT set_config('app.principal_id', :who, true)"), {"who": principal}
                )
                result = await work(session)
                await session.commit()
                return result
        finally:
            await engine.dispose()

    return run(go)


def test_an_envelope_is_sealed_decided_and_read_back_approved() -> None:
    """End to end as the application role: the asker seals it with its card, the approver's
    decision is recorded under their name, and the row read back approves the envelope.

    Delete this and every half of the store can pass alone while the three never meet."""
    waiting = compiled()
    card = raised(waiting)
    with envelopes("brain_bx_round_trip") as url:
        as_principal(
            url, "alex", lambda s: put_envelope(s, waiting, agent_id="agent_books", suspension=card)
        )
        pending = as_principal(url, "u_approver", lambda s: load_envelope(s, "run-1"))
        decided = approve(card)
        as_principal(url, "u_approver", lambda s: record_decision(s, decided))
        stored = as_principal(url, "alex", lambda s: load_envelope(s, "run-1"))
        absent = as_principal(url, "alex", lambda s: load_envelope(s, "run-2"))

    assert pending is not None and pending.approval_state is ApprovalState.PENDING
    assert isinstance(stored, StoredEnvelope)
    assert (stored.approval_state, stored.decided_by) == (ApprovalState.APPROVED, "u_approver")
    approval = stored.approval_for(waiting)
    assert approval is not None
    assert compile_policy(waiting, approval).may_write("filing", Verb.SUBMIT)
    assert absent is None


def test_a_second_seal_for_one_run_is_refused() -> None:
    """Written once. Delete this and `put_envelope` can become an upsert, rewriting what a run
    may do after its card was approved."""
    reading = compiled("invoices")
    with envelopes("brain_bx_once") as url:
        as_principal(url, "alex", lambda s: put_envelope(s, reading, agent_id="agent_books"))
        with pytest.raises(IntegrityError):
            as_principal(url, "alex", lambda s: put_envelope(s, reading, agent_id="agent_books"))


def test_an_envelope_cannot_be_sealed_in_somebody_elses_name() -> None:
    """The insert policy: a connection acting for somebody else is refused, the asker is not.

    Delete this and a request can put another person's reach on a card they never raised."""
    reading = compiled("invoices")
    with envelopes("brain_bx_asker") as url:
        with pytest.raises(DBAPIError, match="row-level security"):
            as_principal(url, "mallory", lambda s: put_envelope(s, reading, agent_id="agent_books"))
        as_principal(url, "alex", lambda s: put_envelope(s, reading, agent_id="agent_books"))
        stored = sql(url, "SELECT asked_by FROM agent.browser_envelope")

    assert stored == [("alex",)]


def test_a_decision_is_recorded_once_and_only_under_the_deciders_own_name() -> None:
    """Recorded by somebody else's connection is refused by the policy, recorded by the decider
    succeeds, and recorded again finds no pending row.

    Delete this and one person's connection can write another person's approval."""
    waiting = compiled()
    card = raised(waiting)
    decided = approve(card)
    with envelopes("brain_bx_decider") as url:
        as_principal(
            url, "alex", lambda s: put_envelope(s, waiting, agent_id="agent_books", suspension=card)
        )
        with pytest.raises(DBAPIError, match="row-level security"):
            as_principal(url, "sam", lambda s: record_decision(s, decided))
        as_principal(url, "u_approver", lambda s: record_decision(s, decided))
        with pytest.raises(EnvelopeStoreError, match="no pending envelope"):
            as_principal(url, "u_approver", lambda s: record_decision(s, decided))


def test_the_app_role_cannot_edit_the_sealed_parts_and_any_other_edit_is_refused_on_read() -> None:
    """The column grant stops the application role; a superuser's edit is caught by the digest.

    Matched on the privilege message and not only the SQLSTATE: with UPDATE granted on the whole
    row, the update policy's WITH CHECK still refuses this statement under the same 42501, so a
    bare `InsufficientPrivilege` passed with the grant widened. Found by mutation.

    Delete this and `0041` can grant UPDATE on the whole row with every other test still green."""
    waiting = compiled()
    card = raised(waiting)
    with envelopes("brain_bx_sealed") as url:
        as_principal(
            url, "alex", lambda s: put_envelope(s, waiting, agent_id="agent_books", suspension=card)
        )
        with psycopg.connect(url) as conn:
            conn.execute("SET ROLE brain_app")
            with pytest.raises(psycopg.errors.InsufficientPrivilege, match="permission denied"):
                conn.execute("UPDATE agent.browser_envelope SET sealed = '{}'::jsonb")
            conn.rollback()
        sql(
            url,
            "UPDATE agent.browser_envelope SET sealed = jsonb_set(sealed, '{budget}', %s::jsonb)",
            '[["submit", 9]]',
        )
        with pytest.raises(EnvelopeStoreError, match="no longer matches its digest"):
            as_principal(url, "alex", lambda s: load_envelope(s, "run-1"))


def test_the_table_refuses_a_decision_with_nobody_on_it_and_accepts_one_with_somebody() -> None:
    """Approved with no decider, and pending with one, are both refused; approved with a decider
    and a time is accepted.

    Delete this and a row can say approved without saying by whom."""
    waiting = compiled()
    insert = (
        "INSERT INTO agent.browser_envelope (run_id, target, agent_id, asked_by, envelope_digest, "
        "sealed, approval_state, raised_at, expires_at, decided_by, decided_at) "
        "VALUES (%s, 'books', 'agent_books', 'alex', %s, '{}'::jsonb, %s, %s, %s, %s, %s)"
    )
    ends = NOW + timedelta(hours=4)
    with envelopes("brain_bx_constraints") as url:
        with pytest.raises(psycopg.errors.CheckViolation):
            sql(url, insert, "run-a", waiting.digest(), "approved", NOW, ends, None, None)
        with pytest.raises(psycopg.errors.CheckViolation):
            sql(url, insert, "run-b", waiting.digest(), "pending", NOW, ends, "u_approver", NOW)
        sql(url, insert, "run-c", waiting.digest(), "approved", NOW, ends, "u_approver", NOW)
        stored = sql(url, "SELECT run_id FROM agent.browser_envelope")

    assert stored == [("run-c",)]


def test_the_migration_builds_exactly_what_the_model_declares() -> None:
    """Every constraint, index and column, compared between `0041` and the model, with row-level
    security on.

    Delete this and the migration and the model can disagree about a constraint's name."""
    with (
        envelopes("brain_bx_shape") as url,
        modelled("brain_bx_shape_modelled", TABLES) as from_models,
    ):
        assert shape(url, TABLES) == shape(from_models, TABLES)
        assert secured(url, TABLES) == dict.fromkeys(TABLES, True)


def test_the_migration_comes_down_and_goes_back_up() -> None:
    """Delete this and a downgrade that leaves the table behind is found at the next upgrade."""
    with envelopes("brain_bx_round_trip_migration") as url:
        migrate("brain_bx_round_trip_migration", "downgrade", predecessor())
        gone = present(url, TABLES)
        migrate("brain_bx_round_trip_migration", "upgrade", "0041")
        back = present(url, TABLES)

    assert gone == set()
    assert back == set(TABLES)
