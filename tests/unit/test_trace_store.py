"""A run's trace graph is built from what finished, stored masked, and read under its own role.

The pure half builds graphs from finished requests and masks them. The database half builds `0150`
at head and drives the recorder and the reader through the application's own sessions, which run
every transaction as `brain_app`; it skips when `DATABASE_URL` is unset, as every `needs_db` test
does. The clock is 2999, for the reason CLAUDE.md records about fixtures that go off.

Task ids: M27.1.3, M24.3.4
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest
from sqlalchemy.schema import CreateTable

from brain.audit.ledger import TRACE_ID, AuditAction
from brain.core.lane import Lane
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.redaction import ChannelPayload
from brain.db import metadata
from brain.gate.context import Channel
from brain.gate.finish import Finished, Origin, ToolCallOutcome
from brain.gate.leash import DIGEST
from brain.models.metering import AnsweredCall, ModelUsage
from brain.ops.trace_store import (
    SET_TRACE_READER_ROLE,
    TRACE_READER_ROLE,
    UNNAMED,
    Step,
    StoredTraces,
    TraceRecorder,
    TraceStoreError,
    rows_of,
    steps_of,
)
from brain.ops.tracing import (
    MASKED_PAYLOADS,
    PAYLOAD_ROLE,
    VALUE_TOKEN_RE,
    StepKind,
    mask_value,
)
from brain.tables.identity import one_of
from tests.unit.test_tables import DIALECT, as_amended, migration_module, rendered, squash

NOW = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)
TRACE = "trace_store_test"
CANARY = "QZCANARY7F3A"
PERSON = "u_weiling.hr"


def _migration() -> Any:
    from tests.unit.test_tables import VERSIONS

    return migration_module(VERSIONS / "0150_trace_store_and_browser_session.py")


def finished(
    *,
    tool_calls: int = 1,
    connector: str | None = None,
    usage: ModelUsage | None = None,
    trace: str = TRACE,
) -> Finished:
    """A tool call that disclosed one record carrying the canary, as the automation path ends."""
    who = Principal(
        id=PERSON,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name="Reader",
    )
    return Finished(
        Origin(trace_id=trace, principal=who, channel=Channel.CONSOLE),
        NOW,
        ToolCallOutcome(
            refused=False,
            disclosed=ChannelPayload(
                records=({"@entity": "personnel", "principal_id": PERSON, "name": CANARY},)
            ),
        ),
        completed_at=NOW + timedelta(milliseconds=5),
        entitlement_hash="0" * 32,
        lane=Lane.TASK,
        tool_calls=tool_calls,
        connector=connector,
        model_usage=usage,
    )


# ------------------------------------------------------------------------- the graph, pure
def test_a_run_s_graph_hangs_every_step_from_the_request_and_each_read_from_its_call() -> None:
    """Two tool calls reading one source and two model attempts, one of them still in flight:
    the request is step zero, the attempts and calls hang from it, and each read hangs from its
    call. Delete this and a graph can come back flat or with edges pointing nowhere, and the
    trace graph screen draws a list."""
    usage = ModelUsage(
        calls=2,
        tokens_in=10,
        tokens_out=5,
        model="acme/model-1",
        provider="acme",
        agent_version=None,
        fallback_count=1,
        retry_count=0,
        answered=(AnsweredCall(provider="acme", model="acme/model-1", tokens_in=10, tokens_out=5),),
    )
    steps = steps_of(
        finished(tool_calls=2, connector="lark_base", usage=usage),
        ["timeout", None],
        environment="production",
    )

    shape = [(one.step, one.parent, one.kind) for one in steps]
    assert shape == [
        (0, None, StepKind.REQUEST),
        (1, 0, StepKind.MODEL_ATTEMPT),
        (2, 0, StepKind.MODEL_ATTEMPT),
        (3, 0, StepKind.TOOL_CALL),
        (4, 3, StepKind.RETRIEVAL),
        (5, 0, StepKind.TOOL_CALL),
        (6, 5, StepKind.RETRIEVAL),
    ]
    assert [one.span.attributes["outcome"] for one in steps[1:3]] == ["timeout", "in_flight"]
    assert steps[0].span.name == Lane.TASK.value
    assert steps[4].span.name == "lark_base"
    assert steps[0].span.attributes["model"] == "acme/model-1"
    assert steps[0].span.attributes["token_count"] == 15


def test_a_run_with_no_calls_is_one_step_and_a_name_that_is_not_vocabulary_names_nothing() -> None:
    """The positive floor and the fallback: a request that called nothing is its own graph, and a
    source whose name is not system vocabulary is stored under the kind's own word. Delete this and
    a connector named by a person's words is kept unmasked in the one field `mask` copies."""
    alone = steps_of(finished(tool_calls=0), [], environment="production")
    read = steps_of(finished(connector="Finance Ledger"), [], environment="production")

    assert [(one.step, one.kind) for one in alone] == [(0, StepKind.REQUEST)]
    assert read[-1].kind is StepKind.RETRIEVAL
    assert read[-1].span.name == StepKind.RETRIEVAL.value
    assert UNNAMED == "unnamed" and VALUE_TOKEN_RE.match(UNNAMED)


def test_every_stored_field_is_what_mask_leaves_and_no_value_reaches_a_row() -> None:
    """The rows `rows_of` builds carry a payload shape and never the payload: the canary in the
    disclosed record and the reader's id appear in no row, every payload is one of the four shapes,
    and the answer was carried, as a shape, rather than dropped. Delete this and a store holding
    what the redactor let one person see passes every test that only counts rows."""
    steps = steps_of(finished(connector="lark_base"), ["answered"], environment="production")

    rows = rows_of(TRACE, steps)

    written = json.dumps(rows, default=str)
    assert CANARY not in written and PERSON not in written
    assert {row["payload_in"] for row in rows} | {row["payload_out"] for row in rows} <= set(
        MASKED_PAYLOADS
    )
    assert rows[0]["payload_out"] != mask_value("")
    root = rows[0]["attributes"]
    assert isinstance(root, dict)
    assert root["principal"] == mask_value(PERSON)
    assert root["channel"] == Channel.CONSOLE.value
    assert all(row["trace_id"] == TRACE for row in rows)


def test_the_four_payload_shapes_are_every_shape_mask_leaves_in_a_payload() -> None:
    """Held against `mask_value` over strings of every length up to past the largest class, not
    against the constant itself. Delete this and a fifth size class makes every large answer a row
    the database refuses."""
    produced = {mask_value("x" * n) for n in range(0, 2100)}

    assert produced == set(MASKED_PAYLOADS)
    assert len(MASKED_PAYLOADS) == 4


# ------------------------------------------------------------------------- the migration
def test_0150_copies_each_rule_it_holds_from_the_code_that_owns_it() -> None:
    """Each pattern and list the migration writes out is the one the code checks against. Delete
    this and the database can admit a payload shape, a step kind or an action the code never
    writes, or refuse one it does."""
    m = _migration()

    assert m.TRACE_ID_PATTERN == TRACE_ID
    assert m.DIGEST_PATTERN == DIGEST
    assert VALUE_TOKEN_RE.pattern == m.NAME_PATTERN
    assert f"payload_in IN {m.MASKED_IN}" == one_of("payload_in", MASKED_PAYLOADS)
    assert one_of("kind", StepKind) == m.KIND_IN
    assert one_of("action", AuditAction) == m.WIDENED_ACTIONS
    assert m.SUPERSEDES == {m.NARROWER_ACTIONS: m.WIDENED_ACTIONS}
    assert m.READER_ROLE == TRACE_READER_ROLE
    assert f"SET LOCAL ROLE {TRACE_READER_ROLE}" == SET_TRACE_READER_ROLE
    assert m.down_revision == "0149"


@pytest.mark.parametrize("qualified", ("agent.browser_session", "obs.trace_step", "obs.trace_read"))
def test_0150_builds_each_table_exactly_as_the_model_declares_it(qualified: str) -> None:
    """Compared as rendered DDL, for `test_tables`' reason. Delete this and a model can gain a
    column or lose a check the database was built without."""
    from tests.unit.test_tables import VERSIONS

    expected = squash(str(CreateTable(metadata.tables[qualified]).compile(dialect=DIALECT)))

    assert expected in as_amended(
        rendered("upgrade", VERSIONS / "0150_trace_store_and_browser_session.py")
    )


def test_0150_grants_the_application_no_read_of_a_trace_and_the_reader_nothing_else() -> None:
    """Asserted on the SQL the upgrade emits. Delete this and a grant of SELECT to the application,
    or a membership it inherits through, ships with the database tests below the only witness."""
    from tests.unit.test_tables import VERSIONS

    emitted = squash(rendered("upgrade", VERSIONS / "0150_trace_store_and_browser_session.py"))

    assert "GRANT INSERT ON obs.trace_step TO brain_app" in emitted
    assert "GRANT SELECT ON obs.trace_step TO brain_trace_reader" in emitted
    assert "GRANT brain_trace_reader TO brain_app WITH INHERIT FALSE, SET TRUE" in emitted
    grants_to_app = [part for part in emitted.split(";") if "obs.trace_step TO brain_app" in part]
    assert grants_to_app and all("SELECT" not in part for part in grants_to_app)
    for table in ("agent.browser_session", "obs.trace_step", "obs.trace_read"):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in emitted


# --------------------------------------------------------------- the order of a read, no server
class Journal:
    """A sessionmaker whose sessions write down what they were asked, in order."""

    def __init__(self, steps: list[dict[str, Any]] | None = None) -> None:
        self.said: list[str] = []
        self.steps = steps or []

    def __call__(self) -> Journal:
        return self

    async def __aenter__(self) -> Journal:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def begin(self) -> Journal:
        self.said.append("begin")
        return self

    async def execute(self, statement: Any) -> Any:
        said = str(statement).split("\n", 1)[0]
        self.said.append(said)

        class Found:
            def all(inner) -> list[tuple[Any, ...]]:  # noqa: N805
                return []

        return Found()


def test_a_read_writes_its_row_and_ends_that_transaction_before_it_takes_the_reader_role() -> None:
    """The row is inserted in a transaction of its own, which ends before the one that takes the
    reader role and selects. Delete this and the two can be swapped or merged, so a read whose row
    failed to commit has already happened."""
    journal = Journal()
    store = StoredTraces(journal)  # type: ignore[arg-type]

    asyncio.run(
        store.read(
            realm_roles=(PAYLOAD_ROLE,), at=NOW, actor="u_ops", trace_id=TRACE, reason="incident"
        )
    )

    said = journal.said
    row = next(i for i, one in enumerate(said) if one.startswith("INSERT INTO obs.trace_read"))
    role = said.index(SET_TRACE_READER_ROLE)
    select = next(i for i, one in enumerate(said) if one.startswith("SELECT obs.trace_step"))
    assert row < said.index("begin", row) < role < select


def test_a_read_without_the_separate_role_writes_nothing_and_reads_nothing() -> None:
    """Refused before any statement, whatever other role is held. Delete this and a read with no
    role can reach the store, or leave a row saying somebody read what they were refused."""
    journal = Journal()
    store = StoredTraces(journal)  # type: ignore[arg-type]

    with pytest.raises(TraceStoreError):
        asyncio.run(
            store.read(
                realm_roles=("super_admin", f"{PAYLOAD_ROLE}-readonly"),
                at=NOW,
                actor="u_ops",
                trace_id=TRACE,
                reason="incident",
            )
        )
    assert journal.said == []


# ------------------------------------------------------------------------ with a server
@pytest.fixture(scope="module")
def head() -> Iterator[str]:
    from tests.unit.test_acceptance import at_head

    with at_head("brain_trace_store") as url:
        yield url


def _sessions(url: str) -> Any:
    from brain.db import normalise_database_url
    from brain.session import make_app_engine, make_application_sessions

    return make_application_sessions(make_app_engine(normalise_database_url(url)))


@pytest.mark.needs_db
def test_a_finished_run_is_stored_masked_and_read_back_only_under_the_reader_role(
    head: str,
) -> None:
    """**The store as the application uses it.** The recorder writes the run's graph as
    `brain_app`; `brain_app` itself is refused a SELECT; a read without the realm role is refused
    with no row; a read with it leaves one row and returns the graph, masked, with the canary in no
    step. Delete this and any one of those can stop holding on a real schema with the pure tests
    green."""
    from tests.fixtures.scratch_postgres import sql

    trace = "trace_store_db_1"
    sessions = _sessions(head)
    asyncio.run(TraceRecorder(sessions, environment="production").finished(finished(trace=trace)))

    with psycopg.connect(head) as conn:
        conn.execute("SET ROLE brain_app")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM obs.trace_step")
        conn.rollback()

    store = StoredTraces(sessions)
    with pytest.raises(TraceStoreError):
        asyncio.run(
            store.read(realm_roles=(), at=NOW, actor="u_ops", trace_id=trace, reason="incident")
        )
    assert sql(head, "SELECT count(*) FROM obs.trace_read WHERE trace_id = %s", trace) == [(0,)]

    steps = asyncio.run(
        store.read(
            realm_roles=(PAYLOAD_ROLE,), at=NOW, actor="u_ops", trace_id=trace, reason="incident"
        )
    )

    assert sql(head, "SELECT actor, reason FROM obs.trace_read WHERE trace_id = %s", trace) == [
        ("u_ops", "incident")
    ]
    assert [(one.kind, one.parent) for one in steps] == [
        (StepKind.REQUEST, None),
        (StepKind.TOOL_CALL, 0),
    ]
    assert all(one.payload_out in MASKED_PAYLOADS for one in steps)
    assert CANARY not in json.dumps([dict(one.attributes) for one in steps])


@pytest.mark.needs_db
def test_the_database_refuses_a_payload_that_is_not_a_shape(head: str) -> None:
    """The second lock: a row written without `mask`, as `brain_app`, is refused by the payload
    column's own check. Delete this and the table's constraint can be dropped with `mask` the only
    thing between a record and the store."""
    with psycopg.connect(head) as conn:
        conn.execute("SET ROLE brain_app")
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "INSERT INTO obs.trace_step (trace_id, step, kind, name, attributes, payload_in,"
                " payload_out) VALUES ('t_raw', 0, 'request', 'task', '{}',"
                " '[masked:str/empty]', %s)",
                (CANARY,),
            )
        conn.rollback()


@pytest.mark.needs_db
def test_a_trace_the_database_refuses_is_logged_and_the_request_goes_on(head: str) -> None:
    """A second run under the same trace collides with the first's steps, and the recorder returns
    rather than raising. Delete this and a trace store fault becomes a fault the asker sees."""
    sessions = _sessions(head)
    recorder = TraceRecorder(sessions, environment="production")
    asyncio.run(recorder.finished(finished(trace="trace_store_db_twice")))

    asyncio.run(recorder.finished(finished(trace="trace_store_db_twice")))


def test_a_step_is_a_span_and_nothing_else_reaches_a_row() -> None:
    """`rows_of` reads the span it is handed through `mask` and takes nothing else from the step
    but its place. Delete this and a field added to `Step` can reach the table unmasked."""
    from brain.ops.tracing import Span

    step = Step(
        step=0,
        parent=None,
        kind=StepKind.REQUEST,
        span=Span(name="task", environment="production", payload_in=CANARY, payload_out=CANARY),
    )

    [row] = rows_of(TRACE, [step])

    assert set(row) == {
        "trace_id",
        "step",
        "parent",
        "kind",
        "name",
        "attributes",
        "payload_in",
        "payload_out",
    }
    assert CANARY not in json.dumps(row)
