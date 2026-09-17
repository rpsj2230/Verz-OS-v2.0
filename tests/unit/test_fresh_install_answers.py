"""A set-up install answers a question through the ladder it was written and its own passages.

Each half has its own file: `tests/unit/test_default_ladder_store.py` writes the ladder and
`tests/unit/test_model_lane_db.py` asks the real search. This joins them on one PostgreSQL database
built through the migrations that ship, to `0059`, with `know.chunk` added the way
`tests/unit/test_document_second_wall.py` adds it, because a server without pgvector cannot run
`0009`. Nothing is a stand-in except the provider's HTTP transport, which records what it was sent
and answers: the ladder is written by `SessionLadderWriter`, read back by `SessionLadder`, walked
by `ModelCalls` with its attempt rows written by `SessionAttempts`, and the passages are found by
the registered search handler through `SessionRowSource`, all as the application role.

**Skips without a server.**

Task ids: none
"""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.lane import Lane
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Scope
from brain.db import normalise_database_url
from brain.firstrun import GRANTED_BY
from brain.gate.answer import Answered, answer_lane
from brain.gate.context import Channel
from brain.gate.finish import Origin
from brain.gate.model_lane import DocumentSearchTool, ModelLane
from brain.knowledge.document_tools import searcher
from brain.knowledge.row_store import SessionRowSource
from brain.knowledge.search import CHUNK, KNOWLEDGE_READ
from brain.models.adapter import SdkDriver
from brain.models.assembly import HOSTED_PROFILE
from brain.models.calls import ModelCalls
from brain.models.default_ladder import DEFAULT_MODELS, LadderWritten
from brain.models.routing import Tier
from brain.ops.default_ladder_store import SessionLadderWriter
from brain.ops.model_service import SessionAttempts, SessionLadder
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import run, sql
from tests.unit import test_document_second_wall as wall
from tests.unit.test_answer_lane import CLIENTS, HOURS, Rows, Sink, readers_for
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_console_control_audit import through_0059
from tests.unit.test_model_calls import Scripted
from tests.unit.test_model_lane import Kept, completion
from tests.unit.test_model_lane_db import FINANCE, PASSAGES, WEB, WITHHELD

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
AT = datetime(2999, 3, 4, 9, 0, tzinfo=UTC)

TRACE = "t-fresh-install-answers"

ASKER = "u_asker"

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


def add_the_document_plane(url: str) -> None:
    """Two departments, four passages, and `know.chunk` where the migrations did not build it.

    With pgvector, which CI has, `through_0059` runs every migration to head, so the table and its
    policies are the ones that ship and only the rows are added. Without it, the table is `CHUNK`
    less its vector with 0009's own policy and grants, as `tests/unit/test_document_second_wall.py`
    builds it.
    """
    [(existing,)] = sql(url, "SELECT to_regclass('know.chunk') IS NOT NULL")
    if not existing:
        metadata = sa.MetaData()
        sa.Table(
            CHUNK.name,
            metadata,
            *(column._copy() for column in CHUNK.columns if column.name != wall.LEFT_OUT),
            schema=CHUNK.schema,
        )
        engine = sa.create_engine(normalise_database_url(url), poolclass=NullPool)
        try:
            metadata.create_all(engine)
        finally:
            engine.dispose()
        migration = wall._migration()
        with psycopg.connect(url, autocommit=True) as conn:
            for statement in (*migration.RLS, *migration.GRANTS):
                conn.execute(statement)
    with psycopg.connect(url, autocommit=True) as conn:
        for slug in (FINANCE, WEB):
            conn.execute(
                "INSERT INTO gate.department (company_id, slug, name, scope_slug) "
                "VALUES (%s, %s, %s, %s)",
                ("c_fresh_install", slug, slug.title(), slug),
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


def test_a_set_up_install_answers_through_its_default_ladder_from_its_own_passages() -> None:
    """**A fresh install answers a question with a model.** The wizard's ladder for a hosted
    provider is written into `ops.routing_rung`; the executor reads it back and calls the default
    `main` model; the question reaches that model with the web asker's company and department
    passages and nothing of finance's or anybody's diary; the answer cites what the model was shown;
    one attempt row names the default rung and the request's trace; and the ledger lane is the
    answer lane's.

    Delete this and each half can pass on its own while the join between them, a ladder the answer
    path actually walks and passages it actually finds, is proved by nothing."""
    transport = Scripted(completion("Invoices are paid within thirty days."))

    async def work(sessions: async_sessionmaker[AsyncSession]) -> tuple[LadderWritten, Answered]:
        written = await SessionLadderWriter(sessions).write(
            "anthropic", actor=GRANTED_BY, trace_id="startup.reconcile.fresh0000000000"
        )
        calls = ModelCalls(
            ladder=SessionLadder(sessions),
            attempts=SessionAttempts(sessions),
            drivers={"anthropic": SdkDriver(provider="anthropic", transport=transport)},
            profile=lambda: HOSTED_PROFILE,
            held=lambda: frozenset({"anthropic"}),
            clock=lambda: AT,
        )
        answered = await answer_lane(
            "invoices",
            origin=Origin(
                trace_id=TRACE,
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
            sink=Sink(),
            now=AT,
            clock=lambda: AT,
            model=ModelLane(
                search=DocumentSearchTool(handler=searcher(SessionRowSource(sessions))),
                model=calls,
            ),
        )
        return written, answered

    async def go() -> tuple[LadderWritten, Answered]:
        built = app_engine(url)
        try:
            return await work(make_session_factory(built))
        finally:
            await built.dispose()

    kept = Kept()
    with through_0059("brain_fresh_install_answers") as url:
        add_the_document_plane(url)
        written, answered = run(go)
        attempts = sql(
            url,
            "SELECT a.trace_id, a.outcome, r.tier, r.provider, r.model FROM ops.model_attempt a "
            "JOIN ops.routing_rung r ON r.id = a.rung_id",
        )

    assert written is LadderWritten.WRITTEN
    assert answered.composed is not None
    (request,) = transport.sent
    assert request.model == DEFAULT_MODELS["anthropic"][Tier.MAIN]
    shown = "\n".join(one.content for one in request.messages)
    assert "paid within thirty days" in shown
    assert "Invoice templates for web clients" in shown
    for value in WITHHELD:
        assert value not in shown
    assert {one.record_id for one in answered.composed.citations} == {
        "c_handbook_1",
        "c_styleguide_1",
    }
    assert attempts == [(TRACE, "ok", Tier.MAIN.value, "anthropic", request.model)]
    (finished,) = kept.seen
    assert finished.lane is Lane.ANSWER
