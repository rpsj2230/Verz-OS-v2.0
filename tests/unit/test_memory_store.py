"""An undo and an edit reach their rows and the ledger, and the next recall reads them.

`tests/unit/test_estate_routes.py` holds who may undo a learning and what the screens say, over the
real store and a stub session. This file holds everything below that. The first half needs no
server: it reads `0061` as the SQL it renders, holds the trigger's subject and details to
`AuditRecorder.memory`'s, holds the migration's copied grammars to the models', and drives the store
over a stub session to prove the order an undo and an edit are written in, which is the whole of
`brain.ops.memory_store.AN_UNDO_IS_DECIDED_UNDER_THE_LOCK_IT_IS_WRITTEN_UNDER`.

The second half builds a database through `0061` and follows an undo to the three places
`docs/admin-console.md` names for a control: the correction row, the ledger entry its trigger
appends under the request's trace, and the behaviour, which is what `brain.memory.recall.recall`
returns from the rows loaded afterwards. **It skips when there is no server**; CI always has one.

The fixtures' instants are 2019 and far from any wall clock, for CLAUDE.md's reason, and every
recall is asked at an instant an hour after them, so nothing here decays on a schedule.

Task ids: M27.7.21, M27.7.22
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateTable

from brain.agents.model import AGENT_ID_CHARS
from brain.audit.ledger import IDENTIFIER, AuditChain, AuditEntry
from brain.audit.record import AuditRecorder, MemoryChange
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.db import metadata
from brain.memory.correction import Correction, Demotion, Supersession
from brain.memory.digest import Learning
from brain.memory.formation import Formation, MemoryKind
from brain.memory.recall import recall
from brain.memory.review import Edit
from brain.memory.signals import Signal
from brain.memory.tiers import Change, propose
from brain.ops.memory_store import (
    REVISION_LOCK_CLASS,
    Corrections,
    MemoryRecords,
    StoredMemoryRecords,
    correction_row,
    corrections_naming,
    corrections_of,
    learning_row,
    lock_on,
    memory_row,
)
from brain.session import make_session_factory
from brain.tables import learning as table_module
from brain.tables.identity import PRINCIPAL_ID_CHARS
from brain.tables.learning import CorrectionRow
from brain.tables.memory import AdaptiveMemoryRow, PersistentMemoryRow
from tests.fixtures.retirable import has_pgvector, retirable
from tests.fixtures.scratch_postgres import add_modelled, migrate, run, sql
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_tables import VERSIONS, migration_module, rendered, squash

DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

MIGRATION: Final = VERSIONS / "0061_learning_and_correction.py"

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
LATER: Final = LONG_AGO + timedelta(hours=1)

CLIENT_NAME: Final = Capability(value="read:client.name")

#: The lock the ledger's own append takes, which a revision's lock must never be.
LEDGER_LOCK: Final = 8274419004


def recorder() -> AuditRecorder:
    return AuditRecorder(
        AuditChain(), actor_id="u_admin", ent_hash="0" * 32, trace_id="t", clock=lambda: LONG_AGO
    )


def compiled(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=DIALECT)).split())


def formation(
    *, kind: MemoryKind = MemoryKind.ADAPTIVE, at: datetime = LONG_AGO, principal: str = "u_subject"
) -> Formation:
    return Formation(
        principal_id=principal,
        capabilities=(CLIENT_NAME,),
        scope=Scope.department("web"),
        ent_hash="e" * 32,
        formed_at=at,
        kind=kind,
    )


def learning(
    memory_id: str,
    *,
    replaced_id: str | None = None,
    kind: MemoryKind = MemoryKind.ADAPTIVE,
    at: datetime = LONG_AGO,
) -> Learning:
    return Learning(
        memory_id=memory_id,
        proposal=propose(Change.PREFERENCE, subject="answer.length"),
        formation=formation(kind=kind, at=at),
        evidence=frozenset({Signal.REASKED}),
        formed_confidence=0.9,
        replaced_id=replaced_id,
        agent_id="desk",
    )


# ------------------------------------------------------------ the migration and the model


def test_the_trigger_writes_the_subject_actor_and_details_the_recorder_writes() -> None:
    """Delete this and the entry a deployed database keeps and the entry `AuditRecorder` writes
    for a chain held anywhere else can come apart without a server to notice: a trigger that put
    the memory that replaced it, or anything of a statement, into the details would pass every
    stubbed test. The body is read off the migration module that executes it."""
    superseded = recorder().memory(memory_id="m_1", change=MemoryChange.SUPERSEDED)
    demoted = recorder().memory(memory_id="m_1", change=MemoryChange.DEMOTED)
    body = " ".join(migration_module(MIGRATION).CORRECTION_TRIGGER_FUNCTION.split())

    assert superseded.subject == "memory:m_1"
    assert (superseded.details, demoted.details) == (
        {"change": "superseded"},
        {"change": "demoted"},
    )
    assert "v_subject text := 'memory:' || NEW.memory_id;" in body
    assert "v_details jsonb := jsonb_build_object('change', NEW.correction);" in body
    assert "v_seq, v_at, NEW.recorded_by, 'memory', v_subject, v_ent_hash," in body
    assert "by_id" not in body and "field" not in body and "prompted_by" not in body
    assert "AFTER INSERT ON mem.correction" in " ".join(
        migration_module(MIGRATION).CORRECTION_TRIGGER.split()
    )


def test_the_recorders_change_words_are_the_corrections_own_words() -> None:
    """`MemoryChange` restates `Correction` because the audit package may not import the memory
    plane. Delete this and one can gain or rename a member alone, after which the trigger writes a
    word the recorder has no member for."""
    assert {one.value for one in MemoryChange} == {one.value for one in Correction}


def test_the_migration_holds_the_live_grammars_widths_and_predicates_it_copied() -> None:
    """`0061` copies the widths, the identifier grammar and three generated predicates for the
    reason `0009` gives. Delete this and one side can change alone: a tier the table admits and
    `Proposal` refuses, or an actor the ledger cannot record."""
    migration = migration_module(MIGRATION)

    assert migration.MEMORY_ID_CHARS == table_module.MEMORY_ID_CHARS
    for stored in (PersistentMemoryRow, AdaptiveMemoryRow):
        assert getattr(stored.__table__.c.id.type, "length", None) == migration.MEMORY_ID_CHARS
    assert migration.CHANGE_CHARS == table_module.CHANGE_CHARS
    assert migration.SIGNAL_CHARS == table_module.SIGNAL_CHARS
    assert migration.SUBJECT_CHARS == table_module.SUBJECT_CHARS
    assert migration.CORRECTION_CHARS == table_module.CORRECTION_CHARS
    assert migration.AGENT_ID_CHARS == AGENT_ID_CHARS
    assert migration.PRINCIPAL_ID_CHARS == PRINCIPAL_ID_CHARS
    assert migration.IDENTIFIER == IDENTIFIER
    assert table_module.change_needs_its_tier() == migration.CHANGE_NEEDS_ITS_TIER
    assert table_module.evidence_is_signals() == migration.EVIDENCE_IS_SIGNALS
    assert (
        table_module.a_correction_has_its_kinds_shape()
        == migration.A_CORRECTION_HAS_ITS_KINDS_SHAPE
    )
    assert max(len(one.value) for one in Change) <= table_module.CHANGE_CHARS
    assert max(len(one.value) for one in Signal) <= table_module.SIGNAL_CHARS
    assert max(len(one.value) for one in Correction) <= table_module.CORRECTION_CHARS


def test_the_tier_predicate_names_every_change_once_at_the_tier_its_reach_needs() -> None:
    """Held against `brain.memory.tiers.propose`, which is the constructor that cannot lower a tier,
    rather than against `BLAST_RADIUS` the predicate is generated from. Delete this and a generator
    that dropped a change, or paired a gated change with tier one, renders a constraint that admits
    a scope widening as automatic."""
    predicate = table_module.change_needs_its_tier()

    for change in Change:
        assert (
            f"(change = '{change.value}' AND tier = {int(propose(change, subject='x').tier)})"
            in (predicate)
        )
    assert predicate.count("(change = ") == len(Change)


def test_the_migration_builds_both_tables_and_their_indexes_as_the_models_declare_them() -> None:
    """Compared as rendered DDL, for the reason `test_tables` compares 0002's. Delete this and a
    model can gain a column or lose a constraint with the database built the old way."""
    emitted = squash(rendered("upgrade", MIGRATION))

    for qualified in ("mem.learning", "mem.correction"):
        mapped = metadata.tables[qualified]
        assert squash(str(CreateTable(mapped).compile(dialect=DIALECT))) in emitted
        for index in mapped.indexes:
            assert squash(str(CreateIndex(index).compile(dialect=DIALECT))) in emitted


def test_the_application_may_read_and_add_to_both_tables_and_nothing_else() -> None:
    """Row-level security on both, SELECT and INSERT granted, and no UPDATE or DELETE anywhere.
    Delete this and a grant widened to UPDATE lets the application rewrite a correction in place,
    which is the one change that makes what the system used to recall unexplainable."""
    emitted = squash(rendered("upgrade", MIGRATION))
    grants = [line for line in emitted.split(";") if "GRANT" in line]

    for qualified in ("mem.learning", "mem.correction"):
        assert f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY" in emitted
        assert f"GRANT SELECT, INSERT ON {qualified} TO brain_app" in emitted
    assert grants
    assert all("UPDATE" not in one and "DELETE" not in one for one in grants)


# ------------------------------------------------------------------------ the store


class _Result:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one(self) -> Any:
        return self._value

    def scalars(self) -> _Result:
        return self

    def all(self) -> Any:
        return self._value


class _Session:
    """An `AsyncSession` in the shape the store uses, noting each statement and what it wrote.

    A SELECT from `mem.correction` is answered `marks`, and the clock is answered `LATER`.
    """

    def __init__(self, log: list[str], marks: list[Any], written: list[dict[str, Any]]) -> None:
        self.log = log
        self.marks = marks
        self.written = written

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def begin(self) -> _Transaction:
        return _Transaction(self.log)

    async def execute(self, statement: Any, *_: Any, **__: Any) -> _Result:
        text = compiled(statement)
        params = statement.compile().params
        if "set_config" in text:
            self.log.append(f"set {params['name']}")
            return _Result(None)
        if "pg_advisory_xact_lock" in text:
            self.log.append(f"lock {params['lock_class']} {params['memory_id']}")
            return _Result(None)
        if text.startswith("SELECT now()"):
            self.log.append("clock")
            return _Result(LATER)
        if text.startswith("SELECT") and "FROM mem.correction" in text:
            self.log.append("read marks")
            return _Result(self.marks)
        if text.startswith("INSERT INTO"):
            table = text.split(" ")[2]
            self.log.append(f"insert {table}")
            self.written.append({"table": table, **params})
            return _Result(None)
        raise AssertionError(f"the store sent a statement nothing expected: {text}")


class _Transaction:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def __aenter__(self) -> None:
        self.log.append("BEGIN")

    async def __aexit__(self, kind: object, *_: object) -> None:
        self.log.append("ROLLBACK" if kind is not None else "COMMIT")


def store_over(
    log: list[str], written: list[dict[str, Any]], marks: list[Any] | None = None
) -> StoredMemoryRecords:
    return StoredMemoryRecords(lambda: _Session(log, marks or [], written))  # type: ignore[arg-type]


def stored_mark(correction: Supersession | Demotion) -> CorrectionRow:
    """A correction as `mem.correction` would hand it back."""
    if isinstance(correction, Supersession):
        return CorrectionRow(
            memory_id=correction.superseded_id,
            correction=Correction.SUPERSEDED.value,
            by_id=correction.by_id,
            prompted_by=correction.prompted_by.value,
            field=None,
            recorded_by="u_earlier",
            at=correction.at,
        )
    return CorrectionRow(
        memory_id=correction.memory_id,
        correction=Correction.DEMOTED.value,
        by_id=None,
        prompted_by=None,
        field=correction.field,
        recorded_by="u_earlier",
        at=correction.at,
    )


def test_the_database_store_is_a_memory_records() -> None:
    """Delete this and the route's `isinstance` check on `app.state.memory_records` can stop
    recognising the store it builds for itself, and the fault is a 500 on the first undo."""
    assert isinstance(StoredMemoryRecords(lambda: None), MemoryRecords)  # type: ignore[arg-type]


def test_an_undo_locks_the_memory_reads_its_marks_and_the_clock_then_writes_one_correction() -> (
    None
):
    """`AN_UNDO_IS_DECIDED_UNDER_THE_LOCK_IT_IS_WRITTEN_UNDER`, as the order of statements. The lock
    comes before the read so a second undo waits for the first; the clock is the database's and is
    read inside the transaction; the trace and reach are set before the insert so the trigger
    attributes the entry; and one transaction commits once. Delete this and any of those can move
    with every route test still green."""
    log: list[str] = []
    written: list[dict[str, Any]] = []

    undone = run(
        lambda: store_over(log, written).undo(
            learning("m_learnt"), actor="u_admin", trace_id="t", ent_hash="e" * 32
        )
    )

    assert log == [
        "BEGIN",
        f"lock {REVISION_LOCK_CLASS} m_learnt",
        "read marks",
        "clock",
        "set brain.trace_id",
        "set brain.ent_hash",
        "insert mem.correction",
        "COMMIT",
    ]
    assert undone.took_effect
    assert written == [
        {
            "table": "mem.correction",
            "memory_id": "m_learnt",
            "correction": "demoted",
            "by_id": None,
            "prompted_by": None,
            "field": "answer.length",
            "recorded_by": "u_admin",
            "at": LATER,
        }
    ]


def test_an_undo_of_a_learning_that_replaced_a_memory_writes_a_supersession_by_that_memory() -> (
    None
):
    """The restoring half of `digest.undo`, written as the table holds it: the learning marked, the
    memory it replaced named as what takes its place, a person's refusal as the signal. Delete this
    and the store can write the supersession the other way round, which marks the memory the undo
    meant to put back."""
    log: list[str] = []
    written: list[dict[str, Any]] = []

    run(
        lambda: store_over(log, written).undo(
            learning("m_learnt", replaced_id="m_before"),
            actor="u_admin",
            trace_id="t",
            ent_hash="e" * 32,
        )
    )

    assert written == [
        {
            "table": "mem.correction",
            "memory_id": "m_learnt",
            "correction": "superseded",
            "by_id": "m_before",
            "prompted_by": "rejected",
            "field": None,
            "recorded_by": "u_admin",
            "at": LATER,
        }
    ]


def test_a_second_undo_reads_the_first_ones_correction_and_writes_nothing() -> None:
    """The first undo's row is what the second reads under the lock, and nothing is inserted, no
    trace is set and the result says nothing was done. Delete this and a double click writes a
    second correction, which on a pair is the latest word and can reverse the first."""
    log: list[str] = []
    written: list[dict[str, Any]] = []
    first = Demotion(memory_id="m_learnt", field="answer.length", at=LONG_AGO)

    again = run(
        lambda: store_over(log, written, [stored_mark(first)]).undo(
            learning("m_learnt"), actor="u_admin", trace_id="t", ent_hash="e" * 32
        )
    )

    assert not again.took_effect
    assert written == []
    assert log == [
        "BEGIN",
        f"lock {REVISION_LOCK_CLASS} m_learnt",
        "read marks",
        "clock",
        "COMMIT",
    ]


def test_an_edit_writes_the_replacement_its_learning_record_and_the_supersession_together() -> None:
    """Three rows in one transaction, the memory first and the mark last, the learning record naming
    what the replacement replaced. Delete this and an edit can write its supersession without the
    replacement, which marks a memory as replaced by something nobody wrote."""
    log: list[str] = []
    written: list[dict[str, Any]] = []
    original = learning("m_original", kind=MemoryKind.PERSISTENT)
    replacement = learning(
        "m_edited", replaced_id="m_original", kind=MemoryKind.PERSISTENT, at=LATER
    )

    edited = run(
        lambda: store_over(log, written).edit(
            original,
            replacement,
            "Prefers the short answer.",
            prompted_by=Signal.CONTRADICTED,
            actor="u_subject",
            trace_id="t",
            ent_hash="e" * 32,
        )
    )

    assert isinstance(edited, Edit) and edited.took_effect
    assert log == [
        "BEGIN",
        f"lock {REVISION_LOCK_CLASS} m_original",
        "read marks",
        "clock",
        "set brain.trace_id",
        "set brain.ent_hash",
        "insert mem.persistent",
        "insert mem.learning",
        "insert mem.correction",
        "COMMIT",
    ]
    memory, record, mark = written
    assert (memory["id"], memory["statement"], memory["kind"]) == (
        "m_edited",
        "Prefers the short answer.",
        "persistent",
    )
    assert (record["memory_id"], record["replaced_id"], record["tier"]) == (
        "m_edited",
        "m_original",
        1,
    )
    assert (mark["memory_id"], mark["by_id"], mark["prompted_by"], mark["at"]) == (
        "m_original",
        "m_edited",
        "contradicted",
        LATER,
    )


def test_an_edit_of_a_memory_already_marked_writes_nothing() -> None:
    """The sibling of the one above. Delete this and an edit pressed after an undo writes a
    replacement for a memory nobody recalls any more."""
    log: list[str] = []
    written: list[dict[str, Any]] = []
    marked = Demotion(memory_id="m_original", field="answer.length", at=LONG_AGO)

    edited = run(
        lambda: store_over(log, written, [stored_mark(marked)]).edit(
            learning("m_original"),
            learning("m_edited", replaced_id="m_original", at=LATER),
            "Prefers the short answer.",
            prompted_by=Signal.CONTRADICTED,
            actor="u_subject",
            trace_id="t",
            ent_hash="e" * 32,
        )
    )

    assert not edited.took_effect
    assert written == []


def test_the_statements_read_both_sides_of_a_pair_and_the_lock_is_not_the_ledgers() -> None:
    """The marks are read by the memory marked and by the memory named as its replacement, because
    an undo that restores a memory is a supersession by it; and the lock takes two keys and a class
    of its own. Delete this and the read can lose one column, after which a memory an undo put back
    reads as still marked, or the lock can become the ledger's and deadlock against the trigger."""
    marks = compiled(corrections_naming(("m_1",)))
    lock = lock_on("m_1")

    assert "WHERE mem.correction.memory_id IN" in marks
    assert "OR mem.correction.by_id IN" in marks
    assert "ORDER BY mem.correction.at, mem.correction.id" in marks
    assert "pg_advisory_xact_lock(%(lock_class)s::INTEGER, hashtext(%(memory_id)s::VARCHAR))" in (
        compiled(lock)
    )
    assert lock.compile().params == {"lock_class": REVISION_LOCK_CLASS, "memory_id": "m_1"}
    assert LEDGER_LOCK not in lock.compile().params.values()


def test_the_rows_an_undo_and_an_edit_write_carry_no_statement_but_the_memorys_own() -> None:
    """A correction row and a learning row are built from the domain's values and carry no text,
    and the memory row carries the one statement a person wrote. Delete this and a column holding
    what was said can be added to the correction log, which is the transcript
    `brain.memory.correction` refuses to keep."""
    mark = correction_row(
        Supersession(superseded_id="m_1", by_id="m_2", prompted_by=Signal.REJECTED, at=LONG_AGO),
        "u_admin",
    )
    record = learning_row(learning("m_2", replaced_id="m_1"))
    written = memory_row(learning("m_2"), "Prefers the short answer.")

    assert set(mark.compile().params) == {
        "memory_id",
        "correction",
        "by_id",
        "prompted_by",
        "field",
        "recorded_by",
        "at",
    }
    assert "statement" not in record.compile().params
    assert written.compile().params["statement"] == "Prefers the short answer."
    assert written.compile().params["formed_confidence"] == 0.9
    with pytest.raises(ValueError, match="neither memory table"):
        memory_row(learning("m_3", kind=MemoryKind.SESSION), "x")


def test_a_correction_row_the_domain_refuses_is_skipped_and_a_good_one_is_kept() -> None:
    """A supersession naming itself as its replacement is on disk only if written round the table's
    constraint, and it is skipped rather than failing every screen that reads corrections. Delete
    this and the skip can widen to every row, after which no undo changes what is recalled."""
    good = stored_mark(Supersession("m_1", "m_2", Signal.REJECTED, LONG_AGO))
    looped = stored_mark(Supersession("m_3", "m_4", Signal.REJECTED, LONG_AGO))
    looped.by_id = "m_3"
    demoted = stored_mark(Demotion(memory_id="m_5", field="answer.length", at=LONG_AGO))

    found = corrections_of([good, looped, demoted])

    assert found == Corrections(
        supersessions=(Supersession("m_1", "m_2", Signal.REJECTED, LONG_AGO),),
        demotions=(Demotion(memory_id="m_5", field="answer.length", at=LONG_AGO),),
    )


# ---------------------------------------------------------------- through a real database


@contextmanager
def through_0061(database: str) -> Iterator[str]:
    """A database with `0061` applied and both memory tables present.

    Without pgvector, `retirable` stops at `0048`; `0049` is run for real, then the migrations
    that build the tables `0059` and `0060` put triggers and constraints on, out of order and
    each after a stamp of its predecessor, as `tests/unit/test_console_control_audit.py` runs
    them: `0014` and `0016` for the agent and its install, `0025` and `0030` for the control run
    and its names, and `0053` for the webhook changes. `0054` to `0061` then run in order. `0018`
    is stamped on that chain, so the two memory tables are built from the models and granted to
    the application as `0018` grants them."""
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
            migrate(database, "upgrade", "0061")
            add_modelled(url, ("mem.persistent", "mem.adaptive"))
            sql(url, "GRANT SELECT, INSERT ON mem.persistent, mem.adaptive TO brain_app")
        yield url


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


def seed(url: str) -> None:
    """Three memories and two learnings: `m_before` a person stated, `m_learnt` the agent inferred
    in its place, with the supersession that marked `m_before`, and `m_alone` inferred from nothing.
    """
    scope = '{"clauses": [{"field": "department", "op": "eq", "value": "web"}]}'
    sql(
        url,
        "INSERT INTO mem.persistent (id, principal_id, statement, capability_tags, scope,"
        " ent_hash, kind, formed_at) VALUES ('m_before', 'u_subject', %s,"
        " ARRAY['read:client.name'], %s::jsonb, repeat('e', 32), 'persistent', %s)",
        "Prefers the long answer.",
        scope,
        LONG_AGO,
    )
    for memory_id, statement in (
        ("m_learnt", "Prefers the short answer."),
        ("m_alone", "Asks on Mondays."),
    ):
        sql(
            url,
            "INSERT INTO mem.adaptive (id, principal_id, statement, capability_tags, scope,"
            " ent_hash, kind, formed_confidence, formed_at) VALUES (%s, 'u_subject', %s,"
            " ARRAY['read:client.name'], %s::jsonb, repeat('e', 32), 'adaptive', 0.9, %s)",
            memory_id,
            statement,
            scope,
            LONG_AGO + timedelta(minutes=5),
        )
    sql(
        url,
        "INSERT INTO mem.learning (memory_id, change, tier, subject, agent_id, replaced_id,"
        " evidence) VALUES"
        " ('m_learnt', 'preference', 1, 'answer.length', 'desk', 'm_before', '{reasked}'),"
        " ('m_alone', 'preference', 1, 'answer.day', 'desk', NULL, '{}')",
    )
    sql(
        url,
        "INSERT INTO mem.correction (memory_id, correction, by_id, prompted_by, recorded_by, at)"
        " VALUES ('m_before', 'superseded', 'm_learnt', 'contradicted', 'u_seed', %s)",
        LONG_AGO + timedelta(minutes=5),
    )


def recalled_now(url: str) -> list[str]:
    """What recall returns for a reader holding the memories' capability in web, from the rows as
    the application reads them now."""
    stated = sql(url, "SELECT id, formed_at FROM mem.persistent")
    inferred = sql(url, "SELECT id, formed_at, formed_confidence FROM mem.adaptive")
    marks = sql(
        url,
        "SELECT memory_id, correction, by_id, prompted_by, field, recorded_by, at"
        " FROM mem.correction",
    )
    memories = [learning(one[0], kind=MemoryKind.PERSISTENT, at=one[1]) for one in stated] + [
        learning(one[0], at=one[1]) for one in inferred
    ]
    found = corrections_of(
        CorrectionRow(
            memory_id=one[0],
            correction=one[1],
            by_id=one[2],
            prompted_by=one[3],
            field=one[4],
            recorded_by=one[5],
            at=one[6],
        )
        for one in marks
    )
    reader = EntitlementSet(
        principal_id="u_reader",
        grants=(Grant(capability=CLIENT_NAME, scope=Scope.department("web")),),
    )
    return sorted(
        one.memory_id
        for one in recall(
            memories,
            reader,
            now=LATER,
            supersessions=found.supersessions,
            demotions=found.demotions,
        )
    )


def test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next() -> None:
    """The control followed to the system, through the store the route uses and as the role the
    application uses.

    Before: recall returns the learnt memory and the lone one, and not the memory it replaced. Two
    undos: the learnt memory's writes a supersession by the memory it replaced, the lone one's a
    demotion, each a row and a `memory` ledger entry attributed to the person under the request's
    trace, and the chain verifies. After: recall returns the memory put back and nothing else. A
    second undo writes neither a row nor an entry. The application may not update or delete a
    correction. Delete this and every one of those can be false in production while the stubbed
    tests above stay green. **Skips without a server.**"""
    with through_0061("brain_memory_correction") as url:
        seed(url)
        before = recalled_now(url)

        async def walk() -> tuple[bool, bool, bool]:
            engine = app_engine(url)
            try:
                store = StoredMemoryRecords(make_session_factory(engine))
                first = await store.undo(
                    learning("m_learnt", replaced_id="m_before"),
                    actor="u_admin",
                    trace_id="trace-undo-one",
                    ent_hash="c" * 32,
                )
                second = await store.undo(
                    learning("m_alone"),
                    actor="u_admin",
                    trace_id="trace-undo-two",
                    ent_hash="c" * 32,
                )
                again = await store.undo(
                    learning("m_learnt", replaced_id="m_before"),
                    actor="u_admin",
                    trace_id="trace-undo-again",
                    ent_hash="c" * 32,
                )
                return first.took_effect, second.took_effect, again.took_effect
            finally:
                await engine.dispose()

        took = run(walk)
        after = recalled_now(url)
        rows = sql(
            url,
            "SELECT memory_id, correction, by_id, prompted_by, field, recorded_by"
            " FROM mem.correction ORDER BY at, memory_id",
        )
        chain = entries(url)
        [(may_update, may_delete)] = sql(
            url,
            "SELECT has_table_privilege('brain_app', 'mem.correction', 'UPDATE'),"
            " has_table_privilege('brain_app', 'mem.correction', 'DELETE')",
        )

    assert before == ["m_alone", "m_learnt"]
    assert took == (True, True, False)
    assert rows[1:] == [
        ("m_learnt", "superseded", "m_before", "rejected", None, "u_admin"),
        ("m_alone", "demoted", None, None, "answer.length", "u_admin"),
    ]
    assert [(one.action.value, one.subject, one.actor_id, one.details) for one in chain] == [
        ("memory", "memory:m_before", "u_seed", {"change": "superseded"}),
        ("memory", "memory:m_learnt", "u_admin", {"change": "superseded"}),
        ("memory", "memory:m_alone", "u_admin", {"change": "demoted"}),
    ]
    assert [one.trace_id for one in chain[1:]] == ["trace-undo-one", "trace-undo-two"]
    assert AuditChain(chain).verify() is None
    assert after == ["m_before"]
    assert (may_update, may_delete) == (False, False)


def test_the_table_refuses_a_lowered_tier_and_a_correction_of_the_wrong_shape() -> None:
    """The constraints stand for a statement written by hand, which constructs no `Proposal` and no
    correction. A scope widening claimed as tier one, a supersession naming no replacement and a
    demotion carrying a signal are refused; the positive half is the same rows written correctly.
    Delete this and a row the domain would never build can make a gated change read as applied, or
    a mark that names nothing. **Skips without a server.**"""
    refused: list[str] = []
    bad = (
        "INSERT INTO mem.learning (memory_id, change, tier, subject)"
        " VALUES ('m_w', 'scope_widening', 1, 'x')",
        "INSERT INTO mem.correction (memory_id, correction, prompted_by, recorded_by, at)"
        " VALUES ('m_s', 'superseded', 'rejected', 'u_admin', now())",
        "INSERT INTO mem.correction (memory_id, correction, prompted_by, field, recorded_by, at)"
        " VALUES ('m_d', 'demoted', 'rejected', 'x', 'u_admin', now())",
    )
    with through_0061("brain_memory_correction_refused") as url:
        for statement in bad:
            try:
                sql(url, statement)
            except Exception as exc:
                refused.append(type(exc).__name__)
        sql(
            url,
            "INSERT INTO mem.learning (memory_id, change, tier, subject) VALUES ('m_w',"
            " 'scope_widening', 3, 'x')",
        )
        sql(
            url,
            "INSERT INTO mem.correction (memory_id, correction, by_id, prompted_by,"
            " recorded_by, at) VALUES ('m_s', 'superseded', 'm_t', 'rejected', 'u_admin', now())",
        )
        sql(
            url,
            "INSERT INTO mem.correction (memory_id, correction, field, recorded_by, at)"
            " VALUES ('m_d', 'demoted', 'x', 'u_admin', now())",
        )
        [(learnt, corrected)] = sql(
            url, "SELECT (SELECT count(*) FROM mem.learning), (SELECT count(*) FROM mem.correction)"
        )

    assert refused == ["CheckViolation"] * 3
    assert (learnt, corrected) == (1, 2)
