"""How the metadata ledger is cut up, derived from how long it is kept rather than chosen.

The metadata ledger is the one table in this estate that grows without bound and is not
allowed to be pruned aggressively. `brain.ops.retention` keeps it for
`METADATA_LEDGER_RETENTION_DAYS`, which is the longest fixed window anywhere here, and it can
afford that only because `brain.ops.telemetry` holds it to names and counts and never a value.
So the table is large by design, and a partitioning scheme is the claim about how it is
queried and pruned.

**Every number in this module is derived and none of them is picked.** That is the whole
argument, because a partition interval is exactly the kind of figure that is right for the
company that wrote it and wrong for the next one. The interval has a floor and a ceiling and
both come from somewhere else:

*The floor is the horizon's own resolution.* `brain.ops.retention.Horizon.days` is a whole
number of days and `expires_at` adds `timedelta(days=...)`, so a day is the finest thing the
retention policy can express. Every partition inside one day becomes droppable on the same
day, so cutting finer than that produces more partitions with the same drop date and buys
nothing. See `A_PARTITION_FINER_THAN_THE_HORIZON_BUYS_NOTHING`.

*The ceiling is what the estate already tolerates in expired data that has not gone yet.* A
partition can only be dropped whole, so it has to be dropped when its **newest** row passes
the horizon and not when its oldest does, and that keeps the oldest row in it for up to one
interval too long. The estate already has a figure for how long an expired row may linger:
`brain.ops.retention.BACKUP_RETENTION_DAYS` is how long after a deletion the deleted data is
still recoverable, and `brain.ops.erasure` reads it for exactly that. A partition scheme whose
over-retention was longer than that would make the partition set, rather than the backup
cycle, the longest-lived copy of an expired ledger row. See
`A_DROP_ON_THE_OLDEST_ROW_TAKES_ROWS_STILL_INSIDE_THE_WINDOW`.

Those two bounds pick the interval on their own: `largest_safe_interval` walks `Interval` and
returns the largest one that satisfies both, and `PARTITION_INTERVAL` is that function's
answer rather than a member typed out. M36.1.1.2 says "partition by month" and monthly is what
the arithmetic returns, which is the useful way round: the leaf is confirmed by the derivation
rather than the derivation being fitted to the leaf. Quarterly is refused by thirty-one days.

**The archive is a step on the way out and not a second lifetime.** M36.1.1.3 asks for detach
and archive rather than delete, and the trap in that sentence is the archive. A detached
partition still holds metadata-ledger rows, so it is still governed by
`horizon_for(METADATA_LEDGER)`; an archive kept on its own schedule would be a per-row
retention override arriving as a file, which is the failure
`brain.ops.retention.THE_CLASS_DECIDES_AND_A_ROW_CANNOT_ARGUE` is written about. So the
detached partition gets a settling window and no more, `SETTLE_DAYS` is what is left of the
allowance after the interval has spent its share of it, and the two together are one budget
rather than two numbers. See `AN_ARCHIVE_WITH_ITS_OWN_LIFETIME_IS_A_PER_ROW_OVERRIDE_IN_A_FILE`.

**The premake count defends a failure that only happens after a restore.** A database restored
from the oldest backup carries the partition set as it was `BACKUP_RETENTION_DAYS` ago, and the
first insert into a period nobody premade fails with no partition found for the row. So the
premake has to cover the backup window and not merely the next period, and `premake_for`
computes it from that window rather than from a habit. See
`A_PARTITION_SET_THAT_STOPS_AT_TODAY_REFUSES_TOMORROWS_WRITE`.

**What is not built, said here rather than left to be inferred.** M36.1.1.1 asks for pg_partman
on the metadata ledger and there is **no ledger table to partition**.
`brain.ops.telemetry`'s docstring says so in as many words: `obs` holds the audit chain, no
migration in this repository creates a metadata-ledger row, and nothing calls `open_request`.
`partman_settings` is therefore the configuration that migration will need, as data a test can
check against the row shape `RequestTelemetry.ledger_row` actually produces, and the migration
itself is not written here. Writing one would mean inventing M27's eighteen-column schema, its
row-level security and its indexes in a module about partitioning, and the first thing to go
wrong would be that the invented schema and the real one disagree.

Rejected: a partition per data class, so that traces and payloads ride the same scheme. They
are three horizons in one schema, which is precisely why `brain.ops.retention.store_gaps`
allows several stores to claim `obs`, and a scheme sized for the five-year window would
over-retain a thirty-day one by a factor of sixty.

Rejected: deriving the interval from an expected row count. It is the obvious approach and it
needs an arrival rate, and the only arrival figures this repository has are the peak-minute
rates in `brain.ops.admission.seed_profiles`, which are deliberately not daily volumes. An
interval sized from a peak read as a daily mean would be wrong by the ratio between them, and
nothing would say so.

Rejected: `DELETE` on the live table with the partitioning left for later. It is the cheaper
change and it is the one that cannot be undone later, because converting a populated table to
a partitioned one rewrites it. See `brain.ops.scaling`, which is where that trigger lives.

Task ids: M36.1.1.2, M36.1.1.3
"""

from __future__ import annotations

import enum
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, assert_never

from brain.ops.retention import (
    BACKUP_RETENTION_DAYS,
    DataClass,
    Lifetime,
    horizon_for,
)
from brain.ops.telemetry import LEDGER_DATA_CLASS, LEDGER_RETENTION_DAYS


class PartitioningError(Exception):
    """Raised when a partition scheme would keep rows longer than their class allows."""


# ------------------------------------------------------------------ written-down reasons
#: Why there is a floor on the interval at all.
A_PARTITION_FINER_THAN_THE_HORIZON_BUYS_NOTHING: Final = (
    "brain.ops.retention.Horizon.days is a whole number of days and expires_at adds a "
    "timedelta in days, so a day is the finest window the retention policy can express. "
    "Every partition lying inside one day therefore becomes droppable on the same day as "
    "every other, and cutting finer than that produces more relations for the planner to "
    "consider, more catalogue rows and more maintenance, in exchange for pruning that "
    "happens at exactly the same moment. The floor is not about performance. It is that "
    "there is nothing below it for a partition to be aligned to."
)

#: Why a partition is dropped on its newest row and what that costs.
A_DROP_ON_THE_OLDEST_ROW_TAKES_ROWS_STILL_INSIDE_THE_WINDOW: Final = (
    "A partition is dropped whole, so the drop happens either when its oldest row passes "
    "the horizon or when its newest one does. On the oldest row it removes every row up to "
    "one interval younger than the horizon, which is a retention policy quietly shortened "
    "for most of the table and shortened by an amount that depends on where in the period a "
    "request happened to arrive. On the newest row it keeps the oldest row for up to one "
    "interval too long, which is visible, bounded and the same for every row. So the drop "
    "is on the newest row, the cost is over-retention, and the interval is bounded by how "
    "much of that the estate already tolerates elsewhere."
)

#: Why the archive cannot have a schedule of its own.
AN_ARCHIVE_WITH_ITS_OWN_LIFETIME_IS_A_PER_ROW_OVERRIDE_IN_A_FILE: Final = (
    "A detached partition still holds metadata-ledger rows and is therefore still governed "
    "by the metadata-ledger horizon. An archive kept on its own schedule is the per-row "
    "override brain.ops.retention refuses to have a field for, arriving as a file instead "
    "of as a column: nobody set it during an investigation, so nobody remembers to end it, "
    "and it becomes the oldest copy of the estate's request history with no policy pointing "
    "at it. Detaching is the removal from the live table and the settling window is how long "
    "the detached table may sit before it is dropped, and that window comes out of the same "
    "allowance the interval spends from."
)

#: Why the premake count is sized against the backup window rather than the next period.
A_PARTITION_SET_THAT_STOPS_AT_TODAY_REFUSES_TOMORROWS_WRITE: Final = (
    "An insert into a partitioned table with no partition for the row's control value fails "
    "outright, and the failure arrives at the ledger, which is the one table that has to "
    "hold a row for the request that went wrong. The ordinary case is covered by any premake "
    "at all. The case that is not is a restore: a database recovered from the oldest backup "
    "carries the partition set as it stood a backup window ago, so unless that set already "
    "reached forward across the whole window, the first write after the restore is refused "
    "by the recovery that was supposed to fix things."
)

#: Why the whole scheme is expressed as one allowance rather than two numbers.
THE_INTERVAL_AND_THE_ARCHIVE_SPEND_FROM_ONE_ALLOWANCE: Final = (
    "Partition alignment keeps an expired row for up to one interval and the settling window "
    "keeps the detached table for however long it is given. Both are the same thing to "
    "anybody reading a subject access request: a row that should have gone and has not. "
    "Budgeting them separately means two numbers each defensible on its own and a total "
    "nobody costed, which is how a five-year window becomes five years and two months. One "
    "allowance, anchored to what the estate already tolerates, and the settling window is "
    "what the interval leaves of it."
)


# ------------------------------------------------------------------------- the allowance
#: The finest window the retention policy can express, in days. Not a chosen granularity: it
#: is a property of `brain.ops.retention.Horizon.days` being an integer count of days.
HORIZON_RESOLUTION_DAYS: Final[int] = 1

#: The most days an expired ledger row may still be somewhere, across alignment and settling.
#:
#: `BACKUP_RETENTION_DAYS` rather than a figure of this module's own, because that is already
#: the estate's answer to the same question: `brain.ops.erasure` reads it to say how long
#: after a deletion the deleted data is still recoverable. A partition scheme that lingered
#: longer than the backups would make the partition set the longest-lived copy of an expired
#: row, which is a thing nobody decided and nothing would report.
MAX_OVER_RETENTION_DAYS: Final[int] = BACKUP_RETENTION_DAYS


class Interval(enum.StrEnum):
    """The candidate partition intervals, as periods rather than as day counts.

    Calendar periods rather than fixed spans of days, because pg_partman's intervals are
    calendar ones and because a boundary that drifts against the month is a boundary nobody
    can find in a query plan. The day counts each period can take are calendar facts and are
    given by `longest_days` and `shortest_days`, which differ and are both needed: the longest
    bounds the over-retention and the shortest bounds how much future a premake covers.
    """

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


def longest_days(interval: Interval) -> int:
    """The most days one period of this interval can span. A calendar fact, not a setting.

    `assert_never` for the reason `brain.ops.retention.horizon_for` uses it: a sixth interval
    cannot reach production without somebody stating how long it can be, and a mapping with a
    default would state it for them in whichever direction the default happened to point.
    """
    match interval:
        case Interval.DAILY:
            return 1
        case Interval.WEEKLY:
            return 7
        case Interval.MONTHLY:
            return 31
        case Interval.QUARTERLY:
            return 92
        case Interval.YEARLY:
            return 366
        case _:  # pragma: no cover - unreachable while Interval has five members
            assert_never(interval)


def shortest_days(interval: Interval) -> int:
    """The fewest days one period of this interval can span.

    Separate from `longest_days` and not a rounding of it. The two are used for opposite
    questions and the safe answer differs: over-retention is bounded by the longest a period
    can be, and the amount of future a premake count covers is bounded by the shortest.
    """
    match interval:
        case Interval.DAILY:
            return 1
        case Interval.WEEKLY:
            return 7
        case Interval.MONTHLY:
            return 28
        case Interval.QUARTERLY:
            return 90
        case Interval.YEARLY:
            return 365
        case _:  # pragma: no cover - unreachable while Interval has five members
            assert_never(interval)


def partman_interval(interval: Interval) -> str:
    """The period as pg_partman spells it in `p_interval`.

    An exhaustive match rather than string surgery on the member's own name, which is what this
    was and which was wrong: `"daily".removesuffix("ly")` is `"dai"`, so a scheme on a daily
    interval would have been configured with a period Postgres cannot parse. It was invisible
    because the only interval the module declares is monthly, where the surgery happens to work.
    Quarterly is three months rather than a quarter for the same reason: the word pg_partman
    takes is the one Postgres parses as an interval.
    """
    match interval:
        case Interval.DAILY:
            return "1 day"
        case Interval.WEEKLY:
            return "1 week"
        case Interval.MONTHLY:
            return "1 month"
        case Interval.QUARTERLY:
            return "3 months"
        case Interval.YEARLY:
            return "1 year"
        case _:  # pragma: no cover - unreachable while Interval has five members
            assert_never(interval)


def over_retention_days(interval: Interval) -> int:
    """How long the oldest row in a partition outlives its horizon under this interval.

    One less than the longest period, because a partition dropped when its newest row passes
    the horizon holds rows spanning the period, and the oldest of them is that much older than
    the newest. A daily interval therefore costs nothing at all, which is the reading that
    makes the arithmetic worth writing: the cost of a coarser interval is exactly the extra
    days it holds.
    """
    return longest_days(interval) - 1


def interval_refusals(
    interval: Interval,
    *,
    resolution_days: int = HORIZON_RESOLUTION_DAYS,
    allowance_days: int = MAX_OVER_RETENTION_DAYS,
    window_days: int = LEDGER_RETENTION_DAYS,
) -> tuple[str, ...]:
    """Every reason this interval cannot be the ledger's, in words an operator can act on.

    Returns all of them rather than the first, matching `brain.ops.wiring.budget_breaches`:
    an interval that is both too fine and too coarse is not a thing, but an interval that
    fails the allowance while also failing against the horizon it is being applied to is, and
    a caller learning one reason at a time re-runs this once per fix.

    **The three bounds are parameters and the defaults are the estate's own figures**, for the
    reason `brain.ops.wiring.trace_stack_gaps` takes its components: two of these refusals
    cannot fire against the declared values at all. No member of `Interval` is finer than a
    day, and none is longer than the five-year window, so a version reading the constants
    directly would carry two branches that are green for every input and would stay green with
    their bodies deleted. That defect has been found three times in this repository. The
    defaults are the real figures, so every caller gets the real answer and only a test hands
    it a policy whose resolution is a week.
    """
    findings: list[str] = []
    if longest_days(interval) < resolution_days:
        findings.append(
            f"a {interval.value} partition spans fewer than {resolution_days} day(s), "
            f"which is finer than the retention policy can express. "
            f"{A_PARTITION_FINER_THAN_THE_HORIZON_BUYS_NOTHING}"
        )
    if over_retention_days(interval) > allowance_days:
        findings.append(
            f"a {interval.value} partition keeps its oldest row {over_retention_days(interval)} "
            f"day(s) past the horizon and the estate allows {allowance_days}, which is "
            f"how long a deleted row already survives in the backups. "
            f"{A_DROP_ON_THE_OLDEST_ROW_TAKES_ROWS_STILL_INSIDE_THE_WINDOW}"
        )
    if longest_days(interval) > window_days:
        findings.append(
            f"a {interval.value} partition spans more than the {window_days}-day "
            "window it is being cut into, so the table is one partition and partitioning it "
            "has changed nothing except the number of relations"
        )
    return tuple(findings)


def largest_safe_interval(
    candidates: Sequence[Interval] | None = None,
    *,
    resolution_days: int = HORIZON_RESOLUTION_DAYS,
    allowance_days: int = MAX_OVER_RETENTION_DAYS,
    window_days: int = LEDGER_RETENTION_DAYS,
) -> Interval:
    """The coarsest interval that satisfies the floor and the allowance.

    Coarsest rather than finest, because everything else about a partition set gets worse as
    the count rises: more relations in every plan, more catalogue rows, more maintenance runs,
    and a longer lock list on any statement that touches the parent. The allowance is what
    stops that argument running away, so the answer is the largest interval it admits.

    `candidates` is a parameter defaulting to the whole enum for the reason
    `brain.ops.retention.horizon_gaps` takes one: a derivation that can only ever be run over
    the set that produces the declared answer is a derivation nobody has seen produce a
    different one, and a test that hands it a shorter list is what shows the walk is real. The
    three bounds are parameters for the same reason, and passing a different allowance is how
    a reader checks that this is a derivation rather than a lookup returning monthly.
    """
    ordered = tuple(Interval) if candidates is None else tuple(candidates)
    admitted = [
        one
        for one in ordered
        if not interval_refusals(
            one,
            resolution_days=resolution_days,
            allowance_days=allowance_days,
            window_days=window_days,
        )
    ]
    if not admitted:
        msg = (
            f"no interval in {[one.value for one in ordered]} fits a {window_days}-day "
            f"window with an allowance of {allowance_days} day(s) of over-retention"
        )
        raise PartitioningError(msg)
    return max(admitted, key=longest_days)


#: The interval the ledger is cut on. The output of the derivation above rather than a member
#: typed out, so a change to the allowance or to the backup window moves it and a mutation of
#: it fails against the walk. M36.1.1.2 asks for monthly and monthly is what this returns.
PARTITION_INTERVAL: Final[Interval] = largest_safe_interval()

#: How long the detached partition may sit before it is dropped.
#:
#: What the interval leaves of the allowance, not a window of its own. See
#: `THE_INTERVAL_AND_THE_ARCHIVE_SPEND_FROM_ONE_ALLOWANCE`. It goes to zero for an interval
#: that spends the whole allowance on alignment, which is the honest answer: at that point
#: there is no room for an archive and the partition is dropped as it is detached.
#:
#: Floored at zero rather than allowed to go negative, and the flooring is not what protects
#: the allowance. `interval_refusals` is: an interval that spends more than the whole allowance
#: is refused before it ever reaches here, and `spec_gaps` reports the total either way. What
#: the floor buys is that this module still imports when its own derivation is broken, so a
#: mutation of the allowance check fails a named test rather than a collection error, which is
#: the difference between a mutation that is caught and one that is flattering.
SETTLE_DAYS: Final[int] = max(0, MAX_OVER_RETENTION_DAYS - over_retention_days(PARTITION_INTERVAL))


def premake_for(interval: Interval, *, restore_window_days: int = BACKUP_RETENTION_DAYS) -> int:
    """How many future partitions must exist, sized against a restore rather than a routine.

    See `A_PARTITION_SET_THAT_STOPS_AT_TODAY_REFUSES_TOMORROWS_WRITE`. The shortest a period
    can be is what bounds how much calendar a count of partitions covers, and the extra one is
    the current period: it is already partly elapsed, so it may cover almost none of the
    future and cannot be counted towards the window.

    `restore_window_days` is a parameter defaulting to the backup window so that "what if
    backups were kept for a quarter" is answerable without editing this module, which is the
    shape `brain.ops.wiring.safe_headroom_mib` uses for the same reason.
    """
    if restore_window_days < 0:
        msg = f"a restore window of {restore_window_days} days is not a window"
        raise PartitioningError(msg)
    return math.ceil(restore_window_days / shortest_days(interval)) + 1


#: The premake for the declared interval.
PREMAKE: Final[int] = premake_for(PARTITION_INTERVAL)


def partitions_over_the_window(
    interval: Interval, *, window_days: int = LEDGER_RETENTION_DAYS
) -> int:
    """How many partitions the retained window holds at its widest, plus the premade ones.

    The shortest period rather than the longest, because the count is worst when the periods
    are short. Reported rather than bounded: there is no ceiling on the partition count in
    this module and there deliberately is not one, since a ceiling on the count would be a
    second, unanchored constraint on the interval that the allowance has already decided.
    """
    if window_days < 1:
        msg = f"a window of {window_days} day(s) holds no partitions"
        raise PartitioningError(msg)
    return math.ceil(window_days / shortest_days(interval)) + premake_for(interval)


# --------------------------------------------------------------------------- the removal
class Removal(enum.StrEnum):
    """What happens to a period once every row in it is past the horizon.

    Three members because the two that are refused are refused for different reasons, and a
    boolean would collapse them into "not the one we chose".
    """

    #: Detach from the parent, leave the table for `SETTLE_DAYS`, then drop it.
    DETACH_THEN_DROP = "detach_then_drop"
    #: A `DELETE` over the live table with no detach at all.
    DELETE_IN_PLACE = "delete_in_place"
    #: Detach and keep the table indefinitely, which is what "archive" usually means.
    DETACH_AND_KEEP = "detach_and_keep"


def removal_refusals(removal: Removal) -> tuple[str, ...]:
    """Why this is not how a ledger partition is removed. Empty for the one that is.

    Exhaustive over `Removal` rather than a lookup, so a fourth member cannot arrive without
    somebody arguing for or against it, which is `brain.ops.admission.kind_of`'s construction.
    """
    match removal:
        case Removal.DETACH_THEN_DROP:
            return ()
        case Removal.DELETE_IN_PLACE:
            return (
                "a delete over the live table is the one operation partitioning exists to "
                "avoid: it rewrites every row it touches, leaves them on disk until a vacuum "
                "reclaims them, and holds a transaction open for as long as it runs, on the "
                "table every request writes to",
            )
        case Removal.DETACH_AND_KEEP:
            return (
                f"a detached table kept indefinitely holds metadata-ledger rows past the "
                f"{LEDGER_RETENTION_DAYS}-day horizon that governs them. "
                f"{AN_ARCHIVE_WITH_ITS_OWN_LIFETIME_IS_A_PER_ROW_OVERRIDE_IN_A_FILE}",
            )
        case _:  # pragma: no cover - unreachable while Removal has three members
            assert_never(removal)


#: How a period leaves the ledger. Detach and drop, with a settling window between them.
REMOVAL: Final[Removal] = Removal.DETACH_THEN_DROP


# ------------------------------------------------------------------------------ the spec
#: The column a row is routed to a partition by. It is the ingress time and nothing else:
#: `brain.ops.telemetry.Ingress.received_at` is the one timestamp on a ledger row that exists
#: before the request is identified, so a row for a refused request has one. A test asserts
#: this name is a key of what `RequestTelemetry.ledger_row` actually produces, rather than
#: trusting a string typed here to match a row shape declared in another module.
CONTROL_COLUMN: Final[str] = "received_at"


@dataclass(frozen=True)
class PartitionSpec:
    """One partitioned table, as the settings a migration has to write.

    Every field is either derived above or is a name a test can check against the thing it
    names. There is no field here holding a number somebody chose, and that is the property
    rather than a coincidence: `spec_gaps` is what notices when one appears.
    """

    #: The data class the rows belong to, which is what decides the horizon.
    data_class: DataClass
    control: str
    interval: Interval
    premake: int
    settle_days: int
    removal: Removal
    because: str

    def __post_init__(self) -> None:
        if not self.control.strip():
            msg = "a partitioned table with no control column routes every row to nowhere"
            raise PartitioningError(msg)
        if not self.because.strip():
            msg = f"the {self.data_class.value} partition scheme states no reason for its shape"
            raise PartitioningError(msg)
        if self.premake < 1:
            # Zero premade partitions is a table that accepts writes until the period rolls
            # and then refuses them, which presents as an outage at midnight on the first of
            # a month rather than as a configuration mistake.
            msg = (
                f"the {self.data_class.value} scheme premakes {self.premake} partition(s), so "
                "the first write into the next period has nowhere to go"
            )
            raise PartitioningError(msg)
        if self.settle_days < 0:
            msg = (
                f"the {self.data_class.value} scheme settles for {self.settle_days} day(s), "
                "which is not a window"
            )
            raise PartitioningError(msg)


#: The metadata ledger's scheme. Assembled from the derivations above rather than written out.
LEDGER_SPEC: Final[PartitionSpec] = PartitionSpec(
    data_class=LEDGER_DATA_CLASS,
    control=CONTROL_COLUMN,
    interval=PARTITION_INTERVAL,
    premake=PREMAKE,
    settle_days=SETTLE_DAYS,
    removal=REMOVAL,
    because=(
        "the ledger is the longest fixed window in the estate and the only table that grows "
        "with every request. The interval is the coarsest one whose over-retention fits "
        "inside what the backup window already tolerates, the premake covers a restore from "
        "the oldest backup, and the settling window is what the interval leaves of the same "
        "allowance"
    ),
)


def partman_settings(
    spec: PartitionSpec = LEDGER_SPEC, *, retention_days: int = LEDGER_RETENTION_DAYS
) -> Mapping[str, object]:
    """The scheme as pg_partman's own parameter names, for whoever writes the migration.

    A mapping rather than a paragraph, so the claim is machine-readable and a test can hold
    each value to the derivation it came from. `retention_keep_table` is true because the
    detached table is what settles; something has to drop it after `settle_days`, and that
    something is the retention executor `brain.ops.retention.StoreSweeper` describes and which
    is also not built.

    **A function taking the spec rather than a constant built from the declared one.** It was a
    constant, and a mutation found what that cost: substituting string surgery on the interval's
    own name for `partman_interval` survived, because `"monthly".removesuffix("ly")` is
    `"month"` and monthly is the only interval this module declares. The same substitution turns
    a daily scheme into `"1 dai"`, which Postgres cannot parse, and nothing could see it because
    nothing could ask for a daily scheme. Taking the spec is how a test asks.
    """
    return MappingProxyType(
        {
            "p_control": spec.control,
            "p_interval": partman_interval(spec.interval),
            "p_premake": spec.premake,
            "retention": f"{retention_days} days",
            "retention_keep_table": True,
            "settle_days": spec.settle_days,
        }
    )


#: The settings the metadata ledger's migration will need, from the declared scheme.
LEDGER_PARTMAN_SETTINGS: Final[Mapping[str, object]] = partman_settings()


def spec_gaps(
    spec: PartitionSpec = LEDGER_SPEC, *, row: Mapping[str, object] | None = None
) -> tuple[str, ...]:
    """Every way a partition scheme disagrees with the retention policy it is serving.

    Six findings, and the first four are the ones that make the scheme a claim about
    retention rather than about storage. The class must have a fixed window at all, since a
    class kept while its record exists has no date to align a partition to. The window has to
    be the one this module derived against. The interval has to satisfy the allowance. And the
    premake has to cover a restore.

    `row` is the ledger row shape the control column is checked against, defaulting to None so
    that a caller who does not have one still gets the other five findings. It is a parameter
    rather than an import of `RequestTelemetry` because the check is about a shape, and a
    version of this that could only be run against the shape it was written from is a check
    that cannot be shown to fail.
    """
    findings: list[str] = []
    horizon = horizon_for(spec.data_class)
    if horizon.lifetime is not Lifetime.FIXED_WINDOW or horizon.days is None:
        findings.append(
            f"{spec.data_class.value} is {horizon.lifetime.value}, so nothing about it expires "
            "on a date and there is no boundary for a partition to be aligned to"
        )
        return tuple(findings)
    findings.extend(interval_refusals(spec.interval))
    findings.extend(
        f"{spec.removal.value} is not how a ledger partition is removed: {reason}"
        for reason in removal_refusals(spec.removal)
    )
    spent = over_retention_days(spec.interval) + spec.settle_days
    if spent > MAX_OVER_RETENTION_DAYS:
        findings.append(
            f"alignment keeps a row {over_retention_days(spec.interval)} day(s) past its "
            f"horizon and settling keeps it {spec.settle_days} more, which is {spent} against "
            f"an allowance of {MAX_OVER_RETENTION_DAYS}. "
            f"{THE_INTERVAL_AND_THE_ARCHIVE_SPEND_FROM_ONE_ALLOWANCE}"
        )
    if spec.premake < premake_for(spec.interval):
        findings.append(
            f"{spec.premake} premade partition(s) of {spec.interval.value} cover "
            f"{spec.premake * shortest_days(spec.interval)} day(s) and a restore can be "
            f"{BACKUP_RETENTION_DAYS} day(s) behind. "
            f"{A_PARTITION_SET_THAT_STOPS_AT_TODAY_REFUSES_TOMORROWS_WRITE}"
        )
    if row is not None and spec.control not in row:
        findings.append(
            f"the scheme routes on {spec.control!r} and the row it is written for holds "
            f"{sorted(row)}, so every insert would fail to find a partition"
        )
    return tuple(findings)


# ------------------------------------------------------------- what is deliberately absent
#: Why there is no migration in this module, said where somebody looking for one will read it.
THERE_IS_NO_LEDGER_TABLE_TO_PARTITION: Final = (
    "M36.1.1.1 asks for pg_partman on the metadata ledger and no migration in this repository "
    "creates that table. brain.ops.telemetry says so in its own docstring: obs holds the audit "
    "chain, nothing calls open_request, and the eighteen-column record exists as a dataclass "
    "and nowhere else. A migration written here would have to invent that schema, its "
    "row-level security and its indexes, and the invented version would then be the one the "
    "real table has to be reconciled with. So the scheme is data, PARTMAN_SETTINGS is what the "
    "migration will need, and the migration belongs with the table."
)
