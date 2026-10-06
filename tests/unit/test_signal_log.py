"""The learning signal's log: `0197`, its store and its writers, held to what they refuse to keep.

The first half needs no server. It holds the migration to the model and to the grammars it
copies, holds that no column could hold a sentence and that the install-wide function returns no
column a person could come back in, holds that nothing deciding an answer imports the log, and
holds that a question handed to a person says so on the answer and on the exchange kept.

The second half builds PostgreSQL to head and drives the writers as the application role: a
question asking the thread's last one again is a signal naming the earlier answer and one on
another subject is not, an exchange handed to a person and an answer marked wrong are signals
naming their answers, one person can neither read nor write another's, a refused signal costs
the exchange nothing, and signals are counted by kind and never per person.

**The database half skips when there is no server**, and CI always has one.

Task ids: M16.2.8, M9.2.4
"""

from __future__ import annotations

import ast
import re
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Final, cast

import pytest
from sqlalchemy import DateTime, String, UniqueConstraint, Uuid, text
from sqlalchemy.schema import CreateIndex

from brain.audit.ledger import TRACE_ID
from brain.chat.remember import exchange_of
from brain.chat.thread_store import Exchange, StoredThreads
from brain.chat.turns import CorrectionKind
from brain.db import metadata
from brain.gate.answer import Answered
from brain.gate.context import Channel
from brain.memory.signals import REASK_WINDOW, Observation, Signal
from brain.ops.signal_store import StoredSignals, kept_trace, noticed
from brain.session import make_session_factory
from brain.tables import signal_log as tables
from brain.tables.audit import TRACE_ID_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of
from tests.fixtures.amended_tables import created_ddl
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import ROOT, at_head
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_tables import DIALECT, VERSIONS, migration_module, rendered, squash

MIGRATION: Final = VERSIONS / "0197_signal_log.py"

#: The packages whose modules decide what an answer says, retrieves or remembers.
DECIDING_PACKAGES: Final = ("gate", "memory", "knowledge", "core")

#: The two modules the log lives in.
LOG_MODULES: Final = frozenset({"brain.tables.signal_log", "brain.ops.signal_store"})

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 6, 9, 0, tzinfo=UTC)

DONE: Final = "event: done\ndata: \n\n"


# ------------------------------------------------------------ the migration and the model
def test_the_migration_copies_the_widths_and_grammars_the_models_declare() -> None:
    """A migration may not import live model code, so the widths, the trace grammar and the
    closed vocabulary are copied. Delete this and `0197` can build a column narrower than the
    model writes, or a kind check that refuses a member `Signal` gained."""
    m = migration_module(MIGRATION)
    assert m.SIGNAL_CHARS == tables.SIGNAL_CHARS
    assert m.TRACE_ID_CHARS == TRACE_ID_CHARS
    assert m.PRINCIPAL_ID_CHARS == PRINCIPAL_ID_CHARS
    assert m.TRACE_ID == TRACE_ID
    assert m.SIGNAL_IN == one_of("signal", (one.value for one in Signal)) == tables.SIGNAL_IN
    # Every kind fits the column, measured against the vocabulary rather than the constant.
    assert max(len(one.value) for one in Signal) <= tables.SIGNAL_CHARS


def test_the_migration_builds_the_table_exactly_as_the_model_declares_it() -> None:
    """Compared on rendered DDL, so a width, a nullability, a key or a constraint that differs
    between the model and `0197` is caught. Delete this and the store can write through a model
    describing a table the database never built."""
    up = squash(rendered("upgrade", MIGRATION))
    table = metadata.tables["mem.signal"]
    assert squash(created_ddl(table, DIALECT)) in up
    for index in table.indexes:
        assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in up


def test_the_table_is_secured_by_person_granted_select_and_insert_and_dropped_after() -> None:
    """The table read and written only in the session's own name, SELECT and INSERT alone, and
    its function executable by the application alone. Delete this and a policy reading
    `USING (true)` lets anybody read what everybody re-asked, or an UPDATE grant lets a signal be
    rewritten after the fact."""
    m = migration_module(MIGRATION)
    up = squash(rendered("upgrade", MIGRATION))
    down = squash(rendered("downgrade", MIGRATION))
    assert m.GRANTS == ("GRANT SELECT, INSERT ON mem.signal TO brain_app",)
    assert "brain_fastlane" not in up
    mine = "principal_id = current_setting('app.principal_id', true)"
    assert m.TABLES == ("mem.signal",)
    assert "ALTER TABLE mem.signal ENABLE ROW LEVEL SECURITY" in up
    assert "DROP TABLE mem.signal" in down
    assert up.count(f"USING ({mine})") == 1
    assert up.count(f"WITH CHECK ({mine})") == 1
    assert f"REVOKE EXECUTE ON FUNCTION {m.SIGNAL_COUNTS} FROM PUBLIC" in up
    assert f"GRANT EXECUTE ON FUNCTION {m.SIGNAL_COUNTS} TO brain_app" in up
    assert f"DROP FUNCTION {m.SIGNAL_COUNTS}" in down


def _returned_columns(body: str) -> set[str]:
    """The column names a `RETURNS TABLE (...)` clause declares."""
    found = re.search(r"RETURNS TABLE \((.*?)\)\s*LANGUAGE", body, re.DOTALL)
    assert found is not None
    return {line.split()[0] for line in found.group(1).split(",") if line.strip()}


def test_the_install_wide_read_returns_no_column_a_person_could_come_back_in() -> None:
    """**The enforceable half of `A_COUNT_PER_PERSON_IS_A_PERFORMANCE_REVIEW`, in the database.**
    The function reads past the per-person policy, so what it returns is everything anybody reads
    of other people's rows: a kind and a count. Delete this and a principal column added to it is
    a ranking of who the system fails, with every other test green."""
    m = migration_module(MIGRATION)
    body = m.CREATE_SIGNAL_COUNTS
    assert _returned_columns(body) == {"signal", "noticed"}
    assert "GROUP BY s.signal ORDER BY s.signal" in squash(body)
    assert "SECURITY DEFINER" in body and "STABLE" in body
    assert "SET search_path = pg_catalog, mem" in body
    assert "now()" not in body.lower()


def test_no_column_of_the_signal_table_could_hold_a_sentence() -> None:
    """**`A_SIGNAL_LOG_MUST_NOT_BECOME_A_SECOND_TRANSCRIPT`, held on the table.** The columns are
    exactly a kind, two UUIDs, a trace, a principal and an instant, and the references are typed
    as UUIDs, which refuse words. Delete this and a `question` column, or a text `message_id`,
    makes the log a second copy of what people asked under weaker permissions."""
    table = metadata.tables["mem.signal"]
    assert set(table.columns.keys()) == {
        "id",
        "signal",
        "conversation_id",
        "message_id",
        "trace_id",
        "principal_id",
        "at",
    }
    for name in ("id", "conversation_id", "message_id"):
        assert isinstance(table.columns[name].type, Uuid), name
    assert isinstance(table.columns["at"].type, DateTime)
    for name in ("signal", "trace_id", "principal_id"):
        column_type = table.columns[name].type
        assert isinstance(column_type, String) and column_type.length is not None
        assert column_type.length <= PRINCIPAL_ID_CHARS, name


def test_one_answer_is_one_piece_of_evidence_per_kind() -> None:
    """The unique key `ONE_ANSWER_IS_ONE_PIECE_OF_EVIDENCE_PER_KIND` rests on. Delete this and
    one person clicking "wrong" five times weighs as five people's judgement."""
    unique = {
        tuple(one.columns.keys())
        for one in metadata.tables["mem.signal"].constraints
        if isinstance(one, UniqueConstraint)
    }
    assert unique == {("signal", "message_id")}


def test_nothing_that_decides_an_answer_can_read_the_signal_log() -> None:
    """**A signal is evidence and never an instruction.** No module under the packages that
    decide what an answer retrieves, remembers or says imports the log's table or its store, so a
    re-ask or a correction cannot reorder what the next person is told. Delete this and a boost
    read off one person's corrections can arrive in a diff about something else."""
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
                if set(names) & LOG_MODULES:
                    importing.append(str(path.relative_to(ROOT)))
    assert importing == []
    # The walk is over real packages, so an empty list is not an empty walk.
    assert (ROOT / "src" / "brain" / "gate" / "model_lane.py").exists()


def test_a_trace_outside_the_ledgers_grammar_is_kept_as_no_trace_and_one_inside_it_as_itself() -> (
    None
):
    """`A_TRACE_IS_KEPT_ONLY_IN_THE_LEDGERS_GRAMMAR`. Delete this and a caller's own header,
    words and all, lands on a row that holds no words, or a real trace is dropped."""
    assert kept_trace("chat-0123abcd") == "chat-0123abcd"
    assert kept_trace("how many hours are left") is None
    assert kept_trace("") is None
    assert kept_trace(None) is None
    assert kept_trace("x" * (TRACE_ID_CHARS + 1)) is None


# ------------------------------------------------------------------- the handoff's flag
def _answered(*, escalated: bool = False) -> Answered:
    # A cast at the boundary: `exchange_of` reads these five attributes and nothing else.
    return cast(
        Answered,
        SimpleNamespace(
            frames=("event: text\ndata: An answer.\n\n", DONE),
            from_cache=False,
            provenance=None,
            referred=False,
            escalated=escalated,
        ),
    )


def test_an_exchange_says_whether_its_question_was_handed_to_a_person() -> None:
    """The flag the escalation signal is written from, carried from the answer. Delete this and
    every handoff is kept as an ordinary answer, or every answer as a handoff."""
    policies: dict[str, Any] = {}
    handed = exchange_of("q", _answered(escalated=True), policies)
    answered = exchange_of("q", _answered(escalated=False), policies)
    assert handed is not None and handed.escalated is True
    assert answered is not None and answered.escalated is False


def _handing_on(monkeypatch: pytest.MonkeyPatch, *, declared: bool) -> None:
    """`escalated`'s collaborators stood in: a skill declaring a queue or none, a store that
    files the handoff with nobody named for the queue, and a send that therefore sends nothing."""
    from brain import escalation_routes
    from brain.tables.escalation import EscalationDelivery

    async def no_skills(*args: Any, **kwargs: Any) -> tuple[()]:
        return ()

    async def filed(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(route=None, escalation_id="e1")

    async def not_sent(*args: Any, **kwargs: Any) -> EscalationDelivery:
        return EscalationDelivery.NOT_SENT

    skill = SimpleNamespace(escalate_to="acceptance_queue", name="escalates")
    told = SimpleNamespace(for_asker=lambda: SimpleNamespace(text="Handed on."))
    monkeypatch.setattr(
        escalation_routes, "escalations_of", lambda request: SimpleNamespace(file=filed)
    )
    monkeypatch.setattr(escalation_routes, "offered_skills", no_skills)
    monkeypatch.setattr(
        escalation_routes, "declared_by", lambda skills: skill if declared else None
    )
    monkeypatch.setattr(escalation_routes, "escalation_for", lambda *args, **kwargs: told)
    monkeypatch.setattr(escalation_routes, "handed_on", not_sent)


@pytest.mark.parametrize("declared", (True, False))
def test_an_abstention_handed_to_a_person_says_so_on_the_answer_and_no_other_does(
    monkeypatch: pytest.MonkeyPatch, declared: bool
) -> None:
    """**Where the ESCALATED signal starts** (M16.2.4, M16.2.8). The answer route marks an answer
    it handed on, and only that one: an abstention under a skill that names no queue is the
    abstention it was. Delete this and the exchange a handoff leaves is kept as an ordinary
    answer, so no signal is ever written for it, or every abstention is filed as a handoff."""
    from brain.escalation_routes import escalated
    from brain.gate.abstain import SearchScope, nothing_retrieved

    _handing_on(monkeypatch, declared=declared)
    answered = Answered(frames=(DONE,), abstention=nothing_retrieved(SearchScope()))
    asking = cast(
        Any,
        SimpleNamespace(
            reach=SimpleNamespace(ent_hash=lambda: "0" * 32),
            principal=SimpleNamespace(id=ME, display_name="Asker"),
            now=LONG_AGO,
        ),
    )
    out = run(
        lambda: escalated(
            cast(Any, None),
            answered,
            agent=cast(Any, SimpleNamespace(agent_id="agent_1")),
            asking=asking,
            question="Who signs the lease renewal",
            trace_id="t-handed",
        )
    )
    assert out.escalated is declared
    assert len(out.frames) == (2 if declared else 1)


# --------------------------------------------------------------------------- on a server
ME: Final = "u_signal_me"
SOMEBODY: Final = "u_signal_somebody"
SUBJECT: Final = "Kandang"


@pytest.fixture(scope="module")
def database() -> Iterator[str]:
    with at_head("brain_signal_log") as url:
        yield url


def with_sessions[T](url: str, work: Callable[[Any], Awaitable[T]]) -> T:
    async def go() -> T:
        engine = app_engine(url)
        try:
            return await work(make_session_factory(engine))
        finally:
            await engine.dispose()

    return run(go)


def _exchange(question: str, *, escalated: bool = False) -> Exchange:
    return Exchange(question=question, answer="An answer.", refs=(), escalated=escalated)


def _answers(url: str, thread: str) -> list[str]:
    rows = sql(
        url,
        "SELECT id FROM chat.message WHERE conversation_id = %s AND role = 'assistant'"
        " ORDER BY created_at, id",
        thread,
    )
    return [str(one[0]) for one in rows]


def _signals(url: str, principal: str) -> list[tuple[str, str, str, str | None]]:
    rows = sql(
        url,
        "SELECT signal, conversation_id, message_id, trace_id FROM mem.signal"
        " WHERE principal_id = %s ORDER BY at, signal",
        principal,
    )
    return [(str(a), str(b), str(c), None if d is None else str(d)) for a, b, c, d in rows]


def _asked(
    url: str, principal: str, questions: list[tuple[str, datetime]], *, trace: str = "t-ask"
) -> str:
    """Ask each question in one thread at its instant; the thread."""

    async def work(sessions: Any) -> str:
        store = StoredThreads(sessions)
        thread: str | None = None
        for n, (question, at) in enumerate(questions):
            thread = await store.record(
                principal,
                thread_id=thread,
                channel=Channel.CONSOLE,
                exchange=_exchange(question),
                now=at,
                trace_id=f"{trace}-{n}",
            )
        assert thread is not None
        return thread

    return with_sessions(url, work)


@pytest.mark.needs_db
def test_a_question_asked_again_in_other_words_is_a_signal_naming_the_earlier_answer(
    database: str,
) -> None:
    """**M16.2.1's signal, written where both texts are.** The second question restates the first
    and is kept as one re-ask naming the first answer at the trace it was asked on; the third is
    about something else and is kept as nothing. Delete this and the detector's verdict goes
    nowhere, which is what it did until `0197`, or every follow-up is filed as a complaint."""
    person = f"{ME}_reask"
    first = f"How many hours are left on the {SUBJECT} retainer"
    again = f"What is the remaining hours balance for the {SUBJECT} retainer"
    other = "Who approved the travel invoice last week"
    thread = _asked(
        database,
        person,
        [
            (first, LONG_AGO),
            (again, LONG_AGO + timedelta(minutes=2)),
            (other, LONG_AGO + timedelta(minutes=3)),
        ],
    )
    answers = _answers(database, thread)
    assert _signals(database, person) == [("reasked", thread, answers[0], "t-ask-1")]


@pytest.mark.needs_db
def test_a_restatement_past_the_window_is_a_new_question(database: str) -> None:
    """The window is measured from the answer. Delete this and a related question after lunch is
    filed as evidence that the morning's answer failed."""
    person = f"{ME}_late"
    _asked(
        database,
        person,
        [
            (f"How many hours are left on the {SUBJECT} retainer", LONG_AGO),
            (
                f"What is the remaining hours balance for the {SUBJECT} retainer",
                LONG_AGO + REASK_WINDOW + timedelta(minutes=1),
            ),
        ],
    )
    assert _signals(database, person) == []


@pytest.mark.needs_db
def test_an_exchange_handed_to_a_person_is_a_signal_naming_its_own_answer(database: str) -> None:
    """**M16.2.4's signal.** Delete this and a question nobody could answer is kept in the thread
    and nowhere the learning loop reads; the sibling exchange shows an ordinary answer is none."""
    person = f"{ME}_handed"

    async def work(sessions: Any) -> str:
        store = StoredThreads(sessions)
        thread = await store.record(
            person,
            thread_id=None,
            channel=Channel.CONSOLE,
            exchange=_exchange("What is the parking policy"),
            now=LONG_AGO,
            trace_id="t-plain",
        )
        return await store.record(
            person,
            thread_id=thread,
            channel=Channel.CONSOLE,
            exchange=_exchange("Who signs the lease renewal", escalated=True),
            now=LONG_AGO + timedelta(minutes=1),
            trace_id="t-handed",
        )

    thread = with_sessions(database, work)
    answers = _answers(database, thread)
    assert _signals(database, person) == [("escalated", thread, answers[1], "t-handed")]


@pytest.mark.needs_db
def test_an_answer_marked_wrong_is_a_contradiction_naming_that_answer(database: str) -> None:
    """**M9.2.4 feeding the learning signal.** The correction names the answer it corrects, not
    its own note, and a second mark on the same answer is the same evidence. Delete this and
    "correction handling that feeds the learning signal" feeds nothing."""
    person = f"{ME}_corrects"
    thread = _asked(database, person, [("What is the parking policy", LONG_AGO)])

    async def work(sessions: Any) -> None:
        store = StoredThreads(sessions)
        for kind in (CorrectionKind.WRONG_FACT, CorrectionKind.STALE):
            made = await store.correct(
                person,
                thread,
                kind,
                now=LONG_AGO + timedelta(minutes=1),
                trace_id="t-correct",
            )
            assert made is not None

    with_sessions(database, work)
    [answer] = _answers(database, thread)
    assert _signals(database, person) == [("contradicted", thread, answer, "t-correct")]


@pytest.mark.needs_db
def test_a_person_reads_and_writes_their_own_signals_and_nobody_elses(database: str) -> None:
    """**The database's half of who may read a signal.** Delete this and a policy reading
    `USING (true)` hands one person everything another re-asked and corrected, or a session can
    file a signal against somebody else; the positive half proves the owner still reads theirs."""
    owner, intruder = f"{ME}_owner", f"{SOMEBODY}_intruder"
    thread = _asked(database, owner, [("What is the parking policy", LONG_AGO)])
    [answer] = _answers(database, thread)

    def observation(principal: str) -> Observation:
        return Observation(
            signal=Signal.COPIED,
            conversation_id=thread,
            message_id=answer,
            principal_id=principal,
            at=LONG_AGO,
        )

    async def work(sessions: Any) -> tuple[bool, bool]:
        async with sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.principal_id', :p, true)"), {"p": intruder}
            )
            refused = await noticed(session, observation(owner), trace_id=None)
            # The savepoint rolled back alone: the transaction is still usable.
            kept = await noticed(session, observation(intruder), trace_id=None)
        return refused, kept

    refused, kept = with_sessions(database, work)
    assert (refused, kept) == (False, True)
    mine = with_sessions(database, lambda s: StoredSignals(s).own(owner))
    theirs = with_sessions(database, lambda s: StoredSignals(s).own(intruder))
    assert mine == ()
    assert [(one.signal, one.principal_id) for one in theirs] == [(Signal.COPIED, intruder)]


@pytest.mark.needs_db
def test_signals_are_counted_by_kind_for_the_install_and_never_per_person(database: str) -> None:
    """**`A_COUNT_PER_PERSON_IS_A_PERFORMANCE_REVIEW`, at the store.** A person's own signals may
    be counted by kind and not by principal, and the install's count is by kind alone across
    everybody. Delete this and a reader can be added that ranks people by how often the system
    failed them; the positive half proves counting still works."""
    one, two = f"{ME}_counted_a", f"{ME}_counted_b"
    at = datetime(2019, 6, 1, 9, 0, tzinfo=UTC)
    for person in (one, two):
        _asked(
            database,
            person,
            [
                (f"How many hours are left on the {SUBJECT} retainer", at),
                (
                    f"What is the remaining hours balance for the {SUBJECT} retainer",
                    at + timedelta(seconds=30),
                ),
            ],
        )

    async def per_person(sessions: Any) -> Any:
        return await StoredSignals(sessions).counts_by(one, "principal_id")

    with pytest.raises(ValueError, match="per person"):
        with_sessions(database, per_person)
    with pytest.raises(ValueError, match="not a field"):
        with_sessions(database, lambda s: StoredSignals(s).counts_by(one, "trace_id"))
    assert with_sessions(database, lambda s: StoredSignals(s).counts_by(one, "signal")) == {
        "reasked": 1
    }
    counted = with_sessions(
        database,
        lambda s: StoredSignals(s).counted(
            since=at - timedelta(minutes=1), until=at + timedelta(minutes=1)
        ),
    )
    assert counted == {"reasked": 2}


@pytest.mark.needs_db
def test_the_same_signal_noticed_twice_is_kept_once_and_both_times_said_kept(database: str) -> None:
    """`ONE_ANSWER_IS_ONE_PIECE_OF_EVIDENCE_PER_KIND`, as the writer reports it: a second notice of
    one kind about one answer writes nothing and is not a failure. Delete this and every retried
    request logs a refused signal, which is the noise that hides a real refusal."""
    person = f"{ME}_twice"
    thread = _asked(database, person, [("What is the parking policy", LONG_AGO)])
    [answer] = _answers(database, thread)
    seen = Observation(
        signal=Signal.COPIED,
        conversation_id=thread,
        message_id=answer,
        principal_id=person,
        at=LONG_AGO,
    )

    async def work(sessions: Any) -> tuple[bool, bool]:
        async with sessions() as session, session.begin():
            await session.execute(
                text("SELECT set_config('app.principal_id', :p, true)"), {"p": person}
            )
            first = await noticed(session, seen, trace_id="t-once")
            second = await noticed(session, seen, trace_id="t-twice")
        return first, second

    assert with_sessions(database, work) == (True, True)
    assert _signals(database, person) == [("copied", thread, answer, "t-once")]


@pytest.mark.needs_db
def test_a_question_in_a_thread_that_holds_no_answer_yet_reasks_nothing(database: str) -> None:
    """A thread begun by attaching a document has a note and no answer. Delete this and the first
    question asked in it fails to be kept, because there was no earlier answer to compare."""
    person = f"{ME}_attached"

    async def work(sessions: Any) -> str:
        store = StoredThreads(sessions)
        thread = await store.attach(
            person, thread_id=None, attachment_id="doc_attached_1", now=LONG_AGO
        )
        return await store.record(
            person,
            thread_id=thread,
            channel=Channel.CONSOLE,
            exchange=_exchange("What does the attached handbook say about leave"),
            now=LONG_AGO + timedelta(minutes=1),
            trace_id="t-after-attach",
        )

    thread = with_sessions(database, work)
    assert len(_answers(database, thread)) == 1
    assert _signals(database, person) == []
