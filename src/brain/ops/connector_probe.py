"""Testing one connection when a person asks: who may ask, when the worker answers, and how often.

The Connectors page offers Test connection, and needs-rupash 107 decided how it works. A test is
one call to the source with the key this install holds, and **only the worker reads a source's
key** (`brain.ops.connector_sync_run.
THE_PROCESS_THAT_RUNS_A_CONNECTOR_READS_ITS_KEY_AND_NO_OTHER_DOES`), so the application cannot make
the call a person asked for. It writes the asking down; the worker
makes the call on its next pass and records what it found on the source's health, as an attempt
whose outcome is `probed` (`0142`). This module is the rule between the two, and the row the
application writes. `brain.ops.connector_probe_run` is the worker's half, and the SQL is
`brain.ops.connector_sync_store`'s.

**A test asked for is an instant in `ops.setting`, `connector.probe_requested.<source>`, and not a
message somebody has to consume.** It is `brain.ops.schedule_control`'s shape for a run asked for,
and for its reasons: the worker makes a test whose newest test started before the instant a person
asked, and the test's own row is what answers the request, so nothing is taken, marked or deleted,
a second press only moves the instant, and a worker that dies between reading the request and
making the call loses nothing. `0059`'s trigger on `ops.setting` appends a `setting` entry for every
press, with who pressed it, at what reach and for which request, so the asking is on the ledger;
the finding is the attempt's row, which nothing edits. See
`A_TEST_ASKED_FOR_IS_AN_INSTANT_AND_NOT_A_MESSAGE`.

**A test is one call under the source's verified ceiling, and three things can stop it being made.**
A source `brain.ops.connector_sync.plan_for` refuses is not called at all, and that includes one
whose ceiling nobody verified, so the application refuses to ask for it and says why. A source that
asked this install to wait is not called until the wait is over (`in_quota_wait`). And the one
call is admitted by `brain.ops.limits.check` against the source's windows for `PROBE_PRINCIPAL`,
counting this connection's own tests over the last day, so pressing the button cannot become a way
to spend the client's allowance. Tests of one connection are also spaced by `PROBE_SPACING`, which
the worker waits out rather than refuses. See `A_TEST_WAITS_FOR_THE_SOURCE_AND_FOR_ITS_OWN_SPACING`.

**The worker makes a test under the lock the scheduled read takes**, `connector_sync`'s advisory
lock, so a test and a read never spend the same source's allowance at the same time, and two
replicas never both answer one press.

Rejected: asking for a run of the `connector_sync` control through `schedule.run_requested`. That
is the existing door, and it would read every due source as well as the one pressed, and it starts
even while a person has paused the control, so a test would override a pause somebody set to stop
the reading.

Rejected: a probe table of its own. `0142` argues it: the screen's health is the newest attempt.

Task ids: M27.15.8
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from brain.connectors.manifest import ConnectorManifest
from brain.connectors.throttle import limits_for
from brain.ops.connector_store import Connection
from brain.ops.connector_sync import (
    PROBE_NOT_SENT_WHILE_WAITING,
    PROBE_REFUSED_FOR_NOW,
    ProbeVerdict,
    SyncOutcome,
    SyncState,
    plan_for,
    verdict_of,
)
from brain.ops.credentials import CONNECTOR_NAME_PATTERN
from brain.ops.limits import Limit, LimiterState
from brain.ops.setting_store import SettingState, put, read_namespace, values_under
from brain.tables.config import SettingType

# ------------------------------------------------------------------ written-down reasons
#: Why a request to test is stored as an instant.
A_TEST_ASKED_FOR_IS_AN_INSTANT_AND_NOT_A_MESSAGE: Final = (
    "The worker already knows when each connection was last tested, from the attempts. A test "
    "asked for is one more instant: make a test if none has started since. The test's own row "
    "answers the request, so nothing has to consume it, a worker that stops mid-pass loses "
    "nothing, and pressing twice asks for one test rather than two."
)

#: Why a test can wait, and what it waits for.
A_TEST_WAITS_FOR_THE_SOURCE_AND_FOR_ITS_OWN_SPACING: Final = (
    "A test spends one call of an allowance the client shares with every other integration. It is "
    "not made while the source has asked this install to wait, it is admitted by the source's "
    "verified windows counting this connection's tests over the last day, and tests of one "
    "connection are at least a minute apart. A press inside that minute is kept and answered when "
    "the minute is up, rather than refused, so the person sees a result without pressing again."
)

# ------------------------------------------------------------------------ the figures
#: `connector.probe_requested.<source>`, an ISO 8601 instant with its offset.
REQUEST_NAMESPACE: Final = "connector.probe_requested"

#: What a request row says about itself in `ops.setting.description`.
REQUEST_DESCRIPTION: Final = "When a person last asked for this source's connection to be tested"

#: The shortest time between two tests of one connection.
PROBE_SPACING: Final = timedelta(minutes=1)

#: How far back this connection's own tests are counted against the source's windows. The longest
#: window any verified ceiling has is a day (`brain.ops.limits.DAY_SECONDS`).
TESTS_COUNTED_OVER: Final = timedelta(days=1)

#: Whose share of a source's minute a test is counted against. Not a person: the subject of a
#: window, kept apart from `brain.ops.connector_sync.SYNC_PRINCIPAL` so a test never takes the
#: read's share.
PROBE_PRINCIPAL: Final = "worker.connector_probe"

#: The lock a test is made under: the scheduled read's, so the two never run together.
PROBE_LOCK: Final = "connector_sync"

# ------------------------------------------------------------------------ the sentences
#: What pressing Test connection agrees to, shown in the confirmation.
TESTING_A_SOURCE: Final = (
    "The worker makes one call to this source with the key this install holds, under the source's "
    "verified call ceiling, and records what it found on the source's health. Nothing the source "
    "sends is kept or shown."
)

#: What the page says while a test waits for the worker.
TEST_WAITING: Final = (
    "Waiting for the worker, which makes the call on its next pass, usually within a minute."
)

#: What the page says about a source nobody has tested.
NEVER_TESTED: Final = "Not tested yet."


class ProbeRequestError(Exception):
    """Raised for a request that could not be a row: a name no source has, or a naive instant."""


# ---------------------------------------------------------------------------- the rule
@dataclass(frozen=True)
class ProbeTarget:
    """One live connection, as the worker decides whether a test is owed on it."""

    connector: str
    #: When a test of this connection last started, or None when none has.
    last_probe_started: datetime | None


def owed_probes(
    requested: Mapping[str, datetime], targets: Collection[ProbeTarget], *, now: datetime
) -> tuple[str, ...]:
    """The sources a test is owed on at `now`, in the order of their names.

    A request is live when it is not in the future and no test has started at or after it, which is
    `brain.ops.schedule_control.chosen_this_tick`'s comparison, strict on the test so one started at
    the very instant counts as the answer. A live request on a connection tested inside
    `PROBE_SPACING` waits. A request for a source with no live connection is nobody's to answer.
    """
    found: list[str] = []
    for one in sorted(targets, key=lambda target: target.connector):
        at = requested.get(one.connector)
        if at is None or at > now:
            continue
        last = one.last_probe_started
        if last is not None and (last >= at or now - last < PROBE_SPACING):
            continue
        found.append(one.connector)
    return tuple(found)


def untestable(connection: Connection, *, now: datetime) -> str:
    """Why this connection cannot be tested, or empty when it can.

    `brain.ops.connector_sync.plan_for`'s refusal, asked with no attempt behind it because a test
    is not held to the schedule: a source nothing may read is one the worker would make no call to,
    so the application refuses to ask rather than leave a request the worker can only decline.
    """
    return plan_for(connection, last=None, now=now).refused


def in_quota_wait(previous: SyncState | None, *, now: datetime) -> bool:
    """Whether the source asked this install to wait and the wait is not over.

    A scheduled read the source refused for volume, and a test the source refused or that was held
    back for the same wait, each carry the instant the source may be called again. A failure's
    backoff is not a wait the source asked for: a person testing a key they have just replaced is
    exactly who a failing source's backoff must not stop.
    """
    if previous is None or now >= previous.next_attempt_at:
        return False
    if previous.outcome is SyncOutcome.QUOTA:
        return True
    return previous.outcome is SyncOutcome.PROBED and previous.detail in (
        PROBE_REFUSED_FOR_NOW,
        PROBE_NOT_SENT_WHILE_WAITING,
    )


def probe_limits(manifest: ConnectorManifest) -> tuple[Limit, ...]:
    """The windows one test is admitted by: the source's verified ceiling, at the test's share."""
    return limits_for(manifest, principal_id=PROBE_PRINCIPAL)


def windows_after(starts: Collection[datetime], limits: tuple[Limit, ...]) -> LimiterState:
    """The windows as this connection's own recent tests left them, oldest first."""
    state = LimiterState()
    for at in sorted(starts):
        state = state.record(at, limits)
    return state


# --------------------------------------------------------------------- what a page reads
@dataclass(frozen=True)
class ProbeRecord:
    """The newest test of a live connection, as its row keeps it."""

    started_at: datetime
    finished_at: datetime
    health: str
    detail: str


@dataclass(frozen=True)
class ProbeStatus:
    """Whether a test is waiting for the worker, and what the newest one found."""

    requested_at: datetime | None
    last: ProbeRecord | None

    @property
    def pending(self) -> bool:
        """A request no test has started since. See `owed_probes` for the comparison."""
        if self.requested_at is None:
            return False
        return self.last is None or self.last.started_at < self.requested_at

    @property
    def verdict(self) -> ProbeVerdict | None:
        return None if self.last is None else verdict_of(self.last.detail)

    def said(self) -> str:
        """The page's sentence: waiting, the newest test's own sentence, or never tested."""
        if self.pending:
            return TEST_WAITING
        return NEVER_TESTED if self.last is None else self.last.detail


# ------------------------------------------------------------------------ the rows
def checked_source(connector: str) -> str:
    """The name, or a refusal: a request row's key segment is a source's name and nothing else."""
    if not re.fullmatch(CONNECTOR_NAME_PATTERN, connector):
        msg = "a test is asked for by a source's name, and that is not one"
        raise ProbeRequestError(msg)
    return connector


def requests_in(states: Mapping[str, SettingState]) -> dict[str, datetime]:
    """When each source was last asked to be tested, for readable rows only.

    `brain.ops.schedule_control.requested_at` is the reading, so a row that does not hold a zoned
    instant is not a request here for the reason it is not one there. Imported here rather than at
    the top: that module imports the runners, whose connector run imports the store that imports
    this module.
    """
    from brain.ops.schedule_control import requested_at

    found: dict[str, datetime] = {}
    for name, state in states.items():
        at = requested_at(state)
        if at is not None:
            found[name] = at
    return found


async def probe_requests(session: AsyncSession) -> dict[str, datetime]:
    """Every live request, by source."""
    return requests_in(
        values_under(await read_namespace(session, REQUEST_NAMESPACE), REQUEST_NAMESPACE)
    )


async def request_probe(session: AsyncSession, connector: str, *, at: datetime, by: str) -> None:
    """Ask for one test of this source at or after `at`, in the caller's transaction.

    The caller sets the ledger's attribution first (`brain.tables.audit.attributed_to`), so the
    entry `0059`'s trigger appends names who pressed it.
    """
    if at.tzinfo is None:
        msg = "a test asked for at a naive instant would be made early or late by the host's offset"
        raise ProbeRequestError(msg)
    await put(
        session,
        f"{REQUEST_NAMESPACE}.{checked_source(connector)}",
        value_type=SettingType.STRING,
        value=at.isoformat(),
        description=REQUEST_DESCRIPTION,
        updated_by=by,
    )
