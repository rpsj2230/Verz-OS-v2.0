"""A scheduled control paused by a person, or asked to run now, and what the worker's tick does
about each.

`brain.ops.worker.tick_controls` starts every control `brain.ops.schedule_runner.due_now` finds
owed, and until this module nothing outside the process could change that. The Live runs screen
said so: no run can be stopped, and nothing here pretends otherwise. What can be real is the two
controls a scheduler honours before a run exists, which are whether it starts one at all and
whether it starts one early. This is both, as rows a person writes and a rule the tick applies.

**A pause is a switch in `ops.setting`, `schedule.paused.<control>`, and the tick reads it at its
own instant.** A paused control is not started by the schedule, is not recorded, and goes on
being owed, so its lateness keeps growing on the Live runs screen exactly as a broken control's
does. That is deliberate: `brain.tables.schedule` argues in
`A_CONTROL_THAT_FAILS_EVERY_RUN_LOOKS_LIKE_ONE_THAT_RUNS` against a control that looks healthy
while it is not doing its job, and a paused control is not doing its job. See
`A_PAUSED_CONTROL_IS_LATE_AND_SAYS_WHY`.

**A run asked for is an instant, `schedule.run_requested.<control>`, and not a message somebody
has to consume.** The tick starts a control whose newest attempt is older than the instant a
person asked, and once an attempt has started the request is satisfied by the run record itself:
nothing is taken, marked or deleted, a second press only moves the instant, and two replicas
ticking together are kept apart by the advisory lock the schedule already takes. A queue of
requests would need a consumer, and a consumer that dies between taking a request and starting
the run loses it silently. See `A_RUN_ASKED_FOR_IS_A_DUE_TIME_AND_NOT_A_MESSAGE`.

**Asked-for runs go through `start_owed`, which is the run.** The same lock, the same row in
`ops.control_run`, the same report-only rule for a destructive control that nobody has released.
That is `brain.ops.worker.A_QUEUED_CONTROL_IS_THE_SCHEDULED_RUN_BY_ANOTHER_DOOR` from a third
door, and it is why the console does not enqueue: the application has no connection to the
queue, whose tables are refused to it (see `THE_QUEUE_IS_NOT_THE_APPLICATIONS_TO_READ` in
`brain.operate_routes`), and a run the tick starts is recorded exactly where a queued one is.

**A run asked for is started even while the control is paused.** A pause stops the schedule,
and a person pressing run now on a paused control has made a decision about one run, which the
screen says in the confirmation. Refusing it would make "pause, run once to see, resume" three
screens and a shell.

**Only a control the worker ticks and can start may be paused or asked for.** A control started
from outside the process is not the schedule's to pause, and a control with no runner is never
started by the tick; a pause on either would be a switch that reaches nothing. `control_refusal`
says which, in the runner's own sentence about what it still needs.

Scope: the rule and the rows. The routes are `brain.jobs_routes`; the tick is `brain.ops.worker`.

Task ids: M27.8.13
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from brain.ops.controls import Control
from brain.ops.schedule import Owed, report_only_now, schedulable
from brain.ops.schedule_runner import RUNNERS, Runner
from brain.ops.setting_store import SettingState, put, read_namespace, values_under
from brain.tables.config import SettingType

# ------------------------------------------------------------------ written-down reasons
#: Why a paused control is still reported owed and late.
A_PAUSED_CONTROL_IS_LATE_AND_SAYS_WHY: Final = (
    "A control exists because something stops being true when it does not run. Pausing it "
    "stops the runs and not the consequence, so the schedule goes on counting it owed and its "
    "lateness goes on growing, and the screen says it is paused beside the lateness. A pause "
    "that also silenced the lateness would be a way to make a broken guarantee look kept."
)

#: Why a request to run is stored as an instant.
A_RUN_ASKED_FOR_IS_A_DUE_TIME_AND_NOT_A_MESSAGE: Final = (
    "The tick already decides from two instants, the last attempt and the last success. A run "
    "asked for is a third: start this control if nothing has started since. The run record "
    "answers whether it happened, so nothing has to consume the request, a worker that dies "
    "mid-tick loses nothing, and pressing twice asks for one run rather than two."
)

# ------------------------------------------------------------------------ the figures
#: `schedule.paused.<control>`, a boolean.
PAUSE_NAMESPACE: Final = "schedule.paused"

#: `schedule.run_requested.<control>`, an ISO 8601 instant with its offset.
RUN_NAMESPACE: Final = "schedule.run_requested"

#: What a pause row says about itself in `ops.setting.description`.
PAUSE_DESCRIPTION: Final = "Whether the worker's schedule starts this control"

#: What a run request row says about itself.
RUN_DESCRIPTION: Final = "When a person last asked for this control to run now"


class ScheduleControlError(Exception):
    """Raised for a control that cannot be paused or asked for, with the reason."""


@dataclass(frozen=True)
class Chosen:
    """One control this tick will try to start, and why.

    `asked` is true for a run a person asked for, whether or not the schedule also owed it, so a
    reader of the tick can tell a pressed button from a cadence.
    """

    name: str
    report_only: bool
    asked: bool


def control_refusal(
    name: str,
    *,
    controls: Sequence[Control] | None = None,
    runners: Sequence[Runner] = RUNNERS,
) -> str:
    """Why this control cannot be paused or run from the console, or empty when it can.

    A name the worker does not tick, and a control with nothing to run, each in words a person
    can act on. The runner's `needs` is its own sentence, so the refusal says what the product
    still lacks rather than that something went wrong.
    """
    if name not in {one.name for one in schedulable(controls)}:
        return f"{name} is not started by the worker's schedule, so there is nothing here to pause"
    for runner in runners:
        if runner.name == name:
            if runner.run is None:
                return f"{name} has nothing to run yet: it needs {runner.needs}"
            return ""
    return f"{name} has no runner, so the worker never starts it"


def paused_in(states: Mapping[str, SettingState]) -> frozenset[str]:
    """The controls whose pause row, keyed by control name, holds the JSON `true`.

    `is True` rather than truthiness, for `brain.ops.features.switched_on_in`'s reason: a person
    at a prompt can write the string `"false"`, which is truthy.
    """
    return frozenset(
        name
        for name, state in states.items()
        if state.value_type == SettingType.BOOLEAN.value and state.value is True
    )


def requested_at(state: SettingState) -> datetime | None:
    """The instant one run request row holds, or None when it holds no readable, zoned instant.

    A row a person wrote by hand that does not parse, or parses to a naive instant, is not a
    request: a naive instant compared against the tick's is wrong by the host's offset, and a
    request that fires hours early or late is worse than one that does not fire.
    """
    if state.value_type != SettingType.STRING.value or not isinstance(state.value, str):
        return None
    try:
        at = datetime.fromisoformat(state.value)
    except ValueError:
        return None
    return at if at.tzinfo is not None else None


def requested_in(states: Mapping[str, SettingState]) -> dict[str, datetime]:
    """When each control was last asked to run, keyed by control name, for readable rows only.

    See `requested_at` for what is not a request.
    """
    found: dict[str, datetime] = {}
    for name, state in states.items():
        at = requested_at(state)
        if at is not None:
            found[name] = at
    return found


def chosen_this_tick(
    owed: Sequence[Owed],
    *,
    now: datetime,
    paused: Collection[str],
    requested: Mapping[str, datetime],
    last_attempt: Mapping[str, datetime],
    released: Collection[str] = (),
    controls: Sequence[Control] | None = None,
) -> tuple[Chosen, ...]:
    """What the tick starts: the owed controls nobody paused, and every run asked for since the
    control last started, in registry order.

    A request is live when it is not in the future and nothing has started at or after it. The
    comparison is strict on the attempt, so a run started at the very instant of the request
    counts as having answered it. See `A_RUN_ASKED_FOR_IS_A_DUE_TIME_AND_NOT_A_MESSAGE`.

    The report-only rule is `brain.ops.schedule.report_only_now` for an asked-for run that the
    schedule did not also owe, which is the rule `owed` applies, so a pressed button cannot run
    a destructive control that nobody released.
    """
    owed_by_name = {one.name: one for one in owed}
    reporting = set(report_only_now(released))
    order = [one.name for one in schedulable(controls)]
    found: list[Chosen] = []
    for name in order:
        at = requested.get(name)
        asked = (
            at is not None and at <= now and not (name in last_attempt and last_attempt[name] >= at)
        )
        if name in owed_by_name and (asked or name not in paused):
            found.append(Chosen(name, owed_by_name[name].report_only, asked))
        elif asked:
            found.append(Chosen(name, name in reporting, True))
    return tuple(found)


# ------------------------------------------------------------------------ the rows
async def pause_states(session: AsyncSession) -> dict[str, SettingState]:
    """Every live pause row, by control name, paused or resumed."""
    return values_under(await read_namespace(session, PAUSE_NAMESPACE), PAUSE_NAMESPACE)


async def request_states(session: AsyncSession) -> dict[str, SettingState]:
    """Every live run request row, by control name."""
    return values_under(await read_namespace(session, RUN_NAMESPACE), RUN_NAMESPACE)


async def paused_controls(session: AsyncSession) -> frozenset[str]:
    """The controls paused now, for the tick."""
    return paused_in(await pause_states(session))


async def run_requests(session: AsyncSession) -> dict[str, datetime]:
    """When each control was last asked to run, for the tick."""
    return requested_in(await request_states(session))


def _refuse_unless_controllable(name: str) -> None:
    refusal = control_refusal(name)
    if refusal:
        raise ScheduleControlError(refusal)


async def set_paused(session: AsyncSession, name: str, *, paused: bool, by: str) -> None:
    """Pause or resume one control in the caller's transaction.

    Resuming writes `false` rather than retiring the row, so the row says who resumed it.
    """
    _refuse_unless_controllable(name)
    await put(
        session,
        f"{PAUSE_NAMESPACE}.{name}",
        value_type=SettingType.BOOLEAN,
        value=paused,
        description=PAUSE_DESCRIPTION,
        updated_by=by,
    )


async def request_run(session: AsyncSession, name: str, *, at: datetime, by: str) -> None:
    """Ask for one run of this control at or after `at`, in the caller's transaction."""
    _refuse_unless_controllable(name)
    if at.tzinfo is None:
        msg = "a run asked for at a naive instant would fire early or late by the host's offset"
        raise ScheduleControlError(msg)
    await put(
        session,
        f"{RUN_NAMESPACE}.{name}",
        value_type=SettingType.STRING,
        value=at.isoformat(),
        description=RUN_DESCRIPTION,
        updated_by=by,
    )
