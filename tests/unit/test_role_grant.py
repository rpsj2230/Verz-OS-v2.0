"""Who holds a role, deputies, the Super Admin floor, the separation of duties, team grants.

The first half needs no server: `0102` read as the SQL it renders and held to the model and to the
rules it copies, the rules themselves, and the Roles routes over an in-memory store. The second
half builds a database through the migrations that ship, connected as the application role, and
proves each rule where a row can arrive another way: the guard refuses a deputy of a deputy and a
removal below the floor, the trigger audits an appointment with its acknowledgement, the routes
write through the real store, and a team's grant reaches its live members and no one else. **It
skips without a server**, which is CI's to provide.

Task ids: M1.3.2, M1.3.3, M1.3.4, M1.5.3, M1.8.7
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.app import Settings, create_app
from brain.console.reads import Plane, plane_capability
from brain.console.scoped_authority import REACH_AUTHORITY, may_appoint_role
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.db import metadata
from brain.identity import role_store
from brain.identity.role_store import Attribution, RoleRefusal, StoredRoles
from brain.identity.roles import (
    DEPUTY_MAX,
    SCOPE_REQUIRED,
    SEPARATION_OF_DUTIES_WARNING,
    SUPER_ADMIN_FLOOR,
    Role,
    RoleGrant,
    separation_crossed,
)
from brain.session import make_session_factory
from brain.tables.gate import TEAM_PATH_CHARS, TEAM_PATH_GRAMMAR
from brain.tables.identity import one_of
from brain.tables.role_grant import RoleGrantRow
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.http_client import Response
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_console_control_audit import pressed
from tests.unit.test_review_store import entries
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

MIGRATION = VERSIONS / "0102_role_grant_and_team_grants.py"
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
API = "/api/v1"

#: Far from any wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

WHOLE = Scope.unrestricted()
IN_WEB = Scope(clauses=(Clause(field="department", op=Op.EQ, value="web"),))
CONFIG = plane_capability(Plane.CONFIGURATION).value


def grant(value: str, scope: Scope = WHOLE) -> Grant:
    return Grant(capability=Capability(value=value), scope=scope)


#: The people the routes sign in, from the token fixture's own subjects.
GRANTS: Final[Mapping[str, tuple[Grant, ...]]] = {
    "u_admin": (
        grant(REACH_AUTHORITY.value),
        grant("read:role"),
        grant(CONFIG),
        grant("read:ticket"),
    ),
    "u_elsewhere": (
        grant(REACH_AUTHORITY.value, IN_WEB),
        grant("read:role", IN_WEB),
        grant(CONFIG, IN_WEB),
    ),
    "u_wide": (grant("read:role"), grant(CONFIG)),
    "u_none": (),
}


# ------------------------------------------------------------------- the migration
def module() -> Any:
    return migration_module(MIGRATION)


def test_the_migration_builds_the_role_table_exactly_as_the_model_declares_it() -> None:
    """The copy compared on rendered DDL. Delete this and the model can declare a check or a
    column the database never has, which is where M1.3.2's scope rule would silently lapse."""
    emitted = squash(rendered("upgrade", MIGRATION))
    table = metadata.tables["gate.role_grant"]
    assert squash(str(CreateTable(table).compile(dialect=DIALECT))) in emitted
    for index in table.indexes:
        assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted


def test_the_rules_the_migration_copies_are_the_rules_the_code_holds() -> None:
    """Each copied constant against the one it copies. Delete this and a sixth role, a longer
    deputy or a different floor is refused by one side and admitted by the other."""
    m = module()
    assert one_of("role", Role) == m.ROLES
    assert one_of("role", SCOPE_REQUIRED) in m.SCOPE_REQUIRED
    assert DEPUTY_MAX.days == m.DEPUTY_DAYS
    assert m.SUPER_ADMIN_FLOOR == SUPER_ADMIN_FLOOR
    assert m.ROLE_LOCK == role_store.ROLE_LOCK
    assert (m.TEAM_PATH_CHARS, m.TEAM_PATH_GRAMMAR) == (TEAM_PATH_CHARS, TEAM_PATH_GRAMMAR)


def test_the_downgrade_puts_back_exactly_the_functions_it_replaced() -> None:
    """The three replaced functions go back as `0003` and `0095` wrote them. Delete this and a
    rollback leaves a resolver or an audit trigger that no migration describes."""
    m = module()
    first = migration_module(VERSIONS / "0003_resolver_and_tables.py")
    partner = migration_module(VERSIONS / "0095_service_accounts_and_partner_reach.py")

    def replaced(text: str) -> str:
        return squash(text).replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")

    assert replaced(first.AUDIT_TRIGGER_FUNCTION) == squash(m.ENTITLEMENT_CHANGE_AS_0003_WROTE_IT)
    assert replaced(first.BUMP_FUNCTION) == squash(m.BUMP_AS_0003_WROTE_IT)
    assert squash(partner.HELD_GRANTS_WITH_PARTNER_WINDOW) == squash(m.HELD_GRANTS_AS_0095_WROTE_IT)
    down = squash(rendered("downgrade", MIGRATION))
    for text in (m.ENTITLEMENT_CHANGE_AS_0003_WROTE_IT, m.BUMP_AS_0003_WROTE_IT):
        assert squash(text) in down


def test_the_application_may_never_hard_delete_a_role_grant() -> None:
    """Revocation retires the row, for `0002`'s reason. Delete this and a role grant can vanish
    with its history."""
    emitted = squash(rendered("upgrade", MIGRATION))
    assert "ALTER TABLE gate.role_grant ENABLE ROW LEVEL SECURITY" in emitted
    grants = [one for one in emitted.split(";") if "GRANT" in one and "role_grant" in one]
    assert grants and not any("DELETE" in one for one in grants)


def test_the_alters_on_the_grant_table_are_the_amendments_the_model_comparison_believes() -> None:
    """`AMENDS_CREATE_TABLE` is a claim `tests/unit/test_tables.py` trusts. Delete this and it can
    say the principal is optional and the team column exists while the upgrade does neither."""
    emitted = squash(rendered("upgrade", MIGRATION))
    assert "ALTER TABLE gate.capability_grant ADD COLUMN team_path VARCHAR(121)" in emitted
    assert "ALTER TABLE gate.capability_grant ALTER COLUMN principal_id DROP NOT NULL" in emitted
    assert "CHECK (team_path IS NULL OR principal_id IS NULL)" in emitted
    assert "CHECK (principal_id IS NOT NULL OR team_path IS NOT NULL)" in emitted


# --------------------------------------------------------------------- the rules
def test_super_admin_and_connector_admin_are_separated_and_nothing_else_is() -> None:
    """M1.8.7's rule. Delete this and the warning can fire for every appointment, or for none."""
    assert separation_crossed([Role.CONNECTOR_ADMIN], Role.SUPER_ADMIN)
    assert separation_crossed([Role.SUPER_ADMIN], Role.CONNECTOR_ADMIN)
    assert not separation_crossed([Role.AUDITOR], Role.SUPER_ADMIN)
    assert not separation_crossed([Role.SUPER_ADMIN], Role.SUPER_ADMIN)
    assert not separation_crossed([], Role.CONNECTOR_ADMIN)


def role(principal: str, which: Role = Role.SUPER_ADMIN, scope: Scope | None = None) -> RoleGrant:
    return RoleGrant(
        principal_id=principal,
        role=which,
        scope=scope,
        granted_by="u_admin",
        reason="the job needs it",
        granted_at=LONG_AGO,
    )


def test_appointing_a_role_takes_the_authority_over_its_scope_and_never_oneself() -> None:
    """Delete this and a department's grant authority appoints a Super Admin, or anybody
    appoints themselves."""
    admin = EntitlementSet(principal_id="u_admin", grants=GRANTS["u_admin"])
    web = EntitlementSet(principal_id="u_elsewhere", grants=GRANTS["u_elsewhere"])
    assert may_appoint_role(role("u_2"), admin, "u_admin", LONG_AGO)
    assert not may_appoint_role(role("u_admin"), admin, "u_admin", LONG_AGO)
    assert not may_appoint_role(role("u_2"), web, "u_elsewhere", LONG_AGO)
    approver = role("u_2", Role.APPROVER, IN_WEB)
    assert may_appoint_role(approver, web, "u_elsewhere", LONG_AGO)


def test_a_company_wide_role_is_written_with_a_sql_null_scope_and_not_a_json_null() -> None:
    """A JSONB column stores Python None as the JSON value `null`, which is not SQL NULL, so the
    scope rule refused every Super Admin appointment in CI. Delete this and that comes back with
    every stubbed test green."""
    statement = role_store.adding(role("u_2"), None).compile(dialect=DIALECT)
    assert "scope" not in statement.params
    assert "NULL" in str(statement)
    scoped = role_store.adding(role("u_2", Role.APPROVER, IN_WEB), None).compile(dialect=DIALECT)
    assert scoped.params["scope"] == IN_WEB.model_dump(mode="json")


# ---------------------------------------------------------- the routes over a fake store
@dataclass
class Memory:
    """A `RoleRecords` in memory: the judge is asked about the rows as they stand, as the store."""

    rows: list[RoleGrantRow] = field(default_factory=list)
    retired: list[uuid.UUID] = field(default_factory=list)
    acknowledged: list[str | None] = field(default_factory=list)

    def add(self, grant: RoleGrant) -> RoleGrantRow:
        row = RoleGrantRow(
            id=uuid.uuid4(),
            principal_id=grant.principal_id,
            role=grant.role.value,
            scope=None if grant.scope is None else grant.scope.model_dump(mode="json"),
            deputy_of=grant.deputy_of,
            granted_by=grant.granted_by,
            reason=grant.reason,
            not_after=grant.not_after,
        )
        row.created_at = grant.granted_at
        row.deleted_at = None
        self.rows.append(row)
        return row

    async def holders(self, limit: int) -> list[tuple[RoleGrantRow, str | None]]:
        return [(one, "web") for one in self.rows]

    async def one(self, grant_id: uuid.UUID) -> RoleGrantRow | None:
        return next((one for one in self.rows if one.id == grant_id), None)

    async def appoint(
        self,
        grant: RoleGrant,
        *,
        acknowledgement: str | None,
        judge: Callable[[Sequence[RoleGrant]], RoleRefusal | None],
        by: Attribution,
    ) -> RoleGrantRow | RoleRefusal:
        held = [
            role_store.role_grant_of(one)
            for one in self.rows
            if one.principal_id == grant.principal_id
        ]
        refused = judge(held)
        if refused is not None:
            return refused
        self.acknowledged.append(acknowledgement)
        return self.add(grant)

    async def retire(
        self,
        grant_id: uuid.UUID,
        *,
        judge: Callable[[RoleGrant, Sequence[RoleGrant]], RoleRefusal | None],
        by: Attribution,
    ) -> datetime | RoleRefusal:
        row = await self.one(grant_id)
        if row is None:
            return RoleRefusal.NOT_WRITABLE
        refused = judge(
            role_store.role_grant_of(row), [role_store.role_grant_of(o) for o in self.rows]
        )
        if refused is not None:
            return refused
        self.rows.remove(row)
        self.retired.append(grant_id)
        return LONG_AGO


@pytest.fixture
def memory() -> Memory:
    return Memory()


@pytest.fixture
def client(memory: Memory) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = gate_wiring(GRANTS)
        app.state.role_records = memory
        app.state.db_sessions = None
        yield c


def post(c: TestClient, pid: str, path: str, body: Mapping[str, Any]) -> Response:
    response: Response = c.post(f"{API}{path}", json=dict(body), headers=headers(pid))
    return response


def appoint(c: TestClient, pid: str, principal: str, which: str, **extra: Any) -> Response:
    return post(
        c,
        pid,
        "/govern/roles/appointment",
        {"principal_id": principal, "role": which, "reason": "cover", **extra},
    )


def test_an_administrator_appoints_a_super_admin_and_the_screen_lists_them(
    client: TestClient, memory: Memory
) -> None:
    """M1.3.2 end to end over the routes. Delete this and every refusal below is satisfied by
    routes that write nothing."""
    answered = appoint(client, "u_admin", "u_2", "super_admin")
    assert answered.status_code == 201, answered.text
    listed = client.get(f"{API}/govern/roles/holders", headers=headers("u_admin")).json()
    assert [(one["principal_id"], one["role"]) for one in listed["items"]] == [
        ("u_2", "super_admin")
    ]
    assert listed["editable"] is True


def test_a_role_needing_a_scope_is_refused_without_one(client: TestClient, memory: Memory) -> None:
    """M1.3.2's scope rule at the route. Delete this and an unscoped Approver approves anything."""
    assert appoint(client, "u_admin", "u_2", "approver").status_code == 404
    assert memory.rows == []


def test_nobody_without_the_authority_appoints_or_removes(
    client: TestClient, memory: Memory
) -> None:
    """Delete this and a reader of the Roles screen can appoint a Super Admin."""
    existing = memory.add(role("u_2"))
    assert appoint(client, "u_wide", "u_3", "super_admin").status_code == 404
    assert appoint(client, "u_none", "u_3", "super_admin").status_code == 404
    assert appoint(client, "u_elsewhere", "u_3", "super_admin").status_code == 404
    removed = post(client, "u_wide", "/govern/roles/removal", {"grant_id": str(existing.id)})
    assert removed.status_code == 404
    assert [one.principal_id for one in memory.rows] == ["u_2"]


def test_appointing_a_connector_admin_as_super_admin_warns_until_acknowledged(
    client: TestClient, memory: Memory
) -> None:
    """M1.8.7. Delete this and one person can hold the credentials and appoint everybody with
    nothing said, or the acknowledgement can be dropped on its way to the row."""
    memory.add(role("u_2", Role.CONNECTOR_ADMIN))
    refused = appoint(client, "u_admin", "u_2", "super_admin")
    assert refused.status_code == 404
    assert SEPARATION_OF_DUTIES_WARNING in refused.json()["message"]
    assert len(memory.rows) == 1
    accepted = appoint(
        client, "u_admin", "u_2", "super_admin", acknowledgement="two-person company"
    )
    assert accepted.status_code == 201, accepted.text
    assert memory.acknowledged == ["two-person company"]


def test_the_last_two_super_admins_cannot_be_reduced_to_one(
    client: TestClient, memory: Memory
) -> None:
    """M1.3.4 at the route. Delete this and removing a Super Admin can leave one person as the
    only way back into the install."""
    first, _ = memory.add(role("u_2")), memory.add(role("u_3"))
    refused = post(client, "u_admin", "/govern/roles/removal", {"grant_id": str(first.id)})
    assert refused.status_code == 404
    assert "fewer than two" in refused.json()["message"]
    memory.add(role("u_4"))
    removed = post(client, "u_admin", "/govern/roles/removal", {"grant_id": str(first.id)})
    assert removed.status_code == 200, removed.text
    assert memory.retired == [first.id]


def test_a_deputy_covers_a_standing_holder_and_never_another_deputy(
    client: TestClient, memory: Memory
) -> None:
    """M1.3.3 at the route: bounded, depth one. Delete this and a deputy appoints a deputy, and
    a thirty-day delegation renews itself for ever."""
    standing = memory.add(role("u_2"))
    body = {"grant_id": str(standing.id), "principal_id": "u_3", "days": 30, "reason": "leave"}
    first = post(client, "u_admin", "/govern/roles/deputy", body)
    assert first.status_code == 201, first.text
    deputy = memory.rows[-1]
    assert deputy.deputy_of == "u_2"
    assert deputy.not_after is not None
    again = {"grant_id": str(deputy.id), "principal_id": "u_4", "days": 5, "reason": "leave"}
    assert post(client, "u_admin", "/govern/roles/deputy", again).status_code == 404
    too_long = {**body, "days": DEPUTY_MAX.days + 1}
    assert post(client, "u_admin", "/govern/roles/deputy", too_long).status_code == 422


# ------------------------------------------------------------------ against a database
@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_role_{uuid.uuid4().hex[:8]}") as url:
        yield url


def person(url: str, pid: str) -> None:
    sql(
        url,
        "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department)"
        " VALUES (%s, 'human', 'staff', %s, 'web')",
        pid,
        f"Person {pid}",
    )


def as_app(url: str, statement: str, *params: object) -> None:
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("SET ROLE brain_app")
        conn.execute(statement, params)


def standing(url: str, pid: str, which: str = "super_admin") -> str:
    [(grant_id,)] = sql(
        url,
        "INSERT INTO gate.role_grant (principal_id, role, granted_by, reason)"
        " VALUES (%s, %s, 'u_admin', 'r') RETURNING id",
        pid,
        which,
    )
    return str(grant_id)


def test_the_guard_refuses_a_removal_below_the_floor_and_allows_one_above_it(
    database: str,
) -> None:
    """M1.3.4 in the database, for a row changed by a statement the application never sends.
    Delete this and a hand-written UPDATE leaves an install with one Super Admin."""
    for pid in ("u_2", "u_3", "u_4"):
        person(database, pid)
    first = standing(database, "u_2")
    standing(database, "u_3")
    with pytest.raises(psycopg.errors.CheckViolation):
        as_app(
            database,
            "UPDATE gate.role_grant SET deleted_at = statement_timestamp() WHERE id = %s",
            first,
        )
    standing(database, "u_4")
    as_app(
        database,
        "UPDATE gate.role_grant SET deleted_at = statement_timestamp() WHERE id = %s",
        first,
    )
    assert sql(
        database, "SELECT deleted_at IS NOT NULL FROM gate.role_grant WHERE id = %s", first
    ) == [(True,)]


def test_the_guard_keeps_deputies_depth_one_and_the_table_keeps_them_bounded(database: str) -> None:
    """M1.3.3 in the database. Delete this and a deputy of a deputy, or a deputy for a year, is a
    row somebody can write by hand."""
    for pid in ("u_2", "u_3", "u_4"):
        person(database, pid)
    standing(database, "u_2")
    later = LONG_AGO.replace(year=2999)
    sql(
        database,
        "INSERT INTO gate.role_grant (principal_id, role, deputy_of, granted_by, reason, not_after)"
        " VALUES ('u_3', 'super_admin', 'u_2', 'u_admin', 'r', now() + interval '10 days')",
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        sql(
            database,
            "INSERT INTO gate.role_grant (principal_id, role, deputy_of, granted_by, reason,"
            " not_after) VALUES ('u_4', 'super_admin', 'u_3', 'u_admin', 'r', now() + interval"
            " '10 days')",
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        sql(
            database,
            "INSERT INTO gate.role_grant (principal_id, role, deputy_of, granted_by, reason,"
            " not_after) VALUES ('u_4', 'super_admin', 'u_2', 'u_admin', 'r', %s)",
            later,
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        sql(
            database,
            "INSERT INTO gate.role_grant (principal_id, role, granted_by, reason)"
            " VALUES ('u_4', 'approver', 'u_admin', 'r')",
        )


def test_an_appointment_through_the_routes_reaches_the_row_and_the_ledger_with_its_reason(
    database: str,
) -> None:
    """M1.8.7 and M1.3.2 on PostgreSQL through the application's own routes: the warning, then the
    acknowledged appointment, whose row carries the reason and whose `grant` entry names the role,
    the appointer and the acknowledgement; then a removal and its `revoke` entry. Delete this and
    the acknowledgement can reach neither."""
    for pid in ("u_2", "u_3", "u_4"):
        person(database, pid)
    standing(database, "u_3")
    standing(database, "u_4")
    connector = standing(database, "u_2", "connector_admin")

    async def go(c: httpx.AsyncClient) -> list[httpx.Response]:
        body = {"principal_id": "u_2", "role": "super_admin", "reason": "cover"}
        done = [
            await c.post(f"{API}/govern/roles/appointment", json=body, headers=headers("u_admin"))
        ]
        acknowledged = {**body, "acknowledgement": "a company of two"}
        done.append(
            await c.post(
                f"{API}/govern/roles/appointment", json=acknowledged, headers=headers("u_admin")
            )
        )
        done.append(
            await c.post(
                f"{API}/govern/roles/removal",
                json={"grant_id": connector},
                headers=headers("u_admin"),
            )
        )
        return done

    answers = pressed(database, GRANTS, go)
    rows = sql(
        database,
        "SELECT role, acknowledgement, granted_by FROM gate.role_grant"
        " WHERE principal_id = 'u_2' AND deleted_at IS NULL",
    )
    granted = [e for e in entries(database, "grant") if e.details.get("acknowledged")]
    revoked = [e for e in entries(database, "revoke") if e.subject == "principal:u_2"]

    assert [one.status_code for one in answers] == [404, 201, 200], [a.text for a in answers]
    assert rows == [("super_admin", "a company of two", "u_admin")]
    assert [(e.actor_id, e.subject, e.details["role"]) for e in granted] == [
        ("u_admin", "principal:u_2", "super_admin")
    ]
    assert granted[0].details["acknowledged"] == "separation_of_duties"
    # The reason is on the row; the ledger holds its digest, never the free text (M1.8.7).
    assert (
        granted[0].details["acknowledgement_digest"]
        == hashlib.sha256(b"a company of two").hexdigest()
    )
    assert "acknowledgement" not in granted[0].details
    assert [(e.actor_id, e.details["role"]) for e in revoked] == [("u_admin", "connector_admin")]


def test_the_store_refuses_the_floor_it_is_asked_to_judge(database: str) -> None:
    """The store's own path for M1.3.4: the judge sees every live grant under the lock. Delete this
    and a judge handed a stale page can remove the second-last Super Admin."""
    for pid in ("u_2", "u_3"):
        person(database, pid)
    first = standing(database, "u_2")
    standing(database, "u_3")

    async def go() -> Any:
        engine = app_engine(database)
        try:
            store = StoredRoles(make_session_factory(engine))

            def judge(target: RoleGrant, every: Sequence[RoleGrant]) -> RoleRefusal | None:
                return None

            return await store.retire(
                uuid.UUID(first),
                judge=judge,
                by=Attribution("u_admin", "a" * 32, "t"),
            )
        finally:
            await engine.dispose()

    assert run(go) is RoleRefusal.FLOOR


def resolved(url: str, pid: str) -> set[str]:
    [(held,)] = sql(url, "SELECT gate.resolve_entitlements(%s, now())", pid)
    return {one["capability"]["value"] for one in held["grants"]}


def version(url: str, pid: str) -> int:
    found = sql(url, "SELECT version FROM gate.grants_version WHERE principal_id = %s", pid)
    return int(found[0][0]) if found else 0


def test_a_teams_grant_reaches_its_live_members_and_moves_their_version(database: str) -> None:
    """M1.5.3 on PostgreSQL: one row whose subject is a team; a member holds it, a non-member does
    not, a member who leaves stops holding it, and each change moves the version a cached reach is
    keyed on. Delete this and a team grant is a row the resolver never reads."""
    for pid in ("u_2", "u_3", "u_4"):
        person(database, pid)
    [(department,)] = sql(
        database,
        "INSERT INTO gate.department (company_id, slug, name, scope_slug)"
        " VALUES ('company', 'web', 'Web', 'web') RETURNING id",
    )
    [(team,)] = sql(
        database,
        "INSERT INTO gate.team (department_id, slug, name) VALUES (%s, 'design', 'Design')"
        " RETURNING id",
        department,
    )
    for pid in ("u_2", "u_3"):
        sql(
            database,
            "INSERT INTO gate.team_membership (team_id, principal_id, added_by)"
            " VALUES (%s, %s, 'u_admin')",
            team,
            pid,
        )
    sql(
        database,
        "INSERT INTO gate.scope (slug, predicate, is_department, label)"
        " VALUES ('web', '{\"department\": \"web\"}', true, 'Web')",
    )
    before = version(database, "u_2")

    async def go(c: httpx.AsyncClient) -> list[httpx.Response]:
        body = {
            "team_path": "web.design",
            "capability": "read:ticket",
            "scope_slug": "web",
            "reason": "the team needs it",
        }
        done = [await c.post(f"{API}/govern/grants", json=body, headers=headers("u_admin"))]
        missing = {**body, "team_path": "web.nobody"}
        done.append(await c.post(f"{API}/govern/grants", json=missing, headers=headers("u_admin")))
        return done

    answers = pressed(database, GRANTS, go)
    granted = version(database, "u_2")
    sql(
        database,
        "UPDATE gate.team_membership SET ended_at = now(), ended_by = 'u_admin'"
        " WHERE principal_id = 'u_3'",
    )
    team_entries = [e for e in entries(database, "grant") if e.details.get("team")]

    assert [one.status_code for one in answers] == [201, 404], [a.text for a in answers]
    assert granted > before
    assert "read:ticket" in resolved(database, "u_2")
    assert "read:ticket" not in resolved(database, "u_3")
    assert "read:ticket" not in resolved(database, "u_4")
    assert [e.details["team"] for e in team_entries] == ["web.design"]
    with pytest.raises(psycopg.errors.CheckViolation):
        sql(
            database,
            "INSERT INTO gate.capability_grant (principal_id, team_path, capability, scope,"
            " granted_by, reason) VALUES ('u_4', 'web.design', 'read:x', %s, 'u_admin', 'r')",
            IN_WEB.model_dump_json(),
        )
