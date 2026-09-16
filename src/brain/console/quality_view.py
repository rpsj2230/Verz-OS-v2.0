"""Quality and canaries, as one reader may be shown them: when the canaries last ran, and no more.

`docs/screens.html` draws the permission canaries as a card: how many synthetic users are under
test, how many assertions a run makes, when the last run was and whether it was green, and what
happens on a red one. The overview repeats it as "Permission canaries green". Measured on
2026-09-16, an install can support one line of that card. `brain.ops.canaries` holds the checks
and runs nothing; the corpus and the planted canary values live in `tests/fixtures`, which
`.dockerignore` keeps out of the image because shipping the suite would ship the canaries; the
scheduled production run is `brain.ops.controls`' `canary_run`, which nothing starts, because
`brain.ops.schedule_runner.RUNNERS` says what it still needs. What an install does record is
`ops.control_run`, one row per attempt to run a control, kept. That is where the last canary run
is read from, and this module decides who may see it.

**A finished run is not a green one, and the screen must not say it is.** The attempt table's
`ok` means the control returned rather than raised, and nothing records what a canary run found:
`brain.ops.canaries.alert_lines` returns lines and no store keeps them. Translating `ok` into
"passed" would put a green light on the screen somebody reads before deciding not to worry, on
the strength of a run that might have found a leak and returned normally to say so. So a run is
`finished`, `failed`, `declined` or `unfinished`, in the attempt table's own terms, and the page
says in words that a finished run is not a passing one. See `A_FINISHED_RUN_IS_NOT_A_GREEN_ONE`.

**A canary run is the whole install's, and a red one is a way in.** It has no department's
version: a canary asks whether the gate refuses what it should across every department at once.
And unlike a release number it is not harmless whole, because a failing run says the gate is
leaking now, which is worth most to exactly the person who should not have it. So a run offers
a grant's scope `RUN_ROW`, which holds no field, and `brain.core.scope.Clause.matches` refuses a
field a row does not have: an unrestricted `read:evaluation` grant matches it and a
department-scoped one matches nothing. That is `brain.console.service_level_view.READING_ROW`'s
shape for a different reason. See `A_CANARY_RUN_IS_THE_WHOLE_INSTALLS_AND_A_RED_ONE_IS_A_WAY_IN`.

**A reader who may not see a run is answered as an install where none is recorded.** No field
says a run was withheld, and whether anything starts the canaries and how often they would run
are carried to everybody, because both are facts about the product's code rather than about this
install's gate. See `A_WITHHELD_RUN_AND_A_RUN_NEVER_MADE_ARE_ONE_OBJECT`.

**No finding reaches this screen, and none could.** `brain.ops.canaries.CanaryFinding.subject`
names a field, and `brain.console.operate.findings_in_reach` is the decision about who may be
shown one. Nothing stores a finding, so there is nothing for that decision to filter, and this
module has no field one could arrive in. The day findings are recorded, they are shown through
that function and not through a second one written here.

What is not built, and why. The golden corpus's score, the synthetic users and the assertions per
run are the test suite's, which is not on an install. A regression since the last release needs a
recorded evaluation run to compare with, and nothing records one; `brain.ops.evaluation` says why
M28.1.4 is not claimed. So M27.7.19 is claimed here for the line the screen can show and is not
closed by it.

Scope: domain logic. Nothing here opens a connection, reads a clock or renders anything.

Task ids: M27.7.19
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final

from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.ops.canaries import CANARY_INTERVAL_SECONDS
from brain.ops.controls import CONTROLS, Control
from brain.tables.schedule import OUTCOMES


class QualityViewError(Exception):
    """Raised when a run record says something the attempt table never writes."""


# ------------------------------------------------------------------ written-down reasons
#: Why `ok` is not rendered as a pass.
A_FINISHED_RUN_IS_NOT_A_GREEN_ONE: Final = (
    "The attempt table records that a control returned, not what it found, and nothing stores "
    "a canary finding. A run that found a leak and returned to report it is ok in that table. "
    "Calling it passed would put a green light on the screen that is read before deciding not "
    "to worry, so the screen says finished and says that finished is not passed."
)

#: Why only a whole-install evaluation grant sees a run.
A_CANARY_RUN_IS_THE_WHOLE_INSTALLS_AND_A_RED_ONE_IS_A_WAY_IN: Final = (
    "A canary run checks the gate across every department at once, so it has no department's "
    "version to narrow to. A failed run says the gate may be leaking now, which is worth most "
    "to the reader who should not have it. So a run offers a grant's scope no field: an "
    "unrestricted grant matches it and a department-scoped grant matches nothing."
)

#: Why a withheld run is not visible as one.
A_WITHHELD_RUN_AND_A_RUN_NEVER_MADE_ARE_ONE_OBJECT: Final = (
    "A reader who may not see the last canary run is answered with no run, which is exactly "
    "what an install that has never run the canaries answers. Nothing on the response says a "
    "run was withheld, and the facts carried to everybody are the product's: whether anything "
    "starts the canaries, and how often they are due."
)

#: Why the golden corpus is not scored on this screen.
THE_GOLDEN_CORPUS_IS_THE_TEST_SUITES_AND_IS_NOT_ON_AN_INSTALL: Final = (
    "The golden questions and the planted canary values live in the test suite, which is kept "
    "out of the image because shipping it would ship the canaries. An install has no corpus to "
    "score and no record of a score, so the screen says so rather than drawing an empty one."
)

#: The screen this module is the reader decision for.
SCREEN_KEY: Final = "quality"

#: The capability the screen is read behind, read off the registry rather than written here.
EVALUATION_AUTHORITY: Final[Capability] = screen(SCREEN_KEY).read.requires

#: The control whose attempts are the canary runs, by its name in `brain.ops.controls`.
CANARY_CONTROL: Final = "canary_run"

#: The fields a run offers a grant's scope: none. See
#: `A_CANARY_RUN_IS_THE_WHOLE_INSTALLS_AND_A_RED_ONE_IS_A_WAY_IN`.
RUN_ROW: Final[Mapping[str, str]] = MappingProxyType({})

#: Whether anything records what a canary run found. Nothing does.
FINDINGS_ARE_RECORDED: Final = False

#: Whether an install holds a golden corpus score or an evaluation run to compare against. No.
EVALUATION_RUNS_ARE_RECORDED: Final = False


# --------------------------------------------------------------------------- the runs
class RunState(enum.StrEnum):
    """How one attempt to run the canaries ended, in the attempt table's own terms.

    Deliberately not passed and failed. See `A_FINISHED_RUN_IS_NOT_A_GREEN_ONE`.
    """

    #: The run returned. What it found is not recorded.
    FINISHED = "finished"
    #: The run raised.
    FAILED = "failed"
    #: The run was reached in report-only mode and did not act.
    DECLINED = "declined"
    #: A start is recorded and no finish: the process died, or the run is still going.
    UNFINISHED = "unfinished"


#: Each finished outcome `brain.tables.schedule.OUTCOMES` allows, and the state it is shown as.
STATE_OF_OUTCOME: Final[Mapping[str, RunState]] = MappingProxyType(
    {"ok": RunState.FINISHED, "failed": RunState.FAILED, "refused": RunState.DECLINED}
)


@dataclass(frozen=True)
class CanaryRun:
    """One attempt to run the canaries: when it started, when it ended, and how."""

    started_at: datetime
    finished_at: datetime | None
    state: RunState


def canary_run_of(
    *, started_at: datetime, finished_at: datetime | None, outcome: str | None
) -> CanaryRun:
    """The run one `ops.control_run` row describes, refusing a row the table never writes.

    `brain.ops.schedule_store.record_finish` writes the finish and the outcome together, so a
    row holding one without the other was not written by it, and a naive instant would be shown
    as a time it was not. Both are refused rather than rendered.
    """
    if started_at.tzinfo is None or (finished_at is not None and finished_at.tzinfo is None):
        msg = "a naive instant on a canary run is shown at the server's offset, not the run's"
        raise QualityViewError(msg)
    if (finished_at is None) != (outcome is None):
        msg = (
            f"a canary run finished at {finished_at} with outcome {outcome!r} is a row the "
            "attempt table never writes, since a finish and its outcome are recorded together"
        )
        raise QualityViewError(msg)
    if outcome is None:
        return CanaryRun(started_at=started_at, finished_at=None, state=RunState.UNFINISHED)
    state = STATE_OF_OUTCOME.get(outcome)
    if state is None:
        msg = f"{outcome!r} is not an outcome the attempt table knows, so no state is shown for it"
        raise QualityViewError(msg)
    return CanaryRun(started_at=started_at, finished_at=finished_at, state=state)


# ---------------------------------------------------------------------------- the screen
@dataclass(frozen=True)
class QualityScreen:
    """What the quality screen may say to one reader.

    `last_canary_run` is None both when no run is recorded and when this reader may not see
    one, and nothing here tells the two apart. See
    `A_WITHHELD_RUN_AND_A_RUN_NEVER_MADE_ARE_ONE_OBJECT`.
    """

    last_canary_run: CanaryRun | None
    #: Whether anything on an install starts the canary control.
    canaries_started: bool
    #: How often the canaries are due, from the canaries module's own figure.
    canary_interval_seconds: int


def may_read_canary_runs(entitlement: EntitlementSet, *, now: datetime) -> bool:
    """Whether this reader's evaluation grant admits the whole install, which is all a run is.

    `scope_for` then `Scope.matches` against a row with no fields. See
    `A_CANARY_RUN_IS_THE_WHOLE_INSTALLS_AND_A_RED_ONE_IS_A_WAY_IN`.
    """
    scope = entitlement.scope_for(EVALUATION_AUTHORITY, now)
    if scope is None:
        return False
    return scope.matches(dict(RUN_ROW))


def quality_for_reader(
    last: CanaryRun | None,
    entitlement: EntitlementSet,
    *,
    now: datetime,
    started: bool,
) -> QualityScreen:
    """The quality screen for one reader (M27.7.19, the canary run half).

    `last` is the newest recorded attempt, read before this is called whoever is asking, and
    `started` is whether the scheduler has a runner for the canary control.
    """
    return QualityScreen(
        last_canary_run=last if may_read_canary_runs(entitlement, now=now) else None,
        canaries_started=started,
        canary_interval_seconds=CANARY_INTERVAL_SECONDS,
    )


# ------------------------------------------------------------------------------ the gaps
def quality_gaps(
    controls: Sequence[Control] = CONTROLS,
    outcomes: Iterable[str] = OUTCOMES,
    states: Mapping[str, RunState] = STATE_OF_OUTCOME,
) -> tuple[str, ...]:
    """Everything that would make this screen show a run it does not understand.

    Three checks: the control the runs are read under is the registry's canary control, every
    outcome the attempt table allows has a state here, and the cadence this screen quotes is the
    one the registry schedules.
    """
    gaps: list[str] = []
    canary = next((one for one in controls if one.name == CANARY_CONTROL), None)
    if canary is None:
        gaps.append(
            f"{CANARY_CONTROL} is not a control in the registry, so the runs this screen reads "
            "are nobody's and the canaries' own runs are read by nothing"
        )
    elif canary.every != timedelta(seconds=CANARY_INTERVAL_SECONDS):
        gaps.append(
            f"the registry schedules {CANARY_CONTROL} every {canary.every} and this screen says "
            f"the canaries are due every {CANARY_INTERVAL_SECONDS} seconds"
        )
    for outcome in outcomes:
        if outcome not in states:
            gaps.append(
                f"the attempt table can record {outcome!r} and this screen has no state for it, "
                "so a run ending that way is refused on the screen rather than shown"
            )
    return tuple(gaps)
