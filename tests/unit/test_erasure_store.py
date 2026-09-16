"""The erasure executor, the queue and its ledger entries, held to what they do to real rows.

Three halves. The declarations are checked against every table the models declare, with no
database, because that is where the next table added without a decision is caught. The executor
and the drain run against a database of their own, built from the models for the tables they
touch, with the grants each table's migration gives the application role, because "retired by its
own rule" is a claim about the catalogue and only a catalogue can answer it. The request table's
policies, grants and trigger are `0060`'s own statements executed on that database, beside `0003`'s
hash function, so the ledger entries asserted here are the ones the migration writes.

It needs a PostgreSQL server and skips without `DATABASE_URL`, which CI always sets. It does not
need pgvector, so it runs on a development machine with the binaries-only server CLAUDE.md names.

Task ids: M27.7.24
"""

from __future__ import annotations

import importlib.util
import types
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg.types.json import Jsonb
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

import brain.tables  # noqa: F401 - registers every table on the metadata
from brain.db import metadata, normalise_database_url
from brain.ops.erasure import ErasureError, StoreRemoval, erasure_targets
from brain.ops.erasure_store import (
    A_CONNECTION_ROW_SECURITY_NARROWS_CANNOT_COUNT_WHAT_IT_ERASES,
    A_TABLE_NOBODY_DECIDED_ABOUT_STOPS_ITS_STORE,
    ABOUT_NOBODY,
    ALREADY_REQUESTED,
    ERASURE_QUEUE_ACTOR,
    NO_CACHE_ERASER,
    NO_INDEX_ERASER,
    NO_OBJECT_STORE_ERASER,
    RETAINED,
    SUBJECT_COLUMNS,
    ErasureRefusedError,
    EstateEraser,
    PostgresEraser,
    StoredErasures,
    Through,
    declaration_gaps,
    drain_erasure_queue,
)
from brain.ops.retention import Store
from brain.ops.retention_store import (
    A_PARTITIONED_TABLE_LEAVES_A_PARTITION_AT_A_TIME,
    A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO,
)
from brain.ops.schedule import DESTRUCTIVE
from brain.ops.schedule_runner import RUNNERS
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import drop, fresh, run, sql

VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"

#: Far outside any wall clock, so no fixture here goes off. See CLAUDE.md on dates in fixtures.
NOW = datetime(2999, 3, 1, 9, 0, tzinfo=UTC)
REQUESTED = NOW - timedelta(hours=1)


def migration(name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(f"erasure_store_{name}", VERSIONS / name)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------ the declarations, no database
def test_every_table_the_models_declare_in_an_erasable_store_is_decided_about_exactly_once() -> (
    None
):
    """Every table in a PostgreSQL store a deletion reaches is declared as a person's, a person's
    through a parent, nobody's, or kept on purpose, and no declaration names a table that is gone.

    Delete this and the next table added to `mem` or `ops` arrives undeclared, and the queue
    refuses that store on every install from the day it ships, or a rename leaves a declaration
    pointing at nothing while the renamed table goes unsearched."""
    assert declaration_gaps(tuple(metadata.tables)) == ()
    assert {"auth.principal", "mem.persistent", "know.chunk"} <= set(SUBJECT_COLUMNS)
    assert "ops.erasure_request" in RETAINED


def test_a_table_undeclared_declared_twice_or_renamed_is_a_finding() -> None:
    """The three ways the declarations stop describing the schema, each produced from a
    constructed set so the check is seen to fire. Delete this and `declaration_gaps` can return
    nothing for every input, and the test above passes with it."""
    undeclared = declaration_gaps(
        ("mem.persistent", "mem.stray"),
        subjects={"mem.persistent": "principal_id"},
        through={},
        about_nobody=frozenset(),
        retained={},
    )
    assert undeclared == (f"mem.stray: {A_TABLE_NOBODY_DECIDED_ABOUT_STOPS_ITS_STORE}",)

    twice = declaration_gaps(
        ("mem.persistent",),
        subjects={"mem.persistent": "principal_id"},
        about_nobody=frozenset({"mem.persistent"}),
        through={},
        retained={},
    )
    assert twice == (
        "mem.persistent is declared more than one way, so which rule applies is a guess",
    )

    renamed = declaration_gaps(
        (), subjects={"mem.gone": "principal_id"}, through={}, about_nobody=frozenset(), retained={}
    )
    assert renamed == ("mem.gone is declared here and is not a table, so a rename left it behind",)

    orphaned = declaration_gaps(
        ("chat.message",),
        subjects={},
        through={"chat.message": Through(parent="chat.x", key="k", parent_key="id")},
        about_nobody=frozenset(),
        retained={},
    )
    assert "chat.message reaches a person through chat.x, which names nobody" in orphaned


def test_the_audit_chain_and_anything_outside_the_erasable_stores_is_not_asked_about() -> None:
    """The audit store is retained and the hold table explains it, so neither needs a declaration
    here; a schema no store a deletion reaches holds is out of scope. Delete this and the check
    could start demanding a subject column on the hash chain, which invites somebody to add one."""
    assert declaration_gaps(
        ("obs.audit_entry", "obs.legal_hold", "chat.message", "public.elsewhere"),
        subjects={},
        through={},
        about_nobody=frozenset(),
        retained={},
    ) == (f"chat.message: {A_TABLE_NOBODY_DECIDED_ABOUT_STOPS_ITS_STORE}",)


def test_an_actor_column_does_not_make_a_table_a_persons() -> None:
    """Tables whose only person columns name who acted are about nobody. Asserted on tables whose
    columns say so, from the models, rather than on the constant alone. Delete this and a table of
    who granted what can be moved into `SUBJECT_COLUMNS` under its `granted_by`, and erasing the
    granter then counts somebody else's grants as theirs."""
    for table in ("ops.credential_write", "ops.webhook_change", "agent.skill"):
        assert table in ABOUT_NOBODY
        columns = {one.name for one in metadata.tables[table].c}
        assert columns & {"written_by", "changed_by", "submitted_by"}
        assert not columns & {"principal_id", "owner_id", "subject_id"}


def test_the_queue_is_not_held_behind_a_release_and_the_schedule_can_start_it() -> None:
    """`A_FILED_REQUEST_IS_ALREADY_THE_DECISION`, as the schedule sees it. Delete this and the queue
    can be added to `DESTRUCTIVE`, where it reports for ever because nothing records its release,
    or lose its runner, and filed requests are never carried out."""
    assert "erasure_queue" not in DESTRUCTIVE
    assert any(one.name == "erasure_queue" and one.run is not None for one in RUNNERS)


# ----------------------------------------------------------------- the estate, no database
class Recording:
    """An eraser that records the stores it was handed and removes one row from each."""

    def __init__(self) -> None:
        self.asked: list[Store] = []

    def count_for(self, store: Store, subject_id: str) -> int:
        return 1

    def erase(self, store: Store, subject_id: str) -> StoreRemoval:
        self.asked.append(store)
        return StoreRemoval(removed=1)


def test_the_estate_hands_each_store_to_the_executor_that_can_reach_it_and_names_the_rest() -> None:
    """PostgreSQL stores go to the PostgreSQL executor, the object store to the seam, and the
    cache and the index are refused by name. With no object-store eraser the object store is
    refused by name too, and with one it is handed over.

    Delete this and a store could be sent to the wrong executor, which refuses it for the wrong
    reason, or the seam could be ignored when an implementation is plugged into it."""
    postgres, objects = Recording(), Recording()
    estate = EstateEraser(postgres, objects=objects)  # type: ignore[arg-type]

    for store in erasure_targets():
        if store in (Store.CACHE, Store.INDEX):
            continue
        estate.erase(store, "p_ada")
    assert postgres.asked == [
        one
        for one in erasure_targets()
        if one not in (Store.RECORDING, Store.ATTACHMENT, Store.CACHE, Store.INDEX)
    ]
    assert objects.asked == [Store.ATTACHMENT, Store.RECORDING]
    with pytest.raises(ErasureError) as cache:
        estate.erase(Store.CACHE, "p_ada")
    with pytest.raises(ErasureError) as index:
        estate.erase(Store.INDEX, "p_ada")
    assert (str(cache.value), str(index.value)) == (NO_CACHE_ERASER, NO_INDEX_ERASER)

    without = EstateEraser(Recording())  # type: ignore[arg-type]
    with pytest.raises(ErasureError) as unattached:
        without.erase(Store.RECORDING, "p_ada")
    assert str(unattached.value) == NO_OBJECT_STORE_ERASER


# ------------------------------------------------------------------------- with a server
#: The tables the executor and the drain touch here, built from the models.
MODELLED: tuple[str, ...] = (
    "auth.principal",
    "auth.principal_identity",
    "auth.session",
    "auth.directory_role_grant",
    "gate.capability_grant",
    "mem.persistent",
    "chat.conversation",
    "chat.message",
    "obs.audit_entry",
    "obs.legal_hold",
    "ops.erasure_request",
)

#: What each table's migration grants the application role, restated for a database built from
#: the models. `0002`, `0003`, `0005`, `0006`, `0018` and `0049`; `0060`'s is executed from it.
GRANTS: tuple[str, ...] = (
    "GRANT SELECT, INSERT, UPDATE ON auth.principal TO brain_app",
    "GRANT SELECT, INSERT, UPDATE ON auth.principal_identity TO brain_app",
    "GRANT SELECT, INSERT, UPDATE ON auth.session TO brain_app",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON auth.directory_role_grant TO brain_app",
    "GRANT SELECT, INSERT, UPDATE ON gate.capability_grant TO brain_app",
    "GRANT SELECT, INSERT ON mem.persistent TO brain_app",
    "GRANT SELECT, INSERT, UPDATE ON chat.conversation TO brain_app",
    "GRANT SELECT, INSERT ON chat.message TO brain_app",
    "GRANT SELECT, INSERT ON obs.legal_hold TO brain_app",
    "GRANT UPDATE (released_at, released_by) ON obs.legal_hold TO brain_app",
    "GRANT USAGE ON SCHEMA chat TO brain_app",
    "GRANT SELECT, INSERT ON obs.audit_entry TO brain_app",
)


@contextmanager
def estate(database: str) -> Iterator[str]:
    """A database holding `MODELLED`, the grants, and `0060`'s policies, grants and trigger."""
    url = fresh(database)
    engine = create_engine(normalise_database_url(url), poolclass=NullPool)
    try:
        sql(url, "CREATE SCHEMA IF NOT EXISTS chat")
        metadata.create_all(engine, tables=[metadata.tables[one] for one in MODELLED])
        sql(url, migration("0003_resolver_and_tables.py").AUDIT_HASH_FUNCTION)
        erasure = migration("0060_erasure_request.py")
        for statement in (*GRANTS, *erasure.RLS, *erasure.GRANTS):
            sql(url, statement)
        sql(url, erasure.ERASURE_REQUEST_TRIGGER_FUNCTION)
        for statement in erasure.TRIGGERS:
            sql(url, statement)
        yield url
    finally:
        engine.dispose()
        drop(database)


def a_person(url: str, person: str) -> None:
    """A principal with a sign-in, a session, a directory role, a grant, a memory and a
    conversation of two messages: one row in every table `MODELLED` holds about a person."""
    sql(
        url,
        "INSERT INTO auth.principal (id, kind, employment, display_name) "
        "VALUES (%s, 'human', 'staff', %s)",
        person,
        person,
    )
    sql(
        url,
        "INSERT INTO auth.principal_identity (channel, identity_hash, principal_id, bound_at) "
        "VALUES ('console', %s, %s, %s)",
        uuid.uuid4().hex + uuid.uuid4().hex,
        person,
        REQUESTED,
    )
    sql(
        url,
        "INSERT INTO auth.session (id, principal_id, channel, assurance, started_at, expires_at) "
        "VALUES (%s, %s, 'console', 1, %s, %s)",
        f"s_{person}",
        person,
        REQUESTED,
        NOW,
    )
    sql(
        url,
        "INSERT INTO auth.directory_role_grant (principal_id, role, source_group, last_seen_at) "
        "VALUES (%s, 'member', 'staff', %s)",
        person,
        REQUESTED,
    )
    sql(
        url,
        "INSERT INTO gate.capability_grant (principal_id, capability, scope, granted_by, reason) "
        "VALUES (%s, 'read:client.name', '{\"clauses\": []}', 'u_seed', 'needed')",
        person,
    )
    sql(
        url,
        "INSERT INTO mem.persistent (id, principal_id, statement, capability_tags, scope, "
        "ent_hash, kind, formed_at) VALUES (%s, %s, 'prefers mornings', ARRAY['read:client.name'], "
        "'{\"clauses\": []}', %s, 'preference', %s)",
        uuid.uuid4().hex[:26],
        person,
        "e" * 32,
        REQUESTED,
    )
    [(conversation,)] = sql(
        url, "INSERT INTO chat.conversation (principal_id) VALUES (%s) RETURNING id", person
    )
    for role in ("user", "assistant"):
        sql(
            url,
            "INSERT INTO chat.message (conversation_id, role, channel) VALUES (%s, %s, 'console')",
            conversation,
            role,
        )


def one(url: str, statement: str, *params: object) -> Any:
    [(value,)] = sql(url, statement, *params)
    return value


def live(url: str, table: str, column: str, person: str) -> int:
    """How many of a person's rows in a table are not retired."""
    schema, _, name = table.partition(".")
    query = psycopg.sql.SQL(
        "SELECT count(*) FROM {table} WHERE {column} = %s AND deleted_at IS NULL"
    ).format(table=psycopg.sql.Identifier(schema, name), column=psycopg.sql.Identifier(column))
    with psycopg.connect(url, autocommit=True) as conn:
        row = conn.execute(query, (person,)).fetchone()
    assert row is not None
    return int(row[0])


def test_an_erasure_retires_removes_and_keeps_each_table_by_its_own_rule_and_nobody_elses() -> None:
    """**The executor, on real rows.** For the person asked about: the principal, its sign-in and
    its grant are retired with the statement's own instant; the directory role, the one table the
    application may delete from, is removed; the session and the memory, which no path may remove,
    are kept and named with the rule; the conversation is retired and its messages, reached through
    it, are kept. Nothing about the other person moves.

    Delete this and an executor can retire a person's rows with the wrong stamp, hard-delete a
    table whose migration argued against it, report kept rows as erased, or reach somebody else."""
    with estate("brain_erasure_rules") as url:
        a_person(url, "p_ada")
        a_person(url, "p_ben")
        with psycopg.connect(url) as conn:
            eraser = PostgresEraser(conn)
            before = eraser.count_for(Store.ROWS, "p_ada")
            rows = eraser.erase(Store.ROWS, "p_ada")
            memory = eraser.erase(Store.MEMORY, "p_ada")
            conversation = eraser.erase(Store.CONVERSATION, "p_ada")
            operations = eraser.erase(Store.OPERATIONS, "p_ada")
            stamped = conn.execute("SELECT statement_timestamp()").fetchone()
            conn.commit()

        assert before == 5
        assert rows == StoreRemoval(
            removed=1,
            retired=3,
            kept=1,
            kept_because=A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO,
        )
        assert memory == StoreRemoval(
            kept=1, kept_because=A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO
        )
        assert conversation == StoreRemoval(
            retired=1, kept=2, kept_because=A_TABLE_WITH_NO_DELETE_GRANT_ARGUED_FOR_HOW_ITS_ROWS_GO
        )
        assert operations == StoreRemoval()
        assert stamped is not None
        for table, column in (
            ("auth.principal", "id"),
            ("auth.principal_identity", "principal_id"),
            ("gate.capability_grant", "principal_id"),
            ("chat.conversation", "principal_id"),
        ):
            assert (live(url, table, column, "p_ada"), live(url, table, column, "p_ben")) == (0, 1)
        assert (
            one(url, "SELECT count(*) FROM auth.directory_role_grant WHERE principal_id = 'p_ada'")
            == 0
        )
        assert (
            one(url, "SELECT count(*) FROM auth.directory_role_grant WHERE principal_id = 'p_ben'")
            == 1
        )
        assert one(url, "SELECT count(*) FROM auth.session WHERE principal_id = 'p_ada'") == 1


def test_a_table_nobody_declared_stops_its_store_before_anything_in_it_is_touched() -> None:
    """A table in the store's schema that no declaration names refuses the store, and the refusal
    comes before a single row in it is retired. Delete this and an undeclared table is skipped,
    and whatever it holds about the person survives an erasure reported as done."""
    with estate("brain_erasure_undeclared") as url:
        a_person(url, "p_ada")
        sql(url, "CREATE TABLE auth.stray (principal_id text)")
        with psycopg.connect(url) as conn:
            with pytest.raises(ErasureError, match=r"auth\.stray: the catalogue lists a table"):
                PostgresEraser(conn).erase(Store.ROWS, "p_ada")
            conn.commit()

        assert one(url, "SELECT count(*) FROM auth.principal WHERE deleted_at IS NULL") == 1
        assert one(url, "SELECT count(*) FROM auth.directory_role_grant") == 1


def test_a_connection_row_security_narrows_is_refused_and_one_it_does_not_is_not() -> None:
    """Run as the application role, whose policies would hide rows from the count, the store is
    refused before anything is counted or written; run as the owner, the same store is erased.

    Delete this and the queue can run on a narrowed connection, count only what the policies show
    it, retire that, and report a person erased with the hidden rows still there."""
    with estate("brain_erasure_narrowed") as url:
        a_person(url, "p_ada")
        sql(url, "ALTER TABLE auth.principal ENABLE ROW LEVEL SECURITY")
        with psycopg.connect(url, options="-c role=brain_app") as narrowed:
            with pytest.raises(ErasureError) as refused:
                PostgresEraser(narrowed).erase(Store.ROWS, "p_ada")
            narrowed.rollback()
        assert A_CONNECTION_ROW_SECURITY_NARROWS_CANNOT_COUNT_WHAT_IT_ERASES in str(refused.value)
        assert one(url, "SELECT count(*) FROM auth.principal WHERE deleted_at IS NULL") == 1

        with psycopg.connect(url) as owner:
            done = PostgresEraser(owner).erase(Store.ROWS, "p_ada")
            owner.commit()
        assert done.retired == 3


def test_a_partitioned_table_keeps_its_rows_for_the_partition_rule() -> None:
    """A partitioned table leaves a partition at a time, so its rows about the person are kept and
    the rule says so, whatever the application role may do. Delete this and an erasure could
    DELETE from the metadata ledger, which `0039` argues is never done a row at a time."""
    with estate("brain_erasure_partitioned") as url:
        sql(url, "CREATE TABLE mem.spilled (principal_id text) PARTITION BY LIST (principal_id)")
        sql(url, "CREATE TABLE mem.spilled_ada PARTITION OF mem.spilled FOR VALUES IN ('p_ada')")
        sql(url, "GRANT SELECT, INSERT, DELETE ON mem.spilled TO brain_app")
        sql(url, "INSERT INTO mem.spilled VALUES ('p_ada')")
        with psycopg.connect(url) as conn:
            kept = PostgresEraser(
                conn, subjects={**SUBJECT_COLUMNS, "mem.spilled": "principal_id"}
            ).erase(Store.MEMORY, "p_ada")
            conn.commit()

        # The application role holds DELETE on it, and the partition rule still wins.
        assert kept == StoreRemoval(
            kept=1, kept_because=A_PARTITIONED_TABLE_LEAVES_A_PARTITION_AT_A_TIME
        )
        assert one(url, "SELECT count(*) FROM mem.spilled") == 1


def file(url: str, person: str, *, by: str = "u_admin", at: datetime = REQUESTED) -> str:
    """A request inserted as the owner, the way an operator's statement would."""
    return str(
        one(
            url,
            "INSERT INTO ops.erasure_request "
            "(subject_id, reason_reference, requested_by, requested_at) "
            "VALUES (%s, 'DSAR-1', %s, %s) RETURNING request_id",
            person,
            by,
            at,
        )
    )


def drain(url: str, at: datetime = NOW) -> str:
    with psycopg.connect(url) as conn:
        said = drain_erasure_queue(conn, now=at)
        conn.commit()
    return said


def entries(url: str, request_id: str) -> list[tuple[Any, ...]]:
    return sql(
        url,
        "SELECT actor_id, action, details FROM obs.audit_entry WHERE subject = %s ORDER BY seq",
        f"erasure:{request_id}",
    )


def test_a_held_request_is_finished_as_held_with_its_holds_and_nothing_is_touched() -> None:
    """A legal hold over the person, placed after the request and active when the queue runs,
    stops it: the request is finished as held naming the hold, no store is recorded, and every row
    about the person is where it was. The ledger records the request and the hold outcome.

    Delete this and a request filed before a dispute began is carried out during it, which
    destroys evidence under a hold somebody placed precisely to keep it."""
    with estate("brain_erasure_held") as url:
        a_person(url, "p_ada")
        request = file(url, "p_ada")
        sql(
            url,
            "INSERT INTO obs.legal_hold "
            "(id, reason_code, subjects, all_subjects, placed_at, placed_by) "
            "VALUES ('hold-dispute', 'employment_dispute', ARRAY['p_ada'], false, %s, 'u_legal')",
            REQUESTED + timedelta(minutes=5),
        )

        said = drain(url)

        assert said == f"erasure request {request}: held"
        assert sql(url, "SELECT outcome, holds, stores, finished_by FROM ops.erasure_request") == [
            ("held", ["hold-dispute"], [], ERASURE_QUEUE_ACTOR)
        ]
        assert one(url, "SELECT count(*) FROM auth.principal WHERE deleted_at IS NULL") == 1
        assert one(url, "SELECT count(*) FROM auth.directory_role_grant") == 1
        assert entries(url, request) == [
            ("u_admin", "erasure", {"change": "requested"}),
            (ERASURE_QUEUE_ACTOR, "erasure", {"change": "held"}),
        ]


def test_the_queue_carries_a_request_out_and_writes_what_each_store_did_and_what_it_could_not() -> (
    None
):
    """**The leaf, end to end on this database.** A request filed and not held is carried out:
    the person's rows are erased by their tables' rules, the request is finished as incomplete
    because the object store, the cache and the index are not reached and rows were kept, every
    store a deletion reaches is on the request with its counts and its sentence, the second run
    finds nothing open, and the ledger has the request and its outcome under the request's id and
    never the person's.

    Delete this and each part can be true alone and the queue still never finish a request, or
    finish one with a record that says nothing about what it reached."""
    with estate("brain_erasure_drained") as url:
        a_person(url, "p_ada")
        request = file(url, "p_ada")
        later = file(url, "p_ben", at=NOW + timedelta(days=1))

        said = drain(url)
        again = drain(url)

        assert said == f"erasure request {request}: incomplete"
        assert again == "no erasure request was open"
        [(outcome, stores, holds, finished_at)] = sql(
            url,
            "SELECT outcome, stores, holds, finished_at FROM ops.erasure_request "
            "WHERE request_id = %s",
            request,
        )
        assert (outcome, holds, finished_at) == ("incomplete", [], NOW)
        by_store = {entry["store"]: entry for entry in stores}
        assert set(by_store) == {store.value for store in Store}
        assert (
            by_store["rows"]["retired"],
            by_store["rows"]["removed"],
            by_store["rows"]["kept"],
        ) == (3, 1, 1)
        assert by_store["recording"] == {
            "store": "recording",
            "disposition": "erase",
            "reached": False,
            "removed": 0,
            "retired": 0,
            "kept": 0,
            "because": NO_OBJECT_STORE_ERASER,
        }
        assert (by_store["cache"]["reached"], by_store["cache"]["because"]) == (
            False,
            NO_CACHE_ERASER,
        )
        assert by_store["audit"]["disposition"] == "retained"
        assert one(url, "SELECT count(*) FROM ops.erasure_request WHERE finished_at IS NULL") == 1
        assert (
            one(url, "SELECT subject_id FROM ops.erasure_request WHERE request_id = %s", later)
            == "p_ben"
        )
        assert entries(url, request) == [
            ("u_admin", "erasure", {"change": "requested"}),
            (ERASURE_QUEUE_ACTOR, "erasure", {"change": "incomplete"}),
        ]
        assert (
            one(
                url,
                "SELECT count(*) FROM obs.audit_entry "
                "WHERE subject LIKE '%%p_ada%%' OR details::text LIKE '%%p_ada%%'",
            )
            == 0
        )


def test_a_request_asked_for_a_report_carries_nothing_out() -> None:
    """Report-only mode counts what is open and touches nothing. Delete this and a run the schedule
    was told only to report could erase somebody."""
    with estate("brain_erasure_report_only") as url:
        a_person(url, "p_ada")
        file(url, "p_ada")
        with psycopg.connect(url) as conn:
            said = drain_erasure_queue(conn, now=NOW, report_only=True)
            conn.commit()

        assert said == "report only: 1 erasure request(s) open and none carried out"
        assert one(url, "SELECT count(*) FROM ops.erasure_request WHERE finished_at IS NULL") == 1
        assert one(url, "SELECT count(*) FROM auth.principal WHERE deleted_at IS NULL") == 1


def app_engine(url: str) -> AsyncEngine:
    """An engine whose every connection is the application role, so `0060`'s policies apply."""
    return create_async_engine(
        normalise_database_url(url),
        poolclass=NullPool,
        connect_args={"options": "-c role=brain_app"},
    )


def test_a_request_is_filed_in_the_sessions_own_name_once_per_open_person_and_never_finished() -> (
    None
):
    """As the application role: a request files in the caller's name and the ledger records it;
    a second open request for the same person is refused by name; a row naming somebody else as
    its filer, or arriving already finished, is refused by the policy; and the application role
    cannot finish a request at all.

    Delete this and a console request can file an erasure in another administrator's name, file
    one already marked erased, or mark a real one erased without the queue ever running."""
    with estate("brain_erasure_filed") as url:

        async def go() -> tuple[Any, Any]:
            engine = app_engine(url)
            try:
                store = StoredErasures(make_session_factory(engine))
                filed = await store.file(
                    subject_id="p_ada",
                    reason_reference="DSAR-7",
                    actor="u_admin",
                    ent_hash="c" * 32,
                    trace_id="trace-erasure",
                    at=REQUESTED,
                )
                with pytest.raises(ErasureRefusedError) as twice:
                    await store.file(
                        subject_id="p_ada",
                        reason_reference="DSAR-8",
                        actor="u_admin",
                        ent_hash="c" * 32,
                        trace_id="trace-erasure",
                        at=REQUESTED,
                    )
                listed = await store.requests(limit=10)
                return (filed, twice.value.reason), listed
            finally:
                await engine.dispose()

        (filed, reason), listed = run(go)

        assert reason == ALREADY_REQUESTED
        assert [one.request_id for one in listed] == [filed.request_id]
        assert (filed.subject_id, filed.requested_by, filed.outcome) == ("p_ada", "u_admin", None)
        assert sql(
            url,
            "SELECT actor_id, details, ent_hash, trace_id FROM obs.audit_entry WHERE subject = %s",
            f"erasure:{filed.request_id}",
        ) == [("u_admin", {"change": "requested"}, "c" * 32, "trace-erasure")]

        with psycopg.connect(url, options="-c role=brain_app") as app:
            app.execute("SELECT set_config('app.principal_id', 'u_admin', false)")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                app.execute(
                    "INSERT INTO ops.erasure_request (subject_id, reason_reference, requested_by, "
                    "requested_at) VALUES ('p_ben', 'DSAR-9', 'u_someone_else', %s)",
                    (REQUESTED,),
                )
            app.rollback()
            app.execute("SELECT set_config('app.principal_id', 'u_admin', false)")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                app.execute(
                    "INSERT INTO ops.erasure_request (subject_id, reason_reference, requested_by, "
                    "requested_at, finished_at, finished_by, outcome, stores, holds) VALUES "
                    "('p_ben', 'DSAR-9', 'u_admin', %s, %s, 'u_admin', 'erased', %s, %s)",
                    (REQUESTED, NOW, Jsonb([]), Jsonb([])),
                )
            app.rollback()
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                app.execute(
                    "UPDATE ops.erasure_request SET finished_at = %s, finished_by = 'u_admin', "
                    "outcome = 'erased', stores = '[]', holds = '[]'",
                    (NOW,),
                )
            app.rollback()
