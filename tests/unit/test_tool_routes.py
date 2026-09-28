"""The Tools screen: the catalogue table, the routes, and the switch followed to its ledger entry.

Three halves. **The table** is read off the migration that ships and held to the models and to the
grammar the registry refuses a name on, so `agent.tool_definition` cannot record a tool no registry
would accept (M12.1.1) or a result contract no tool can declare (M12.1.4). **The routes** are driven
through the real application with a stub where the pool is, answered by `ToolRows` below from each
statement's own compiled parameters, so a route that wrote the wrong department is caught rather
than agreed with. **The database** half presses the switch over HTTP as the application role and
follows it to the row, the `setting` entry and a call refused through `SessionSwitchSource`, and
skips without a server, which CI provides.

Task ids: M12.1.1, M12.1.3, M12.1.4, M12.3.8, M12.4.3
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import String, create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.selectable import Select

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import (
    TOOL_NAME_PATTERN,
    Entity,
    IdentityMode,
    SideEffect,
    ToolDefinition,
    TypedResult,
)
from brain.core.scope import Scope
from brain.db import metadata
from brain.identity.first_administrator import ADMINISTRATION
from brain.ops.halt import MINIMUM_REASON
from brain.ops.tool_store import (
    SessionSwitchSource,
    definition_values,
    departments_statement,
    live_stops_statement,
    recorded_statement,
)
from brain.session import make_session_factory
from brain.tables import tool_definition as tables
from brain.tables.gate import CAPABILITY_PATTERN
from brain.tables.identity import one_of
from brain.tool_routes import TOOL_AUTHORITY, TOOLS_PATH
from brain.tool_routes import router as tool_router
from brain.tools.registry import (
    TOOL_NAME_RE,
    ResultContract,
    SensitiveEffect,
    ToolRegistry,
    ToolSwitchedOffError,
)
from tests.fixtures.console_http import Stub, console_client, gate_wiring, headers
from tests.fixtures.retirable import present_tables, retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.fixtures.setting_rows import Result, Row
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_review_store import entries
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

MIGRATION = VERSIONS / "0117_tool_catalogue_and_switch.py"
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
SCREEN = f"{API_PREFIX}{TOOLS_PATH}"

#: Far from any wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

WHOLE = Scope.unrestricted()
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": (Grant(capability=TOOL_AUTHORITY, scope=WHOLE),),
    "u_narrow": (Grant(capability=TOOL_AUTHORITY, scope=Scope.department("web")),),
    "u_elsewhere": (Grant(capability=TOOL_AUTHORITY, scope=Scope.department("sales")),),
    "u_wide": (Grant(capability=Capability(value="admin:feature"), scope=WHOLE),),
    "u_none": (),
}

READ_NOTE = "notes.read_note"
UPDATE_NOTE = "notes.update_note"
DELETE_FILE = "drive.delete_file"


class Note(Entity):
    text: str = ""


def read_note(*, entitlement: EntitlementSet, now: datetime | None = None) -> TypedResult[Note]:
    return TypedResult[Note](records=(Note(entity="note", id="n_1", text="kept"),))


def a_registry() -> ToolRegistry:
    """A read, a write and an irreversible tool, the three words the screen uses."""
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name=READ_NOTE,
            description="Read a note",
            entity="note",
            required_capability="read:note.text",
        ),
        read_note,
    )
    registry.register(
        ToolDefinition(
            name=UPDATE_NOTE,
            description="Change what a note says",
            entity="note",
            required_capability="write:note.text",
            side_effect=SideEffect.WRITE,
        ),
        read_note,
    )
    registry.register(
        ToolDefinition(
            name=DELETE_FILE,
            description="Delete a file from the shared drive",
            entity="note",
            required_capability="write:note.text",
            side_effect=SideEffect.WRITE,
            identity_mode=IdentityMode.DELEGATED,
            sensitive=True,
        ),
        read_note,
        sensitive_effect=SensitiveEffect.DELETION,
    )
    return registry.freeze()


# ------------------------------------------------------------------------- the table
def module() -> Any:
    return migration_module(MIGRATION)


def test_the_migration_builds_both_tables_exactly_as_the_models_declare_them() -> None:
    """The copy compared on rendered DDL. Delete this and the model can declare the name grammar
    or the one-live-stop index while the database never has either."""
    emitted = squash(rendered("upgrade", MIGRATION))
    for qualified in ("agent.tool_definition", "agent.tool_switch"):
        table = metadata.tables[qualified]
        assert squash(str(CreateTable(table).compile(dialect=DIALECT))) in emitted
        for index in table.indexes:
            assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted


@pytest.mark.parametrize(
    "name",
    [
        "notes.read_note",
        "xero.create_invoice",
        "client.read",
        "Client.read_summary",
        "client",
        "client.read summary",
        "client..read_summary",
        "a1.b2_c3",
        "client.read_summary'); DROP TABLE x; --",
    ],
)
def test_the_databases_name_grammar_admits_exactly_what_the_registry_does(name: str) -> None:
    """M12.1.1's closed grammar, held in the database. The constraint is compiled from the one
    pattern `brain.core.envelope` writes down, and a name is admitted by the one exactly when it is
    admitted by the other. Delete this and a catalogue row can name a tool no registry accepts."""
    m = module()
    assert f"name ~ '{tables.TOOL_NAME_SQL_PATTERN}'" == m.TOOL_NAME_GRAMMAR
    sql_pattern = re.compile(tables.TOOL_NAME_SQL_PATTERN)
    assert bool(sql_pattern.match(name)) is bool(TOOL_NAME_RE.match(name))
    assert "?P<" not in tables.TOOL_NAME_SQL_PATTERN and "?P<" in TOOL_NAME_PATTERN


def test_the_vocabularies_the_migration_copies_are_the_ones_the_code_holds() -> None:
    """Each copied constant against the enum or the figure it copies. Delete this and a sixth side
    effect, a third result contract or an eighth sensitive effect is refused by the database after
    passing every test that only exercised Python."""
    m = module()
    assert one_of("side_effect", SideEffect) == m.SIDE_EFFECTS
    assert one_of("result_contract", ResultContract) == m.RESULT_CONTRACTS
    assert one_of("identity_mode", IdentityMode) == m.IDENTITY_MODES
    assert one_of("sensitive_effect", SensitiveEffect) in m.SENSITIVE_EFFECTS
    assert f"required_capability ~ '{CAPABILITY_PATTERN}'" == m.CAPABILITY_GRAMMAR
    assert f"entity ~ '{tables.OBJECT_NAME_SQL_PATTERN}'" == m.ENTITY_GRAMMAR
    assert (m.DEPARTMENT_CHARS, m.DESCRIPTION_CHARS, m.VOCABULARY_CHARS) == (
        tables.DEPARTMENT_CHARS,
        tables.DESCRIPTION_CHARS,
        tables.VOCABULARY_CHARS,
    )
    column = metadata.tables["auth.principal"].c.primary_department.type
    assert isinstance(column, String)
    assert column.length == tables.DEPARTMENT_CHARS


def test_nothing_may_delete_a_tool_or_a_stop_and_both_tables_are_row_level_secured() -> None:
    """A retired stop is the record that a tool was off. Delete this and a DELETE grant can land on
    the table the question "was this tool off in March" is answered from."""
    m = module()
    assert all("DELETE" not in one for one in (*m.DEFINITION_GRANTS, *m.SWITCH_GRANTS))
    assert "ENABLE ROW LEVEL SECURITY" in m.DEFINITION_RLS[0]
    assert "ENABLE ROW LEVEL SECURITY" in m.SWITCH_RLS[0]
    emitted = squash(rendered("upgrade", MIGRATION))
    assert "ALTER TABLE agent.tool_definition ENABLE ROW LEVEL SECURITY" in emitted
    assert "ALTER TABLE agent.tool_switch ENABLE ROW LEVEL SECURITY" in emitted


def test_every_stop_and_every_restart_is_audited_and_no_reason_reaches_the_ledger() -> None:
    """The trigger writes `off` on an insert and `on` on a retirement, with the tool, the scope and
    the department as a digest. Delete this and the switch can be thrown with nothing recording who
    threw it, or a reason naming a client can land in the ledger nobody may delete from."""
    m = module()
    trigger = squash(m.SWITCH_AUDIT_TRIGGER)
    assert "AFTER INSERT OR UPDATE ON agent.tool_switch" in trigger
    body = squash(m.SWITCH_AUDIT_FUNCTION)
    for fragment in (
        "jsonb_build_object('change', 'off')",
        "jsonb_build_object('change', 'on')",
        "v_subject := 'setting:tool_switch.' || NEW.id::text",
        "'tool', NEW.tool_name",
        "'department_digest', encode(sha256(convert_to(NEW.department, 'UTF8')), 'hex')",
    ):
        assert fragment in body, fragment
    assert "reason" not in body
    assert "v_action := 'setting'" in body


def test_a_catalogue_row_says_what_the_registration_says() -> None:
    """The row is written from the registration and nothing else. Delete this and the catalogue
    can record a sensitive tool as ordinary, or an opaque one as typed."""
    registry = a_registry()
    values = definition_values(registry.get(DELETE_FILE))
    assert values["sensitive"] is True
    assert values["sensitive_effect"] == "deletion"
    assert values["result_contract"] == "typed"
    assert values["required_capability"] == "write:note.text"
    assert values["source"] == "drive"
    assert definition_values(registry.get(READ_NOTE))["sensitive"] is False


# --------------------------------------------------------------------------- the routes
_STOP_COLUMNS = [one["name"] for one in live_stops_statement().column_descriptions]
_RECORDED_COLUMNS = [one["name"] for one in recorded_statement().column_descriptions]
_DEPARTMENT_COLUMNS = [one["name"] for one in departments_statement().column_descriptions]


class ToolRows:
    """The two tables and the principals' departments, answered from compiled parameters."""

    def __init__(self) -> None:
        self.stops: list[dict[str, Any]] = []
        self.definitions: dict[str, dict[str, Any]] = {}
        self.departments = ["sales", "web"]

    def stop(self, tool: str, department: str | None, *, by: str = "u_admin") -> None:
        self.stops.append(
            {
                "id": uuid.uuid4(),
                "tool_name": tool,
                "department": department,
                "switched_off_by": by,
                "created_at": LONG_AGO,
                "off_reason": None,
                "live": True,
            }
        )

    def live(self) -> list[dict[str, Any]]:
        return [one for one in self.stops if one["live"]]

    def answer(self, statement: Any) -> Result | None:
        if isinstance(statement, Select):
            names = [one["name"] for one in statement.column_descriptions]
            if names == _STOP_COLUMNS:
                return Result(Row(tuple(one[key] for key in names)) for one in self.live())
            if names == _RECORDED_COLUMNS:
                return Result(
                    Row(tuple(one[key] for key in names)) for one in self.definitions.values()
                )
            if names == _DEPARTMENT_COLUMNS:
                return Result(Row((one,)) for one in sorted(self.departments))
            return None
        if not isinstance(statement, Insert | Update):
            return None
        params = statement.compile(dialect=DIALECT).params
        table = statement.table.name  # type: ignore[union-attr]
        if isinstance(statement, Insert) and table == "tool_definition":
            self.definitions[str(params["name"])] = dict(params)
            return Result([])
        if isinstance(statement, Insert) and table == "tool_switch":
            same = [
                one
                for one in self.live()
                if (one["tool_name"], one["department"])
                == (params["tool_name"], params["department"])
            ]
            if same:
                return Result([])
            self.stop(str(params["tool_name"]), params["department"], by=params["switched_off_by"])
            self.stops[-1]["off_reason"] = params["off_reason"]
            return Result([Row((self.stops[-1]["id"],))])
        if isinstance(statement, Update) and table == "tool_switch":
            found = [
                one
                for one in self.live()
                if one["tool_name"] == params["tool_name_1"]
                and one["department"] == params.get("department_1")
            ]
            for one in found:
                one["live"] = False
                one["switched_on_by"] = params["switched_on_by"]
                one["on_reason"] = params["on_reason"]
            return Result([Row((one["id"],)) for one in found])
        return None


@pytest.fixture
def rows() -> ToolRows:
    return ToolRows()


@pytest.fixture
def served(rows: ToolRows) -> Iterator[tuple[TestClient, Stub]]:
    with console_client(GRANTS) as (client, stub):
        client.app.include_router(tool_router)  # type: ignore[attr-defined]
        client.app.state.tools = a_registry()  # type: ignore[attr-defined]
        stub.answerers.append(rows.answer)
        yield client, stub


def switch(
    client: TestClient,
    pid: str,
    name: str,
    *,
    on: bool,
    department: str | None = None,
    reason: str | None = None,
) -> Any:
    body: dict[str, Any] = {"on": on, "department": department, "reason": reason}
    return client.post(f"{SCREEN}/{name}/switch", json=body, headers=headers(pid))


@pytest.mark.parametrize("pid", ["u_none", "u_wide"])
def test_a_caller_without_the_authority_is_refused_before_anything_is_read(pid: str) -> None:
    """The same refusal with a database and without, for the read and the write, and nothing
    read or written. The positive sibling is every test below. Delete this and another admin
    capability opens the screen, or anybody can switch a tool off."""
    for database in (True, False):
        with console_client(GRANTS, database=database) as (client, stub):
            client.app.include_router(tool_router)  # type: ignore[attr-defined]
            client.app.state.tools = a_registry()  # type: ignore[attr-defined]
            assert client.get(SCREEN, headers=headers(pid)).status_code == 404
            assert switch(client, pid, READ_NOTE, on=False).status_code == 404
            assert stub.statements == []


def test_the_authority_is_an_administration_capability_the_first_administrator_holds() -> None:
    """`admin:`, so a password-only session is refused by `brain.gate.admission`, and in the
    appointment, so the first administrator can open the screen. Delete this and the capability
    can be respelled into one nobody on any install holds."""
    assert TOOL_AUTHORITY.value.startswith("admin:")
    assert TOOL_AUTHORITY.value in ADMINISTRATION


def test_the_screen_lists_each_tool_with_the_capability_it_needs_and_its_effect(
    served: tuple[TestClient, Stub], rows: ToolRows
) -> None:
    """The owner's Tools screen: every tool, what it needs, and read, write or irreversible, with
    the named sensitive effect, the result contract and the highest rung a leash keeps. A row the
    table holds for a tool no longer registered is listed as not offered. Delete this and the
    screen can drop a tool, or call a delete a write."""
    client, _ = served
    rows.definitions["old.read_thing"] = {
        "name": "old.read_thing",
        "source": "old",
        "entity": "thing",
        "description": "A tool a release stopped registering",
        "required_capability": "read:thing",
        "side_effect": "none",
        "sensitive": False,
        "sensitive_effect": None,
        "result_contract": "typed",
        "identity_mode": "delegated",
    }
    page = client.get(SCREEN, headers=headers("u_admin")).json()
    by_name = {one["name"]: one for one in page["tools"]}
    assert sorted(by_name) == sorted([READ_NOTE, UPDATE_NOTE, DELETE_FILE, "old.read_thing"])
    assert [by_name[one]["effect"] for one in (READ_NOTE, UPDATE_NOTE, DELETE_FILE)] == [
        "read",
        "write",
        "irreversible",
    ]
    assert by_name[DELETE_FILE]["capability"] == "write:note.text"
    assert by_name[DELETE_FILE]["sensitive_effect"] == "deletion"
    assert by_name[READ_NOTE]["result_contract"] == "typed"
    assert [by_name[one]["leash_at_most"] for one in (READ_NOTE, UPDATE_NOTE, DELETE_FILE)] == [
        "autonomous",
        "assisted",
        "assisted",
    ]
    assert by_name["old.read_thing"]["registered"] is False
    assert by_name[READ_NOTE]["registered"] is True
    assert page["may_switch_install"] is True
    assert page["departments"] == ["sales", "web"]
    assert page["reason_to_switch_on"] == MINIMUM_REASON


def test_a_super_administrator_switches_a_tool_off_for_the_install(
    served: tuple[TestClient, Stub], rows: ToolRows
) -> None:
    """One insert with no department, the catalogue row written first, the attribution set before
    both, and the answer saying what now holds. Delete this and the switch can write a department
    stop, or no row at all, while the screen says the tool is off."""
    client, stub = served
    answered = switch(client, "u_admin", READ_NOTE, on=False)
    assert answered.status_code == 200, answered.text
    body = answered.json()
    assert body["changed"] is True
    assert body["tool"]["off_for_install"]["switched_off_by"] == "u_admin"
    assert [(one["tool_name"], one["department"]) for one in rows.live()] == [(READ_NOTE, None)]
    assert READ_NOTE in rows.definitions
    assert ("brain.actor_id", "u_admin") in stub.attributions
    assert stub.commits == 1
    again = switch(client, "u_admin", READ_NOTE, on=False).json()
    assert again["changed"] is False
    assert len(rows.live()) == 1


def test_switching_a_tool_back_on_takes_a_reason_and_retires_the_stop(
    served: tuple[TestClient, Stub], rows: ToolRows
) -> None:
    """`brain.ops.halt`'s asymmetry: stopping needs nothing, starting again a reason of the halt's
    length. Delete this and a stop can be lifted by a stray click with nothing saying why."""
    client, stub = served
    rows.stop(READ_NOTE, None)
    for short in (None, "   ", "x" * (MINIMUM_REASON - 1)):
        refused = switch(client, "u_admin", READ_NOTE, on=True, reason=short)
        assert refused.status_code == 404
        assert "reason" in refused.json()["message"]
    assert stub.statements == []
    reason = "the vendor fixed the fault in their release"
    answered = switch(client, "u_admin", READ_NOTE, on=True, reason=reason).json()
    assert answered["changed"] is True
    assert answered["tool"]["off_for_install"] is None
    assert rows.live() == []
    assert rows.stops[0]["on_reason"] == reason


def test_a_department_administrator_stops_a_tool_for_their_own_department_only(
    served: tuple[TestClient, Stub], rows: ToolRows
) -> None:
    """The owner's rule for a department administrator, and the refusals naming only the reader's
    own reach. Delete this and a department admin can stop another department's tools, or switch
    one off for the whole company."""
    client, stub = served
    own = switch(client, "u_narrow", UPDATE_NOTE, on=False, department="web")
    assert own.status_code == 200, own.text
    assert [(one["tool_name"], one["department"]) for one in rows.live()] == [(UPDATE_NOTE, "web")]
    written = len(stub.statements)
    for department in ("sales", None):
        refused = switch(client, "u_narrow", UPDATE_NOTE, on=False, department=department)
        assert refused.status_code == 404
        assert "sales" not in refused.json()["message"]
    assert len(stub.statements) == written
    assert len(rows.live()) == 1


def test_a_department_reader_sees_the_installs_switch_and_only_their_own_departments_stops(
    served: tuple[TestClient, Stub], rows: ToolRows
) -> None:
    """A stop on another department is a fact about how somebody else's work is governed. Delete
    this and a department's screen lists every department that has a stop, which is the filter
    list disclosure `brain.console.screens` names."""
    client, _ = served
    rows.stop(READ_NOTE, None)
    rows.stop(UPDATE_NOTE, "web")
    rows.stop(UPDATE_NOTE, "sales")
    narrow = client.get(SCREEN, headers=headers("u_narrow")).json()
    wide = client.get(SCREEN, headers=headers("u_admin")).json()
    shown = {one["name"]: one for one in narrow["tools"]}
    assert shown[READ_NOTE]["off_for_install"] is not None
    assert [one["department"] for one in shown[UPDATE_NOTE]["stopped_for"]] == ["web"]
    assert narrow["may_switch_install"] is False
    assert narrow["departments"] == ["web"]
    everything = {one["name"]: one for one in wide["tools"]}
    assert [one["department"] for one in everything[UPDATE_NOTE]["stopped_for"]] == [
        "sales",
        "web",
    ]


def test_a_stop_for_a_department_nobody_is_in_is_refused(
    served: tuple[TestClient, Stub], rows: ToolRows
) -> None:
    """A stop is compared with a caller's department, so a misspelt one stops nobody while the
    screen says it stopped somebody. Delete this and that stop is written and believed."""
    client, _ = served
    refused = switch(client, "u_admin", UPDATE_NOTE, on=False, department="finanse")
    assert refused.status_code == 404
    assert "nobody" in refused.json()["message"]
    assert rows.live() == []


def test_a_tool_this_install_does_not_register_is_refused_by_name(
    served: tuple[TestClient, Stub], rows: ToolRows
) -> None:
    """Delete this and a stop can be written for a name nothing calls, and read as a switch that
    worked."""
    client, _ = served
    refused = switch(client, "u_admin", "nothing.read_here", on=False)
    assert refused.status_code == 404
    assert "nothing.read_here" in refused.json()["message"]
    assert rows.live() == []


# ------------------------------------------------------------------------- the database
@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_tools_{uuid.uuid4().hex[:8]}") as url:
        if "agent.tool_switch" not in present_tables(url):
            pytest.skip("0117 is built only on the chain CI runs, where every table is")
        yield url


def person(url: str, pid: str, department: str) -> None:
    sql(
        url,
        "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department)"
        " VALUES (%s, 'human', 'staff', %s, %s)",
        pid,
        f"Person {pid}",
        department,
    )


def pressed[T](url: str, presses: Callable[[httpx.AsyncClient], Awaitable[T]]) -> T:
    """The application's own routes over this database as the application role, with the tool
    router and a registry of its own. No lifespan runs, so nothing is read from the environment."""

    async def go() -> T:
        built = app_engine(url)
        try:
            app = create_app(Settings(env="development"))
            app.include_router(tool_router)
            app.state.gate = gate_wiring(GRANTS)
            app.state.db_sessions = make_session_factory(built)
            app.state.console_reads = None
            app.state.tools = a_registry()
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://brain") as client:
                return await presses(client)
        finally:
            await built.dispose()

    return run(go)


def called_as(url: str, pid: str) -> bool:
    """Whether a call to the read tool, made for this person, runs through the real source."""

    async def go() -> bool:
        built = app_engine(url)
        try:
            registry = a_registry().govern(SessionSwitchSource(make_session_factory(built)))
            try:
                answered = registry.get(READ_NOTE).handler(
                    entitlement=EntitlementSet(principal_id=pid), now=LONG_AGO
                )
                await answered  # type: ignore[misc]
            except ToolSwitchedOffError:
                return False
            return True
        finally:
            await built.dispose()

    return run(go)


def post(client: httpx.AsyncClient, pid: str, body: Mapping[str, Any]) -> Awaitable[httpx.Response]:
    return client.post(f"{SCREEN}/{READ_NOTE}/switch", json=dict(body), headers=headers(pid))


def test_switching_through_the_routes_reaches_the_row_the_ledger_and_every_call(
    database: str,
) -> None:
    """M12.4.3 on PostgreSQL as the application role, end to end: the install switch refuses
    everybody's call and a `setting` entry names the administrator; switching back on lets them
    through and appends `on`; a department stop refuses that department's person and nobody
    else's. Delete this and the switch can be a table nothing a call ever reads."""
    for pid, department in (("u_admin", "web"), ("u_narrow", "web"), ("u_elsewhere", "sales")):
        person(database, pid, department)
    assert called_as(database, "u_narrow")

    async def off(c: httpx.AsyncClient) -> httpx.Response:
        return await post(c, "u_admin", {"on": False})

    assert pressed(database, off).status_code == 200
    assert not called_as(database, "u_narrow") and not called_as(database, "u_elsewhere")

    async def on(c: httpx.AsyncClient) -> httpx.Response:
        return await post(c, "u_admin", {"on": True, "reason": "the fault has been fixed"})

    assert pressed(database, on).status_code == 200
    assert called_as(database, "u_narrow")

    async def web(c: httpx.AsyncClient) -> httpx.Response:
        return await post(c, "u_narrow", {"on": False, "department": "web"})

    assert pressed(database, web).status_code == 200
    assert not called_as(database, "u_narrow")
    assert called_as(database, "u_elsewhere")

    changes = [e for e in entries(database, "setting") if e.subject.startswith("setting:tool_")]
    assert [(e.actor_id, e.details["change"], e.details["scope"]) for e in changes] == [
        ("u_admin", "off", "install"),
        ("u_admin", "on", "install"),
        ("u_narrow", "off", "department"),
    ]
    assert {e.details["tool"] for e in changes} == {READ_NOTE}
    assert changes[2].details["department_digest"] == hashlib.sha256(b"web").hexdigest()
    assert all(not e.trace_id.startswith("tx.") for e in changes)


def test_one_live_stop_per_tool_and_place_is_the_databases_rule_too(database: str) -> None:
    """Delete this and two stops for one place can arrive by a statement the routes never send,
    and switching the tool back on retires one of them and leaves it off."""
    sql(
        database,
        "INSERT INTO agent.tool_definition (name, source, entity, description,"
        " required_capability, side_effect, sensitive, result_contract, identity_mode)"
        " VALUES ('notes.read_note', 'notes', 'note', 'Read a note', 'read:note.text', 'none',"
        " false, 'typed', 'delegated')",
    )
    stop = (
        "INSERT INTO agent.tool_switch (tool_name, department, switched_off_by)"
        " VALUES (%s, %s, 'u')"
    )
    sql(database, stop, READ_NOTE, None)
    sql(database, stop, READ_NOTE, "web")
    for department in (None, "web"):
        with pytest.raises(Exception, match="uq_tool_switch_tool_name_department_live"):
            sql(database, stop, READ_NOTE, department)


@pytest.mark.parametrize("name", ["client.read", "Client.read_summary", "notes..read_note"])
def test_the_database_refuses_a_tool_name_outside_the_grammar(database: str, name: str) -> None:
    """The grammar held by the database as well as the registry. Delete this and the check can be
    dropped from the migration with every Python test still green."""
    with pytest.raises(Exception, match="ck_tool_definition_name_grammar"):
        sql(
            database,
            "INSERT INTO agent.tool_definition (name, source, entity, description,"
            " required_capability, side_effect, sensitive, result_contract, identity_mode)"
            " VALUES (%s, split_part(%s, '.', 1), 'note', 'd', 'read:note.text', 'none', false,"
            " 'typed', 'delegated')",
            name,
            name,
        )
