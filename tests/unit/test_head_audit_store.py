"""Each department head's audit reach, rewritten from the staff list on every scheduled read.

Without a server: the statements a head's reach becomes, over reaches `audit_reach_for_head`
computes from real rosters; the whole rewrite over a session that answers its reads the way the
database would; the scheduled run, which rewrites the heads after the roster and never lets a
failure there undo it; and the console path, where a signed-in head asks `GET /audit` and the
navigation with a reach read off the statements the rewrite wrote.

Then against PostgreSQL, which is the proof, because every grant this module wrote was refused by
the ledger's actor grammar until it was run against one: the rows and the entries the triggers
append, the reach the one resolver gives the head, what the audit route answers them over the real
ledger, a transfer, a leaver, a former head, a head who left, and the scheduled run doing all of it
in the run that applies the staff list. CI sets `DATABASE_URL`; without it those tests skip.

Task ids: M1.8.3
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.dml import Insert, Update

from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.audit.ledger import AuditAction
from brain.audit.view import CAPABILITY_BY_KIND, MAX_PAGE_SIZE, AuditFilter, AuditRow, AuditView
from brain.audit_routes import StoredLedger, read_page
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.gate.context import Channel
from brain.gate.entitlement_store import StoredEntitlements
from brain.identity.bearer import TokenAuthority
from brain.identity.packs import SubjectGrant
from brain.identity.staff_roster import digest_of
from brain.identity.staff_source import DEFAULT_TRUST, Roster
from brain.identity.staff_sync import (
    AUDIT_PAGE_CAPABILITY,
    AUDIT_PLANE_CAPABILITY,
    GRANT_LIFETIME,
    ROSTER_PREFIX,
    SYNC_INTERVAL,
    audit_reach_for_head,
)
from brain.identity.teams import PrincipalSubject
from brain.ops import head_audit_store
from brain.ops.head_audit_store import heads_from, rewrite_head_audit_reach, writes_for
from brain.ops.staff_sync_store import leavers_principals
from brain.session import make_session_factory
from brain.tables.organisation import DepartmentLeadRow
from tests.fixtures.console_http import Store, headers
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_api_routes import AUDIENCE, ISSUER, Keys, NoCache, Versions, verifier
from tests.unit.test_audit_routes import Directory, Ledger, chain_of, stored
from tests.unit.test_staff_sync import person

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Far outside any plausible wall clock, on `tests/unit/test_scope_and_capability.py`'s rule.
READ_AT = datetime(2999, 1, 1, 3, 0, tzinfo=UTC)
SOURCE = "google_workspace"
GRANTOR = f"{ROSTER_PREFIX}{SOURCE}"
#: A subject the token fixture signs in, so the same head can ask the routes.
HEAD = "u_narrow"
HEAD_ADDRESS = "head@example.com"
BOUND = {"priya@example.com": "u_priya", "wei@example.com": "u_wei", "sam@example.com": "u_sam"}
#: The kinds that decide which entries a head reads, as opposed to the page and its plane.
ROW_CAPABILITIES = frozenset(one.value for one in CAPABILITY_BY_KIND.values())
FIVE = sorted(
    [
        AUDIT_PAGE_CAPABILITY.value,
        AUDIT_PLANE_CAPABILITY.value,
        "read:audit.agent",
        "read:audit.leash",
        "read:audit.principal",
    ]
)


def roster(*people: Any) -> Roster:
    return Roster(source=SOURCE, people=people, complete=True, asserts=DEFAULT_TRUST[SOURCE])


MAINTENANCE = roster(
    person("priya@example.com", department="Maintenance"),
    person("wei@example.com", department="Maintenance"),
    person("sam@example.com", department="Web"),
)
WEI_MOVED = roster(
    person("priya@example.com", department="Maintenance"),
    person("wei@example.com", department="Web"),
    person("sam@example.com", department="Web"),
)
PRIYA_LEFT = roster(
    person("priya@example.com", department="Maintenance", active=False),
    person("wei@example.com", department="Web"),
    person("sam@example.com", department="Web"),
)


def people(*members: str) -> Clause:
    return Clause(field="actor_id", op=Op.IN, value=members)


def sql_of(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=DIALECT)).split())


def params_of(statement: Any) -> dict[str, Any]:
    return dict(statement.compile(dialect=DIALECT).params)


def a_grant(
    capability: str, members: tuple[str, ...], *, by: str = GRANTOR, head: str = HEAD
) -> SubjectGrant:
    return SubjectGrant(
        subject=PrincipalSubject(principal_id=head),
        capability=Capability(value=capability),
        scope=Scope(clauses=(people(*members),)),
        granted_by=by,
        reason="heads maintenance, whose people this roster names",
        granted_at=READ_AT - timedelta(days=1),
        not_after=READ_AT + timedelta(hours=1),
    )


def reach_for(
    source: Roster, held: Sequence[SubjectGrant] = (), *, read_at: datetime = READ_AT
) -> Any:
    return audit_reach_for_head(
        source,
        department=("maintenance",),
        head_id=HEAD,
        known=BOUND,
        read_at=read_at,
        held=held,
    )


# ------------------------------------------------------------------------ the statements


def test_a_head_with_people_and_nothing_held_is_granted_the_five_grants_over_them() -> None:
    """**Option A applied.** Three kinds scoped to the people the roster places in the
    department, and the page and its console plane scoped to those people in that department.
    Delete this and the reach `audit_reach_for_head` computes can go on being computed and never
    written, which is where it stood from item 48's decision until this module."""
    statements = writes_for(reach_for(MAINTENANCE), [], read_at=READ_AT)
    assert all(isinstance(one, Insert) for one in statements)
    written = {params_of(one)["capability"]: params_of(one) for one in statements}
    assert sorted(written) == FIVE
    kinds = [{"field": "actor_id", "op": "in", "value": ["u_priya", "u_wei"]}]
    screen_ = [*kinds, {"field": "department", "op": "eq", "value": "maintenance"}]
    for capability, one in written.items():
        assert one["principal_id"] == HEAD
        assert one["granted_by"] == GRANTOR
        assert one["scope"]["clauses"] == (kinds if capability in ROW_CAPABILITIES else screen_)
        assert one["not_after"] == READ_AT + GRANT_LIFETIME


def test_a_capability_somebody_else_granted_the_head_is_not_written_again() -> None:
    """The table holds one live grant per person and capability, and an administrator's is not
    the sync's to replace; a plane an administrator gave over the department is the case that
    matters most. Delete this and a head who already holds either makes every nightly run fail
    on the unique index."""
    for theirs in (
        a_grant("read:audit.principal", ("u_anyone",), by="u_admin"),
        SubjectGrant(
            subject=PrincipalSubject(principal_id=HEAD),
            capability=AUDIT_PLANE_CAPABILITY,
            scope=Scope.department("maintenance"),
            granted_by="u_admin",
            reason="runs maintenance",
            granted_at=READ_AT,
        ),
    ):
        statements = writes_for(reach_for(MAINTENANCE, [theirs]), [theirs], read_at=READ_AT)
        written = [params_of(one)["capability"] for one in statements]
        assert theirs.capability.value not in written
        assert len(written) == 4


def test_a_transfer_retires_the_roster_grants_and_writes_them_again_over_who_is_left() -> None:
    """Wei moves to Web: each roster grant naming both is retired and one naming Priya alone is
    written, retirements first so the unique index never sees two live rows. Delete this and a
    head goes on reading somebody who left their department."""
    held = reach_for(MAINTENANCE).to_insert
    statements = writes_for(reach_for(WEI_MOVED, held), held, read_at=READ_AT)
    kinds = [type(one).__name__ for one in statements]
    assert kinds == ["Update"] * 5 + ["Insert"] * 5
    assert all("deleted_at" in sql_of(one) and "LIKE" in sql_of(one) for one in statements[:5])
    named = {
        tuple(clause["value"])
        for one in statements[5:]
        for clause in params_of(one)["scope"]["clauses"]
        if clause["field"] == "actor_id"
    }
    assert named == {("u_priya",)}


def test_a_head_whose_people_did_not_change_has_the_lapse_moved_on_and_nothing_else() -> None:
    """A roster grant lapses two sync intervals after its reading. Delete this and a head whose
    department is unchanged loses every audit read the night after the lifetime runs out, because
    the reach reads as unchanged and nothing renews it."""
    held = reach_for(MAINTENANCE, read_at=READ_AT - SYNC_INTERVAL).to_insert
    statements = writes_for(reach_for(MAINTENANCE, held), held, read_at=READ_AT)
    assert all(isinstance(one, Update) for one in statements)
    assert len(statements) == 5
    assert {params_of(one)["not_after"] for one in statements} == {READ_AT + GRANT_LIFETIME}
    assert all(
        "deleted_at" not in sql_of(one).split(" SET ")[1].split(" WHERE ")[0] for one in statements
    )


def test_a_source_not_trusted_with_departments_writes_nothing() -> None:
    """Delete this and a spreadsheet that cannot say who is in which department rewrites who a
    head may audit."""
    untrusted = Roster(source="google_sheet", people=MAINTENANCE.people, complete=True)
    assert reach_for(untrusted).refusals
    assert writes_for(reach_for(untrusted), [], read_at=READ_AT) == []


# ------------------------------------------------------------------------ the rewrite


@dataclass
class Answer:
    rows: list[Any]

    def all(self) -> list[Any]:
        return self.rows

    def scalars(self) -> Answer:
        return self


@dataclass
class HeadsSession:
    """Answers the lead, holder, binding and grant reads as the database would, and keeps every
    write. Each read is recognised by the statement its builder makes, not by a word in it."""

    leads: list[tuple[str, str]] = field(default_factory=lambda: [(HEAD, "maintenance")])
    holders: list[str] = field(default_factory=list)
    held: list[Any] = field(default_factory=list)
    written: list[Any] = field(default_factory=list)

    async def execute(self, statement: Any) -> Answer:
        if isinstance(statement, Insert | Update):
            self.written.append(statement)
            return Answer([])
        text = sql_of(statement)
        if text == sql_of(head_audit_store.leads()):
            return Answer(self.leads)
        if text == sql_of(head_audit_store.roster_audit_holders()):
            return Answer(self.holders)
        if "principal_identity" in text:
            return Answer([(digest_of(address), pid) for address, pid in BOUND.items()])
        if "capability_grant" in text:
            return Answer(self.held)
        raise AssertionError(text)


def rewrite(session: HeadsSession, source: Roster = MAINTENANCE) -> Any:
    return asyncio.run(rewrite_head_audit_reach(session, source, read_at=READ_AT))  # type: ignore[arg-type]


def test_the_rewrite_reads_leads_bindings_and_grants_and_writes_each_heads_reach() -> None:
    """End to end over the reads: the lead table names the head, the email bindings name the
    people, and the head's five grants are written. Delete this and the pieces above can each be
    right while the rewrite asks the wrong table who leads."""
    session = HeadsSession()
    applied = rewrite(session)
    assert [(one.head_id, one.members) for one in applied] == [(HEAD, ("u_priya", "u_wei"))]
    assert len(session.written) == 5


def test_a_former_head_has_every_grant_a_sync_gave_them_retired() -> None:
    """Somebody holding sync-written audit grants who is no longer a live head is retired in
    the run that finds them, before anybody's reach is written, and a live head is not. Delete
    this and a lead stood down goes on reading their old department until the lapse, because the
    rewrite walks live leads and never looks at them again."""
    session = HeadsSession(holders=[HEAD, "u_old_head"])
    rewrite(session)
    first = session.written[0]
    assert isinstance(first, Update)
    assert params_of(first)["principal_id_1"] == "u_old_head"
    assert "deleted_at=statement_timestamp()" in sql_of(first).replace(" ", "")
    retired = [
        params_of(one).get("principal_id_1")
        for one in session.written
        if isinstance(one, Update) and "deleted_at=statement_timestamp()" in sql_of(one)
    ]
    assert retired == ["u_old_head"]

    nobody_leads = HeadsSession(leads=[], holders=["u_old_head"])
    assert rewrite(nobody_leads) == ()
    assert [params_of(one)["principal_id_1"] for one in nobody_leads.written] == ["u_old_head"]


def test_a_former_heads_retirement_touches_only_what_a_sync_wrote() -> None:
    """The retirement is bounded to live audit grants carrying the roster's grantor. Delete this
    and a former head's company-wide audit read, or any other grant an administrator gave them,
    goes with the ones the sync wrote."""
    retire = sql_of(head_audit_store.retire_a_former_heads_grants("u_old_head"))
    params = params_of(head_audit_store.retire_a_former_heads_grants("u_old_head"))
    assert "capability_grant.deleted_at IS NULL" in retire
    assert "capability_grant.granted_by LIKE" in retire
    assert params["granted_by_1"] == ROSTER_PREFIX
    assert set(params["capability_1"]) >= set(FIVE)
    assert "read:client" not in " ".join(params["capability_1"])


def test_a_head_of_two_departments_is_one_reach_over_both() -> None:
    """Delete this and a head of two departments is written each department's people in turn,
    reads whichever came last, and the ledger takes a revocation and a grant for each every
    night."""
    session = HeadsSession(leads=[(HEAD, "maintenance"), (HEAD, "web")])
    applied = rewrite(session)
    assert [(one.head_id, one.members) for one in applied] == [
        (HEAD, ("u_priya", "u_sam", "u_wei"))
    ]
    assert len(session.written) == 5
    assert heads_from([("u_a", "web"), ("u_b", "web"), ("u_a", "finance")]) == {
        "u_a": ("finance", "web"),
        "u_b": ("web",),
    }


def test_a_lead_the_roster_marks_as_left_is_not_read_as_a_head() -> None:
    """The lead read excludes every principal the staff list has marked as having left, by the
    same join that stops a leaver's agents. Asserted on the whole condition rather than on a word
    in the statement. Delete this and a head who left keeps the reach renewed every night until
    somebody ends the lead by hand."""
    condition = DepartmentLeadRow.principal_id.not_in(leavers_principals())
    assert sql_of(condition) in sql_of(head_audit_store.leads())


def test_a_person_nobody_has_bound_contributes_nothing() -> None:
    """Delete this and the rewrite can put somebody into a head's reach by address alone."""
    known = head_audit_store.known_from(MAINTENANCE, {digest_of("priya@example.com"): "u_priya"})
    assert known == {"priya@example.com": "u_priya"}


# ------------------------------------------------------------------------ the scheduled run


def test_the_scheduled_run_rewrites_the_heads_after_the_roster_and_survives_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run applies the roster, then the heads, each in its own transaction; a failure in the
    second is logged and the run still reports the roster applied. Delete this and the heads'
    reach can stop being called, or its failure can roll back every joiner and leaver."""
    from brain.ops import staff_sync_run
    from tests.unit.test_staff_sync_run import APP_ID, APP_SECRET, LARK_ENV, Keys, Lease, run

    order: list[str] = []

    async def read_members(session: object, source: str) -> tuple[()]:
        return ()

    async def read_last_applied(session: object, source: str) -> None:
        return None

    async def write_application(session: object, app: object, record: object) -> None:
        order.append("roster")

    async def failing(session: object, roster: Roster, *, read_at: datetime) -> tuple[()]:
        order.append("heads")
        raise RuntimeError("a unique index said no")

    monkeypatch.setattr(staff_sync_run, "read_members", read_members)
    monkeypatch.setattr(staff_sync_run, "read_last_applied", read_last_applied)
    monkeypatch.setattr(staff_sync_run, "write_application", write_application)
    monkeypatch.setattr(staff_sync_run, "run_row", lambda record: ("run", record))
    monkeypatch.setattr(staff_sync_run, "rewrite_head_audit_reach", failing)

    ran, _ = run(env=LARK_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")))
    assert order == ["roster", "heads"]
    assert ran.outcome is not None
    assert ran.outcome.value in {"applied", "unchanged"}


# ------------------------------------------------------------------------ the console path

#: Six entries, oldest first: two by the head's people about kinds a head reads, one by
#: somebody in another department, two by the head's people about kinds a head does not read,
#: and one by an administrator.
PLAN: Sequence[tuple[AuditAction, str, str, Mapping[str, object]]] = (
    (AuditAction.GRANT, "u_priya", "principal:u_sam", {"capability": "read:client.name"}),
    (AuditAction.LEASH_CHANGE, "u_wei", "agent:helper", {"target": "ticket.status"}),
    (AuditAction.GRANT, "u_sam", "principal:u_priya", {"capability": "read:client.name"}),
    (AuditAction.PUBLISH, "u_priya", "artifact:report_1", {}),
    (AuditAction.DENY, "u_wei", "connector:xero", {"reason": "no_grant"}),
    (AuditAction.SIGN_IN, "u_admin", "principal:u_wei", {"change": "bound"}),
)


def grants_written(session: HeadsSession) -> tuple[Grant, ...]:
    """What the rewrite's INSERT statements hold, read off the statements themselves."""
    return tuple(
        Grant(
            capability=Capability(value=params_of(one)["capability"]),
            scope=Scope.model_validate(params_of(one)["scope"]),
        )
        for one in session.written
        if isinstance(one, Insert)
    )


@contextmanager
def signed_in(grants: Mapping[str, tuple[Grant, ...]], ledger: Ledger) -> Iterator[TestClient]:
    """The real application, the token fixture's sign-in, these grants and this ledger."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer=ISSUER,
                audience=AUDIENCE,
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(grants),
            cache=NoCache(),
        )
        app.state.audit_ledger = ledger
        yield client


def menu_of(body: Mapping[str, Any]) -> list[tuple[str, list[str]]]:
    return [(one["heading"], [e["key"] for e in one["entries"]]) for one in body["sections"]]


def test_a_signed_in_head_reads_through_get_audit_exactly_their_peoples_entries() -> None:
    """**The read a department head makes.** The reach is what the rewrite wrote, read off its
    statements; the route is the application's own, with the screen's gate and `AuditView`
    inside it. Priya's and Wei's entries about kinds a head reads come back, newest first, and
    nothing by Sam, nothing of a kind a head does not read, and nothing by an administrator.
    The navigation offers the head their department's console with Audit under Govern.

    Delete this and the grants can be written, each correct, and open no screen and no menu
    entry, which is where every head stood until the plane was written beside the page."""
    session = HeadsSession()
    rewrite(session)
    ledger = Ledger(rows=[stored(one) for one in chain_of(PLAN)])
    with signed_in({HEAD: grants_written(session)}, ledger) as client:
        page = client.get(f"{API_PREFIX}/audit", headers=headers(HEAD))
        menu = client.get(f"{API_PREFIX}/console/navigation", headers=headers(HEAD))

    assert page.status_code == 200, page.text
    shown = [
        (one["actor_id"], f"{one['subject_kind']}:{one['subject_id']}")
        for one in page.json()["items"]
    ]
    assert shown == [("u_wei", "agent:helper"), ("u_priya", "principal:u_sam")]
    assert menu.status_code == 200, menu.text
    assert menu.json()["console"] == "department"
    assert menu.json()["departments"] == ["maintenance"]
    assert menu_of(menu.json()) == [("Govern", ["audit"])]


def test_a_reader_the_rewrite_wrote_nothing_for_is_refused_as_anybody_else_is() -> None:
    """The sibling: the same route and ledger, a person who is no head, refused with the one
    refusal every caller without the screen gets. Delete this and the test above is satisfied by
    a route that answers everybody."""
    ledger = Ledger(rows=[stored(one) for one in chain_of(PLAN)])
    with signed_in({"u_none": ()}, ledger) as client:
        refused = client.get(f"{API_PREFIX}/audit", headers=headers("u_none"))
    assert refused.status_code == 404
    assert "items" not in refused.json()


# ------------------------------------------------------------------------ against PostgreSQL


@contextmanager
def a_company(database: str) -> Iterator[str]:
    """Every migration to head, maintenance and web, the head and three people bound by email,
    the head leading maintenance, and one thing each person did filed under another person.
    Skips where the server has no pgvector, which CI has."""
    from tests.fixtures.retirable import has_pgvector, retirable

    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip(
                "the lead, role and grant tables need the whole chain, which needs pgvector"
            )
        seeded(url, lead="maintenance", addresses={**BOUND, HEAD_ADDRESS: HEAD})
        for actor, subject in (("u_priya", "u_sam"), ("u_wei", "u_priya"), ("u_sam", "u_wei")):
            sql(
                url,
                "INSERT INTO gate.role_grant (principal_id, role, granted_by, reason)"
                " VALUES (%s, 'member', %s, 'joined')",
                subject,
                actor,
            )
        yield url


def seeded(url: str, *, lead: str, addresses: Mapping[str, str]) -> None:
    """Departments with their scopes, a principal and an email binding per address, one lead."""
    for slug in ("maintenance", "web", "engineering", "finance"):
        sql(
            url,
            "INSERT INTO gate.scope (slug, predicate) VALUES (%s, %s)",
            slug,
            json.dumps({"department": slug}),
        )
        sql(
            url,
            "INSERT INTO gate.department (company_id, slug, name, scope_slug)"
            " VALUES ('c_1', %s, %s, %s)",
            slug,
            slug.title(),
            slug,
        )
    for address, pid in addresses.items():
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name)"
            " VALUES (%s, 'human', 'staff', %s)",
            pid,
            f"Person {pid}",
        )
        sql(
            url,
            "INSERT INTO auth.principal_identity (channel, identity_hash, principal_id, bound_at)"
            " VALUES (%s, %s, %s, now())",
            Channel.EMAIL.value,
            digest_of(address),
            pid,
        )
    sql(
        url,
        "INSERT INTO gate.department_lead (department_id, principal_id, appointed_by)"
        " SELECT id, %s, 'u_admin' FROM gate.department WHERE slug = %s",
        HEAD,
        lead,
    )


def app_role(url: str) -> Any:
    from tests.unit.test_automation_owner_store import app_engine

    return app_engine(url)


def night(url: str, source: Roster, at: datetime) -> tuple[Any, ...]:
    """One rewrite in its own transaction, as the application role, as the run makes it."""

    async def go() -> tuple[Any, ...]:
        engine = app_role(url)
        try:
            sessions = make_session_factory(engine)
            async with sessions() as session, session.begin():
                return await rewrite_head_audit_reach(session, source, read_at=at)
        finally:
            await engine.dispose()

    return run(go)


def live(url: str, principal_id: str = HEAD) -> dict[str, Scope]:
    """The live grants a sync wrote this principal, by capability."""
    rows = sql(
        url,
        "SELECT capability, scope FROM gate.capability_grant"
        " WHERE principal_id = %s AND deleted_at IS NULL AND granted_by LIKE 'roster.%%'",
        principal_id,
    )
    return {str(capability): Scope.model_validate(scope) for capability, scope in rows}


def recorded_by_the_sync(url: str) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (str(action), str(subject), dict(details))
        for action, subject, details in sql(
            url,
            "SELECT action, subject, details FROM obs.audit_entry WHERE actor_id = %s ORDER BY seq",
            GRANTOR,
        )
    ]


def as_the_head(url: str, at: datetime) -> tuple[EntitlementSet, tuple[AuditRow, ...]]:
    """The head's reach from the one resolver, and what the audit route's own reading gives them
    over the stored ledger, both as the application role."""

    async def go() -> tuple[EntitlementSet, tuple[AuditRow, ...]]:
        engine = app_role(url)
        try:
            sessions = make_session_factory(engine)
            reach = await StoredEntitlements(sessions).load(HEAD, at)
            page = await read_page(
                StoredLedger(sessions),
                lambda loaded: AuditView(loaded, reader=reach, now=at),
                AuditFilter(),
                limit=MAX_PAGE_SIZE,
                cursor=None,
                newest_first=True,
            )
            return reach, page.rows
        finally:
            await engine.dispose()

    return run(go)


def whose(rows: Sequence[AuditRow]) -> set[str]:
    """Whose actions the head was shown, leaving out the entries about the head themselves."""
    return {one.actor_id for one in rows if one.subject_id != HEAD}


#: The two grants that open the screen, as against the kinds that decide its rows.
SCREEN_CAPABILITIES = frozenset({AUDIT_PAGE_CAPABILITY.value, AUDIT_PLANE_CAPABILITY.value})


def expected(members: tuple[str, ...], department: str = "maintenance") -> dict[str, Scope]:
    """The five grants a head of this department holds over these people, by capability."""
    where = Clause(field="department", op=Op.EQ, value=department)
    return {
        one: Scope(clauses=(people(*members), where))
        if one in SCREEN_CAPABILITIES
        else Scope(clauses=(people(*members),))
        for one in FIVE
    }


@pytest.mark.needs_db
def test_through_the_database_a_transfer_and_a_leaver_rewrite_what_a_head_reads() -> None:
    """**The proof, on the tables.** Night one writes the five grants as the application role,
    the ledger accepts each under the roster's grantor, the resolver gives the head their people
    and the audit route's reading shows them Priya and Wei and never Sam. Night two, Wei has moved
    to Web: the five are retired and five naming Priya written, and Wei's entries are gone from
    the head's page. Night three, Priya has left: everything is retired and nothing written, and
    the head reads nobody. **Skips without a server.**

    Delete this and the statements can be refused by a trigger, a policy or a check on every
    install with every test over a stand-in green, which is exactly what happened: the grantor
    was spelled with a colon the ledger refuses, and the whole rewrite rolled back every night."""
    with a_company("brain_head_audit_nights") as url:
        night(url, MAINTENANCE, READ_AT)
        first = live(url)
        first_reach, first_rows = as_the_head(url, READ_AT + timedelta(hours=1))

        night(url, WEI_MOVED, READ_AT + SYNC_INTERVAL)
        second = live(url)
        _, second_rows = as_the_head(url, READ_AT + SYNC_INTERVAL + timedelta(hours=1))

        night(url, PRIYA_LEFT, READ_AT + 2 * SYNC_INTERVAL)
        third = live(url)
        _, third_rows = as_the_head(url, READ_AT + 2 * SYNC_INTERVAL + timedelta(hours=1))
        entries = recorded_by_the_sync(url)
        retired = sql(
            url,
            "SELECT count(*) FROM gate.capability_grant"
            " WHERE principal_id = %s AND deleted_at IS NOT NULL",
            HEAD,
        )

    assert first == expected(("u_priya", "u_wei"))
    assert permitted(screen("audit").read, first_reach, READ_AT + timedelta(hours=1))
    assert whose(first_rows) == {"u_priya", "u_wei"}

    assert second == expected(("u_priya",))
    assert whose(second_rows) == {"u_priya"}

    assert third == {}
    assert whose(third_rows) == set()
    assert retired == [(10,)]
    assert [action for action, _, _ in entries] == ["grant"] * 5 + ["revoke"] * 5 + [
        "grant"
    ] * 5 + ["revoke"] * 5


@pytest.mark.needs_db
def test_through_the_database_no_entry_the_rewrite_causes_records_a_department() -> None:
    """**Item 48's own condition, on the ledger.** Every entry the rewrite's grants and
    retirements append names the grant and never a department: no key, no value, no subject, and
    the ledger has no column to hold one. The department is on the page grant's scope, which the
    ledger does not copy. **Skips without a server.**

    Delete this and a trigger change that starts copying a grant's scope into its entry turns the
    audit trail into a record of which department each head's people were in, night by night,
    which is Option B arriving through a side door."""
    with a_company("brain_head_audit_no_department") as url:
        night(url, MAINTENANCE, READ_AT)
        night(url, WEI_MOVED, READ_AT + SYNC_INTERVAL)
        entries = recorded_by_the_sync(url)
        columns = sql(
            url,
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema = 'obs' AND table_name = 'audit_entry'",
        )

    assert len(entries) == 15
    for _, subject, details in entries:
        assert subject.startswith("grant:")
        assert "department" not in details
        for slug in ("maintenance", "web"):
            assert not re.search(rf"\b{slug}\b", json.dumps(details).casefold())
            assert not re.search(rf"\b{slug}\b", subject.casefold())
    assert "department" not in {str(one) for (one,) in columns}


@pytest.mark.needs_db
def test_through_the_database_an_unchanged_night_renews_the_rows_and_records_nothing() -> None:
    """The same people two nights running: the same five rows, their lapse moved one interval on,
    and no second grant in the ledger. **Skips without a server.** Delete this and an unchanged
    department either loses its reach at the lapse or fills the ledger with a revocation and a
    grant per head per night."""
    with a_company("brain_head_audit_renewal") as url:
        night(url, MAINTENANCE, READ_AT)
        before = sql(url, "SELECT id FROM gate.capability_grant WHERE deleted_at IS NULL")
        night(url, MAINTENANCE, READ_AT + SYNC_INTERVAL)
        after = sql(url, "SELECT id, not_after FROM gate.capability_grant WHERE deleted_at IS NULL")
        entries = recorded_by_the_sync(url)

    assert sorted(one for (one,) in before) == sorted(one for one, _ in after)
    assert {lapse for _, lapse in after} == {READ_AT + SYNC_INTERVAL + GRANT_LIFETIME}
    assert len(entries) == 5


@pytest.mark.needs_db
def test_through_the_database_a_former_head_and_a_head_who_left_keep_nothing() -> None:
    """Night one writes the head's grants; the lead is then ended and night two retires all five.
    The same again with the lead standing and the head marked as having left the staff list.
    **Skips without a server.** Delete this and a head stood down or gone keeps reading their old
    people until the lapse, because the rewrite only walks live leads."""
    with a_company("brain_head_audit_former") as url:
        night(url, MAINTENANCE, READ_AT)
        held = live(url)
        sql(
            url,
            "UPDATE gate.department_lead SET ended_at = now(), ended_by = 'u_admin'"
            " WHERE principal_id = %s",
            HEAD,
        )
        night(url, MAINTENANCE, READ_AT + SYNC_INTERVAL)
        stood_down = live(url)

    with a_company("brain_head_audit_left") as url:
        night(url, MAINTENANCE, READ_AT)
        again = live(url)
        sql(
            url,
            "INSERT INTO auth.staff_member (source, address_hash, display_name, first_listed_at,"
            " last_listed_at, left_at, left_because)"
            " VALUES (%s, %s, 'The head', now(), now(), now(), 'source_says_left')",
            SOURCE,
            digest_of(HEAD_ADDRESS),
        )
        night(url, MAINTENANCE, READ_AT + SYNC_INTERVAL)
        gone = live(url)

    assert sorted(held) == FIVE
    assert stood_down == {}
    assert sorted(again) == FIVE
    assert gone == {}


@pytest.mark.needs_db
def test_through_the_database_the_audit_route_answers_a_signed_in_head_their_people() -> None:
    """**The read a department head makes, on the tables.** Signed in through the token fixture,
    resolved by the one resolver over the grants night one wrote, answered by `GET /audit` over the
    stored ledger as the application role, and offered Audit on their department's console.
    **Skips without a server.** Delete this and the route and the rows can each be right in
    memory while the head's page is refused or empty on an install."""
    with a_company("brain_head_audit_route") as url:
        night(url, MAINTENANCE, READ_AT)

        async def go() -> tuple[int, dict[str, Any], dict[str, Any]]:
            engine = app_role(url)
            try:
                sessions = make_session_factory(engine)
                app = create_app(Settings(env="development"))
                app.state.gate = GateWiring(
                    authority=TokenAuthority(
                        issuer=ISSUER,
                        audience=AUDIENCE,
                        keys=Keys(),
                        verify=verifier,
                        directory=Directory(),
                    ),
                    versions=Versions(),
                    store=StoredEntitlements(sessions),
                    cache=NoCache(),
                )
                app.state.db_sessions = sessions
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://brain") as c:
                    page = await c.get(f"{API_PREFIX}/audit", headers=headers(HEAD))
                    menu = await c.get(f"{API_PREFIX}/console/navigation", headers=headers(HEAD))
                    return page.status_code, page.json(), menu.json()
            finally:
                await engine.dispose()

        status, page, menu = run(go)

    assert status == 200, page
    assert {one["actor_id"] for one in page["items"] if one["subject_id"] != HEAD} == {
        "u_priya",
        "u_wei",
    }
    assert "total" not in page
    assert menu["departments"] == ["maintenance"]
    assert ("Govern", ["audit"]) in menu_of(menu)


@pytest.mark.needs_db
def test_through_the_database_the_run_that_applies_the_staff_list_rewrites_the_head() -> None:
    """**The staff sync itself.** The head leads engineering. Night one reads the directory: Ada
    is in engineering, Grace has resigned, and the run that writes the staff list writes the
    head's grants over Ada alone. Night two Ada is gone from a complete list: the same run marks
    her as having left and retires the head's grants. **Skips without a server.**

    Delete this and the rewrite can be right when called and never called by the run, or called
    in a transaction the roster's failure takes with it."""
    from brain.identity.staff_roster import RunOutcome
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.unit.test_staff_sync_run import Directory as Lark
    from tests.unit.test_staff_sync_store import FIRST_NIGHT, SECOND_NIGHT, OnlyKatherine, sync

    staff = {
        "ada@example.com": "p_ada",
        "grace@example.com": "p_grace",
        "katherine@example.com": "p_katherine",
        HEAD_ADDRESS: HEAD,
    }
    with retirable("brain_head_audit_scheduled") as url:
        if not has_pgvector(url):
            pytest.skip("the lead and grant tables need the whole chain, which needs pgvector")
        seeded(url, lead="engineering", addresses=staff)
        first = sync(url, at=FIRST_NIGHT, fetch=Lark())
        after_first = live(url)
        second = sync(url, at=SECOND_NIGHT, fetch=OnlyKatherine())
        after_second = live(url)
        ada_left = sql(
            url,
            "SELECT left_because FROM auth.staff_member WHERE address_hash = %s",
            digest_of("ada@example.com"),
        )

    assert first.outcome is RunOutcome.APPLIED
    assert after_first == expected(("p_ada",), "engineering")
    assert second.outcome is RunOutcome.APPLIED
    assert ada_left == [("absent_from_complete_roster",)]
    assert after_second == {}
