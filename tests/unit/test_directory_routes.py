"""The People directory, one person's page, and a person added by hand, over HTTP and a database.

Driven through the real application with the people signed in by `tests.fixtures.console_http`
and a stub session that answers each statement by the table it names, the pattern
`tests/unit/test_govern_routes.py` argues for, so every refusal, the order the checks run in and
what each row may carry are exercised without a server. The last three tests drive the same routes
against PostgreSQL as the application role: the insert, the `principal_state` entry `0141`'s
trigger writes under the new person, and the directory and the person's page read back from real
rows, sessions, grants and packs included. Those skip without a server and run in CI.

**Every refusal has a sibling proving the permitted case is answered**, CLAUDE.md's rule about a
guard tested only by its refusals. The capabilities are written out rather than read off the
registry, for `tests/unit/test_govern_routes.py`'s reason.

Task ids: M27.11.2, M27.11.3, M27.15.19
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain import directory_routes as routes
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.audit.ledger import AuditChain
from brain.audit.record import AuditRecorder, PrincipalStateChange
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import Capability, Grant
from brain.core.errors import Absent
from brain.core.scope import Scope
from brain.gate.admission import Assurance
from brain.identity.standing import WHY_KEPT_OUT, KeptOut
from brain.install import hold_saved
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.tables.gate import (
    CapabilityGrantRow,
    CapabilityPackAssignmentRow,
    CapabilityPackRow,
    ScopeRow,
)
from brain.tables.identity import PrincipalRow
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.http_client import Response
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import sql
from tests.unit.test_console_control_audit import pressed
from tests.unit.test_credential_writes import entries as every_entry
from tests.unit.test_review_store import entries
from tests.unit.test_tables import DIALECT

DIRECTORY = f"{API_PREFIX}/govern/directory"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
FAR_OFF = datetime(2999, 1, 1, tzinfo=UTC)

MAINTENANCE = "maintenance"
FINANCE = "finance"
WHOLE = Scope.unrestricted()
IN_MAINTENANCE = Scope.department(MAINTENANCE)
CONFIGURATION = plane_capability(Plane.CONFIGURATION).value


def grant(value: str, scope: Scope = WHOLE) -> Grant:
    return Grant(capability=Capability(value=value), scope=scope)


#: `u_admin` reads People, the vocabulary, Sessions and Scopes everywhere and governs everybody.
#: `u_elsewhere` holds the same over maintenance only. `u_wide` reads People everywhere and nothing
#: else. `u_narrow` holds People's capability without the console plane. `u_prefix` holds the
#: organising authority over maintenance and reads nothing. `u_none` holds nothing.
GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_admin": (
        grant("read:grant"),
        grant("read:capability"),
        grant("read:session"),
        grant("read:scope"),
        grant("approve:grant"),
        grant(CONFIGURATION),
    ),
    "u_elsewhere": (
        grant("read:grant", IN_MAINTENANCE),
        grant("read:capability", IN_MAINTENANCE),
        grant("read:session", IN_MAINTENANCE),
        grant("read:scope", IN_MAINTENANCE),
        grant("approve:grant", IN_MAINTENANCE),
        grant(CONFIGURATION),
    ),
    "u_wide": (grant("read:grant"), grant(CONFIGURATION)),
    "u_narrow": (grant("read:grant"),),
    "u_prefix": (grant("approve:grant", IN_MAINTENANCE),),
    "u_none": (),
}

# ------------------------------------------------------------------------------ the rows

#: Who the stub holds: (id, name, department, employment, disabled at). Human, live rows only,
#: because the statements carry the kind and the retirement, which `test_the_directory_reads_live_
#: people_only` holds, and a stub cannot evaluate a WHERE clause.
PEOPLE: tuple[tuple[str, str, str | None, str, datetime | None], ...] = (
    ("u_1", "Alice Ang", MAINTENANCE, "staff", None),
    ("u_2", "Bob Bee", FINANCE, "staff", LONG_AGO),
    ("u_3", "Cara Cho", None, "contractor", None),
)


def pack_row(name: str = "helpdesk") -> CapabilityPackRow:
    row = CapabilityPackRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, name),
        name=name,
        description="What the help desk needs",
        capabilities=["read:ticket", "write:ticket"],
        version=3,
    )
    row.created_at = LONG_AGO
    row.deleted_at = None
    return row


def assignment_row(principal_id: str, *, not_after: datetime | None = None) -> Any:
    row = CapabilityPackAssignmentRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"assignment/{principal_id}"),
        principal_id=principal_id,
        pack_id=pack_row().id,
        scope=IN_MAINTENANCE.model_dump(),
        granted_by="u_2",
        reason="joined the help desk",
        not_after=not_after,
    )
    row.created_at = LONG_AGO
    row.deleted_at = None
    return row


def grant_row(capability: str, scope: Scope, granted_by: str = "u_1") -> CapabilityGrantRow:
    row = CapabilityGrantRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"grant/{capability}"),
        principal_id="u_1",
        capability=capability,
        scope=scope.model_dump(),
        granted_by=granted_by,
        reason="the work needs it",
        not_after=None,
    )
    row.created_at = LONG_AGO
    row.deleted_at = None
    return row


def scope_row(slug: str, predicate: dict[str, Any], label: str) -> ScopeRow:
    row = ScopeRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, slug),
        slug=slug,
        predicate=predicate,
        is_department=False,
        label=label,
    )
    row.created_at = LONG_AGO
    row.deleted_at = None
    return row


class Rows:
    def __init__(self, rows: Sequence[Any]) -> None:
        self._rows = tuple(rows)

    def scalars(self) -> Rows:
        return Rows([row[0] if isinstance(row, tuple) else row for row in self._rows])

    def all(self) -> tuple[Any, ...]:
        return self._rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        [row] = self._rows
        return row[0] if isinstance(row, tuple) else row


class Held:
    """What the stub answers each table, and every statement it was asked to run."""

    def __init__(self) -> None:
        self.people = list(PEOPLE)
        self.departments = [(FINANCE, "Finance"), (MAINTENANCE, "Maintenance")]
        #: (whose, pack, lapses)
        self.packs: list[tuple[str, str, datetime | None]] = [("u_1", "helpdesk", None)]
        #: (whose, began, assurance), one per person, newest first as `DISTINCT ON` leaves it.
        self.sessions = [("u_1", LONG_AGO, int(Assurance.STRONG))]
        self.grants = [
            grant_row("read:client.name", IN_MAINTENANCE),
            grant_row("read:invoice.total", WHOLE, granted_by="u_2"),
        ]
        self.assignments = [(assignment_row("u_1"), pack_row())]
        self.scopes = [
            scope_row("company", {}, "Everything"),
            scope_row(MAINTENANCE, {"department": MAINTENANCE}, "All of maintenance"),
        ]
        self.teams = [(MAINTENANCE, "boilers", "Boilers"), (FINANCE, "payroll", "Payroll")]
        self.leads = [(MAINTENANCE, "Maintenance"), (FINANCE, "Finance")]
        #: Where the staff list names people, joined through the roster's email binding:
        #: (whose, status, employment type, left at). Read only when a staff list is chosen.
        self.standing: list[tuple[str, str, str | None, datetime | None]] = [
            ("u_1", "suspended", "regular", None),
            ("u_3", "active", "outsourced", None),
        ]
        self.statements: list[str] = []
        self.commits = 0

    def answer(self, statement: Any) -> Rows:
        text = str(statement)
        params: Mapping[str, Any] = (
            statement.compile().params if hasattr(statement, "compile") else {}
        )
        if text.startswith(("SET TRANSACTION", "SELECT set_config")):
            return Rows([])
        if text.startswith("INSERT INTO auth.principal"):
            return Rows([(LONG_AGO,)])
        if "FROM auth.session" in text:
            wanted = set(params.get("principal_id_1", ()))
            return Rows([one for one in self.sessions if one[0] in wanted])
        if "JOIN auth.staff_member" in text:
            wanted = set(params.get("principal_id_1", ()))
            return Rows([one for one in self.standing if one[0] in wanted])
        if "FROM gate.team_membership" in text:
            return Rows(self.teams)
        if "FROM gate.department_lead" in text:
            return Rows(self.leads)
        if "FROM gate.capability_pack_assignment" in text and "principal_id_1" in params:
            if isinstance(params["principal_id_1"], list | tuple):
                wanted = set(params["principal_id_1"])
                return Rows([one for one in self.packs if one[0] in wanted])
            return Rows(self.assignments)
        if "FROM gate.capability_grant" in text:
            return Rows([(one,) for one in self.grants])
        if "FROM gate.scope" in text:
            return Rows([(one,) for one in self.scopes])
        if "FROM gate.department" in text:
            if "slug_1" in params:
                slug = params["slug_1"]
                return Rows([(uuid.uuid4(),)] if slug in dict(self.departments) else [])
            return Rows(self.departments)
        if "FROM auth.principal" in text:
            if "id_1" in params:
                wanted_id = params["id_1"]
                if isinstance(wanted_id, list | tuple):
                    return Rows([one[:3] for one in self.people if one[0] in wanted_id])
                return Rows([one for one in self.people if one[0] == wanted_id])
            return Rows(self.people)
        msg = f"no stub answers {text}"
        raise AssertionError(msg)


_HELD = Held()


class StubSession(AsyncSession):
    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            _HELD.statements.append(str(statement.compile(compile_kwargs={"literal_binds": True})))
        except Exception:
            _HELD.statements.append(str(statement))
        return _HELD.answer(statement)

    async def commit(self) -> None:
        _HELD.commits += 1

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


@pytest.fixture
def held() -> Iterator[Held]:
    global _HELD
    _HELD = Held()
    yield _HELD


@pytest.fixture
def no_staff_list() -> Iterator[None]:
    """An install reading no staff list, whatever this process was started with."""
    before = hold_saved({"INSTALL_STAFF_SOURCE": "none"})
    yield
    hold_saved(before)


@pytest.fixture
def client(held: Held, no_staff_list: None) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    # Included here as well as by `brain.app`, so the routes are exercised in a worktree whose
    # `brain.app` predates the line, which is `tests.fixtures.console_http`'s arrangement.
    app.include_router(routes.router)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = gate_wiring(GRANTS)
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        app.state.console_reads = None
        yield c


def get(c: TestClient, pid: str, path: str = DIRECTORY, **params: Any) -> Response:
    response: Response = c.get(path, headers=headers(pid), params=params or None)
    return response


def add(c: TestClient, pid: str, body: Mapping[str, object]) -> Response:
    response: Response = c.post(DIRECTORY, json=dict(body), headers=headers(pid))
    return response


def ids(page: Mapping[str, Any]) -> list[str]:
    return [one["principal_id"] for one in page["items"]]


def without_trace(body: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in body.items() if key != "trace_id"}


# ------------------------------------------------------------------------ the directory


def test_every_person_is_listed_whether_or_not_they_hold_a_grant(
    client: TestClient, held: Held
) -> None:
    """The gap this closes: the People screen built from grants never shows somebody holding
    nothing, so they can never be granted anything. `u_3` holds nothing and is in no department,
    `u_2` is disabled, and all three are listed, in name order, each with what the row says.

    Delete this and the directory can quietly become a listing of grant subjects again, or drop a
    disabled person who somebody needs to find in order to reinstate them."""
    page = get(client, "u_admin").json()

    assert ids(page) == ["u_1", "u_2", "u_3"]
    alice, bob, cara = page["items"]
    assert alice == {
        "principal_id": "u_1",
        "display_name": "Alice Ang",
        "department": MAINTENANCE,
        "department_name": "Maintenance",
        "employment": "staff",
        "standing": "live",
        "second_factor": True,
        "last_signed_in_at": LONG_AGO.isoformat().replace("+00:00", "Z"),
        "packs": ["helpdesk"],
        "staff_status": None,
        "employment_type": None,
    }
    assert (bob["standing"], bob["second_factor"], bob["last_signed_in_at"]) == (
        "disabled",
        None,
        None,
    )
    assert (cara["department"], cara["department_name"], cara["employment"], cara["packs"]) == (
        None,
        None,
        "contractor",
        [],
    )
    assert (page["editable"], page["may_disable"], page["may_add"], page["truncated"]) == (
        True,
        True,
        True,
        False,
    )
    assert page["adding"] == routes.ADDING_A_PERSON_GRANTS_NOTHING
    assert page["account_ready"] is None
    assert page["next_cursor"] is None


def test_a_department_reader_is_listed_only_the_people_where_they_read(
    client: TestClient, held: Held
) -> None:
    """`nameable` decides, and the route adds nothing. Delete this and a maintenance reader is
    shown finance's people, or a person in no department, who sits where only a company-wide
    reader reaches."""
    page = get(client, "u_elsewhere").json()

    assert ids(page) == ["u_1"]
    assert page["items"][0]["packs"] == ["helpdesk"]
    assert page["may_add"] is True


def test_packs_and_a_sign_in_are_told_only_through_their_own_screens(
    client: TestClient, held: Held
) -> None:
    """`u_wide` may open People and neither the Capabilities nor the Sessions screen: every person
    is listed, with no pack and no sign-in, exactly as somebody who holds none and never signed in
    reads, and no pack or session is even read on their behalf.

    Delete this and the directory becomes a way to read somebody's packs past the vocabulary's
    grant, or their sign-ins past the Sessions screen's."""
    page = get(client, "u_wide").json()

    assert ids(page) == ["u_1", "u_2", "u_3"]
    assert {(one["second_factor"], one["last_signed_in_at"]) for one in page["items"]} == {
        (None, None)
    }
    assert {tuple(one["packs"]) for one in page["items"]} == {()}
    assert not [one for one in held.statements if "auth.session" in one]
    assert not [one for one in held.statements if "capability_pack" in one]
    assert (page["editable"], page["may_add"], page["may_disable"]) == (False, False, False)


def test_a_sign_in_below_a_second_factor_is_said_to_be_one(client: TestClient, held: Held) -> None:
    """`second_factor` is the most recent session's assurance at STRONG and nothing weaker. Delete
    this and a password-only sign-in can be shown as a second factor."""
    held.sessions = [("u_1", LONG_AGO, int(Assurance.AUTHENTICATED))]

    alice = get(client, "u_admin").json()["items"][0]

    assert alice["second_factor"] is False


def test_a_lapsed_pack_is_not_one_somebody_holds(client: TestClient, held: Held) -> None:
    """Delete this and the directory names a pack whose assignment lapsed, which confers nothing,
    as one the person holds."""
    held.packs = [("u_1", "helpdesk", LONG_AGO)]

    alice = get(client, "u_admin").json()["items"][0]

    assert alice["packs"] == []


def test_the_directory_is_refused_before_the_database(client: TestClient, held: Held) -> None:
    """The ordering every govern screen keeps, and the plane: `u_narrow` holds People's capability
    without the console plane. Delete this and a caller holding nothing can tell a process with a
    database from one without, or an existence-only reader is answered a configuration screen."""
    answers = [get(client, pid) for pid in ("u_narrow", "u_none", "u_prefix")]

    assert {one.status_code for one in answers} == {404}
    assert held.statements == []


def test_the_directory_searches_filters_orders_and_pages_what_the_row_shows(
    client: TestClient, held: Held
) -> None:
    """Through `brain.listing`, over the projected rows. Delete this and a column the console
    filters or orders by is refused as undeclared, or a search reads a field the row does not
    show."""
    by_name = get(client, "u_admin", q="cara")
    disabled = get(client, "u_admin", filter="standing:disabled")
    in_maintenance = get(client, "u_admin", filter="department:maintenance")
    by_pack = get(client, "u_admin", filter="packs:helpdesk")
    newest = get(client, "u_admin", sort="-display_name")
    first = get(client, "u_admin", limit=1)
    second = get(client, "u_admin", limit=1, cursor=first.json()["next_cursor"])
    strong = get(client, "u_admin", filter="second_factor:true")

    assert ids(by_name.json()) == ["u_3"]
    assert ids(disabled.json()) == ["u_2"]
    assert ids(in_maintenance.json()) == ["u_1"]
    assert ids(by_pack.json()) == ["u_1"]
    assert ids(newest.json()) == ["u_3", "u_2", "u_1"]
    assert (ids(first.json()), ids(second.json())) == (["u_1"], ["u_2"])
    assert ids(strong.json()) == ["u_1"]
    assert get(client, "u_admin", sort="employment").status_code == 422


def test_a_full_load_says_it_is_truncated_and_nothing_counts_anybody(
    client: TestClient, held: Held, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`truncated` is the load coming back full, measured against what was loaded and never against
    what `nameable` kept, and no field of either response is a count. Delete this and the flag can
    say how many a reader was not shown, or a total arrives in a field somebody added to be
    helpful."""
    monkeypatch.setattr(routes, "MAX_PEOPLE", 3)
    full = get(client, "u_elsewhere").json()
    monkeypatch.setattr(routes, "MAX_PEOPLE", 4)
    room = get(client, "u_elsewhere").json()

    assert (full["truncated"], ids(full)) == (True, ["u_1"])
    assert room["truncated"] is False
    for shape in (
        routes.DirectoryPage,
        routes.DirectoryPersonView,
        routes.PersonDetail,
        routes.HeldView,
        routes.PlacementView,
    ):
        assert not set(shape.model_fields) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT, shape


def test_the_directory_reads_live_people_only_and_each_ones_newest_session() -> None:
    """The statements carry the rules a stub cannot evaluate. Delete this and service principals
    or retired people are listed, the load is narrowed by what somebody searched, or the sign-in
    shown is somebody's oldest rather than their newest."""

    def rendered(statement: Any) -> str:
        return str(statement.compile(dialect=DIALECT, compile_kwargs={"literal_binds": True}))

    people = rendered(routes.live_people(10))
    one = rendered(routes.one_person("u_1"))
    sessions = rendered(routes.last_sessions(["u_1"]))
    teams = rendered(routes.teams_of("u_1", 10))
    leads = rendered(routes.leads_of("u_1", 10))

    for statement in (people, one):
        assert "auth.principal.deleted_at IS NULL" in statement
        assert "auth.principal.kind = 'human'" in statement
    assert "LIMIT 10" in people
    assert "SELECT DISTINCT ON (auth.session.principal_id)" in sessions
    assert "ORDER BY auth.session.principal_id, auth.session.started_at DESC" in sessions
    assert "FROM gate.team_membership JOIN gate.team" in teams
    assert "FROM gate.department_lead JOIN gate.department" in leads


# ------------------------------------------------------------------------ one person


def test_a_persons_page_says_where_they_sit_and_what_they_hold(
    client: TestClient, held: Held
) -> None:
    """M27.11.3's view of one person: their row, their department, team and lead in departments the
    reader is offered, their direct grants by capability and then their packs, each with the scope
    named where a live scope carries exactly that predicate, and the granter named.

    Delete this and every refusal below is satisfied by a page that answers nobody, or a pack's
    capabilities, version or label can be dropped, or the order a reviewer reads in can drift."""
    answered = get(client, "u_admin", f"{DIRECTORY}/u_1")
    assert answered.status_code == 200, answered.text
    page = answered.json()

    assert page["person"]["display_name"] == "Alice Ang"
    assert page["placements"] == {
        "department": {"slug": MAINTENANCE, "name": "Maintenance"},
        "teams": [
            {"department": MAINTENANCE, "slug": "boilers", "name": "Boilers"},
            {"department": FINANCE, "slug": "payroll", "name": "Payroll"},
        ],
        "leads": [
            {"slug": MAINTENANCE, "name": "Maintenance"},
            {"slug": FINANCE, "name": "Finance"},
        ],
    }
    assert [(one["kind"], one["capabilities"]) for one in page["held"]] == [
        ("grant", ["read:client.name"]),
        ("grant", ["read:invoice.total"]),
        ("pack", ["read:ticket", "write:ticket"]),
    ]
    first, second, pack = page["held"]
    assert (first["scope_slug"], first["scope_label"]) == (MAINTENANCE, "All of maintenance")
    assert (second["scope_slug"], second["scope_label"]) == ("company", "Everything")
    assert (first["granted_by"], first["granted_by_name"]) == ("u_1", "Alice Ang")
    assert (second["granted_by"], second["granted_by_name"]) == ("u_2", "Bob Bee")
    assert (pack["pack"], pack["pack_label"], pack["pack_version"]) == (
        "helpdesk",
        "What the help desk needs",
        3,
    )
    assert pack["row_id"] == str(assignment_row("u_1").id)
    assert first["row_id"] == str(grant_row("read:client.name", IN_MAINTENANCE).id)
    assert (page["editable"], page["may_disable"], page["may_organise"]) == (True, True, True)
    assert page["from_a_pack"] == routes.A_CAPABILITY_FROM_A_PACK_GOES_WITH_THE_PACK


def test_a_hidden_person_and_a_missing_one_are_answered_byte_for_byte_alike(
    client: TestClient, held: Held
) -> None:
    """`A_PERSON_PAGE_REFUSES_A_HIDDEN_PERSON_AS_IT_REFUSES_A_MISSING_ONE`. A maintenance reader
    asking for somebody in finance, for somebody in no department, for an id nobody holds, and a
    reader who may not open People at all asking for a person they could otherwise see, are one
    status and one body, trace aside, and nothing past a hidden person's own row is read.

    Delete this and the address answers, for every id somebody types, whether it is a person."""
    finance = get(client, "u_elsewhere", f"{DIRECTORY}/u_2")
    after_hidden = list(held.statements)
    nowhere = get(client, "u_elsewhere", f"{DIRECTORY}/u_3")
    missing = get(client, "u_elsewhere", f"{DIRECTORY}/u_missing")
    closed = get(client, "u_narrow", f"{DIRECTORY}/u_1")
    shown = get(client, "u_elsewhere", f"{DIRECTORY}/u_1")

    bodies = {str(sorted(without_trace(one.json()).items())) for one in (finance, nowhere, missing)}
    bodies.add(str(sorted(without_trace(closed.json()).items())))
    assert {one.status_code for one in (finance, nowhere, missing, closed)} == {404}
    assert len(bodies) == 1
    assert finance.json()["message"] == Absent.public_message
    assert [one for one in after_hidden if "FROM auth.principal" not in one] == [
        "SET TRANSACTION READ ONLY"
    ]
    assert shown.status_code == 200


def test_a_department_reader_is_shown_only_what_their_own_screens_would_show(
    client: TestClient, held: Held
) -> None:
    """A maintenance reader on a maintenance person's page: their finance team and their lead of
    finance are not placements this reader is offered; a granter in finance is not named; and a
    company-wide scope is not named, because `scope_rows` would not show it to them.

    Delete this and one person's page becomes the way round the Departments page's offer, the
    People screen's read over the granter, or the Scopes screen's containment."""
    page = get(client, "u_elsewhere", f"{DIRECTORY}/u_1").json()

    assert page["placements"]["teams"] == [
        {"department": MAINTENANCE, "slug": "boilers", "name": "Boilers"}
    ]
    assert page["placements"]["leads"] == [{"slug": MAINTENANCE, "name": "Maintenance"}]
    whole = next(one for one in page["held"] if one["capabilities"] == ["read:invoice.total"])
    assert (whole["scope_slug"], whole["scope_label"], whole["granted_by_name"]) == (
        None,
        None,
        None,
    )
    mine = next(one for one in page["held"] if one["capabilities"] == ["read:client.name"])
    assert (mine["scope_slug"], mine["granted_by_name"]) == (MAINTENANCE, "Alice Ang")


def test_a_reader_without_the_vocabulary_is_shown_nothing_a_person_holds(
    client: TestClient, held: Held
) -> None:
    """`u_wide` may see who somebody is and not what they hold: no holding, no pack, no sign-in and
    no placement, since they read neither the vocabulary nor Sessions nor Scopes, and none of those
    tables is read for them. Delete this and a person's page lists capabilities past the
    Capabilities screen's grant."""
    page = get(client, "u_wide", f"{DIRECTORY}/u_1").json()

    assert page["held"] == []
    assert page["person"]["packs"] == []
    assert page["person"]["second_factor"] is None
    assert page["placements"] == {"department": None, "teams": [], "leads": []}
    assert not [one for one in held.statements if "capability_grant" in one]
    assert not [one for one in held.statements if "auth.session" in one]


# ------------------------------------------------------------------------ adding somebody


def test_a_person_is_added_by_hand_where_no_staff_list_is_read(
    client: TestClient, held: Held
) -> None:
    """M27.15.19, the positive case. The name is trimmed, the id is minted, the person is a human
    at the department named holding nothing, and the caller is named to the transaction before the
    insert so `0141`'s trigger records them.

    Delete this and every refusal below is satisfied by a route that adds nobody, or the entry can
    be recorded against nobody."""
    answered = add(
        client, "u_elsewhere", {"display_name": "  Dee Dunn ", "department": MAINTENANCE}
    )

    assert answered.status_code == 201, answered.text
    body = answered.json()
    assert body["principal_id"].startswith("u_") and len(body["principal_id"]) == 34
    assert (body["display_name"], body["department"]) == ("Dee Dunn", MAINTENANCE)
    actor = next(i for i, one in enumerate(held.statements) if "brain.actor_id" in one)
    insert = next(i for i, one in enumerate(held.statements) if one.startswith("INSERT"))
    assert actor < insert
    assert "'u_elsewhere'" in held.statements[actor]
    assert "'human'" in held.statements[insert]
    assert held.commits == 1


def test_a_person_is_added_only_where_the_caller_governs(client: TestClient, held: Held) -> None:
    """`may_add_person` over the row the new person will sit in. A maintenance organiser adding
    somebody to finance, or to no department, is refused before the database, exactly as a caller
    holding nothing is; an administrator adding somebody to no department is answered; and a
    department no live row carries is said, only to a caller whose authority covers it.

    Delete this and a department's organiser can put people into another department's directory,
    or the sentence about a department becomes a way to learn which departments exist."""
    outside = add(client, "u_elsewhere", {"display_name": "Eve", "department": FINANCE})
    nowhere = add(client, "u_elsewhere", {"display_name": "Eve"})
    unknown_outside = add(client, "u_elsewhere", {"display_name": "Eve", "department": "sales"})
    nothing = add(client, "u_none", {"display_name": "Eve", "department": MAINTENANCE})
    reached_before = list(held.statements)
    company = add(client, "u_admin", {"display_name": "Eve"})
    unknown = add(client, "u_admin", {"display_name": "Eve", "department": "sales"})

    refused = {(one.status_code, one.json()["message"]) for one in (outside, nowhere, nothing)}
    assert refused == {(404, Absent.public_message)}
    assert (unknown_outside.status_code, unknown_outside.json()["message"]) == (
        404,
        Absent.public_message,
    )
    assert reached_before == []
    assert company.status_code == 201, company.text
    assert (unknown.status_code, unknown.json()["message"]) == (
        404,
        f"Nothing was changed: {routes.A_DEPARTMENT_NAMED_IS_NOT_LIVE}.",
    )
    assert held.commits == 1


def test_beside_a_staff_list_nobody_is_added_and_a_holder_is_told_why(
    client: TestClient, held: Held
) -> None:
    """`A_PERSON_IS_ADDED_BY_HAND_ONLY_WHERE_NO_STAFF_LIST_IS_READ`. With a source configured, a
    caller holding the organising authority is told in a sentence that people arrive from it, a
    caller holding nothing is told nothing more than the one refusal, nothing is read or written,
    and the directory stops offering the control and says why.

    Delete this and a person typed in by hand sits beside the list the next sync reads, and is
    either written twice or marked as having left."""
    before = hold_saved({"INSTALL_STAFF_SOURCE": "lark"})
    try:
        holder = add(client, "u_admin", {"display_name": "Eve", "department": MAINTENANCE})
        nothing = add(client, "u_none", {"display_name": "Eve", "department": MAINTENANCE})
        page = get(client, "u_admin").json()
    finally:
        hold_saved(before)

    sentence = routes.PEOPLE_ARRIVE_FROM_THE_STAFF_SOURCE.rstrip(".")
    assert (holder.status_code, holder.json()["message"]) == (
        404,
        f"Nothing was changed: {sentence}.",
    )
    assert (nothing.status_code, nothing.json()["message"]) == (404, Absent.public_message)
    assert not [one for one in held.statements if one.startswith("INSERT")]
    assert (page["may_add"], page["adding"]) == (False, routes.PEOPLE_ARRIVE_FROM_THE_STAFF_SOURCE)
    # The sentence the owner asked for, written out here so it cannot drift with its constant.
    assert page["account_ready"] == (
        "Your account is ready. Go to the sign-in page, press Forgot password and enter your "
        "work email."
    )


def test_an_install_reading_no_list_is_told_apart_from_one_reading_any() -> None:
    """`none` is the one source that reads nothing, and a name nobody recognises counts as a list.
    Delete this and a misspelt source switches adding by hand on beside a real list, or `none`
    switches it off everywhere."""
    assert routes.reads_a_staff_list(env={}, saved={"INSTALL_STAFF_SOURCE": "none"}) is False
    assert routes.reads_a_staff_list(env={}, saved={}) is False
    assert routes.reads_a_staff_list(env={}, saved={"INSTALL_STAFF_SOURCE": "lark"}) is True
    assert routes.reads_a_staff_list(env={}, saved={"INSTALL_STAFF_SOURCE": "spreadsheet"}) is True
    assert routes.reads_a_staff_list(env={}, saved={"INSTALL_STAFF_SOURCE": "nonsense"}) is True


def test_a_body_the_types_refuse_is_a_422_that_reaches_no_database(
    client: TestClient, held: Held
) -> None:
    """Delete this and a contractor with no end, a service account, a blank name, a malformed
    department, a naive end or a body choosing its own id reaches the database, where it is a
    constraint error, or a person arrives who is not one."""
    bodies: list[Mapping[str, object]] = [
        {"display_name": "Eve", "employment": "contractor"},
        {"display_name": "Eve", "employment": "service"},
        {"display_name": "   "},
        {"display_name": "Eve", "department": "Not A Slug"},
        {"display_name": "Eve", "employment": "partner", "not_after": "2999-01-01T00:00:00"},
        {"display_name": "Eve", "principal_id": "u_chosen"},
    ]
    answers = [add(client, "u_admin", body) for body in bodies]
    bounded = add(
        client,
        "u_admin",
        {"display_name": "Eve", "employment": "contractor", "not_after": FAR_OFF.isoformat()},
    )

    assert [one.status_code for one in answers] == [422] * len(bodies)
    assert bounded.status_code == 201, bounded.text


# ----------------------------------------------------------------------- against a database


def test_a_person_added_by_hand_is_recorded_and_then_listed_with_what_they_hold() -> None:
    """**M27.15.19 on PostgreSQL, through the routes, as the application role.** A person added by
    hand is one `auth.principal` row, a human in the department named, and exactly one ledger entry,
    `principal_state` `created` under the new person, naming the caller with the request's reach
    digest and trace. The directory then lists them, and once they have signed in and been granted
    a capability and a pack, it lists their sign-in and pack, and their page holds the grant and the
    pack with the named scope and the granter's name. The chain verifies.

    Delete this and the statements behind the directory and the page, `DISTINCT ON` and the joins
    included, have never met PostgreSQL, and the entry recording a person's creation can be
    missing, unattributed or filed under somebody else. **Skips without a server.**"""
    before_saved = hold_saved({"INSTALL_STAFF_SOURCE": "none"})
    try:
        with retirable("brain_directory_people") as url:
            if not has_pgvector(url):
                pytest.skip("0141 sits on the whole chain, which runs only where pgvector is")
            sql(
                url,
                "INSERT INTO gate.scope (slug, predicate, label) VALUES"
                " ('maintenance', '{\"department\": \"maintenance\"}', 'All of maintenance')",
            )
            sql(
                url,
                "INSERT INTO gate.department (company_id, slug, name, scope_slug)"
                " VALUES ('company', 'maintenance', 'Maintenance', 'maintenance')",
            )
            ledger_before = len(entries(url, "principal_state"))

            async def create(client: httpx.AsyncClient) -> tuple[int, dict[str, Any]]:
                answer = await client.post(
                    DIRECTORY,
                    json={"display_name": "Dee Dunn", "department": MAINTENANCE},
                    headers=headers("u_admin"),
                )
                return answer.status_code, answer.json()

            status, created = pressed(url, GRANTS, create)
            new_id = str(created["principal_id"])
            rows = sql(
                url,
                "SELECT kind, employment, display_name, primary_department FROM auth.principal"
                " WHERE id = %s",
                new_id,
            )
            recorded = entries(url, "principal_state")[ledger_before:]
            sql(
                url,
                "INSERT INTO auth.session (id, principal_id, channel, assurance, started_at,"
                " expires_at) VALUES ('s_old', %s, 'console', 2, %s, %s),"
                " ('s_new', %s, 'console', 3, %s, %s)",
                new_id,
                LONG_AGO,
                LONG_AGO + timedelta(hours=1),
                new_id,
                LONG_AGO + timedelta(days=1),
                LONG_AGO + timedelta(days=1, hours=1),
            )
            sql(
                url,
                "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by,"
                " reason) VALUES (%s, 'read:client.name', %s::jsonb, 'u_admin', 'needed')",
                new_id,
                IN_MAINTENANCE.model_dump_json(),
            )
            [(pack_id,)] = sql(
                url,
                "INSERT INTO gate.capability_pack (name, description, capabilities)"
                " VALUES ('helpdesk', 'Help desk', ARRAY['read:ticket']) RETURNING id",
            )
            sql(
                url,
                "INSERT INTO gate.capability_pack_assignment (principal_id, pack_id, scope,"
                " granted_by, reason) VALUES (%s, %s, %s::jsonb, 'u_admin', 'joined')",
                new_id,
                pack_id,
                IN_MAINTENANCE.model_dump_json(),
            )

            async def read(client: httpx.AsyncClient) -> tuple[Any, Any]:
                listed = await client.get(DIRECTORY, headers=headers("u_admin"))
                page = await client.get(f"{DIRECTORY}/{new_id}", headers=headers("u_admin"))
                return listed.json(), page.json()

            listed, page = pressed(url, GRANTS, read)
            chain = every_entry(url)
    finally:
        hold_saved(before_saved)

    assert status == 201, created
    assert rows == [("human", "staff", "Dee Dunn", MAINTENANCE)]
    expected = AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash="0" * 32, trace_id="t", clock=lambda: LONG_AGO
    ).principal_state(principal_id=new_id, change=PrincipalStateChange.CREATED)
    assert [(one.actor_id, one.subject, dict(one.details)) for one in recorded] == [
        ("u_admin", expected.subject, dict(expected.details))
    ]
    assert recorded[0].ent_hash != "0" * 32
    assert not recorded[0].trace_id.startswith("tx.")
    [row] = [one for one in listed["items"] if one["principal_id"] == new_id]
    assert (row["department_name"], row["standing"], row["packs"]) == (
        "Maintenance",
        "live",
        ["helpdesk"],
    )
    assert row["second_factor"] is True
    assert row["last_signed_in_at"].startswith("2019-03-05")
    assert [(one["kind"], one["capabilities"]) for one in page["held"]] == [
        ("grant", ["read:client.name"]),
        ("pack", ["read:ticket"]),
    ]
    assert page["held"][0]["scope_slug"] == MAINTENANCE
    assert page["placements"]["department"] == {"slug": MAINTENANCE, "name": "Maintenance"}
    assert AuditChain(chain).verify() is None


def test_the_trigger_records_a_creation_exactly_as_the_recorder_does() -> None:
    """Delete this and `PrincipalStateChange.CREATED` and the word `0141`'s trigger writes can come
    apart with no server to notice, or the trigger stop naming an unattributed insert as such."""
    from tests.unit.test_tables import VERSIONS, migration_module, squash

    migration = migration_module(VERSIONS / "0141_packs_people_and_scope_labels_audited.py")
    body = squash(migration.PRINCIPAL_TRIGGER_FUNCTION)

    assert PrincipalStateChange.CREATED.value == "created"
    assert "v_details jsonb := jsonb_build_object('change', 'created');" in body
    assert "v_seq, v_at, v_actor, 'principal_state', 'principal:' || NEW.id, v_ent_hash," in body
    assert "jsonb_build_object('actor', 'unattributed')" in body


def test_the_minted_id_is_the_setup_wizards_and_the_statement_writes_a_human() -> None:
    """Delete this and the directory mints ids a second way, which is two answers to what a
    principal id looks like, or writes the person as a service principal."""
    from brain.setup_routes import PRINCIPAL_PREFIX, new_principal_id

    assert vars(routes)["new_principal_id"] is new_principal_id
    body = routes.PersonAdding(display_name="Eve", department=MAINTENANCE)
    values = routes.adding_person("u_x", body).compile().params
    assert (values["id"], values["kind"], values["employment"]) == ("u_x", "human", "staff")
    assert values["primary_department"] == MAINTENANCE
    assert new_principal_id().startswith(PRINCIPAL_PREFIX)
    assert PrincipalRow.__tablename__ == "principal"


# ------------------------------------------------------------ what the staff list says (M1.6.13)
def test_beside_a_staff_list_each_person_carries_their_status_and_type_and_filters_on_both(
    client: TestClient, held: Held
) -> None:
    """M1.6.13: People shows where the list says each person stands and their employment type,
    joined through the roster's email binding to the chosen source's rows, and filters on both;
    somebody the list does not name carries neither. Delete this and People can stop saying why
    somebody cannot sign in, or read another source's rows."""
    before = hold_saved({"INSTALL_STAFF_SOURCE": "lark"})
    try:
        page = get(client, "u_admin").json()
        suspended = get(client, "u_admin", filter="staff_status:suspended").json()
        outsourced = get(client, "u_admin", filter="employment_type:outsourced").json()
    finally:
        hold_saved(before)

    shown = {
        one["principal_id"]: (one["staff_status"], one["employment_type"]) for one in page["items"]
    }
    assert shown == {
        "u_1": ("suspended", "regular"),
        "u_2": (None, None),
        "u_3": ("active", "outsourced"),
    }
    assert ids(suspended) == ["u_1"]
    assert ids(outsourced) == ["u_3"]
    joined = [one for one in held.statements if "auth.staff_member" in one]
    assert joined and all("staff_member.source = 'lark'" in one for one in joined)


def test_a_person_the_list_keeps_out_says_why_on_their_page_and_one_it_lets_in_says_nothing(
    client: TestClient, held: Held
) -> None:
    """M1.6.14's half an administrator reads: the suspended person's page says the list keeps
    them from signing in or asking, and an outsourced person's says their type may not use the
    Brain; with no staff list read, nobody's page says anything. Delete this and an administrator
    sees a disabled person with no reason, and re-enables them to have them disabled again."""
    before = hold_saved({"INSTALL_STAFF_SOURCE": "lark"})
    try:
        ada = get(client, "u_admin", f"{DIRECTORY}/u_1").json()
        cara = get(client, "u_admin", f"{DIRECTORY}/u_3").json()
        bob = get(client, "u_admin", f"{DIRECTORY}/u_2").json()
    finally:
        hold_saved(before)
    alone = get(client, "u_admin", f"{DIRECTORY}/u_1").json()

    assert ada["kept_out"] == WHY_KEPT_OUT[KeptOut.SUSPENDED]
    assert cara["kept_out"] == WHY_KEPT_OUT[KeptOut.TYPE_NOT_ALLOWED]
    assert bob["kept_out"] is None
    assert alone["kept_out"] is None and alone["person"]["staff_status"] is None
