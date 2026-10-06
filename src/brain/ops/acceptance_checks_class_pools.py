"""The install's check that a batch job holding its share cannot take a person's connection.

`brain.ops.class_pools` splits the database's slots three ways and moves each process onto its
class's pool while the class pooler runs. The property that is the whole point of it is not that
three pools exist but that **a batch job holding every connection its class has leaves an
interactive transaction running at once**, so the check holds batch's whole share and asks.

**It asks three things, because each half alone passes for a pooler that isolates nothing.** That
an interactive transaction runs at once while batch's share is held is satisfied by a batch pool
larger than its share, where nothing was really held. So it also asks that one more batch
transaction does not get a connection while the share is held, which proves the share was full,
and that it does once the share is let go, which proves batch work still proceeds and that the
refusal before was the pool and not a broken login. A pooler that refused everything would fail
the first and the last; one that bounded nothing would fail the second.

**Where the class pooler is not running for this release the check is not run, and says so.**
That is a server with no room for it, or a deploy whose step has not reported yet, and in both
every process is on the pooler it had, which is the design rather than a fault
(`A_PROCESS_USES_ITS_CLASS_POOLER_ONLY_WHEN_THIS_RELEASE_SAW_IT_RUNNING`). Where batch work is
holding its share when the check runs, it cannot hold the share itself, and that is not run too:
the check never waits behind somebody's sync to report on it.

It connects from the worker the suite runs in, over the class URLs derived from the worker's own
application URL, so it reaches the pooler by the route a moved process does. Its connections run
`SELECT 1` and nothing else, so it writes nothing and reads nothing anybody keeps.

Task ids: M22.2.2
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Final

import structlog

from brain.ops.acceptance import CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness
from brain.ops.admission import WorkloadClass
from brain.ops.class_pools import POOLS, class_url_of, observed_running

if TYPE_CHECKING:
    from psycopg import AsyncConnection

#: Where this module's check stands on the Install page: after the capacity checks (140), whose
#: classes these pools are for. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 145

log = structlog.get_logger(__name__)

#: How long "at once" is for a transaction on a pool with room: a connection and `SELECT 1`
#: through a pooler on the same server, with a margin for a server busy at deploy time.
AT_ONCE_SECONDS: Final = 5.0

#: How long a batch transaction is watched for while batch's share is held. A pooler hands a free
#: connection over in milliseconds, so two seconds without one is a client waiting in its queue.
HELD_SHARE_WAIT_SECONDS: Final = 2.0

#: Said where this release's class pooler is not reported running.
NOT_RUNNING_HERE: Final = (
    "the connection pools per workload class are not reported running on this release, so every "
    "process is on the pooler it already had; the deploy step reports them after every deploy "
    "that starts them"
)

#: Said where the worker's application URL does not go through the transaction pooler.
NOT_THROUGH_THE_POOLER: Final = (
    "the worker's application connection does not go through the transaction pooler, so no "
    "process here is moved onto the class pools and there is nothing to ask them"
)

#: Said where batch work already holds connections the check needs to hold.
BATCH_IS_BUSY: Final = (
    "batch work was holding the batch class's connections when the check ran, so its share "
    "could not be held for the check; it is asked again on the next run"
)

#: Said where the batch pool refused a connection outright.
THE_BATCH_POOL_REFUSED: Final = (
    "the batch class's pool refused a connection the check asked for within its share"
)

#: Said where an interactive transaction did not run while batch's share was held.
BATCH_TOOK_THE_REQUEST_PATHS_CONNECTION: Final = (
    "with the batch class holding its whole share of connections, an interactive transaction "
    "did not run at once"
)

#: Said where one more batch transaction got a connection while the share was held.
THE_BATCH_SHARE_IS_NOT_BOUNDED: Final = (
    "with the batch class holding its whole share of connections, one more batch transaction "
    "still got one, so the share bounds nothing"
)

#: Said where batch work did not proceed once its share was let go.
BATCH_DID_NOT_PROCEED: Final = (
    "once the batch class's share was let go, a batch transaction did not run at once"
)


def targets(h: Harness) -> Mapping[WorkloadClass, str] | None:
    """The class URLs a process moved from the worker's application URL would use, or None."""
    url = h.settings.database_url
    found = {
        one: class_url_of(url, one) for one in (WorkloadClass.INTERACTIVE, WorkloadClass.BATCH)
    }
    if any(value is None for value in found.values()):
        return None
    return {one: value for one, value in found.items() if value is not None}


async def _transaction(url: str, timeout: float) -> AsyncConnection:
    """A connection inside an open transaction that has run `SELECT 1`, so it holds a server
    connection through a transaction pooler until it ends. Closed again on any failure."""
    import psycopg

    from brain.db import libpq_conninfo

    conn = await asyncio.wait_for(
        psycopg.AsyncConnection.connect(libpq_conninfo(url), prepare_threshold=None), timeout
    )
    try:
        await asyncio.wait_for(conn.execute("SELECT 1"), timeout)
    except BaseException:
        with contextlib.suppress(Exception):
            await conn.close()
        raise
    return conn


async def _runs(url: str, timeout: float) -> bool:
    """Whether one transaction gets a connection and runs within `timeout`, ending it either way."""
    import psycopg

    try:
        conn = await _transaction(url, timeout)
    except (TimeoutError, psycopg.Error, OSError):
        return False
    with contextlib.suppress(Exception):
        await conn.rollback()
    with contextlib.suppress(Exception):
        await conn.close()
    return True


@check(
    leaves=("M22.2.2",),
    sentence=(
        "With the batch class holding every connection its share of the database allows, an "
        "interactive transaction still runs at once and one more batch transaction waits; once "
        "the share is let go, batch work runs again."
    ),
)
async def a_batch_job_holding_its_share_cannot_take_a_persons_connection(h: Harness) -> None:
    import psycopg

    if not await observed_running(h.sessions, commit=h.settings.resolved_commit()):
        raise CheckNotRunError(NOT_RUNNING_HERE)
    urls = targets(h)
    if urls is None:
        raise CheckNotRunError(NOT_THROUGH_THE_POOLER)
    batch, interactive = urls[WorkloadClass.BATCH], urls[WorkloadClass.INTERACTIVE]
    held: list[AsyncConnection] = []
    try:
        for _ in range(POOLS.batch):
            try:
                held.append(await _transaction(batch, AT_ONCE_SECONDS))
            except TimeoutError as error:
                raise CheckNotRunError(BATCH_IS_BUSY) from error
            except (psycopg.Error, OSError) as error:
                raise CheckFailedError(THE_BATCH_POOL_REFUSED) from error
        interactive_ran = await _runs(interactive, AT_ONCE_SECONDS)
        one_more_ran = await _runs(batch, HELD_SHARE_WAIT_SECONDS)
    finally:
        for conn in held:
            with contextlib.suppress(Exception):
                await conn.close()
    batch_ran_after = await _runs(batch, AT_ONCE_SECONDS)
    log.info(
        "acceptance.class_pools",
        held=len(held),
        interactive_ran=interactive_ran,
        one_more_ran=one_more_ran,
        batch_ran_after=batch_ran_after,
    )
    if not interactive_ran:
        raise CheckFailedError(BATCH_TOOK_THE_REQUEST_PATHS_CONNECTION)
    if one_more_ran:
        raise CheckFailedError(THE_BATCH_SHARE_IS_NOT_BOUNDED)
    if not batch_ran_after:
        raise CheckFailedError(BATCH_DID_NOT_PROCEED)
