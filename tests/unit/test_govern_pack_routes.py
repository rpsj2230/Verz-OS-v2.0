"""Pack assignment and the Approver misconfiguration flag, over HTTP and against a database.

Driven through the real application with a stub session for the refusals and the statement order,
the pattern `tests/unit/test_govern_routes.py` argues for, and through PostgreSQL for the three
places an assignment must reach: the row, the `grant` entry `0003`'s trigger writes, and what the
resolver then returns. The database half skips without a server and runs in CI.

Task ids: M1.4.3, M1.4.8, M1.8.4
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.console.govern import Placed, approver_misconfigurations
from brain.console.reads import Plane, plane_capability
from brain.console.scoped_authority import REACH_AUTHORITY
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.govern_pack_routes import MISMATCH_SENTENCES, add_assignment, approver_holders
from brain.identity.packs import PackAssignment, SubjectGrant
from brain.identity.roles import RoleMismatchKind, mismatches_between
from brain.identity.teams import PrincipalSubject
from brain.session import make_session_factory
from brain.tables.audit import ACTOR_SETTING
from brain.tables.gate import (
    CapabilityGrantRow,
    CapabilityPackAssignmentRow,
    CapabilityPackRow,
    ScopeRow,
)
from tests.fixtures.http_client import Response
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_api_routes import Directory, Keys, NoCache, Versions, token_for, verifier
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_review_store import entries, through_0052

PACKS_PATH = f"{API_PREFIX}/govern/packs"
ASSIGN_PATH = f"{API_PREFIX}/govern/packs/assignment"
MISCONFIG_PATH = f"{API_PREFIX}/govern/roles/misconfigurations"

#: Far from any wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}

WHOLE = Scope.unrestricted()
MAINTENANCE = "maintenance"
FINANCE = "finance"
IN_MAINTENANCE = Scope(clauses=(Clause(field="department", op=Op.EQ, value=MAINTENANCE),))


def _grant(value: str, scope: Scope = WHOLE) -> Grant:
    return Grant(capability=Capability(value=value), scope=scope)


def _reads(scope: Scope) -> tuple[Grant, ...]:
    return (
        _grant("read:grant", scope),
        _grant("read:role", scope),
        _grant("read:capability", scope),
        _grant(plane_capability(Plane.CONFIGURATION).value, scope),
    )


#: The pack these tests assign holds two capabilities, so "one missing refuses the lot" can bite.
PACK_CAPABILITIES = ("read:ticket", "write:ticket")

GRANTS: dict[str, tuple[Grant, ...]] = {
    "u_none": (),
    "u_prefix": (_grant(plane_capability(Plane.CONFIGURATION).value),),
    # The authority and the pack's first capability, not its second.
    "u_narrow": (*_reads(WHOLE), _grant(REACH_AUTHORITY.value), _grant("read:ticket")),
    # May open Roles and People and may not name capabilities.
    "u_wide": (
        _grant("read:grant"),
        _grant("read:role"),
        _grant(plane_capability(Plane.CONFIGURATION).value),
    ),
    "u_admin": (
        *_reads(WHOLE),
        _grant(REACH_AUTHORITY.value),
        *(_grant(one) for one in PACK_CAPABILITIES),
    ),
    "u_elsewhere": (
        *_reads(IN_MAINTENANCE),
        _grant(REACH_AUTHORITY.value, IN_MAINTENANCE),
        *(_grant(one, IN_MAINTENANCE) for one in PACK_CAPABILITIES),
    ),
}


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


def pack_row(capabilities: Sequence[str] = PACK_CAPABILITIES) -> CapabilityPackRow:
    row = CapabilityPackRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, "helpdesk"),
        name="helpdesk",
        description="what somebody on the help desk needs",
        capabilities=list(capabilities),
    )
    row.created_at = LONG_AGO
    row.deleted_at = None
    return row


def scope_row(slug: str, predicate: dict[str, Any]) -> ScopeRow:
    row = ScopeRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, slug),
        slug=slug,
        predicate=predicate,
        is_department=False,
        label=slug,
    )
    row.created_at = LONG_AGO
    row.deleted_at = None
    return row


def grant_row(principal_id: str, capability: str) -> CapabilityGrantRow:
    row = CapabilityGrantRow(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"{principal_id}/{capability}"),
        principal_id=principal_id,
        capability=capability,
        scope=WHOLE.model_dump(),
        granted_by="u_seed",
        reason="the job needs it",
        not_after=None,
    )
    row.created_at = LONG_AGO
    row.deleted_at = None
    return row


class Result:
    def __init__(self, rows: Sequence[Any]) -> None:
        self._rows = tuple(rows)

    def scalars(self) -> Result:
        return Result([row[0] if isinstance(row, tuple) else row for row in self._rows])

    def all(self) -> tuple[Any, ...]:
        return self._rows

    def scalar_one_or_none(self) -> Any:
        if not self._rows:
            return None
        row = self._rows[0]
        return row[0] if isinstance(row, tuple) else row


class Recorded:
    """What each table answers, and every statement run, keyed by table rather than order."""

    def __init__(self) -> None:
        self.scopes: dict[str, ScopeRow] = {
            MAINTENANCE: scope_row(MAINTENANCE, {"department": MAINTENANCE}),
            FINANCE: scope_row(FINANCE, {"department": FINANCE}),
            "company": scope_row("company", {}),
        }
        self.pack: CapabilityPackRow | None = pack_row()
        self.grants: list[tuple[CapabilityGrantRow, str | None]] = []
        self.holders: list[tuple[str, str | None]] = []
        self.integrity = False
        self.statements: list[str] = []
        self.committed = 0
        self.rolled_back = 0

    def answer(self, statement: Any) -> Result:
        sql_text = str(statement)
        if sql_text.startswith("INSERT INTO gate.capability_pack_assignment"):
            written = CapabilityPackAssignmentRow(
                id=uuid.uuid4(),
                principal_id="u_2",
                pack_id=self.pack.id if self.pack else uuid.uuid4(),
                scope={},
                granted_by="u_admin",
                reason="r",
                not_after=None,
            )
            written.created_at = LONG_AGO
            return Result([written])
        if "directory_role_grant" in sql_text:
            return Result(self.holders)
        if "capability_pack_assignment" in sql_text:
            return Result([])
        if "gate.capability_pack" in sql_text:
            return Result([] if self.pack is None else [self.pack])
        if "gate.scope" in sql_text:
            slug = statement.compile().params.get("slug_1")
            return Result([self.scopes[slug]] if slug in self.scopes else [])
        if "capability_grant" in sql_text:
            return Result(self.grants)
        return Result([])


_RECORDED = Recorded()


class Session(AsyncSession):
    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        sql_text = str(statement)
        try:
            _RECORDED.statements.append(
                str(statement.compile(compile_kwargs={"literal_binds": True}))
            )
        except Exception:
            _RECORDED.statements.append(sql_text)
        if _RECORDED.integrity and sql_text.startswith("INSERT INTO"):
            raise IntegrityError("insert", None, Exception("uq_assignment"))
        return _RECORDED.answer(statement)

    async def commit(self) -> None:
        _RECORDED.committed += 1

    async def rollback(self) -> None:
        _RECORDED.rolled_back += 1

    async def close(self) -> None:
        return None


@pytest.fixture
def recorded() -> Iterator[Recorded]:
    global _RECORDED
    _RECORDED = Recorded()
    yield _RECORDED


@pytest.fixture
def client(recorded: Recorded) -> Iterator[TestClient]:
    from brain.api_routes import GateWiring
    from brain.identity.bearer import TokenAuthority

    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer="https://id.verz.example/realms/brain",
                audience="brain-api",
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(),
            cache=NoCache(),
        )
        app.state.db_sessions = async_sessionmaker(class_=Session)
        app.state.console_reads = None
        yield c


def assign(c: TestClient, pid: str, **overrides: object) -> Response:
    body: dict[str, object] = {
        "principal_id": "u_2",
        "pack_slug": "helpdesk",
        "scope_slug": MAINTENANCE,
        "reason": "joined the help desk",
    }
    body.update(overrides)
    response: Response = c.post(
        ASSIGN_PATH,
        headers={"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"},
        json=body,
    )
    return response


def get(c: TestClient, path: str, pid: str) -> Response:
    response: Response = c.get(
        path, headers={"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"}
    )
    return response


def inserted(recorded: Recorded) -> list[str]:
    return [s for s in recorded.statements if s.startswith("INSERT INTO")]


# ------------------------------------------------------------------ pack assignment
def test_a_pack_is_assigned_over_a_named_scope_the_assigner_holds_every_capability_in(
    client: TestClient, recorded: Recorded
) -> None:
    """M1.4.3's writer. Delete this and nothing proves an assignment can be made at all, which was
    the state of every install until this route: the table existed and nothing inserted into it."""
    answered = assign(client, "u_admin")
    assert answered.status_code == 201, answered.text
    body = answered.json()
    assert (body["principal_id"], body["pack_slug"], body["scope_slug"]) == (
        "u_2",
        "helpdesk",
        MAINTENANCE,
    )
    [insert] = inserted(recorded)
    assert "gate.capability_pack_assignment" in insert
    assert recorded.committed == 1


def test_the_assigner_is_named_to_the_transaction_before_the_insert(
    client: TestClient, recorded: Recorded
) -> None:
    """M1.4.8's attribution. The trigger writes the audit entry and reads the actor from this
    setting; delete this and an assignment can be recorded against nobody."""
    assign(client, "u_admin")
    actor = next(i for i, s in enumerate(recorded.statements) if ACTOR_SETTING in s)
    insert = next(i for i, s in enumerate(recorded.statements) if s.startswith("INSERT INTO"))
    assert actor < insert
    assert "'u_admin'" in recorded.statements[actor]


def test_one_capability_the_assigner_lacks_refuses_the_whole_pack(
    client: TestClient, recorded: Recorded
) -> None:
    """The escalation a pack hides. Delete this and a pack becomes a way to hand over
    `write:ticket` by somebody who holds only `read:ticket`."""
    assert assign(client, "u_narrow").status_code == 404
    assert inserted(recorded) == []
    assert recorded.committed == 0


def test_a_scope_wider_than_the_assigners_own_is_refused(
    client: TestClient, recorded: Recorded
) -> None:
    """A department-scoped assigner may assign in their department and nowhere else. Delete this
    and the narrowing on a single grant can be walked round through a pack."""
    assert assign(client, "u_elsewhere", scope_slug=FINANCE).status_code == 404
    assert inserted(recorded) == []
    assert assign(client, "u_elsewhere").status_code == 201


def test_a_scope_that_restricts_nothing_is_refused_even_to_a_company_wide_assigner(
    client: TestClient, recorded: Recorded
) -> None:
    """`PackAssignment` refuses an unrestricted scope, the widest row in the system. Delete this
    and the route could be relaxed to default the scope without any test noticing."""
    assert assign(client, "u_admin", scope_slug="company").status_code == 404
    assert inserted(recorded) == []


def test_a_caller_without_the_authority_never_reaches_the_database(
    client: TestClient, recorded: Recorded
) -> None:
    """The ordering every govern write keeps. Delete this and a caller holding nothing can tell
    a process with a database from one without."""
    assert assign(client, "u_none").status_code == 404
    assert assign(client, "u_prefix").status_code == 404
    assert recorded.statements == []


def test_a_pack_or_scope_nothing_matches_is_the_same_refusal(
    client: TestClient, recorded: Recorded
) -> None:
    """One sentence for every cause, so the route cannot be used to list packs or scopes."""
    wider = assign(client, "u_elsewhere", scope_slug=FINANCE)
    unknown_scope = assign(client, "u_admin", scope_slug="nowhere")
    recorded.pack = None
    unknown_pack = assign(client, "u_admin")
    assert unknown_scope.status_code == unknown_pack.status_code == wider.status_code == 404
    messages = {one.json()["message"] for one in (wider, unknown_scope, unknown_pack)}
    assert len(messages) == 1
    assert inserted(recorded) == []


def test_a_constraint_refusing_the_insert_is_the_ordinary_refusal(
    client: TestClient, recorded: Recorded
) -> None:
    """A pack the person already holds, or a person who does not exist, is a fact about somebody
    else. Delete this and the constraint name reaches the caller as a 500."""
    recorded.integrity = True
    answered = assign(client, "u_admin")
    assert answered.status_code == 404
    assert recorded.committed == 0
    assert recorded.rolled_back >= 1


def test_a_body_naming_the_granter_or_a_predicate_is_refused(client: TestClient) -> None:
    """`extra="forbid"`: the granter is the token and the scope is a name. Delete this and a
    browser could attribute an assignment to somebody else."""
    assert assign(client, "u_admin", granted_by="u_other").status_code == 422
    assert assign(client, "u_admin", scope={"clauses": []}).status_code == 422


def test_the_insert_stores_the_named_scope_and_the_caller_as_granter() -> None:
    """The row carries what was judged. Delete this and the statement could store a different
    scope from the one `write_grant` was asked about."""
    assignment = PackAssignment(
        subject=PrincipalSubject(principal_id="u_2"),
        pack_slug="helpdesk",
        scope=IN_MAINTENANCE,
        granted_by="u_admin",
        reason="joined",
        granted_at=LONG_AGO,
    )
    values = add_assignment(assignment, "u_2", pack_row()).compile().params
    assert values["scope"] == IN_MAINTENANCE.model_dump()
    assert values["granted_by"] == "u_admin"
    assert values["pack_id"] == pack_row().id


def test_the_pack_catalogue_is_answered_under_the_vocabulary_grant_only(
    client: TestClient, recorded: Recorded
) -> None:
    """A pack's contents are capability names. Delete this and the pack list becomes a way to
    read the vocabulary without the Capabilities screen's grant."""
    shown = get(client, PACKS_PATH, "u_admin").json()["packs"]
    assert shown == [
        {
            "slug": "helpdesk",
            "label": "what somebody on the help desk needs",
            "capabilities": list(PACK_CAPABILITIES),
        }
    ]
    before = len(recorded.statements)
    assert get(client, PACKS_PATH, "u_wide").json() == {"packs": []}
    assert len(recorded.statements) == before


# ------------------------------------------------------------- the Approver flag
def test_the_two_mismatches_are_the_two_set_differences() -> None:
    """M1.8.4's comparison. Delete this and either direction can be dropped silently."""
    found = mismatches_between(["u_role_only", "u_both"], ["u_both", "u_cap_only"])
    assert [(one.principal_id, one.kind) for one in found] == [
        ("u_role_only", RoleMismatchKind.ROLE_WITHOUT_CAPABILITY),
        ("u_cap_only", RoleMismatchKind.CAPABILITY_WITHOUT_ROLE),
    ]


def _placed_grant(pid: str, capability: str, department: str) -> Placed[SubjectGrant]:
    return Placed(
        record=SubjectGrant(
            subject=PrincipalSubject(principal_id=pid),
            capability=Capability(value=capability),
            scope=WHOLE,
            granted_by="u_seed",
            reason="r",
            granted_at=LONG_AGO,
        ),
        where={"department": department},
    )


def test_the_flag_is_judged_only_over_people_the_reader_may_see() -> None:
    """A department reader learns nothing about another department's approvers. Delete this and
    the flag becomes a list of who can approve across the company."""
    holdings = [
        _placed_grant("u_cap_here", "approve:action", MAINTENANCE),
        _placed_grant("u_cap_there", "approve:action", FINANCE),
    ]
    role = [
        Placed(record="u_role_here", where={"department": MAINTENANCE}),
        Placed(record="u_role_there", where={"department": FINANCE}),
    ]
    wide = EntitlementSet(principal_id="u_admin", grants=GRANTS["u_admin"])
    narrow = EntitlementSet(principal_id="u_elsewhere", grants=GRANTS["u_elsewhere"])
    blind = EntitlementSet(principal_id="u_wide", grants=GRANTS["u_wide"])
    assert {one.principal_id for one in approver_misconfigurations(holdings, role, wide)} == {
        "u_cap_here",
        "u_cap_there",
        "u_role_here",
        "u_role_there",
    }
    assert {one.principal_id for one in approver_misconfigurations(holdings, role, narrow)} == {
        "u_cap_here",
        "u_role_here",
    }
    assert approver_misconfigurations(holdings, role, blind) == ()


def test_the_roles_screen_flags_both_directions_and_not_a_consistent_approver(
    client: TestClient, recorded: Recorded
) -> None:
    """The console half of M1.8.4. Delete this and the route can answer nothing for everybody."""
    recorded.grants = [
        (grant_row("u_both", "approve:action"), MAINTENANCE),
        (grant_row("u_cap_only", "approve:grant"), MAINTENANCE),
        (grant_row("u_reader", "read:ticket"), MAINTENANCE),
    ]
    recorded.holders = [("u_both", MAINTENANCE), ("u_role_only", MAINTENANCE)]
    answered = get(client, MISCONFIG_PATH, "u_admin")
    assert answered.status_code == 200, answered.text
    assert answered.json()["items"] == [
        {
            "principal_id": "u_role_only",
            "kind": "role_without_capability",
            "sentence": MISMATCH_SENTENCES[RoleMismatchKind.ROLE_WITHOUT_CAPABILITY],
        },
        {
            "principal_id": "u_cap_only",
            "kind": "capability_without_role",
            "sentence": MISMATCH_SENTENCES[RoleMismatchKind.CAPABILITY_WITHOUT_ROLE],
        },
    ]


def test_the_flag_needs_both_the_roles_and_the_people_screen(
    client: TestClient, recorded: Recorded
) -> None:
    """A reader of neither is refused before the database. Delete this and the approver list is
    open to anybody holding a token."""
    assert get(client, MISCONFIG_PATH, "u_none").status_code == 404
    assert get(client, MISCONFIG_PATH, "u_prefix").status_code == 404
    assert recorded.statements == []


def test_the_role_holders_are_read_from_the_directory_for_the_approver_role() -> None:
    """Delete this and the load could read every role, flagging a Super Admin as an Approver."""
    rendered = str(approver_holders(10).compile(compile_kwargs={"literal_binds": True}))
    assert "auth.directory_role_grant.role = 'approver'" in rendered
    assert "auth.principal.deleted_at IS NULL" in rendered


# ---------------------------------------------------------------- against a database
def test_an_assignment_reaches_the_row_the_ledger_and_the_resolver() -> None:
    """M1.4.3 and M1.4.8 on PostgreSQL: the statement this route runs inserts a row as the
    application role, `0003`'s trigger appends a `grant` entry naming the pack and the assigner,
    and the resolver then returns the pack's capabilities. Delete this and all three can be false
    in production while the stubbed tests above stay green."""
    with through_0052("brain_pack_assign") as url:
        for pid in ("u_holder", "u_lead"):
            sql(
                url,
                "INSERT INTO auth.principal (id, kind, employment, display_name,"
                " primary_department) VALUES (%s, 'human', 'staff', %s, 'web')",
                pid,
                f"Person {pid}",
            )
        [(pack_id,)] = sql(
            url,
            "INSERT INTO gate.capability_pack (name, description, capabilities)"
            " VALUES ('helpdesk', 'a pack', ARRAY['read:ticket', 'write:ticket']) RETURNING id",
        )
        pack = CapabilityPackRow(id=pack_id, name="helpdesk", description="a pack", capabilities=[])
        scope = Scope(clauses=(Clause(field="department", op=Op.EQ, value="web"),))
        assignment = PackAssignment(
            subject=PrincipalSubject(principal_id="u_holder"),
            pack_slug="helpdesk",
            scope=scope,
            granted_by="u_lead",
            reason="joined the help desk",
            granted_at=LONG_AGO,
        )

        async def go() -> None:
            engine = app_engine(url)
            try:
                async with make_session_factory(engine)() as session:
                    await session.execute(
                        text("SELECT set_config(:n, :v, true)").bindparams(
                            n=ACTOR_SETTING, v="u_lead"
                        )
                    )
                    await session.execute(add_assignment(assignment, "u_holder", pack))
                    await session.commit()
            finally:
                await engine.dispose()

        run(go)
        rows = sql(
            url,
            "SELECT principal_id, scope, granted_by FROM gate.capability_pack_assignment"
            " WHERE deleted_at IS NULL",
        )
        granted = entries(url, "grant")
        held = sql(url, "SELECT gate.resolve_entitlements('u_holder', now())")

    assert rows == [("u_holder", json.loads(json.dumps(scope.model_dump())), "u_lead")]
    assert [(one.actor_id, one.details.get("pack")) for one in granted] == [("u_lead", "helpdesk")]
    capabilities = {one["capability"]["value"] for one in held[0][0]["grants"]}
    assert {"read:ticket", "write:ticket"} <= capabilities
