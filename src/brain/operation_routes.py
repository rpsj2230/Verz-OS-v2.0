"""The interrupted actions over HTTP: every side effect a stopped worker left unconfirmed, and
what the recovery sweep learnt about each, for the person who decides whether to issue it again.

`brain.ops.recovery_run.resume_side_effects` reads back what a connector can answer for and
leaves the rest `UNKNOWN`. Nothing is retried by the machine, so a record left unknown is a
decision waiting for somebody, and a decision nobody is shown is a record that stays unknown for
ever. This is where it is shown.

**Who may see the list is who may see the job that sweeps it.** The reader is asked
`brain.jobs_routes.may_see_job` for `side_effect_resume`, which is the queue screen's read over
a row that carries no person and no department, so it opens for a reader whose read of the queue
covers the whole install and nobody else. There is no second decision here. A reader it refuses
is answered an empty list, which is what an install with nothing interrupted is answered, so the
response never says a narrowing happened and never counts what it did not show.

**What an entry carries is what a person needs to look for it at the source.** The connector,
the tool, the operation's key, its state, when it last moved and what the sweep learnt. Not who
issued it and not its intent reference: the person deciding can find the act at the source from
the connector, the tool and the time, and a list of who did what across the install is a second
activity log this screen has no reason to become.

**An unknown record is listed at any age, and a sent or verifying one only past the sweep's
grace.** Unknown is where a record rests waiting for somebody, and the sweep's own move to it
stamps it now, so holding it to the grace would hide it for a minute after the sweep had finished.
A sent record younger than `stale_after` may be held by a live worker about to confirm it, and
listing it would put an ordinary call in front of a person as though it had been interrupted.

Rejected: a retry button here. Issuing again is `brain.ops.idempotency.issue_once` under the
operation's own key, from the tool that raised it; a second door that issues would be a second
place for the exactly-once rule to be wrong, and the leaf this serves asks for the read-back to
come before any retry, not for the retry.

Task ids: M23.3.1
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Failed
from brain.jobs_routes import may_see_job
from brain.ops.heartbeat import stale_after
from brain.ops.recovery_run import StoredOperations, Waiting, standing_of
from brain.routing_routes import sessions_of

#: The control whose job decides who may see the list.
SWEPT_BY: Final = "side_effect_resume"

#: Where the list is served.
INTERRUPTED_PATH: Final = "/operations/interrupted"

router = APIRouter(prefix=API_PREFIX, tags=["operate"])


class InterruptedView(BaseModel):
    """One unconfirmed side effect, as a person looking for it at the source needs it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    connector: str
    tool: str
    state: str
    since: datetime
    #: What the sweep learnt, or that it has not looked yet. Product text.
    standing: str


class InterruptedPage(BaseModel):
    """Every interrupted side effect this reader may see."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: datetime
    operations: tuple[InterruptedView, ...]


def interrupted_for(
    waiting: Sequence[Waiting], reach: EntitlementSet, now: datetime
) -> tuple[InterruptedView, ...]:
    """What this reach is shown of the waiting records: all of them, or nothing."""
    if not may_see_job(SWEPT_BY, reach, now):
        return ()
    return tuple(
        InterruptedView(
            key=one.operation.key,
            connector=one.operation.connector,
            tool=one.operation.tool,
            state=one.operation.state.value,
            since=one.since,
            standing=standing_of(one.operation),
        )
        for one in waiting
    )


def interrupted_before(now: datetime, grace: timedelta | None = None) -> datetime:
    """The instant before which an unconfirmed record counts as interrupted."""
    return now - (stale_after() if grace is None else grace)


@router.get(INTERRUPTED_PATH, response_model=InterruptedPage, responses=COMMON_RESPONSES)
async def interrupted(request: Request, asked: Asked) -> InterruptedPage:
    """Every side effect a stopped worker left unconfirmed, for a reader who may see the sweep."""
    if not may_see_job(SWEPT_BY, asked.reach, asked.now):
        return InterruptedPage(as_of=asked.now, operations=())
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    waiting = await StoredOperations(sessions).waiting(interrupted_before(asked.now))
    return InterruptedPage(
        as_of=asked.now, operations=interrupted_for(waiting, asked.reach, asked.now)
    )
