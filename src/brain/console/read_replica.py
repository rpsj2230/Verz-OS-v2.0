"""Which database a console read is answered from, and what the page says when it is behind.

M36.1.2 adds a streaming replica so that the console's heavy reads stop competing with answers
for the primary. Routing a read there is one line. What is not one line is that a replica is
**a copy of the database as it was some seconds ago**, and a console is where somebody reads a
value and then acts on it: they read a rung's timeout, change it, and the page they come back
to is read from a copy that has not replayed the change yet. This module decides which copy
answers, and what the page must say when the copy is behind. It holds no connection;
`brain.ops.replica_store` measures and reads, for the reason `brain.ops.limits` gives about
policy that owns a client.

**A read that decides anything is answered by the primary, always.** A grant revoked a second
ago is still present on a replica that has not replayed the revocation, so an entitlement read
from one admits somebody the owner has just removed, for as long as the lag lasts. A page that
is a few seconds out of date is a nuisance with a banner on it. An authorisation that is a few
seconds out of date is the revocation not having happened, and no banner can be shown to the
person it failed to stop. `Purpose.DECISION` is how a caller says which kind of read it is
making, and it never reaches the replica, however healthy the replica is. See
`A_DECISION_IS_NEVER_READ_FROM_A_COPY`.

**Past a named threshold the read goes back to the primary rather than being shown with a
banner, and that is the fail-safe direction.** Three answers were available for a replica that
is very far behind, or unreachable, or not a replica at all.

- *Serve it with a banner at any age.* A banner reading "three hours behind" on an
  administrative screen is a banner people learn to scroll past, and the screen still invites
  an edit against a value three hours old. The write goes to the primary and silently
  overwrites whatever changed in between.
- *Refuse the page.* That makes the replica a dependency the console did not have before it
  existed: an install that added a replica for headroom would find its console down whenever
  the replica was.
- *Read the primary.* This returns the console to exactly what it did before M36.1.2, which is
  a load the install has already survived. It is the one answer that is never wrong about the
  data.

So `FALL_BACK_AFTER` bounds how old a displayed page may be, and between `BANNER_AFTER` and it
the page is served from the replica **with** `StalenessBanner` on it. There is no third band in
which a replica read is older than `BANNER_AFTER` and carries no banner: `ConsoleRoute` refuses
to be built that way. See `A_REPLICA_READ_PAST_THE_BANNER_THRESHOLD_ALWAYS_CARRIES_ONE`.

The cost of falling back is stated rather than hidden. **Replication lags most when the primary
is busiest**, so the fall-back moves console load onto the primary at the moment it is least
welcome. The alternative that avoids that is serving stale figures, and this module does not
buy headroom with wrong numbers. `brain.ops.scaling.replica_is_due` is where that load is
measured.

**How far behind a reading is, and what a null means.** The store asks the replica for
`now() - pg_last_xact_replay_timestamp()`, the age of the last transaction it replayed, and
three things make that figure unsafe to read on its own.

- *It is null on a primary*, because a primary replays nothing. `pg_is_in_recovery()` is read
  beside it, and a server that is not in recovery is not a replica, whatever the setting says.
  That is either the primary's own address typed twice, which is harmless and reads the primary
  here anyway, or **a replica that was promoted**, which is a second writable database
  diverging from the real one, and reading it is wrong by an amount nobody can state. Both go
  to the primary. See `A_SERVER_NOT_IN_RECOVERY_IS_NOT_A_COPY_OF_ANYTHING`.
- *It is also null on a replica that has replayed nothing since it started*, which holds the
  base backup it was built from and nothing newer. Its age is unknown, so it is not stated as
  zero: it goes to the primary.
- *It grows on an idle primary.* No new transaction means no new replay timestamp, so a
  perfectly current replica reads as minutes behind. The store therefore also reports whether
  a WAL receiver is running and has replayed everything it received, and that reads as no lag
  at all. The receiver's details need `pg_read_all_stats`, but its row, carrying only its pid,
  is visible to any role, and existence is all that is asked. When the receiver cannot be seen
  the replay age is used as it stands, and the failure is then an idle primary answering the
  console, which is the one moment falling back costs nothing.

And one residue that is not closed. A receiver whose network has silently gone keeps its row
and its equal positions until `wal_receiver_timeout` (sixty seconds by default) notices, so for
up to that long a stalled replica can read as caught up. It is bounded, it is PostgreSQL's
timeout rather than one of this module's, and it is written here so nobody believes the figure
is tighter than it is.

**A reading's own age is added to the lag it reports.** A measurement taken two seconds ago that
said one second behind is, at worst, three seconds behind now: a replica that stopped replaying
the instant after it was measured has fallen behind by exactly the time since. `stated_lag` adds
it, so caching a measurement for `MEASURE_EVERY` can overstate a page's age and can never
understate it. A reading dated after the instant it is being judged at is a clock nobody can
trust and goes to the primary.

**The banner describes the copy and never the rows.** It says how many seconds the database the
page was read from is behind, which is the same figure for every reader who reaches the page
and says nothing about what any of them may see. It is only ever computed after a route's own
capability check, so an unentitled caller cannot learn from it that a replica exists. See
`THE_BANNER_DESCRIBES_THE_COPY_AND_NEVER_THE_ROWS`.

What was rejected, besides the three answers above.

*A heartbeat table on the primary, written every second and read on the replica.* It measures
lag exactly, idle primary included, and it needs a writer that runs on a schedule, a migration,
and a table with row-level security that every read of it has to be granted. The replay
timestamp needs none of those and its one blind spot is handled above.

*Grading the lag on `brain.gate.provenance`'s LIVE, AGEING and STALE scale.* That scale grades
how much weight a figure's age allows, and it is right for a citation. Lag is a different
question, which copy to read, and its answer is a route rather than a label, so borrowing the
words would say AGEING on a page that was in fact switched to the primary. The provenance
horizon is used as the ceiling instead: `threshold_gaps` refuses a `FALL_BACK_AFTER` longer than
the window in which an answer would still be called live.

*Rounding the banner's figure to the nearest second.* It rounds up, so 10.2 seconds behind is
eleven and a banner can overstate by under a second and never understate.

Task ids: M36.1.2.2, M36.1.2.3
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from brain.gate.provenance import DEFAULT_HORIZON


class ReadReplicaError(Exception):
    """Raised when a route or a threshold would let a stale read reach a page unannounced."""


# ------------------------------------------------------------------ written-down reasons
#: Why an authorisation or a write's precondition never reads the replica.
A_DECISION_IS_NEVER_READ_FROM_A_COPY: Final = (
    "A replica holds the database as it was some seconds ago. A grant revoked in that window is "
    "still there, so an entitlement read from the copy admits somebody the owner has just "
    "removed, and no banner can be shown to the person the revocation failed to stop. A page a "
    "few seconds behind is a nuisance with a notice on it; a decision a few seconds behind is the "
    "change not having happened. Anything whose answer decides what is allowed or what is "
    "written next reads the primary, however healthy the replica is."
)

#: Why a replica read past the banner threshold is refused without a banner.
A_REPLICA_READ_PAST_THE_BANNER_THRESHOLD_ALWAYS_CARRIES_ONE: Final = (
    "A page read from a copy that is behind by more than BANNER_AFTER shows values somebody may "
    "act on, and the only thing telling them the values may already have changed is the banner. "
    "A route to the replica in that band with no banner is stale data served silently, so "
    "ConsoleRoute refuses to be built that way rather than trusting every caller to attach one."
)

#: Why a very stale or unmeasurable replica sends the read back to the primary.
PAST_THE_THRESHOLD_THE_PRIMARY_ANSWERS_RATHER_THAN_A_BANNER: Final = (
    "A banner reading hours behind is a banner people scroll past on a screen that still invites "
    "an edit, and the edit lands on the primary over whatever changed meanwhile. Refusing the "
    "page instead makes the replica a dependency the console never had. Reading the primary is "
    "what the console did before the replica existed, at a load the install already survived, "
    "and it is never wrong about the data."
)

#: Why a server that is not in recovery is not read as a replica.
A_SERVER_NOT_IN_RECOVERY_IS_NOT_A_COPY_OF_ANYTHING: Final = (
    "pg_last_xact_replay_timestamp is null on a primary, and a replica address that answers as a "
    "primary is either the primary typed twice or a replica that was promoted. A promoted replica "
    "is a second writable database diverging from the real one by an amount nobody can measure, "
    "so its lag cannot be stated and it is not read."
)

#: Why the banner cannot disclose anything a reader may not see.
THE_BANNER_DESCRIBES_THE_COPY_AND_NEVER_THE_ROWS: Final = (
    "The banner states how far the database the page was read from is behind, which is the same "
    "figure for every reader and says nothing about which rows exist or which were withheld. It "
    "is computed only after the route has admitted the caller, so a caller refused the page "
    "cannot learn from it that this install has a replica."
)


# ---------------------------------------------------------------------- the thresholds
#: How long one lag measurement is reused. Short, because its age is added to the lag it states.
MEASURE_EVERY: Final = timedelta(seconds=2)

#: How long a measurement may take before the replica is treated as unreachable for this reading.
MEASURE_TIMEOUT: Final = timedelta(seconds=1)

#: The lag at which a page read from the replica starts carrying a banner.
BANNER_AFTER: Final = timedelta(seconds=10)

#: The lag past which the read goes to the primary. See the module docstring.
FALL_BACK_AFTER: Final = timedelta(minutes=5)


def threshold_gaps(
    *,
    measure_every: timedelta = MEASURE_EVERY,
    measure_timeout: timedelta = MEASURE_TIMEOUT,
    banner_after: timedelta = BANNER_AFTER,
    fall_back_after: timedelta = FALL_BACK_AFTER,
) -> tuple[str, ...]:
    """Every way the four thresholds contradict each other or the provenance horizon.

    Parameters defaulting to the constants, so the check can be shown to refuse, for the reason
    `brain.ops.install_docs.mechanism_gaps` takes its registry as one.
    """
    findings: list[str] = []
    if measure_every >= banner_after:
        findings.append(
            "a measurement reused for as long as the banner threshold raises the banner on its "
            "own age, on a replica that is not behind at all"
        )
    if measure_timeout > measure_every:
        findings.append(
            "a measurement allowed longer than it is reused for is re-attempted while it is "
            "still waiting, and every console read queues behind an unreachable replica"
        )
    if banner_after >= fall_back_after:
        findings.append(
            "a banner threshold at or past the fall-back threshold leaves no band in which a "
            "page is served from the replica with a banner, so the banner can never appear"
        )
    if fall_back_after > DEFAULT_HORIZON.live_for:
        findings.append(
            "a console page may be older than the window in which an answer citing the same "
            "value would still be called live"
        )
    return tuple(findings)


# ------------------------------------------------------------------------ the readings
class Purpose(enum.StrEnum):
    """What a console read is for. See `A_DECISION_IS_NEVER_READ_FROM_A_COPY`."""

    #: Shown to a person, who can be told its age.
    DISPLAY = "display"
    #: Its answer decides what is allowed or what is written next. Always the primary.
    DECISION = "decision"


@dataclass(frozen=True)
class LagReading:
    """What the replica said about itself, as `brain.ops.replica_store.measure_lag` reads it.

    `replay_age` is `now() - pg_last_xact_replay_timestamp()` on the replica's own clock, and is
    None both on a primary and on a replica that has replayed nothing since it started.
    `caught_up` is a running WAL receiver whose received and replayed positions are equal.
    """

    in_recovery: bool
    replay_age: timedelta | None
    caught_up: bool


@dataclass(frozen=True)
class Unreachable:
    """The replica did not answer the measurement in time, or refused the connection."""


@dataclass(frozen=True)
class Measurement:
    """One reading, and the instant it was taken at."""

    reading: LagReading | Unreachable
    at: datetime


class Target(enum.StrEnum):
    PRIMARY = "primary"
    REPLICA = "replica"


class Why(enum.StrEnum):
    """Why a read went where it went. For a log line, never for a response body."""

    NO_REPLICA = "no replica is configured"
    A_DECISION = "a read that decides something is answered by the primary"
    UNREACHABLE = "the replica did not answer its lag measurement"
    NOT_IN_RECOVERY = "the replica address answers as a primary"
    NOTHING_REPLAYED = "the replica has replayed nothing, so its age is unknown"
    CLOCKS_DISAGREE = "the lag came out negative, so the two clocks cannot be trusted"
    TOO_FAR_BEHIND = "the replica is further behind than a page may be"
    CURRENT = "the replica is within the banner threshold"
    BEHIND = "the replica is behind, and the page says by how much"


class StalenessBanner(BaseModel):
    """What a page read from a replica says about its own age. A field, never a caption.

    Whole seconds, rounded up. See the module docstring.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    behind_seconds: int = Field(ge=1)
    message: str


def banner_for(lag: timedelta) -> StalenessBanner:
    """The banner for a page this far behind."""
    seconds = math.ceil(lag.total_seconds())
    return StalenessBanner(
        behind_seconds=seconds,
        message=(
            f"This page was read from a copy of the database that is {seconds} seconds behind. "
            f"A change made in the last {seconds} seconds may not be shown yet."
        ),
    )


@dataclass(frozen=True)
class ConsoleRoute:
    """Where one console read goes, why, and the banner the page carries if any.

    Refuses the two shapes that would put a stale page in front of somebody unannounced: a
    route to the replica described as behind with no banner, and a banner on a read from the
    primary, which would tell a reader a current page is out of date and teach them to ignore
    the banner that matters.
    """

    target: Target
    why: Why
    banner: StalenessBanner | None = None

    def __post_init__(self) -> None:
        if self.target is Target.PRIMARY and self.banner is not None:
            msg = "a read answered by the primary is current and carries no staleness banner"
            raise ReadReplicaError(msg)
        if self.target is Target.REPLICA and self.why not in (Why.CURRENT, Why.BEHIND):
            msg = f"a replica read cannot be routed for the reason {self.why.value!r}"
            raise ReadReplicaError(msg)
        if self.why is Why.BEHIND and self.banner is None:
            raise ReadReplicaError(A_REPLICA_READ_PAST_THE_BANNER_THRESHOLD_ALWAYS_CARRIES_ONE)


def stated_lag(measurement: Measurement, *, now: datetime) -> timedelta | Why:
    """How far behind the replica may be at `now`, or why that cannot be said.

    The reading's own age is added, so a cached measurement overstates and never understates.
    """
    reading = measurement.reading
    if isinstance(reading, Unreachable):
        return Why.UNREACHABLE
    if not reading.in_recovery:
        return Why.NOT_IN_RECOVERY
    since = now - measurement.at
    if since < timedelta():
        return Why.CLOCKS_DISAGREE
    if reading.caught_up:
        return since
    if reading.replay_age is None:
        return Why.NOTHING_REPLAYED
    if reading.replay_age < timedelta():
        return Why.CLOCKS_DISAGREE
    return reading.replay_age + since


def route_read(purpose: Purpose, measurement: Measurement | None, *, now: datetime) -> ConsoleRoute:
    """Which database answers this read. `measurement` is None when no replica is configured."""
    if purpose is Purpose.DECISION:
        return ConsoleRoute(target=Target.PRIMARY, why=Why.A_DECISION)
    if measurement is None:
        return ConsoleRoute(target=Target.PRIMARY, why=Why.NO_REPLICA)
    lag = stated_lag(measurement, now=now)
    if isinstance(lag, Why):
        return ConsoleRoute(target=Target.PRIMARY, why=lag)
    if lag > FALL_BACK_AFTER:
        return ConsoleRoute(target=Target.PRIMARY, why=Why.TOO_FAR_BEHIND)
    if lag > BANNER_AFTER:
        return ConsoleRoute(target=Target.REPLICA, why=Why.BEHIND, banner=banner_for(lag))
    return ConsoleRoute(target=Target.REPLICA, why=Why.CURRENT)
