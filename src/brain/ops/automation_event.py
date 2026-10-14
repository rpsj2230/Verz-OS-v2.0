"""What starts an automation besides the clock: a change a connector's index reports.

The owner decided this on 2026-10-13 (needs-rupash 223, option B): an automation starts by a
schedule or by a connected source reporting a changed record, and **by nothing that faces the
internet**. No
signed inbound address, no webhook, no secret in a URL. A webhook is a kind the form still names
because the closed list of kinds is `brain.orchestration.unattended.TriggerKind`, and it is refused
in words when somebody writes one (`WEBHOOKS_ARE_NOT_OFFERED`). This module holds the decisions a
change-started run makes and `brain.ops.automation_event_store` is the half that holds a connection.
Nothing here reads a clock, opens a connection or writes a row.

**A change is a record id and the instant it changed, and never its content.** The marker is
`proj.record.updated_at`, which `brain.ops.connector_sync_store.record_upsert` now moves only when a
record's fields change or a retired record returns. Until then it moved on every upsert, so a
source confirming nothing new would have started a run for every record on every sync, which is
the flood this decision exists to avoid. `last_seen_at` is not it, for the reason
`brain.tables.projection` gives about staleness.

**A change starts a run only for an owner who may read the record.** The store filters the changed
rows by the owner's row scope, compiled by `brain.core.scope_sql.compile_where`, inside the
statement. A run that started for a record its owner cannot read would tell them the record
exists and changed, which is a count of what they may not see by another route; and the owner's
reach is the run's, `E(owner) ∩ agent_ceiling` through `brain.ops.automation_run.admitted_run`, so
a change outside it is absent from the automation exactly as it is absent from the person. See
`A_CHANGE_OUTSIDE_THE_OWNERS_REACH_STARTS_NOTHING`.

**Every change is one run, once, however often it is found.** A run's id is derived from the
automation and the change (`brain.ops.automation_run.run_id` with a `change_key`), so a second
worker, a retried pass or a pass that overlaps the last one writes the same id and the table's key
refuses it. That is also what makes the look-back safe: a source's page is written in a transaction
that began before it committed, so a row stamped a moment ago can become visible after a pass has
gone by. Each pass therefore looks back `SETTLE` before the newest change it has run, and the ids
sort out what was already done. Rejected: a stored cursor, which is a second fact beside the runs
and the one a restored backup would leave pointing past changes it had never run.

**Two bounds, and a change over a bound waits and is never lost until it is a day old.** A pass runs
at most `EVENT_RUNS_PER_PASS` changes of one automation and an automation at most
`EVENT_RUNS_PER_HOUR` in an hour, because a source that rewrites a thousand records is one event
a person did not mean as a thousand runs. Changes beyond the bounds are found by the next pass in
order. One older than `MAX_AGE` is not run: a run at that point would answer a change nobody
remembers, and the bound on how far back a pass reads is also what bounds the query.

Task ids: M17.4.1
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from brain.ops.automation_run import run_id
from brain.orchestration.unattended import TriggerKind

# ------------------------------------------------------------------ written-down reasons
#: Why a record the owner may not read starts nothing.
A_CHANGE_OUTSIDE_THE_OWNERS_REACH_STARTS_NOTHING: Final = (
    "A change starts a run only when the person it runs as may read the changed record, decided "
    "by their row scope inside the statement that finds changes. A run started by a record they "
    "cannot read would say that the record exists and moved, and nobody is told a thing about "
    "what they may not see by being handed a run of their own automation."
)

#: Why a webhook is refused when somebody writes one.
WEBHOOKS_ARE_NOT_OFFERED: Final = (
    "Nothing on this install starts work from a call made from outside it. An automation starts on "
    "a schedule or when a connected source reports a change, and a web address that started work "
    "is a door onto the internet that nobody has asked this install to open."
)

#: What the form says beside a webhook, which it still lists so the choice is visibly closed.
WEBHOOK_NOT_OFFERED_ON_THE_FORM: Final = (
    "Not offered. An automation here starts on a schedule or when a connected source reports a "
    "change, and nothing starts work from outside."
)

#: Why a change is run once whoever finds it.
A_CHANGE_RUNS_ONCE_HOWEVER_OFTEN_IT_IS_FOUND: Final = (
    "A run's id is derived from the automation and the change, so a pass that overlaps the last, a "
    "second worker or a retry after a rollback writes the id that is already there and the key "
    "refuses it. The look-back that makes a late-committed change visible is safe for that reason "
    "alone."
)

# ------------------------------------------------------------------ the figures
#: How many changes one automation runs in one pass. A pass is a minute apart.
EVENT_RUNS_PER_PASS: Final = 5

#: How many runs one automation makes in an hour, however many changes wait.
EVENT_RUNS_PER_HOUR: Final = 20

#: The hour the bound above is counted over.
RUNS_WINDOW: Final = timedelta(hours=1)

#: How far before the newest change a pass has run it looks again. Longer than any transaction
#: the sync holds open, which is seconds.
SETTLE: Final = timedelta(minutes=5)

#: How old a change may be and still start a run.
MAX_AGE: Final = timedelta(hours=24)

#: What a refusal at the door of an armed automation is keyed by, so it is recorded once.
REFUSED_AT_THE_DOOR: Final = "refused at the door"

#: The kinds a change or a clock starts. `TriggerKind.WEBHOOK` is the one that is not here.
STARTABLE_KINDS: Final[frozenset[TriggerKind]] = frozenset(
    {TriggerKind.SCHEDULE, TriggerKind.CONNECTOR_EVENT}
)


@dataclass(frozen=True)
class Change:
    """One changed record: which, and when its fields last changed. Never what they say."""

    source: str
    entity: str
    source_id: str
    changed_at: datetime

    def __post_init__(self) -> None:
        if self.changed_at.tzinfo is None:
            msg = "a change with no timezone is a different instant on every host"
            raise ValueError(msg)

    @property
    def order(self) -> tuple[datetime, str, str]:
        """The order changes are run in: oldest first, then by entity and record, which is total."""
        return (self.changed_at, self.entity, self.source_id)


def change_key(change: Change) -> str:
    """The change as `brain.ops.automation_run.run_id` hashes it: the record and its instant."""
    at = change.changed_at.astimezone(UTC).isoformat(timespec="microseconds")
    return f"{change.source}\n{change.entity}\n{change.source_id}\n{at}"


def event_run_id(automation_id: str, change: Change) -> str:
    """The id of the one run this change makes of this automation."""
    return run_id(automation_id, change.changed_at, change_key(change))


def refusal_run_id(automation_id: str, armed_at: datetime) -> str:
    """The id of the one refusal an arming can have, so a pass that repeats it writes nothing."""
    return run_id(automation_id, armed_at, REFUSED_AT_THE_DOOR)


@dataclass(frozen=True)
class Window:
    """Which changes a pass reads: after the arming, and not before a floor that moves with runs."""

    #: Strictly after this instant, which is when the automation was armed.
    after: datetime
    #: At or after this instant.
    not_before: datetime


def window(*, armed_at: datetime, newest_run: datetime | None, now: datetime) -> Window:
    """The changes to read: nothing before the arming, nothing older than `MAX_AGE`, and nothing
    before the newest change run less `SETTLE`.

    `newest_run` is the greatest instant of a change this automation has run, or None for one that
    has run none.
    """
    floor = now - MAX_AGE
    if newest_run is not None:
        floor = max(floor, newest_run - SETTLE)
    return Window(after=armed_at, not_before=max(floor, armed_at))


def allowance(*, ran_this_hour: int) -> int:
    """How many changes this pass may run: the pass bound, less what the hour has already used."""
    return max(0, min(EVENT_RUNS_PER_PASS, EVENT_RUNS_PER_HOUR - ran_this_hour))


def fetch_limit(*, recorded_in_window: int) -> int:
    """How many changed rows a pass reads, which is enough to get past every one it has run.

    Those already run sort ahead of those that have not, and are at most as many as the runs
    recorded in the window, so reading that many more than the pass may run always reaches one it
    may. A fixed number would stall for good the day a window held more than it.
    """
    return EVENT_RUNS_PER_PASS + recorded_in_window


def changes_to_run(
    automation_id: str,
    found: Sequence[Change],
    *,
    recorded: Collection[str],
    allowed: int,
) -> tuple[Change, ...]:
    """The oldest of `found` that have no run yet, at most `allowed`, in the order they are run."""
    fresh = [
        one
        for one in sorted(found, key=lambda c: c.order)
        if event_run_id(automation_id, one) not in recorded
    ]
    return tuple(fresh[: max(0, allowed)])
