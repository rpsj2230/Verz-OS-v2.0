"""The learning signal's log: `0197`, its store and its writers, held to what they refuse to keep.

The first half needs no server. It holds the migration to the models and to the grammars it
copies, holds that no column of either table could hold a sentence and that neither install-wide
function returns a column a person could come back in, holds that nothing deciding an answer
imports the log, and drives the retrieval log's search wrapper over the model lane's own fixtures:
a passage the redactor drops is never kept, and the one it keeps is.

The second half builds PostgreSQL to head and drives the writers as the application role: a
question asking the thread's last one again is a signal naming the earlier answer and one on
another subject is not, an exchange handed to a person and an answer marked wrong are signals
naming their answers, one person can neither read nor write another's, a refused signal costs
the exchange nothing, signals are counted by kind and never per person, and a retrieval is kept
at its trace for its asker and read across the install as a ranking alone.

**The database half skips when there is no server**, and CI always has one.

Task ids: M16.2.8, M15.3.4, M9.2.4
"""

from __future__ import annotations

import ast
import dataclasses
import re
import uuid
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
from brain.gate.model_lane import ModelLane
from brain.knowledge.quality import RETRIEVER_RE, RetrievalEvent
from brain.knowledge.search import CHUNK_ID_CHARS
from brain.memory.signals import REASK_WINDOW, Observation, Signal
from brain.ops.retrieval_log import (
    RETRIEVER,
    LoggedSearch,
    Retrieved,
    StoredRetrievals,
    cited_positions,
    kept_retrieval,
    logging_retrievals,
)
from brain.ops.signal_store import StoredSignals, kept_trace, noticed
from brain.session import make_session_factory
from brain.tables import signal_log as tables
from brain.tables.audit import TRACE_ID_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of
from tests.fixtures.amended_tables import created_ddl
from tests.fixtures.scratch_postgres import run, sql
from tests.unit.test_acceptance import ROOT, at_head
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_model_lane import CALLER, VISIBLE, WITHHELD, Passages
from tests.unit.test_tables import DIALECT, VERSIONS, migration_module, rendered, squash

MIGRATION: Final = VERSIONS / "0197_signal_log.py"

#: The packages whose modules decide what an answer says, retrieves or remembers.
DECIDING_PACKAGES: Final = ("gate", "memory", "knowledge", "core")

#: The three modules the log lives in.
LOG_MODULES: Final = frozenset(
    {"brain.tables.signal_log", "brain.ops.signal_store", "brain.ops.retrieval_log"}
)

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
    assert m.CHUNK_ID_CHARS == CHUNK_ID_CHARS
    assert m.TRACE_ID == TRACE_ID
    assert m.SIGNAL_IN == one_of("signal", (one.value for one in Signal)) == tables.SIGNAL_IN
    assert m.POSITIONS_ARE_INSIDE_WHAT_WAS_RETURNED == tables.POSITIONS_ARE_INSIDE_WHAT_WAS_RETURNED
    # Every kind fits the column, measured against the vocabulary rather than the constant.
    assert max(len(one.value) for one in Signal) <= tables.SIGNAL_CHARS


@pytest.mark.parametrize("qualified", ("mem.signal", "mem.retrieval"))
def test_the_migration_builds_each_table_exactly_as_the_model_declares_it(qualified: str) -> None:
    """Compared on rendered DDL, so a width, a nullability, a key or a constraint that differs
    between the model and `0197` is caught. Delete this and the store can write through a model
    describing a table the database never built."""
    up = squash(rendered("upgrade", MIGRATION))
    table = metadata.tables[qualified]
    assert squash(created_ddl(table, DIALECT)) in up
    for index in table.indexes:
        assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in up


def test_the_tables_are_secured_by_person_granted_select_and_insert_and_dropped_after() -> None:
    """Both tables read and written only in the session's own name, SELECT and INSERT alone,
    and both functions executable by the application alone. Delete this and a policy reading
    `USING (true)` lets anybody read what everybody re-asked, or an UPDATE grant lets a signal be
    rewritten after the fact."""
    m = migration_module(MIGRATION)
    up = squash(rendered("upgrade", MIGRATION))
    down = squash(rendered("downgrade", MIGRATION))
    assert m.GRANTS == (
        "GRANT SELECT, INSERT ON mem.signal TO brain_app",
        "GRANT SELECT, INSERT ON mem.retrieval TO brain_app",
    )
    assert "brain_fastlane" not in up
    mine = "principal_id = current_setting('app.principal_id', true)"
    for table in ("mem.signal", "mem.retrieval"):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in up
        assert f"DROP TABLE {table}" in down
    assert up.count(f"USING ({mine})") == 2
    assert up.count(f"WITH CHECK ({mine})") == 2
    for function in (m.SIGNAL_COUNTS, m.RETRIEVAL_EVENTS):
        assert f"REVOKE EXECUTE ON FUNCTION {function} FROM PUBLIC" in up
        assert f"GRANT EXECUTE ON FUNCTION {function} TO brain_app" in up
        assert f"DROP FUNCTION {function}" in down


def _returned_columns(body: str) -> set[str]:
    """The column names a `RETURNS TABLE (...)` clause declares."""
    found = re.search(r"RETURNS TABLE \((.*?)\)\s*LANGUAGE", body, re.DOTALL)
    assert found is not None
    return {line.split()[0] for line in found.group(1).split(",") if line.strip()}


def test_the_install_wide_reads_return_no_column_a_person_or_a_passage_could_come_back_in() -> None:
    """**The enforceable half of `A_COUNT_PER_PERSON_IS_A_PERFORMANCE_REVIEW`, in the database.**
    The two functions read past the per-person policy, so what they return is everything anybody
    reads of other people's rows: a kind and a count, and a count, positions and a duration.
    Delete this and a principal column added to either is a ranking of who the system fails, or
    a list of which documents one person's reach holds, with every other test green."""
    m = migration_module(MIGRATION)
    assert _returned_columns(m.CREATE_SIGNAL_COUNTS) == {"signal", "noticed"}
    assert _returned_columns(m.CREATE_RETRIEVAL_EVENTS) == {"returned", "used", "latency_ms"}
    assert "GROUP BY s.signal ORDER BY s.signal" in squash(m.CREATE_SIGNAL_COUNTS)
    for body in (m.CREATE_SIGNAL_COUNTS, m.CREATE_RETRIEVAL_EVENTS):
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
    retrieval = metadata.tables["mem.retrieval"]
    assert set(retrieval.columns.keys()) == {
        "id",
        "trace_id",
        "principal_id",
        "chunk_ids",
        "used",
        "latency_ms",
        "at",
    }


def test_one_answer_is_one_piece_of_evidence_per_kind_and_one_retrieval_per_trace() -> None:
    """The unique keys `ONE_ANSWER_IS_ONE_PIECE_OF_EVIDENCE_PER_KIND` rests on. Delete this and
    one person clicking "wrong" five times weighs as five people's judgement."""
    signal, retrieval = (
        {
            tuple(one.columns.keys())
            for one in metadata.tables[table].constraints
            if isinstance(one, UniqueConstraint)
        }
        for table in ("mem.signal", "mem.retrieval")
    )
    assert signal == {("signal", "message_id")}
    assert retrieval == {("trace_id",)}


def test_nothing_that_decides_an_answer_can_read_the_signal_log() -> None:
    """**A signal is evidence and never an instruction.** No module under the packages that
    decide what an answer retrieves, remembers or says imports the log's table or either store,
    so a re-ask or a retrieval cannot reorder what the next person is told. Delete this and a
    boost read off one person's retrievals can arrive in a diff about something else, which is
    what `brain.knowledge.quality` rejected."""
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


# ------------------------------------------------------------------- the retrieval log, pure
def test_a_search_keeps_the_passages_the_model_is_shown_and_never_one_the_redactor_dropped() -> (
    None
):
    """**`A_RETRIEVAL_KEEPS_ONLY_WHAT_THE_MODEL_WAS_SHOWN`.** The model lane's own fixtures: the
    caller may read the handbook's passage and not the quarantined one. Delete this and the log
    keeps the id of a passage the caller was never shown, which is a record of what they could
    not see; the positive half proves the wrapper is not keeping nothing."""
    kept = Retrieved()
    search = LoggedSearch(inner=Passages(VISIBLE, WITHHELD), kept=kept)
    found = run(lambda: search.passages("leave", entitlement=CALLER, now=LONG_AGO))
    assert [one.id for one in found.records] == [VISIBLE.id, WITHHELD.id]
    assert kept.chunk_ids == (VISIBLE.id,)
    assert kept.latency_ms >= 0


def test_the_first_search_of_a_request_is_its_retrieval() -> None:
    """A second search at the same trace does not replace the first. Delete this and a lane that
    searched twice keeps whichever ran last, which is not the list the answer was drawn from."""
    kept = Retrieved()
    run(
        lambda: LoggedSearch(inner=Passages(VISIBLE), kept=kept).passages(
            "leave", entitlement=CALLER, now=LONG_AGO
        )
    )
    run(
        lambda: LoggedSearch(inner=Passages(), kept=kept).passages(
            "leave", entitlement=CALLER, now=LONG_AGO
        )
    )
    assert kept.chunk_ids == (VISIBLE.id,)


def test_no_model_step_logs_nothing_and_a_model_step_has_its_search_wrapped() -> None:
    """Delete this and a process with no model gains a lane, or the lane's search is not the
    one that notes what it returned."""
    kept = Retrieved()
    assert logging_retrievals(None, kept) is None
    # No model is asked here, so none is given: the wrapper reads only the search.
    lane = ModelLane(search=Passages(VISIBLE), model=cast(Any, None))
    wrapped = logging_retrievals(lane, kept)
    assert wrapped is not None and isinstance(wrapped.search, LoggedSearch)
    assert wrapped.search.inner is lane.search
    assert wrapped.search.kept is kept
    assert dataclasses.replace(wrapped, search=lane.search) == lane


def _evidence(view: dict[str, str]) -> Any:
    return SimpleNamespace(view=lambda: view)


def _answered(*documents: Any, escalated: bool = False) -> Answered:
    provenance = SimpleNamespace(documents=documents) if documents else None
    return cast(
        Answered,
        SimpleNamespace(
            frames=("event: text\ndata: An answer.\n\n", DONE),
            from_cache=False,
            provenance=provenance,
            referred=False,
            escalated=escalated,
        ),
    )


def test_the_positions_kept_are_those_of_the_passages_the_answer_cited() -> None:
    """Read from the answer's own document evidence by the chunk each anchor names. Delete this
    and the ranking signal reads every answer as unused, or as used at the wrong place."""
    cited = _evidence({"kind": "document", "document_id": "d1", "anchor": "chunk=c3&x=1"})
    row = _evidence({"kind": "record", "entity": "client", "record_id": "c1", "field": "f"})
    assert cited_positions(("c1", "c2", "c3"), _answered(cited, row)) == (3,)
    assert cited_positions(("c1", "c2"), _answered(cited)) == ()
    assert cited_positions(("c1",), _answered()) == ()
    # The positions are a record quality accepts: sorted, one-based, inside what was returned.
    event = RetrievalEvent(retrievers=(RETRIEVER,), returned=3, used=(3,))
    assert event.first_used_position == 3
    assert RETRIEVER_RE.match(RETRIEVER)


def test_an_exchange_says_whether_its_question_was_handed_to_a_person() -> None:
    """The flag the escalation signal is written from, carried from the answer. Delete this and
    every handoff is kept as an ordinary answer, or every answer as a handoff."""
    policies: dict[str, Any] = {}
    handed = exchange_of("q", _answered(escalated=True), policies)
    answered = exchange_of("q", _answered(escalated=False), policies)
    assert handed is not None and handed.escalated is True
    assert answered is not None and answered.escalated is False


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


def _retrieved(url: str, principal: str, trace: str, ids: tuple[str, ...] | None) -> bool:
    cited = _evidence({"kind": "document", "document_id": "d", "anchor": "chunk=c2"})
    return with_sessions(
        url,
        lambda s: kept_retrieval(
            s,
            trace_id=trace,
            principal_id=principal,
            retrieved=Retrieved(chunk_ids=ids, latency_ms=12),
            answered=_answered(cited),
            now=datetime(2019, 7, 1, 9, 0, tzinfo=UTC),
        ),
    )


@pytest.mark.needs_db
def test_a_retrieval_is_kept_at_its_trace_for_its_asker_and_read_by_the_install_as_a_ranking(
    database: str,
) -> None:
    """**M15.3.4, and `THE_INSTALL_READS_A_RETRIEVAL_AS_A_RANKING_AND_ITS_ASKER_AS_IDS`.** The
    asker reads the ids and the cited position back at the trace, somebody else reads nothing
    there, and the install reads a `RetrievalEvent` with no id in it. Delete this and the log can
    go unwritten, or be read by anybody, with the arithmetic over it still green."""
    trace = f"t-retrieval-{uuid.uuid4().hex[:8]}"
    assert _retrieved(database, ME, trace, ("c1", "c2", "c3"))
    # One retrieval per trace: a second write there keeps the first and fails nothing.
    assert _retrieved(database, ME, trace, ("c9",))
    mine = with_sessions(database, lambda s: StoredRetrievals(s).at_trace(ME, trace))
    assert mine is not None and (mine.chunk_ids, mine.used) == (("c1", "c2", "c3"), (2,))
    assert with_sessions(database, lambda s: StoredRetrievals(s).at_trace(SOMEBODY, trace)) is None
    events = with_sessions(
        database,
        lambda s: StoredRetrievals(s).events(
            since=datetime(2019, 6, 30, tzinfo=UTC), until=datetime(2019, 7, 2, tzinfo=UTC)
        ),
    )
    assert RetrievalEvent(retrievers=(RETRIEVER,), returned=3, used=(2,), latency_ms=12) in events


@pytest.mark.needs_db
def test_a_question_that_searched_nothing_keeps_nothing_and_one_that_found_nothing_is_kept(
    database: str,
) -> None:
    """A fast-lane answer searched nothing; a search that found nothing is the evidence knowledge
    gaps are read from. Delete this and either every fast-lane answer looks like an empty search,
    or the questions nothing could answer are the ones the log forgets."""
    assert not _retrieved(database, ME, "t-searched-nothing", None)
    assert not _retrieved(database, ME, "not a trace at all", ("c1",))
    assert _retrieved(database, ME, "t-found-nothing", ())
    empty = with_sessions(database, lambda s: StoredRetrievals(s).at_trace(ME, "t-found-nothing"))
    assert empty is not None and empty.chunk_ids == ()
    assert (
        with_sessions(database, lambda s: StoredRetrievals(s).at_trace(ME, "t-searched-nothing"))
        is None
    )


@pytest.mark.needs_db
def test_a_cited_position_past_the_passages_returned_is_refused_by_the_database(
    database: str,
) -> None:
    """The table's own `used_inside_returned`, which `RetrievalEvent` holds in Python. Delete
    this and a position of something the caller was never shown can be written by any writer
    that skips the dataclass."""
    import psycopg

    with pytest.raises(psycopg.errors.CheckViolation):
        sql(
            database,
            "INSERT INTO mem.retrieval (trace_id, principal_id, chunk_ids, used, latency_ms, at)"
            " VALUES ('t-past-the-end', 'u', ARRAY['c1'], ARRAY[2]::smallint[], 1, now())",
        )
    sql(
        database,
        "INSERT INTO mem.retrieval (trace_id, principal_id, chunk_ids, used, latency_ms, at)"
        " VALUES ('t-inside', 'u', ARRAY['c1'], ARRAY[1]::smallint[], 1, now())",
    )


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


@pytest.mark.needs_db
def test_an_id_no_passage_carries_keeps_no_retrieval_and_fails_nothing(database: str) -> None:
    """A live source can hand back an id longer than a passage id. Delete this and that id is
    sent to a column that refuses it, which is an error on the answer path rather than a log."""
    assert not _retrieved(database, ME, "t-overlong", ("c" * (CHUNK_ID_CHARS + 1),))
    assert not _retrieved(database, ME, "t-unnamed", ("",))
    assert with_sessions(database, lambda s: StoredRetrievals(s).at_trace(ME, "t-overlong")) is None


def test_a_retrieval_that_cannot_be_kept_never_fails_the_answer() -> None:
    """`A_SIGNAL_NEVER_COSTS_THE_PERSON_THEIR_TRANSCRIPT`, for the retrieval log: a database that
    cannot be reached is logged and the answer goes out. Delete this and a retrieval write that
    fails turns a good answer into a fault."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from brain.api_routes import retrieval_logged

    async def go() -> None:
        # Nothing listens on port one, so the connection is refused at once.
        engine = create_async_engine("postgresql+psycopg://nobody@127.0.0.1:1/none")
        try:
            await retrieval_logged(
                SimpleNamespace(db_sessions=async_sessionmaker(engine)),
                trace_id="t-unreachable",
                principal_id=ME,
                retrieved=Retrieved(chunk_ids=("c1",)),
                answered=_answered(),
                now=LONG_AGO,
            )
        finally:
            await engine.dispose()

    run(go)
