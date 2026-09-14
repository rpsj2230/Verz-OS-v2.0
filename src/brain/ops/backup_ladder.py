"""Which copies a retention ladder keeps, decided without deleting anything.

`brain.ops.recovery` declares the ladder M30.3.5 asks for, thirty daily, twelve weekly and twelve
monthly, and refuses to adopt it: the ladder keeps a copy up to 372 days old and every erasure
certificate promises a deletion is beyond backup reach after `BACKUP_RETENTION_DAYS`, which is 35.
That refusal stands and this module keeps it. What was missing beside it is the selection itself,
so that on the day somebody moves one of the two numbers the pruning is a function that has
already been tested across a year boundary, rather than a date calculation written that
afternoon against a live bucket.

**This module decides and does not prune.** It takes copies and an instant and returns which are
kept and which are not, and nothing here lists a bucket, deletes an object or reads a clock.
Nothing anywhere prunes to a ladder today either: the only thing that removes a copy is the
bucket's own lifecycle rule in `ops/seaweedfs/provision.sh`, which expires every object at 35
days whatever this module would have said. A pruner is a runner on the client's own server, in
the shape of `ops/backup/brain-backup`, and it is not written.

**The ladder is refused when it outlives the horizon, so the declared one is refused by
default.** `select` takes the horizon as a parameter defaulting to `BACKUP_RETENTION_DAYS` and
raises when `Ladder.horizon_days` exceeds it, with
`THE_LADDER_OUTLIVES_THE_HORIZON_EVERY_CERTIFICATE_PROMISES` as the reason. A caller can only
select to thirty, twelve and twelve by stating a horizon of at least 372 days, and stating that
is the decision `brain.ops.recovery` says is not this repository's to take.

**A ladder counts periods that hold a copy, not calendar periods.** Thirty daily copies means the
newest copy from each of the thirty most recent days on which a copy was taken, which is
restic's `--keep-daily` and pgBackRest's reading too. The calendar reading, keep whatever falls
in the last thirty days, deletes every daily copy during a fortnight's outage of the taker, and
the copies it deletes are the last good ones before whatever stopped it. See
`A_LADDER_COUNTS_DAYS_THAT_HOLD_A_COPY_NOT_DAYS_ON_THE_CALENDAR`.

**The calendar still has the last word, and only about age.** Counting periods means a copy can
be kept older than the ladder's horizon when copies were taken irregularly: thirty daily copies
taken every third day reach ninety days back. A certificate does not know the taker was
irregular, so no copy is kept once it is `horizon_days` old, whatever a rung counted. See
`NO_COPY_IS_KEPT_PAST_THE_HORIZON_WHATEVER_A_RUNG_COUNTED`.

**Periods are UTC days, ISO weeks and UTC months.** A copy stamped 00:30 at +08:00 belongs to the
previous UTC day, and bucketing by the server's own zone would make two installs of one product
disagree about which copy is Monday's, and give a daylight-saving day of twenty-three hours in
which two copies share a date. A week keyed by week-of-year splits the week holding 1 January in
two and keeps two weekly copies days apart at every new year; an ISO week keeps it whole. See
`A_PERIOD_IS_A_UTC_PERIOD` and `A_WEEK_IS_AN_ISO_WEEK`.

**Only a copy that restores on its own is laddered.** A full dump and a content-addressed
snapshot each restore without anything else. An incremental restores on top of the full below
it, and continuous archiving replays onto a base, and neither `Backup` nor the manifest
`brain.ops.backup_manifest` reads names that base. Selecting by date across a chain would
delete a full that twelve kept incrementals still need, and the copies would go on being listed
as kept. So chained methods are refused rather than guessed at. See
`A_CHAIN_IS_NOT_PRUNED_BY_THE_CALENDAR`. The nightly taker writes `full` today, so nothing it
produces is refused.

Rejected: a pruning function in `brain.ops.recovery` beside the ladder. That module's docstring
argues there is none there because pruning to the declared ladder is the act that makes the
certificates wrong, and it imports nothing that could act. A selection that refuses the declared
ladder is not that act, and keeping it out of the declaration keeps the declaration's argument
true as written.

Rejected: keeping the newest copy of a coverage unconditionally, as a floor under the age cap.
It is the obvious safety net against a taker that stopped, and it is a copy past the horizon a
certificate promised was gone. It would also describe a shelf that does not exist: the bucket's
lifecycle rule has already expired that object, so a selection keeping it is a selection about
nothing.

Scope: domain logic. Every clock and every copy is a parameter, for the reason
`brain.ops.recovery` gives: the cases that are always wrong are the ones you cannot reach
through a module that owns the bucket.

Task ids: none
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from brain.ops.recovery import (
    RETENTION_LADDER,
    THE_LADDER_OUTLIVES_THE_HORIZON_EVERY_CERTIFICATE_PROMISES,
    Backup,
    Coverage,
    Ladder,
    Method,
    RecoveryError,
)
from brain.ops.retention import BACKUP_RETENTION_DAYS

# ------------------------------------------------------------------ written-down reasons
#: Why a rung counts the periods that hold a copy.
A_LADDER_COUNTS_DAYS_THAT_HOLD_A_COPY_NOT_DAYS_ON_THE_CALENDAR: Final = (
    "Keeping whatever falls in the last thirty calendar days deletes every daily copy while the "
    "taker is down, and the copies it deletes are the last good ones before whatever stopped it. "
    "Counting the thirty most recent days that hold a copy keeps thirty copies through an outage "
    "of any length, which is what somebody reading thirty daily copies believes they have."
)

#: Why the horizon caps the age of every copy, whatever a rung counted.
NO_COPY_IS_KEPT_PAST_THE_HORIZON_WHATEVER_A_RUNG_COUNTED: Final = (
    "Counting periods that hold a copy lets a rung reach further back than its horizon when "
    "copies were irregular: thirty daily copies taken every third day reach ninety days. An "
    "erasure certificate states a date after which a deletion is beyond backup reach and knows "
    "nothing about the taker's cadence, so a copy that has reached the horizon is not kept, and "
    "the bucket's own lifecycle rule has expired it by then in any case."
)

#: Why periods are taken in UTC.
A_PERIOD_IS_A_UTC_PERIOD: Final = (
    "A copy stamped half past midnight at +08:00 is the previous day in UTC. Bucketing by the "
    "server's own zone makes two installs of one product disagree about which copy is Monday's, "
    "and a daylight-saving change gives a day of twenty-three hours in which two copies share a "
    "date and one of them is pruned as a duplicate."
)

#: Why a week is an ISO week.
A_WEEK_IS_AN_ISO_WEEK: Final = (
    "A week keyed by week-of-year restarts at 1 January, so the week holding new year is two "
    "weeks and keeps two weekly copies a few days apart. An ISO week runs Monday to Sunday "
    "across the year boundary and belongs to one ISO year, so every week is seven days and "
    "keeps one copy."
)

#: Why an incremental or an archived segment is refused.
A_CHAIN_IS_NOT_PRUNED_BY_THE_CALENDAR: Final = (
    "An incremental restores on top of the full below it and an archived segment replays onto a "
    "base, and nothing a copy records names that base. Selecting by date across a chain deletes "
    "a full that the kept incrementals still need, and they go on being listed as kept while "
    "restoring nothing. A chain is pruned by the tool that knows its links, never by a ladder "
    "that can only see dates."
)

#: The methods whose copies restore on their own, and so the only ones a ladder may select.
SELF_CONTAINED: Final[frozenset[Method]] = frozenset({Method.FULL, Method.SNAPSHOT})


class Rung(enum.StrEnum):
    """One kind of period a ladder keeps a copy per."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


def period_of(instant: datetime, rung: Rung) -> tuple[int, ...]:
    """The period an instant falls in, ordered so a later period compares greater.

    Converted to UTC first; see `A_PERIOD_IS_A_UTC_PERIOD`. A week is `(ISO year, ISO week)`,
    which is not `(calendar year, week)`: 2018-12-31 is in the first week of 2019. See
    `A_WEEK_IS_AN_ISO_WEEK`.
    """
    if instant.tzinfo is None:
        msg = "a naive instant falls in whichever day this machine's offset puts it in"
        raise RecoveryError(msg)
    utc = instant.astimezone(UTC)
    match rung:
        case Rung.DAILY:
            return (utc.year, utc.month, utc.day)
        case Rung.WEEKLY:
            iso = utc.isocalendar()
            return (iso.year, iso.week)
        case Rung.MONTHLY:
            return (utc.year, utc.month)


def count_for(ladder: Ladder, rung: Rung) -> int:
    """How many periods of this kind the ladder keeps a copy for."""
    match rung:
        case Rung.DAILY:
            return ladder.daily
        case Rung.WEEKLY:
            return ladder.weekly
        case Rung.MONTHLY:
            return ladder.monthly


@dataclass(frozen=True)
class Kept:
    """One copy the ladder keeps, and every rung that keeps it.

    The rungs are carried because a copy kept only as the twelfth monthly is the one a person
    deciding to shorten the ladder needs to see, and a bare list of kept copies cannot say
    which those are.
    """

    backup: Backup
    rungs: frozenset[Rung]

    def __post_init__(self) -> None:
        if not self.rungs:
            msg = f"backup {self.backup.backup_id!r} is kept by no rung, which is not kept"
            raise RecoveryError(msg)


@dataclass(frozen=True)
class Selection:
    """Every copy handed in, as kept or not kept. Each copy is in exactly one of the two."""

    kept: tuple[Kept, ...]
    pruned: tuple[Backup, ...]


def _newest(one: Backup) -> tuple[datetime, str]:
    return (one.recoverable_to, one.backup_id)


def select(
    backups: Sequence[Backup],
    *,
    now: datetime,
    ladder: Ladder = RETENTION_LADDER,
    horizon_days: int = BACKUP_RETENTION_DAYS,
) -> Selection:
    """Which copies `ladder` keeps at `now`, per coverage, capped at `horizon_days` old.

    Each coverage is laddered on its own: a database dump and an object store snapshot taken on
    one day are two copies of two things, and one must not stand in for the other.

    Within a coverage, for each rung, the newest copy in each of the `count` most recent periods
    that hold a copy is kept. See the module docstring for why periods holding a copy are counted
    rather than calendar periods, and why no copy survives the horizon.

    Refuses rather than selects when the ladder outlives the horizon, when a copy is chained,
    when a copy restores to a moment after `now`, when two copies share an identifier and when
    `now` is naive. Every one of those is a selection that would delete the wrong thing and
    report success.
    """
    if now.tzinfo is None:
        msg = "a naive now ages every copy by this machine's offset"
        raise RecoveryError(msg)
    reach = ladder.horizon_days()
    if reach > horizon_days:
        msg = (
            f"the ladder keeps a copy for up to {reach} days and the horizon is {horizon_days}. "
            f"{THE_LADDER_OUTLIVES_THE_HORIZON_EVERY_CERTIFICATE_PROMISES}"
        )
        raise RecoveryError(msg)

    seen: set[str] = set()
    for one in backups:
        if one.backup_id in seen:
            msg = (
                f"backup {one.backup_id!r} is handed in twice, and a pruner deleting by "
                "identifier would delete the copy this selection kept"
            )
            raise RecoveryError(msg)
        seen.add(one.backup_id)
        if one.method not in SELF_CONTAINED:
            msg = (
                f"backup {one.backup_id!r} is a {one.method.value} copy. "
                f"{A_CHAIN_IS_NOT_PRUNED_BY_THE_CALENDAR}"
            )
            raise RecoveryError(msg)
        if one.recoverable_to > now:
            msg = (
                f"backup {one.backup_id!r} restores to a moment that has not happened, so a "
                "clock somewhere disagrees and its age here would be negative"
            )
            raise RecoveryError(msg)

    oldest = timedelta(days=horizon_days)
    rungs_of: dict[str, set[Rung]] = {}
    for coverage in Coverage:
        young = [
            one for one in backups if one.coverage is coverage and now - one.recoverable_to < oldest
        ]
        for rung in Rung:
            newest_in: dict[tuple[int, ...], Backup] = {}
            for one in young:
                period = period_of(one.recoverable_to, rung)
                held = newest_in.get(period)
                if held is None or _newest(one) > _newest(held):
                    newest_in[period] = one
            for period in sorted(newest_in, reverse=True)[: count_for(ladder, rung)]:
                rungs_of.setdefault(newest_in[period].backup_id, set()).add(rung)

    ordered = sorted(backups, key=_newest)
    return Selection(
        kept=tuple(
            Kept(backup=one, rungs=frozenset(rungs_of[one.backup_id]))
            for one in ordered
            if one.backup_id in rungs_of
        ),
        pruned=tuple(one for one in ordered if one.backup_id not in rungs_of),
    )
