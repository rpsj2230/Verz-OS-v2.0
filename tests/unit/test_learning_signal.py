"""A mark on an answer and a pause on an agent's learning: the tables, the store and their readers.

The first half holds the migration's copied widths to the models and holds that nothing deciding
an answer can read a mark. The second builds PostgreSQL to head and drives
`brain.ops.learning_signal_store` as the application role: a mark lands only on an answer the
marker was given, a count takes each person's latest mark once, a row in somebody else's name is
refused by the database, and a paused agent's turn forms no memory while a resumed one does.

**The database half skips when there is no server**, and CI always has one.

Task ids: M16.7.2, M16.6.4, M16.7.4, M16.7.13
"""

from __future__ import annotations

import ast
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.memory.turn import NotFormed, Turn
from brain.ops.learning_signal_store import (
    MARKABLE_FOR,
    StoredLearningPauses,
    StoredMarks,
    Tallied,
)
from brain.ops.memory_store import StoredFormations
from brain.session import make_session_factory
from brain.tables import learning_signal as tables
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import ROOT, at_head
from tests.unit.test_automation_owner_store import app_engine

MIGRATION = ROOT / "migrations" / "versions" / "0154_answer_marks_and_learning_pause.py"

#: The packages whose modules decide what an answer says, retrieves or remembers.
DECIDING_PACKAGES = ("gate", "memory", "knowledge", "core")

#: The two modules a mark lives in.
MARK_MODULES = frozenset({"brain.tables.learning_signal", "brain.ops.learning_signal_store"})


def migration_module() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("migration_0154", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------ without a server
def test_the_migration_copies_the_widths_the_models_declare() -> None:
    """A migration may not import live model code, so the widths are copied. Delete this and a
    column can be wider in the model than in the database, and a trace or a reason is cut on the
    way in."""
    from brain.agents.model import AGENT_ID_CHARS
    from brain.tables.audit import TRACE_ID_CHARS
    from brain.tables.identity import PRINCIPAL_ID_CHARS

    built = migration_module()
    assert built.TRACE_ID_CHARS == tables.TRACE_ID_CHARS == TRACE_ID_CHARS
    assert built.PRINCIPAL_ID_CHARS == PRINCIPAL_ID_CHARS
    assert built.AGENT_ID_CHARS == AGENT_ID_CHARS
    assert built.REASON_CHARS == tables.REASON_CHARS
    assert all("UPDATE" not in one and "DELETE" not in one for one in built.GRANTS)


def test_nothing_that_decides_an_answer_can_read_a_mark() -> None:
    """**A mark is counted and changes nothing by itself** (M16.7.4). No module under the packages
    that decide what an answer retrieves, remembers or says imports the mark's table or its store,
    so a later answer is retrieved exactly as it would have been with no mark. Delete this and a
    retrieval boost read off one person's click can arrive in a diff about something else."""
    importing: list[str] = []
    for package in DECIDING_PACKAGES:
        for path in sorted((ROOT / "src" / "brain" / package).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    names = [node.module]
                if set(names) & MARK_MODULES:
                    importing.append(str(path.relative_to(ROOT)))
    assert importing == []
    assert (ROOT / "src" / "brain" / "gate" / "answer.py").exists()


def test_the_markable_window_is_a_week() -> None:
    """Delete this and the window can shrink until nobody can mark an answer they acted on, or
    grow until every mark reads the whole request ledger."""
    assert timedelta(days=7) == MARKABLE_FOR


# --------------------------------------------------------------------------- on a server
NOW = datetime.now(UTC)
ME, SOMEBODY = "u_marker", "u_somebody"


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    with at_head("brain_learning_signal") as url:
        yield url


def answered(url: str, trace: str, principal: str, at: datetime | None = None) -> None:
    """One finished request in the ledger, answering `principal` under `trace`."""
    sql(
        url,
        "INSERT INTO obs.request_telemetry (received_at, trace_id, traffic_class, principal, "
        "entitlement_hash, lane, cache_hit, status, duration_ms) VALUES "
        "(%s, %s, 'human_interactive', %s, %s, 'answer', false, 'answered', 10)",
        at or NOW,
        trace,
        principal,
        "a" * 32,
    )


def with_sessions[T](url: str, work: Callable[[Any], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = app_engine(url)
        try:
            return await work(make_session_factory(engine))
        finally:
            await engine.dispose()

    return run(go)


@pytest.mark.needs_db
def test_a_person_marks_their_own_answer_and_no_other(database: str) -> None:
    """**A mark is on an answer the marker was given** (M16.6.4). Their own trace is counted;
    somebody else's, one that never ran and one older than the window are refused and write
    nothing. Delete this and a person can count against answers other people were given, and
    learn from the refusal which traces exist."""
    answered(database, "trace-mine", ME)
    answered(database, "trace-theirs", SOMEBODY)
    answered(database, "trace-old", ME, NOW - MARKABLE_FOR - timedelta(hours=1))
    before = sql(database, "SELECT count(*) FROM mem.mark")

    def marking(trace: str) -> Callable[[Any], Awaitable[bool]]:
        async def go(sessions: Any) -> bool:
            return await StoredMarks(sessions).mark(
                principal_id=ME, trace_id=trace, helpful=False, now=NOW
            )

        return go

    mine = with_sessions(database, marking("trace-mine"))
    refused = [
        with_sessions(database, marking(trace))
        for trace in ("trace-theirs", "trace-never", "trace-old")
    ]
    after = sql(database, "SELECT trace_id, principal_id, helpful FROM mem.mark")

    assert mine is True
    assert refused == [False, False, False]
    assert before == [(0,)]
    assert after == [("trace-mine", ME, False)]


@pytest.mark.needs_db
def test_an_answer_is_counted_once_by_each_persons_latest_mark(database: str) -> None:
    """A second mark by the same person replaces their first in the count, and each answer counts
    once. Delete this and pressing a button twice counts twice."""
    answered(database, "trace-counted", ME)

    async def go(sessions: Any) -> tuple[Tallied, Tallied]:
        marks = StoredMarks(sessions)
        await marks.mark(principal_id=ME, trace_id="trace-counted", helpful=False, now=NOW)
        await marks.mark(principal_id=ME, trace_id="trace-counted", helpful=True, now=NOW)
        return await marks.on("trace-counted"), await marks.counted(
            since=NOW - timedelta(days=1), until=NOW + timedelta(days=1)
        )

    on, window = with_sessions(database, go)

    assert on == Tallied(helpful=1, unhelpful=0)
    assert window.helpful >= 1


@pytest.mark.needs_db
def test_a_row_written_in_somebody_elses_name_is_refused_by_the_database(database: str) -> None:
    """The policies are `0149`'s: a mark names its marker and a pause its setter as the session's
    principal. Delete this and the store's check is the only thing between a person and a mark or
    a pause in somebody else's name."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    async def go(sessions: Any) -> list[bool]:
        refused: list[bool] = []
        for statement in (
            "INSERT INTO mem.mark (trace_id, principal_id, helpful) VALUES ('t', 'u_other', true)",
            "INSERT INTO agent.learning_pause (agent_id, paused, reason, set_by)"
            " VALUES ('desk', true, 'r', 'u_other')",
        ):
            async with sessions() as session:
                try:
                    await session.execute(
                        text("SELECT set_config('app.principal_id', 'u_me', true)")
                    )
                    await session.execute(text(statement))
                    await session.commit()
                    refused.append(False)
                except DBAPIError:
                    refused.append(True)
        return refused

    assert with_sessions(database, go) == [True, True]


def a_turn(said: str, *, agent_id: str | None, trace: str) -> Turn:
    reach = EntitlementSet(
        principal_id=ME,
        grants=(Grant(capability=Capability(value="read:client.name"), scope=Scope()),),
    )
    return Turn(
        trace_id=trace,
        principal_id=ME,
        said=said,
        answered=True,
        reach=reach,
        at=NOW,
        agent_id=agent_id,
        department="web",
    )


@pytest.mark.needs_db
def test_a_paused_agents_turn_forms_nothing_and_a_resumed_or_other_ones_does(
    database: str,
) -> None:
    """**Pausing learning on one agent stops memory formation from its runs** (M16.7.13), and
    only from its runs: a turn with no agent and a turn of another agent still form, and resuming
    the agent forms again from its next turn. Delete this and the switch can pause everything, or
    nothing, with a row saying it paused one agent."""

    async def go(sessions: Any) -> list[tuple[str, ...]]:
        pauses = StoredLearningPauses(sessions)
        formations = StoredFormations(sessions)
        found: list[tuple[str, ...]] = []
        await pauses.set(agent_id="desk", paused=True, reason="an incident", by="u_admin")
        for said, agent_id, trace in (
            ("Remember that I sign as Wei.", "desk", "t-paused"),
            ("Remember that I sit by the window.", None, "t-plain"),
            ("Remember that I like tea.", "other_agent", "t-other"),
        ):
            done = await formations.form(a_turn(said, agent_id=agent_id, trace=trace))
            found.append(tuple(one.value for one in done.skipped) or ("formed",))
        await pauses.set(agent_id="desk", paused=False, reason="resolved", by="u_admin")
        resumed = await formations.form(
            a_turn("Remember that I sign as Wei.", agent_id="desk", trace="t-resumed")
        )
        found.append(tuple(one.value for one in resumed.skipped) or ("formed",))
        found.append(tuple(sorted(await pauses.paused(("desk", "other_agent")))))
        return found

    assert with_sessions(database, go) == [
        (NotFormed.PAUSED.value,),
        ("formed",),
        ("formed",),
        ("formed",),
        (),
    ]
    assert Path(MIGRATION).exists()


@pytest.mark.needs_db
def test_a_helpful_mark_on_an_answer_that_recalled_a_memory_leaves_the_memory_as_it_was(
    database: str,
) -> None:
    """**A mark by itself confirms nothing** (M16.7.4, M16.3.2), and M16.7.2 is where somebody will
    want it to. An inference the person's answer recalled, the answer marked helpful: the memory's
    `last_confirmed_at` is still unset and recall gives it the same confidence as before the mark.
    Saying it again is what confirms it, and that is shown beside. Delete this and a helpful mark
    can start refreshing every memory an answer used, which is a thumb deciding what is kept."""
    from brain.memory.turn import recall_place
    from brain.ops.memory_store import StoredRecall

    trace = "t-recalled"
    answered(database, trace, ME)

    async def go(sessions: Any) -> tuple[object, ...]:
        formations = StoredFormations(sessions)
        made = await formations.form(a_turn("I prefer terse answers.", agent_id=None, trace="t-1"))
        [memory] = made.memory_ids
        reader = a_turn("", agent_id=None, trace="t-2").reach
        where = recall_place(ME, "web")
        before = await StoredRecall(sessions).recalled(reader, where=where, now=NOW)
        marked = await StoredMarks(sessions).mark(
            principal_id=ME, trace_id=trace, helpful=True, now=NOW
        )
        after = await StoredRecall(sessions).recalled(reader, where=where, now=NOW)
        return memory, before, marked, after

    memory, before, marked, after = with_sessions(database, go)
    stamped = sql(database, "SELECT last_confirmed_at FROM mem.adaptive WHERE id = %s", memory)

    assert marked is True
    assert before == after
    assert "I prefer terse answers" in before  # type: ignore[operator]
    assert stamped == [(None,)]

    said_again = with_sessions(
        database,
        lambda sessions: StoredFormations(sessions).form(
            a_turn("I prefer terse answers.", agent_id=None, trace="t-3")
        ),
    )
    assert said_again.confirmed == (memory,)
    assert sql(
        database, "SELECT last_confirmed_at IS NOT NULL FROM mem.adaptive WHERE id = %s", memory
    ) == [(True,)]


@pytest.mark.needs_db
def test_a_confirmation_is_refused_back_dated_or_in_somebody_elses_name(database: str) -> None:
    """`0163`'s policy, asked as the application role: a confirmation stamped with any time but the
    statement's own is refused, one in another person's name moves no row, and one in the person's
    own name at the statement's time is admitted. Delete this and a confirmation could be written
    to keep a memory alive for ever, or for somebody else."""
    import psycopg

    async def go(sessions: Any) -> str:
        made = await StoredFormations(sessions).form(
            a_turn("I prefer blunt answers.", agent_id=None, trace="t-policy")
        )
        return made.memory_ids[0]

    memory = with_sessions(database, go)

    def as_the_application(principal: str, stamp: str) -> tuple[str | None, int]:
        with psycopg.connect(database) as conn:
            try:
                conn.execute("SET LOCAL ROLE brain_app")
                conn.execute("SELECT set_config('app.principal_id', %s, true)", (principal,))
                moved = conn.execute(
                    f"UPDATE mem.adaptive SET last_confirmed_at = {stamp} WHERE id = %s",  # noqa: S608
                    (memory,),
                ).rowcount
            except psycopg.Error as refused:
                conn.rollback()
                return str(refused.sqlstate), 0
            conn.rollback()
        return None, moved

    assert as_the_application(ME, "statement_timestamp() - interval '30 days'")[0] == "42501"
    assert as_the_application(SOMEBODY, "statement_timestamp()") == (None, 0)
    assert as_the_application(ME, "statement_timestamp()") == (None, 1)
