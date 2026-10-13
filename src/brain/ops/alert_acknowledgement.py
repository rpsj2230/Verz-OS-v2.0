"""Acknowledging an alert: who and when, and the repeat notice that stops (M27.15.45).

`brain.ops.alerting` gives every severity an acknowledgement window and says nothing records one
being met. An incident on the Incidents screen is read off the worker's newest attempt at a source,
so there is nothing to mark. This is the mark: `ops.alert_acknowledgement` (`0224`), one row per
incident, keyed on its kind, its subject and the instant it began.

**The first press wins and a second changes nothing.** `acknowledge` inserts and, when the row is
there already, reads it back, so the person and the instant that come back are always the first
person's. Who acknowledged an incident is a fact about the past and a second person pressing a
button does not make it a different fact. Rejected: an upsert, which would let a later press
rewrite who and when and turn the record into a last-writer-wins field.

**An acknowledgement stops the repeat and nothing else.** `notice_may_repeat` is the one rule a
sender asks before it says an alert again: an acknowledged alert is not repeated, and an
unacknowledged one is repeated once the interval has passed since it was last said. The incident
stays on the screen and keeps its state; acknowledging says somebody has seen it, never that it is
fixed, so a source that is still down is still listed as down. See
`AN_ACKNOWLEDGEMENT_STOPS_THE_REPEAT_AND_NEVER_HIDES_THE_INCIDENT`.

**A source that recovers and fails again is a new incident.** The key carries `since`, so the new
failure has no row and is notified afresh.

**Nothing here decides who may acknowledge.** The route asks the screen's own grant held across
the whole install, which is `brain.console.department_console.held_across_the_install`'s question,
and this module takes the person as a value. The decision lives where the reader's reach is known.

Task ids: M27.15.45
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from brain.tables.alert_acknowledgement import AlertAcknowledgementRow, AlertKind

# ------------------------------------------------------------------ written-down reasons
#: Why acknowledging leaves the incident on the screen.
AN_ACKNOWLEDGEMENT_STOPS_THE_REPEAT_AND_NEVER_HIDES_THE_INCIDENT: Final = (
    "Acknowledging an alert says somebody has seen it, never that it is fixed. The repeat notice "
    "stops, and the incident stays listed in the state the worker found, so a source that is still "
    "down is still shown as down and an acknowledgement cannot be used to make a screen look calm."
)

#: Why only the first acknowledgement is kept.
THE_FIRST_ACKNOWLEDGEMENT_IS_THE_RECORD: Final = (
    "Who acknowledged an incident, and when, is a fact about the past. A second press finds the "
    "first row and writes nothing, so the record can never be rewritten by whoever pressed last."
)

#: The most keys one read of acknowledgements takes, so a listing cannot ask for the table.
MOST_KEYS_READ: Final = 500


@dataclass(frozen=True)
class Acknowledged:
    """Who acknowledged one incident and when. A value; the row carries nothing else."""

    kind: AlertKind
    subject: str
    since: datetime
    by: str
    at: datetime


def notice_may_repeat(
    *, acknowledged: bool, last_said: datetime | None, every: timedelta, now: datetime
) -> bool:
    """Whether an alert is said again at `now`.

    Never once it is acknowledged. Otherwise when it was never said, or when `every` has passed
    since it last was. `every` must be positive, because a zero interval says an alert on every
    pass, which is a flood and not a repeat.
    """
    if every <= timedelta(0):
        msg = "a repeat interval is positive"
        raise ValueError(msg)
    if acknowledged:
        return False
    return last_said is None or now - last_said >= every


async def acknowledge(
    session: AsyncSession, *, kind: AlertKind, subject: str, since: datetime, by: str
) -> Acknowledged:
    """Record `by` as acknowledging this incident, or return who already did.

    The session's principal (`app.principal_id`) must be `by`, which `0224`'s insert policy holds.
    """
    await session.execute(text("SELECT set_config('app.principal_id', :by, true)"), {"by": by})
    await session.execute(
        insert(AlertAcknowledgementRow)
        .values(kind=kind.value, subject=subject, since=since, acknowledged_by=by)
        .on_conflict_do_nothing(constraint="uq_alert_one_acknowledgement")
    )
    row = (
        await session.execute(
            select(AlertAcknowledgementRow).where(
                AlertAcknowledgementRow.kind == kind.value,
                AlertAcknowledgementRow.subject == subject,
                AlertAcknowledgementRow.since == since,
            )
        )
    ).scalar_one()
    return Acknowledged(
        kind=kind,
        subject=row.subject,
        since=row.since,
        by=row.acknowledged_by,
        at=row.acknowledged_at,
    )


async def acknowledgements(
    session: AsyncSession, kind: AlertKind, subjects: Collection[str]
) -> Mapping[tuple[str, datetime], Acknowledged]:
    """The acknowledgements of these subjects' incidents, keyed on (subject, since)."""
    if not subjects:
        return {}
    rows = (
        (
            await session.execute(
                select(AlertAcknowledgementRow)
                .where(
                    AlertAcknowledgementRow.kind == kind.value,
                    AlertAcknowledgementRow.subject.in_(sorted(subjects)[:MOST_KEYS_READ]),
                )
                .order_by(AlertAcknowledgementRow.acknowledged_at)
            )
        )
        .scalars()
        .all()
    )
    return {
        (one.subject, one.since): Acknowledged(
            kind=kind,
            subject=one.subject,
            since=one.since,
            by=one.acknowledged_by,
            at=one.acknowledged_at,
        )
        for one in rows
    }
