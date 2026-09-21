"""Group and role sync from the identity provider: the rules, the sync, and the Roles routes.

The first half needs no server: `0109` held to the model and to the rules it copies, the plan a
sign-in applies, the memory that keeps an unchanged token from opening a transaction on every
request, the token authority handing each interactive sign-in's groups over, and the routes over
an in-memory store. The second half builds a database through the migrations that ship,
connected as the application role, and proves the writes and their ledger entries. **It skips
without a server**, which is CI's to provide.

Task ids: M1.1.5
"""

from __future__ import annotations

import dataclasses
import hashlib
import uuid
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import TextClause, create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.app import Settings, create_app
from brain.console.reads import Plane, plane_capability
from brain.console.scoped_authority import REACH_AUTHORITY
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Clause, Op, Scope
from brain.db import metadata
from brain.group_rule_routes import ALREADY_MAPPED
from brain.identity import group_sync
from brain.identity.directory import (
    DirectoryAssertion,
    Reconciliation,
    assert_reconciler_cannot_reach_hand_made_grants,
)
from brain.identity.group_sync import (
    REFRESH_EVERY,
    SYNC_ACTOR,
    GroupSync,
    StoredGroupRules,
    conferred_by,
    plan_for,
)
from brain.identity.oidc import GroupRoleRule
from brain.identity.roles import SCOPE_REQUIRED, IdentityError, Role
from brain.session import make_session_factory
from brain.tables.group_role_rule import GROUP_CHARS, GroupRoleRuleRow
from brain.tables.identity import DirectoryRoleGrantRow, one_of
from tests.fixtures.console_http import SECOND_FACTOR, gate_wiring, headers
from tests.fixtures.http_client import Response
from tests.fixtures.retirable import retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_api_routes import token_for
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_console_control_audit import pressed
from tests.unit.test_review_store import entries
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

MIGRATION = VERSIONS / "0109_group_role_rule.py"
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
API = "/api/v1"

#: Far from any wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

WHOLE = Scope.unrestricted()
IN_WEB = Scope(clauses=(Clause(field="department", op=Op.EQ, value="web"),))
CONFIG = plane_capability(Plane.CONFIGURATION).value
AUDITORS = "/brain/auditor"
ADMINS = "/brain/super_admin"


def grant(value: str, scope: Scope = WHOLE) -> Grant:
    return Grant(capability=Capability(value=value), scope=scope)


GRANTS: Final[Mapping[str, tuple[Grant, ...]]] = {
    "u_admin": (grant(REACH_AUTHORITY.value), grant("read:role"), grant(CONFIG)),
    "u_elsewhere": (
        grant(REACH_AUTHORITY.value, IN_WEB),
        grant("read:role", IN_WEB),
        grant(CONFIG, IN_WEB),
    ),
    "u_wide": (grant("read:role"), grant(CONFIG)),
    "u_none": (),
}


def said(who: str, role: Role, group: str) -> DirectoryAssertion:
    return DirectoryAssertion(principal_id=who, role=role, source_group=group)


RULES = (
    GroupRoleRule(group=AUDITORS, role=Role.AUDITOR),
    GroupRoleRule(group=ADMINS, role=Role.SUPER_ADMIN),
)


# ------------------------------------------------------------------- the migration
def module() -> Any:
    return migration_module(MIGRATION)


def test_the_migration_builds_the_rule_table_exactly_as_the_model_declares_it() -> None:
    """The copy compared on rendered DDL. Delete this and the model can declare a check the
    database never has, which is where the one-rule-per-group index would silently lapse."""
    emitted = squash(rendered("upgrade", MIGRATION))
    table = metadata.tables["auth.group_role_rule"]
    assert squash(str(CreateTable(table).compile(dialect=DIALECT))) in emitted
    for index in table.indexes:
        assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted


def test_the_rules_the_migration_copies_are_the_rules_the_code_holds() -> None:
    """Each copied constant against the one it copies, and the actor against the ledger's
    identifier grammar. Delete this and a seventh role, a wider group or a renamed actor is
    refused by one side and admitted by the other."""
    m = module()
    assert one_of("role", Role) == m.ROLES
    assert one_of("role", SCOPE_REQUIRED) in m.SCOPE_REQUIRED
    assert m.GROUP_CHARS == GROUP_CHARS
    GroupRoleRule(group="g" * GROUP_CHARS, role=Role.AUDITOR)
    with pytest.raises(ValueError, match="at most"):
        GroupRoleRule(group="g" * (GROUP_CHARS + 1), role=Role.AUDITOR)
    assert m.SYNC_ACTOR == SYNC_ACTOR
    assert f"'{SYNC_ACTOR}'" in m.SYNC_AUDIT_FUNCTION


def test_the_application_may_never_hard_delete_a_rule() -> None:
    """A retired rule stays as history. Delete this and a DELETE grant can land on the table the
    audit trail of who mapped what depends on."""
    m = module()
    assert all("DELETE" not in statement for statement in m.GRANTS)
    assert "ENABLE ROW LEVEL SECURITY" in m.RLS[0]


def test_the_synced_table_is_audited_on_insert_and_delete_and_not_on_a_touch() -> None:
    """A grant and a revoke entry for every synced row, and none for `last_seen_at`. Delete this
    and the record that the directory once asserted a role, which `0006` sends to the ledger, is
    written by nothing again."""
    m = module()
    trigger = squash(m.SYNC_AUDIT_TRIGGER)
    assert "AFTER INSERT OR DELETE ON auth.directory_role_grant" in trigger
    assert "UPDATE" not in trigger
    body = squash(m.SYNC_AUDIT_FUNCTION)
    assert "'source', 'directory'" in body
    # The group is a digest: a group path is not a name the ledger may hold.
    assert "'group_digest', encode(sha256(convert_to(v_group, 'UTF8')), 'hex')" in body


# ------------------------------------------------------------------- the plan
def test_joining_a_mapped_group_adds_its_role_and_an_unmapped_group_adds_nothing() -> None:
    """The additive half of M1.1.5. Delete this and a sync that writes nothing, or one that turns
    every group in a client's directory into a row, passes."""
    plan = plan_for("u_2", [AUDITORS, "/somebody/else"], RULES, held=())
    assert plan.to_insert == {said("u_2", Role.AUDITOR, AUDITORS)}
    assert plan.to_delete == frozenset()


def test_leaving_a_group_deletes_exactly_the_row_it_conferred() -> None:
    """Revocation is deletion of the synced grant when the membership disappears. Delete this
    and leaving a group never takes the role away, or takes the other group's row with it."""
    held = (said("u_2", Role.AUDITOR, AUDITORS), said("u_2", Role.SUPER_ADMIN, ADMINS))
    plan = plan_for("u_2", [ADMINS], RULES, held)
    assert plan.to_delete == {said("u_2", Role.AUDITOR, AUDITORS)}
    assert plan.unchanged == {said("u_2", Role.SUPER_ADMIN, ADMINS)}
    assert plan.to_insert == frozenset()


def test_a_sign_in_with_no_groups_removes_every_row_the_person_held() -> None:
    """`A_SIGN_IN_WITHOUT_GROUPS_IS_A_PERSON_IN_NO_GROUP`. Delete this and leaving your last
    group, which drops the claim from the token, never removes anything."""
    held = (said("u_2", Role.AUDITOR, AUDITORS),)
    assert plan_for("u_2", [], RULES, held).to_delete == set(held)


def test_a_plan_refuses_rows_that_belong_to_somebody_else() -> None:
    """Delete this and a caller handing the whole table to one person's sign-in deletes every
    other person's synced grants, none of which that token asserts."""
    with pytest.raises(IdentityError):
        plan_for("u_2", [AUDITORS], RULES, (said("u_3", Role.AUDITOR, AUDITORS),))


def test_the_sync_has_nowhere_to_put_a_hand_made_grant() -> None:
    """Entitlements are additive only: the sync cannot name a row in `gate.role_grant`. Delete
    this and a parameter taking a `RoleGrant` can be added to the plan with nothing noticing."""
    assert_reconciler_cannot_reach_hand_made_grants(plan_for)
    assert_reconciler_cannot_reach_hand_made_grants(conferred_by)


def test_retiring_a_rule_takes_every_row_it_conferred_and_no_other() -> None:
    """`RETIRING_A_RULE_REMOVES_WHAT_IT_CONFERRED`. Delete this and a retired rule leaves its
    role with everybody who does not sign in again, or takes another group's rows with it."""
    held = (
        said("u_2", Role.AUDITOR, AUDITORS),
        said("u_3", Role.AUDITOR, AUDITORS),
        said("u_3", Role.SUPER_ADMIN, ADMINS),
    )
    assert conferred_by(AUDITORS, held) == set(held[:2])


# ------------------------------------------------------------------ the memory
@dataclass
class Applied:
    """An `Applies` that records each run and plans against rows it holds."""

    rows: set[DirectoryAssertion] = field(default_factory=set)
    runs: list[tuple[str, frozenset[str]]] = field(default_factory=list)

    async def apply(
        self, principal_id: str, groups: Iterable[str], *, trace_id: str = ""
    ) -> Reconciliation:
        mine = {one for one in self.rows if one.principal_id == principal_id}
        plan = plan_for(principal_id, groups, RULES, mine)
        self.rows = (self.rows - plan.to_delete) | plan.to_insert
        self.runs.append((principal_id, frozenset(groups)))
        return plan


def test_an_unchanged_token_is_not_applied_again_until_the_refresh_and_a_change_is_at_once() -> (
    None
):
    """Delete this and either every request opens a transaction, or a group removed in the
    identity provider is ignored until the refresh, or a rule added is never applied to
    somebody already signed in."""
    store = Applied()
    sync = GroupSync(store)

    async def go() -> None:
        await sync.observe("u_2", [AUDITORS], now=LONG_AGO)
        await sync.observe("u_2", [AUDITORS], now=LONG_AGO + timedelta(minutes=1))
        await sync.observe("u_2", [], now=LONG_AGO + timedelta(minutes=2))
        await sync.observe("u_2", [], now=LONG_AGO + timedelta(minutes=2) + REFRESH_EVERY)

    run(go)
    assert [groups for _, groups in store.runs] == [
        frozenset({AUDITORS}),
        frozenset(),
        frozenset(),
    ]
    assert store.rows == set()


def test_the_refresh_is_short_enough_to_reach_somebody_signed_in_the_same_morning() -> None:
    """The bound a newly added rule waits, against the thirty-day deputy maximum's order of
    magnitude rather than itself. Delete this and a refresh of a day passes."""
    assert timedelta(0) < REFRESH_EVERY <= timedelta(minutes=15)


# --------------------------------------------------------------- at sign-in
@dataclass
class Observer:
    seen: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    fails: bool = False

    async def observe(self, principal_id: str, groups: Sequence[str], *, now: datetime) -> None:
        if self.fails:
            raise RuntimeError("the database went away")
        self.seen.append((principal_id, tuple(groups)))


def _authenticate(observer: Observer, claims: Mapping[str, object]) -> str:
    authority = dataclasses.replace(gate_wiring(GRANTS).authority, memberships=observer)

    async def go() -> str:
        caller = await authority.authenticate(
            f"Bearer {token_for('u_admin', claims=claims)}", now=datetime.now(UTC)
        )
        return caller.principal.id

    return run(go)


def test_an_interactive_sign_in_hands_its_groups_to_the_sync() -> None:
    """The wiring M1.1.5 was missing: nothing read the groups claim for a sync. Delete this and
    the rules can be configured and never applied to anybody."""
    observer = Observer()
    assert _authenticate(observer, {**SECOND_FACTOR, "groups": [AUDITORS, 7]}) == "u_admin"
    assert observer.seen == [("u_admin", (AUDITORS,))]


def test_a_token_from_no_session_is_not_synced() -> None:
    """A service account's token names no session and is not a person in a directory group.
    Delete this and a machine credential carrying a groups claim confers roles."""
    observer = Observer()
    _authenticate(observer, {"sid": None, "groups": [AUDITORS]})
    assert observer.seen == []


def test_a_sync_that_fails_does_not_refuse_the_sign_in() -> None:
    """`A_GROUP_SYNC_FAILURE_DOES_NOT_REFUSE_A_SIGN_IN`. Delete this and a hiccup in a side table
    refuses every sign-in in the company."""
    assert _authenticate(Observer(fails=True), {**SECOND_FACTOR, "groups": []}) == "u_admin"


# --------------------------------------------------------------- the routes
@dataclass
class Memory:
    """A `GroupRuleRecords` in memory, which deletes what a retired rule conferred."""

    rules_held: list[GroupRoleRuleRow] = field(default_factory=list)
    synced_rows: list[DirectoryRoleGrantRow] = field(default_factory=list)
    attributed: list[Sequence[TextClause]] = field(default_factory=list)

    async def rules(self) -> list[GroupRoleRuleRow]:
        return [one for one in self.rules_held if one.deleted_at is None]

    async def synced(self, limit: int) -> list[tuple[DirectoryRoleGrantRow, str | None]]:
        return [
            (one, "web" if one.principal_id == "u_web" else "sales") for one in self.synced_rows
        ]

    async def one(self, rule_id: uuid.UUID) -> GroupRoleRuleRow | None:
        return next((o for o in await self.rules() if o.id == rule_id), None)

    async def add(
        self,
        rule: GroupRoleRule,
        *,
        reason: str,
        created_by: str,
        attributed: Sequence[TextClause],
    ) -> GroupRoleRuleRow | None:
        if any(one.idp_group == rule.group for one in await self.rules()):
            return None
        row = GroupRoleRuleRow(
            id=uuid.uuid4(),
            idp_group=rule.group,
            role=rule.role.value,
            scope=None if rule.scope is None else rule.scope.model_dump(mode="json"),
            created_by=created_by,
            reason=reason,
        )
        row.created_at = LONG_AGO
        row.deleted_at = None
        self.rules_held.append(row)
        self.attributed.append(attributed)
        return row

    async def retire(
        self, rule_id: uuid.UUID, *, attributed: Sequence[TextClause]
    ) -> tuple[datetime, int] | None:
        row = await self.one(rule_id)
        if row is None:
            return None
        row.deleted_at = LONG_AGO
        gone = [one for one in self.synced_rows if one.source_group == row.idp_group]
        self.synced_rows = [one for one in self.synced_rows if one not in gone]
        self.attributed.append(attributed)
        return LONG_AGO, len(gone)

    def sync(self, who: str, role: Role, group: str) -> None:
        row = DirectoryRoleGrantRow(
            principal_id=who, role=role.value, source_group=group, last_seen_at=LONG_AGO
        )
        row.created_at = LONG_AGO
        self.synced_rows.append(row)


@pytest.fixture
def memory() -> Memory:
    return Memory()


@pytest.fixture
def client(memory: Memory) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = gate_wiring(GRANTS)
        app.state.group_rules = memory
        app.state.db_sessions = None
        yield c


def post(
    c: TestClient, pid: str, path: str, body: Mapping[str, Any], *, groups: Sequence[str] = ()
) -> Response:
    token = token_for(pid, claims={**SECOND_FACTOR, "groups": list(groups)})
    response: Response = c.post(
        f"{API}{path}", json=dict(body), headers={"authorization": f"Bearer {token}"}
    )
    return response


def mapping(c: TestClient, pid: str, group: str, role: str, **extra: Any) -> Response:
    body = {"idp_group": group, "role": role, "reason": "the directory says so", **extra}
    return post(c, pid, "/govern/roles/group-rules", body)


def test_an_administrator_maps_a_group_and_the_screen_lists_it(
    client: TestClient, memory: Memory
) -> None:
    """The mapping configuration end to end over the routes, attributed. Delete this and every
    refusal below is satisfied by routes that store nothing."""
    answered = mapping(client, "u_admin", AUDITORS, "auditor")
    assert answered.status_code == 201, answered.text
    listed = client.get(f"{API}/govern/roles/group-rules", headers=headers("u_admin")).json()
    assert [(one["idp_group"], one["role"]) for one in listed["rules"]] == [(AUDITORS, "auditor")]
    assert listed["editable"] is True
    assert len(memory.attributed) == 1
    assert len(memory.attributed[0]) == 3


def test_nobody_without_the_authority_maps_or_retires(client: TestClient, memory: Memory) -> None:
    """Mapping a group is appointing everybody in it. Delete this and a reader of the Roles
    screen makes a whole directory group Super Admin."""
    assert mapping(client, "u_wide", ADMINS, "super_admin").status_code == 404
    assert mapping(client, "u_elsewhere", ADMINS, "super_admin").status_code == 404
    assert memory.rules_held == []
    mapping(client, "u_admin", ADMINS, "super_admin")
    rule_id = str(memory.rules_held[0].id)
    retired = post(client, "u_wide", "/govern/roles/group-rules/retirement", {"rule_id": rule_id})
    assert retired.status_code == 404
    assert memory.rules_held[0].deleted_at is None


def test_a_caller_cannot_map_a_group_their_own_token_carries(
    client: TestClient, memory: Memory
) -> None:
    """Never about oneself, as an appointment is never of oneself. Delete this and an
    administrator makes themselves Super Admin through the group they sit in."""
    body = {"idp_group": ADMINS, "role": "super_admin", "reason": "me"}
    refused = post(client, "u_admin", "/govern/roles/group-rules", body, groups=[ADMINS])
    assert refused.status_code == 404
    assert memory.rules_held == []


def test_a_role_needing_a_scope_is_refused_without_one(client: TestClient, memory: Memory) -> None:
    """M1.3.2's scope rule reaches the mapping. Delete this and a group makes an unscoped
    Approver who approves anything in the company."""
    assert mapping(client, "u_admin", "/brain/approver", "approver").status_code == 404
    assert memory.rules_held == []


def test_a_group_already_mapped_is_refused_with_a_sentence(
    client: TestClient, memory: Memory
) -> None:
    """One live rule per group, said to the administrator who asked. Delete this and a second
    rule for one group is a 201 that the database then refuses as a failure."""
    mapping(client, "u_admin", AUDITORS, "auditor")
    again = mapping(client, "u_admin", AUDITORS, "super_admin")
    assert again.status_code == 404
    assert ALREADY_MAPPED in again.text


def test_retiring_a_rule_removes_what_it_conferred_and_the_screen_says_so(
    client: TestClient, memory: Memory
) -> None:
    """The route half of revocation. Delete this and a retired rule's synced grants stay on the
    screen and with their holders."""
    mapping(client, "u_admin", AUDITORS, "auditor")
    memory.sync("u_web", Role.AUDITOR, AUDITORS)
    before = client.get(f"{API}/govern/roles/group-rules", headers=headers("u_admin")).json()
    assert [one["principal_id"] for one in before["synced"]] == ["u_web"]
    rule_id = str(memory.rules_held[0].id)
    retired = post(client, "u_admin", "/govern/roles/group-rules/retirement", {"rule_id": rule_id})
    assert retired.status_code == 200, retired.text
    after = client.get(f"{API}/govern/roles/group-rules", headers=headers("u_admin")).json()
    assert after["rules"] == []
    assert after["synced"] == []


def test_the_synced_grants_are_narrowed_to_where_the_reader_may_look(
    client: TestClient, memory: Memory
) -> None:
    """A department admin sees the synced holders in their department and nobody else's, with no
    count of the rest. Delete this and the screen lists every Super Admin to anybody."""
    mapping(client, "u_admin", AUDITORS, "auditor")
    memory.sync("u_web", Role.AUDITOR, AUDITORS)
    memory.sync("u_sales", Role.AUDITOR, AUDITORS)
    wide = client.get(f"{API}/govern/roles/group-rules", headers=headers("u_admin")).json()
    narrow = client.get(f"{API}/govern/roles/group-rules", headers=headers("u_elsewhere")).json()
    assert sorted(one["principal_id"] for one in wide["synced"]) == ["u_sales", "u_web"]
    assert [one["principal_id"] for one in narrow["synced"]] == ["u_web"]
    assert set(narrow) == {"rules", "synced", "editable"}


def test_a_reader_with_no_grant_is_refused_the_mapping(client: TestClient) -> None:
    """Delete this and the list of which groups confer Super Admin is answerable to anybody."""
    answered = client.get(f"{API}/govern/roles/group-rules", headers=headers("u_none"))
    assert answered.status_code == 404


# ------------------------------------------------------------------ the database
@pytest.fixture
def database() -> Iterator[str]:
    with retirable(f"brain_groups_{uuid.uuid4().hex[:8]}") as url:
        yield url


def person(url: str, pid: str) -> None:
    sql(
        url,
        "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department)"
        " VALUES (%s, 'human', 'staff', %s, 'web')",
        pid,
        f"Person {pid}",
    )


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_a_sign_in_writes_and_removes_synced_rows_and_the_ledger_records_both(
    database: str,
) -> None:
    """M1.1.5 on PostgreSQL as the application role: a rule, a sign-in carrying its group writes
    the row and a `grant` entry naming the sync, and a sign-in without it deletes the row and
    writes a `revoke`. Delete this and the sync can be a pure function nothing ever runs."""
    person(database, "u_2")
    sql(
        database,
        "INSERT INTO auth.group_role_rule (idp_group, role, created_by, reason)"
        " VALUES (%s, 'auditor', 'u_admin', 'r')",
        AUDITORS,
    )

    async def go() -> tuple[Reconciliation, Reconciliation]:
        engine = app_engine(database)
        try:
            store = StoredGroupRules(make_session_factory(engine))
            joined = await store.apply("u_2", [AUDITORS, "/unmapped"])
            left = await store.apply("u_2", [])
            return joined, left
        finally:
            await engine.dispose()

    joined, left = run(go)
    assert joined.to_insert == {said("u_2", Role.AUDITOR, AUDITORS)}
    assert left.to_delete == {said("u_2", Role.AUDITOR, AUDITORS)}
    assert sql(database, "SELECT count(*) FROM auth.directory_role_grant") == [(0,)]
    granted = [e for e in entries(database, "grant") if e.details.get("source") == "directory"]
    revoked = [e for e in entries(database, "revoke") if e.details.get("source") == "directory"]
    for found in (granted, revoked):
        assert [(e.actor_id, e.subject, e.details["role"]) for e in found] == [
            (SYNC_ACTOR, "principal:u_2", "auditor")
        ]
        assert found[0].details["group_digest"] == digest(AUDITORS)


def test_mapping_and_retiring_through_the_routes_reach_the_rows_and_the_ledger(
    database: str,
) -> None:
    """The console write followed to its row, its `setting` entry naming the administrator, and
    its behaviour: retiring deletes every synced row the rule conferred, each with a `revoke`.
    Delete this and the mapping screen can store rules nothing audits or honours."""
    for pid in ("u_2", "u_3"):
        person(database, pid)

    async def go(c: httpx.AsyncClient) -> list[httpx.Response]:
        body = {"idp_group": AUDITORS, "role": "auditor", "reason": "from the directory"}
        added = await c.post(
            f"{API}/govern/roles/group-rules", json=body, headers=headers("u_admin")
        )
        return [added]

    [added] = pressed(database, GRANTS, go)
    assert added.status_code == 201, added.text
    rule_id = added.json()["id"]

    async def sign_ins() -> None:
        engine = app_engine(database)
        try:
            store = StoredGroupRules(make_session_factory(engine))
            await store.apply("u_2", [AUDITORS])
            await store.apply("u_3", [AUDITORS])
        finally:
            await engine.dispose()

    run(sign_ins)
    assert sql(database, "SELECT count(*) FROM auth.directory_role_grant") == [(2,)]

    async def retire(c: httpx.AsyncClient) -> list[httpx.Response]:
        return [
            await c.post(
                f"{API}/govern/roles/group-rules/retirement",
                json={"rule_id": rule_id},
                headers=headers("u_admin"),
            )
        ]

    [retired] = pressed(database, GRANTS, retire)
    assert retired.status_code == 200, retired.text
    assert sql(database, "SELECT count(*) FROM auth.directory_role_grant") == [(0,)]
    changes = [e for e in entries(database, "setting") if e.subject.startswith("setting:group_")]
    assert [(e.actor_id, e.details["change"], e.details["role"]) for e in changes] == [
        ("u_admin", "added", "auditor"),
        ("u_admin", "retired", "auditor"),
    ]
    assert changes[0].details["group_digest"] == digest(AUDITORS)
    revoked = [e for e in entries(database, "revoke") if e.details.get("source") == "directory"]
    assert sorted(e.subject for e in revoked) == ["principal:u_2", "principal:u_3"]
    assert {e.actor_id for e in revoked} == {"u_admin"}


def test_one_live_rule_per_group_is_the_databases_rule_too(database: str) -> None:
    """Delete this and two rules for one group can arrive by a statement the routes never send,
    and the sync reads whichever it met first."""
    first = (
        "INSERT INTO auth.group_role_rule (idp_group, role, created_by, reason)"
        " VALUES (%s, %s, 'u_admin', 'r')"
    )
    sql(database, first, AUDITORS, "auditor")
    with pytest.raises(Exception, match="uq_group_role_rule_idp_group_live"):
        sql(database, first, AUDITORS, "super_admin")


def test_the_store_module_names_the_lock_it_takes() -> None:
    """The lock is the store's own number and not the role grant lock or the ledger's. Delete
    this and a shared number serialises unrelated writes, or a copied one serialises nothing."""
    from brain.identity.role_store import ROLE_LOCK

    assert group_sync.GROUP_LOCK not in {ROLE_LOCK, 8274419004}
