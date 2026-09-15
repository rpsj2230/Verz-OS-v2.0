"""Where a graph's saved state is written, and the two doors every save and every resume pass.

`brain.ops.checkpoints` decides where the state may go and what it may hold, and opens nothing.
This module is the half that holds a connection, in the split `brain.ops.limits` and
`brain.ops.limit_store` make and for the same reason: a module that opens a socket cannot be
tested for the case that is always wrong, so every decision here is a call to that one.

**The saver is the library's own, and it is never built from a connection string.**
`PostgresSaver.from_conn_string` opens its connection with `prepare_threshold=0`, which
`CheckpointerConfig` refuses, and the refusal is not a preference: a statement prepared on one
backend and executed on another is the pooler failure this repository has now written down
four times. So the pool is built here from the configuration, bounded at
`WORKER_CHECKPOINTER_CONNECTIONS`, which is the figure `brain.ops.connections` budgets for this
half of a worker. See `checkpointer_pool_settings`.

**The library pipelines each write inside one checkout whatever it is told**, and that is safe
for a reason worth stating rather than assuming. `PostgresSaver.put` enters pipeline mode on the
connection it has checked out when libpq supports it, and releases the connection afterwards.
A pipeline on one connection that stays on one backend is correct; the thing
`CheckpointerConfig.pipeline` refuses is a pipeline across a pooler that swaps the backend under
it. `connection_refusals` is what keeps the pooler out of the URL, so the pipelining is sound
here and would not be behind PgBouncer.

**Every save passes `checkpoint_refusals`, and every read passes ownership.** See
`A_SAVER_THAT_CHECKS_NOTHING_IS_A_COPY_OF_EVERYTHING`. `GuardedSaver` wraps the library's saver
and is the only saver this module hands out. A write naming a channel nobody declared, a value
that is not a scalar reference, or an owner other than the caller is refused before a row is
written, and a checkpoint belonging to somebody else reads as no checkpoint at all, so a thread
id somebody guessed is indistinguishable from one that does not exist.

**A resumed run cannot keep reach its caller has lost, and that is what the state's shape buys
rather than a step anybody performs.** The state holds references and a principal's
identifier. It holds no entitlement set and no scope, and `A_CHECKPOINT_CANNOT_CARRY_A_REACH` is
the refusal that keeps it that way. So a node that needs a record after a resume has to ask for
the caller's reach again, through `brain.ops.automation.flow_reach` or the gate, at that
instant. The test proving it saves a real graph to PostgreSQL, revokes the caller's grant,
resumes on a new pool as a restarted process would, and watches the resumed node find nothing.

**An error is not saved, and a resume runs the failed task again.** See
`brain.ops.checkpoints.THE_FRAMEWORKS_CHANNELS_OBEY_THE_SAME_RULES`. An exception's message is
whatever the failing code put in it. The library re-runs a task whose saved write is an error,
and it re-runs one with no saved write, so dropping the write changes nothing a resume does and
keeps a record identifier out of a store with its own retention. Measured both ways against
the library's in-memory saver before this was written.

**The tables are the library's, created by its own setup, and secured by what the catalogue
gained.** `PostgresSaver.setup` records the migrations it has applied in a table of its own and
applies only the ones after it, so unlike the queue driver's schema command it is safe to run
on every deploy. `install_checkpointer` runs it and then enables row-level security on every
table carrying `SAVER_TABLE_PREFIX` in `CHECKPOINT_SCHEMA`, with no policy, for the reason
`brain.ops.queue.driver_rls_statements` gives: PostgreSQL exempts the owner, which is the role
the saver connects as, and a policy of `USING (true)` would grant everything straight back.
Rejected: migration 0042 transcribing those tables. A transcribed CREATE forks at the library's
next release with no error until a query names a column that is not there, which is the
argument `brain.ops.queue.THE_QUEUE_SCHEMA_IS_NOT_ALEMBICS` already won.

**Synchronous only, and an asynchronous run fails loudly rather than unguarded.** The library's
base class raises `NotImplementedError` for the `a`-prefixed methods, and `GuardedSaver` does not
provide them, so a graph run with `ainvoke` stops at its first save. Delegating them to the
library's saver would be the easy change and would put every save of that run past both doors.

What is not here: a graph. Nothing under `src/brain` compiles one yet, so `guarded_saver` is
called by the tests that prove it and by nothing else, and `install_checkpointer` is called by
`python -m brain.ops.worker --install-checkpointer`. The agent loop that hands this a graph is
its own leaf.

Task ids: M17.2.1, M32.4.1.2
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Final, cast

import psycopg
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from brain.db import libpq_url
from brain.ops.checkpoints import (
    ERROR_CHANNEL,
    CheckpointerConfig,
    CheckpointerError,
    CheckpointHeader,
    checkpoint_refusals,
    connection_refusals,
    may_resume,
    owner_of,
)
from brain.ops.connections import WORKER_CHECKPOINTER_CONNECTIONS
from brain.ops.queue import QueueError, driver_rls_statements

#: Why the library's saver is never handed out on its own.
A_SAVER_THAT_CHECKS_NOTHING_IS_A_COPY_OF_EVERYTHING: Final = (
    "The library's saver writes whatever the graph's state holds and reads back whatever a "
    "thread id names. Handed out directly, the allowlist in brain.ops.checkpoints is a function "
    "nothing calls and a thread id is a bearer token. So the saver is wrapped: a save is refused "
    "before a row is written when its state is not references owned by the caller, and a read "
    "of a run the caller does not own answers exactly as a read of a run that does not exist."
)

#: Why one refusal on a thread refuses every later save on it.
A_REFUSED_RUN_SAVES_NOTHING_MORE: Final = (
    "The graph library saves in the background by default, so a save this saver refuses does "
    "not stop the run: the loop carries on, later steps save again, and the refusal surfaces "
    "only when the run ends. Measured on 2026-09-15, a run whose input held a list was refused "
    "twice and then saved its next step, leaving a checkpoint whose earlier channels, its owner "
    "among them, had never been written. So a refusal is remembered per thread and every later "
    "save or write on that thread is refused too, whatever mode the graph was run in. A refused "
    "run saves nothing more, and the run that could not be saved is the one that cannot resume."
)

#: What every table the library's setup creates is called. Anything else it creates stops the
#: install, for the reason `brain.ops.queue.unattributable_tables` gives about the queue's.
SAVER_TABLE_PREFIX: Final = "checkpoint"


def _thread_of(config: RunnableConfig) -> str:
    return str(config.get("configurable", {}).get("thread_id", ""))


def checkpointer_pool_settings(config: CheckpointerConfig) -> Mapping[str, object]:
    """Exactly what the saver's pool is built from. Refuses a connection the saver may not use.

    A function rather than an argument list, for the reason `brain.ops.queue.driver_pool_settings`
    is one: every value is a decision argued somewhere, and assembled inline they are literals
    in a constructor call, which is where one of them stops being passed.

    `max_size` is `WORKER_CHECKPOINTER_CONNECTIONS` and no other figure. `min_size` is one, so
    an idle worker is not holding its whole allowance against a database it shares.
    """
    refusals = connection_refusals(config.url)
    if refusals:
        msg = "this connection is not one a checkpointer may use: " + "; ".join(refusals)
        raise CheckpointerError(msg)
    return {
        "conninfo": libpq_url(config.url),
        "min_size": 1,
        "max_size": WORKER_CHECKPOINTER_CONNECTIONS,
        "kwargs": {
            "autocommit": True,
            "prepare_threshold": config.prepare_threshold,
            "row_factory": dict_row,
            "options": config.connect_options,
        },
    }


def checkpointer_pool(config: CheckpointerConfig) -> ConnectionPool[Any]:
    """The saver's pool, built and not yet opened. The caller opens it and closes it."""
    settings = checkpointer_pool_settings(config)
    return ConnectionPool(
        conninfo=str(settings["conninfo"]),
        min_size=cast(int, settings["min_size"]),
        max_size=cast(int, settings["max_size"]),
        kwargs=cast(dict[str, Any], settings["kwargs"]),
        open=False,
    )


class GuardedSaver(BaseCheckpointSaver[str]):
    """The library's saver behind the two doors. See the module docstring."""

    def __init__(self, inner: BaseCheckpointSaver[str], *, principal_id: str) -> None:
        if not principal_id.strip():
            msg = "a saver for nobody would own every run it saved and could resume any of them"
            raise CheckpointerError(msg)
        super().__init__(serde=inner.serde)
        self.inner = inner
        self.principal_id = principal_id
        #: Each thread a save was refused on, with the reason the first refusal gave. See
        #: `A_REFUSED_RUN_SAVES_NOTHING_MORE`.
        #:
        #: **The first reason is kept and repeated, because the library saves in the background
        #: and which refusal reaches the caller first is a race.** It was a set, so a later save
        #: on a refused thread raised "already refused" with no reason, and on a run where that
        #: later save surfaced first the caller never learnt what was refused. CI caught it on
        #: 2026-09-15 as a test that passed on one run and failed on the next.
        self.refused_threads: dict[str, str] = {}

    def _refuse_if_already_refused(self, config: RunnableConfig) -> None:
        thread = _thread_of(config)
        first = self.refused_threads.get(thread)
        if first is not None:
            msg = (
                f"a save on this run was already refused, so nothing more of it is saved. "
                f"The first refusal: {first} {A_REFUSED_RUN_SAVES_NOTHING_MORE}"
            )
            raise CheckpointerError(msg)

    def _refuse(self, config: RunnableConfig, message: str) -> CheckpointerError:
        self.refused_threads.setdefault(_thread_of(config), message)
        return CheckpointerError(message)

    def _owns(self, found: CheckpointTuple) -> bool:
        owner = owner_of(found.checkpoint["channel_values"])
        if not owner.strip():
            return False
        thread = _thread_of(found.config) or "unnamed"
        return may_resume(CheckpointHeader(run_id=thread, principal_id=owner), self.principal_id)

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        found = self.inner.get_tuple(config)
        return found if found is not None and self._owns(found) else None

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,  # noqa: A002
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        for found in self.inner.list(config, filter=filter, before=before, limit=limit):
            if self._owns(found):
                yield found

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        self._refuse_if_already_refused(config)
        values = checkpoint["channel_values"]
        refusals = list(checkpoint_refusals(values))
        if owner_of(values) != self.principal_id:
            refusals.append(
                "this checkpoint does not name the caller as its owner, and a saved run belongs "
                "to the principal it was started for"
            )
        if refusals:
            raise self._refuse(config, "this checkpoint was not saved: " + "; ".join(refusals))
        return self.inner.put(config, checkpoint, metadata, new_versions)

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self._refuse_if_already_refused(config)
        kept = [(channel, value) for channel, value in writes if channel != ERROR_CHANNEL]
        refusals = [
            refusal for channel, value in kept for refusal in checkpoint_refusals({channel: value})
        ]
        refusals.extend(
            "a node wrote a different owner into the run, and a saved run belongs to the "
            "principal it was started for"
            for channel, value in kept
            if channel == "principal_id" and value != self.principal_id
        )
        if refusals:
            raise self._refuse(config, "these writes were not saved: " + "; ".join(refusals))
        if kept:
            self.inner.put_writes(config, kept, task_id, task_path)

    def delete_thread(self, thread_id: str) -> None:
        latest = self.inner.get_tuple(
            {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        )
        if latest is not None and self._owns(latest):
            self.inner.delete_thread(thread_id)

    def get_next_version(self, current: str | None, channel: None) -> str:
        return self.inner.get_next_version(current, channel)


def guarded_saver(pool: ConnectionPool[Any], *, principal_id: str) -> GuardedSaver:
    """The only saver this module hands out: the library's, on this pool, behind both doors."""
    # A library boundary: the saver's constructor names a pool of dictionary-row connections,
    # which is what `checkpointer_pool_settings` configures and what the type cannot see.
    return GuardedSaver(PostgresSaver(cast(Any, pool)), principal_id=principal_id)


def _tables(connection: psycopg.Connection[Any], schema: str) -> frozenset[str]:
    rows = connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = %s", (schema,)
    ).fetchall()
    return frozenset(str(row[0]) for row in rows)


def install_checkpointer(config: CheckpointerConfig) -> tuple[str, ...]:
    """Create the schema, run the library's own setup, and secure what the catalogue gained.

    Safe on every deploy: the library's setup applies only the migrations it has not recorded,
    and the security step runs whatever the setup did, so a flag somebody turned off is turned
    back on. Returns what it did, one sentence per step.
    """
    checkpointer_pool_settings(config)
    dsn = libpq_url(config.url)
    schema = config.schema
    done: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        # Interpolated because DDL takes no parameters; `CheckpointerConfig` has already refused
        # a schema that `brain.db.SCHEMAS` does not name.
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        before = _tables(conn, schema)
    done.append(f"schema {schema!r} exists; it held {len(before)} table(s) before this ran")

    with psycopg.connect(
        dsn,
        autocommit=True,
        prepare_threshold=config.prepare_threshold,
        row_factory=dict_row,
        options=config.connect_options,
    ) as conn:
        PostgresSaver(cast(Any, conn)).setup()
    done.append("the library applied its own schema, at the version this image has of it")

    with psycopg.connect(dsn, autocommit=True) as conn:
        after = _tables(conn, schema)
        strangers = sorted(
            name for name in after - before if not name.startswith(SAVER_TABLE_PREFIX)
        )
        if strangers:
            msg = (
                f"the library's setup created {strangers}, which are not named "
                f"{SAVER_TABLE_PREFIX}*, so the security step has no basis to touch them"
            )
            raise CheckpointerError(msg)
        tables = tuple(sorted(name for name in after if name.startswith(SAVER_TABLE_PREFIX)))
        if not tables:
            msg = f"the library's setup left no {SAVER_TABLE_PREFIX}* table in {schema!r}"
            raise CheckpointerError(msg)
        try:
            statements = driver_rls_statements(tables, schema=schema)
        except QueueError as exc:
            raise CheckpointerError(str(exc)) from exc
        for statement in statements:
            conn.execute(statement)
        unsecured = conn.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relname = ANY(%s) AND NOT c.relrowsecurity",
            (schema, list(tables)),
        ).fetchall()
        if unsecured:
            msg = f"row-level security is still off on {sorted(str(r[0]) for r in unsecured)}"
            raise CheckpointerError(msg)
    done.append(f"row-level security is on for all {len(tables)} of {list(tables)}")
    return tuple(done)
