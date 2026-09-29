"""A trial read of the staff source: asked for on the Staff sources screen, made by the worker.

The screen's Try a read said "This install cannot try your staff source yet. Nothing here fetches
a list", which stopped being true on 2026-09-21 when `brain.ops.staff_sync_run` began reading every
source every night. On 2026-09-29 the owner's first Lark sync placed 123 people in no department,
and the button that would have shown him before the night's run still said it could not read
anything. This is the button's other half.

**The application cannot make the read, so it writes the asking down and the worker makes it.**
Only the worker reads the staff source's credential (`brain.ops.staff_sync_run.
THE_STAFF_SOURCE_CREDENTIAL_IS_A_CONNECTOR_KEY`), exactly as only the worker reads a connector's
key, so the shape is `brain.ops.connector_probe`'s: a request is an instant in `ops.setting`,
`staff_source.trial_requested`, `0059`'s trigger puts every press on the ledger with who pressed
it, and the worker's pass after each tick of the schedule makes the read when one is owed. See
`A_TRIAL_ASKED_FOR_IS_AN_INSTANT_AND_NOT_A_MESSAGE`.

**What the worker makes is the night's run with nothing applied.** `sync_staff_on(..., trial=True)`
chooses, leases, reads, checks and plans exactly as the run does and appends one row with outcome
`tried`, the counts of what a run would change and the reading's report, and writes no member. See
`brain.ops.staff_sync_run.A_TRIAL_IS_THE_RUN_WITH_NOTHING_APPLIED`.

**Any run that starts after the press answers it.** A trial row, a failed trial, and the night's
own run all read the source and all say what they read, so the rule is the one
`brain.ops.schedule_control.chosen_this_tick` keeps for a run asked for: owed while no run has
started at or after the instant. Nothing is consumed, a second press only moves the instant, and a
worker that stops mid-read loses nothing. **A request older than `TRIAL_ANSWERED_WITHIN` is let go**,
because a chosen source that no longer reads a list appends no row and would otherwise leave a
request owed on every tick for ever.

Rejected: asking for a run of `directory_sync` through `schedule.run_requested`. That is the door
that exists, and it applies the list: the whole point of a trial is to see what would happen before
anything does. Rejected: reading in the application with a credential typed again. The connect
drawer's test does that before a source is saved; once it is saved, the person pressing may not hold
the secret, and the key the worker reads with is the one the night's run will use.

Task ids: M1.6.11, M1.6.12, M27.7.2
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.setting_store import put, read_namespace
from brain.ops.staff_sync_run import StaffSyncRun, run_staff_sync_now
from brain.ops.staff_sync_store import read_last_started
from brain.tables.config import SettingType

# ------------------------------------------------------------------ written-down reasons
#: Why a request to try the source is stored as an instant.
A_TRIAL_ASKED_FOR_IS_AN_INSTANT_AND_NOT_A_MESSAGE: Final = (
    "Every run of the staff source appends a row with when it started, so a trial asked for is one "
    "more instant: read the source if no run has started since. The row the read appends answers "
    "the request, so nothing has to consume it, a worker that stops mid-read loses nothing, and "
    "pressing twice asks for one read rather than two."
)

# ------------------------------------------------------------------------ the figures
#: The namespace and the one key a request is kept under in `ops.setting`.
REQUEST_NAMESPACE: Final = "staff_source"
REQUEST_KEY: Final = f"{REQUEST_NAMESPACE}.trial_requested"

#: What a request row says about itself in `ops.setting.description`.
REQUEST_DESCRIPTION: Final = "When a person last asked for the staff source to be read as a trial"

#: How long a request waits for a run before it is let go. The worker ticks every minute, so a
#: request still unanswered after this is one no run can answer.
TRIAL_ANSWERED_WITHIN: Final = timedelta(minutes=15)

# ------------------------------------------------------------------------ the sentences
#: What pressing Try a read agrees to, and what the screen says while the worker has not read.
TRIAL_WAITING: Final = (
    "Asked. The worker reads your staff source with the credential it keeps, usually within a "
    "minute, and changes nobody. What it read appears under Recent sync runs as a trial read."
)

#: What the screen says when no trial is waiting.
NO_TRIAL_WAITING: Final = ""


class TrialRequestError(Exception):
    """Raised for a request that could not be a row: a naive instant."""


# ---------------------------------------------------------------------------- the rule
def trial_owed(
    requested: datetime | None, last_started: datetime | None, *, now: datetime
) -> bool:
    """Whether a trial is owed at `now`: asked for, not in the future, not stale, not answered.

    Strict on the run, so a run that started at the very instant of the press answers it, which is
    `brain.ops.schedule_control.chosen_this_tick`'s comparison.
    """
    if requested is None or requested > now or now - requested > TRIAL_ANSWERED_WITHIN:
        return False
    return last_started is None or last_started < requested


def waiting(requested: datetime | None, last_started: datetime | None, *, now: datetime) -> bool:
    """Whether the screen should say a trial is waiting: asked for, not stale and not answered.

    Not `trial_owed`: a press the worker has not reached yet is in the future of no tick, and it is
    still waiting.
    """
    if requested is None or now - requested > TRIAL_ANSWERED_WITHIN:
        return False
    return last_started is None or last_started < requested


# ------------------------------------------------------------------------ the rows
async def trial_requested(session: AsyncSession) -> datetime | None:
    """When a trial was last asked for, or None for no readable request.

    `brain.ops.schedule_control.requested_at` is the reading, so a row that does not hold a zoned
    instant is not a request here for the reason it is not one there. Imported here rather than at
    the top, for `brain.ops.connector_probe.requests_in`'s reason: that module imports the runners.
    """
    from brain.ops.schedule_control import requested_at

    state = (await read_namespace(session, REQUEST_NAMESPACE)).get(REQUEST_KEY)
    return None if state is None else requested_at(state)


async def request_trial(session: AsyncSession, *, at: datetime, by: str) -> None:
    """Ask for one trial read at or after `at`, in the caller's transaction.

    The caller sets the ledger's attribution first (`brain.attribution.attribute`), so the entry
    `0059`'s trigger appends names who pressed it.
    """
    if at.tzinfo is None:
        msg = "a trial asked for at a naive instant would be made early or late by the host's offset"
        raise TrialRequestError(msg)
    await put(
        session,
        REQUEST_KEY,
        value_type=SettingType.STRING,
        value=at.isoformat(),
        description=REQUEST_DESCRIPTION,
        updated_by=by,
    )


# ------------------------------------------------------------------------ the worker's half
def _trial_in_thread(database_url: str, now: datetime) -> StaffSyncRun:
    """What the thread runs: a literal call to `run_staff_sync_now` as a trial, with the worker's
    vault, read from this process's settings as the `directory_sync` runner reads it."""
    from brain.ops.worker import _loop_factory
    from brain.settings import process_environment, settings_from

    settings = settings_from(process_environment())
    return run_staff_sync_now(
        database_url,
        now=now,
        vault_address=settings.vault_address,
        vault_token=settings.vault_token,
        loop_factory=_loop_factory(),
        trial=True,
    )


async def tick_staff_trial(
    sessions: async_sessionmaker[AsyncSession],
    *,
    now: datetime,
    database_url: str,
) -> StaffSyncRun | None:
    """Make the trial owed at `now`, or return None having read one small statement.

    Called by `brain.ops.worker.run_schedule` after each tick, so the common case, nothing asked,
    is one read of one key. The read itself runs in a thread with its own loop and engine, the
    shape `brain.ops.connector_probe_run.tick_probes` takes, because the directory calls block,
    and the thread's work is a literal call to `_trial_in_thread` for that function's reason: a
    function handed to the thread as a value reads as a caller nothing reaches.
    """
    async with sessions() as session:
        requested = await trial_requested(session)
        started = await read_last_started(session) if requested is not None else None
    if not trial_owed(requested, started, now=now):
        return None
    return await asyncio.to_thread(lambda: _trial_in_thread(database_url, now))
