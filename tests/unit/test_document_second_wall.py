"""The document tools against the real row-level security policy on `know.chunk`.

`tests/unit/test_document_tools.py` holds the tools to what they build: every chunk statement
carries `reach_predicate` and `session_settings` for one `Reach`. That cannot say whether the
settings reach the policy, because a stand-in source evaluates no SQL, and the failure it would
miss is silent: settings run in a different transaction leave `current_setting` NULL, and the
policy admits company-visible chunks only. So this runs the real tools, through the real
`SessionRowSource`, on a real server, as the role the policy names.

**The policy is 0009's own text, and the table is built from `CHUNK` less one column.** 0009
cannot be run here, because `know.chunk.embedding` is a pgvector column and a server without
the extension cannot create it. Rather than a copy of the policy written out in this file, the
test imports `RLS` and `GRANTS` from the migration and executes them, so what is under test is
the policy that ships. The table is `brain.knowledge.search.CHUNK` with every column except
`embedding`, which no statement these tools build reads; a test in `test_document_tools.py`
walks their statements to hold that. `gate.department` is built from `DepartmentRow` with no
policy of its own, because its policy is `deleted_at IS NULL` and the query already says so.

**Both halves are asserted, and the second wall is asserted on its own.** A department document
comes back for a caller in that department and not for one outside it, and a personal document
for its owner and nobody else. The refusals alone would pass for settings that never arrived,
since the first wall refuses those callers too, so the positive half is the load-bearing one;
and a statement with no reach predicate at all is run under each set of settings, to show the
policy narrows by itself rather than borrowing its refusals from the WHERE clause.

**Connecting as `brain_app` is `options=-c role=brain_app`,** which sets the role for the
session the way `SET ROLE` would. A superuser bypasses row-level security, so without it every
test here passes against a policy nobody consulted, which the policy-alone test would catch by
reading department chunks with no settings.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is.

Task ids: M15.2.6, M15.2.7
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import TypedResult
from brain.core.scope import Scope
from brain.db import libpq_url, normalise_database_url
from brain.knowledge.document_tools import (
    DocumentRead,
    DocumentSearch,
    KnowledgePassage,
    reader,
    searcher,
)
from brain.knowledge.row_store import SessionRowSource
from brain.knowledge.rows import RowQuery
from brain.knowledge.search import CHUNK, KNOWLEDGE_READ, Reach, session_settings
from brain.tables.gate import DepartmentRow

pytestmark = pytest.mark.needs_db

#: A database of this file's own, created and dropped here, for the reason
#: `tests/unit/test_delegation_sql.py` gives about its own.
DATABASE = "brain_document_second_wall"

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0009_search.py"

#: The only column of `CHUNK` a server without pgvector cannot create.
LEFT_OUT = "embedding"

COMPANY = "c_second_wall"
FINANCE = "finance"
WEB = "web"

OWNER = "u_owner"
OTHER = "u_other"


def _database_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("BRAIN_DATABASE_URL") or None


def _pointed_at(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{database}"))


def _migration() -> Any:
    spec = importlib.util.spec_from_file_location("m0009_second_wall", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    body: str
    visibility: str
    owner_id: str = OWNER
    department: str | None = None


#: One document at each visibility, each a single passage carrying a word no other one does, so
#: a search for that word can only ever find that document.
CHUNKS: tuple[Chunk, ...] = (
    Chunk("c_handbook_1", "doc_handbook", "The company handbook covers holidays.", "company"),
    Chunk(
        "c_payroll_1",
        "doc_payroll",
        "Payroll closes on the twentieth of every month.",
        "department",
        department=FINANCE,
    ),
    Chunk(
        "c_styleguide_1",
        "doc_styleguide",
        "The styleguide names every brand colour.",
        "department",
        department=WEB,
    ),
    Chunk("c_diary_1", "doc_diary", "My diary says the appraisal is Thursday.", "personal"),
)


def _build(admin: str, url: str) -> None:
    """Create the scratch database, both tables, 0009's policy and grants, and the rows."""
    import psycopg

    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{DATABASE}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{DATABASE}"')

    scratch = _pointed_at(admin, DATABASE)
    with psycopg.connect(scratch, autocommit=True) as conn:
        conn.execute("CREATE SCHEMA know")
        conn.execute("CREATE SCHEMA gate")
        conn.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'brain_app') "
            "THEN CREATE ROLE brain_app NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$"
        )
        conn.execute("GRANT USAGE ON SCHEMA know, gate TO brain_app")

    metadata = sa.MetaData()
    sa.Table(
        CHUNK.name,
        metadata,
        *(column._copy() for column in CHUNK.columns if column.name != LEFT_OUT),
        schema=CHUNK.schema,
    )
    # Read through the metadata rather than `__table__`, which is typed as a `FromClause`.
    DepartmentRow.metadata.tables["gate.department"].to_metadata(metadata)
    engine = sa.create_engine(
        _pointed_at(normalise_database_url(url), DATABASE), poolclass=NullPool
    )
    try:
        metadata.create_all(engine)
    finally:
        engine.dispose()

    migration = _migration()
    with psycopg.connect(scratch, autocommit=True) as conn:
        for statement in (*migration.RLS, *migration.GRANTS):
            conn.execute(statement)
        conn.execute("GRANT SELECT ON gate.department TO brain_app")
        for slug in (FINANCE, WEB):
            conn.execute(
                "INSERT INTO gate.department (company_id, slug, name, scope_slug) "
                "VALUES (%s, %s, %s, %s)",
                (COMPANY, slug, slug.title(), slug),
            )
        for ordinal, one in enumerate(CHUNKS):
            conn.execute(
                "INSERT INTO know.chunk (chunk_id, document_id, ordinal, kind, title, span_start, "
                "span_end, body, owner_id, department, visibility, state) "
                "VALUES (%s, %s, %s, 'prose', %s, 0, %s, %s, %s, %s, %s, 'published')",
                (
                    one.chunk_id,
                    one.document_id,
                    ordinal,
                    one.document_id,
                    len(one.body),
                    one.body,
                    one.owner_id,
                    one.department,
                    one.visibility,
                ),
            )


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    """The SQLAlchemy url of a scratch database holding the rows above under 0009's policy."""
    import psycopg

    url = _database_url()
    if url is None:
        pytest.skip("DATABASE_URL is unset, so there is no server to ask; CI always sets it")

    admin = libpq_url(url)
    _build(admin, url)
    yield _pointed_at(normalise_database_url(url), DATABASE)

    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{DATABASE}" WITH (FORCE)')


def _run[T](url: str, work: Callable[[SessionRowSource], Awaitable[T]]) -> T:
    """Run one piece of work through a `SessionRowSource` connected as `brain_app`.

    A fresh engine per call and disposed in the same loop, because an async engine is bound to
    the loop it was first used in. The selector loop on Windows, because psycopg's async mode
    does not run on the proactor loop Windows defaults to.
    """

    async def go() -> T:
        engine = create_async_engine(
            url, poolclass=NullPool, connect_args={"options": "-c role=brain_app"}
        )
        try:
            return await work(SessionRowSource(async_sessionmaker(engine, class_=AsyncSession)))
        finally:
            await engine.dispose()

    if os.name == "nt":
        return asyncio.run(go(), loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(go())


def reading(principal_id: str, scope: Scope) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=(Grant(capability=Capability(value=KNOWLEDGE_READ.value), scope=scope),),
    )


def read(url: str, document_id: str, who: EntitlementSet) -> TypedResult[KnowledgePassage]:
    async def work(source: SessionRowSource) -> TypedResult[KnowledgePassage]:
        return await reader(source)(DocumentRead(document_id=document_id), entitlement=who)

    return _run(url, work)


def search(url: str, question: str, who: EntitlementSet) -> TypedResult[KnowledgePassage]:
    async def work(source: SessionRowSource) -> TypedResult[KnowledgePassage]:
        return await searcher(source)(DocumentSearch(question=question), entitlement=who)

    return _run(url, work)


def documents(found: TypedResult[KnowledgePassage]) -> list[str]:
    return sorted({one.document_id for one in found.records})


IN_FINANCE = reading(OTHER, Scope.department(FINANCE))
IN_WEB = reading(OTHER, Scope.department(WEB))


def test_a_department_document_reaches_a_caller_in_that_department_and_nobody_outside_it(
    server: str,
) -> None:
    """**The half that was false until 2026-09-14.** A finance caller reads finance's payroll
    document through `knowledge.read_document` on a real server, through the real policy, as
    `brain_app`. Before the settings travelled with the statement the policy saw no
    `app.departments`, admitted company chunks only, and this read came back empty.

    The web caller is refused the same document and still reads the company handbook, so the
    refusal is the reach and not a connection that returns nothing to anybody.

    Delete this and the settings can stop reaching the policy, which every stand-in test passes
    and which hands every department nothing of its own."""
    assert documents(read(server, "doc_payroll", IN_FINANCE)) == ["doc_payroll"]
    assert documents(read(server, "doc_payroll", IN_WEB)) == []
    assert documents(read(server, "doc_handbook", IN_WEB)) == ["doc_handbook"]


def test_a_personal_document_reaches_its_owner_and_nobody_else(server: str) -> None:
    """The personal branch reads `app.principal_id`. Its owner reads the diary through the real
    policy; another person holding the same unrestricted grant does not, and still reads the
    handbook.

    Delete this and `app.principal_id` can stop arriving, which leaves every person's own
    documents unreachable to them while company documents go on answering."""
    everywhere = Scope.unrestricted()

    assert documents(read(server, "doc_diary", reading(OWNER, everywhere))) == ["doc_diary"]
    assert documents(read(server, "doc_diary", reading(OTHER, everywhere))) == []
    assert documents(read(server, "doc_handbook", reading(OTHER, everywhere))) == ["doc_handbook"]


def test_a_search_finds_a_department_passage_for_its_department_and_not_for_another(
    server: str,
) -> None:
    """The search tool runs three kinds of chunk statement, a ranking leg and the bodies of what
    it ranked, and each has to carry the settings: a ranking admitted by the policy and a bodies
    statement that was not would find the passage and hand back nothing.

    Delete this and one of the search tool's statements can lose its settings while the read
    tool, which runs one statement, still passes."""
    assert documents(search(server, "payroll", IN_FINANCE)) == ["doc_payroll"]
    assert documents(search(server, "payroll", IN_WEB)) == []
    assert documents(search(server, "handbook", IN_WEB)) == ["doc_handbook"]


def test_the_policy_by_itself_admits_what_the_settings_say_and_company_chunks_without_them(
    server: str,
) -> None:
    """**The second wall, with the first taken away.** A statement selecting every chunk with no
    reach predicate at all is run three ways. With no settings the policy admits the company
    chunk only, which is the fail-closed default 0009 records. With web's settings for a caller
    who owns nothing it admits the company chunk and web's. With the owner's settings and no
    department it admits the company chunk and the diary.

    Without this the refusals above could be the WHERE clause's alone, and a policy that
    admitted everything, or a connection that bypassed it, would pass every one of them.

    Delete this and the second wall can be switched off with every test here still green."""
    everything = sa.select(CHUNK.c.chunk_id.label("chunk_id")).order_by(CHUNK.c.chunk_id)

    def ids(settings: tuple[Any, ...]) -> list[str]:
        query = RowQuery(
            entity="knowledge",
            source="knowledge",
            columns=("chunk_id",),
            statement=everything,
            certainly_empty=False,
            settings=settings,
        )

        async def work(source: SessionRowSource) -> list[str]:
            return [str(row["chunk_id"]) for row in await source.rows(query)]

        return _run(server, work)

    assert ids(()) == ["c_handbook_1"]
    assert ids(session_settings(Reach(principal_id=OTHER, departments=(WEB,)))) == [
        "c_handbook_1",
        "c_styleguide_1",
    ]
    assert ids(session_settings(Reach(principal_id=OWNER))) == ["c_diary_1", "c_handbook_1"]
