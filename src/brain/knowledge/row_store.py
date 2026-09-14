"""The `RowSource` that runs a compiled statement against the application's own pool.

`brain.knowledge.rows` builds the statement and decides what may be in it. This runs it, and
that is the whole of the split: the module holding the policy holds no connection, and this
one holds a connection and no policy. It is the arrangement `brain.ops.limits` and
`brain.ops.limit_store` are built on, and the reason is the case that is always wrong, which
here is the empty one: a query builder that opened a socket could not be tested on a caller
who reaches nothing.

**This is the first implementation of the protocol, and until 2026-09-07 there could not be
one.** `RowSource.rows` was synchronous and `brain.session` builds an `AsyncEngine`, so no
implementation could use the pool the application already had, and `brain.app` therefore
registered no row tools and logged `tools=0` beside a readiness check saying tools were fine.
Making the protocol awaitable removed the mismatch; this is what the removal was for.

**It adds nothing to the statement it is given.** No filter, no limit, no ordering, no scope.
Everything about what may come back was decided by `compile_row_query` under the caller's
entitlements, and a source that appended anything would be a second opinion about a permission
question, formed by something with a connection and no idea whose reach it was running under.
`SOURCE_RUNS_THE_STATEMENT_AND_DECIDES_NOTHING` says so where somebody would otherwise add a
`LIMIT` for safety.

**One session per read, from the factory rather than a session handed in.** A session held
across reads is a transaction held across reads, and two callers sharing one would see each
other's uncommitted work; taking the factory means the lifetime is this function's and the
pool's checkout is as short as the statement. It is the same reason `request_session` exists
rather than a module-level session.

**A query's settings run first, in the same session, and that is not a second opinion.**
`RowQuery.settings` is how a statement carries the session settings a row-level security policy
reads, and `know.chunk`'s policy reads two. They are written with `set_config(..., true)`, which
lasts for one transaction, so the only place they can do anything is the transaction the
statement runs in: run through a second session they land on another connection, or on this
one inside a transaction that has already ended, and the policy sees NULL and admits
company-visible chunks only. That fails closed and silently, which is why
`SETTINGS_RUN_IN_THE_STATEMENTS_OWN_TRANSACTION` is written down. The source still decides
nothing: the settings were built beside the statement, under the caller's reach, and are run
as they arrived.

Rejected: a session-lifetime `SET` issued when a connection is checked out. PgBouncer runs in
transaction mode here, so a session setting outlives the request and lands on whoever takes the
connection next, which is the trap `brain.knowledge.search._set_config` records.

**Rows come back as plain mappings.** `read_rows` builds its records from `query.columns`, so
a driver handing back extra keys cannot widen an answer, and this returns what the driver gave
rather than filtering it: filtering here would be a second place that decides what a record
holds, and the first place is the one with the projection in front of it.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.knowledge.rows import RowQuery

#: Why this adds nothing to the statement it was handed.
SOURCE_RUNS_THE_STATEMENT_AND_DECIDES_NOTHING = (
    "Everything about what may come back was decided by compile_row_query under the caller's "
    "entitlements: the columns are the compiled projection, the predicate is the caller's "
    "scope, and the bound is the request's own limit. A source that appended a filter, a "
    "limit or an ordering would be forming a second opinion about a permission question, "
    "from a module that holds a connection and does not know whose reach it is running "
    "under. The one thing it may do is refuse to run a statement the compiler already said "
    "cannot return a row, and even that is done by the caller rather than here."
)

#: Why the settings a query carries share its session and its transaction.
SETTINGS_RUN_IN_THE_STATEMENTS_OWN_TRANSACTION = (
    "A query's settings are set_config(..., true) statements, which last for one transaction, "
    "and the row-level security policy that reads them is evaluated inside the statement. Run "
    "in another session, after the statement, or across a commit, they set nothing the policy "
    "can see, current_setting returns NULL, and the policy admits company-visible rows only. "
    "Nothing raises, so the only symptom is a department's documents missing for the people "
    "in it."
)


class SessionRowSource:
    """Runs compiled row statements on the application's async pool.

    Constructed with a session factory rather than a session, so the transaction lives for
    one read. See the module docstring.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        """Run one compiled statement and hand back what came out, keyed by label.

        `mappings()` rather than tuples, because `read_rows` looks its columns up by name and
        a positional result would make the record depend on the order the projection happened
        to compile in.

        No transaction is committed, because nothing is written. The session's context manager
        rolls back on the way out, which for a read is the cheapest correct thing and means a
        statement that somehow modified something could not persist it.

        The query's settings run first, on this session, so they share the transaction the
        session begins on its first statement. See
        `SETTINGS_RUN_IN_THE_STATEMENTS_OWN_TRANSACTION`.
        """
        async with self._sessions() as session:
            for setting in query.settings:
                await session.execute(setting)
            result = await session.execute(query.statement)
            return [dict(row) for row in result.mappings().all()]
