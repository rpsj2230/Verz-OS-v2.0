"""The answer lane's model step through the real passage search, on PostgreSQL, under 0009's policy.

`tests/unit/test_model_lane.py` breaches the first wall on purpose and proves the redactor holds.
This proves the first wall stands where it is supposed to: the registered search handler, through
`SessionRowSource` connected as the application role, with `reach_predicate` in every statement and
0009's row-level security reading the settings each statement carries. The model is a real
`brain.models.calls.ModelCalls` over a transport that records what it was sent.

**The caller reads every passage field over everything and the plane over one department**, so the
redactor would pass anything the search returned: whatever is absent from the prompt here is absent
because the query and the policy never returned it. The table is built the way
`tests/unit/test_document_second_wall.py` builds it, from `CHUNK` less the pgvector column, with
0009's own policy and grants executed.

Skipped when `DATABASE_URL` is unset, as every `needs_db` test is.

Task ids: none
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.lane import Lane
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.db import libpq_url, normalise_database_url
from brain.gate.abstain import AbstentionReason
from brain.gate.answer import Answered, answer_lane
from brain.gate.context import Channel
from brain.gate.finish import Finished, Origin
from brain.gate.model_lane import DocumentSearchTool, ModelLane
from brain.gate.streaming import frames
from brain.knowledge.document_tools import searcher
from brain.knowledge.row_store import SessionRowSource
from brain.knowledge.search import CHUNK, KNOWLEDGE_READ
from brain.models.driver import DriverRequest
from brain.ops.telemetry import request_telemetry_of
from brain.tables.gate import DepartmentRow
from tests.unit import test_document_second_wall as wall
from tests.unit.test_answer_lane import CLIENTS, HOURS, Rows, Sink, readers_for
from tests.unit.test_model_calls import T0, Ladder, Log, Scripted, executor, rung
from tests.unit.test_model_lane import Kept, completion

pytestmark = pytest.mark.needs_db

#: A database of this file's own, created and dropped here.
DATABASE = "brain_model_lane"

COMPANY = "c_model_lane"
FINANCE = "finance"
WEB = "web"
OWNER = "u_owner"
ASKER = "u_asker"


@dataclass(frozen=True)
class Passage:
    chunk_id: str
    document_id: str
    title: str
    body: str
    visibility: str
    owner_id: str = OWNER
    department: str | None = None


#: Four documents that all mention invoices, at each visibility, and two words only a withheld
#: document holds, so a question for one of those words can be answered by nothing the asker reads.
PASSAGES: tuple[Passage, ...] = (
    Passage(
        "c_handbook_1",
        "doc_handbook",
        "Handbook",
        "Invoices are paid within thirty days, says the company handbook.",
        "company",
    ),
    Passage(
        "c_ledger_1",
        "doc_ledger",
        "Ledger TAPIRTITLE",
        "Invoices above the limit need PANGOLINAPPROVAL from the controller.",
        "department",
        department=FINANCE,
    ),
    Passage(
        "c_styleguide_1",
        "doc_styleguide",
        "Styleguide",
        "Invoice templates for web clients live in the styleguide.",
        "department",
        department=WEB,
    ),
    Passage(
        "c_diary_1",
        "doc_diary",
        "Diary",
        "My diary says the OCELOTDIARY invoices are late.",
        "personal",
    ),
)

#: Everything the asker must never be shown, from the finance document and the personal one.
WITHHELD: tuple[str, ...] = (
    "c_ledger_1",
    "doc_ledger",
    "TAPIRTITLE",
    "PANGOLINAPPROVAL",
    "c_diary_1",
    "doc_diary",
    "OCELOTDIARY",
)

#: The plane over web, and every passage field over everything.
ASKER_REACH = EntitlementSet(
    principal_id=ASKER,
    grants=(
        Grant(capability=Capability(value=KNOWLEDGE_READ.value), scope=Scope.department(WEB)),
        *(
            Grant(capability=Capability(value=f"read:knowledge.{field}"), scope=Scope())
            for field in ("document", "title", "section", "updated_at")
        ),
    ),
)


def _build(admin: str, url: str) -> None:
    """The scratch database: `know.chunk` less its vector, `gate.department`, 0009's policy."""
    import psycopg

    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{DATABASE}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{DATABASE}"')

    scratch = wall._pointed_at(admin, DATABASE)
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
        *(column._copy() for column in CHUNK.columns if column.name != wall.LEFT_OUT),
        schema=CHUNK.schema,
    )
    DepartmentRow.metadata.tables["gate.department"].to_metadata(metadata)
    engine = sa.create_engine(
        wall._pointed_at(normalise_database_url(url), DATABASE), poolclass=NullPool
    )
    try:
        metadata.create_all(engine)
    finally:
        engine.dispose()

    migration = wall._migration()
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
        for ordinal, one in enumerate(PASSAGES):
            conn.execute(
                "INSERT INTO know.chunk (chunk_id, document_id, ordinal, kind, title, span_start, "
                "span_end, body, owner_id, department, visibility, state) "
                "VALUES (%s, %s, %s, 'prose', %s, 0, %s, %s, %s, %s, %s, 'published')",
                (
                    one.chunk_id,
                    one.document_id,
                    ordinal,
                    one.title,
                    len(one.body),
                    one.body,
                    one.owner_id,
                    one.department,
                    one.visibility,
                ),
            )


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    """The SQLAlchemy url of the scratch database above."""
    import psycopg

    url = os.environ.get("DATABASE_URL") or os.environ.get("BRAIN_DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is unset, so there is no server to ask; CI always sets it")
    admin = libpq_url(url)
    _build(admin, url)
    yield wall._pointed_at(normalise_database_url(url), DATABASE)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{DATABASE}" WITH (FORCE)')


@dataclass
class Asked:
    answered: Answered
    finished: Finished
    sent: list[DriverRequest]
    attempts: Log
    sink: Sink


def ask(url: str, question: str) -> Asked:
    """One question through the lane, the real search as `brain_app`, and a recording model."""
    transport = Scripted(completion("Invoices are paid within thirty days."))
    calls, attempts = executor(Ladder((rung("anthropic"),)), {"anthropic": transport})
    sink = Sink()
    kept = Kept()

    async def go(source: SessionRowSource) -> Answered:
        return await answer_lane(
            question,
            origin=Origin(
                trace_id="t-model-lane-db",
                principal=Principal(
                    id=ASKER,
                    kind=PrincipalKind.HUMAN,
                    employment=Employment.STAFF,
                    display_name="Asker",
                ),
                channel=Channel.CONSOLE,
            ),
            recorders=(kept,),
            rules=(HOURS,),
            readers=readers_for(Rows()),
            entitlement=ASKER_REACH,
            policies={"client": CLIENTS.policy()},
            reachable_sources=(),
            sink=sink,
            now=T0,
            clock=lambda: T0,
            model=ModelLane(search=DocumentSearchTool(handler=searcher(source)), model=calls),
        )

    answered = _run(url, go)
    (finished,) = kept.seen
    return Asked(answered, finished, transport.sent, attempts, sink)


def _run(url: str, work: Callable[[SessionRowSource], Awaitable[Answered]]) -> Answered:
    """`tests/unit/test_document_second_wall._run`, returning the lane's outcome."""

    async def go() -> Answered:
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


def prompt(asked: Asked) -> str:
    return "\n".join(one.content for request in asked.sent for one in request.messages)


def surfaces(asked: Asked) -> dict[str, str]:
    return {
        "prompt": prompt(asked),
        "attempt rows": repr(asked.attempts.rows),
        "trace sink": "".join(
            payload.model_dump_json() + trace.model_dump_json()
            for _, payload, trace in asked.sink.emitted
        ),
        "ledger row": repr(request_telemetry_of(asked.finished)),
        "frames": frames(asked.answered.frames),
    }


def test_through_postgres_the_model_reads_its_departments_passages_and_no_others(
    server: str,
) -> None:
    """**The whole path on a real server.** A web asker's question matching four documents is
    answered by a model shown the company handbook and web's styleguide, cited from those two, and
    shown nothing of finance's ledger or somebody else's diary: not in the prompt, the attempt
    rows, the trace, the ledger row or the frames. The ledger row is the answer lane's.

    Delete this and the lane can be wired to a search that reads without the asker's reach, which
    every stand-in test passes, and one department's documents answer another's question."""
    asked = ask(server, "invoices")

    assert asked.answered.composed is not None
    shown = prompt(asked)
    assert "paid within thirty days" in shown
    assert "Invoice templates for web clients" in shown
    cited = {one.record_id for one in asked.answered.composed.citations}
    assert cited == {"c_handbook_1", "c_styleguide_1"}
    for where, text in surfaces(asked).items():
        for value in WITHHELD:
            assert value not in text, f"{value} reached the {where}"
    assert asked.finished.lane is Lane.ANSWER


def test_through_postgres_a_question_only_a_withheld_document_answers_is_one_nothing_answers(
    server: str,
) -> None:
    """**DENIED and ABSENT on a real server.** A word only finance's ledger holds and a word no
    document holds give the web asker byte-identical frames and the same abstention, and neither
    reaches a model.

    Delete this and the reach predicate can be dropped from the ranking statement while the bodies
    statement keeps it, which finds the ledger, fetches nothing and asks a model about nothing, and
    the extra step tells the asker the word exists somewhere they cannot see."""
    withheld = ask(server, "pangolinapproval")
    absent = ask(server, "zeppelinnowhere")

    assert withheld.answered.frames == absent.answered.frames
    assert withheld.answered.abstention == absent.answered.abstention
    assert withheld.answered.abstention is not None
    assert withheld.answered.abstention.reason is AbstentionReason.NOTHING_RETRIEVED
    assert withheld.sent == absent.sent == []
    assert withheld.finished.lane is absent.finished.lane is Lane.FAST


def test_the_withheld_word_is_found_by_somebody_who_may_read_it(server: str) -> None:
    """The refusal above is only a refusal if the word is there to be found. A finance reader's
    search for it returns finance's ledger through the same handler, and the rows are all there
    when read as the superuser, which row-level security does not bind.

    Delete this and a fixture that inserted nothing, or a word the text search cannot match, makes
    the refusal pass by emptiness."""
    import psycopg

    finance = wall.reading("u_finance", Scope.department(FINANCE))
    with psycopg.connect(libpq_url(server)) as conn:
        found = conn.execute("SELECT chunk_id FROM know.chunk ORDER BY chunk_id").fetchall()

    assert wall.documents(wall.search(server, "pangolinapproval", finance)) == ["doc_ledger"]
    assert [one for (one,) in found] == sorted(one.chunk_id for one in PASSAGES)
