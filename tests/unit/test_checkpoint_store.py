"""A real graph, saved and resumed through the guarded saver, and the reach it finds on resume.

The first half needs no server: the library's in-memory saver sits behind `GuardedSaver`, so
every refusal and every read is the guard's own code running against the library's real graph
loop. The second half is the leaf: the same graph against a scratch PostgreSQL, installed by
`install_checkpointer`, interrupted, the caller's grant revoked, and resumed on a new pool.

Task ids: M17.2.1, M32.4.1.2
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, TypedDict

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.ops.automation import flow_reach
from brain.ops.checkpoint_store import (
    SAVER_TABLE_PREFIX,
    GuardedSaver,
    checkpointer_pool,
    checkpointer_pool_settings,
    guarded_saver,
    install_checkpointer,
)
from brain.ops.checkpoints import CHECKPOINT_SCHEMA, CheckpointerConfig, CheckpointerError
from brain.ops.connections import WORKER_CHECKPOINTER_CONNECTIONS
from brain.ops.queue import SEARCH_PATH_SQL


class RecordingConnection:
    """Records what a pool's `configure` step runs, and whether it left the connection idle."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.committed = False

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executed.append((sql, params))

    def commit(self) -> None:
        self.committed = True


READ = Capability(value="read:ticket.status")
OWNER = "u_owner"
STRANGER = "u_stranger"
AGENT = "ag_support"


def holding(principal_id: str, *capabilities: Capability) -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=tuple(Grant(capability=c, scope=Scope.unrestricted()) for c in capabilities),
        not_after=None,
    )


CEILING = holding(AGENT, READ)


class State(TypedDict, total=False):
    run_id: str
    principal_id: str
    node: str
    step: int
    record_refs: Any


class Directory:
    """Who holds what right now. A resumed node asks this, never the saved state."""

    def __init__(self) -> None:
        self.grants: dict[str, EntitlementSet] = {OWNER: holding(OWNER, READ)}
        self.seen: list[bool] = []

    def revoke(self, principal_id: str) -> None:
        self.grants[principal_id] = holding(principal_id)


def a_graph(directory: Directory, saver: GuardedSaver, *, plan_writes: Any = "t_1,t_2") -> Any:
    def plan(state: State) -> State:
        return {"node": "plan", "step": 1, "record_refs": plan_writes}

    def fetch(state: State) -> State:
        # The caller's reach, asked for now, through the one implementation of the invariant.
        reach = flow_reach(directory.grants[state["principal_id"]], CEILING)
        directory.seen.append(reach.scope_for(READ) is not None)
        return {"node": "fetch", "step": 2}

    graph = StateGraph(State)
    graph.add_node("plan", plan)
    graph.add_node("fetch", fetch)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "fetch")
    graph.add_edge("fetch", END)
    compiled: CompiledStateGraph[Any, Any, Any, Any] = graph.compile(
        checkpointer=saver, interrupt_before=["fetch"]
    )
    return compiled


def thread(name: str) -> Any:
    return {"configurable": {"thread_id": name}}


def saved_at(name: str) -> Any:
    """The config a direct `put` takes, which names the checkpoint namespace as well."""
    return {"configurable": {"thread_id": name, "checkpoint_ns": ""}}


def started(principal_id: str = OWNER) -> State:
    return {"run_id": "r_1", "principal_id": principal_id}


# ------------------------------------------------------------------ without a server
def test_a_run_of_references_is_saved_and_resumed_through_the_guard() -> None:
    """The positive sibling of every refusal below. A guard proven only by what it refuses is
    satisfied by one that refuses everything, and that guard leaves no graph able to pause.

    Delete this and the saver can refuse the library's own input checkpoint or routing markers,
    which no refusal test would notice."""
    directory = Directory()
    saver = GuardedSaver(InMemorySaver(), principal_id=OWNER)
    app = a_graph(directory, saver)

    paused = app.invoke(started(), thread("t"))
    finished = app.invoke(None, thread("t"))

    assert paused["node"] == "plan"
    assert finished == {**started(), "node": "fetch", "step": 2, "record_refs": "t_1,t_2"}
    assert directory.seen == [True]


def test_a_node_that_saves_a_list_stops_the_run_and_nothing_of_it_is_written() -> None:
    """The retrieved passages are a list, and the whole of the protection is that a list never
    reaches the store. Asserted on the store as well as on the exception, because a guard that
    raised after writing would pass the first half.

    Delete this and `put_writes` can stop calling `checkpoint_refusals`."""
    inner = InMemorySaver()
    app = a_graph(Directory(), GuardedSaver(inner, principal_id=OWNER), plan_writes=["t_1", "t_2"])

    with pytest.raises(CheckpointerError, match="record_refs"):
        app.invoke(started(), thread("t"))

    assert "record_refs" not in str(inner.writes)
    assert "t_2" not in str(inner.writes)


def test_a_checkpoint_naming_another_owner_is_not_saved() -> None:
    """A saver bound to one principal refuses a run started for another, so a worker handed the
    wrong saver cannot file a run under somebody else's name.

    Delete this and the owner check in `put` can go, and a resumable run could be assembled for
    one person and filed as another's."""
    from langgraph.checkpoint.base import empty_checkpoint

    inner = InMemorySaver()
    saver = GuardedSaver(inner, principal_id=OWNER)
    theirs = empty_checkpoint()
    theirs["channel_values"] = {"run_id": "r_1", "principal_id": STRANGER}
    ours = empty_checkpoint()
    ours["channel_values"] = {"run_id": "r_2", "principal_id": OWNER}

    with pytest.raises(CheckpointerError, match="owner"):
        saver.put(saved_at("t_theirs"), theirs, {}, {})
    assert inner.get_tuple(thread("t_theirs")) is None

    # Separate threads, because a refusal on a thread refuses everything after it on that thread.
    mine = saved_at("t_ours")
    saved = saver.put(mine, ours, {}, {})
    saver.put_writes(saved, [("principal_id", OWNER)], "task_1")
    with pytest.raises(CheckpointerError, match="different owner"):
        saver.put_writes(saved, [("principal_id", STRANGER)], "task_2")
    assert STRANGER not in str(inner.writes)
    with pytest.raises(CheckpointerError, match="already refused"):
        saver.put_writes(saved, [("node", "plan")], "task_3")


def test_an_input_carrying_a_list_is_not_saved_as_the_first_checkpoint() -> None:
    """The first save a graph makes is its input, before any node has written a channel, so
    it is `put` that sees the list and not `put_writes`. The library saves in the background, so
    the run goes on after that refusal and saves its next step, and the assertion that nothing at
    all is stored is what holds `A_REFUSED_RUN_SAVES_NOTHING_MORE`.

    Delete this and `put` can stop asking `checkpoint_refusals`, or a refused run can go on
    saving, leaving an ownerless checkpoint, with every other test still green."""
    inner = InMemorySaver()
    app = a_graph(Directory(), GuardedSaver(inner, principal_id=OWNER))

    with pytest.raises(CheckpointerError, match="record_refs"):
        app.invoke({**started(), "record_refs": ["t_1", "t_2"]}, thread("t"))
    assert inner.get_tuple(thread("t")) is None


def test_another_principal_finds_no_run_on_the_thread_rather_than_a_refusal() -> None:
    """DENIED and ABSENT read the same. A stranger holding the thread id gets exactly what a
    thread that never existed gives, and the owner still gets the run.

    Delete this and `get_tuple` or `list` can return another principal's run, which makes a
    thread id a bearer token for a half-finished answer composed for somebody else."""
    inner = InMemorySaver()
    a_graph(Directory(), GuardedSaver(inner, principal_id=OWNER)).invoke(started(), thread("t"))
    stranger = GuardedSaver(inner, principal_id=STRANGER)
    owner = GuardedSaver(inner, principal_id=OWNER)

    assert stranger.get_tuple(thread("t")) is None
    assert stranger.get_tuple(thread("t")) == stranger.get_tuple(thread("never"))
    assert list(stranger.list(thread("t"))) == []
    assert owner.get_tuple(thread("t")) is not None
    assert list(owner.list(thread("t")))


def test_a_stranger_cannot_delete_a_run_and_its_owner_can() -> None:
    """Deletion is the other way a thread id could act as a bearer token. Delete this and
    `delete_thread` can delegate unconditionally."""
    inner = InMemorySaver()
    a_graph(Directory(), GuardedSaver(inner, principal_id=OWNER)).invoke(started(), thread("t"))

    GuardedSaver(inner, principal_id=STRANGER).delete_thread("t")
    assert inner.get_tuple(thread("t")) is not None

    GuardedSaver(inner, principal_id=OWNER).delete_thread("t")
    assert inner.get_tuple(thread("t")) is None


def test_an_error_is_not_saved_and_a_resume_runs_the_task_again() -> None:
    """An exception's message carried a record identifier here, as real ones do. It is not
    written, and the resume after the fault is fixed still completes.

    Delete this and `__error__` can be refused instead of dropped, which replaces the node's
    own exception with the saver's, or admitted, which files the message in the store."""
    failing = {"on": True}
    inner = InMemorySaver()
    saver = GuardedSaver(inner, principal_id=OWNER)

    def plan(state: State) -> State:
        if failing["on"]:
            msg = "could not read record t_1 for u_owner"
            raise RuntimeError(msg)
        return {"node": "plan", "step": 1}

    graph = StateGraph(State)
    graph.add_node("plan", plan)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", END)
    app = graph.compile(checkpointer=saver)

    with pytest.raises(RuntimeError, match="t_1"):
        app.invoke(started(), thread("t"))
    assert "t_1" not in str(inner.writes)
    assert "__error__" not in str(inner.writes)

    failing["on"] = False
    assert app.invoke(None, thread("t"))["node"] == "plan"


def test_a_resumed_run_asks_for_its_callers_reach_again() -> None:
    """**The property, without a server.** The run pauses holding references only, the caller's
    grant is revoked, and the resumed node finds no reach. Nothing in the saved state could have
    told it otherwise.

    Delete this and the in-memory half of the leaf's proof is gone; the PostgreSQL test below is
    skipped wherever no server is set."""
    directory = Directory()
    app = a_graph(directory, GuardedSaver(InMemorySaver(), principal_id=OWNER))

    app.invoke(started(), thread("t"))
    directory.revoke(OWNER)
    app.invoke(None, thread("t"))

    assert directory.seen == [False]


def test_a_saver_bound_to_nobody_is_refused() -> None:
    """A saver for an empty principal would own every run it saved. Delete this and the check
    becomes a comment."""
    with pytest.raises(CheckpointerError, match="nobody"):
        GuardedSaver(InMemorySaver(), principal_id="  ")


def test_the_pool_is_built_from_the_configuration_and_bounded_at_the_budgeted_figure() -> None:
    """The saver's own constructor prepares every statement, so the pool is built here, and its
    ceiling is the figure `brain.ops.connections` budgets for the checkpointer half of a worker.

    Delete this and `max_size` can drift from the budget, or `prepare_threshold` can be left to
    the library's default, and nothing else would say so."""
    settings = checkpointer_pool_settings(
        CheckpointerConfig(url="postgresql://brain@db:5432/brain")
    )
    kwargs = settings["kwargs"]

    assert settings["max_size"] == WORKER_CHECKPOINTER_CONNECTIONS
    assert settings["min_size"] == 1
    assert isinstance(kwargs, dict)
    assert kwargs["prepare_threshold"] is None
    assert kwargs["autocommit"] is True
    # Placed after connecting, never as a libpq startup option, which PgBouncer refuses.
    assert "options" not in kwargs
    conn = RecordingConnection()
    configure = settings["configure"]
    assert callable(configure)
    configure(conn)
    assert conn.executed == [(SEARCH_PATH_SQL, (CHECKPOINT_SCHEMA,))]
    assert conn.committed


def test_a_pool_is_not_built_on_the_pooler() -> None:
    """Delete this and the pool can be built on a URL `connection_refusals` would refuse, and the
    pipelining the library does inside each write goes across a backend swap."""
    with pytest.raises(CheckpointerError, match="pooler"):
        checkpointer_pool_settings(
            CheckpointerConfig(url="postgresql://brain@pgbouncer:5432/brain")
        )


# ------------------------------------------------------------------------ with a server
def _server() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("BRAIN_DATABASE_URL") or None


@contextmanager
def scratch(database: str) -> Iterator[str]:
    from tests.fixtures.scratch_postgres import drop, fresh

    if _server() is None:
        pytest.skip("DATABASE_URL is unset, so there is no server to save to; CI always sets it")
    url = fresh(database)
    try:
        yield url
    finally:
        drop(database)


@pytest.mark.needs_db
def test_the_install_creates_the_savers_tables_secured_and_is_safe_to_run_again() -> None:
    """The library's tables appear in the schema the security sweep reads, every one reports
    row-level security, none carries a policy, and a second run succeeds rather than raising.
    Row-level security is switched off between the runs, so the second run is seen turning it
    back on rather than finding it already set.

    Delete this and the install is verified by the absence of an exception."""
    from tests.fixtures.scratch_postgres import sql

    with scratch("brain_cpstore_install") as url:
        config = CheckpointerConfig(url=url)
        first = install_checkpointer(config)
        for (name,) in sql(
            url,
            "SELECT tablename FROM pg_tables WHERE schemaname = %s AND tablename LIKE %s",
            CHECKPOINT_SCHEMA,
            f"{SAVER_TABLE_PREFIX}%",
        ):
            sql(url, f"ALTER TABLE {CHECKPOINT_SCHEMA}.{name} DISABLE ROW LEVEL SECURITY")
        second = install_checkpointer(config)
        rows = sql(
            url,
            "SELECT c.relname, c.relrowsecurity, "
            "(SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relkind = 'r' AND c.relname LIKE %s",
            CHECKPOINT_SCHEMA,
            f"{SAVER_TABLE_PREFIX}%",
        )

    assert any("row-level security is on" in line for line in first)
    assert any("row-level security is on" in line for line in second)
    assert {name for name, _, _ in rows} >= {"checkpoints", "checkpoint_writes", "checkpoint_blobs"}
    assert all(secured is True for _, secured, _ in rows)
    assert all(policies == 0 for _, _, policies in rows)


@pytest.mark.needs_db
def test_a_real_graph_saved_to_postgres_resumes_after_a_restart_with_its_reach_asked_again() -> (
    None
):
    """**The leaf.** A real graph is saved to PostgreSQL through the guarded saver and pauses
    before the node that reads. The pool is closed, as a process that died would leave it. The
    caller's grant is revoked. A new pool and a new saver resume the run, and the resumed node
    finds no reach. A second run on another thread, not revoked, finds its reach, so the first
    result is the revocation and not a broken graph. The saved rows are read back and hold the
    references and no entitlement.

    Delete this and every claim that the checkpointer works on PostgreSQL, and that a resume
    cannot keep revoked reach, rests on an in-memory saver."""
    from tests.fixtures.scratch_postgres import sql

    with scratch("brain_cpstore_resume") as url:
        config = CheckpointerConfig(url=url)
        install_checkpointer(config)
        directory = Directory()

        before = checkpointer_pool(config)
        before.open()
        try:
            app = a_graph(directory, guarded_saver(before, principal_id=OWNER))
            app.invoke(started(), thread("revoked"))
            app.invoke(started(), thread("kept"))
        finally:
            before.close()

        directory.revoke(OWNER)
        directory.grants[OWNER + "_kept"] = holding(OWNER, READ)

        after = checkpointer_pool(config)
        after.open()
        try:
            resumed = a_graph(directory, guarded_saver(after, principal_id=OWNER))
            finished = resumed.invoke(None, thread("revoked"))
            revoked_saw = list(directory.seen)
            directory.grants[OWNER] = holding(OWNER, READ)
            resumed.invoke(None, thread("kept"))
            stranger = guarded_saver(after, principal_id=STRANGER)
            hidden = stranger.get_tuple(thread("kept"))
        finally:
            after.close()

        # Written out rather than built from `CHECKPOINT_SCHEMA`: the schema being `agent` is
        # asserted in `test_checkpoints.py`, and a literal here keeps the query a literal.
        saved = sql(url, "SELECT thread_id, count(*) FROM agent.checkpoints GROUP BY thread_id")
        channels = sql(url, "SELECT DISTINCT channel FROM agent.checkpoint_writes")

    assert finished["node"] == "fetch"
    assert revoked_saw == [False]
    assert directory.seen == [False, True]
    assert hidden is None
    assert dict(saved).keys() == {"revoked", "kept"}
    assert {channel for (channel,) in channels} <= {
        "run_id",
        "principal_id",
        "node",
        "step",
        "record_refs",
        "branch:to:plan",
        "branch:to:fetch",
    }
