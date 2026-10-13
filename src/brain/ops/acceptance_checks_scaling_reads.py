"""Install checks for the three scaling mechanisms that already run: ledger partitions, the console
read replica's routing, and the spend report's refresh and its staleness.

Each was built and wired on main and no check on an install named it. None of them needs the
scaling trigger to have fired: the partitions exist on every install, the replica's routing is
a decision made by `ConsoleReads` whether or not a replica is configured, and the spend report
is rebuilt daily on every install.

**The partitions are read from the catalogue the worker made them in, and the check never makes
one.** Creating a partition is data definition the check's transaction would hold but the worker
does in its own, and running the worker's maintenance from a check would leave months behind on a
server. So the check asks the catalogue which months are attached to `obs.request_telemetry`, holds
that against `months_ahead` of this instant, and says NOT RUN when the worker has not yet made
them, which is true of an install that has not had its first daily run. See
`A_CHECK_READS_THE_PARTITIONS_THE_WORKER_MADE_AND_MAKES_NONE`.

**The replica is two session factories the check labels, both over the check's transaction.** A
second server is not needed to prove a routing decision: `ConsoleReads` is given a replica factory
and a lag the check says, and what is asked is where a display read goes, where a decision goes,
what a page carries when the copy is behind, and where a read goes when the copy is further behind
than a page may be. The routing is held last in the check, because a read-only read leaves the
transaction read-only, which is the end of anything it would still write.

**The staleness is read through the route at two instants.** The daily view is rebuilt in the
check's transaction, the report is read at once and says it is live, and read again at an instant
past the stale threshold and says so, with the instant it is as of on the figure each time.

Task ids: M36.1.1.1, M36.1.2.2, M36.1.3.2
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy import text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_operations_console import asking_as, console_for
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2120

A, _B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why the partition check makes none.
A_CHECK_READS_THE_PARTITIONS_THE_WORKER_MADE_AND_MAKES_NONE: Final = (
    "Months are created by the worker's retention run in its own transactions. A check that ran "
    "that maintenance would leave partitions on a server it was only meant to read, so it reads "
    "the catalogue and says it did not run where the worker has not made the months yet."
)

# ----------------------------------------------------------------------- the sentences
THE_MONTHS_ARE_NOT_MADE_YET: Final = (
    "the worker has not made this install's ledger partitions for the months ahead yet, which its "
    "daily retention run does; this check reads them and never makes one"
)
THE_READ_AUTHORITY: Final = "read:usage"

#: How far behind the check says the replica is, for a copy within a page's threshold, past it,
#: and past where the primary answers instead.
WITHIN: Final = timedelta(seconds=1)
BEHIND: Final = timedelta(seconds=60)
FURTHER_THAN_A_PAGE_MAY_BE: Final = timedelta(hours=1)


# ------------------------------------------------------------------ 1. the ledger's partitions
@check(
    leaves=("M36.1.1.1",),
    sentence=(
        "The metadata ledger is partitioned by month in plain SQL, and the catalogue shows a "
        "partition attached for this month and for each month ahead the worker keeps made, each "
        "named for its month, beside the default partition that takes a row no month claims."
    ),
)
async def the_ledger_has_a_partition_for_this_month_and_each_one_ahead(h: Harness) -> None:
    from brain.ops.ledger_partitions import DEFAULT_PARTITION, LEDGER, Month, months_ahead

    found = (
        await h.execute(
            text(
                "SELECT c.relname FROM pg_catalog.pg_inherits AS i "
                "JOIN pg_catalog.pg_class AS c ON c.oid = i.inhrelid "
                "WHERE i.inhparent = CAST(:ledger AS regclass)"
            ).bindparams(ledger=LEDGER)
        )
    ).all()
    names = {str(name) for (name,) in found}
    if DEFAULT_PARTITION.split(".", 1)[1] not in names:
        raise CheckFailedError("the ledger has no default partition for a row no month claims")
    attached = {month for name in names if (month := Month.named(name)) is not None}
    wanted = months_ahead(datetime.now(UTC))
    if not attached:
        raise CheckNotRunError(THE_MONTHS_ARE_NOT_MADE_YET)
    missing = [one.name for one in wanted if one not in attached]
    if missing:
        raise CheckFailedError("the ledger lacked a partition for a month the worker keeps made")
    kind = (
        await h.execute(
            text(
                "SELECT partstrat FROM pg_catalog.pg_partitioned_table "
                "WHERE partrelid = CAST(:ledger AS regclass)"
            ).bindparams(ledger=LEDGER)
        )
    ).scalar_one_or_none()
    if kind != "r":
        raise CheckFailedError("the ledger is not partitioned by range")


# ------------------------------------------------------------- 2. the console read replica
@check(
    leaves=("M36.1.2.2",),
    sentence=(
        "With a replica configured, a console page's read is served from it and carries no banner "
        "while it is within a page's threshold, carries a banner saying how far behind it is "
        "when it is behind, and is answered by the primary when the copy is further behind than a "
        "page may be; a read that decides something is answered by the primary whatever the copy."
    ),
)
async def a_console_read_goes_to_the_replica_and_a_decision_never_does(h: Harness) -> None:
    from brain.console.read_replica import LagReading, Purpose
    from brain.ops.replica_store import ConsoleReads

    def labelled(name: str) -> Any:
        def make() -> Any:
            made = h.sessions()
            made.info["served_by"] = name
            return made

        return make

    lag = {"now": WITHIN}

    async def measured(_session: Any) -> LagReading:
        return LagReading(in_recovery=True, replay_age=lag["now"], caught_up=False)

    async def who(session: Any) -> str:
        return str(session.info["served_by"])

    reads = ConsoleReads(labelled("primary"), labelled("replica"), measure=measured)
    # A cast at the boundary: the routing only calls the factories and reads the session's `info`.
    at = datetime.now(UTC)
    current = await reads.read(who, now=at, purpose=Purpose.DISPLAY)
    if current.value != "replica" or current.banner is not None:
        raise CheckFailedError("a console read was not served from the replica within threshold")
    decided = await reads.read(who, now=at, purpose=Purpose.DECISION)
    if decided.value != "primary" or decided.banner is not None:
        raise CheckFailedError("a read that decides something was answered by the replica")

    lag["now"] = BEHIND
    later = at + timedelta(minutes=1)
    behind = await reads.read(who, now=later, purpose=Purpose.DISPLAY)
    if behind.value != "replica" or behind.banner is None or behind.banner.behind_seconds < 60:
        raise CheckFailedError("a read from a replica that is behind did not say how far")
    lag["now"] = FURTHER_THAN_A_PAGE_MAY_BE
    gone = await reads.read(who, now=later + timedelta(minutes=1), purpose=Purpose.DISPLAY)
    if gone.value != "primary" or gone.banner is not None:
        raise CheckFailedError(
            "a read from a replica too far behind was not answered by the primary"
        )
    alone = ConsoleReads(labelled("primary"))
    if (await alone.read(who, now=at, purpose=Purpose.DISPLAY)).value != "primary":
        raise CheckFailedError("an install with no replica did not answer from its primary")


# ------------------------------------------------------- 3. the spend report's refresh and age
@check(
    leaves=("M36.1.3.2",),
    sentence=(
        "The worker's daily schedule names a run that rebuilds the spend view; once it is rebuilt "
        "the Spend report says it is live and as of the rebuild, and read after the stale "
        "threshold it says it is stale, with the instant it is as of on the figure each time."
    ),
)
async def the_spend_report_is_rebuilt_daily_and_says_how_old_it_is(h: Harness) -> None:
    from brain.ops.controls import CONTROLS
    from brain.ops.schedule_runner import RUNNERS
    from brain.ops.spend_store import refresh_spend_daily
    from brain.report_routes import spend

    named = [one for one in RUNNERS if one.name == "spend_report_refresh"]
    if len(named) != 1 or named[0].run is None:
        raise CheckFailedError("the worker's schedule does not run the spend view's rebuild")
    if all(one.name != "spend_report_refresh" for one in CONTROLS):
        raise CheckFailedError("the spend view's rebuild is not a control the schedule lists")

    await h.found_departments()
    reader = h.principal(A, "spend_age")
    await h.person(reader, department=A, grants=((THE_READ_AUTHORITY, Scope.unrestricted()),))
    async with h.sessions() as session:
        rebuilt = await refresh_spend_daily(session)
        await session.commit()
    console = console_for(h)
    asking = await asking_as(h, reader)
    fresh = await spend(console.request(), asking)
    if not fresh.built or fresh.as_of is None or fresh.freshness != "live":
        raise CheckFailedError("a freshly rebuilt spend report did not say it was live")
    if abs((fresh.as_of - rebuilt).total_seconds()) > 1:
        raise CheckFailedError("the spend report was not as of the rebuild that made it")
    from brain.console.spend_report_view import STALE_AFTER

    aged = replace(asking, now=rebuilt + STALE_AFTER + timedelta(hours=1))
    stale = await spend(console.request(), aged)
    if stale.freshness != "stale" or stale.as_of != fresh.as_of:
        raise CheckFailedError("an old spend report did not say it was stale, as of when it was")
