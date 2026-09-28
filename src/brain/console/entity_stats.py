"""The figures on an entity's detail page: an agent, a skill, a connector and a channel.

The owner asked for a detail page with stats for every entity. Every figure below is counted
from a table that already records it, and a figure nothing records is named with the reason
rather than drawn as nought. What is decided here is the arithmetic over rows somebody else
fetched; `brain.console_stats_routes` fetches them and decides who may be told of the entity.

**A figure is counted over rows the reader may read, and the narrowing happens before the
count, in two places.** Rows that belong to somebody (a request, a charged run, a person bound
to a channel) are counted at a `brain.console.workspace.Basis`: everybody's rows for a reader
holding the owning screen's read over everything, and only their own otherwise. The route puts
that predicate into the statement that fetches them, so another person's row never reaches the
process for a reader on the narrower basis, and every function here applies the basis again
over whatever arrives, which is `brain.console.workspace.headline`'s construction: the day a
statement loses its predicate, the figure still does not move. Rows that belong to nobody (a
connector's attempts, a channel's deliveries) are readable to exactly the reader who may be
told the entity exists, so they are counted whole for that reader and for nobody else. See
`A_FIGURE_IS_COUNTED_ONLY_OVER_ROWS_ITS_READER_MAY_READ`.

**No figure here is a count of what was withheld, and none can be derived by subtraction.**
Each result type carries counts of rows that were counted, a basis saying whose they were,
and no total beside them; `hidden_count_views` in the tests reads every field name. A refused
request and a request about nothing are one status in `brain.ops.telemetry.RequestStatus`, so
`nothing_returned` is one figure and is never split: splitting it is the count of what people
were refused. See `A_REFUSAL_AND_AN_ABSENCE_ARE_ONE_FIGURE`.

**A skill's runs and a source's live reads are uses, and a use belongs to the person who asked.**
A skill's runs are `agent.skill_invocation` rows, one per skill per finished request, written by
`brain.ops.usage_store`; a source's live reads are `obs.request_telemetry` rows whose `connector`
names it (`brain.ops.telemetry.FILLED_BY_A_SOURCE_READ`). Both carry the person, so both are
counted at the basis an agent's requests are, `brain.console.agent_tabs.usage_basis`, with the
predicate in the statement and applied again here by `counted`, the one function all three
figures ask. A skill's runs are narrowed once more, to the agents the reader may see: a run by an
agent outside their audience is a fact about that agent, and counting it would be the count the
audience withholds. See `A_USE_IS_COUNTED_AT_THE_READERS_BASIS_AND_ONLY_THROUGH_AGENTS_THEY_SEE`.

**A figure this page does not count is named, and never served as nought.** A run's cost has no
writer on the request path while `brain.console.agent_profile.RUN_SPEND_IS_RECORDED` is false,
and a channel's answers are not told apart from its other messages. Each is an `Unrecorded` row
with its sentence, which is `brain.agent_routes.A_FIGURE_NOTHING_STORES_IS_ABSENT_AND_NEVER_NOUGHT`
applied to a page of figures rather than to one headline.

**Two periods, the last seven and the last thirty days, from `brain.console.workspace.window`.**
The same function the agent headline asks, so a thirty-day figure here and the headline's
cannot disagree about where the month begins.

Rejected: aggregating in SQL (`count(*) FILTER`, `percentile_cont`). It is cheaper on a busy
agent, and it is a second implementation of the window and the basis in another language, so
the headline and this page could disagree about one agent's month. The rows are bounded
(`MAX_ACTIVITY_ROWS`, newest first) and a page read over a full bound says so in `at_least`;
because the bound is applied after the basis predicate, a full page says nothing about rows
the reader may not see.

Scope: domain logic. Nothing here opens a connection or reads a clock; `now` and the rows are
parameters.

Task ids: M27.15.8, M27.15.9, M27.15.27, M27.15.33
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from brain.console.workspace import Basis, Range, window
from brain.ops.connector_sync import SyncOutcome
from brain.ops.telemetry import RequestStatus
from brain.tables.channel import DeliveryOutcome, Direction

# ------------------------------------------------------------------ written-down reasons
#: Why a figure moves only when a row the reader may read moves.
A_FIGURE_IS_COUNTED_ONLY_OVER_ROWS_ITS_READER_MAY_READ: Final = (
    "A count over rows the reader may not read tells them how many of those rows exist, and a "
    "count that moves when a colleague works is the colleague's activity. So a row that belongs "
    "to somebody is counted at the owning screen's basis, with the predicate in the statement "
    "and applied again over what arrives, and a row that belongs to nobody is counted only for a "
    "reader who may already be told the entity it describes exists."
)

#: Why refused and abstained requests are one figure.
A_REFUSAL_AND_AN_ABSENCE_ARE_ONE_FIGURE: Final = (
    "The request ledger records a refused request and a request about nothing under one status, "
    "nothing_returned, because a status separating them is a count of what people were refused. "
    "So an agent's page shows how many requests returned nothing and never how many were denied."
)

#: Why a skill's runs and a source's live reads are counted as an agent's requests are.
A_USE_IS_COUNTED_AT_THE_READERS_BASIS_AND_ONLY_THROUGH_AGENTS_THEY_SEE: Final = (
    "A skill run or a live read is somebody's request, so it is counted at the basis the agent's "
    "requests are: everybody's for a reader of everybody's usage and their own otherwise, with "
    "the person in the WHERE clause. A skill's runs are also counted only through agents the "
    "reader may see, because a run by any other agent is a fact about an agent they may not be "
    "told exists."
)

#: Why an entity outside a reader's reach and one that does not exist are one answer.
AN_ENTITY_OUT_OF_REACH_ANSWERS_AS_ONE_THAT_DOES_NOT_EXIST: Final = (
    "A stats address is a loop a person can run over names. If an entity they may not be told "
    "of answered differently from a name that matches nothing, the difference would list the "
    "company's agents, skills, sources and channels one guess at a time, so each module refuses "
    "both with its own one refusal, the one its list screen already makes."
)

# --------------------------------------------------------------------------- the periods
#: The two windows every periodised figure is given over, shortest first.
#:
#: `Range` members rather than day counts, so the thirty-day window is the one the budget month
#: and the agent headline use; `brain.console.workspace.RANGE_DAYS` holds the lengths.
PERIODS: Final[tuple[Range, ...]] = (Range.SEVEN_DAYS, Range.THIRTY_DAYS)

#: The longest period, which is the window every statement reads.
LONGEST: Final = PERIODS[-1]

#: How many rows one figure reads at most, newest first.
#:
#: The agent headline's bound (`brain.agent_routes.MAX_HEADLINE_ROWS`) is twenty thousand
#: charged runs a month; a busy agent's requests are the same order of magnitude, and a page
#: over a full bound says `at_least` rather than presenting a lower figure as the figure.
MAX_ACTIVITY_ROWS: Final = 20_000


def periods(now: datetime) -> tuple[tuple[Range, datetime, datetime], ...]:
    """Each period with the instants it covers, from the one `window` the headline asks."""
    return tuple((one, *window(one, now)) for one in PERIODS)


def _within(at: datetime, since: datetime, until: datetime) -> bool:
    return since <= at <= until


# ----------------------------------------------------------------------- what is not recorded
@dataclass(frozen=True)
class Unrecorded:
    """A figure the design asks for, and why nothing on an install records it.

    Served beside the figures so the page can say "not recorded" in words rather than draw an
    empty tile or a nought. The sentence is a constant; it names no entity and no person.
    """

    figure: str
    why: str


#: Why a run's cost is not shown while nothing on the request path writes one.
RUN_COST_IS_NOT_RECORDED: Final = Unrecorded(
    figure="model_cost",
    why=(
        "nothing on the request path writes a run's cost to the spend ledger yet, so a cost "
        "shown here would be nought for every agent rather than a measurement"
    ),
)

#: Why a channel's answers are served as messages sent.
CHANNEL_ANSWERS_ARE_NOT_TOLD_APART: Final = Unrecorded(
    figure="answered",
    why=(
        "a delivery row carries no link to the message it replied to, so what is shown is every "
        "message the vendor accepted from this install: replies, sign-in prompts and test "
        "messages alike"
    ),
)


# ------------------------------------------------------------------------------ an agent
@dataclass(frozen=True)
class Run:
    """One request the answer lane finished for an agent, as much as the figures need.

    Not `brain.ops.telemetry.RequestTelemetry`: that is a record of forty fields and the page
    needs four, and a type carrying the rest would be a type somebody renders.
    """

    principal_id: str
    at: datetime
    status: RequestStatus
    duration_ms: float


@dataclass(frozen=True)
class RunFigures:
    """What one agent's requests came to over one period, at one basis.

    `nothing_returned` is refused and abstained together. See
    `A_REFUSAL_AND_AN_ABSENCE_ARE_ONE_FIGURE`. No field is a total beside a narrowed count.
    """

    runs: int
    answered: int
    nothing_returned: int
    #: The median duration in milliseconds, or None over no requests. None rather than nought,
    #: because nought milliseconds is a measurement of something very fast.
    p50_latency_ms: float | None


class Attributed(Protocol):
    """A row that belongs to one person at one instant: a request, a skill's run, a live read."""

    @property
    def principal_id(self) -> str: ...

    @property
    def at(self) -> datetime: ...


def counted[T: Attributed](
    rows: Iterable[T],
    *,
    caller_id: str,
    basis: Basis,
    since: datetime,
    until: datetime,
) -> tuple[T, ...]:
    """The rows this reader may be counted over, inside one window, in the order given.

    The basis is applied here whatever the statement already applied. See the module
    docstring: the statement's predicate keeps other people's rows out of the process, and this
    keeps them out of the figure. One function for every figure over somebody's rows, so an
    agent's requests, a skill's runs and a source's reads cannot disagree about whose they are.
    """
    return tuple(
        one
        for one in rows
        if _within(one.at, since, until)
        and (basis is Basis.EVERYONE or one.principal_id == caller_id)
    )


def counted_runs(
    runs: Iterable[Run],
    *,
    caller_id: str,
    basis: Basis,
    since: datetime,
    until: datetime,
) -> tuple[Run, ...]:
    """An agent's requests this reader may be counted over: `counted`, for `Run`."""
    return counted(runs, caller_id=caller_id, basis=basis, since=since, until=until)


def run_figures(
    runs: Iterable[Run],
    *,
    caller_id: str,
    basis: Basis,
    since: datetime,
    until: datetime,
) -> RunFigures:
    """Requests, answers, nothing returned and the median duration, over one window."""
    kept = counted_runs(runs, caller_id=caller_id, basis=basis, since=since, until=until)
    durations = [one.duration_ms for one in kept]
    return RunFigures(
        runs=len(kept),
        answered=sum(1 for one in kept if one.status is RequestStatus.ANSWERED),
        nothing_returned=sum(1 for one in kept if one.status is RequestStatus.NOTHING_RETURNED),
        p50_latency_ms=statistics.median(durations) if durations else None,
    )


def last_active(
    rows: Iterable[Attributed], *, caller_id: str, basis: Basis, since: datetime, until: datetime
) -> datetime | None:
    """The newest row this reader may be counted over, or None when there is none in the window."""
    kept = counted(rows, caller_id=caller_id, basis=basis, since=since, until=until)
    return max((one.at for one in kept), default=None)


# ------------------------------------------------------------------------------- a skill
@dataclass(frozen=True)
class SkillFigures:
    """What the reader's agents and the library say about one skill.

    Counted over the agents the reader's audience covers and over the library only for a
    reader it is listed to; `versions` is None for anybody else, which is also what a skill
    with no library row is, so the None says nothing about the library.
    """

    agents_pinned: int
    pinned_versions: int
    versions: int | None


def skill_figures(
    name: str,
    pins: Iterable[tuple[str, str, str]],
    library_digests: Iterable[tuple[str, str]] | None,
) -> SkillFigures:
    """The agents pinned to one skill, the versions they run, and the versions in the library.

    `pins` are `(agent_id, skill_name, digest)` from agents the reader may already see, and
    `library_digests` are `(skill_name, digest)` from a library the reader may already read, or
    None when it may not be listed to them. Both are filtered to the name here rather than
    trusted to arrive filtered.
    """
    mine = [(agent, digest) for agent, skill, digest in pins if skill == name]
    versions = (
        None
        if library_digests is None
        else len({digest for skill, digest in library_digests if skill == name})
    )
    return SkillFigures(
        agents_pinned=len({agent for agent, _ in mine}),
        pinned_versions=len({digest for _, digest in mine}),
        versions=versions,
    )


def versions_added(
    name: str, submitted: Iterable[tuple[str, datetime]], *, since: datetime, until: datetime
) -> int:
    """How many versions of one skill arrived in the library inside one window."""
    return sum(1 for skill, at in submitted if skill == name and _within(at, since, until))


@dataclass(frozen=True)
class SkillRun:
    """One finished request that used a skill: which agent ran it, for whom, and when.

    One `agent.skill_invocation` row. The recorder writes one per skill per finished request,
    so a count of these is a count of runs that used the skill.
    """

    agent_id: str
    principal_id: str
    at: datetime


def skill_runs(
    runs: Iterable[SkillRun],
    *,
    agents: frozenset[str],
    caller_id: str,
    basis: Basis,
    since: datetime,
    until: datetime,
) -> tuple[SkillRun, ...]:
    """The runs of one skill this reader may be counted over, inside one window.

    Through an agent the reader may see and at their basis, both applied here whatever the
    statement applied. See `A_USE_IS_COUNTED_AT_THE_READERS_BASIS_AND_ONLY_THROUGH_AGENTS_THEY_SEE`.
    """
    return counted(
        (one for one in runs if one.agent_id in agents),
        caller_id=caller_id,
        basis=basis,
        since=since,
        until=until,
    )


# --------------------------------------------------------------------------- a connector
@dataclass(frozen=True)
class Attempt:
    """One finished attempt to read a connected source, as much as the figures need."""

    at: datetime
    outcome: SyncOutcome


@dataclass(frozen=True)
class LiveRead:
    """One request whose readers read this source live: for whom, and when. Never what was read."""

    principal_id: str
    at: datetime


@dataclass(frozen=True)
class AttemptFigures:
    """The worker's attempts on one source over one period.

    `quota_waits` is its own figure rather than a failure, for `brain.ops.connector_sync`'s
    reason: a source that asked to be left alone for an hour has not failed.
    """

    attempts: int
    read_to_the_end: int
    failures: int
    quota_waits: int


def attempt_figures(
    attempts: Iterable[Attempt], *, since: datetime, until: datetime
) -> AttemptFigures:
    """What the worker's attempts came to inside one window.

    A test a person asked for (`SyncOutcome.PROBED`) is not a read and is not counted, here as in
    the statement that fetches the attempts, so a caller handing one in cannot inflate the figures.
    """
    kept = [
        one
        for one in attempts
        if one.outcome is not SyncOutcome.PROBED and _within(one.at, since, until)
    ]
    return AttemptFigures(
        attempts=len(kept),
        read_to_the_end=sum(1 for one in kept if one.outcome is SyncOutcome.SYNCED),
        failures=sum(1 for one in kept if one.outcome is SyncOutcome.FAILED),
        quota_waits=sum(1 for one in kept if one.outcome is SyncOutcome.QUOTA),
    )


# ----------------------------------------------------------------------------- a channel
@dataclass(frozen=True)
class Delivery:
    """One delivery across a channel: which way, what happened and when. Never what was said."""

    direction: Direction
    outcome: DeliveryOutcome
    at: datetime


@dataclass(frozen=True)
class DeliveryFigures:
    """What crossed one channel over one period.

    `sent` is every outbound message the vendor accepted; see
    `CHANNEL_ANSWERS_ARE_NOT_TOLD_APART`. `unknown` is its own figure rather than a failure,
    because a vendor that timed out may have delivered.
    """

    received: int
    sent: int
    failed: int
    unknown: int
    refused_inbound: int


def delivery_figures(
    deliveries: Iterable[Delivery], *, since: datetime, until: datetime
) -> DeliveryFigures:
    """What one channel received and sent inside one window, and what did not arrive."""
    kept = [one for one in deliveries if _within(one.at, since, until)]

    def count(direction: Direction, outcome: DeliveryOutcome) -> int:
        return sum(1 for one in kept if one.direction is direction and one.outcome is outcome)

    return DeliveryFigures(
        received=count(Direction.INBOUND, DeliveryOutcome.ACCEPTED),
        sent=count(Direction.OUTBOUND, DeliveryOutcome.SENT),
        failed=count(Direction.OUTBOUND, DeliveryOutcome.REFUSED),
        unknown=count(Direction.OUTBOUND, DeliveryOutcome.UNKNOWN),
        refused_inbound=count(Direction.INBOUND, DeliveryOutcome.REFUSED),
    )


def bound_people(bound: Iterable[str], *, caller_id: str, basis: Basis) -> int:
    """How many people are bound to a channel, at the People screen's basis.

    Everybody's bindings for a reader of the People screen over everything, and on the narrower
    basis whether the reader is bound themselves, which is one or nought and a fact about them.
    """
    people = set(bound)
    if basis is Basis.EVERYONE:
        return len(people)
    return 1 if caller_id in people else 0


def newest(instants: Sequence[datetime | None]) -> datetime | None:
    """The latest of some instants, ignoring the absent ones, or None."""
    return max((one for one in instants if one is not None), default=None)
