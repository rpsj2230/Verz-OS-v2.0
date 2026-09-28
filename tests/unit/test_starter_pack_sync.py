"""Every person the staff sync brings in holds the Starter pack for their own department.

Needs Rupash item 105, decided on 2026-09-28. Without a server: the plan
`brain.identity.starter_pack_sync.starter_plan` makes of real rosters, for a joiner, a mover, a
leaver, somebody an administrator gave a pack by hand, a department nobody registered, a source
not trusted with departments and a pack row wider than the joiner's; the statements
`brain.ops.starter_pack_store` turns a plan into; and the scheduled run calling it after the roster
and the heads without ever undoing either.

Then against PostgreSQL, which is the proof: the scheduled run reads a Lark directory, gives the
engineering person and the finance person each their own department's pack, the ledger records
both under the roster, and the one resolver's reach finds an engineering document for the first
and exactly nothing for the second. A second night moves one person and loses another, and each
one's reach follows with no reindex. CI sets `DATABASE_URL`; without it those tests skip.

Task ids: M26.1.2, M26.1.3, M26.2.6
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from brain.connectors.staff_directories import Answer, Outbound
from brain.core.department import department_scope
from brain.core.entitlement import EntitlementSet
from brain.core.scope import Scope
from brain.gate.context import Channel
from brain.gate.entitlement_store import StoredEntitlements
from brain.identity.lifecycle import STARTER_PACK
from brain.identity.staff_roster import RunOutcome, digest_of
from brain.identity.staff_source import DEFAULT_TRUST, Roster
from brain.identity.staff_sync import ROSTER_PREFIX
from brain.identity.starter_pack_sync import (
    A_DEPARTMENT_NOBODY_REGISTERED_GIVES_NOTHING,
    HeldStarter,
    StarterPlan,
    department_of,
    registered_by_name,
    starter_plan,
)
from brain.identity.teams import PrincipalSubject
from brain.ops import starter_pack_store
from brain.ops.starter_pack_store import retire, writes_for
from brain.session import make_session_factory
from brain.tables.organisation import SYNC_ACTOR_PREFIX
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_staff_sync import person

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Far outside any plausible wall clock, on `tests/unit/test_scope_and_capability.py`'s rule.
READ_AT = datetime(2999, 1, 1, 3, 0, tzinfo=UTC)
SOURCE = "lark"
GRANTOR = f"{ROSTER_PREFIX}{SOURCE}"
DEPARTMENTS = {"engineering": "Engineering", "finance": "Finance", "web": "Web Design"}
BOUND = {
    "ada@example.com": "p_ada",
    "grace@example.com": "p_grace",
    "katherine@example.com": "p_katherine",
}
STANDING = frozenset(BOUND.values())
DECLARED = tuple(one.value for one in STARTER_PACK.capabilities)


def roster(*people: Any, source: str = SOURCE) -> Roster:
    return Roster(source=source, people=people, complete=True, asserts=DEFAULT_TRUST[source])


NIGHT_ONE = roster(
    person("ada@example.com", department="Engineering"),
    person("grace@example.com", department="engineering", active=False),
    person("katherine@example.com", department=" finance "),
)


def plan_for(
    source: Roster,
    *,
    held: tuple[HeldStarter, ...] = (),
    leavers: frozenset[str] = frozenset(),
    standing: frozenset[str] = STANDING,
    pack: tuple[str, ...] | None = DECLARED,
    departments: Mapping[str, str] = DEPARTMENTS,
    known: Mapping[str, str] = BOUND,
) -> StarterPlan:
    return starter_plan(
        source,
        known=known,
        standing=standing,
        departments=departments,
        held=held,
        leavers=leavers,
        pack=pack,
        read_at=READ_AT,
    )


def given(plan: StarterPlan) -> dict[str, str | None]:
    """Who is given which department's pack."""
    return {
        str(one.subject.principal_id): department_of(one.scope)
        for one in plan.to_assign
        if isinstance(one.subject, PrincipalSubject)
    }


def a_held(principal: str, department: str, *, by: str = GRANTOR) -> HeldStarter:
    return HeldStarter(principal_id=principal, scope=department_scope(department), granted_by=by)


# ------------------------------------------------------------------------ the plan
def test_a_synced_person_is_given_the_starter_pack_over_their_own_department_and_no_other() -> None:
    """**Item 105's sentence.** Ada is placed in Engineering and Katherine in finance: each is
    given the Starter pack scoped to exactly that registered department, granted by the roster,
    with no lapse. Grace has left and is given nothing. Delete this and the sync can give a pack
    over the wrong department, over everything, or to a leaver, with every other test green."""
    plan = plan_for(NIGHT_ONE)

    assert plan.safe_to_apply and not plan.to_retire
    assert given(plan) == {"p_ada": "engineering", "p_katherine": "finance"}
    for one in plan.to_assign:
        assert one.pack_slug == STARTER_PACK.slug
        assert one.scope in (department_scope("engineering"), department_scope("finance"))
        assert one.granted_by == GRANTOR
        assert one.not_after is None


def test_the_granter_is_the_organisation_syncs_own_actor_so_the_ledger_accepts_it() -> None:
    """Every assignment names `roster.<source>`, which is the organisation sync's actor prefix
    and a string the ledger's actor grammar admits. Delete this and a respelling to
    `roster:<source>` rolls every night's packs back on a real database, as it did for the
    heads' audit grants."""
    (first, *_) = plan_for(NIGHT_ONE).to_assign
    assert first.granted_by.startswith(SYNC_ACTOR_PREFIX)
    assert ":" not in first.granted_by


def test_a_department_is_matched_to_a_registered_slug_or_name_ignoring_case_and_spacing() -> None:
    """Lark sends a department's name and the install files documents under its slug. `Web
    Design` is the web department by name, `ENGINEERING` by slug. Delete this and a directory
    whose names are capitalised gives nobody anything."""
    source = roster(
        person("ada@example.com", department="  web   design "),
        person("katherine@example.com", department="ENGINEERING"),
    )
    assert given(plan_for(source)) == {"p_ada": "web", "p_katherine": "engineering"}


def test_a_spelling_two_departments_answer_to_places_nobody() -> None:
    """A department slugged `ops` and another named `Ops` both answer to `ops`, so neither is
    chosen. Delete this and which department bounds somebody's reach is whichever came last."""
    assert registered_by_name({"ops": "Operations", "ops-uk": "Ops"}) == {
        "operations": "ops",
        "ops-uk": "ops-uk",
    }


def test_a_department_nobody_registered_gives_nothing_and_is_reported() -> None:
    """A person placed in `Legal`, which the install has not registered, is given nothing and
    the name is reported with the reason. Delete this and the sync writes a pack over a slug no
    document is filed under, which reads as reach given and reaches nothing."""
    plan = plan_for(roster(person("ada@example.com", department="Legal")))

    assert plan.to_assign == ()
    assert plan.unregistered == ("Legal",)
    assert A_DEPARTMENT_NOBODY_REGISTERED_GIVES_NOTHING in plan.withheld


def test_a_source_not_trusted_with_departments_gives_nobody_anything() -> None:
    """A Google Sheet asserts existence alone, so it cannot say which department's pack anybody
    holds: the plan is refused and empty. Delete this and a sheet anybody can edit hands out
    department reach."""
    plan = plan_for(
        roster(person("ada@example.com", department="Engineering"), source="google_sheet")
    )

    assert not plan.safe_to_apply
    assert plan.changes_nothing


def test_a_live_pack_wider_than_the_joiners_is_refused_and_a_narrower_one_is_given() -> None:
    """**Nobody grants what they do not hold.** A Starter row edited to carry `admin:grant` is
    refused, because the sync holds nothing to grant the difference; one narrowed to the plain
    knowledge read is given. Delete this and an edited pack becomes a nightly escalation for
    every synced person."""
    wider = plan_for(NIGHT_ONE, pack=(*DECLARED, "admin:grant"))
    narrower = plan_for(NIGHT_ONE, pack=DECLARED[:1])

    assert not wider.safe_to_apply and wider.to_assign == ()
    assert narrower.safe_to_apply and given(narrower) == {
        "p_ada": "engineering",
        "p_katherine": "finance",
    }


def test_no_live_starter_pack_gives_nothing() -> None:
    """An install never furnished, or whose administrator retired the pack, gives nothing and
    says so. Delete this and the store inserts against a pack id it does not have."""
    plan = plan_for(NIGHT_ONE, pack=None)
    assert not plan.safe_to_apply
    assert plan.to_assign == ()


def test_a_mover_has_the_pack_the_sync_gave_retired_and_the_new_departments_given() -> None:
    """**The mover.** Katherine held finance's pack from the sync and is now in engineering: the
    finance one is retired and engineering's given, in that order. Delete this and a mover
    keeps reading the department they left, or is refused by the one-live-pack index."""
    source = roster(person("katherine@example.com", department="Engineering"))
    old = a_held("p_katherine", "finance")
    plan = plan_for(source, held=(old,))

    assert plan.to_retire == (old,)
    assert given(plan) == {"p_katherine": "engineering"}


def test_an_unchanged_person_is_neither_retired_nor_given_again() -> None:
    """Ada already holds engineering's pack from the sync: the plan changes nothing. Delete this
    and every night writes a revocation and a grant into the ledger for everybody."""
    plan = plan_for(
        roster(person("ada@example.com", department="engineering")),
        held=(a_held("p_ada", "engineering"),),
    )
    assert plan.changes_nothing


def test_a_pack_an_administrator_assigned_is_never_retired_or_replaced() -> None:
    """Katherine holds a Starter pack an administrator assigned over finance, and the list now
    says engineering: nothing happens to it, and nothing is added over it. Delete this and the
    sync overwrites a decision a person took on Govern > Roles."""
    by_hand = a_held("p_katherine", "finance", by="u_admin")
    plan = plan_for(
        roster(person("katherine@example.com", department="engineering")), held=(by_hand,)
    )

    assert plan.changes_nothing
    assert plan.withheld


def test_a_leaver_loses_the_pack_the_sync_gave_and_keeps_one_a_person_gave() -> None:
    """**The leaver.** Ada is marked as having left and is not on this list: the pack the sync
    gave her is retired. Grace also left and holds one an administrator gave: it stays. Delete
    this and a leaver goes on holding their department's reach, or the sync revokes a person's
    decision."""
    adas, graces = a_held("p_ada", "engineering"), a_held("p_grace", "web", by="u_admin")
    plan = plan_for(
        roster(person("katherine@example.com", department="finance")),
        held=(adas, graces, a_held("p_katherine", "finance")),
        leavers=frozenset({"p_ada", "p_grace"}),
    )
    assert plan.to_retire == (adas,)
    assert plan.to_assign == ()


def test_absence_and_a_blank_department_retire_nothing() -> None:
    """Ada is missing from the list and Katherine is listed with no department: both keep the
    pack the sync gave. Delete this and a half-answered export or a failed department lookup
    takes everybody's knowledge away."""
    held = (a_held("p_ada", "engineering"), a_held("p_katherine", "finance"))
    plan = plan_for(roster(person("katherine@example.com", department="")), held=held)
    assert plan.changes_nothing


def test_a_mover_into_a_department_nobody_registered_loses_the_old_one() -> None:
    """The list says Katherine is in `Legal` now, positively: the finance pack the sync gave is
    retired even though Legal's cannot be given. Delete this and somebody who left finance keeps
    reading it until an administrator registers where they went."""
    old = a_held("p_katherine", "finance")
    plan = plan_for(roster(person("katherine@example.com", department="Legal")), held=(old,))
    assert plan.to_retire == (old,)
    assert plan.to_assign == ()


def test_a_partner_or_a_service_and_somebody_nobody_bound_are_given_nothing() -> None:
    """Only a person who may hold a standing entitlement is given a pack, and only once an email
    binding proves who they are. Delete this and a partner holds a row that confers nothing and
    reads as though it did, or an address alone earns reach."""
    source = roster(
        person("ada@example.com", department="engineering"),
        person("stranger@example.com", department="engineering"),
    )
    assert plan_for(source, standing=frozenset()).to_assign == ()
    assert given(plan_for(source)) == {"p_ada": "engineering"}


def test_one_person_the_list_places_in_two_departments_is_given_neither() -> None:
    """Ada's two bound addresses are listed in engineering and in finance. Delete this and her
    reach is decided by whichever row sorted first."""
    source = roster(
        person("ada@example.com", department="engineering"),
        person("ada.lovelace@example.com", department="finance"),
    )
    plan = plan_for(source, known={**BOUND, "ada.lovelace@example.com": "p_ada"})
    assert plan.to_assign == ()
    assert plan.withheld


def test_department_of_reads_exactly_one_department_and_nothing_wider() -> None:
    """A mover is recognised by comparing a held scope with a department's. A scope with a second
    clause is not a department's, and neither is the unrestricted scope. Delete this and a row a
    person wrote over a narrower scope reads as the sync's own department."""
    assert department_of(department_scope("finance")) == "finance"
    assert department_of(Scope.unrestricted()) is None
    narrower = Scope.model_validate(
        {
            "clauses": [
                {"field": "department", "op": "eq", "value": "finance"},
                {"field": "owner_id", "op": "eq", "value": "p_ada"},
            ]
        }
    )
    assert department_of(narrower) is None


# ------------------------------------------------------------------------ the statements
def sql_of(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=DIALECT)).split())


PACK_ID = uuid.UUID("00000000-0000-4000-8000-000000000105")


def test_a_plan_becomes_retirements_first_then_assignments_and_a_refusal_becomes_nothing() -> None:
    """The one-live-pack index refuses a second live Starter row, so a mover's old row goes
    first. Delete this and every mover's night fails at the insert."""
    source = roster(person("katherine@example.com", department="engineering"))
    plan = plan_for(source, held=(a_held("p_katherine", "finance"),))
    statements = [sql_of(one) for one in writes_for(plan, PACK_ID)]

    assert [one.split()[0] for one in statements] == ["UPDATE", "INSERT"]
    assert writes_for(plan_for(source, pack=None), PACK_ID) == []


def test_a_retirement_names_the_granter_so_a_persons_row_is_never_the_one_ended() -> None:
    """The WHERE clause carries the live row, the pack and the roster's granter. Delete this and
    a row an administrator wrote between the read and the write is the one retired."""
    rendered = sql_of(retire(a_held("p_katherine", "finance"), PACK_ID))
    assert "capability_pack_assignment.deleted_at IS NULL" in rendered
    assert "capability_pack_assignment.granted_by = " in rendered
    assert "capability_pack_assignment.granted_by LIKE " in rendered
    assert "deleted_at=statement_timestamp()" in rendered


# ------------------------------------------------------------------------ the scheduled run
def test_the_scheduled_run_gives_the_packs_after_the_heads_and_survives_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run applies the roster, rewrites the heads, then gives the packs, each in its own
    transaction; a failure giving packs is logged and the run still reports the roster applied.
    Delete this and the packs can stop being given, or their failure can undo the staff list."""
    from brain.ops import staff_sync_run
    from tests.unit.test_staff_sync_run import APP_ID, APP_SECRET, LARK_ENV, Keys, Lease
    from tests.unit.test_staff_sync_run import run as run_the_sync

    order: list[str] = []

    async def read_members(session: object, source: str) -> tuple[()]:
        return ()

    async def read_last_applied(session: object, source: str) -> None:
        return None

    async def write_application(session: object, app: object, record: object) -> None:
        order.append("roster")

    async def heads(session: object, source: Roster, *, read_at: datetime) -> tuple[()]:
        order.append("heads")
        return ()

    async def failing(session: object, source: Roster, *, read_at: datetime) -> StarterPlan:
        order.append("packs")
        raise RuntimeError("a unique index said no")

    monkeypatch.setattr(staff_sync_run, "read_members", read_members)
    monkeypatch.setattr(staff_sync_run, "read_last_applied", read_last_applied)
    monkeypatch.setattr(staff_sync_run, "write_application", write_application)
    monkeypatch.setattr(staff_sync_run, "run_row", lambda record: ("run", record))
    monkeypatch.setattr(staff_sync_run, "rewrite_head_audit_reach", heads)
    monkeypatch.setattr(staff_sync_run, "grant_starter_packs", failing)

    ran, _ = run_the_sync(env=LARK_ENV, keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")))
    assert order == ["roster", "heads", "packs"]
    assert ran.outcome is RunOutcome.APPLIED


# ------------------------------------------------------------------------ against PostgreSQL
ADMINISTRATOR = "u_knowledge_administrator"
STAFF = {**BOUND, "priya@example.com": "p_priya"}


@contextmanager
def a_company(database: str) -> Iterator[str]:
    """Every migration to head, engineering and finance registered, the Starter pack furnished,
    four people bound by email, and an engineering document an administrator uploaded. Skips
    where the server has no pgvector, which CI has."""
    from brain.ops.starter import PACKS
    from brain.ops.starter_store import furnish_packs
    from tests.fixtures.retirable import has_pgvector, retirable
    from tests.unit.test_knowledge_upload_db import an_administrator

    with retirable(database) as url:
        if not has_pgvector(url):
            pytest.skip("the pack, identity and knowledge tables need the whole chain")
        for slug in ("engineering", "finance"):
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
        for address, pid in STAFF.items():
            sql(
                url,
                "INSERT INTO auth.principal (id, kind, employment, display_name)"
                " VALUES (%s, 'human', 'staff', %s)",
                pid,
                f"Person {pid}",
            )
            sql(
                url,
                "INSERT INTO auth.principal_identity"
                " (channel, identity_hash, principal_id, bound_at) VALUES (%s, %s, %s, now())",
                Channel.EMAIL.value,
                digest_of(address),
                pid,
            )
        furnished(url, furnish_packs(PACKS))
        an_administrator(url)
        uploaded_to(url, "engineering")
        yield url


def uploaded_to(url: str, department: str) -> None:
    """The upload test's markdown file, placed in this department by the administrator."""
    from brain.knowledge.ingest import MediaType, admit_upload
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.uploads import ReadUpload, ReceivedUpload, read_for_text_path
    from brain.knowledge.visibility import KnowledgeVisibility
    from tests.unit.test_knowledge_upload_db import MARKDOWN, stored

    upload = admit_upload(
        filename="Site handover.md", declared_type=MediaType.MARKDOWN.value, content=MARKDOWN
    )
    read = read_for_text_path(
        ReceivedUpload(upload=upload, body=MARKDOWN),
        kind=KnowledgeKind.SOP,
        placement=KnowledgeVisibility.of_department(department, owner_id=ADMINISTRATOR),
        owner_id=ADMINISTRATOR,
    )
    assert isinstance(read, ReadUpload)
    stored(url, read)


def app_role(url: str) -> Any:
    from tests.unit.test_automation_owner_store import app_engine

    return app_engine(url)


def furnished(url: str, statement: Any) -> None:
    """The install's own furnishing statement, as the application role runs it at start."""

    async def go() -> None:
        engine = app_role(url)
        try:
            async with make_session_factory(engine)() as session, session.begin():
                await session.execute(statement)
        finally:
            await engine.dispose()

    run(go)


def reach_of(url: str, principal_id: str) -> EntitlementSet:
    """This person's reach now, from the one resolver, as the application role."""

    async def go() -> EntitlementSet:
        engine = app_role(url)
        try:
            return await StoredEntitlements(make_session_factory(engine)).load(
                principal_id, datetime.now(tz=UTC)
            )
        finally:
            await engine.dispose()

    return run(go)


def found(url: str, principal_id: str) -> tuple[Any, ...]:
    """What a text search for the document's word hands this person, under their real reach."""
    from tests.unit.test_knowledge_upload_db import searched

    return searched(url, reach_of(url, principal_id)).records


def searched_by_nobody(url: str) -> tuple[Any, ...]:
    from tests.unit.test_knowledge_upload_db import departmental, searched

    return searched(url, departmental("p_nobody", "nowhere")).records


def sync_as_the_application(url: str, *, at: datetime, fetch: Any) -> Any:
    """The scheduled run itself, every transaction as the application role, so every policy on
    the staff, pack and ledger tables is the one a real install applies."""
    from brain.ops.staff_sync_run import sync_staff_on
    from tests.unit.test_staff_sync_run import APP_ID, APP_SECRET, LARK_ENV, Keys, Lease

    async def go() -> Any:
        engine = app_role(url)
        try:
            return await sync_staff_on(
                sessions=make_session_factory(engine),
                now=at,
                env=LARK_ENV,
                keys=Keys(Lease(f"{APP_ID}:{APP_SECRET}")),
                fetch=fetch,
                clock=lambda: at + timedelta(seconds=5),
            )
        finally:
            await engine.dispose()

    return run(go)


def live_packs(url: str) -> dict[str, tuple[str | None, str]]:
    """Each person's live Starter assignment: its department and who gave it."""
    return {
        str(pid): (department_of(Scope.model_validate(scope)), str(by))
        for pid, scope, by in sql(
            url,
            "SELECT a.principal_id, a.scope, a.granted_by FROM gate.capability_pack_assignment a"
            " JOIN gate.capability_pack p ON p.id = a.pack_id"
            " WHERE p.name = %s AND a.deleted_at IS NULL",
            STARTER_PACK.slug,
        )
    }


def recorded_by_the_sync(url: str) -> list[tuple[str, dict[str, Any]]]:
    return [
        (str(action), dict(details))
        for action, details in sql(
            url,
            "SELECT action, details FROM obs.audit_entry WHERE actor_id = %s"
            " AND details ->> 'source' = 'capability_pack_assignment' ORDER BY seq",
            GRANTOR,
        )
    ]


@dataclass
class KatherineMoves:
    """The second night: Katherine is in engineering now, and Ada is gone from a complete list."""

    sent: list[Outbound]

    async def __call__(self, outbound: Outbound) -> Answer:
        from tests.fixtures.roster_payloads import LARK_USERS_PAGE_TWO
        from tests.unit.test_staff_directories import lark_pages
        from tests.unit.test_staff_sync_run import TENANT_TOKEN

        self.sent.append(outbound)
        if outbound.url.endswith("/auth/v3/tenant_access_token/internal"):
            return Answer(200, {"code": 0, "tenant_access_token": TENANT_TOKEN})
        katherine = {
            **LARK_USERS_PAGE_TWO["data"]["items"][0],
            "department_ids": ["od-engineering"],
        }
        moved = {
            **LARK_USERS_PAGE_TWO,
            "data": {**LARK_USERS_PAGE_TWO["data"], "items": [katherine]},
        }
        empty = {"code": 0, "data": {"has_more": False, "items": []}}
        pages = {
            **lark_pages(),
            "department_id=0&": moved,
            "department_id=od-engineering&": moved,
            "department_id=od-finance&": empty,
        }
        for fragment, page in pages.items():
            if fragment in outbound.url:
                return Answer(200, page)
        return Answer(404, {"msg": f"no stand-in for {outbound.url}"})


@pytest.mark.needs_db
def test_through_the_database_a_synced_person_reads_their_departments_document_only() -> None:
    """**Item 105 on the tables, through the scheduled run.** The run reads a Lark directory as
    the application role: Ada is in engineering, Katherine in finance and Grace has resigned.
    Ada and Katherine each hold their own department's Starter pack, given by the roster, and
    the ledger has one grant for each naming the pack under that actor. Ada's reach from the one
    resolver finds the engineering document; Katherine's finds exactly what a search nobody's
    document matches finds. **Skips without a server.**

    Delete this and the packs can be refused by a trigger, a policy or a check on every install,
    or given over the wrong department, with every test over a stand-in green."""
    from tests.unit.test_staff_sync_run import Directory

    with a_company("brain_starter_pack_reads") as url:
        ran = sync_as_the_application(url, at=READ_AT, fetch=Directory())
        packs = live_packs(url)
        entries = recorded_by_the_sync(url)
        adas, katherines, nobodys = (
            found(url, "p_ada"),
            found(url, "p_katherine"),
            searched_by_nobody(url),
        )

    assert ran.outcome is RunOutcome.APPLIED
    assert packs == {"p_ada": ("engineering", GRANTOR), "p_katherine": ("finance", GRANTOR)}
    assert [(action, details["pack"]) for action, details in entries] == [
        ("grant", STARTER_PACK.slug),
        ("grant", STARTER_PACK.slug),
    ]
    assert adas and {one.department for one in adas} == {"engineering"}
    assert any("TEALCHECK" in one.document for one in adas)
    assert katherines == nobodys == ()


@pytest.mark.needs_db
def test_through_the_database_a_mover_and_a_leaver_change_reach_with_no_reindex() -> None:
    """**The second night.** Katherine has moved to engineering and Ada is gone from a complete
    list. The run marks Ada as having left and retires her pack, retires Katherine's finance
    pack and gives her engineering's, and Priya's pack, which an administrator assigned, is
    untouched. The document was never touched: Katherine now finds it and Ada finds nothing.
    **Skips without a server.**

    Delete this and a mover keeps the department they left, a leaver keeps reading, or the sync
    retires a pack a person assigned, each visible only on an install."""
    from tests.unit.test_staff_sync_run import Directory

    with a_company("brain_starter_pack_moves") as url:
        sql(
            url,
            "INSERT INTO gate.capability_pack_assignment"
            " (principal_id, pack_id, scope, granted_by, reason)"
            " SELECT 'p_priya', id, %s, 'u_admin', 'assigned by hand' FROM gate.capability_pack"
            " WHERE name = %s",
            json.dumps(department_scope("finance").model_dump(mode="json")),
            STARTER_PACK.slug,
        )
        sync_as_the_application(url, at=READ_AT, fetch=Directory())
        second = sync_as_the_application(
            url, at=READ_AT + timedelta(days=1), fetch=KatherineMoves([])
        )
        packs = live_packs(url)
        entries = recorded_by_the_sync(url)
        adas, katherines = found(url, "p_ada"), found(url, "p_katherine")

    assert second.outcome is RunOutcome.APPLIED
    assert packs == {
        "p_katherine": ("engineering", GRANTOR),
        "p_priya": ("finance", "u_admin"),
    }
    assert [action for action, _ in entries] == ["grant", "grant", "revoke", "revoke", "grant"]
    assert katherines and {one.department for one in katherines} == {"engineering"}
    assert adas == ()


def test_the_store_reads_the_starter_pack_by_the_joiners_slug() -> None:
    """The row the store looks up is the one `starter_store` furnishes, by name. Delete this and
    a rename on either side leaves the sync finding no pack and giving nothing, on every
    install, with a log line as the only trace."""
    rendered = starter_pack_store.the_starter_pack().compile(dialect=DIALECT)
    assert rendered.params["name_1"] == STARTER_PACK.slug == "starter"
