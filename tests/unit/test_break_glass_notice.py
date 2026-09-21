"""A break-glass session notifies the standing Super Admins: the table and the screen.

`tests/unit/test_elevation_store.py` proves an approval writes one notice per standing Super Admin
in its own transaction; `tests/unit/test_elevation.py` holds who is told (`client_recipients`) and
`tests/unit/test_govern_people_routes.py` that the route asks it. This file holds the table the
notices live in, the route that answers each person their own and nobody else's, and, on
PostgreSQL, that an approval with nobody independent to tell writes nothing at all. **The
database half skips without a server**, which CI provides.

Task ids: M1.2.5
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.app import Settings, create_app
from brain.db import metadata
from brain.gate.elevation_store import NoticeRecords, StoredElevations, StoredNotices
from brain.identity.roles import BreakGlassReason
from brain.ops.notices import NoticeKind, notice
from brain.session import make_session_factory
from brain.tables.break_glass_notice import BreakGlassNoticeRow
from brain.tables.identity import one_of
from tests.fixtures.console_http import gate_wiring, headers
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_elevation_store import CAPABILITY, grant_for, tell, through_0062
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

MIGRATION: Final = VERSIONS / "0109_group_role_rule.py"
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect
API = "/api/v1"

#: Far from any wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


# ------------------------------------------------------------------- the notice
def test_the_notice_says_it_is_shown_and_has_no_switch() -> None:
    """The Notifications screen's sentence matches what now happens, and the notice still cannot
    be silenced. Delete this and the screen goes on saying nothing sends it."""
    emergency = notice(NoticeKind.EMERGENCY_ACCESS.value)
    assert not emergency.switchable
    assert "Elevation screen" in emergency.how


# ------------------------------------------------------------------- the table
def test_the_migration_builds_the_notice_table_exactly_as_the_model_declares_it() -> None:
    """Delete this and the model can declare the check that the person acting is never told, and
    the database not hold it."""
    emitted = squash(rendered("upgrade", MIGRATION))
    table = metadata.tables["gate.break_glass_notice"]
    assert squash(str(CreateTable(table).compile(dialect=DIALECT))) in emitted
    for index in table.indexes:
        assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted


def test_a_notice_is_written_once_and_never_edited() -> None:
    """SELECT and INSERT only, and the copied reasons are the live ones. Delete this and a notice
    of emergency access can be quietly rewritten or removed afterwards."""
    m = migration_module(MIGRATION)
    assert m.NOTICE_GRANTS == ("GRANT SELECT, INSERT ON gate.break_glass_notice TO brain_app",)
    assert one_of("reason", BreakGlassReason) == m.BREAK_GLASS_REASONS


# ------------------------------------------------------------------- the screen
@dataclass
class Notices:
    rows: list[BreakGlassNoticeRow] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)

    async def addressed_to(self, recipient_id: str, *, limit: int) -> list[BreakGlassNoticeRow]:
        self.asked.append(recipient_id)
        return list(self.rows)

    def add(self, recipient: str) -> None:
        row = BreakGlassNoticeRow(
            id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            recipient_id=recipient,
            principal_id="u_requester",
            authorised_by="u_approver",
            reason="lockout",
            lapses_at=LONG_AGO + timedelta(hours=4),
        )
        row.created_at = LONG_AGO
        self.rows.append(row)


@pytest.fixture
def notices() -> Notices:
    return Notices()


@pytest.fixture
def client(notices: Notices) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = gate_wiring({"u_admin": (), "u_wide": ()})
        app.state.break_glass_notices = notices
        app.state.db_sessions = None
        yield c


def test_a_super_admin_reads_the_sessions_they_were_told_about(
    client: TestClient, notices: Notices
) -> None:
    """The delivery half of "notifies". Delete this and the notices are written and read by
    nobody."""
    notices.add("u_admin")
    answered = client.get(f"{API}/govern/elevation/notices", headers=headers("u_admin"))
    assert answered.status_code == 200, answered.text
    [item] = answered.json()["items"]
    assert (item["principal_id"], item["authorised_by"], item["reason"]) == (
        "u_requester",
        "u_approver",
        "lockout",
    )
    assert notices.asked == ["u_admin"]


def test_nobody_is_shown_a_notice_addressed_to_somebody_else(
    client: TestClient, notices: Notices
) -> None:
    """Asked by the caller's own id, and a row for anybody else dropped even if a store returned
    it. Delete this and every emergency access is readable by whoever asks."""
    notices.add("u_admin")
    answered = client.get(f"{API}/govern/elevation/notices", headers=headers("u_wide"))
    assert answered.status_code == 200
    assert answered.json() == {"items": []}
    assert notices.asked == ["u_wide"]


def test_the_stored_notices_are_the_records_the_route_asks_for() -> None:
    """Delete this and the store can drift from the protocol the route holds."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    assert isinstance(StoredNotices(async_sessionmaker()), NoticeRecords)


# ------------------------------------------------------------------- the database
def test_an_approval_with_no_standing_super_admin_to_tell_writes_nothing() -> None:
    """A session nobody is told about is an unaudited admin account, so it does not open: no
    grant, no decision, no notice. Delete this and an install with no Super Admin on record hands
    out emergency access in silence. **Skips without a server.**"""
    with through_0062("brain_break_glass_notice") as url:
        for pid in ("u_requester", "u_approver"):
            sql(
                url,
                "INSERT INTO auth.principal (id, kind, employment, display_name,"
                " primary_department) VALUES (%s, 'human', 'staff', %s, 'web')",
                pid,
                f"Person {pid}",
            )
        sql(
            url,
            "INSERT INTO gate.scope (slug, predicate)"
            " VALUES ('web_all', '{\"department\": \"web\"}')",
        )

        async def walk() -> object:
            engine = app_engine(url)
            try:
                store = StoredElevations(make_session_factory(engine))
                filed = await store.file(
                    principal_id="u_requester",
                    capability=CAPABILITY,
                    scope_slug="web_all",
                    reason=BreakGlassReason.LOCKOUT.value,
                    explanation="locked out of the client portal",
                    hours=1,
                    ent_hash="a" * 32,
                    trace_id="trace-file",
                )
                assert filed is not None
                return await store.approve(
                    filed.request_id,
                    approver_id="u_approver",
                    ent_hash="b" * 32,
                    trace_id="trace-approve",
                    grant_for=grant_for,
                    tell=tell,
                )
            finally:
                await engine.dispose()

        decided = run(walk)
        written = sql(
            url,
            "SELECT (SELECT count(*) FROM gate.break_glass_notice),"
            " (SELECT count(*) FROM gate.capability_grant WHERE principal_id = 'u_requester'),"
            " (SELECT count(*) FROM gate.elevation_request WHERE decision IS NOT NULL)",
        )

    assert decided is None
    assert written == [(0, 0, 0)]
