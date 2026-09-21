"""Departments, teams and scopes created, renamed and retired from the console, each change audited.

M27.11.1, followed from the decision to the ledger. **The first half needs no server.** It holds the
decisions in `brain.console.organisation` to who may change the structure; it reads `0086` as the
SQL it renders and holds its three triggers' subjects and details to
`AuditRecorder.organisation`'s; and it drives the eight routes over HTTP with the structure in
memory, where every question is still the route's own callable asked about the row as the double
holds it, exactly as `brain.identity.organisation_store.StoredOrganisation` asks it.

**The second half presses the routes against PostgreSQL**, through the application's own routes,
signed in with the grants each act asks for, against a database built through the migrations that
ship and connected as the application role, so every policy applies. It reads the rows as the
superuser and the ledger as `AuditEntry`s with the chain verified, and reads the behaviour through
the grant route and the one resolver. **It skips without a server**, which is CI's to provide; a
server without pgvector builds what `0086` sits on by running `0062`'s chain and then `0086`, which
`through_0086` states.

Task ids: M27.11.1
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain import govern_people_routes as routes
from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.audit.ledger import AuditChain
from brain.audit.record import AuditRecorder, OrganisationChange
from brain.console.organisation import (
    A_DEPARTMENTS_OWN_SCOPE_GOES_WITH_ITS_DEPARTMENT,
    A_RETIRED_DEPARTMENT_LEAVES_EVERY_GRANT_ALREADY_WRITTEN_IN_FORCE,
    COMPANY_ID,
    DEPARTMENT_AUTHORITY,
    SCOPE_AUTHORITY,
    THE_COMPANY_WIDE_SCOPE_IS_NEVER_RETIRED,
    Department,
    Member,
    drawn,
    founded,
    may_draw_scope,
    may_found_or_retire_departments,
    may_know_taken_scope,
    may_shape_department,
    names_department,
    retired_with,
    scope_retirement,
)
from brain.console.reads import Plane, plane_capability
from brain.console.scoped_authority import REACH_AUTHORITY
from brain.core.department import Department as DepartmentRecord
from brain.core.department import DepartmentError, ScopeRecord, membership_scope
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.demo import DEMO_PREFIX
from brain.firstrun import GRANTED_BY
from brain.gate.entitlement_store import StoredEntitlements
from brain.identity.first_administrator import ADMINISTRATION, OVERSIGHT
from brain.identity.organisation_store import (
    Attribution,
    StoredOrganisation,
    Structured,
    StructureRecords,
    StructureRefusal,
)
from brain.identity.teams import Team as TeamRecord
from brain.identity.teams import references_team, team_scope
from brain.ops.replica_store import Served
from brain.ops.starter import COMPANY_SCOPE
from brain.ops.starter_store import furnish
from brain.session import make_session_factory
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.http_client import Response
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_console_control_audit import pressed
from tests.unit.test_credential_writes import entries
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

MIGRATION: Final = VERSIONS / "0086_organisation_structure_audit.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
LATER: Final = datetime(2999, 1, 1, tzinfo=UTC)

WHOLE: Final = Scope.unrestricted()
WEB: Final = Scope.department("web")
CONFIGURATION: Final = plane_capability(Plane.CONFIGURATION)

#: The capability the grant tests grant over the scopes they draw.
GRANTED: Final = "read:knowledge"
#: A second one, for a grant asked for after a retirement.
GRANTED_LATER: Final = "read:question"


def grant(capability: Capability | str, scope: Scope = WHOLE) -> Grant:
    value = capability if isinstance(capability, Capability) else Capability(value=capability)
    return Grant(capability=value, scope=scope)


def reach(principal_id: str, *grants: Grant) -> EntitlementSet:
    return EntitlementSet(principal_id=principal_id, grants=grants)


#: Everything the structure asks for, over the whole company, and what the Departments page and
#: the grant route read. The people are the ones `tests/unit/test_api_routes.SUBJECTS` signs in.
EVERYTHING: Final[tuple[Grant, ...]] = (
    grant(DEPARTMENT_AUTHORITY),
    grant(SCOPE_AUTHORITY),
    grant(REACH_AUTHORITY),
    grant("read:scope"),
    grant("read:grant"),
    grant(GRANTED),
    grant(GRANTED_LATER),
    grant(CONFIGURATION),
)

#: A department administrator of web: both authorities, and the page's read, in web only.
IN_WEB: Final[tuple[Grant, ...]] = (
    grant(DEPARTMENT_AUTHORITY, WEB),
    grant(SCOPE_AUTHORITY, WEB),
    grant("read:scope", WEB),
    grant(CONFIGURATION),
)

GRANTS: Final[Mapping[str, tuple[Grant, ...]]] = {
    "u_admin": EVERYTHING,
    "u_elsewhere": IN_WEB,
    "u_none": (grant("read:scope"), grant(CONFIGURATION)),
}


# --------------------------------------------------------------------------- the decisions


def test_founding_or_retiring_a_department_takes_both_authorities_over_the_whole_company() -> None:
    """Delete this and a department administrator can create a department whose scope nobody could
    have granted them, or retire one and with it a scope naming a department they were never shown;
    or somebody holding only one of the two authorities writes a scope under the other's name."""
    assert may_found_or_retire_departments(reach("u_admin", *EVERYTHING), LATER)
    assert not may_found_or_retire_departments(reach("u_elsewhere", *IN_WEB), LATER)
    assert not may_found_or_retire_departments(reach("u_d", grant(DEPARTMENT_AUTHORITY)), LATER)
    assert not may_found_or_retire_departments(reach("u_s", grant(SCOPE_AUTHORITY)), LATER)
    lapsed = EntitlementSet(principal_id="u_old", grants=EVERYTHING, not_after=LONG_AGO)
    assert not may_found_or_retire_departments(lapsed, LATER)


def test_a_department_administrator_shapes_their_own_department_and_no_other() -> None:
    """Delete this and `may_shape_department` can ask about the wrong predicate, and a web
    administrator renames finance or gives it a team; the positive half stops it refusing
    everyone."""
    web = reach("u_elsewhere", *IN_WEB)
    admin = reach("u_admin", *EVERYTHING)

    assert may_shape_department(web, department="web", now=LATER)
    assert not may_shape_department(web, department="finance", now=LATER)
    assert may_shape_department(admin, department="finance", now=LATER)
    assert not may_shape_department(reach("u_s", grant(SCOPE_AUTHORITY)), department="web")


def test_a_scope_is_drawn_or_retired_only_inside_the_authority_over_scopes() -> None:
    """Delete this and a web administrator draws a scope over web and finance and grants over a
    boundary wider than their own, or the authority over departments stands in for the one over
    scopes."""
    web = reach("u_elsewhere", *IN_WEB)

    assert may_draw_scope(web, membership_scope(["web"]), LATER)
    assert not may_draw_scope(web, membership_scope(["web", "finance"]), LATER)
    assert not may_draw_scope(web, WHOLE, LATER)
    assert may_draw_scope(reach("u_admin", *EVERYTHING), WHOLE, LATER)
    assert not may_draw_scope(reach("u_d", grant(DEPARTMENT_AUTHORITY)), WEB, LATER)


def test_a_scope_names_a_department_by_any_clause_admitting_it_and_the_company_names_none() -> None:
    """Delete this and retiring web leaves live a scope over web and sales, so a new grant can still
    reach web; or it retires the company-wide scope, which admits every department and names
    none."""
    assert names_department(membership_scope(["web"]), "web")
    assert names_department(membership_scope(["sales", "web"]), "web")
    assert not names_department(membership_scope(["sales", "web"]), "finance")
    prefix = Scope(clauses=(Clause(field="department", op=Op.PREFIX, value="we"),))
    assert names_department(prefix, "web")
    anything = Scope(clauses=(Clause(field="department", op=Op.ANY),))
    assert not names_department(anything, "web")
    other_field = Scope(clauses=(Clause(field="team", op=Op.EQ, value="web"),))
    assert not names_department(other_field, "web")
    assert not names_department(COMPANY_SCOPE.scope, "web")


def test_retiring_a_department_takes_its_own_scope_by_name_and_every_scope_naming_it() -> None:
    """Delete this and a department's own scope whose row the type refuses stays live under a
    retired department's name, or a scope naming only somebody else is retired with it."""
    both = drawn("web_and_sales", "Web and sales", ["web", "sales"])
    sales = drawn("sales_only", "Sales", ["sales"])

    assert retired_with("web", None, department="web", defining="web")
    assert retired_with(both.slug, both, department="web", defining="web")
    assert not retired_with(sales.slug, sales, department="web", defining="web")
    assert not retired_with("broken", None, department="web", defining="web")
    assert not retired_with(COMPANY_SCOPE.slug, COMPANY_SCOPE, department="web", defining="web")


def test_a_scope_retirement_refuses_out_of_reach_then_the_company_then_a_departments_own() -> None:
    """The order is the property. Delete this and the company-wide scope's sentence is said to a
    web administrator, which tells them nothing new but is a sentence to somebody outside the
    authority, or a department's own scope is retired alone and its department has no scope."""
    admin = reach("u_admin", *EVERYTHING)
    web = reach("u_elsewhere", *IN_WEB)
    own = founded("web", "Web")[1]
    drawn_in_web = drawn("web_all", "Web", ["web"])

    assert scope_retirement(web, COMPANY_SCOPE, defines_a_live_department=False, now=LATER) is (
        StructureRefusal.NOT_WRITABLE
    )
    assert scope_retirement(admin, COMPANY_SCOPE, defines_a_live_department=False, now=LATER) is (
        StructureRefusal.COMPANY_WIDE_SCOPE
    )
    assert scope_retirement(web, own, defines_a_live_department=False, now=LATER) is (
        StructureRefusal.DEPARTMENTS_OWN_SCOPE
    )
    assert scope_retirement(web, drawn_in_web, defines_a_live_department=True, now=LATER) is (
        StructureRefusal.DEPARTMENTS_OWN_SCOPE
    )
    assert scope_retirement(web, drawn_in_web, defines_a_live_department=False, now=LATER) is None


def test_a_taken_scope_name_is_said_only_to_a_reader_whose_authority_contains_that_scope() -> None:
    """Delete this and a web administrator trying a short name learns that a scope over finance
    holds it, which is a scope they were never shown; the positive half stops it saying nothing."""
    web = reach("u_elsewhere", *IN_WEB)

    assert may_know_taken_scope(web, drawn("web_all", "Web", ["web"]), LATER)
    assert not may_know_taken_scope(web, drawn("finance_all", "Finance", ["finance"]), LATER)
    assert not may_know_taken_scope(reach("u_admin", *EVERYTHING), None, LATER)


def test_the_two_authorities_are_administration_held_with_the_audit_of_what_they_change() -> None:
    """Delete this and the capabilities can be renamed in the decisions and not in the declaration,
    so no first administrator holds them, reconciliation grants the old name and the registry lists
    a capability nothing checks; or the new ledger kinds arrive with no administrator able to read
    what was changed."""
    assert DEPARTMENT_AUTHORITY.value in ADMINISTRATION
    assert SCOPE_AUTHORITY.value in ADMINISTRATION
    assert {"read:audit.department", "read:audit.scope"} <= set(OVERSIGHT)


def test_a_new_department_is_written_with_the_one_scope_that_defines_it() -> None:
    """Delete this and a department can be written with no scope of its own, which no grant can
    name, or with the wizard's other two scopes, which reach no row; or its company id can become
    something a company typed."""
    department, scope = founded("web", "Web design")

    assert department == DepartmentRecord(
        company_id=COMPANY_ID, slug="web", name="Web design", scope_slug="web"
    )
    assert scope.slug == department.scope_slug
    assert scope.is_department
    assert scope.predicate() == {"department": "web"}
    assert COMPANY_SCOPE.slug == COMPANY_ID
    assert not COMPANY_ID.startswith(DEMO_PREFIX)
    with pytest.raises(ValueError, match="usable department slug"):
        founded("Web", "Web")
    assert issubclass(DepartmentError, Exception)


def test_a_drawn_scope_is_over_the_departments_named_and_never_a_departments_own() -> None:
    """Delete this and a scope over one department is written as a membership of one, which hashes
    differently from the same scope everywhere else, or a drawn scope carries the department flag
    and cannot be retired."""
    one = drawn("web_all", "Web", ["web"])
    several = drawn("web_and_sales", "Web and sales", ["web", "sales"])

    assert one.predicate() == {"department": "web"}
    assert several.predicate() == {"department": ["sales", "web"]}
    assert not one.is_department
    assert not several.is_department


def test_the_company_wide_scope_restricts_nothing_so_its_retirement_is_always_refused() -> None:
    """The refusal is keyed on a scope restricting nothing, and furnishing's scope is the one that
    must meet it. Delete this and a furnished scope given a clause would be retirable from the
    console with nothing failing."""
    assert COMPANY_SCOPE.scope.is_unrestricted()


# ------------------------------------------------------------------ the migration and the recorder


def recorder() -> AuditRecorder:
    return AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash="0" * 32, trace_id="t", clock=lambda: LONG_AGO
    )


def test_the_triggers_write_the_subjects_and_details_the_recorder_writes() -> None:
    """Delete this and the entries a deployed database keeps and the entries `AuditRecorder` writes
    can come apart with no server to notice: a team filed under its own id rather than its
    department, a predicate's value put in the details, or an operator's edit left unrecorded.
    Read off the executed module."""
    created = recorder().organisation(change=OrganisationChange.CREATED, department="web")
    team = recorder().organisation(
        change=OrganisationChange.RENAMED, department="web", team="web.design"
    )
    changed = recorder().organisation(
        change=OrganisationChange.CHANGED,
        scope="web_all",
        fields=("predicate", "label"),
        actor_inferred=True,
    )
    migration = migration_module(MIGRATION)
    department = squash(migration.DEPARTMENT_TRIGGER_FUNCTION)
    teams = squash(migration.TEAM_TRIGGER_FUNCTION)
    scopes = squash(migration.SCOPE_TRIGGER_FUNCTION)

    assert (created.subject, created.details) == ("department:web", {"change": "created"})
    assert (team.subject, team.details) == (
        "department:web",
        {"change": "renamed", "team": "web.design"},
    )
    assert (changed.subject, changed.details) == (
        "scope:web_all",
        {"change": "changed", "fields": "label,predicate", "actor": "inferred"},
    )
    assert "v_subject text := 'department:' || NEW.slug;" in department
    assert "v_subject text := 'scope:' || NEW.slug;" in scopes
    assert "v_subject := 'department:' || v_department; v_team := v_department || '.' ||" in teams
    assert "jsonb_build_object('change', v_changes[i]) || jsonb_build_object('team', v_team);" in (
        teams
    )
    for body in (department, teams, scopes):
        assert "v_actor := COALESCE(v_supplied, session_user::text);" in body
        assert "v_seq, v_at, v_actor, 'organisation', v_subject, v_ent_hash," in body
        assert "v_changes := v_changes || 'created'::text;" in body
        assert "IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN" in body
        assert "v_details := v_details || jsonb_build_object('fields', v_fields);" in body
        assert "jsonb_build_object('actor', 'inferred')" in body
        assert "predicate'" not in body.replace("'predicate'", "")
    assert "ARRAY['id', 'created_at', 'updated_at', 'deleted_at', 'name']" in department
    assert "ARRAY['id', 'created_at', 'updated_at', 'deleted_at', 'name']" in teams
    assert "ARRAY['id', 'created_at', 'updated_at', 'deleted_at']" in scopes


def test_the_recorder_refuses_a_structure_change_no_trigger_writes() -> None:
    """Delete this and an entry can name a person on a department's creation, rename a scope, put a
    team under a scope, or list fields on a creation, none of which a trigger writes and every
    reader would believe."""
    for where in (
        {"change": OrganisationChange.CREATED, "department": "web", "principal_id": "u_1"},
        {"change": OrganisationChange.CREATED},
        {"change": OrganisationChange.CREATED, "department": "web", "scope": "web"},
        {"change": OrganisationChange.RENAMED, "scope": "web_all"},
        {"change": OrganisationChange.RETIRED, "scope": "web_all", "team": "web.design"},
        {"change": OrganisationChange.CREATED, "department": "web", "fields": ("name",)},
        {"change": OrganisationChange.CHANGED, "department": "web"},
        {
            "change": OrganisationChange.JOINED,
            "team": "web.design",
            "principal_id": "u_1",
            "actor_inferred": True,
        },
    ):
        with pytest.raises(ValueError):
            recorder().organisation(**where)
    # The positive case of the placement half, which the extension must not have taken away.
    placed = recorder().organisation(
        change=OrganisationChange.JOINED, principal_id="u_1", team="web.design"
    )
    assert placed.subject == "principal:u_1"


def test_the_migration_audits_the_three_tables_widens_the_grammar_and_grants_nothing() -> None:
    """Rendered, not read off the file. Delete this and a trigger can be written and never created,
    fire on insert and not on the retirement, the grammar be widened in a constant nobody executes,
    or a grant widen what the application may do to three tables it already writes."""
    upgrade = squash(rendered("upgrade", MIGRATION))
    downgrade = squash(rendered("downgrade", MIGRATION))
    migration = migration_module(MIGRATION)
    from brain.tables.audit import SUBJECT_PATTERN

    for table, function in (
        ("department", "gate.record_department_change"),
        ("team", "gate.record_team_change"),
        ("scope", "gate.record_scope_change"),
    ):
        assert (
            f"CREATE TRIGGER {table}_is_audited AFTER INSERT OR UPDATE ON gate.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION {function}()"
        ) in upgrade
        assert f"DROP TRIGGER {table}_is_audited ON gate.{table}" in downgrade
        assert f"DROP FUNCTION {function}()" in downgrade
    assert squash(f"CHECK (subject ~ '{SUBJECT_PATTERN}')") in upgrade
    assert squash(migration.WIDENED_SUBJECTS) == squash(f"subject ~ '{SUBJECT_PATTERN}'")
    assert squash(f"CHECK ({migration.NARROWER_SUBJECTS}) NOT VALID") in downgrade
    assert "GRANT" not in upgrade
    assert migration.TABLES == ()


# ------------------------------------------------------------------------- the routes


@dataclass
class Structure(StructureRecords):
    """`StructureRecords` in memory. Every question is the route's callable, asked about the rows
    as this holds them, in the order `StoredOrganisation` asks it."""

    departments: dict[str, tuple[str, str]] = field(default_factory=dict)
    teams: dict[tuple[str, str], str] = field(default_factory=dict)
    scopes: dict[str, ScopeRecord] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    by: list[Attribution] = field(default_factory=list)
    #: A refusal every write answers with instead of doing anything, when set.
    answer: StructureRefusal | None = None

    def _asked(self, name: str, by: Attribution) -> StructureRefusal | None:
        self.calls.append(name)
        self.by.append(by)
        return self.answer

    async def found_department(
        self, *, department: DepartmentRecord, scope: ScopeRecord, by: Attribution
    ) -> Structured:
        if (refused := self._asked("found_department", by)) is not None:
            return refused
        if department.slug in self.departments or scope.slug in self.scopes:
            return StructureRefusal.NAME_TAKEN
        self.scopes[scope.slug] = scope
        self.departments[department.slug] = (department.name, department.scope_slug)
        return LONG_AGO

    async def rename_department(
        self, *, slug: str, expected_name: str, name: str, by: Attribution
    ) -> Structured:
        if (refused := self._asked("rename_department", by)) is not None:
            return refused
        if slug not in self.departments:
            return StructureRefusal.NOT_WRITABLE
        if self.departments[slug][0] != expected_name:
            return StructureRefusal.CHANGED_SINCE
        self.departments[slug] = (name, self.departments[slug][1])
        return LONG_AGO

    async def retire_department(
        self,
        *,
        slug: str,
        expected_name: str,
        takes: Callable[[str, ScopeRecord | None, str], bool],
        by: Attribution,
    ) -> Structured:
        if (refused := self._asked("retire_department", by)) is not None:
            return refused
        if slug not in self.departments:
            return StructureRefusal.NOT_WRITABLE
        name, defining = self.departments[slug]
        if name != expected_name:
            return StructureRefusal.CHANGED_SINCE
        for key in [one for one in self.teams if one[0] == slug]:
            del self.teams[key]
        for scope in [one for one, record in self.scopes.items() if takes(one, record, defining)]:
            del self.scopes[scope]
        del self.departments[slug]
        return LONG_AGO

    async def add_team(self, *, team: TeamRecord, by: Attribution) -> Structured:
        if (refused := self._asked("add_team", by)) is not None:
            return refused
        if team.department_slug not in self.departments:
            return StructureRefusal.NOT_WRITABLE
        if (team.department_slug, team.slug) in self.teams:
            return StructureRefusal.NAME_TAKEN
        self.teams[(team.department_slug, team.slug)] = team.name
        return LONG_AGO

    async def rename_team(
        self, *, department: str, slug: str, expected_name: str, name: str, by: Attribution
    ) -> Structured:
        if (refused := self._asked("rename_team", by)) is not None:
            return refused
        if (department, slug) not in self.teams:
            return StructureRefusal.NOT_WRITABLE
        if self.teams[(department, slug)] != expected_name:
            return StructureRefusal.CHANGED_SINCE
        self.teams[(department, slug)] = name
        return LONG_AGO

    async def retire_team(
        self, *, department: str, slug: str, expected_name: str, by: Attribution
    ) -> Structured:
        if (refused := self._asked("retire_team", by)) is not None:
            return refused
        if (department, slug) not in self.teams:
            return StructureRefusal.NOT_WRITABLE
        if self.teams[(department, slug)] != expected_name:
            return StructureRefusal.CHANGED_SINCE
        del self.teams[(department, slug)]
        return LONG_AGO

    async def draw_scope(
        self,
        *,
        scope: ScopeRecord,
        departments: Sequence[str],
        may_know: Callable[[ScopeRecord | None], bool],
        by: Attribution,
        team: str | None = None,
    ) -> Structured:
        if (refused := self._asked("draw_scope", by)) is not None:
            return refused
        if scope.slug in self.scopes:
            if may_know(self.scopes[scope.slug]):
                return StructureRefusal.NAME_TAKEN
            return StructureRefusal.NOT_WRITABLE
        if not set(departments) <= set(self.departments):
            return StructureRefusal.UNKNOWN_DEPARTMENT
        if team is not None and (departments[0], team) not in self.teams:
            return StructureRefusal.NOT_WRITABLE
        self.scopes[scope.slug] = scope
        return LONG_AGO

    async def retire_scope(
        self,
        *,
        slug: str,
        expected: Scope,
        judge: Callable[[ScopeRecord, bool], StructureRefusal | None],
        by: Attribution,
    ) -> Structured:
        if (refused := self._asked("retire_scope", by)) is not None:
            return refused
        record = self.scopes.get(slug)
        if record is None:
            return StructureRefusal.NOT_WRITABLE
        defines = any(defining == slug for _, defining in self.departments.values())
        found = judge(record, defines)
        if found is not None:
            return found
        if record.scope != expected:
            return StructureRefusal.CHANGED_SINCE
        del self.scopes[slug]
        return LONG_AGO


class Source(routes.OrganisationSource):
    """An `OrganisationSource` handing back two departments and nobody in them."""

    def __init__(self) -> None:
        object.__setattr__(self, "reads", None)

    async def load(self, *, limit: int, now: datetime) -> Served[routes.LoadedOrganisation]:
        return Served(
            value=routes.LoadedOrganisation(
                departments=(
                    Department(slug="finance", name="Finance"),
                    Department(slug="web", name="Web"),
                ),
                teams=(),
                members=(
                    Member(
                        principal_id="u_2", display_name="Wei", department="web", disabled=False
                    ),
                ),
                full=False,
            ),
            banner=None,
        )


@contextmanager
def client_over(structure: Structure) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    app.include_router(routes.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = gate_wiring(GRANTS)
        app.state.structure_records = structure
        app.state.organisation_source = Source()
        yield client


def post(client: TestClient, pid: str, path: str, body: Mapping[str, Any]) -> Response:
    answer: Response = client.post(f"{API_PREFIX}{path}", json=dict(body), headers=headers(pid))
    return answer


def seeded() -> Structure:
    """Web and finance, each with its own scope, a design team in web, and a scope over web."""
    structure = Structure()
    for slug, name in (("web", "Web"), ("finance", "Finance")):
        department, scope = founded(slug, name)
        structure.departments[slug] = (department.name, department.scope_slug)
        structure.scopes[scope.slug] = scope
    structure.teams[("web", "design")] = "Design"
    structure.scopes["web_all"] = drawn("web_all", "All of web", ["web"])
    structure.scopes["finance_all"] = drawn("finance_all", "All of finance", ["finance"])
    return structure


def test_an_administrator_creates_renames_and_retires_departments_teams_and_scopes() -> None:
    """M27.11.1 over HTTP, the positive case every refusal below needs. Delete this and every
    refusal is satisfied by routes that write nothing, the change words can be crossed, or the actor
    taken from somewhere other than the token."""
    structure = seeded()
    with client_over(structure) as client:
        answers = [
            post(client, "u_admin", "/govern/departments", {"slug": "sales", "name": "Sales"}),
            post(
                client,
                "u_admin",
                "/govern/departments/rename",
                {"slug": "sales", "expected_name": "Sales", "name": "Sales and service"},
            ),
            post(
                client,
                "u_elsewhere",
                "/govern/departments/team",
                {"department": "web", "slug": "hosting", "name": "Hosting"},
            ),
            post(
                client,
                "u_elsewhere",
                "/govern/departments/team/rename",
                {"department": "web", "slug": "hosting", "expected_name": "Hosting", "name": "Ops"},
            ),
            post(
                client,
                "u_elsewhere",
                "/govern/departments/team/retirement",
                {"department": "web", "slug": "hosting", "expected_name": "Ops"},
            ),
            post(
                client,
                "u_admin",
                "/govern/departments/scopes",
                {
                    "slug": "web_and_sales",
                    "label": "Web and sales",
                    "departments": ["web", "sales"],
                },
            ),
            post(
                client,
                "u_elsewhere",
                "/govern/departments/scopes/retirement",
                {"slug": "web_all", "expected_scope": WEB.model_dump(mode="json")},
            ),
            post(
                client,
                "u_admin",
                "/govern/departments/retirement",
                {"slug": "sales", "expected_name": "Sales and service"},
            ),
        ]

    assert [one.status_code for one in answers] == [201, 200, 201, 200, 200, 201, 200, 200]
    assert [(one.json()["kind"], one.json()["change"]) for one in answers] == [
        ("department", "created"),
        ("department", "renamed"),
        ("team", "created"),
        ("team", "renamed"),
        ("team", "retired"),
        ("scope", "created"),
        ("scope", "retired"),
        ("department", "retired"),
    ]
    assert answers[2].json()["department"] == "web"
    assert [one.actor for one in structure.by] == [
        "u_admin",
        "u_admin",
        "u_elsewhere",
        "u_elsewhere",
        "u_elsewhere",
        "u_admin",
        "u_elsewhere",
        "u_admin",
    ]
    assert all(len(one.ent_hash) == 32 for one in structure.by)
    # Retiring sales took its own scope and the scope over web and sales, and left web's.
    assert "sales" not in structure.departments
    assert set(structure.scopes) == {"web", "finance", "finance_all"}
    assert ("web", "design") in structure.teams


def ordinary(answer: Response) -> tuple[int, str]:
    return answer.status_code, str(answer.json()["message"])


def test_a_department_administrator_outside_their_department_is_answered_as_a_missing_row() -> None:
    """DENIED and ABSENT, for the structure. A web administrator renaming finance, giving it a
    team, retiring its team, drawing a scope over it, retiring its scope, creating a department and
    retiring one are each answered exactly as an administrator is answered about a department, a
    team or a scope that is not there, and every refusal that needs no row reaches no store.

    Delete this and a refusal about a place outside somebody's reach says it exists, by status, by
    sentence, or by the store being asked about it at all."""
    structure = seeded()
    with client_over(structure) as client:
        missing = [
            post(
                client,
                "u_admin",
                "/govern/departments/rename",
                {"slug": "gone", "expected_name": "Gone", "name": "Still gone"},
            ),
            post(
                client,
                "u_admin",
                "/govern/departments/team/retirement",
                {"department": "finance", "slug": "payroll", "expected_name": "Payroll"},
            ),
            post(
                client,
                "u_admin",
                "/govern/departments/scopes/retirement",
                {"slug": "gone_all", "expected_scope": WEB.model_dump(mode="json")},
            ),
        ]
        stored_before = list(structure.calls)
        outside = [
            post(
                client,
                "u_elsewhere",
                "/govern/departments/rename",
                {"slug": "finance", "expected_name": "Finance", "name": "Money"},
            ),
            post(
                client,
                "u_elsewhere",
                "/govern/departments/team",
                {"department": "finance", "slug": "payroll", "name": "Payroll"},
            ),
            post(
                client,
                "u_elsewhere",
                "/govern/departments/team/retirement",
                {"department": "finance", "slug": "payroll", "expected_name": "Payroll"},
            ),
            post(
                client,
                "u_elsewhere",
                "/govern/departments/scopes",
                {"slug": "finance_two", "label": "Finance", "departments": ["finance"]},
            ),
            post(client, "u_elsewhere", "/govern/departments", {"slug": "sales", "name": "Sales"}),
            post(
                client,
                "u_elsewhere",
                "/govern/departments/retirement",
                {"slug": "web", "expected_name": "Web"},
            ),
            post(
                client,
                "u_none",
                "/govern/departments/team",
                {"department": "web", "slug": "hosting", "name": "Hosting"},
            ),
        ]
        stored_after_outside = list(structure.calls)
        scope_outside = post(
            client,
            "u_elsewhere",
            "/govern/departments/scopes/retirement",
            {
                "slug": "finance_all",
                "expected_scope": Scope.department("finance").model_dump(mode="json"),
            },
        )

    answers = {ordinary(one) for one in (*missing, *outside, scope_outside)}
    assert answers == {ordinary(missing[0])}
    assert answers == {(404, "I could not find that.")}
    assert stored_after_outside == stored_before
    assert "finance_all" in structure.scopes
    assert structure.departments["finance"] == ("Finance", "finance")


def test_every_readable_refusal_is_a_sentence_saying_what_to_do() -> None:
    """Delete this and a duplicate name, a row changed since the page was read, a scope over a
    department that is not there, the company-wide scope and a department's own scope all answer
    "I could not find that", which tells somebody who holds the authority nothing they can act on;
    or a sentence is said for a taken scope name its reader may not know about."""
    structure = seeded()
    structure.scopes[COMPANY_SCOPE.slug] = COMPANY_SCOPE
    with client_over(structure) as client:
        taken_department = post(
            client, "u_admin", "/govern/departments", {"slug": "web", "name": "Web again"}
        )
        taken_scope_name = post(
            client, "u_admin", "/govern/departments", {"slug": "web_all", "name": "Web all"}
        )
        taken_team = post(
            client,
            "u_elsewhere",
            "/govern/departments/team",
            {"department": "web", "slug": "design", "name": "Design"},
        )
        taken_scope = post(
            client,
            "u_elsewhere",
            "/govern/departments/scopes",
            {"slug": "web_all", "label": "Web", "departments": ["web"]},
        )
        taken_elsewhere = post(
            client,
            "u_elsewhere",
            "/govern/departments/scopes",
            {"slug": "finance_all", "label": "Web", "departments": ["web"]},
        )
        changed = post(
            client,
            "u_elsewhere",
            "/govern/departments/rename",
            {"slug": "web", "expected_name": "Website", "name": "Web design"},
        )
        unknown = post(
            client,
            "u_admin",
            "/govern/departments/scopes",
            {"slug": "sales_all", "label": "Sales", "departments": ["sales"]},
        )
        company = post(
            client,
            "u_admin",
            "/govern/departments/scopes/retirement",
            {"slug": COMPANY_SCOPE.slug, "expected_scope": WHOLE.model_dump(mode="json")},
        )
        own = post(
            client,
            "u_elsewhere",
            "/govern/departments/scopes/retirement",
            {"slug": "web", "expected_scope": WEB.model_dump(mode="json")},
        )
        changed_scope = post(
            client,
            "u_admin",
            "/govern/departments/scopes/retirement",
            {"slug": "web_all", "expected_scope": WHOLE.model_dump(mode="json")},
        )

    said = {
        "department": ordinary(taken_department),
        "scope name": ordinary(taken_scope_name),
        "team": ordinary(taken_team),
        "scope": ordinary(taken_scope),
        "changed": ordinary(changed),
        "unknown": ordinary(unknown),
        "company": ordinary(company),
        "own": ordinary(own),
        "changed scope": ordinary(changed_scope),
    }
    assert {status for status, _ in said.values()} == {404}
    assert said["department"][1] == f"Nothing was changed: {routes.A_DEPARTMENT_NAME_IS_TAKEN}."
    assert said["scope name"] == said["department"]
    assert said["team"][1] == f"Nothing was changed: {routes.A_TEAM_NAME_IS_TAKEN}."
    assert said["scope"][1] == f"Nothing was changed: {routes.A_SCOPE_NAME_IS_TAKEN}."
    assert said["changed"][1] == f"Nothing was changed: {routes.IT_CHANGED_SINCE_YOU_OPENED_IT}."
    assert said["changed scope"] == said["changed"]
    assert said["unknown"][1] == f"Nothing was changed: {routes.A_SCOPE_NAMES_NO_LIVE_DEPARTMENT}."
    assert said["company"][1] == f"Nothing was changed: {THE_COMPANY_WIDE_SCOPE_IS_NEVER_RETIRED}"
    assert (
        said["own"][1] == f"Nothing was changed: {A_DEPARTMENTS_OWN_SCOPE_GOES_WITH_ITS_DEPARTMENT}"
    )
    assert ordinary(taken_elsewhere) == (404, "I could not find that.")
    assert COMPANY_SCOPE.slug in structure.scopes
    assert structure.departments["web"] == ("Web", "web")


def test_a_body_the_types_refuse_is_a_422_that_reaches_no_store() -> None:
    """Validation before the write. Delete this and a team with its department's short name, a team
    named for a role, a short name the grammar refuses, a scope naming a department twice, a rename
    to the name already held or a predicate that is not a scope reaches the store, where it is
    either a constraint violation or a row nothing can read."""
    structure = seeded()
    with client_over(structure) as client:
        answers = [
            post(
                client,
                "u_admin",
                "/govern/departments/team",
                {"department": "web", "slug": "web", "name": "Web"},
            ),
            post(
                client,
                "u_admin",
                "/govern/departments/team",
                {"department": "web", "slug": "super_admin", "name": "Admins"},
            ),
            post(client, "u_admin", "/govern/departments", {"slug": "Web-Team", "name": "Web"}),
            post(client, "u_admin", "/govern/departments", {"slug": "sales", "name": "   "}),
            post(
                client,
                "u_admin",
                "/govern/departments/scopes",
                {"slug": "twice", "label": "Twice", "departments": ["web", "web"]},
            ),
            post(
                client,
                "u_admin",
                "/govern/departments/rename",
                {"slug": "web", "expected_name": "Web", "name": "Web"},
            ),
            post(
                client,
                "u_admin",
                "/govern/departments/scopes/retirement",
                {"slug": "web_all", "expected_scope": {"department": "web"}},
            ),
            post(
                client,
                "u_admin",
                "/govern/departments/scopes",
                {"slug": "nothing", "label": "Nothing", "departments": []},
            ),
        ]

    assert [one.status_code for one in answers] == [422] * len(answers)
    assert structure.calls == []


def test_the_page_offers_each_structure_control_only_where_its_authority_is_held() -> None:
    """Presentation only, and still worth holding. Delete this and a web administrator is offered
    controls on finance that every press refuses, or the whole company's controls, or an
    administrator holding the authorities is offered none and the screen reads as read-only."""
    with client_over(Structure()) as client:
        admin = client.get(f"{API_PREFIX}/govern/departments", headers=headers("u_admin")).json()
        web = client.get(f"{API_PREFIX}/govern/departments", headers=headers("u_elsewhere")).json()
        none = client.get(f"{API_PREFIX}/govern/departments", headers=headers("u_none")).json()

    assert (admin["may_found"], admin["may_draw_scopes"]) == (True, True)
    assert [(one["slug"], one["shapeable"]) for one in admin["items"]] == [
        ("finance", True),
        ("web", True),
    ]
    assert (web["may_found"], web["may_draw_scopes"]) == (False, True)
    assert [(one["slug"], one["shapeable"]) for one in web["items"]] == [("web", True)]
    assert (none["may_found"], none["may_draw_scopes"]) == (False, False)
    assert {one["shapeable"] for one in none["items"]} == {False}
    assert admin["retiring_department"].endswith(
        A_RETIRED_DEPARTMENT_LEAVES_EVERY_GRANT_ALREADY_WRITTEN_IN_FORCE
    )


def test_the_stored_organisation_is_the_structure_the_routes_ask_for() -> None:
    """Delete this and the store can drift from the protocol the routes hold, and a route handed
    the database is handed something `structure_records_of` would not accept."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    assert isinstance(StoredOrganisation(async_sessionmaker()), StructureRecords)


# ------------------------------------------------------------------------------ the database


@contextmanager
def through_0086(database: str) -> Iterator[str]:
    """A database with `0086` applied.

    With pgvector, which CI has, `retirable` runs every migration to head. Without it, the chain
    `tests/unit/test_organisation_store.py` runs to `0062` is run, which builds the three tables,
    the ledger's grammar as `0061` left it, the setting trigger furnishing records itself with and
    the grant route's tables; `0083` is then stamped, because nothing from `0063` to `0083` touches
    what `0086` does or what these tests read, and `0086` runs for real."""
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
            migrate(database, "stamp", "0083")
            migrate(database, "upgrade", "0086")
        yield url


def a_person(url: str, principal_id: str) -> None:
    sql(
        url,
        "INSERT INTO auth.principal (id, kind, employment, display_name, primary_department)"
        " VALUES (%s, 'human', 'staff', %s, 'web')",
        principal_id,
        f"Person {principal_id}",
    )


@dataclass(frozen=True)
class Pressed:
    status: int
    body: dict[str, Any]


def pressing(url: str, presses: Sequence[tuple[str, str, Mapping[str, Any]]]) -> list[Pressed]:
    """Each `(person, path, body)` posted in order through the application over this database."""

    async def go(client: httpx.AsyncClient) -> list[Pressed]:
        done: list[Pressed] = []
        for pid, path, body in presses:
            answer = await client.post(f"{API_PREFIX}{path}", json=dict(body), headers=headers(pid))
            done.append(Pressed(answer.status_code, answer.json()))
        return done

    return pressed(url, GRANTS, go)


def organisation_entries(url: str) -> list[tuple[str, str, dict[str, str]]]:
    return [
        (one.actor_id, one.subject, dict(one.details))
        for one in entries(url)
        if one.action.value == "organisation"
    ]


def held_scope(url: str, principal_id: str, capability: str) -> Scope | None:
    """The scope the one resolver gives this person for this capability, as the application."""

    async def load() -> Scope | None:
        built = app_engine(url)
        try:
            found = await StoredEntitlements(make_session_factory(built)).load(principal_id, LATER)
        finally:
            await built.dispose()
        return found.scope_for(Capability(value=capability), LATER)

    return run(load)


def granting(
    capability: str, scope_slug: str, holder: str = "u_holder"
) -> tuple[str, str, Mapping[str, Any]]:
    return (
        "u_admin",
        "/govern/grants",
        {
            "principal_id": holder,
            "capability": capability,
            "scope_slug": scope_slug,
            "reason": "the work needs it",
        },
    )


def test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor() -> None:
    """**Every route, followed to the rows and the ledger.** Two departments are created, one is
    renamed;
    a team is created, renamed and retired; a scope over both departments is drawn and retired; and
    one department is retired. The tables then hold exactly those rows, live or retired, and the
    ledger holds one `organisation` entry per row written, in order, each naming the person who
    pressed, with the request's reach digest and trace and no inferred actor, and the chain
    verifies.

    Delete this and a change can reach its row and not the ledger, a trigger can record a rename as
    a
    change or a retirement as nothing, a team can be filed under the wrong department, or the entry
    can name the database role rather than the person. **Skips without a server.**"""
    with through_0086("brain_structure_writes") as url:
        answers = pressing(
            url,
            (
                ("u_admin", "/govern/departments", {"slug": "web", "name": "Web"}),
                ("u_admin", "/govern/departments", {"slug": "sales", "name": "Sales"}),
                (
                    "u_admin",
                    "/govern/departments/rename",
                    {"slug": "web", "expected_name": "Web", "name": "Web design"},
                ),
                (
                    "u_elsewhere",
                    "/govern/departments/team",
                    {"department": "web", "slug": "design", "name": "Design"},
                ),
                (
                    "u_elsewhere",
                    "/govern/departments/team/rename",
                    {
                        "department": "web",
                        "slug": "design",
                        "expected_name": "Design",
                        "name": "Visual design",
                    },
                ),
                (
                    "u_admin",
                    "/govern/departments/scopes",
                    {"slug": "web_and_sales", "label": "Both", "departments": ["web", "sales"]},
                ),
                (
                    "u_admin",
                    "/govern/departments/scopes/retirement",
                    {
                        "slug": "web_and_sales",
                        "expected_scope": membership_scope(["web", "sales"]).model_dump(
                            mode="json"
                        ),
                    },
                ),
                (
                    "u_elsewhere",
                    "/govern/departments/team/retirement",
                    {"department": "web", "slug": "design", "expected_name": "Visual design"},
                ),
                (
                    "u_admin",
                    "/govern/departments/retirement",
                    {"slug": "sales", "expected_name": "Sales"},
                ),
            ),
        )
        departments = sql(
            url,
            "SELECT slug, name, scope_slug, company_id, deleted_at IS NOT NULL"
            " FROM gate.department ORDER BY slug",
        )
        teams = sql(url, "SELECT slug, name, deleted_at IS NOT NULL FROM gate.team")
        scopes = sql(
            url,
            "SELECT slug, predicate, is_department, deleted_at IS NOT NULL FROM gate.scope"
            " ORDER BY slug",
        )
        found = organisation_entries(url)
        chain = entries(url)

    assert [one.status for one in answers] == [201, 201, 200, 201, 200, 201, 200, 200, 200], [
        one.body for one in answers
    ]
    assert departments == [
        ("sales", "Sales", "sales", COMPANY_ID, True),
        ("web", "Web design", "web", COMPANY_ID, False),
    ]
    assert teams == [("design", "Visual design", True)]
    assert scopes == [
        ("sales", {"department": "sales"}, True, True),
        ("web", {"department": "web"}, True, False),
        ("web_and_sales", {"department": ["sales", "web"]}, False, True),
    ]
    assert found == [
        ("u_admin", "scope:web", {"change": "created"}),
        ("u_admin", "department:web", {"change": "created"}),
        ("u_admin", "scope:sales", {"change": "created"}),
        ("u_admin", "department:sales", {"change": "created"}),
        ("u_admin", "department:web", {"change": "renamed"}),
        ("u_elsewhere", "department:web", {"change": "created", "team": "web.design"}),
        ("u_elsewhere", "department:web", {"change": "renamed", "team": "web.design"}),
        ("u_admin", "scope:web_and_sales", {"change": "created"}),
        ("u_admin", "scope:web_and_sales", {"change": "retired"}),
        ("u_elsewhere", "department:web", {"change": "retired", "team": "web.design"}),
        ("u_admin", "scope:sales", {"change": "retired"}),
        ("u_admin", "department:sales", {"change": "retired"}),
    ]
    written = [one for one in chain if one.action.value == "organisation"]
    assert all(one.ent_hash != "0" * 32 for one in written)
    assert not [one for one in written if one.trace_id.startswith("tx.")]
    assert AuditChain(chain).verify() is None


def test_a_duplicate_short_name_is_refused_with_a_sentence_and_writes_nothing() -> None:
    """**The refusal, and nothing behind it.** A department, a team and a scope created twice are
    each refused the second time with the sentence saying the name is taken, and neither a row nor a
    ledger entry is added by any of the three.

    Positive sibling:
    `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor`.

    Delete this and a second department under a live short name is written beside the first, which
    the partial index refuses as a constraint error, or refused with a sentence that says nothing a
    person can act on. **Skips without a server.**"""
    once = (
        ("u_admin", "/govern/departments", {"slug": "web", "name": "Web"}),
        (
            "u_admin",
            "/govern/departments/team",
            {"department": "web", "slug": "design", "name": "D"},
        ),
        (
            "u_admin",
            "/govern/departments/scopes",
            {"slug": "web_all", "label": "Web", "departments": ["web"]},
        ),
    )
    with through_0086("brain_structure_duplicates") as url:
        first = pressing(url, once)
        before = (
            sql(url, "SELECT count(*) FROM gate.department"),
            sql(url, "SELECT count(*) FROM gate.team"),
            sql(url, "SELECT count(*) FROM gate.scope"),
            len(entries(url)),
        )
        again = pressing(url, once)
        after = (
            sql(url, "SELECT count(*) FROM gate.department"),
            sql(url, "SELECT count(*) FROM gate.team"),
            sql(url, "SELECT count(*) FROM gate.scope"),
            len(entries(url)),
        )

    assert [one.status for one in first] == [201, 201, 201]
    assert [(one.status, one.body["message"]) for one in again] == [
        (404, f"Nothing was changed: {routes.A_DEPARTMENT_NAME_IS_TAKEN}."),
        (404, f"Nothing was changed: {routes.A_TEAM_NAME_IS_TAKEN}."),
        (404, f"Nothing was changed: {routes.A_SCOPE_NAME_IS_TAKEN}."),
    ]
    assert after == before


def test_the_store_answers_an_out_of_reach_row_as_it_answers_a_missing_one() -> None:
    """**DENIED and ABSENT, against the rows as the store reads them.** A web administrator renaming
    finance, retiring its team and retiring its scope gets the answer an administrator gets about a
    department, a team and a scope that are not there, and nothing about finance changes; renaming
    web and giving it a team, their own department, is written.

    Delete this and the store's refusal of an out-of-reach row can differ from its refusal of a
    missing one, in status or in words, which is a way to learn what exists. **Skips without a
    server.**"""
    with through_0086("brain_structure_reach") as url:
        setup = pressing(
            url,
            (
                ("u_admin", "/govern/departments", {"slug": "web", "name": "Web"}),
                ("u_admin", "/govern/departments", {"slug": "finance", "name": "Finance"}),
                (
                    "u_admin",
                    "/govern/departments/team",
                    {"department": "finance", "slug": "payroll", "name": "Payroll"},
                ),
                (
                    "u_admin",
                    "/govern/departments/scopes",
                    {"slug": "finance_all", "label": "Finance", "departments": ["finance"]},
                ),
            ),
        )
        finance_scope = Scope.department("finance").model_dump(mode="json")
        refused = pressing(
            url,
            (
                (
                    "u_elsewhere",
                    "/govern/departments/rename",
                    {"slug": "finance", "expected_name": "Finance", "name": "Money"},
                ),
                (
                    "u_elsewhere",
                    "/govern/departments/team/retirement",
                    {"department": "finance", "slug": "payroll", "expected_name": "Payroll"},
                ),
                (
                    "u_elsewhere",
                    "/govern/departments/scopes/retirement",
                    {"slug": "finance_all", "expected_scope": finance_scope},
                ),
                (
                    "u_admin",
                    "/govern/departments/rename",
                    {"slug": "gone", "expected_name": "Gone", "name": "Still gone"},
                ),
                (
                    "u_admin",
                    "/govern/departments/team/retirement",
                    {"department": "finance", "slug": "gone", "expected_name": "Gone"},
                ),
                (
                    "u_admin",
                    "/govern/departments/scopes/retirement",
                    {"slug": "gone_all", "expected_scope": finance_scope},
                ),
            ),
        )
        permitted = pressing(
            url,
            (
                (
                    "u_elsewhere",
                    "/govern/departments/rename",
                    {"slug": "web", "expected_name": "Web", "name": "Web design"},
                ),
                (
                    "u_elsewhere",
                    "/govern/departments/team",
                    {"department": "web", "slug": "design", "name": "Design"},
                ),
            ),
        )
        finance = sql(
            url,
            "SELECT d.name, d.deleted_at IS NULL, t.deleted_at IS NULL, s.deleted_at IS NULL"
            " FROM gate.department d JOIN gate.team t ON t.department_id = d.id"
            " JOIN gate.scope s ON s.slug = 'finance_all' WHERE d.slug = 'finance'",
        )

    assert [one.status for one in setup] == [201, 201, 201, 201]
    assert {(one.status, one.body["message"]) for one in refused} == {
        (404, "I could not find that.")
    }
    assert [one.status for one in permitted] == [200, 201]
    assert finance == [("Finance", True, True, True)]


def test_a_retired_department_refuses_a_new_grant_and_every_grant_already_written_stays() -> None:
    """**The behaviour a retirement changes, through the grant route and the one resolver.** One
    person is granted a capability over web and another over a scope naming web and sales; web is
    retired. A second person is then refused a grant over web and over the scope naming it, and
    granted one over sales, which is still live. The two grants written before stay live rows, no
    revocation is recorded, and the resolver still gives their holder exactly what they gave.

    Delete this and retiring a department can silently revoke its grants, or leave a scope naming it
    live so a new grant still reaches it, or retire a department's neighbour with it. **Skips
    without a server.**"""
    both = membership_scope(["web", "sales"])
    with through_0086("brain_structure_retired_grant") as url:
        for pid in ("u_holder", "u_other"):
            a_person(url, pid)
        before = pressing(
            url,
            (
                ("u_admin", "/govern/departments", {"slug": "web", "name": "Web"}),
                ("u_admin", "/govern/departments", {"slug": "sales", "name": "Sales"}),
                (
                    "u_admin",
                    "/govern/departments/scopes",
                    {"slug": "web_and_sales", "label": "Both", "departments": ["web", "sales"]},
                ),
                granting(GRANTED, "web"),
                granting(GRANTED_LATER, "web_and_sales"),
                (
                    "u_admin",
                    "/govern/departments/retirement",
                    {"slug": "web", "expected_name": "Web"},
                ),
            ),
        )
        after = pressing(
            url,
            (
                granting(GRANTED, "web", holder="u_other"),
                granting(GRANTED, "web_and_sales", holder="u_other"),
                granting(GRANTED, "sales", holder="u_other"),
            ),
        )
        live = sql(
            url,
            "SELECT principal_id, capability, scope FROM gate.capability_grant"
            " WHERE deleted_at IS NULL ORDER BY principal_id, capability",
        )
        revoked = [one for one in entries(url) if one.action.value == "revoke"]
        still = (held_scope(url, "u_holder", GRANTED), held_scope(url, "u_holder", GRANTED_LATER))

    assert [one.status for one in before] == [201, 201, 201, 201, 201, 200], [
        one.body for one in before
    ]
    assert [one.status for one in after] == [404, 404, 201], [one.body for one in after]
    assert live == [
        ("u_holder", GRANTED, WEB.model_dump(mode="json")),
        ("u_holder", GRANTED_LATER, both.model_dump(mode="json")),
        ("u_other", GRANTED, Scope.department("sales").model_dump(mode="json")),
    ]
    assert revoked == []
    assert still == (WEB, both)


def test_a_grant_over_a_newly_drawn_scope_is_written_through_the_grant_route() -> None:
    """**What drawing a scope is for.** Two departments and a scope over both are created from the
    console, and the grant route then writes a grant over that scope by its name, which the resolver
    gives its holder exactly as drawn. A grant over a scope nobody drew is refused beside it.

    Delete this and the console can write a scope the grant route cannot resolve, or one whose
    predicate is not the shape the grant route reads, and drawing a scope changes nothing anybody
    can be granted. **Skips without a server.**"""
    both = membership_scope(["web", "sales"])
    with through_0086("brain_structure_new_scope") as url:
        a_person(url, "u_admin")
        a_person(url, "u_holder")
        answers = pressing(
            url,
            (
                granting(GRANTED, "web_and_sales"),
                ("u_admin", "/govern/departments", {"slug": "web", "name": "Web"}),
                ("u_admin", "/govern/departments", {"slug": "sales", "name": "Sales"}),
                (
                    "u_admin",
                    "/govern/departments/scopes",
                    {"slug": "web_and_sales", "label": "Both", "departments": ["web", "sales"]},
                ),
                granting(GRANTED, "web_and_sales"),
            ),
        )
        stored = sql(
            url,
            "SELECT granted_by, scope FROM gate.capability_grant"
            " WHERE principal_id = 'u_holder' AND deleted_at IS NULL",
        )
        held = held_scope(url, "u_holder", GRANTED)

    assert [one.status for one in answers] == [404, 201, 201, 201, 201], [
        one.body for one in answers
    ]
    assert stored == [("u_admin", both.model_dump(mode="json"))]
    assert held == both


def test_retiring_the_company_wide_scope_furnishing_wrote_is_refused_with_a_sentence() -> None:
    """**The one scope that is never retired.** After furnishing, an administrator holding the
    authority over scopes everywhere asks to retire the company-wide scope and is told why not; the
    scope stays live and nothing is recorded but its creation by first run.

    Positive sibling: the retirement of a drawn scope in
    `test_each_change_writes_its_rows_and_one_ledger_entry_per_row_naming_the_actor`.

    Delete this and the scope every grant over the whole company is written at can be retired from
    the console, and furnishing never writes it again. **Skips without a server.**"""
    with through_0086("brain_structure_company_scope") as url:

        async def furnished() -> None:
            built = app_engine(url)
            try:
                await furnish(
                    make_session_factory(built),
                    actor=GRANTED_BY,
                    trace_id="install.furnish.0123456789abcdef",
                )
            finally:
                await built.dispose()

        run(furnished)
        [refused] = pressing(
            url,
            (
                (
                    "u_admin",
                    "/govern/departments/scopes/retirement",
                    {"slug": COMPANY_SCOPE.slug, "expected_scope": WHOLE.model_dump(mode="json")},
                ),
            ),
        )
        live = sql(url, "SELECT slug FROM gate.scope WHERE deleted_at IS NULL")
        found = organisation_entries(url)

    assert refused.status == 404
    assert refused.body["message"] == (
        f"Nothing was changed: {THE_COMPANY_WIDE_SCOPE_IS_NEVER_RETIRED}"
    )
    assert live == [(COMPANY_SCOPE.slug,)]
    assert found == [(GRANTED_BY, f"scope:{COMPANY_SCOPE.slug}", {"change": "created"})]


# ------------------------------------------------------------------ team scopes (M1.5.2)
def test_a_team_scope_is_its_departments_clause_and_the_teams() -> None:
    """M1.5.2: a scope predicate may reference a team. Delete this and a team scope could drop the
    department clause and admit a same-named team in every department."""
    record = drawn("web_design", "Web design", ["web"], "design")
    assert record.scope == team_scope("web.design")
    assert references_team(record.scope)
    with pytest.raises(ValueError, match="one department"):
        drawn("both_design", "Design", ["web", "finance"], "design")


def test_a_team_scope_is_drawn_for_a_live_team_and_refused_for_one_that_is_not_there() -> None:
    """The route half of M1.5.2. Delete this and a scope can name a team nobody created, or a team
    scope can never be drawn at all."""
    structure = seeded()
    with client_over(structure) as client:
        drawn_one = post(
            client,
            "u_elsewhere",
            "/govern/departments/scopes",
            {"slug": "web_design", "label": "Web design", "departments": ["web"], "team": "design"},
        )
        missing = post(
            client,
            "u_elsewhere",
            "/govern/departments/scopes",
            {"slug": "web_ops", "label": "Web ops", "departments": ["web"], "team": "ops"},
        )
        two = post(
            client,
            "u_admin",
            "/govern/departments/scopes",
            {
                "slug": "x_design",
                "label": "Design",
                "departments": ["web", "finance"],
                "team": "design",
            },
        )
    assert drawn_one.status_code == 201, drawn_one.text
    assert structure.scopes["web_design"].scope == team_scope("web.design")
    assert missing.status_code == 404
    assert "web_ops" not in structure.scopes
    assert two.status_code == 422


def test_a_grant_over_a_team_scope_resolves_to_that_team() -> None:
    """M1.5.2 on PostgreSQL: a team is created, a scope over it is drawn, a grant is written over
    that scope by name, and the resolver gives its holder the team predicate. Delete this and the
    store can write a team scope the grant route cannot resolve. **Skips without a server.**"""
    with through_0086("brain_structure_team_scope") as url:
        a_person(url, "u_admin")
        a_person(url, "u_holder")
        answers = pressing(
            url,
            (
                ("u_admin", "/govern/departments", {"slug": "web", "name": "Web"}),
                (
                    "u_admin",
                    "/govern/departments/team",
                    {"department": "web", "slug": "design", "name": "Design"},
                ),
                (
                    "u_admin",
                    "/govern/departments/scopes",
                    {"slug": "web_ops", "label": "Ops", "departments": ["web"], "team": "ops"},
                ),
                (
                    "u_admin",
                    "/govern/departments/scopes",
                    {
                        "slug": "web_design",
                        "label": "Design",
                        "departments": ["web"],
                        "team": "design",
                    },
                ),
                granting(GRANTED, "web_design"),
            ),
        )
        held = held_scope(url, "u_holder", GRANTED)

    assert [one.status for one in answers] == [201, 201, 404, 201, 201], [
        one.body for one in answers
    ]
    assert held == team_scope("web.design")
