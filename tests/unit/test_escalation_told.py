"""An asker whose handed-on question expired is told once, in their own chat, by the web process.

The pure half holds the sentence, the key and the cadence, and drives
`brain.escalation_told.tell_expired_askers` with its sender and its switch replaced. The server
half builds the schema at head, files handoffs through `brain.ops.escalation_store`, expires them as
the worker's login does, and reads them back through `0177`'s function as a reader with no row of
their own.

Task ids: M8.3.4
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import psycopg
import pytest
from sqlalchemy import text

from brain import escalation_told
from brain.escalation_told import (
    A_HANDED_ON_QUESTION_NOBODY_PICKED_UP,
    AN_EXPIRED_HANDOFF_IS_READ_FOR_ITS_ASKER_AND_NAMES_NOTHING_ELSE,
    INTENT_PREFIX,
    LOOKBACK,
    TELL_EVERY,
    Expired,
    expired_between,
    expired_text,
    intent_ref_for,
    tell_expired_askers,
)
from brain.gate.abstain import EXPIRY_EVERY
from brain.ops.escalation_store import StoredEscalations, expire_overdue
from brain.ops.notices import NoticeKind
from brain.session import make_session_factory
from brain.tables.channel import DeliveryOutcome
from tests.fixtures.scratch_postgres import migrate, run, sql
from tests.unit.test_acceptance import at_head
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_escalation_store import LONG_AGO, QUEUE, _escalation

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "0177_expired_handoffs.py"
SRC = ROOT / "src" / "brain"
NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m0177", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------ the pieces
def test_the_asker_is_told_the_queue_their_question_went_to_and_nothing_of_the_question() -> None:
    """The sentence names the queue the asker was told, and the key is one per handoff. Delete
    this and a later message can quote the question to wherever the person last wrote, or two
    handoffs share a key and the second asker is never told."""
    said = expired_text(QUEUE)
    one = Expired(escalation_id="e1", asker_id="u_asker", queue=QUEUE, expired_at=NOW)

    assert said == A_HANDED_ON_QUESTION_NOBODY_PICKED_UP.format(queue=QUEUE)
    assert QUEUE in said and "{" not in said
    assert intent_ref_for(one) == f"{INTENT_PREFIX}.e1"
    assert intent_ref_for(replace(one, escalation_id="e2")) != intent_ref_for(one)


def test_the_loop_runs_as_often_as_the_worker_marks_and_looks_back_further() -> None:
    """Asked as often as the worker expires handoffs, and looking back more than one gap, so a
    handoff expired between two passes, or while the process was down for hours, is still told.
    Delete this and a cadence edit leaves askers told late, or a lookback shorter than the gap
    leaves some never told."""
    assert TELL_EVERY == EXPIRY_EVERY
    assert LOOKBACK >= TELL_EVERY * 4


@dataclass
class Session:
    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


@dataclass
class Sent:
    outcome: DeliveryOutcome
    issued: bool = True


@dataclass
class Teller:
    """`brain.tell_later.tell` in memory: every message it was asked to send."""

    told: list[tuple[str, str, str]] = field(default_factory=list)
    reachable: frozenset[str] = frozenset({"u_asker"})

    async def __call__(
        self, request: Any, person: str, said: str, *, intent_ref: str, now: datetime
    ) -> Sent | None:
        self.told.append((person, said, intent_ref))
        return Sent(DeliveryOutcome.SENT) if person in self.reachable else None


def telling(monkeypatch: pytest.MonkeyPatch, *, on: bool) -> Teller:
    teller = Teller()

    async def switched(session: Any, kind: NoticeKind) -> bool:
        assert kind is NoticeKind.QUESTION_NOT_PICKED_UP
        return on

    monkeypatch.setattr(escalation_told, "notice_is_on", switched)
    monkeypatch.setattr(escalation_told, "tell", teller)
    return teller


EXPIRED = (
    Expired(escalation_id="e1", asker_id="u_asker", queue=QUEUE, expired_at=NOW),
    Expired(escalation_id="e2", asker_id="u_gone", queue="finance", expired_at=NOW),
)


def test_each_asker_is_told_once_under_the_handoff_s_own_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**The positive case.** Every expired handoff is handed to the sender with its asker, the
    sentence for its queue and its own key, and only the ones sent are counted. Delete this and
    the loop can tell nobody while its switch reads on."""
    teller = telling(monkeypatch, on=True)

    sent = asyncio.run(tell_expired_askers(None, Session, now=NOW, expired=EXPIRED))  # type: ignore[arg-type]

    assert sent == 1
    assert teller.told == [
        ("u_asker", expired_text(QUEUE), "escalation_expired.e1"),
        ("u_gone", expired_text("finance"), "escalation_expired.e2"),
    ]


def test_switched_off_the_notice_tells_nobody(monkeypatch: pytest.MonkeyPatch) -> None:
    """`QUESTION_NOT_PICKED_UP` off, nothing is sent. Delete this and an administrator's switch
    stops nothing."""
    teller = telling(monkeypatch, on=False)

    sent = asyncio.run(tell_expired_askers(None, Session, now=NOW, expired=EXPIRED))  # type: ignore[arg-type]

    assert (sent, teller.told) == (0, [])


def test_the_sender_is_the_one_later_sender_and_the_worker_sends_nothing() -> None:
    """`THE_WORKER_MARKS_AND_THE_WEB_PROCESS_TELLS`: the telling module sends through
    `brain.tell_later.tell` alone, and the worker's expiry imports neither. Delete this and a
    second path to a chat appears beside the one that re-checks reach, or the worker starts
    needing the channels' tokens."""
    told = ast.parse((SRC / "escalation_told.py").read_text(encoding="utf-8"))
    imported = {
        (node.module, alias.name)
        for node in ast.walk(told)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert ("brain.tell_later", "tell") in imported
    assert not any(module == "brain.channels.outbound" for module, _ in imported)
    worker = (SRC / "ops" / "escalation_store.py").read_text(encoding="utf-8")
    assert "tell_later" not in worker and "escalation_told" not in worker


# ------------------------------------------------------------------------ the migration
def test_the_function_is_a_pinned_definer_revoked_from_public_that_reads_no_clock() -> None:
    """What `0172`'s function is held to, held here too, off the migration's own statements.
    Delete this and the search path can be left to the caller, PUBLIC keep EXECUTE, or the window
    end on the database's clock."""
    built = migration()
    body = " ".join(built.CREATE_FUNCTION.split())

    assert "SECURITY DEFINER" in body and "STABLE" in body
    assert "SET search_path = pg_catalog, gate" in body
    assert "now()" not in body.lower()
    assert (
        f"REVOKE EXECUTE ON FUNCTION {built.FUNCTION} FROM PUBLIC",
        f"GRANT EXECUTE ON FUNCTION {built.FUNCTION} TO brain_app",
    ) == built.GRANTS
    assert f"FROM {built.FUNCTION.split('(')[0]}(" in str(escalation_told._READ)
    assert "question" in AN_EXPIRED_HANDOFF_IS_READ_FOR_ITS_ASKER_AND_NAMES_NOTHING_ELSE


# ------------------------------------------------------------------------ on a server
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_escalation_told") as url:
        for pid in ("u_admin", "u_asker", "u_other"):
            sql(
                url,
                "INSERT INTO auth.principal (id, kind, employment, display_name) "
                "VALUES (%s, 'human', 'staff', %s) ON CONFLICT (id) DO NOTHING",
                pid,
                pid,
            )
        yield url


def _file(url: str, *askers: str) -> list[str]:
    async def go() -> list[str]:
        engine = app_engine(url)
        try:
            store = StoredEscalations(make_session_factory(engine))
            ids = []
            for asker in askers:
                raised = _escalation(now=LONG_AGO)
                filed = await store.file(
                    replace(raised, handoff=replace(raised.handoff, asker_id=asker)),
                    skill_name="quote-desk",
                    agent_id="agent_quotes",
                    ent_hash="0" * 32,
                )
                ids.append(filed.escalation_id)
            return ids
        finally:
            await engine.dispose()

    return run(go)


def _expire(url: str, at: datetime) -> int:
    async def go() -> int:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        from brain.db import normalise_database_url

        engine = create_async_engine(normalise_database_url(url), poolclass=NullPool)
        try:
            async with make_session_factory(engine)() as session, session.begin():
                return await expire_overdue(session, now=at)
        finally:
            await engine.dispose()

    return run(go)


EXPIRED_AT = LONG_AGO + timedelta(days=1)


@pytest.mark.needs_db
def test_the_function_returns_who_asked_the_queue_and_when_and_nothing_else(install: str) -> None:
    """**What crosses the policy is four facts per handoff.** One row per handoff that expired in
    the window, with its id, asker, queue and expiry and no other column, oldest first; a window
    ending before the expiry returns none. Delete this and the function can return the question,
    what was tried or whom it went to, to a process telling somebody else."""
    ids = _file(install, "u_asker", "u_other")
    assert _expire(install, EXPIRED_AT) >= 2

    with psycopg.connect(install) as conn:
        cursor = conn.execute(
            "SELECT * FROM gate.expired_handoffs(%s, %s, %s)",
            (EXPIRED_AT - timedelta(hours=1), EXPIRED_AT, 50),
        )
        columns = [one.name for one in cursor.description or ()]
        rows = cursor.fetchall()
        before = conn.execute(
            "SELECT * FROM gate.expired_handoffs(%s, %s, %s)",
            (EXPIRED_AT - timedelta(hours=1), EXPIRED_AT - timedelta(seconds=1), 50),
        ).fetchall()

    assert columns == ["escalation_id", "asker_id", "queue", "expired_at"]
    mine = [row for row in rows if str(row[0]) in ids]
    assert sorted((row[1], row[2], row[3]) for row in mine) == [
        ("u_asker", QUEUE, EXPIRED_AT),
        ("u_other", QUEUE, EXPIRED_AT),
    ]
    assert not [row for row in before if str(row[0]) in ids]


@pytest.mark.needs_db
def test_a_reader_with_no_handoff_of_their_own_still_learns_which_expired(install: str) -> None:
    """**The reason the function exists.** As the application role for somebody who asked nothing,
    the table shows none of the handoffs and `expired_between` still returns every one that
    expired. Delete this and the telling loop can be read under a reader's policy, where it would
    find nothing and tell nobody."""
    ids = _file(install, "u_asker")
    later = EXPIRED_AT + timedelta(days=30)
    assert _expire(install, later) >= 1

    async def go() -> tuple[int, tuple[Expired, ...]]:
        engine = app_engine(install)
        try:
            sessions = make_session_factory(engine)
            async with sessions() as session, session.begin():
                await session.execute(
                    text("SELECT set_config('app.principal_id', 'u_stranger', true)")
                )
                seen = (
                    await session.execute(text("SELECT count(*) FROM gate.escalation"))
                ).scalar_one()
            found = await expired_between(sessions, after=later - timedelta(hours=1), until=later)
            return int(seen), found
        finally:
            await engine.dispose()

    seen, found = run(go)

    assert seen == 0
    assert [(one.asker_id, one.queue) for one in found if one.escalation_id in ids] == [
        ("u_asker", QUEUE)
    ]


@pytest.mark.needs_db
def test_the_function_runs_as_its_owner_for_the_application_alone(install: str) -> None:
    """Read off the catalogue. Delete this and a missing REVOKE leaves a read past the handoff
    policy callable by any role with USAGE on the schema."""
    [(definer, config, acl)] = sql(
        install,
        "SELECT prosecdef, proconfig, proacl::text[] FROM pg_proc"
        " WHERE proname = 'expired_handoffs'",
    )
    assert definer is True
    assert config == ["search_path=pg_catalog, gate"]
    assert not any(one.startswith("=") for one in acl), acl
    assert any(one.startswith("brain_app=X/") for one in acl), acl


@pytest.mark.needs_db
def test_the_migration_reverses_and_applies_again(install: str) -> None:
    """Delete this and a rollback can leave a definer function no migration knows it owns."""
    database = install.rsplit("/", 1)[-1].split("?")[0]
    migrate(database, "downgrade", str(migration().down_revision))
    gone = sql(install, "SELECT count(*) FROM pg_proc WHERE proname = 'expired_handoffs'")
    migrate(database, "upgrade", "head")
    back = sql(install, "SELECT count(*) FROM pg_proc WHERE proname = 'expired_handoffs'")

    assert (gone, back) == ([(0,)], [(1,)])
