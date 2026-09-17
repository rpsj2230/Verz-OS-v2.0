"""Who is in a team and who leads a department reach their rows, the ledger and the page.

`tests/unit/test_govern_people_routes.py` holds who may place somebody over an in-memory store, and
`tests/unit/test_organisation.py` holds the decisions. This file holds everything below them. The
first half needs no server: it reads `0062` as the SQL it renders and holds the two triggers'
subjects and details to `AuditRecorder.organisation`'s, the tables to the models, and the grants and
policies to a placement ended once.

The second half builds a database through `0062` and proves M27.7.4's writes reach the system: a
placement and an appointment made through the store and the route's own questions leave rows and
`organisation` entries by the person who made them, the Departments and teams page then lists the
member and the lead for a reader who may name them and not for one who may not, and the directory
sync's plan applied ends only what the sync made. **It skips when there is no server.**

Task ids: M27.7.4
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.audit.ledger import AuditChain, AuditEntry
from brain.audit.record import AuditRecorder, OrganisationChange
from brain.console.organisation import (
    Member,
    may_appoint,
    may_organise,
    may_place,
    organisation,
)
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.db import metadata
from brain.govern_people_routes import OrganisationSource, member_of
from brain.identity.organisation_store import (
    OrganisationRecords,
    Person,
    StoredOrganisation,
)
from brain.identity.organisation_sync import organisation_plan
from brain.identity.staff_source import Asserts, Roster, StaffRecord
from brain.ops.replica_store import ConsoleReads
from brain.session import make_session_factory
from brain.tables.organisation import SYNC_ACTOR_PREFIX
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

MIGRATION: Final = VERSIONS / "0062_organisation_and_elevation.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
LATER: Final = datetime(2999, 1, 1, tzinfo=UTC)

WHOLE: Final = Scope.unrestricted()
CONFIGURATION: Final = Grant(
    capability=Capability(value=plane_capability(Plane.CONFIGURATION).value), scope=WHOLE
)

#: Organises everywhere and reads both screens company-wide.
ADMIN: Final = EntitlementSet(
    principal_id="u_admin",
    grants=(
        Grant(capability=Capability(value="approve:grant"), scope=WHOLE),
        Grant(capability=Capability(value="read:scope"), scope=WHOLE),
        Grant(capability=Capability(value="read:grant"), scope=WHOLE),
        CONFIGURATION,
    ),
)
#: Reads both screens in web only.
WEB_READER: Final = EntitlementSet(
    principal_id="u_reader",
    grants=(
        Grant(capability=Capability(value="read:scope"), scope=Scope.department("web")),
        Grant(capability=Capability(value="read:grant"), scope=Scope.department("web")),
        CONFIGURATION,
    ),
)


def recorder() -> AuditRecorder:
    return AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash="0" * 32, trace_id="t", clock=lambda: LONG_AGO
    )


# ------------------------------------------------------------ the migration and the model


def test_the_triggers_write_the_subject_and_details_the_recorder_writes() -> None:
    """Delete this and the entries a deployed database keeps and the entries `AuditRecorder` writes
    can come apart with no server to notice: a trigger naming the team by its id, the lead by the
    appointer, or a membership under a team subject nobody filters on. Read off the executed module.
    """
    joined = recorder().organisation(
        principal_id="u_1", change=OrganisationChange.JOINED, team="web.design"
    )
    appointed = recorder().organisation(
        principal_id="u_1", change=OrganisationChange.APPOINTED, department="web"
    )
    migration = migration_module(MIGRATION)
    team = " ".join(migration.TEAM_MEMBERSHIP_TRIGGER_FUNCTION.split())
    lead = " ".join(migration.DEPARTMENT_LEAD_TRIGGER_FUNCTION.split())

    assert (joined.subject, joined.details) == (
        "principal:u_1",
        {"change": "joined", "team": "web.design"},
    )
    assert appointed.details == {"change": "appointed", "department": "web"}
    for body in (team, lead):
        assert "v_subject text := 'principal:' || NEW.principal_id;" in body
        assert "v_details := v_where || jsonb_build_object('change', v_changes[i]);" in body
        assert "v_seq, v_at, v_actors[i], 'organisation', v_subject, v_ent_hash," in body
    assert "(SELECT d.slug || '.' || t.slug FROM gate.team t" in team
    assert "v_changes := v_changes || 'joined'::text; v_actors := v_actors || NEW.added_by" in team
    assert "v_changes := v_changes || 'left'::text; v_actors := v_actors || NEW.ended_by" in team
    assert "(SELECT d.slug FROM gate.department d WHERE d.id = NEW.department_id)" in lead
    assert "'appointed'::text; v_actors := v_actors || NEW.appointed_by" in lead
    assert "'stood_down'::text; v_actors := v_actors || NEW.ended_by" in lead


def test_the_recorder_refuses_a_team_change_naming_a_department_and_the_reverse() -> None:
    """Delete this and an entry can say somebody left a department they were never a member of, or
    was appointed to lead a team, which no trigger writes and every reader would believe."""
    for change, where in (
        (OrganisationChange.JOINED, {"department": "web"}),
        (OrganisationChange.LEFT, {}),
        (OrganisationChange.APPOINTED, {"team": "web.design"}),
        (OrganisationChange.STOOD_DOWN, {"team": "web.design", "department": "web"}),
    ):
        try:
            recorder().organisation(
                principal_id="u_1",
                change=change,
                team=where.get("team", ""),
                department=where.get("department", ""),
            )
        except ValueError:
            continue
        raise AssertionError(f"{change} with {where} was recorded")


def test_the_migration_builds_both_tables_exactly_as_the_models_declare_them() -> None:
    """Compared as rendered DDL. Delete this and a model can lose the partial index that keeps one
    live lead per department, with the database built the old way and two leads possible."""
    emitted = squash(rendered("upgrade", MIGRATION))
    for qualified in ("gate.team_membership", "gate.department_lead"):
        mapped = metadata.tables[qualified]
        assert squash(str(CreateTable(mapped).compile(dialect=DIALECT))) in emitted
        for index in mapped.indexes:
            assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted


def test_the_application_may_place_and_end_a_placement_once_and_nothing_else() -> None:
    """Delete this and an UPDATE on who placed somebody, or a DELETE, can arrive with either table,
    or row-level security can be left off one, with every other test green."""
    emitted = squash(rendered("upgrade", MIGRATION))
    for table in ("team_membership", "department_lead"):
        assert f"ALTER TABLE gate.{table} ENABLE ROW LEVEL SECURITY" in emitted
        assert f"GRANT SELECT, INSERT ON gate.{table} TO brain_app" in emitted
        assert f"GRANT UPDATE (ended_at, ended_by) ON gate.{table} TO brain_app" in emitted
        assert f"DELETE ON gate.{table}" not in emitted
        assert (
            f"CREATE POLICY {table}_live ON gate.{table} FOR INSERT TO brain_app WITH CHECK "
            "(ended_at IS NULL AND ended_by IS NULL)"
        ) in emitted
        assert (
            f"CREATE POLICY {table}_ended_once ON gate.{table} FOR UPDATE TO brain_app USING "
            "(ended_at IS NULL) WITH CHECK (ended_at IS NOT NULL)"
        ) in emitted
    assert "bump_grants_version" not in emitted


def test_the_stored_organisation_is_the_records_the_routes_ask_for() -> None:
    """Delete this and the store can drift from the protocol the routes hold."""
    assert isinstance(StoredOrganisation(async_sessionmaker()), OrganisationRecords)


# ------------------------------------------------------------------------ the database


@contextmanager
def through_0062(database: str) -> Iterator[str]:
    """A database with `0062` applied, as `tests/unit/test_elevation_store.py` builds one."""
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


def seeded(url: str) -> None:
    """Web with a design team, finance, and four people: two in web, one in finance, one gone."""
    sql(url, "INSERT INTO gate.scope (slug, predicate) VALUES ('web', '{\"department\": \"web\"}')")
    sql(
        url,
        "INSERT INTO gate.scope (slug, predicate)"
        " VALUES ('finance', '{\"department\": \"finance\"}')",
    )
    for slug, name in (("web", "Web"), ("finance", "Finance")):
        sql(
            url,
            "INSERT INTO gate.department (company_id, slug, name, scope_slug)"
            " VALUES ('c_1', %s, %s, %s)",
            slug,
            name,
            slug,
        )
    sql(
        url,
        "INSERT INTO gate.team (department_id, slug, name)"
        " SELECT id, 'design', 'Design' FROM gate.department WHERE slug = 'web'",
    )
    for pid, department, disabled in (
        ("u_wei", "web", False),
        ("u_new", "web", False),
        ("u_grace", "finance", False),
        ("u_gone", "web", True),
    ):
        sql(
            url,
            "INSERT INTO auth.principal"
            " (id, kind, employment, display_name, primary_department, disabled_at)"
            " VALUES (%s, 'human', 'staff', %s, %s, %s)",
            pid,
            f"Person {pid}",
            department,
            LONG_AGO if disabled else None,
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


def placements(chain: list[AuditEntry]) -> list[AuditEntry]:
    """The entries about where somebody sits, which are filed under the person.

    Since `0086` the seeded scopes, departments and team are recorded too, under `department:` and
    `scope:` and as the database role that inserted them; these tests are about the placements.
    """
    return [one for one in chain if one.subject.startswith("principal:")]


def placing(reach: EntitlementSet, department: str = "web") -> Any:
    def may(person: Person) -> bool:
        return may_place(reach, department=department, person=member_of(person), now=LATER)

    return may


def ending(reach: EntitlementSet, department: str = "web") -> Any:
    def may(person: Person) -> bool:
        return may_organise(reach, department=department, person=member_of(person), now=LATER)

    return may


def appointing(reach: EntitlementSet, department: str = "web") -> Any:
    def may(person: Person, incumbent: Person | None) -> bool:
        if not may_appoint(reach, department=department, person=member_of(person), now=LATER):
            return False
        return incumbent is None or may_organise(
            reach, department=department, person=member_of(incumbent), now=LATER
        )

    return may


def test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page() -> None:
    """M27.7.4's writes, followed to the system, through the store and the route's own questions, as
    the role the application uses.

    Wei and Grace are placed in design; Wei is appointed lead and then replaced by New, which ends
    Wei's lead in the same transaction; the page then lists both members and New as lead for an
    administrator, and for a web reader lists Wei and New and not Grace, whose department they may
    not name. Wei is taken out of design and New stood down. Every change is an `organisation` entry
    by the administrator under the person's own subject, and the chain verifies. Delete this and
    any of it can be false in production while the stubbed tests stay green. **Skips without a
    server.**"""
    with through_0062("brain_organisation_writes") as url:
        seeded(url)

        async def walk() -> tuple[Any, Any, list[object]]:
            engine = app_engine(url)
            try:
                sessions = make_session_factory(engine)
                store = StoredOrganisation(sessions)
                common = {"actor": "u_admin", "ent_hash": "a" * 32, "trace_id": "trace-org"}
                done: list[object] = [
                    await store.place(
                        department="web",
                        team="design",
                        principal_id="u_wei",
                        may=placing(ADMIN),
                        **common,
                    ),
                    await store.place(
                        department="web",
                        team="design",
                        principal_id="u_grace",
                        may=placing(ADMIN),
                        **common,
                    ),
                    await store.appoint(
                        department="web", principal_id="u_wei", may=appointing(ADMIN), **common
                    ),
                    await store.appoint(
                        department="web", principal_id="u_new", may=appointing(ADMIN), **common
                    ),
                ]
                source = OrganisationSource(ConsoleReads(sessions))
                loaded = (await source.load(limit=100, now=LATER)).value
                pages = [
                    organisation(
                        loaded.departments,
                        loaded.teams,
                        loaded.members,
                        reader,
                        LATER,
                        memberships=loaded.memberships,
                        leads=loaded.leads,
                    )
                    for reader in (ADMIN, WEB_READER)
                ]
                done.append(
                    await store.unplace(
                        department="web",
                        team="design",
                        principal_id="u_wei",
                        may=ending(ADMIN),
                        **common,
                    )
                )
                done.append(await store.stand_down(department="web", may=ending(ADMIN), **common))
                return pages[0], pages[1], done
            finally:
                await engine.dispose()

        admin_page, web_page, done = run(walk)
        memberships = sql(
            url,
            "SELECT principal_id, added_by, ended_by FROM gate.team_membership"
            " ORDER BY principal_id",
        )
        leads = sql(
            url,
            "SELECT principal_id, appointed_by, ended_by FROM gate.department_lead"
            " ORDER BY appointed_at",
        )
        chain = entries(url)

    assert all(one is not None for one in done)
    web = next(line for line in admin_page.departments if line.slug == "web")
    assert [one.principal_id for one in web.teams[0].members] == ["u_grace", "u_wei"]
    assert web.lead is not None and web.lead.principal_id == "u_new"
    [web_only] = web_page.departments
    assert [one.principal_id for one in web_only.teams[0].members] == ["u_wei"]
    assert web_only.lead is not None and web_only.lead.principal_id == "u_new"
    assert memberships == [("u_grace", "u_admin", None), ("u_wei", "u_admin", "u_admin")]
    assert leads == [("u_wei", "u_admin", "u_admin"), ("u_new", "u_admin", "u_admin")]
    assert [(one.subject, one.actor_id, one.details) for one in placements(chain)] == [
        ("principal:u_wei", "u_admin", {"change": "joined", "team": "web.design"}),
        ("principal:u_grace", "u_admin", {"change": "joined", "team": "web.design"}),
        ("principal:u_wei", "u_admin", {"change": "appointed", "department": "web"}),
        ("principal:u_wei", "u_admin", {"change": "stood_down", "department": "web"}),
        ("principal:u_new", "u_admin", {"change": "appointed", "department": "web"}),
        ("principal:u_wei", "u_admin", {"change": "left", "team": "web.design"}),
        ("principal:u_new", "u_admin", {"change": "stood_down", "department": "web"}),
    ]
    assert {one.action.value for one in chain} == {"organisation"}
    assert AuditChain(chain).verify() is None


def test_every_refused_placement_writes_nothing() -> None:
    """The refusals, against the real store and the real questions. Delete this and somebody
    appointing themselves, a disabled person placed, a web-only organiser placing somebody from
    finance, a second live membership of one team, or a team nobody registered can each leave a row
    or an entry. **Skips without a server.**"""
    web_organiser = EntitlementSet(
        principal_id="u_wei",
        grants=(
            Grant(capability=Capability(value="approve:grant"), scope=Scope.department("web")),
        ),
    )
    with through_0062("brain_organisation_refused") as url:
        seeded(url)

        async def walk() -> list[object]:
            engine = app_engine(url)
            try:
                store = StoredOrganisation(make_session_factory(engine))
                common = {"actor": "u_wei", "ent_hash": "a" * 32, "trace_id": "trace"}
                first = await store.place(
                    department="web",
                    team="design",
                    principal_id="u_new",
                    may=placing(web_organiser),
                    **common,
                )
                assert first is not None
                return [
                    await store.appoint(
                        department="web",
                        principal_id="u_wei",
                        may=appointing(web_organiser),
                        **common,
                    ),
                    await store.place(
                        department="web",
                        team="design",
                        principal_id="u_gone",
                        may=placing(web_organiser),
                        **common,
                    ),
                    await store.place(
                        department="web",
                        team="design",
                        principal_id="u_grace",
                        may=placing(web_organiser),
                        **common,
                    ),
                    await store.place(
                        department="web",
                        team="design",
                        principal_id="u_new",
                        may=placing(web_organiser),
                        **common,
                    ),
                    await store.place(
                        department="web",
                        team="nowhere",
                        principal_id="u_new",
                        may=placing(web_organiser),
                        **common,
                    ),
                    await store.stand_down(department="web", may=ending(web_organiser), **common),
                ]
            finally:
                await engine.dispose()

        refused = run(walk)
        [(rows,)] = sql(url, "SELECT count(*) FROM gate.team_membership")
        [(lead_rows,)] = sql(url, "SELECT count(*) FROM gate.department_lead")
        chain = entries(url)

    assert refused == [None, None, None, None, None, None]
    assert (rows, lead_rows) == (1, 0)
    assert len(placements(chain)) == 1


def test_the_sync_places_where_the_source_says_and_ends_only_what_it_made() -> None:
    """The directory sync's half of M27.7.4, through the plan and the store. A trusted, complete
    source places Wei in design and appoints New; a hand-made placement of Grace is there already.
    A second run whose roster no longer names Wei's team or New's lead ends both, as the sync's
    actor, and leaves Grace's alone. Delete this and the sync can take away what a person placed, or
    write rows nothing records under the source that asserted them. **Skips without a server.**"""
    first = Roster(
        source="lark",
        complete=True,
        asserts=frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT}),
        people=(
            StaffRecord("wei@example.test", "Wei", department="web", teams=("design",)),
            StaffRecord("new@example.test", "New", department="web", leads=True),
        ),
    )
    second = Roster(
        source="lark",
        complete=True,
        asserts=first.asserts,
        people=(
            StaffRecord("wei@example.test", "Wei", department="web"),
            StaffRecord("new@example.test", "New", department="web"),
        ),
    )
    known = {"wei@example.test": "u_wei", "new@example.test": "u_new"}
    with through_0062("brain_organisation_sync") as url:
        seeded(url)

        async def walk() -> None:
            engine = app_engine(url)
            try:
                store = StoredOrganisation(make_session_factory(engine))
                await store.place(
                    department="web",
                    team="design",
                    principal_id="u_grace",
                    actor="u_admin",
                    ent_hash="a" * 32,
                    trace_id="t",
                    may=lambda _: True,
                )
                for roster, last in ((first, None), (second, LONG_AGO)):
                    memberships, leads, teams, departments = await store.sync_holdings()
                    plan = organisation_plan(
                        roster,
                        known=known,
                        teams=teams,
                        departments=departments,
                        memberships=memberships,
                        leads=leads,
                        last_applied=last,
                    )
                    await store.apply_sync(plan, trace_id="trace-sync")
            finally:
                await engine.dispose()

        run(walk)
        memberships = sql(
            url,
            "SELECT principal_id, added_by, ended_by FROM gate.team_membership"
            " ORDER BY principal_id",
        )
        leads = sql(url, "SELECT principal_id, appointed_by, ended_by FROM gate.department_lead")
        actors = [one.actor_id for one in placements(entries(url))]

    sync = f"{SYNC_ACTOR_PREFIX}lark"
    assert memberships == [("u_grace", "u_admin", None), ("u_wei", sync, sync)]
    assert leads == [("u_new", sync, sync)]
    assert actors == ["u_admin", sync, sync, sync, sync]


def test_a_member_is_the_person_the_write_read() -> None:
    """Delete this and `member_of` can drop the disablement or the department on the way from the
    store to the question, and a disabled person or one in another department is placed."""
    person = Person(principal_id="u_1", display_name="One", department="finance", disabled=True)

    assert member_of(person) == Member(
        principal_id="u_1", display_name="One", department="finance", disabled=True
    )
