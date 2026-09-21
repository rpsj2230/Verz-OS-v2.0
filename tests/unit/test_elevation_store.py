"""An elevation request reaches its row, the ledger and the resolver: table, trigger, store.

`tests/unit/test_govern_people_routes.py` holds who may file, see and decide a request over an
in-memory store, and `tests/unit/test_elevation.py` holds the decisions. This file holds everything
below them. The first half needs no server: it reads `0062` as the SQL it renders, holds the
trigger's subject and details to `AuditRecorder.elevation`'s, holds the copied grammars to the live
ones, and the table's grants and policies to a request decided once.

The second half builds a database through `0062` and proves the leaf's sentence against the one
resolver: **an approved elevation widens what the requester resolves to, and after its lapse it no
longer does**, with the row, the ledger entries and a chain that verifies. It also proves the
refusals write nothing. **It skips when there is no server**, and CI always has one.

Task ids: M27.7.8
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.audit.ledger import IDENTIFIER, AuditChain, AuditEntry
from brain.audit.record import AuditRecorder, ElevationChange
from brain.console.elevation import ElevationError, client_recipients
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.db import metadata
from brain.gate.elevation_store import ElevationRecords, PendingRequest, StoredElevations
from brain.gate.entitlement_store import StoredEntitlements
from brain.govern_people_routes import approval_grant
from brain.identity.roles import BreakGlassReason, RoleGrant
from brain.session import make_session_factory
from brain.tables import elevation as table_module
from brain.tables.gate import CAPABILITY_PATTERN, SLUG_SQL_PATTERN
from brain.tables.identity import PRINCIPAL_ID_CHARS
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

MIGRATION: Final = VERSIONS / "0062_organisation_and_elevation.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

CAPABILITY: Final = "read:client.name"
WHOLE: Final = Scope.unrestricted()

#: The approver holds the authority and the capability company-wide, as an administrator does.
APPROVER: Final = EntitlementSet(
    principal_id="u_approver",
    grants=(
        Grant(capability=Capability(value="approve:grant"), scope=WHOLE),
        Grant(capability=Capability(value=CAPABILITY), scope=WHOLE),
    ),
)


def recorder() -> AuditRecorder:
    return AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash="0" * 32, trace_id="t", clock=lambda: LONG_AGO
    )


# ------------------------------------------------------------ the migration and the model


def test_the_trigger_writes_the_subject_and_details_the_recorder_writes() -> None:
    """Delete this and the entry a deployed database keeps and the entry `AuditRecorder` writes can
    come apart without a server to notice: a trigger that put the explanation in the details, or
    named the decider as the subject, passes every stubbed test. Read off the executed module."""
    requested = recorder().elevation(
        principal_id="u_1",
        change=ElevationChange.REQUESTED,
        capability=Capability(value=CAPABILITY),
        reason="incident_response",
    )
    body = " ".join(migration_module(MIGRATION).ELEVATION_REQUEST_TRIGGER_FUNCTION.split())

    assert requested.subject == "principal:u_1"
    assert requested.details == {
        "change": "requested",
        "capability": CAPABILITY,
        "reason": "incident_response",
    }
    assert "v_subject text := 'principal:' || NEW.principal_id;" in body
    assert (
        "v_where := jsonb_build_object('capability', NEW.capability, 'reason', NEW.reason);" in body
    )
    assert "v_details := v_where || jsonb_build_object('change', v_changes[i]);" in body
    assert (
        "v_changes := v_changes || 'requested'::text; v_actors := v_actors || NEW.principal_id"
        in body
    )
    assert (
        "ELSIF OLD.decision IS NULL AND NEW.decision IS NOT NULL THEN v_changes := v_changes || "
        "NEW.decision::text; v_actors := v_actors || NEW.decided_by::text;"
    ) in body
    assert "v_seq, v_at, v_actors[i], 'elevation', v_subject, v_ent_hash," in body
    assert "explanation" not in body
    assert {one.value for one in ElevationChange} == {"requested", "approved", "denied"}
    assert {one.value for one in table_module.ElevationDecision} < {
        one.value for one in ElevationChange
    }


def test_the_migration_holds_the_live_grammars_and_widths_it_copied() -> None:
    """`0062` copies grammars and bounds for `0009`'s reason. Delete this and one side changes
    alone: a capability the grant table admits and this one refuses, a window longer than the
    session ceiling, or a reason code in `BreakGlassReason` that the table refuses."""
    migration = migration_module(MIGRATION)

    assert migration.IDENTIFIER == IDENTIFIER
    assert migration.PRINCIPAL_ID_CHARS == PRINCIPAL_ID_CHARS
    assert migration.CAPABILITY_PATTERN == CAPABILITY_PATTERN
    assert migration.SLUG_SQL_PATTERN == SLUG_SQL_PATTERN
    assert migration.LONGEST_HOURS == table_module.LONGEST_HOURS == 4
    assert migration.EXPLANATION_CHARS == table_module.EXPLANATION_CHARS
    assert migration.DECISIONS == "decision IN ('approved', 'denied')"
    assert all(f"'{one.value}'" in migration.REASONS for one in BreakGlassReason)
    assert max(len(one.value) for one in BreakGlassReason) <= migration.REASON_CHARS
    assert re.fullmatch(migration.CAPABILITY_PATTERN, CAPABILITY)


def test_the_migration_builds_the_request_table_exactly_as_the_model_declares_it() -> None:
    """Compared as rendered DDL, for the reason `test_tables` compares 0002's. Delete this and the
    model can gain a column or lose a check, such as the one refusing a lapse longer than asked,
    with the database built the old way."""
    emitted = squash(rendered("upgrade", MIGRATION))
    mapped = metadata.tables["gate.elevation_request"]

    assert squash(str(CreateTable(mapped).compile(dialect=DIALECT))) in emitted
    for index in mapped.indexes:
        assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted


def test_the_application_may_file_a_request_and_decide_it_once_and_nothing_else() -> None:
    """A record of who approved somebody's access that could be edited is one whose author moved
    after the fact. Delete this and an UPDATE on the capability or the requester, or a DELETE, can
    arrive with the table, or row-level security can be left off it, with every other test green."""
    emitted = squash(rendered("upgrade", MIGRATION))

    assert "ALTER TABLE gate.elevation_request ENABLE ROW LEVEL SECURITY" in emitted
    assert "GRANT SELECT, INSERT ON gate.elevation_request TO brain_app" in emitted
    assert (
        "GRANT UPDATE (decision, decided_by, decided_at, grant_id, lapses_at) ON "
        "gate.elevation_request TO brain_app"
    ) in emitted
    assert "DELETE ON gate.elevation_request" not in emitted
    assert "GRANT UPDATE ON gate.elevation_request" not in emitted
    assert "FOR INSERT TO brain_app WITH CHECK (decision IS NULL AND grant_id IS NULL)" in emitted
    assert (
        "FOR UPDATE TO brain_app USING (decision IS NULL) WITH CHECK (decision IS NOT NULL)"
        in emitted
    )
    assert (
        "CREATE TRIGGER elevation_request_is_audited AFTER INSERT OR UPDATE ON "
        "gate.elevation_request"
    ) in emitted


def test_the_stored_elevations_are_the_records_the_routes_ask_for() -> None:
    """Delete this and the store can drift from the protocol the routes hold, and a route handed
    the database is handed something `organisation_records_of` would not accept."""
    assert isinstance(StoredElevations(async_sessionmaker()), ElevationRecords)


# ------------------------------------------------------------------------ the database


@contextmanager
def through_0062(database: str) -> Iterator[str]:
    """A database with `0062` applied. Without pgvector, `retirable` stops at `0048`; `0049` is run
    for real, then the migrations that build the tables `0059` and `0060` put triggers and
    constraints on, out of order and each after a stamp of its predecessor, as
    `tests/unit/test_console_control_audit.py` runs them: `0014` and `0016` for the agent and its
    install, `0025` and `0030` for the control run and its names, and `0053` for the webhook
    changes. `0054` to `0062` then run for real."""
    with retirable(database) as url:
        if not has_pgvector(url):
            migrate(database, "upgrade", "0049")
            for predecessor, revision in (
                ("0013", "0014"),
                ("0015", "0016"),
                ("0024", "0025"),
                ("0029", "0030"),
                ("0052", "0053"),
            ):
                migrate(database, "stamp", predecessor)
                migrate(database, "upgrade", revision)
            migrate(database, "upgrade", "0062")
        yield url


#: The standing Super Admins every approval tells (M1.2.5): the approver is one of them, so the
#: other two are told and the approver is not.
SUPER_ADMINS: Final = ("u_approver", "u_sa_one", "u_sa_two")


def seeded(url: str) -> None:
    """A requester and an approver in web, a named scope, a grant of the capability that lapsed
    long ago, which is what a person elevated once before holds, and the standing Super Admins."""
    for pid in ("u_requester", *SUPER_ADMINS):
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department)"
            " VALUES (%s, 'human', 'staff', %s, 'web')",
            pid,
            f"Person {pid}",
        )
    sql(
        url,
        "INSERT INTO gate.scope (slug, predicate) VALUES ('web_all', '{\"department\": \"web\"}')",
    )
    sql(
        url,
        "INSERT INTO gate.capability_grant"
        " (principal_id, capability, scope, granted_by, reason, not_after)"
        " VALUES ('u_requester', %s, '{\"clauses\": []}', 'u_seed', 'an old elevation', %s)",
        CAPABILITY,
        LONG_AGO,
    )
    for pid in SUPER_ADMINS:
        sql(
            url,
            "INSERT INTO gate.role_grant (principal_id, role, granted_by, reason)"
            " VALUES (%s, 'super_admin', 'u_seed', 'standing')",
            pid,
        )


def entries(url: str) -> list[AuditEntry]:
    rows = sql(
        url,
        "SELECT seq, at, actor_id, action, subject, ent_hash, trace_id, details, prev_hash,"
        " entry_hash FROM obs.audit_entry ORDER BY seq",
    )
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
    return [AuditEntry(**dict(zip(names, row, strict=True))) for row in rows]


def grant_for(pending: PendingRequest, requester: EntitlementSet, at: datetime) -> Any:
    return approval_grant(pending, approver=APPROVER, requester=requester, at=at)


def tell(role_grants: Sequence[RoleGrant], pending: PendingRequest, at: datetime) -> Any:
    """The route's `tell`, for the approver these tests use: `client_recipients` or None."""
    try:
        return client_recipients(
            role_grants, subject_id=pending.request.principal_id, authorised_by="u_approver", now=at
        )
    except ElevationError:
        return None


def test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not() -> None:
    """M27.7.8's proof, through the store, the route's own approval and the one resolver, as the
    role the application uses.

    A request leaves a pending row and a `requested` entry by the requester. Approving it retires
    the lapsed grant of the same capability, writes a grant whose `not_after` is the requested
    hours after the database's instant, marks the request approved with that grant and lapse, and
    appends the revoke, the grant and the `approved` entry by the approver; the chain verifies. The
    requester resolves to the capability, at the named scope, just after the approval, and not at
    all just after the lapse. Delete this and every one of those can be false in production while
    the stubbed tests stay green. **Skips without a server.**"""
    with through_0062("brain_elevation_request") as url:
        seeded(url)
        before = len(entries(url))

        async def walk() -> tuple[Any, Any, EntitlementSet, EntitlementSet]:
            engine = app_engine(url)
            try:
                sessions = make_session_factory(engine)
                store = StoredElevations(sessions)
                filed = await store.file(
                    principal_id="u_requester",
                    capability=CAPABILITY,
                    scope_slug="web_all",
                    reason=BreakGlassReason.INCIDENT_RESPONSE.value,
                    explanation="the client portal is down and I need their names",
                    hours=2,
                    ent_hash="a" * 32,
                    trace_id="trace-file",
                )
                assert filed is not None
                decided = await store.approve(
                    filed.request_id,
                    approver_id="u_approver",
                    ent_hash="b" * 32,
                    trace_id="trace-approve",
                    grant_for=grant_for,
                    tell=tell,
                )
                assert decided is not None and decided.lapses_at is not None
                resolver = StoredEntitlements(sessions)
                during = await resolver.load(
                    "u_requester", decided.decided_at + timedelta(minutes=1)
                )
                after = await resolver.load("u_requester", decided.lapses_at + timedelta(seconds=1))
                listed, _ = await store.requests(limit=10)
                return decided, listed, during, after
            finally:
                await engine.dispose()

        decided, listed, during, after = run(walk)
        rows = sql(
            url,
            "SELECT r.decision, r.decided_by, r.lapses_at = g.not_after, g.granted_by,"
            " r.lapses_at = r.decided_at + interval '2 hours'"
            " FROM gate.elevation_request r JOIN gate.capability_grant g ON g.id = r.grant_id",
        )
        [(retired,)] = sql(
            url,
            "SELECT count(*) FROM gate.capability_grant WHERE deleted_at IS NOT NULL"
            " AND reason = 'an old elevation'",
        )
        chain = entries(url)
        notices = sql(
            url,
            "SELECT recipient_id, principal_id, authorised_by, reason, lapses_at = %s"
            " FROM gate.break_glass_notice WHERE request_id = %s ORDER BY recipient_id",
            decided.lapses_at,
            decided.request_id,
        )

    # M1.2.5: the standing Super Admins who took no part are told, in the approval's transaction.
    assert decided.notified == ("u_sa_one", "u_sa_two")
    assert notices == [
        ("u_sa_one", "u_requester", "u_approver", "incident_response", True),
        ("u_sa_two", "u_requester", "u_approver", "incident_response", True),
    ]
    assert rows == [("approved", "u_approver", True, "u_approver", True)]
    assert retired == 1
    wanted = Capability(value=CAPABILITY)
    assert during.scope_for(wanted, decided.decided_at) == Scope.department("web")
    assert after.scope_for(wanted, decided.lapses_at) is None
    assert listed[0].grant_live is True and listed[0].decision is not None
    tail = [(one.action.value, one.subject, one.actor_id) for one in chain[before:]]
    assert tail == [
        ("elevation", "principal:u_requester", "u_requester"),
        ("revoke", tail[1][1], "u_approver"),
        ("grant", tail[2][1], "u_approver"),
        ("elevation", "principal:u_requester", "u_approver"),
        # `0104`: the approval opens a break-glass session, recorded after the decision.
        ("break_glass", f"session:{decided.request_id}", "u_approver"),
    ]
    assert chain[before].details == {
        "change": "requested",
        "capability": CAPABILITY,
        "reason": "incident_response",
    }
    assert chain[-2].details["change"] == "approved"
    assert chain[-1].details == {
        "reason": "incident_response",
        "principal": "u_requester",
        "authorised_by": "u_approver",
    }
    assert [one.trace_id for one in (chain[before], chain[-2], chain[-1])] == [
        "trace-file",
        "trace-approve",
        "trace-approve",
    ]
    assert AuditChain(chain).verify() is None


def test_a_denial_is_recorded_and_every_refused_decision_writes_nothing() -> None:
    """The refusals, against the real store and the real approval. Delete this and the requester
    approving their own request, an approval of a capability the requester already holds (which
    would narrow them), an approval naming a scope nobody registered, and a second decision on a
    decided request can each write a row or an entry. The positive half is a denial by somebody
    else, recorded once. **Skips without a server.**"""
    with through_0062("brain_elevation_refused") as url:
        seeded(url)
        sql(
            url,
            "INSERT INTO gate.capability_grant"
            " (principal_id, capability, scope, granted_by, reason)"
            " VALUES ('u_requester', 'read:invoice.*', '{\"clauses\": []}', 'u_seed', 'held')",
        )

        async def walk() -> list[object]:
            engine = app_engine(url)
            try:
                store = StoredElevations(make_session_factory(engine))

                async def ask(capability: str, slug: str = "web_all") -> uuid.UUID:
                    filed = await store.file(
                        principal_id="u_requester",
                        capability=capability,
                        scope_slug=slug,
                        reason="data_recovery",
                        explanation="restoring what was lost",
                        hours=1,
                        ent_hash="a" * 32,
                        trace_id="trace",
                    )
                    assert filed is not None
                    return filed.request_id

                held = await ask("read:invoice.total")
                nowhere = await ask(CAPABILITY, slug="no_such_scope")
                own = await ask(CAPABILITY)

                def as_requester(
                    pending: PendingRequest, requester: EntitlementSet, at: datetime
                ) -> Any:
                    self_approver = EntitlementSet(
                        principal_id="u_requester", grants=APPROVER.grants
                    )
                    return approval_grant(
                        pending, approver=self_approver, requester=requester, at=at
                    )

                results: list[object] = [
                    await store.approve(
                        held,
                        approver_id="u_approver",
                        ent_hash="b" * 32,
                        trace_id="t",
                        grant_for=grant_for,
                        tell=tell,
                    ),
                    await store.approve(
                        nowhere,
                        approver_id="u_approver",
                        ent_hash="b" * 32,
                        trace_id="t",
                        grant_for=grant_for,
                        tell=tell,
                    ),
                    await store.approve(
                        own,
                        approver_id="u_requester",
                        ent_hash="b" * 32,
                        trace_id="t",
                        grant_for=as_requester,
                        tell=tell,
                    ),
                ]
                denied = await store.deny(
                    own,
                    decider_id="u_approver",
                    ent_hash="b" * 32,
                    trace_id="t",
                    may=lambda _: True,
                )
                results.append(denied)
                results.append(
                    await store.deny(
                        own,
                        decider_id="u_approver",
                        ent_hash="b" * 32,
                        trace_id="t",
                        may=lambda _: True,
                    )
                )
                return results
            finally:
                await engine.dispose()

        results = run(walk)
        decisions = sql(
            url, "SELECT decision, decided_by FROM gate.elevation_request ORDER BY requested_at"
        )
        [(grants,)] = sql(
            url, "SELECT count(*) FROM gate.capability_grant WHERE deleted_at IS NULL"
        )
        actions = [one.action.value for one in entries(url) if one.action.value == "elevation"]

    assert results[:3] == [None, None, None]
    assert results[3] is not None and results[4] is None
    assert decisions == [(None, None), (None, None), ("denied", "u_approver")]
    assert grants == 2
    assert actions == ["elevation", "elevation", "elevation", "elevation"]
