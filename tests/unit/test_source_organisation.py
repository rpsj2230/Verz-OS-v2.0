"""The departments a staff source names, founded on a person's word, and the sync's placements.

`brain.ops.source_organisation` reads the roster's department names and founds the confirmed ones
through the Departments screen's own write, and applies the organisation plan for the team
memberships and leads a source names. The decisions are `brain.identity.organisation_sync`'s and are
tested there without a database; these drive the reads and writes against PostgreSQL built to head
through the migrations, so the triggers that put a founding on the ledger are the shipped ones.
Skipped where the server has no pgvector, because the chain to head needs it, and always run in CI.

Task ids: M27.7.4, M1.6.12
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.audit.ledger import TRACE_ID
from brain.console.organisation import founded
from brain.gate.context import Channel
from brain.gate.ingress import identity_hash
from brain.identity.organisation_store import Attribution, StoredOrganisation
from brain.identity.organisation_sync import sync_trace
from brain.identity.staff_source import Asserts, Roster, StaffRecord
from brain.ops.source_organisation import apply_organisation, found_named, named_departments
from brain.session import make_session_factory
from brain.tables.organisation import SYNC_ACTOR_PREFIX
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import database_url, run, sql
from tests.unit.test_automation_owner_store import app_engine

#: Far outside any plausible wall clock, on `tests/unit/test_scope_and_capability.py`'s rule.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
BY = Attribution(actor="u_admin", ent_hash="a" * 32, trace_id="trace-founding")


@pytest.fixture
def url() -> Iterator[str]:
    if database_url() is None:
        pytest.skip("DATABASE_URL is unset, so there is no server to ask; CI always sets it")
    with retirable("brain_test_source_organisation") as scratch:
        if not has_pgvector(scratch):
            pytest.skip("the chain to head needs pgvector, which CI's server has")
        yield scratch


def through[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = app_engine(url)
        try:
            return await work(make_session_factory(engine))
        finally:
            await engine.dispose()

    return run(go)


def listed(url: str, source: str, address: str, department: str, *, left: bool = False) -> None:
    """One roster row, as a run writes it: the address's digest, never the address."""
    sql(
        url,
        "INSERT INTO auth.staff_member (source, address_hash, display_name, department,"
        " first_listed_at, last_listed_at, left_at, left_because)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        source,
        identity_hash(Channel.EMAIL, address),
        address.split("@")[0],
        department,
        LONG_AGO,
        LONG_AGO,
        LONG_AGO if left else None,
        "source_says_left" if left else None,
    )


def test_a_source_s_departments_are_offered_founded_once_as_the_person_and_put_on_the_ledger(
    url: str,
) -> None:
    """The names the chosen source's live rows carry, less the ones a registered department
    answers to, are offered; the confirmed one is founded with its scope through the founding
    write, under the person who pressed; a second read offers it no more, and a leaver's
    department and another source's are never offered. Delete this and the offer or the founding
    could read or write a column nothing else does, with every stand-in test green."""
    for address, department in (
        ("ada@example.test", "Web Development"),
        ("grace@example.test", "web  development"),
        ("kay@example.test", "Finance"),
        ("wei@example.test", "Design"),
    ):
        listed(url, "lark", address, department)
    listed(url, "lark", "gone@example.test", "Old Team", left=True)
    listed(url, "google_workspace", "elsewhere@example.test", "Elsewhere")

    async def walk(sessions: async_sessionmaker[AsyncSession]) -> tuple[Any, ...]:
        store = StoredOrganisation(sessions)
        department, scope = founded("finance", "Finance")
        await store.found_department(department=department, scope=scope, by=BY)
        before = await named_departments(sessions, "lark")
        done = await found_named(store, before, confirmed={"web_development"}, by=BY)
        after = await named_departments(sessions, "lark")
        return before, done, after

    before, done, after = through(url, walk)

    assert [(one.name, one.slug) for one in before.to_found] == [
        ("Design", "design"),
        ("Web Development", "web_development"),
    ]
    assert before.registered == ("Finance",)
    assert [one.slug for one in done.created] == ["web_development"]
    assert [(one.name, one.slug) for one in after.to_found] == [("Design", "design")]
    assert sorted(after.registered) == ["Finance", "Web Development"]
    assert sql(
        url,
        "SELECT name, scope_slug FROM gate.department WHERE slug = 'web_development'"
        " AND deleted_at IS NULL",
    ) == [("Web Development", "web_development")]
    founding = sql(
        url,
        "SELECT actor_id FROM obs.audit_entry WHERE subject = 'department:web_development'",
    )
    assert founding == [("u_admin",)]


def test_a_run_places_people_in_the_teams_a_source_names_by_its_own_spelling(url: str) -> None:
    """Lark spells the department `Web Development` and the install's slug is `web_development`;
    the plan matches them, so the person is placed in the team and the lead appointed, as the
    source's actor. Until 2026-09-29 the plan compared the spelling with the slug and placed
    nobody. Delete this and every department with a space in its name places nobody."""
    roster = Roster(
        source="lark",
        complete=True,
        asserts=frozenset({Asserts.EXISTENCE, Asserts.DEPARTMENT}),
        people=(
            StaffRecord("wei@example.test", "Wei", department="Web Development", teams=("design",)),
            StaffRecord("new@example.test", "New", department="web development", leads=True),
        ),
    )
    for pid, name in (("u_wei", "Wei"), ("u_new", "New")):
        sql(
            url,
            "INSERT INTO auth.principal (id, kind, employment, display_name)"
            " VALUES (%s, 'human', 'staff', %s)",
            pid,
            name,
        )

    async def walk(sessions: async_sessionmaker[AsyncSession]) -> Any:
        store = StoredOrganisation(sessions)
        department, scope = founded("web_development", "Web Development")
        await store.found_department(department=department, scope=scope, by=BY)
        from brain.identity.teams import Team

        await store.add_team(
            team=Team(
                company_id="company",
                department_slug="web_development",
                slug="design",
                name="Design",
            ),
            by=BY,
        )
        return await apply_organisation(
            sessions,
            roster,
            known={"wei@example.test": "u_wei", "new@example.test": "u_new"},
            last_applied=None,
            # The trace a scheduled run writes under, not one written for the test: until
            # 2026-09-29 the run's was an ISO time the ledger refuses, and every placement with it.
            trace_id=sync_trace("staff-sync", datetime(2999, 3, 1, 2, 0, tzinfo=UTC)),
        )

    plan = through(url, walk)

    sync = f"{SYNC_ACTOR_PREFIX}lark"
    assert plan.unregistered == ()
    assert sql(url, "SELECT principal_id, added_by FROM gate.team_membership") == [("u_wei", sync)]
    assert sql(url, "SELECT principal_id, appointed_by FROM gate.department_lead") == [
        ("u_new", sync)
    ]


@pytest.mark.parametrize(
    "at",
    [
        datetime(2999, 3, 1, 2, 0, tzinfo=UTC),
        datetime(2019, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
        datetime(2999, 3, 1, 10, 30, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_a_scheduled_run_s_trace_is_one_the_ledger_accepts(at: datetime) -> None:
    """The ledger's own pattern, for any clock and any offset, and the same instant in two zones is
    one trace. Delete this and a step can go back to `now.isoformat()`, which the ledger refuses
    with the whole write, and the run's broad catch hides it."""
    assert re.fullmatch(TRACE_ID, sync_trace("staff-sync", at))
    assert sync_trace("staff-accounts", at) == sync_trace("staff-accounts", at.astimezone(UTC))
