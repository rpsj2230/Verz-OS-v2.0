"""Pack assignment and the Approver misconfiguration flag, over HTTP and against a database.

Driven through the real application with a stub session for the refusals and the statement order,
the pattern `tests/unit/test_govern_routes.py` argues for, and through PostgreSQL for the three
places an assignment must reach: the row, the `grant` entry `0003`'s trigger writes, and what the
resolver then returns. The database half skips without a server and runs in CI.

Pack writes (M27.15.24) are driven over a stub of their own, with the signed-in people chosen by
`tests.fixtures.console_http`, and on PostgreSQL through the routes to the rows, the `pack` entries
`0141`'s trigger writes and what the resolver then gives a holder.

Task ids: M1.4.3, M1.4.8, M1.8.4, M27.15.24
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
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
from brain.audit.ledger import AuditAction, AuditChain
from brain.audit.record import PACK_VERSION_PREFIX, AuditRecorder, PackChange
from brain.console.govern import Placed, approver_misconfigurations
from brain.console.reads import Plane, plane_capability
from brain.console.scoped_authority import REACH_AUTHORITY
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Clause, Op, Scope
from brain.govern_pack_routes import (
    A_NEW_VERSION_CHANGES_WHAT_EVERY_HOLDER_HOLDS,
    A_PACK_NAME_IS_TAKEN,
    A_PACK_SOMEBODY_HOLDS_IS_NOT_RETIRED,
    MISMATCH_SENTENCES,
    NOT_A_REGISTERED_CAPABILITY,
    add_assignment,
    approver_holders,
    held_by_somebody,
    retiring_pack,
    versioning_pack,
)
from brain.govern_people_routes import IT_CHANGED_SINCE_YOU_OPENED_IT
from brain.identity.packs import PackAssignment, SubjectGrant
from brain.identity.roles import RoleMismatchKind, mismatches_between
from brain.identity.teams import PrincipalSubject
from brain.ops.migration_policy import check_file
from brain.session import make_session_factory
from brain.tables.audit import ACTOR_SETTING, SUBJECT_PATTERN
from brain.tables.gate import (
    CapabilityGrantRow,
    CapabilityPackAssignmentRow,
    CapabilityPackRow,
    ScopeRow,
)
from brain.tables.identity import one_of
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.http_client import Response
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_api_routes import Directory, Keys, NoCache, Versions, token_for, verifier
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_review_store import entries, through_0052
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

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
        version=1,
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
        #: Approvers by a person's appointment (`gate.role_grant`): who, where, and the lapse.
        self.appointments: list[tuple[str, str | None, datetime | None]] = []
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
        if "gate.role_grant" in sql_text:
            return Result(self.appointments)
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
            "version": 1,
        }
    ]
    before = len(recorded.statements)
    assert get(client, PACKS_PATH, "u_wide").json()["packs"] == []
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


def test_an_appointed_approver_counts_until_the_appointment_lapses(
    client: TestClient, recorded: Recorded
) -> None:
    """M1.8.4 over `gate.role_grant` (`0102`). Delete this and the flag reads the directory alone,
    missing every Approver somebody appointed, or keeps flagging a deputy whose days ran out."""
    recorded.appointments = [
        ("u_appointed", MAINTENANCE, None),
        ("u_lapsed", MAINTENANCE, LONG_AGO),
    ]
    answered = get(client, MISCONFIG_PATH, "u_admin")
    assert answered.status_code == 200, answered.text
    assert [(one["principal_id"], one["kind"]) for one in answered.json()["items"]] == [
        ("u_appointed", "role_without_capability")
    ]


# ------------------------------------------------------------ writing packs (M27.15.24)

PACK_VERSION_PATH = f"{API_PREFIX}/govern/packs/version"
PACK_COPY_PATH = f"{API_PREFIX}/govern/packs/copy"
PACK_RETIREMENT_PATH = f"{API_PREFIX}/govern/packs/retirement"
LABEL_MIGRATION = VERSIONS / "0141_packs_people_and_scope_labels_audited.py"

#: Who may write what, signed in through `tests.fixtures.console_http`. `u_admin` holds the pack
#: authority and every capability over everything and may name capabilities; `u_prefix` the
#: same without the vocabulary's read; `u_narrow` the authority and one of the two capabilities;
#: `u_elsewhere` everything, in maintenance only; `u_wide` the vocabulary and no authority.
WRITERS: dict[str, tuple[Grant, ...]] = {
    "u_admin": (
        _grant(REACH_AUTHORITY.value),
        *(_grant(one) for one in PACK_CAPABILITIES),
        _grant("read:invoice"),
        _grant("read:capability"),
        _grant(plane_capability(Plane.CONFIGURATION).value),
    ),
    "u_prefix": (
        _grant(REACH_AUTHORITY.value),
        *(_grant(one) for one in PACK_CAPABILITIES),
        _grant("read:invoice"),
    ),
    "u_narrow": (
        _grant(REACH_AUTHORITY.value),
        _grant("read:ticket"),
        _grant("read:invoice"),
        _grant("read:capability"),
        _grant(plane_capability(Plane.CONFIGURATION).value),
    ),
    "u_elsewhere": (
        _grant(REACH_AUTHORITY.value, IN_MAINTENANCE),
        *(_grant(one, IN_MAINTENANCE) for one in PACK_CAPABILITIES),
        _grant("read:capability", IN_MAINTENANCE),
        _grant(plane_capability(Plane.CONFIGURATION).value),
    ),
    "u_wide": (
        _grant("read:capability"),
        _grant(plane_capability(Plane.CONFIGURATION).value),
    ),
    "u_none": (),
}


class Rows:
    """What a statement answers, in the shapes the pack writes read."""

    def __init__(self, rows: Sequence[Any]) -> None:
        self._rows = tuple(rows)

    def scalars(self) -> Rows:
        return Rows([row[0] if isinstance(row, tuple) else row for row in self._rows])

    def all(self) -> tuple[Any, ...]:
        return self._rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def one(self) -> Any:
        assert len(self._rows) == 1
        return self._rows[0]

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self) -> Any:
        found = self.first()
        return found[0] if isinstance(found, tuple) else found


def named_pack(name: str, capabilities: Sequence[str] = PACK_CAPABILITIES) -> CapabilityPackRow:
    row = pack_row(capabilities)
    row.id = uuid.uuid5(uuid.NAMESPACE_URL, name)
    row.name = name
    return row


class Book:
    """The packs, the registry and the assignments a write reads, and everything it ran."""

    def __init__(self) -> None:
        self.packs: dict[str, CapabilityPackRow] = {"helpdesk": pack_row()}
        self.registry: set[str] = {*PACK_CAPABILITIES, "read:invoice"}
        #: Whether a live assignment of the pack being retired exists.
        self.held = False
        #: Whether the guarded update finds its row at the expected version.
        self.update_lands = True
        #: Whether the insert meets the partial unique index on a live name.
        self.taken_on_insert = False
        self.statements: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    def answer(self, statement: Any) -> Rows:
        text = str(statement)
        if "set_config" in text:
            return Rows([])
        if text.startswith("INSERT INTO gate.capability_pack "):
            if self.taken_on_insert:
                raise IntegrityError("insert", None, Exception("uq_capability_pack_name_live"))
            return Rows([(1, LONG_AGO)])
        if text.startswith("UPDATE gate.capability_pack "):
            return Rows([(2, LONG_AGO)] if self.update_lands else [])
        if "FROM gate.capability_registry" in text:
            return Rows([(one,) for one in sorted(self.registry)])
        if "FROM gate.capability_pack_assignment" in text:
            return Rows([(uuid.uuid4(),)] if self.held else [])
        if "FROM gate.capability_pack" in text:
            params = statement.compile().params
            if "name_1" not in params:
                return Rows(list(self.packs.values()))
            found = self.packs.get(str(params["name_1"]))
            return Rows([] if found is None else [found])
        msg = f"no stub answers {text}"
        raise AssertionError(msg)


_BOOK = Book()


class BookSession(AsyncSession):
    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            _BOOK.statements.append(str(statement.compile(compile_kwargs={"literal_binds": True})))
        except Exception:
            _BOOK.statements.append(str(statement))
        return _BOOK.answer(statement)

    async def commit(self) -> None:
        _BOOK.commits += 1

    async def rollback(self) -> None:
        _BOOK.rollbacks += 1

    async def close(self) -> None:
        return None


@pytest.fixture
def book() -> Iterator[Book]:
    global _BOOK
    _BOOK = Book()
    yield _BOOK


@pytest.fixture
def writer(book: Book) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = gate_wiring(WRITERS)
        app.state.db_sessions = async_sessionmaker(class_=BookSession)
        app.state.console_reads = None
        yield c


def write(c: TestClient, pid: str, path: str, body: Mapping[str, object]) -> Response:
    response: Response = c.post(path, json=dict(body), headers=headers(pid))
    return response


def creating(slug: str = "billing", *capabilities: str) -> dict[str, object]:
    return {
        "slug": slug,
        "label": "what somebody in billing needs",
        "capabilities": list(capabilities or ("read:ticket", "read:invoice")),
    }


def versioning(expected: int = 1, *capabilities: str) -> dict[str, object]:
    return {
        "slug": "helpdesk",
        "expected_version": expected,
        "label": "what the help desk needs now",
        "capabilities": list(capabilities or (*PACK_CAPABILITIES, "read:invoice")),
    }


COPYING: dict[str, object] = {"slug": "helpdesk", "new_slug": "helpdesk_two", "label": "Second"}
RETIRING: dict[str, object] = {"slug": "helpdesk", "expected_version": 1}


def writes(book: Book) -> list[str]:
    return [one for one in book.statements if one.startswith(("INSERT", "UPDATE"))]


def answer_of(one: Response) -> tuple[int, str]:
    return one.status_code, str(one.json()["message"])


def said(message: str) -> tuple[int, str]:
    return 404, f"Nothing was changed: {message}."


def test_a_writer_holding_everything_creates_versions_copies_and_retires_a_pack(
    writer: TestClient, book: Book
) -> None:
    """M27.15.24's four writes, the positive case every refusal below needs. Delete this and a set
    of routes that refuses everybody passes the whole section, or the change words are crossed, or
    a write is sent before the writer is named to the transaction."""
    answers = [
        write(writer, "u_admin", PACKS_PATH, creating()),
        write(writer, "u_admin", PACK_VERSION_PATH, versioning()),
        write(writer, "u_admin", PACK_COPY_PATH, COPYING),
        write(writer, "u_admin", PACK_RETIREMENT_PATH, RETIRING),
    ]

    assert [one.status_code for one in answers] == [201, 200, 201, 200], [
        one.text for one in answers
    ]
    assert [(one.json()["slug"], one.json()["change"]) for one in answers] == [
        ("billing", "created"),
        ("helpdesk", "versioned"),
        ("helpdesk_two", "copied"),
        ("helpdesk", "retired"),
    ]
    assert [one.json()["version"] for one in answers[:3]] == [1, 2, 1]
    assert book.commits == 4
    named = [i for i, one in enumerate(book.statements) if ACTOR_SETTING in one]
    written = [i for i, one in enumerate(book.statements) if one.startswith(("INSERT", "UPDATE"))]
    assert len(named) == len(written) == 4
    assert all(before < after for before, after in zip(named, written, strict=True))
    assert all("'u_admin'" in book.statements[i] for i in named)


def test_a_writer_short_of_one_capability_is_refused_every_write_that_bundles_it(
    writer: TestClient, book: Book
) -> None:
    """Nobody bundles what they could not grant alone. `u_narrow` holds the authority, `read:ticket`
    and `read:invoice` everywhere and not `write:ticket`: creating a pack carrying it is refused
    before the database, versioning `helpdesk` is refused even to a body leaving `write:ticket` out,
    because taking it from every holder is a decision only somebody holding it may make, and copying
    `helpdesk` is refused because the copy carries it. A pack of what they do hold is created.

    Delete this and a pack is where a capability its writer could not grant hides."""
    create = write(writer, "u_narrow", PACKS_PATH, creating("billing", "write:ticket"))
    reached_before_database = list(book.statements)
    version = write(writer, "u_narrow", PACK_VERSION_PATH, versioning(1, "read:ticket"))
    copy = write(writer, "u_narrow", PACK_COPY_PATH, COPYING)
    allowed = write(writer, "u_narrow", PACKS_PATH, creating("billing", "read:ticket"))

    assert {answer_of(one) for one in (create, version, copy)} == {(404, Absent.public_message)}
    assert reached_before_database == []
    assert allowed.status_code == 201, allowed.text
    assert len(writes(book)) == 1
    assert book.commits == 1


def test_a_writer_who_cannot_write_packs_is_refused_before_the_database(
    writer: TestClient, book: Book
) -> None:
    """The ordering every govern write keeps, and one refusal for each of the four writes. Delete
    this and a caller holding the authority in one department, or none, can tell a process with a
    database from one without, or learn which pack names exist."""
    for pid in ("u_elsewhere", "u_wide", "u_none"):
        for path, body in (
            (PACKS_PATH, creating()),
            (PACK_VERSION_PATH, versioning()),
            (PACK_COPY_PATH, COPYING),
            (PACK_RETIREMENT_PATH, RETIRING),
        ):
            answered = write(writer, pid, path, body)
            assert answer_of(answered) == (404, Absent.public_message), (pid, path)
    assert book.statements == []


def test_a_pack_that_is_not_there_is_the_ordinary_refusal(writer: TestClient, book: Book) -> None:
    """Delete this and versioning, copying or retiring a pack that does not exist is answered
    differently from one the caller may not write, which lists the packs one POST at a time."""
    gone = {"slug": "nothing_here"}
    answers = [
        write(writer, "u_admin", PACK_VERSION_PATH, {**versioning(), **gone}),
        write(writer, "u_admin", PACK_COPY_PATH, {**COPYING, **gone}),
        write(writer, "u_admin", PACK_RETIREMENT_PATH, {**RETIRING, **gone}),
    ]

    assert {answer_of(one) for one in answers} == {(404, Absent.public_message)}
    assert writes(book) == []


def test_every_readable_refusal_is_a_sentence_a_pack_writer_can_act_on(
    writer: TestClient, book: Book
) -> None:
    """A taken short name, a version that moved since the page was opened, a pack somebody still
    holds, and a capability the registry does not hold, each said in a sentence to a writer holding
    the pack authority, and the last only to a writer who may also name capabilities.

    Delete this and each of those answers "I could not find that", which a person governing every
    pack can do nothing with, or the registry's contents are read back to a writer the Capabilities
    screen would refuse."""
    book.packs["billing"] = named_pack("billing")
    taken = write(writer, "u_admin", PACKS_PATH, creating("helpdesk"))
    copied_onto = write(writer, "u_admin", PACK_COPY_PATH, {**COPYING, "new_slug": "billing"})
    moved = write(writer, "u_admin", PACK_VERSION_PATH, versioning(3))
    moved_retire = write(
        writer, "u_admin", PACK_RETIREMENT_PATH, {**RETIRING, "expected_version": 3}
    )
    book.held = True
    held = write(writer, "u_admin", PACK_RETIREMENT_PATH, RETIRING)
    book.registry.discard("read:invoice")
    unregistered = write(writer, "u_admin", PACKS_PATH, creating("fresh"))
    unregistered_blind = write(writer, "u_prefix", PACKS_PATH, creating("fresh"))
    book.registry.add("read:invoice")
    book.taken_on_insert = True
    raced = write(writer, "u_admin", PACKS_PATH, creating("fresh"))

    assert answer_of(taken) == answer_of(copied_onto) == answer_of(raced)
    assert answer_of(taken) == said(A_PACK_NAME_IS_TAKEN)
    assert answer_of(moved) == answer_of(moved_retire) == said(IT_CHANGED_SINCE_YOU_OPENED_IT)
    assert answer_of(held) == said(A_PACK_SOMEBODY_HOLDS_IS_NOT_RETIRED)
    assert answer_of(unregistered) == said(
        NOT_A_REGISTERED_CAPABILITY.format(capability="read:invoice")
    )
    assert answer_of(unregistered_blind) == (404, Absent.public_message)
    assert book.commits == 0
    assert [one for one in writes(book) if one.startswith("UPDATE")] == []


def test_the_retirement_refusal_names_nobody_and_counts_nothing() -> None:
    """Delete this and the sentence grows a holder's name or how many hold the pack, or the
    statement behind it counts them, which is a fact about people the pack authority does not make
    the writer's to read."""
    assert not any(one.isdigit() for one in A_PACK_SOMEBODY_HOLDS_IS_NOT_RETIRED)
    compiled = str(held_by_somebody(pack_row()).compile(compile_kwargs={"literal_binds": True}))
    assert "LIMIT 1" in compiled
    assert "count(" not in compiled.lower()
    assert "capability_pack_assignment.not_after > statement_timestamp()" in compiled


def test_a_versioning_that_leaves_the_pack_as_it_is_is_a_422(
    writer: TestClient, book: Book
) -> None:
    """Delete this and a press that changes nothing raises the version and writes a ledger entry
    saying every holder's pack changed when it did not."""
    same = {
        "slug": "helpdesk",
        "expected_version": 1,
        "label": "what somebody on the help desk needs",
        "capabilities": list(reversed(PACK_CAPABILITIES)),
    }
    answered = write(writer, "u_admin", PACK_VERSION_PATH, same)
    changed = write(writer, "u_admin", PACK_VERSION_PATH, {**same, "label": "a new label"})

    assert answered.status_code == 422
    assert changed.status_code == 200, changed.text
    assert len(writes(book)) == 1


def test_a_body_the_types_refuse_is_a_422_that_reaches_no_database(
    writer: TestClient, book: Book
) -> None:
    """Delete this and a capability named twice, a malformed capability, an empty pack, a copy onto
    its own name, a version of nought, a blank label or a body naming its own writer reaches the
    database, where it is a constraint error or a row nothing can read."""
    bodies: list[tuple[str, Mapping[str, object]]] = [
        (PACKS_PATH, {**creating(), "capabilities": ["read:ticket", "read:ticket"]}),
        (PACKS_PATH, {**creating(), "capabilities": ["not a capability"]}),
        (PACKS_PATH, {**creating(), "capabilities": []}),
        (PACKS_PATH, {**creating(), "label": "   "}),
        (PACKS_PATH, {**creating(), "granted_by": "u_other"}),
        (PACKS_PATH, {**creating(), "slug": "Bad-Slug"}),
        (PACK_COPY_PATH, {**COPYING, "new_slug": "helpdesk"}),
        (PACK_VERSION_PATH, {**versioning(), "expected_version": 0}),
        (PACK_RETIREMENT_PATH, {**RETIRING, "expected_version": 0}),
    ]
    answers = [write(writer, "u_admin", path, body) for path, body in bodies]

    assert [one.status_code for one in answers] == [422] * len(bodies)
    assert book.statements == []


def test_the_catalogue_carries_each_version_and_whether_this_reader_may_write(
    writer: TestClient, book: Book
) -> None:
    """Presentation, held anyway. Delete this and the page cannot send the version a versioning
    names, or offers the writes to somebody every press refuses, or drops the two sentences."""
    admin = writer.get(PACKS_PATH, headers=headers("u_admin")).json()
    reader = writer.get(PACKS_PATH, headers=headers("u_wide")).json()
    blind = writer.get(PACKS_PATH, headers=headers("u_prefix")).json()

    assert [(one["slug"], one["version"]) for one in admin["packs"]] == [("helpdesk", 1)]
    assert (admin["may_write"], reader["may_write"], blind["may_write"]) == (True, False, True)
    assert blind["packs"] == []
    assert admin["versioning"] == A_NEW_VERSION_CHANGES_WHAT_EVERY_HOLDER_HOLDS
    assert admin["retiring"] == f"{A_PACK_SOMEBODY_HOLDS_IS_NOT_RETIRED}."


def test_a_version_is_the_same_row_updated_and_never_a_new_row() -> None:
    """`A_VERSION_IS_THE_SAME_PACK_MOVED_IN_PLACE`, as the statement. Delete this and a versioning
    can be rewritten as an insert beside a retirement, which strands every assignment on the old row
    and takes the pack away from all its holders the moment it is improved."""
    pack = pack_row()
    compiled = versioning_pack(pack, 1, "new label", ["read:ticket"]).compile()
    rendered_update = str(compiled)

    assert rendered_update.startswith("UPDATE gate.capability_pack SET")
    assert "version=(gate.capability_pack.version + " in rendered_update
    assert "WHERE gate.capability_pack.id = " in rendered_update
    assert "gate.capability_pack.deleted_at IS NULL" in rendered_update
    assert compiled.params["id_1"] == pack.id
    assert compiled.params["version_1"] == 1
    assert "deleted_at=" not in rendered_update
    assert "deleted_at=statement_timestamp()" in str(retiring_pack(pack, 1).compile())


def test_the_trigger_and_the_recorder_write_a_packs_version_the_same_way() -> None:
    """Delete this and the prefix a deployed database writes and the one `AuditRecorder.pack`
    writes can come apart, or the version be written as a bare number the ledger refuses to load,
    or the recorder accept a retirement at a version or a creation at none."""

    def recorder() -> AuditRecorder:
        return AuditRecorder(
            AuditChain(),
            actor_id="u_admin",
            ent_hash="0" * 32,
            trace_id="t",
            clock=lambda: LONG_AGO,
        )

    migration = migration_module(LABEL_MIGRATION)
    entry = recorder().pack(name="helpdesk", change=PackChange.VERSIONED, version=3)
    retired = recorder().pack(name="helpdesk", change=PackChange.RETIRED)

    assert migration.PACK_VERSION_PREFIX == PACK_VERSION_PREFIX
    assert (entry.subject, entry.details) == (
        "pack:helpdesk",
        {"change": "versioned", "version": "v3"},
    )
    assert retired.details == {"change": "retired"}
    body = squash(migration.PACK_TRIGGER_FUNCTION)
    assert "jsonb_build_object('version', 'v' || NEW.version::text)" in body
    assert "v_seq, v_at, v_actor, 'pack', v_subject, v_ent_hash," in body
    assert "OLD.capabilities IS DISTINCT FROM NEW.capabilities" in body
    assert "OLD.description IS DISTINCT FROM NEW.description" in body
    wrong: list[dict[str, Any]] = [
        {"change": PackChange.CREATED},
        {"change": PackChange.RETIRED, "version": 2},
        {"change": PackChange.VERSIONED, "version": 0},
    ]
    for one in wrong:
        with pytest.raises(ValueError):
            recorder().pack(name="helpdesk", **one)


def test_the_migration_adds_the_version_the_triggers_and_both_vocabularies_and_grants_nothing() -> (
    None
):
    """Rendered, not read off the file. Delete this and the column can arrive without its default,
    so the migration fails on a populated table; a trigger can be written and never created; the
    action or the subject grammar can be widened in a constant nobody executes; or the downgrade
    can narrow either without `NOT VALID` and fail on every install that used the release."""
    migration = migration_module(LABEL_MIGRATION)
    upgrade = squash(rendered("upgrade", LABEL_MIGRATION))
    downgrade = squash(rendered("downgrade", LABEL_MIGRATION))
    # The lists in the database when this lands: `0137`'s actions and `0136`'s subject grammar.
    earlier = migration_module(VERSIONS / "0137_agent_lifecycle_audit.py")
    halted = migration_module(VERSIONS / "0136_ops_halt.py")

    assert (
        "ALTER TABLE gate.capability_pack ADD COLUMN version INTEGER DEFAULT 1 NOT NULL "
        "CONSTRAINT ck_capability_pack_version_at_least_one CHECK (version >= 1)"
    ) in upgrade
    assert (
        "CREATE TRIGGER capability_pack_is_audited AFTER INSERT OR UPDATE ON gate.capability_pack "
        "FOR EACH ROW EXECUTE FUNCTION gate.record_pack_change()"
    ) in upgrade
    assert (
        "CREATE TRIGGER principal_creation_is_audited AFTER INSERT ON auth.principal "
        "FOR EACH ROW EXECUTE FUNCTION auth.record_principal_created()"
    ) in upgrade
    assert squash(f"CHECK ({migration.WIDENED_ACTIONS})") in upgrade
    assert squash(f"CHECK ({migration.WIDENED_SUBJECTS})") in upgrade
    assert squash(f"CHECK ({migration.NARROWER_ACTIONS}) NOT VALID") in downgrade
    assert squash(f"CHECK ({migration.NARROWER_SUBJECTS}) NOT VALID") in downgrade
    assert "ALTER TABLE gate.capability_pack DROP COLUMN version" in downgrade
    assert "DROP TRIGGER capability_pack_is_audited ON gate.capability_pack" in downgrade
    assert "DROP TRIGGER principal_creation_is_audited ON auth.principal" in downgrade
    assert "GRANT" not in upgrade
    assert squash(migration.NARROWER_ACTIONS) == squash(earlier.WIDENED_ACTIONS)
    assert squash(migration.NARROWER_SUBJECTS) == squash(halted.WIDENED_SUBJECTS)
    assert migration.down_revision == earlier.revision
    assert squash(migration.WIDENED_ACTIONS) == squash(one_of("action", AuditAction))
    assert squash(migration.WIDENED_SUBJECTS) == squash(f"subject ~ '{SUBJECT_PATTERN}'")
    assert check_file(LABEL_MIGRATION) == []


# ----------------------------------------------------------------- against a database


@contextmanager
def through_0141(database: str) -> Iterator[str]:
    """A database migrated to head, which with pgvector, as CI has, runs `0141` for real."""
    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("0141 sits on the whole chain, which runs only where pgvector is")
        yield url


def test_each_pack_write_reaches_its_row_one_ledger_entry_and_every_holder() -> None:
    """**M27.15.24 on PostgreSQL, through the application's own routes.** A pack is created,
    assigned to a person, versioned, copied, refused retirement while held, and retired once the
    assignment is removed. The rows hold exactly that; the ledger holds one `pack` entry per write,
    each naming the writer with the request's reach digest and trace and the version a creation or
    a versioning left, and nothing for the refused press; and the resolver gives the holder exactly
    the new version's capabilities without anybody being granted anything again. The chain
    verifies.

    Delete this and a write can reach its row and not the ledger, be recorded under the database
    role, record a version the row does not hold, or a versioning can leave its holders at the old
    bundle. **Skips without a server.**"""
    with through_0141("brain_pack_writes") as url:
        for capability in ("read:ticket", "write:ticket", "read:invoice"):
            sql(
                url,
                "INSERT INTO gate.capability_registry (capability, description)"
                " VALUES (%s, 'what it reaches')",
                capability,
            )
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department)"
            " VALUES ('u_holder', 'human', 'staff', 'Holder', 'maintenance')",
        )
        sql(
            url,
            "INSERT INTO gate.scope (slug, predicate)"
            " VALUES ('maintenance', '{\"department\": \"maintenance\"}')",
        )
        before = len(entries(url, "pack"))

        async def go(client: Any) -> list[tuple[int, dict[str, Any]]]:
            done: list[tuple[int, dict[str, Any]]] = []
            for path, body in (
                (PACKS_PATH, {**creating("billing", "read:ticket"), "label": "Billing"}),
                (
                    ASSIGN_PATH,
                    {
                        "principal_id": "u_holder",
                        "pack_slug": "billing",
                        "scope_slug": "maintenance",
                        "reason": "joined billing",
                    },
                ),
                (
                    PACK_VERSION_PATH,
                    {
                        "slug": "billing",
                        "expected_version": 1,
                        "label": "Billing, with invoices",
                        "capabilities": ["read:ticket", "read:invoice"],
                    },
                ),
                (PACK_COPY_PATH, {"slug": "billing", "new_slug": "billing_two", "label": "Two"}),
                (PACK_RETIREMENT_PATH, {"slug": "billing", "expected_version": 2}),
            ):
                answer = await client.post(path, json=body, headers=headers("u_admin"))
                done.append((answer.status_code, answer.json()))
            return done

        from tests.unit.test_console_control_audit import pressed

        pressed_first = pressed(url, WRITERS, go)
        holder = sql(url, "SELECT gate.resolve_entitlements('u_holder', now())")
        sql(
            url,
            "UPDATE gate.capability_pack_assignment SET deleted_at = statement_timestamp()"
            " WHERE principal_id = 'u_holder'",
        )

        async def retire(client: Any) -> tuple[int, dict[str, Any]]:
            answer = await client.post(
                PACK_RETIREMENT_PATH,
                json={"slug": "billing", "expected_version": 2},
                headers=headers("u_admin"),
            )
            return answer.status_code, answer.json()

        retired = pressed(url, WRITERS, retire)
        packs = sql(
            url,
            "SELECT name, description, capabilities, version, deleted_at IS NOT NULL"
            " FROM gate.capability_pack ORDER BY name",
        )
        found = entries(url, "pack")[before:]
        chain = sql(url, "SELECT count(*) FROM obs.audit_entry")

    statuses = [status for status, _ in pressed_first]
    refused = pressed_first[-1][1]
    assert statuses == [201, 201, 200, 201, 404], pressed_first
    assert refused["message"] == f"Nothing was changed: {A_PACK_SOMEBODY_HOLDS_IS_NOT_RETIRED}."
    assert retired[0] == 200, retired
    assert (retired[1]["change"], retired[1]["version"]) == ("retired", 2)
    assert packs == [
        ("billing", "Billing, with invoices", ["read:ticket", "read:invoice"], 2, True),
        ("billing_two", "Two", ["read:ticket", "read:invoice"], 1, False),
    ]
    assert [(one.actor_id, one.subject, dict(one.details)) for one in found] == [
        ("u_admin", "pack:billing", {"change": "created", "version": "v1"}),
        ("u_admin", "pack:billing", {"change": "versioned", "version": "v2"}),
        ("u_admin", "pack:billing_two", {"change": "created", "version": "v1"}),
        ("u_admin", "pack:billing", {"change": "retired"}),
    ]
    assert all(one.ent_hash != "0" * 32 for one in found)
    assert not [one for one in found if one.trace_id.startswith("tx.")]
    held = {one["capability"]["value"] for one in holder[0][0]["grants"]}
    assert {"read:ticket", "read:invoice"} <= held
    assert "write:ticket" not in held
    assert chain[0][0] > len(found)
