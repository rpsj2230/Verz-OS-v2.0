"""The four govern screens over HTTP: who may open one, what each shows, and what may be written.

Driven through the real application. The token machinery, the identity directory and the key
source are imported from `tests/unit/test_api_routes.py` rather than rebuilt, for the reason
`tests/unit/test_routing_routes.py` gives about the same imports: what is under test is a
capability and not an identity, and a second copy of a JWS builder would be a second place for
a token to be minted subtly differently, producing failures that look like permission bugs.

**The database is a stub session and not a double for the grant tables.** This repository has
no PostgreSQL, so `async_sessionmaker(class_=...)` supplies a session whose `execute` returns a
canned result chosen by which table the statement names. That is honest about what it proves:
every refusal, the order the checks happen in, and the statements the routes compile are
exercised, and no SQL is run, so nothing here says a WHERE clause matches what PostgreSQL would
match, and nothing here says the audit trigger fired.

**Two refusals per screen and never one.** A guard tested only by its refusals is satisfied by
a route that refuses everybody, so every refusal below has a sibling proving the screen still
answers. The pair that matters most on these screens is the plane: a caller holding the
screen's tool capability and no console plane must be refused, and one holding both must not,
because a route written with `reach.holds(...)` passes the first half of every other test in
this file and answers an existence-only reader a configuration screen.

**The department-scoped reader is a person and not an assertion.** `u_elsewhere` holds every
capability `u_admin` does, narrowed to one department, and the tests ask what they are answered
rather than asserting that something was filtered. Two of the four screens narrow for them and
two do not, and both of those are deliberate: the vocabulary is answered whole or not at all,
because narrowing it to what a reader holds is
`govern.A_CATALOGUE_FILTERED_TO_THE_READER_IS_THEIR_OWN_ENTITLEMENT_RELABELLED`, and the role
catalogue is product documentation that `role_catalogue` cannot see a reader to narrow by.

**Six people and no seventh.** `token_for` mints tokens for the subjects `test_api_routes`
registers, so the personas here are those six with different grants. What that costs is that
one person plays several parts, and the way round it is the grant rows rather than the callers:
`u_admin` holds every screen capability and `read:invoice.total` nowhere, so the finance row is
a grant they may see and may not decide, which is `may_certify`'s third question asked without
a seventh token.

Task ids: M27.7.3, M27.7.4, M27.7.5, M27.7.6, M27.7.7
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.govern import VOCABULARY_SCREEN
from brain.console.reads import CONSOLE_CAPABILITY_PREFIX, Plane, plane_capability
from brain.console.scoped_authority import REACH_AUTHORITY
from brain.console.screens import screen
from brain.core.entitlement import CAPABILITY_RE, Capability, EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Clause, Op, Scope
from brain.govern_routes import (
    DEFAULT_PEOPLE_PER_PAGE,
    MAX_CAPABILITIES_PER_PAGE,
    PEOPLE_SCREEN,
    REASON_CHARS,
    ROLES_SCREEN,
    add_grant,
    live_assignments,
    live_departments,
    live_grants,
    one_live_grant,
    retire_grant,
)
from brain.identity.packs import SubjectGrant
from brain.identity.roles import ROLE_COUNT, ROLE_SPECS
from brain.identity.teams import PrincipalSubject
from brain.tables.audit import ACTOR_SETTING
from brain.tables.gate import (
    CapabilityGrantRow,
    CapabilityPackAssignmentRow,
    CapabilityPackRow,
    CapabilityRegistryRow,
    ScopeRow,
)
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

PEOPLE_PATH = f"{API_PREFIX}/govern/people"
ROLES_PATH = f"{API_PREFIX}/govern/roles"
CAPABILITIES_PATH = f"{API_PREFIX}/govern/capabilities"
SCOPES_PATH = f"{API_PREFIX}/govern/scopes"
GRANTS_PATH = f"{API_PREFIX}/govern/grants"
REMOVAL_PATH = f"{GRANTS_PATH}/removal"

#: Pinned far outside any plausible wall clock, deliberately, which is
#: `tests/unit/test_scope_and_capability.py`'s practice and `CLAUDE.md`'s rule about a fixture
#: with a date in it. Nothing in this file is about the present, so nothing in it should go red
#: at a particular hour of a particular day.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
FAR_OFF = datetime(2999, 1, 1, tzinfo=UTC)

MAINTENANCE = "maintenance"
FINANCE = "finance"

WHOLE = Scope.unrestricted()
IN_MAINTENANCE = Scope(clauses=(Clause(field="department", op=Op.EQ, value=MAINTENANCE),))
IN_FINANCE = Scope(clauses=(Clause(field="department", op=Op.EQ, value=FINANCE),))

#: The capability a grant is written of in these tests. An ordinary read over a business noun,
#: so that what is being checked is the granting rule rather than anything special about the
#: capability being granted.
GRANTED = "read:client.name"

#: An `amr` a Keycloak session carries when a second factor was used. A literal rather than a
#: value read out of `SECOND_FACTOR_METHODS`, for the reason `test_routing_routes.py` gives
#: about its own copy: reading the constant would compare it against itself.
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}


def _grant(value: str, scope: Scope) -> Grant:
    return Grant(capability=Capability(value=value), scope=scope)


def _configuration(scope: Scope = WHOLE) -> Grant:
    """The console plane every govern screen needs on top of its own capability."""
    return _grant(plane_capability(Plane.CONFIGURATION).value, scope)


#: What each of `test_api_routes`' six people holds here. Six personas and no seventh, because
#: `token_for` mints a token for the subjects that module registers and a directory of this
#: file's own would be a second place for a token to be minted subtly differently.
#:
#: Every screen's own capability is spelled out rather than read off the registry, because a
#: test reading `screen("people").read.requires` to build the grant it then asserts against
#: would be comparing the registry with itself: repointing the screen's capability would move
#: both sides and stay green.
GOVERN_GRANTS: dict[str, tuple[Grant, ...]] = {
    # Nobody. The refusal every screen gives.
    "u_none": (),
    # The console plane and no screen capability: the half that is usually forgotten.
    "u_prefix": (_configuration(),),
    # Every screen capability and no plane: the half a `reach.holds` check would let through.
    "u_narrow": (
        _grant("read:grant", WHOLE),
        _grant("read:role", WHOLE),
        _grant("read:capability", WHOLE),
        _grant("read:scope", WHOLE),
    ),
    # May see who holds what and may not name a capability, and may write nothing. The People
    # screen's two decisions pulled apart, which is what `govern.may_name_capabilities` is for,
    # and the caller every ordering test on the write path uses.
    "u_wide": (
        _grant("read:grant", WHOLE),
        _grant("read:role", WHOLE),
        _grant("read:scope", WHOLE),
        _configuration(),
    ),
    # Everything, company-wide, including the authority to write a grant and the one capability
    # these tests grant. Deliberately not `read:invoice.total`, so that the grant row sitting in
    # finance is one they may see and may not decide: `may_certify`'s third question needs
    # somebody holding the round and not the capability, and this is them.
    "u_admin": (
        _grant("read:grant", WHOLE),
        _grant("read:role", WHOLE),
        _grant("read:capability", WHOLE),
        _grant("read:scope", WHOLE),
        _grant(REACH_AUTHORITY.value, WHOLE),
        _grant(GRANTED, WHOLE),
        _configuration(),
    ),
    # The same person narrowed to one department. What they are answered less of is the
    # property two screens here are checked by, and what they may not write is the escalation.
    "u_elsewhere": (
        _grant("read:grant", IN_MAINTENANCE),
        _grant("read:role", IN_MAINTENANCE),
        _grant("read:capability", IN_MAINTENANCE),
        _grant("read:scope", IN_MAINTENANCE),
        _grant(REACH_AUTHORITY.value, IN_MAINTENANCE),
        _grant(GRANTED, IN_MAINTENANCE),
        _configuration(IN_MAINTENANCE),
    ),
}


class GovernStore:
    """A `brain.gate.resolve.EntitlementStore` over `GOVERN_GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GOVERN_GRANTS[principal_id])


# --------------------------------------------------------------------- the rows


def grant_row(
    *,
    principal_id: str,
    capability: str = GRANTED,
    scope: Scope = WHOLE,
    granted_by: str = "u_admin",
    not_after: datetime | None = None,
    row_id: uuid.UUID | None = None,
) -> CapabilityGrantRow:
    """One row of `gate.capability_grant`, built in memory.

    A real mapped row rather than a dictionary, so the loader is exercised against the
    attributes the route will actually read. Nothing is added to a session.
    """
    row = CapabilityGrantRow(
        id=row_id or uuid.uuid5(uuid.NAMESPACE_URL, f"{principal_id}/{capability}"),
        principal_id=principal_id,
        capability=capability,
        scope=scope.model_dump(),
        granted_by=granted_by,
        reason="because the job needs it",
        not_after=not_after,
    )
    row.created_at = LONG_AGO
    row.deleted_at = None
    return row


def pack_row(
    *, name: str = "maintenance_engineer", capabilities: Sequence[str]
) -> CapabilityPackRow:
    """One row of `gate.capability_pack`. The default name satisfies both grammars.

    `gate.capability_pack.name` is checked against a looser pattern than
    `CapabilityPack.slug`, so a name is a way of building a row the type refuses; the
    default here is deliberately one that both accept, and the test that needs the other
    kind asks for it by name.
    """
    row = CapabilityPackRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, name),
        name=name,
        description="what a maintenance engineer needs to do the job",
        capabilities=list(capabilities),
    )
    row.created_at = LONG_AGO
    row.deleted_at = None
    return row


def assignment_row(*, principal_id: str, pack: CapabilityPackRow) -> CapabilityPackAssignmentRow:
    row = CapabilityPackAssignmentRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"{principal_id}/{pack.name}"),
        principal_id=principal_id,
        pack_id=pack.id,
        scope=IN_MAINTENANCE.model_dump(),
        granted_by="u_admin",
        reason="joined the maintenance team",
        not_after=None,
    )
    row.created_at = LONG_AGO
    row.deleted_at = None
    return row


def scope_row(*, slug: str, predicate: dict[str, Any], is_department: bool = False) -> ScopeRow:
    row = ScopeRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, slug),
        slug=slug,
        predicate=predicate,
        is_department=is_department,
        label=slug.replace("-", " "),
    )
    row.created_at = LONG_AGO
    row.deleted_at = None
    return row


def registry_row(*, capability: str) -> CapabilityRegistryRow:
    row = CapabilityRegistryRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, capability),
        capability=capability,
        description=f"what {capability} reaches",
        required_by_tool=None,
    )
    row.created_at = LONG_AGO
    row.deleted_at = None
    return row


PACK = pack_row(capabilities=["read:ticket", "write:ticket"])

#: Two subjects in two departments, so a department-scoped reader is answered one of them.
MAINTENANCE_GRANT = grant_row(principal_id="u_1")
FINANCE_GRANT = grant_row(principal_id="u_2", capability="read:invoice.total")

#: A grant that has already lapsed. `SubjectGrant.is_active` drops it and `govern.people` asks.
LAPSED_GRANT = grant_row(
    principal_id="u_3",
    capability="read:client.contract_value",
    not_after=LONG_AGO + timedelta(days=1),
)


# ----------------------------------------------------------------- the stub session


class StubResult:
    """What `AsyncSession.execute` hands back, in the four shapes these routes read."""

    def __init__(self, rows: Sequence[Any]) -> None:
        self._rows = tuple(rows)

    def scalars(self) -> StubResult:
        return StubResult([row[0] if isinstance(row, tuple) else row for row in self._rows])

    def all(self) -> tuple[Any, ...]:
        return self._rows

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self) -> Any:
        if not self._rows:
            return None
        row = self._rows[0]
        return row[0] if isinstance(row, tuple) else row


class Executed:
    """What the stub answers each table, and every statement it was asked to run."""

    def __init__(self) -> None:
        self.grants: list[tuple[CapabilityGrantRow, str | None]] = [
            (MAINTENANCE_GRANT, MAINTENANCE),
            (FINANCE_GRANT, FINANCE),
        ]
        self.assignments: list[
            tuple[CapabilityPackAssignmentRow, CapabilityPackRow, str | None]
        ] = []
        self.scopes: list[ScopeRow] = []
        self.departments: list[str] = [MAINTENANCE, FINANCE]
        self.registry: list[CapabilityRegistryRow] = []
        self.written: CapabilityGrantRow | None = None
        self.retired: tuple[datetime] | None = None
        #: Set to raise from the insert, which is how a foreign key and a unique index both
        #: arrive: as an `IntegrityError` from the driver with a constraint name on it.
        self.integrity: bool = False
        self.statements: list[str] = []
        self.committed = 0
        self.rolled_back = 0

    def answer(self, sql: str) -> StubResult:
        """Which canned rows a statement gets, decided by the table it names.

        By table name rather than by call order, because the routes make two statements in one
        read and a fixture keyed on order is a fixture that silently answers the wrong table
        the day somebody reorders two lines.
        """
        if "capability_pack_assignment" in sql:
            return StubResult(self.assignments)
        if "capability_registry" in sql:
            return StubResult(self.registry)
        if "gate.department" in sql:
            return StubResult(self.departments)
        if "gate.scope" in sql:
            return StubResult(self.scopes)
        if sql.startswith("INSERT INTO gate.capability_grant"):
            return StubResult([] if self.written is None else [self.written])
        if sql.startswith("UPDATE gate.capability_grant"):
            return StubResult([] if self.retired is None else [self.retired])
        if "capability_grant" in sql:
            return StubResult(self.grants)
        return StubResult([])


_EXECUTED = Executed()


def _rendered(statement: Any, fallback: str) -> str:
    """One statement with its bound values in it, or its plain text when that cannot be done.

    The values matter here and nowhere else in this file: `set_config(:name, :value, true)`
    carries the actor's id in a bind parameter, so a recorder keeping only the statement's text
    records every write as attributable to nobody and the two attribution tests below pass for
    a route that never sets it. Compiling with literal binds is what puts the value back in the
    string; a statement that cannot be compiled that way, which is any insert carrying a JSONB
    dictionary, falls back to its text, which is all those tests ask of it.
    """
    try:
        return str(statement.compile(compile_kwargs={"literal_binds": True}))
    except Exception:
        return fallback


class StubSession(AsyncSession):
    """An `AsyncSession` that runs nothing and records everything.

    Subclassed rather than faked, so `sessions_of`'s `isinstance` check is satisfied by the
    real factory type. That check is not scaffolding: it is what stops a bare test application
    answering 500 from an `AttributeError` that reads like a bug in the gate.
    """

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        sql = str(statement)
        _EXECUTED.statements.append(_rendered(statement, sql))
        if _EXECUTED.integrity and sql.startswith("INSERT INTO gate.capability_grant"):
            raise IntegrityError("insert", None, Exception("uq_capability_grant_principal_id"))
        return _EXECUTED.answer(sql)

    async def commit(self) -> None:
        _EXECUTED.committed += 1

    async def rollback(self) -> None:
        _EXECUTED.rolled_back += 1

    async def close(self) -> None:
        return None


@pytest.fixture
def executed() -> Iterator[Executed]:
    """A fresh recorder per test, so one test's statements are never another's evidence."""
    global _EXECUTED
    _EXECUTED = Executed()
    yield _EXECUTED


def _wiring() -> Any:
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    return GateWiring(
        authority=TokenAuthority(
            issuer="https://id.verz.example/realms/brain",
            audience="brain-api",
            keys=Keys(),
            verify=verifier,
            directory=Directory(),
        ),
        versions=Versions(),
        store=GovernStore(),
        cache=NoCache(),
    )


@pytest.fixture
def client(executed: Executed) -> Iterator[TestClient]:
    """The real application, with a stub session factory where the pool would be.

    `create_app` produced everything else, including the router registration under test: a test
    that mounted the router itself would prove the routes work and not that they are served.
    """
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        # The lifespan built its console reads over whatever DATABASE_URL named, and CI names a
        # real database. Replacing the factory without them would read from there.
        app.state.console_reads = None
        yield c


@pytest.fixture
def unwired() -> Iterator[TestClient]:
    """The same application with no session factory, which is every deployment today."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = None
        app.state.console_reads = None
        yield c


def get(c: TestClient, path: str, pid: str, **params: Any) -> Response:
    token = token_for(pid, claims=SECOND_FACTOR)
    response: Response = c.get(
        path, headers={"authorization": f"Bearer {token}"}, params=params or {}
    )
    return response


def propose(
    c: TestClient,
    pid: str,
    *,
    body: Mapping[str, object] | None = None,
) -> Response:
    token = token_for(pid, claims=SECOND_FACTOR)
    response: Response = c.post(
        GRANTS_PATH,
        headers={"authorization": f"Bearer {token}"},
        json=dict(
            body
            or {
                "principal_id": "u_2",
                "capability": GRANTED,
                "scope_slug": MAINTENANCE,
                "reason": "covering the maintenance rota",
            }
        ),
    )
    return response


def remove(c: TestClient, pid: str, *, principal_id: str, capability: str) -> Response:
    token = token_for(pid, claims=SECOND_FACTOR)
    response: Response = c.post(
        REMOVAL_PATH,
        headers={"authorization": f"Bearer {token}"},
        json={"principal_id": principal_id, "capability": capability},
    )
    return response


# ------------------------------------------------------------- who may open a screen
@pytest.mark.parametrize(
    ("path", "pid"),
    [
        (PEOPLE_PATH, "u_none"),
        (PEOPLE_PATH, "u_prefix"),
        (PEOPLE_PATH, "u_narrow"),
        (ROLES_PATH, "u_none"),
        (ROLES_PATH, "u_prefix"),
        (ROLES_PATH, "u_narrow"),
        (SCOPES_PATH, "u_none"),
        (SCOPES_PATH, "u_prefix"),
        (SCOPES_PATH, "u_narrow"),
    ],
)
def test_a_govern_screen_needs_its_own_capability_and_the_console_plane_together(
    client: TestClient, path: str, pid: str
) -> None:
    """Both halves of `brain.console.reads.permitted`, asked of every screen that refuses.

    `u_narrow` is the case a route written with `reach.holds(...)` would answer: they hold
    `read:grant`, `read:role` and `read:scope` over everything and hold no console plane at
    all, which `Plane` exists to distinguish. `u_prefix` is the mirror.

    Delete this and the plane check can be dropped from every route in the module while every
    other test in this file stays green, because every other person here holds both."""
    response = get(client, path, pid)

    assert response.status_code == 404
    assert response.json()["message"] == Absent.public_message


@pytest.mark.parametrize("path", [PEOPLE_PATH, ROLES_PATH, SCOPES_PATH, CAPABILITIES_PATH])
def test_a_reader_holding_both_halves_is_answered_every_govern_screen(
    client: TestClient, path: str
) -> None:
    """The sibling of the refusals above, which a router that refused everybody would pass.

    Delete this and every assertion about a refusal in this file is satisfied by four routes
    that answer 404 to the entitled caller too."""
    assert get(client, path, "u_admin").status_code == 200


def test_a_refusal_names_the_screen_and_never_the_capability_it_wanted(
    client: TestClient,
) -> None:
    """The screen names are the console's own menu and the capability is not.

    `console/src/layout/Shell.tsx` lists every section to everybody and says why, so a body
    naming the screen discloses nothing this install has not already published. A body naming
    `read:grant` would name a capability to somebody who does not hold it, which is the
    vocabulary disclosed one refusal at a time.

    Delete this and the refusal grows the helpful sentence, which is the one that says which
    grant to ask for."""
    body = get(client, PEOPLE_PATH, "u_narrow").text

    assert "read:grant" not in body
    assert CONSOLE_CAPABILITY_PREFIX not in body


def test_a_caller_with_no_grant_cannot_tell_whether_this_process_has_a_database(
    unwired: TestClient,
) -> None:
    """The screen's question is asked before the wiring, so the two answers differ only for
    somebody already entitled to know.

    Driven against an application with no session factory, which is what every deployment of
    this system is today. Swap the two checks in `people_page` and the unentitled caller
    receives a 500, which says the screen would have been answered if only the database were up.

    Delete this and the order of two lines becomes a matter of taste, and the taste that reads
    better is the wrong one: reaching for the session first is the natural way to write it."""
    assert get(unwired, PEOPLE_PATH, "u_none").status_code == 404
    assert get(unwired, PEOPLE_PATH, "u_admin").status_code == 500
    assert get(unwired, SCOPES_PATH, "u_none").status_code == 404
    assert get(unwired, SCOPES_PATH, "u_admin").status_code == 500


def test_the_capability_catalogue_is_empty_rather_than_a_fault_for_a_reader_who_may_not_see_it(
    unwired: TestClient,
) -> None:
    """The one screen here whose refusal is an empty answer keeps the ordering property anyway.

    `govern.catalogue` returns an empty tuple rather than refusing, and its docstring says why.
    If the route loaded the registry first and asked afterwards, an unentitled caller would get
    an empty catalogue where there is a database and a 500 where there is not, which publishes
    the deployment's state to exactly the population the empty answer exists to tell nothing.

    Delete this and the early return in `capabilities` looks like a redundant check somebody
    can tidy away, and tidying it away is invisible on every other test in this file."""
    refused = get(unwired, CAPABILITIES_PATH, "u_none")

    assert refused.status_code == 200
    assert refused.json()["capabilities"] == []
    assert get(unwired, CAPABILITIES_PATH, "u_admin").status_code == 500


# ------------------------------------------------------------------ the people screen
def test_the_people_screen_lists_the_subjects_whose_rows_this_reader_reaches(
    client: TestClient,
) -> None:
    """A reader holding the screen's capability over everything sees both departments.

    Delete this and the positive half of every narrowing test below is gone: a route answering
    an empty page always would satisfy the department test underneath."""
    body = get(client, PEOPLE_PATH, "u_admin").json()

    assert [one["subject"] for one in body["items"]] == ["principal:u_1", "principal:u_2"]


def test_a_department_scoped_reader_is_answered_fewer_subjects_than_a_company_wide_one(
    client: TestClient,
) -> None:
    """The narrowing that makes M27.7.30's claim checkable, asked of a person rather than
    asserted of a function.

    `u_elsewhere` holds exactly what `u_admin` holds, narrowed to one department, and the grant rows
    sit in two. `govern.people` decides this through `_in_reach`; the route hands it every row
    it loaded and filters nothing itself.

    Delete this and the route can pass the loaded rows straight into the response, which is one
    line shorter and shows a finance grant to a maintenance admin."""
    wide = get(client, PEOPLE_PATH, "u_admin").json()
    narrow = get(client, PEOPLE_PATH, "u_elsewhere").json()

    assert [one["subject"] for one in wide["items"]] == ["principal:u_1", "principal:u_2"]
    assert [one["subject"] for one in narrow["items"]] == ["principal:u_1"]


def test_a_reader_who_may_not_name_capabilities_is_told_who_holds_something_and_not_what(
    client: TestClient,
) -> None:
    """The People screen's two decisions are separate and a reader can have one without the other.

    `u_wide` holds `read:grant` and not `read:capability`, so they see the subjects and an
    empty capability list; `u_admin` holds both. There is deliberately no third value saying
    which, and the assertion checks that too: a subject holding nothing and a subject whose
    capabilities were withheld produce an identical row.

    Delete this and the route can name capabilities to whoever may open the screen, which is a
    way of reading the Capabilities screen's contents without the Capabilities screen's grant."""
    withheld = get(client, PEOPLE_PATH, "u_wide").json()["items"]
    named = get(client, PEOPLE_PATH, "u_admin").json()["items"]

    assert [one["subject"] for one in withheld] == [one["subject"] for one in named]
    assert all(one["capabilities"] == [] for one in withheld)
    assert named[0]["capabilities"] == [GRANTED]
    assert set(withheld[0]) == {"subject", "capabilities"}


def test_a_capability_conferred_by_a_pack_is_on_the_people_screen(
    client: TestClient, executed: Executed
) -> None:
    """A pack assignment confers capabilities and the screen says so.

    The pack's two capabilities arrive through `brain.identity.packs.expand`, which is the only
    route from a pack to the grants it means, and they appear beside the direct grant on the
    same subject's row rather than as a second row about a bundle.

    Delete this and the People screen reads one table, shows a person holding one capability
    when they hold three, and the administrator looking at it writes the grant again."""
    executed.assignments = [(assignment_row(principal_id="u_1", pack=PACK), PACK, MAINTENANCE)]

    rows = get(client, PEOPLE_PATH, "u_admin").json()["items"]
    held = {one["subject"]: one["capabilities"] for one in rows}

    assert held["principal:u_1"] == sorted([GRANTED, "read:ticket", "write:ticket"])


def test_a_pack_the_type_refuses_is_skipped_rather_than_taking_the_screen_away(
    client: TestClient, executed: Executed
) -> None:
    """One unreadable row does not hide every other person from the administrator.

    `gate.capability_pack.name` admits a trailing underscore and `CapabilityPack.slug` does
    not, so a pack named that way is a row the column accepted and the type refuses. Answering
    500 for it would take the People screen away from exactly the person who could fix it, and
    nothing on the response says a row was skipped, because that is a count of what this reader
    was not shown.

    Delete this and one pack name takes down the screen an administrator opens to find out
    why."""
    refused = pack_row(name="maintenance_", capabilities=["read:ticket"])
    executed.assignments = [
        (assignment_row(principal_id="u_1", pack=refused), refused, MAINTENANCE)
    ]

    response = get(client, PEOPLE_PATH, "u_admin")

    assert response.status_code == 200
    assert [one["subject"] for one in response.json()["items"]] == [
        "principal:u_1",
        "principal:u_2",
    ]
    assert "read:ticket" not in response.text


def test_a_grant_that_has_lapsed_is_not_a_holding(client: TestClient, executed: Executed) -> None:
    """A row that confers nothing is absent rather than shown as expired.

    `SubjectGrant.is_active` is the single statement of whether a grant still confers, and
    `govern.people` asks it. The route loads the row regardless, which is the honest shape: a
    statement that filtered on `not_after` would be the route deciding what a holding is.

    Delete this and an access review shows a lapsed grant as standing access, which is the
    direction that gets somebody re-certified for something they have not had in a year."""
    executed.grants = [*executed.grants, (LAPSED_GRANT, MAINTENANCE)]

    rows = get(client, PEOPLE_PATH, "u_admin").json()["items"]

    assert [one["subject"] for one in rows] == ["principal:u_1", "principal:u_2"]


def test_a_grant_whose_subject_sits_nowhere_reaches_only_a_company_wide_reader(
    client: TestClient, executed: Executed
) -> None:
    """The fail-closed direction, asked of the one row that has no place at all.

    A grant whose principal row is missing or soft-deleted comes back from the outer join with
    no department, and `govern.NOWHERE` is the empty mapping: `Clause.matches` refuses a field
    that is not in the row, so such a grant satisfies no scoped grant and reaches only a reader
    whose own is company-wide. Both directions are asserted, because a row nobody can see is as
    wrong as one everybody can: it is a live grant an access review has to be able to find.

    Delete this and the conditional that builds `where` can be flattened to
    `{"department": department}`, which puts a null in the row rather than leaving the field
    out, and what a null matches is a question about `Clause` that nothing here would be
    asking."""
    executed.grants = [(grant_row(principal_id="u_7"), None)]

    wide = get(client, PEOPLE_PATH, "u_admin").json()["items"]
    narrow = get(client, PEOPLE_PATH, "u_elsewhere").json()["items"]

    assert [one["subject"] for one in wide] == ["principal:u_7"]
    assert narrow == []


def test_a_page_of_the_people_screen_carries_no_count_of_anything(client: TestClient) -> None:
    """`total` is inherited from `brain.api.Page` and never populated.

    Asserted over every key in the body rather than on `total` alone, because the failure is a
    number arriving under a different name: `count`, `withheld`, `subjects`. This collection is
    filtered per caller, so a count here is the subtraction `CLAUDE.md` forbids rather than a
    harmless footer.

    Delete this and the first person to want a footer adds `total=len(found)`, which is one
    word, and a maintenance admin learns how many grants exist in finance."""
    body = get(client, PEOPLE_PATH, "u_admin").json()

    assert body["total"] is None
    numbers = {
        key for key, value in body.items() if isinstance(value, int) and not isinstance(value, bool)
    }
    assert numbers == set(), f"a page carries a number of its own: {sorted(numbers)}"


def test_the_people_page_says_whether_this_caller_may_write_a_grant(client: TestClient) -> None:
    """`editable` is presentation, recomputed per request, and both directions are asserted.

    A flag that is always true and a flag that is always false each satisfy half of this.

    Delete this and `editable` can be hard-coded either way: false hides the grant form from
    the person who needs it, and true draws a form whose every submission is refused."""
    assert get(client, PEOPLE_PATH, "u_admin").json()["editable"] is True
    assert get(client, PEOPLE_PATH, "u_wide").json()["editable"] is False


def test_a_full_page_of_people_says_there_is_more_without_saying_how_much(
    client: TestClient,
) -> None:
    """`truncated` is the page having come back full, and it is a boolean.

    The stub answers two grant rows whatever the statement asked for, so what varies is the
    limit the caller sent and nothing else.

    Delete this and `truncated` can be computed against what `govern.people` returned, which is
    a count of what the decision withheld spelled as a flag."""
    assert get(client, PEOPLE_PATH, "u_admin", limit=2).json()["truncated"] is True
    assert get(client, PEOPLE_PATH, "u_admin", limit=3).json()["truncated"] is False


# ------------------------------------------------------------------- the roles screen
def test_the_roles_screen_answers_the_six_and_never_a_capability_beside_one(
    client: TestClient,
) -> None:
    """The catalogue is whole, and nothing on it puts a capability next to a role.

    `govern.GOVERN_SURFACES` states the rule for this exact screen: no role implies a
    capability, and a table that put the two side by side would be read as though one did. The
    assertion is over the response text rather than over a field list, because the failure is a
    capability arriving under any name at all.

    Delete this and somebody adds the capabilities a role is usually granted with, helpfully,
    and the console then documents an implication this system does not have."""
    body = get(client, ROLES_PATH, "u_admin").json()

    assert len(body["roles"]) == ROLE_COUNT
    assert {one["role"] for one in body["roles"]} == {one.value for one in ROLE_SPECS}
    # Over every string a role row carries rather than over a field list, because the failure is
    # a capability arriving under any name at all: permits, unlocks, usually_granted_with.
    for role in body["roles"]:
        for value in role.values():
            assert not CAPABILITY_RE.search(str(value)), value


def test_the_roles_screen_says_nothing_about_who_holds_one(client: TestClient) -> None:
    """There is no holder listing, because there is no table to build one from.

    `role_grant` is M1.3.2 and does not exist; `auth.directory_role_grant` records what a
    directory asserts, which is a different fact. The response says so in a field rather than
    leaving the absence to be read as an empty list.

    Delete this and the obvious next change is to read the directory table under this heading,
    which puts "the identity provider says so" and "somebody appointed them" under one word."""
    body = get(client, ROLES_PATH, "u_admin").json()

    assert body["holders_are_not_recorded_yet"] is True
    assert all("holders" not in one for one in body["roles"])


def test_the_role_catalogue_is_the_same_for_a_department_scoped_reader(
    client: TestClient,
) -> None:
    """One of the two screens here that does not narrow, and it is deliberate.

    What a role is for is product documentation: `role_catalogue` takes no entitlement at all
    and its docstring says that absence is the statement. A screen that showed a department
    admin four roles would be inventing a fact about the product from a fact about the reader.

    Delete this and somebody narrows this screen for symmetry with the other three."""
    assert (
        get(client, ROLES_PATH, "u_elsewhere").json() == get(client, ROLES_PATH, "u_admin").json()
    )


# ------------------------------------------------------------ the capability catalogue
def test_the_catalogue_names_a_capability_the_reader_does_not_hold(
    client: TestClient, executed: Executed
) -> None:
    """Whole, and never narrowed to what the reader themselves holds.

    This is the property the screen exists for and the one the attractive mistake breaks:
    showing somebody the capabilities they hold under a heading reading everything that can be
    granted discloses nothing and tells them the vocabulary is smaller than it is. `u_admin`
    holds none of the three registered capabilities below and is answered all three.

    Delete this and `catalogue` can be replaced by a comprehension over the reader's grants,
    which reads as a security improvement and is the collapse wearing the vocabulary's label."""
    executed.registry = [
        registry_row(capability="read:invoice.total"),
        registry_row(capability="admin:halt"),
        registry_row(capability="write:ticket"),
    ]

    body = get(client, CAPABILITIES_PATH, "u_admin").json()

    assert [one["capability"] for one in body["capabilities"]] == [
        "admin:halt",
        "read:invoice.total",
        "write:ticket",
    ]
    assert all(one["description"] for one in body["capabilities"])


def test_a_department_scoped_reader_is_answered_the_whole_catalogue(
    client: TestClient, executed: Executed
) -> None:
    """The second screen that does not narrow, and the reason is the same one again.

    The vocabulary is a fact about the install rather than about anybody's rows, so there is
    nothing in it for a department to be a subset of. A narrowed catalogue would make a
    department admin believe a capability they cannot grant does not exist.

    Delete this and somebody adds a scope filter here for consistency with People and Scopes."""
    executed.registry = [registry_row(capability="read:invoice.total")]

    assert (
        get(client, CAPABILITIES_PATH, "u_elsewhere").json()["capabilities"]
        == get(client, CAPABILITIES_PATH, "u_admin").json()["capabilities"]
    )


def test_a_reader_without_the_vocabulary_grant_is_answered_an_empty_catalogue(
    client: TestClient, executed: Executed
) -> None:
    """Empty rather than refused, which is `catalogue`'s own decision and not this route's.

    Paired with the test above, because a route that answered everybody an empty catalogue
    would pass this one alone.

    Delete this and the route can refuse instead, which draws a lock on a screen `navigation`
    has already left out of that person's menu."""
    executed.registry = [registry_row(capability="read:invoice.total")]

    assert get(client, CAPABILITIES_PATH, "u_wide").json()["capabilities"] == []
    assert get(client, CAPABILITIES_PATH, "u_admin").json()["capabilities"] != []


def test_a_registry_larger_than_the_screen_can_answer_whole_is_a_fault_and_not_a_short_list(
    client: TestClient, executed: Executed
) -> None:
    """A truncated catalogue is the one shape this screen must never take.

    The bound exists so that one statement cannot be unbounded, and the answer to hitting it is
    a fault rather than a page: a reader shown the first two thousand of a larger vocabulary,
    with no count and no cursor, has been told the vocabulary is smaller than it is, which is
    the same lie a filtered catalogue tells.

    Delete this and the bound becomes a silent `LIMIT` and the screen starts lying at 2001."""
    executed.registry = [
        registry_row(capability=f"read:thing_{index}")
        for index in range(MAX_CAPABILITIES_PER_PAGE + 1)
    ]

    assert get(client, CAPABILITIES_PATH, "u_admin").status_code == 500


# ------------------------------------------------------------------ the scopes screen
def test_the_scopes_screen_shows_a_predicate_whole_or_not_at_all(
    client: TestClient, executed: Executed
) -> None:
    """A scope row carries its predicate, because the name is the predicate in other words.

    `govern_surfaces.A_SCOPE_NAME_IS_THE_PREDICATE_SPELLED_IN_WORDS` is the argument: a row
    with the predicate blanked is a row whose name already said it.

    Delete this and somebody redacts the predicate for a reader who may see the row, which
    reads as caution and shows them a name with nothing behind it."""
    executed.scopes = [
        scope_row(slug=MAINTENANCE, predicate={"department": MAINTENANCE}, is_department=True)
    ]

    rows = get(client, SCOPES_PATH, "u_admin").json()["items"]

    assert [one["slug"] for one in rows] == [MAINTENANCE]
    assert rows[0]["scope"]["clauses"] == [
        {"field": "department", "op": "eq", "value": MAINTENANCE}
    ]
    assert rows[0]["is_department"] is True


def test_a_department_scoped_reader_sees_fewer_scopes_and_fewer_department_options(
    client: TestClient, executed: Executed
) -> None:
    """Both halves of this screen narrow for the same person, by two different tests.

    The rows narrow by `scope_rows`, which is containment through
    `scoped_authority.within_reach`; the filter options narrow by `departments_offered`, which
    is `admits_department` and then `screens.offerable`. A screen that narrowed the rows and
    not the dropdown would hand a maintenance admin the company's department list, which is
    `A_LISTING_OF_DEPARTMENTS_IS_AN_ORG_CHART_A_REFUSAL_HANDED_OVER`.

    Delete this and the dropdown becomes every department in the install, which is the org
    chart published to whoever may open the screen at all."""
    executed.scopes = [
        scope_row(slug=MAINTENANCE, predicate={"department": MAINTENANCE}, is_department=True),
        scope_row(slug=FINANCE, predicate={"department": FINANCE}, is_department=True),
    ]

    wide = get(client, SCOPES_PATH, "u_admin").json()
    narrow = get(client, SCOPES_PATH, "u_elsewhere").json()

    assert [one["slug"] for one in wide["items"]] == [MAINTENANCE, FINANCE]
    assert [one["slug"] for one in narrow["items"]] == [MAINTENANCE]
    assert list(wide["departments"]) == [MAINTENANCE, FINANCE]
    assert list(narrow["departments"]) == [MAINTENANCE]


def test_a_scope_row_that_does_not_construct_is_skipped_and_not_a_fault(
    client: TestClient, executed: Executed
) -> None:
    """One broken row does not take the screen away from the person who came to fix it.

    `ScopeRecord` refuses a predicate that can match nothing, and a row like that in the table
    is a configuration fault. Answering 500 would hide every other scope behind it, and nothing
    on the response says one was skipped, because a count of skipped rows is a count of rows
    this reader was not shown.

    Delete this and one hand-written UPDATE against `gate.scope` takes the whole screen down."""
    executed.scopes = [
        scope_row(slug="broken", predicate={"department": []}),
        scope_row(slug=MAINTENANCE, predicate={"department": MAINTENANCE}, is_department=True),
    ]

    body = get(client, SCOPES_PATH, "u_admin").json()

    assert [one["slug"] for one in body["items"]] == [MAINTENANCE]
    assert "broken" not in get(client, SCOPES_PATH, "u_admin").text


# ------------------------------------------------------------------------ granting
def test_a_grantor_may_write_a_grant_inside_the_scope_they_hold(
    client: TestClient, executed: Executed
) -> None:
    """The positive case, which a route refusing everybody would otherwise satisfy.

    The answer is built from the row the stub says the database returned rather than from the
    request, which is why `written` carries a different reason from the one posted: what comes
    back is what is stored.

    Delete this and every refusal test below is satisfied by a route that refuses every write."""
    executed.scopes = [
        scope_row(slug=MAINTENANCE, predicate={"department": MAINTENANCE}, is_department=True)
    ]
    executed.written = grant_row(principal_id="u_2", scope=IN_MAINTENANCE, granted_by="u_admin")

    response = propose(client, "u_admin")

    assert response.status_code == 201
    assert response.json()["granted_by"] == "u_admin"
    assert response.json()["capability"] == GRANTED
    assert executed.committed == 1


def test_a_grantor_may_not_write_a_grant_wider_than_the_scope_they_hold(
    client: TestClient, executed: Executed
) -> None:
    """The one escalation an additive model cannot undo, refused at the route.

    `u_elsewhere` holds the authority and the capability in one department and proposes a
    grant at a company-wide scope. `scoped_authority.may_grant` refuses it; nothing here
    re-implements that, and the refusal reaches the caller as the ordinary sentence.

    Delete this and the route can call `add_grant` with whatever `proposal_from` built, which
    writes a company-wide grant from a department admin and nothing ever takes it back."""
    executed.scopes = [scope_row(slug="everywhere", predicate={})]
    executed.written = grant_row(principal_id="u_2")

    response = propose(
        client,
        "u_elsewhere",
        body={
            "principal_id": "u_2",
            "capability": GRANTED,
            "scope_slug": "everywhere",
            "reason": "covering the rota",
        },
    )

    assert response.status_code == 404
    assert response.json()["message"] == Absent.public_message
    assert executed.committed == 0


def test_a_grantor_may_not_write_a_capability_they_do_not_hold_themselves(
    client: TestClient, executed: Executed
) -> None:
    """`may_grant`'s second question, which is a different capability from its first.

    `u_admin` holds `approve:grant` over everything and holds `read:invoice.total` nowhere, so
    they may run a review and may not create that reach. The two are separate questions and a
    route asking only the first would let anybody with review authority grant anything.

    Delete this and the authority to review becomes the authority to grant, which is the
    quietest privilege escalation this system has."""
    executed.scopes = [
        scope_row(slug=MAINTENANCE, predicate={"department": MAINTENANCE}, is_department=True)
    ]
    executed.written = grant_row(principal_id="u_2")

    response = propose(
        client,
        "u_admin",
        body={
            "principal_id": "u_2",
            "capability": "read:invoice.total",
            "scope_slug": MAINTENANCE,
            "reason": "covering the rota",
        },
    )

    assert response.status_code == 404
    assert executed.committed == 0


def test_a_scope_slug_nothing_matches_is_the_same_refusal_as_one_out_of_reach(
    client: TestClient, executed: Executed
) -> None:
    """Two outcomes and one answer, which is what stops this route enumerating the scopes.

    A slug naming no live row and a slug naming a row this grantor could not write at produce
    the same status and the same body. If they differed, a grantor could ask for slugs one at a
    time and learn which scopes exist without ever being shown one.

    Delete this and the route grows a helpful 404 saying the scope was not found, which is the
    one that tells you when it was."""
    executed.scopes = []
    absent = propose(
        client,
        "u_admin",
        body={
            "principal_id": "u_2",
            "capability": GRANTED,
            "scope_slug": "no-such-scope",
            "reason": "covering the rota",
        },
    )

    executed.scopes = [
        scope_row(slug=FINANCE, predicate={"department": FINANCE}, is_department=True)
    ]
    out_of_reach = propose(
        client,
        "u_elsewhere",
        body={
            "principal_id": "u_2",
            "capability": GRANTED,
            "scope_slug": FINANCE,
            "reason": "covering the rota",
        },
    )

    assert absent.status_code == out_of_reach.status_code == 404
    # The message and not the whole body; see the removal's own version of this test.
    assert absent.json()["message"] == out_of_reach.json()["message"] == Absent.public_message


def test_a_constraint_refusing_the_write_is_answered_as_the_ordinary_refusal(
    client: TestClient, executed: Executed
) -> None:
    """A foreign key and a unique index are both facts about somebody else.

    An unknown principal and a subject who already holds the capability arrive identically,
    through the driver, with a constraint name attached. Answering 500 would put that name in
    front of a caller who may not know either fact, and the difference between the two answers
    would be a probe for whether a person exists.

    Delete this and a grant form becomes a way to test whether a principal id is real, one
    submission at a time, reading the answer off the status code."""
    executed.scopes = [
        scope_row(slug=MAINTENANCE, predicate={"department": MAINTENANCE}, is_department=True)
    ]
    executed.integrity = True

    response = propose(client, "u_admin")

    assert response.status_code == 404
    assert response.json()["message"] == Absent.public_message
    assert "constraint" not in response.text.lower()
    assert executed.rolled_back == 1


def test_a_caller_who_may_not_grant_never_reaches_the_database(
    unwired: TestClient, client: TestClient, executed: Executed
) -> None:
    """The ordering property again, on the write path, where the refusal is not a screen's.

    Against an application with no session factory, a caller with no grant authority gets the
    ordinary refusal and one with it gets the process fault. And against the wired application
    the unentitled caller runs no statement at all, which is the same property read from the
    other side.

    Delete this and the scope lookup moves above the authority check, which reads better and
    lets anybody with a token ask whether this process has a database."""
    assert propose(unwired, "u_wide").status_code == 404
    assert propose(unwired, "u_admin").status_code == 500

    propose(client, "u_wide")
    assert executed.statements == []


def test_a_body_carrying_a_predicate_or_a_granter_is_refused_rather_than_ignored(
    client: TestClient,
) -> None:
    """`extra="forbid"` on `GrantProposal`, which is what makes the absent fields an answer.

    A body naming `granted_by` would otherwise be dropped silently and the console would
    believe it had attributed the grant; a body naming `scope` would be dropped and the console
    would believe it had narrowed one.

    Delete this and both keys become values a browser can send that nothing reads, which is the
    shape where a form looks like it works and writes something else."""
    for key, value in (("granted_by", "u_1"), ("scope", {"clauses": []})):
        response = propose(
            client,
            "u_admin",
            body={
                "principal_id": "u_2",
                "capability": GRANTED,
                "scope_slug": MAINTENANCE,
                "reason": "covering the rota",
                key: value,
            },
        )
        assert response.status_code == 422, key


def test_a_malformed_capability_is_refused_before_anything_is_decided(
    client: TestClient, executed: Executed
) -> None:
    """The grammar is on the field, so a bad one is a 422 naming it rather than a 500.

    `Capability` refuses the value either way. Doing it on the model means the caller is told
    which field was wrong, and it means a `ValidationError` from inside `proposal_from` is not
    the thing that reaches `handle_brain_error`.

    Delete this and a typo in a capability box answers "Something went wrong.\""""
    response = propose(
        client,
        "u_admin",
        body={
            "principal_id": "u_2",
            "capability": "not a capability",
            "scope_slug": MAINTENANCE,
            "reason": "covering the rota",
        },
    )

    assert response.status_code == 422
    assert executed.statements == []


def test_the_reason_bound_is_the_bound_the_grant_model_declares(client: TestClient) -> None:
    """A copy, checked against the original rather than against itself.

    `REASON_CHARS` is restated on the route so an over-long reason is a 422 naming the field.
    Read off `SubjectGrant`'s own field rather than typed twice, so widening one and not the
    other fails here instead of producing a 500 from inside the model.

    Delete this and the two numbers drift, and the shorter one is whichever nobody updated."""
    declared = SubjectGrant.model_fields["reason"].metadata

    assert REASON_CHARS in [getattr(one, "max_length", None) for one in declared]


# ------------------------------------------------------------------------ removing
def test_a_reviewer_may_remove_a_grant_their_own_scope_and_capability_admit(
    client: TestClient, executed: Executed
) -> None:
    """The positive case for the removal, which every refusal below would otherwise satisfy.

    `u_admin` holds the review authority and the capability the stored grant confers, over
    everything, and the grant's subject is somebody else.

    Delete this and a route that refuses every removal passes the whole of the rest of this
    section."""
    executed.retired = (FAR_OFF,)

    response = remove(client, "u_admin", principal_id="u_1", capability=GRANTED)

    assert response.status_code == 200
    assert response.json()["principal_id"] == "u_1"
    assert response.json()["capability"] == GRANTED
    assert executed.committed == 1


def test_a_reviewer_may_not_remove_a_grant_whose_capability_they_do_not_hold(
    client: TestClient, executed: Executed
) -> None:
    """`may_certify`'s third question: an admin may not decide what they could not have granted.

    `u_admin` holds `approve:grant` over everything and holds `read:invoice.total` nowhere, so
    the round is theirs and the finance grant is not. Removal is the safe direction and it is
    still refused, because the same authority that removes a grant confirms one, and a
    confirmation is the grant made again by somebody it was never theirs to make.

    Delete this and review authority alone becomes authority over every grant in the install."""
    executed.grants = [(FINANCE_GRANT, FINANCE)]
    executed.retired = (FAR_OFF,)

    refused = remove(client, "u_admin", principal_id="u_2", capability="read:invoice.total")

    assert refused.status_code == 404
    assert executed.committed == 0


def test_nobody_may_remove_their_own_grant(client: TestClient, executed: Executed) -> None:
    """A certification of your own grant is a self-grant with a round attached.

    The row below is a grant of `GRANTED` to `u_admin`, who holds the review authority and that
    capability over everything, so every question `may_certify` asks is answered yes and the
    only thing standing in their way is that they are its subject. `Certification` refuses it in
    its constructor, which is where that rule lives so a hand-built object cannot go round it,
    and the route does not ask this question itself and must not start.

    Delete this and the one decision an access review exists to catch is the one it permits."""
    own = grant_row(principal_id="u_admin")
    executed.grants = [(own, MAINTENANCE)]
    executed.retired = (FAR_OFF,)

    refused = remove(client, "u_admin", principal_id="u_admin", capability=GRANTED)

    assert refused.status_code == 404
    assert executed.committed == 0


def test_a_grant_that_is_not_there_is_the_same_refusal_as_one_out_of_reach(
    client: TestClient, executed: Executed
) -> None:
    """The oracle this route would otherwise be, closed by one answer for both.

    An id matching no live row and an id matching a row this caller may not decide produce the
    same status and the same body. Any difference between them answers "does this grant exist"
    for anybody able to type a uuid.

    Delete this and the removal button becomes a way to enumerate grant ids."""
    executed.grants = []
    absent = remove(client, "u_admin", principal_id="u_9", capability=GRANTED)

    executed.grants = [(FINANCE_GRANT, FINANCE)]
    out_of_reach = remove(client, "u_admin", principal_id="u_2", capability="read:invoice.total")

    assert absent.status_code == out_of_reach.status_code == 404
    # The message and not the whole body: every response carries its own trace id, which is the
    # one field two requests differ in by construction.
    assert absent.json()["message"] == out_of_reach.json()["message"] == Absent.public_message


def test_a_capability_that_came_from_a_pack_is_not_removable_here(
    client: TestClient, executed: Executed
) -> None:
    """The gap this screen has, asserted so that it is a decision rather than a surprise.

    A pack's capability is on the People screen and there is no grant row behind it, so the
    removal finds nothing and refuses in the ordinary words. That is the right refusal and not
    a bug: removing it means removing the assignment, which takes away everything else in the
    pack at the same time, and the refusal says nothing about which of a subject's capabilities
    arrived that way, because that would be a fact about somebody else's access.

    Delete this and somebody makes the removal fall back to the assignment table, helpfully,
    and one click takes away eleven capabilities the person clicking was shown one of."""
    executed.assignments = [(assignment_row(principal_id="u_1", pack=PACK), PACK, MAINTENANCE)]
    executed.grants = []
    executed.retired = (FAR_OFF,)

    shown = get(client, PEOPLE_PATH, "u_admin").json()["items"]
    refused = remove(client, "u_admin", principal_id="u_1", capability="read:ticket")

    assert "read:ticket" in shown[0]["capabilities"]
    assert refused.status_code == 404
    assert refused.json()["message"] == Absent.public_message
    assert executed.committed == 0


def test_a_caller_who_may_not_review_never_reaches_the_database(
    unwired: TestClient, client: TestClient, executed: Executed
) -> None:
    """The ordering property on the removal path.

    Delete this and the row is loaded before the authority is asked, which tells anybody with a
    token whether this process has a database."""
    unentitled = remove(unwired, "u_wide", principal_id="u_1", capability=GRANTED)
    entitled = remove(unwired, "u_admin", principal_id="u_1", capability=GRANTED)

    assert unentitled.status_code == 404
    assert entitled.status_code == 500

    remove(client, "u_wide", principal_id="u_1", capability=GRANTED)
    assert executed.statements == []


# ----------------------------------------------------------------- the attribution
def test_both_writes_name_the_actor_to_the_transaction_before_they_write(
    client: TestClient, executed: Executed
) -> None:
    """The audit trigger cannot work out who revoked a grant, so the application says.

    `gate.record_entitlement_change` falls back to `granted_by` when nothing set
    `brain.actor_id`, and `brain.tables.audit` says why that is a fallback rather than an
    answer: nothing on the row records who removed it. Asserted as an order rather than as a
    presence, because a `set_config` issued after the write is a setting the trigger has
    already run without.

    Delete this and every removal in the ledger is attributed to whoever made the grant, which
    is a record of the wrong person deciding."""
    executed.scopes = [
        scope_row(slug=MAINTENANCE, predicate={"department": MAINTENANCE}, is_department=True)
    ]
    executed.written = grant_row(principal_id="u_2", scope=IN_MAINTENANCE, granted_by="u_admin")
    propose(client, "u_admin")

    settings = [index for index, sql in enumerate(executed.statements) if ACTOR_SETTING in sql]
    writes = [
        index
        for index, sql in enumerate(executed.statements)
        if sql.startswith("INSERT INTO gate.capability_grant")
    ]
    assert settings and writes and settings[0] < writes[0]

    executed.statements.clear()
    executed.retired = (FAR_OFF,)
    remove(client, "u_admin", principal_id="u_1", capability=GRANTED)

    settings = [index for index, sql in enumerate(executed.statements) if ACTOR_SETTING in sql]
    writes = [
        index
        for index, sql in enumerate(executed.statements)
        if sql.startswith("UPDATE gate.capability_grant")
    ]
    assert settings and writes and settings[0] < writes[0]


def test_the_actor_is_the_caller_and_never_the_body(client: TestClient, executed: Executed) -> None:
    """Who made the write comes from the token, so a browser cannot name somebody else.

    Both writes, and the removal is the one that was missing until a mutation found it. Setting
    the actor to `body.principal_id` there survived every other test in this file, and it is the
    worst version of this defect available: the audit entry for a revocation would name the
    person whose access was taken away as the person who took it, which is a record that looks
    complete and accuses the wrong party. The subject and the caller are different people in
    both halves below, so the assertion cannot pass by them being the same string.

    Delete this and `granted_by` becomes a field a console could send, and a grant is
    attributable to whoever the person writing it chose to blame."""
    executed.scopes = [
        scope_row(slug=MAINTENANCE, predicate={"department": MAINTENANCE}, is_department=True)
    ]
    executed.written = grant_row(principal_id="u_2", scope=IN_MAINTENANCE, granted_by="u_admin")

    propose(client, "u_admin")

    named = [sql for sql in executed.statements if ACTOR_SETTING in sql]
    assert named
    assert all("u_admin" in sql for sql in named)
    assert not any("u_2" in sql for sql in named)

    executed.statements.clear()
    executed.retired = (FAR_OFF,)
    remove(client, "u_admin", principal_id="u_1", capability=GRANTED)

    named = [sql for sql in executed.statements if ACTOR_SETTING in sql]
    assert named
    assert all("u_admin" in sql for sql in named)
    assert not any("u_1" in sql for sql in named)


# ------------------------------------------------------------------ the statements
def test_every_listing_reads_live_rows_only(client: TestClient) -> None:
    """`deleted_at IS NULL` in the statement as well as in the row-level policy.

    Compiled and read as SQL, because a stub session runs nothing and could answer any
    statement at all. The reason for writing it twice is the one `live_rungs` gives: a
    statement whose correctness depends on a policy being installed is wrong on a database
    restored without one.

    Delete this and a retired grant reappears on the People screen the day somebody restores a
    database without its policies, which is the day nobody is checking."""
    for statement in (
        live_grants(DEFAULT_PEOPLE_PER_PAGE),
        live_assignments(DEFAULT_PEOPLE_PER_PAGE),
        live_departments(10),
        one_live_grant("u_1", GRANTED),
    ):
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        assert "deleted_at IS NULL" in sql


def test_the_people_load_keeps_a_grant_whose_principal_row_is_missing(client: TestClient) -> None:
    """An outer join, so a grant with no department is a row with no place rather than no row.

    `govern.NOWHERE` is the empty mapping and `Clause.matches` refuses a field that is not in
    the row, so such a grant reaches only a company-wide reader. That is the fail-closed
    direction. An inner join would drop the row instead, which also fails closed and does it
    where nobody can see: the grant is then invisible to an access review as well.

    Delete this and the join tightens to an inner one, reasonably, and a grant belonging to a
    soft-deleted principal stops appearing anywhere a person could remove it."""
    sql = str(live_grants(DEFAULT_PEOPLE_PER_PAGE).compile(compile_kwargs={"literal_binds": True}))

    assert "LEFT OUTER JOIN auth.principal" in sql


def test_the_removal_touches_only_the_deleted_at_column(client: TestClient) -> None:
    """The SET list is one column and the WHERE clause keeps a retired grant retired.

    Read off the compiled statement rather than off the route, so this is the statement being
    checked rather than a description of it. The second `deleted_at IS NULL` is what makes a
    second removal write nothing and answer identically to a first one against an unknown id.

    Delete this and the update can grow a `reason` or a `not_after`, which is an edit to a
    grant wearing a removal's name, and the audit entry still says revoke.

    And the stamp is the statement's own. This asserted a bound `deleted_at` until 2026-09-17,
    which was the request's instant, and `0045`'s policies refuse that as `brain_app`: the test
    held the defect in place."""
    statement = retire_grant("u_1", GRANTED)
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "deleted_at" not in statement.compile().binds
    # The SET list read off the compiled statement rather than described: `deleted_at`, and the
    # `updated_at` `TimestampMixin` maintains on every update. A third column here would be an
    # edit to a grant wearing a removal's name, with the audit entry still reading revoke.
    assigned = sql.split("SET")[1].split("WHERE")[0]
    assert sorted(one.strip() for one in assigned.split(",")) == [
        "deleted_at=statement_timestamp()",
        "updated_at=now()",
    ]
    assert "deleted_at IS NULL" in sql


def test_the_insert_does_not_name_the_instant_it_was_written(client: TestClient) -> None:
    """`created_at` is the database's clock and is deliberately absent from the values.

    `TimestampMixin` exists so that the time on a row comes from one clock rather than from
    whichever container handled the write. A route passing its own `now` would put the
    application's clock in a column an audit reads.

    Delete this and `granted_at` becomes a value the request's instant decides, and two
    containers with drifting clocks write grants that sort wrongly against each other."""
    proposed = SubjectGrant(
        subject=PrincipalSubject(principal_id="u_2"),
        capability=Capability(value=GRANTED),
        scope=IN_MAINTENANCE,
        granted_by="u_admin",
        reason="covering the rota",
        granted_at=LONG_AGO,
    )
    statement = add_grant(proposed, "u_2")
    named = set(statement.compile().binds)

    assert "created_at" not in named
    assert "granted_at" not in named
    assert {"principal_id", "capability", "scope", "granted_by", "reason"} <= named


# ------------------------------------------------------------------------ the wiring
def test_every_govern_route_refuses_a_request_carrying_no_credential(
    client: TestClient,
) -> None:
    """The gate is on these as it is on everything else under the prefix.

    `test_every_route_under_the_prefix_authenticates_its_caller` asserts this over the mounted
    set and would catch it too; it is here as well because that test drives GET only, and the
    two writes here are routes somebody can add with the dependency left off.

    Delete this and the grant route is the one that gets mounted without `Asked`."""
    for path in (PEOPLE_PATH, ROLES_PATH, CAPABILITIES_PATH, SCOPES_PATH):
        assert client.get(path).status_code == 401
    assert client.post(GRANTS_PATH, json={}).status_code == 401
    assert client.post(REMOVAL_PATH, json={}).status_code == 401


def test_the_govern_screens_are_absent_from_the_publicly_served_document() -> None:
    """These routes describe the permission system, so they stay out of the public schema.

    Delete this and a router mounted at the root publishes the shape of this company's
    governance to anybody who asks for the document."""
    from brain.openapi import public_operations

    app: FastAPI = create_app(Settings(env="production"))

    for path in public_operations(app):
        assert "govern" not in path


def test_the_screens_this_router_serves_are_the_keys_the_registry_holds() -> None:
    """The three screen keys are pinned against the registry rather than derived from it.

    Written out in the module and compared here, which is the construction
    `scoped_authority.REACH_AUTHORITY` argues for: read off the registry on both sides, the
    comparison would be a constant against itself and repointing a key would move both.

    Delete this and `PEOPLE_SCREEN` can be repointed at a screen with a different capability
    and a different plane, and every narrowing test in this file follows it there."""
    assert screen(PEOPLE_SCREEN).read.requires == Capability(value="read:grant")
    assert screen(ROLES_SCREEN).read.requires == Capability(value="read:role")
    assert screen(VOCABULARY_SCREEN).read.requires == Capability(value="read:capability")
    assert screen(PEOPLE_SCREEN).read.plane is Plane.CONFIGURATION
