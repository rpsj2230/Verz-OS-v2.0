"""The scheduled staff sync against a real PostgreSQL: two nights, a leaver, and a refused secret.

`tests/unit/test_staff_sync_run.py` holds the run's order with stand-ins. This drives the same
`sync_staff_on` through `brain.ops.staff_sync_store` into a scratch database built from the models,
so the statements the run writes are the ones checked: the upsert, the mark, the run row, the
check that refuses a failed run naming anybody, and the join from a leaver to their principal.
CI sets `DATABASE_URL`; without it every test here is skipped by `admin_url`.

Task ids: M1.6.1, M1.6.2, M1.6.7, M1.6.12, M1.8.6, M1.8.9
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.connectors.staff_directories import Answer, Outbound
from brain.gate.context import Channel
from brain.gate.ingress import identity_hash
from brain.identity.staff_roster import RunOutcome
from brain.ops.staff_sync_run import StaffSyncRun, sync_staff_on
from brain.ops.staff_sync_store import read_last_applied, read_leavers, read_runs
from brain.session import make_app_engine, make_session_factory
from tests.fixtures.roster_payloads import LARK_USERS_PAGE_TWO
from tests.fixtures.scratch_postgres import modelled, run, sql
from tests.unit.test_staff_sync_run import APP_ID, APP_SECRET, LARK_ENV, Directory, Keys, Lease

TABLES: tuple[str, ...] = (
    # The run stops a leaver's agents in its own transaction, so it writes this table too.
    "agent.agent",
    "auth.principal",
    "auth.principal_identity",
    "auth.staff_member",
    "auth.staff_sync_run",
)

#: Far outside any plausible wall clock, on `tests/unit/test_scope_and_capability.py`'s rule.
FIRST_NIGHT = datetime(2999, 3, 1, 2, 0, tzinfo=UTC)
SECOND_NIGHT = FIRST_NIGHT + timedelta(days=1)


@pytest.fixture
def url() -> Iterator[str]:
    with modelled("brain_test_staff_sync_store", TABLES) as scratch:
        yield scratch


def through[T](url: str, work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = make_app_engine(url)
        try:
            return await work(make_session_factory(engine))
        finally:
            await engine.dispose()

    return run(go)


class OnlyKatherine(Directory):
    """The second night: the root department holds Katherine alone and there is nothing more."""

    async def __call__(self, outbound: Outbound) -> Answer:
        self.sent.append(outbound)
        if outbound.url.endswith("/auth/v3/tenant_access_token/internal"):
            return self.token_answer
        if "departments/0/children" in outbound.url:
            return Answer(200, {"code": 0, "data": {"has_more": False, "items": []}})
        return Answer(200, LARK_USERS_PAGE_TWO)


def sync(
    url: str, *, at: datetime, fetch: Directory, env: Mapping[str, str] = LARK_ENV
) -> StaffSyncRun:
    keys = Keys(Lease(f"{APP_ID}:{APP_SECRET}"))
    return through(
        url,
        lambda sessions: sync_staff_on(
            sessions=sessions,
            now=at,
            env=env,
            keys=keys,
            fetch=fetch,
            clock=lambda: at + timedelta(seconds=5),
        ),
    )


def rows(url: str, statement: str, *params: object) -> list[tuple[Any, ...]]:
    return sql(url, statement, *params)


def test_two_nights_add_the_people_listed_and_then_mark_the_one_no_longer_named(url: str) -> None:
    """M1.6.12 end to end: the first night adds and removes nobody, the second marks a leaver.

    Delete this and the upsert, the mark and `last_applied` could each be wrong with every
    stand-in test green, because none of them has run against a table."""
    first = sync(url, at=FIRST_NIGHT, fetch=Directory())
    second = sync(url, at=SECOND_NIGHT, fetch=OnlyKatherine())

    assert first.outcome is RunOutcome.APPLIED
    assert second.outcome is RunOutcome.APPLIED
    members = dict(rows(url, "SELECT display_name, left_because FROM auth.staff_member ORDER BY 1"))
    assert members == {"Ada Lovelace": "absent_from_complete_roster", "Katherine Johnson": None}
    assert through(url, lambda s: _last_applied(s)) == SECOND_NIGHT + timedelta(seconds=5)
    runs = through(url, lambda s: _runs(s))
    assert [one.marked_left for one in runs] == [("Ada Lovelace",), ()]


def test_the_roster_holds_digests_and_no_address_and_gives_nobody_a_sign_in(url: str) -> None:
    """M1.6.2: a roster lists people and never signs anybody in, measured in the tables.

    Delete this and a run could write an address into the roster or a principal and a binding for
    whoever the source names, which is a spreadsheet appointing people."""
    sync(url, at=FIRST_NIGHT, fetch=Directory())

    stored = rows(url, "SELECT address_hash, display_name FROM auth.staff_member")
    assert stored
    assert all("@" not in digest and len(digest) == 64 for digest, _ in stored)
    assert rows(url, "SELECT count(*) FROM auth.principal") == [(0,)]
    assert rows(url, "SELECT count(*) FROM auth.principal_identity") == [(0,)]


def test_a_leaver_with_a_proven_email_binding_is_the_principal_whose_agents_are_listed(
    url: str,
) -> None:
    """M1.8.9's join: the mark the sync wrote, to the principal an email binding proves.

    Delete this and the transfer list reads nobody on an install where the sync marks leavers."""
    rows(
        url,
        "INSERT INTO auth.principal (id, kind, employment, display_name) "
        "VALUES ('p_ada', 'human', 'staff', 'Ada')",
    )
    rows(
        url,
        "INSERT INTO auth.principal_identity (channel, identity_hash, principal_id, bound_at) "
        "VALUES (%s, %s, 'p_ada', now())",
        Channel.EMAIL.value,
        identity_hash(Channel.EMAIL, "ada@example.com"),
    )
    sync(url, at=FIRST_NIGHT, fetch=Directory())
    assert through(url, lambda s: _leavers(s)) == frozenset()

    sync(url, at=SECOND_NIGHT, fetch=OnlyKatherine())

    assert through(url, lambda s: _leavers(s)) == frozenset({"p_ada"})


def an_agent_row(url: str, agent_id: str, owner: str, *, archived: bool = False) -> None:
    sql(
        url,
        "INSERT INTO agent.agent (id, display_name, persona, tier, visibility, owner_id,"
        " department, scope, capabilities, allowed_tools, required_tools, max_side_effect,"
        " created_by, archived_at) VALUES (%s, 'Quote helper', 'Answers briefly.', 'main',"
        " 'company', %s, NULL, '{\"clauses\": []}', '{}', '{}', '{}', 'none', %s,"
        " CASE WHEN %s THEN now() END)",
        agent_id,
        owner,
        owner,
        archived,
    )


def test_the_night_that_marks_a_leaver_stops_their_agents_and_nobody_elses(url: str) -> None:
    """M1.8.9, as the owner decided it: a leaver's agents stop until a new owner accepts them.

    Ada's running agent is disabled by the run that marks her, her archived agent is left as it
    was, and Katherine's agent keeps running. Delete this and the statement could stop nobody, or
    everybody, with every stand-in test green."""
    rows(
        url,
        "INSERT INTO auth.principal (id, kind, employment, display_name) "
        "VALUES ('p_ada', 'human', 'staff', 'Ada')",
    )
    rows(
        url,
        "INSERT INTO auth.principal_identity (channel, identity_hash, principal_id, bound_at) "
        "VALUES (%s, %s, 'p_ada', now())",
        Channel.EMAIL.value,
        identity_hash(Channel.EMAIL, "ada@example.com"),
    )
    an_agent_row(url, "adas-helper", "p_ada")
    an_agent_row(url, "adas-old-helper", "p_ada", archived=True)
    an_agent_row(url, "someone-elses", "p_katherine")
    sync(url, at=FIRST_NIGHT, fetch=Directory())
    assert rows(url, "SELECT count(*) FROM agent.agent WHERE disabled_at IS NOT NULL") == [(0,)]

    sync(url, at=SECOND_NIGHT, fetch=OnlyKatherine())

    stopped = dict(rows(url, "SELECT id, disabled_at IS NOT NULL FROM agent.agent ORDER BY id"))
    assert stopped == {"adas-helper": True, "adas-old-helper": False, "someone-elses": False}


def test_a_refused_credential_on_the_second_night_changes_nobody_in_the_table(url: str) -> None:
    """M1.8.6 in the database: one run row saying so, and every member exactly as it was.

    Delete this and a refused secret could reach the members table through a path the stand-in
    test does not see."""
    sync(url, at=FIRST_NIGHT, fetch=Directory())
    before = rows(url, "SELECT * FROM auth.staff_member ORDER BY id")
    refused = Directory(token_answer=Answer(200, {"code": 10014, "msg": "app secret invalid"}))

    ran = sync(url, at=SECOND_NIGHT, fetch=refused)

    assert ran.outcome is RunOutcome.CREDENTIAL_REFUSED
    assert rows(url, "SELECT * FROM auth.staff_member ORDER BY id") == before
    newest = through(url, lambda s: _runs(s))[0]
    assert newest.outcome is RunOutcome.CREDENTIAL_REFUSED
    assert through(url, lambda s: _last_applied(s)) == FIRST_NIGHT + timedelta(seconds=5)


def test_the_table_refuses_a_failed_run_that_names_anybody(url: str) -> None:
    """The check `only_an_applied_run_changes_anybody`, which holds the rule below the code.

    Delete this and a later writer could record a refused run beside a list of leavers."""
    import psycopg

    with pytest.raises(psycopg.errors.CheckViolation):
        rows(
            url,
            "INSERT INTO auth.staff_sync_run (source, started_at, finished_at, outcome, detail, "
            "added, marked_left, renamed, withheld) VALUES ('lark', now(), now(), "
            "'credential_refused', 'refused', '{}', '{Ada}', '{}', '{}')",
        )


async def _last_applied(sessions: async_sessionmaker[AsyncSession]) -> datetime | None:
    async with sessions() as session, session.begin():
        return await read_last_applied(session, "lark")


async def _runs(sessions: async_sessionmaker[AsyncSession]) -> Any:
    async with sessions() as session, session.begin():
        return await read_runs(session)


async def _leavers(sessions: async_sessionmaker[AsyncSession]) -> frozenset[str]:
    async with sessions() as session, session.begin():
        return await read_leavers(session)
