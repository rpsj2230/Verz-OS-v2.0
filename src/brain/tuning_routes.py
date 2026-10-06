"""The Rate limits screen's changes over HTTP: every budget and window a person may set, and a set.

`brain.ops.tuning` decides what may be set, between which bounds, and what is in force; this is the
read of those knobs and the one write. It is a module of its own rather than two routes in
`brain.install_routes`, because that module's docstring rejects a write anywhere in it, and the
argument there (a screen's read deciding a write from the side that renders) is the reason the two
are kept apart here too.

**The read is the Rate limits screen's, and the write is `admin:install_setting` over everything.**
Anybody who may open the screen sees what is in force and between which bounds, as they already
see the windows; `may_change` says whether they may set one, so the console draws the control only
for somebody the write would admit, and the write asks again whatever the console drew. A budget or
a request window is the whole install's, exactly as the company's name is, and there is no
department's version of either: the Rate limits screen is already withheld from a department
admin (`brain.console.screens.NOT_AT_DEPARTMENT_SCOPE`). So the question is
`brain.settings_routes.may_configure`, asked before anything is read, and a caller without it is
refused with the one sentence every caller without it gets. Rejected: a `write:rate_limit`
capability of its own, which would be a second way to change installation values beside the one
the Settings screen asks for, and a grant nobody on an existing install holds.

**A save is written to `ops.setting` inside the audit attribution, and held here at once.** The
value goes through `brain.ops.tuning.save`, refused outside the knob's bounds before it is written,
inside `brain.tables.audit.attributed_to`, so `0059`'s trigger appends the ledger entry naming who
changed which knob. After the commit the saved values are read back and held by this process, and
every other process holds them within a minute: see
`brain.ops.tuning.A_TUNED_VALUE_REACHES_EVERY_PROCESS_WITHIN_A_MINUTE`. The answer is the knobs as
they now are, so the screen draws the new figure from the response rather than a guess.

**The Learning screen's two figures are read and set here too, by the same write.** How long an
inferred memory lasts and how many conversations must agree before a learned rule is offered for
review are knobs of `KnobKind.LEARNING`, with the same authority for the same reason: a decay rate
is the whole install's, as a request window is. Each screen lists and sets its own kinds and
refuses a name of the other's with the sentence an unknown name gets, so a figure is changed from
the screen that explains it. The Learning screen's reading is answered to anybody who may open
that screen, and says in words how long an inference is recalled at the figure in force.

Task ids: M22.4.1, M22.1.2, M16.6.8
"""

from __future__ import annotations

from collections.abc import Set
from typing import Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictInt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody
from brain.api_routes import Asked
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.errors import Absent, Failed
from brain.ops.tuning import (
    A_TUNED_VALUE_REACHES_EVERY_PROCESS_WITHIN_A_MINUTE,
    KNOB_BY_NAME,
    KNOBS,
    LEARNING_KINDS,
    LIMIT_KINDS,
    NOT_A_KNOB,
    Knob,
    KnobKind,
    hold,
    is_saved,
    lifetime_sentence,
    load,
    problem,
    save,
    value,
)
from brain.routing_routes import sessions_of
from brain.settings_routes import may_configure
from brain.tables.audit import attributed_to

log = structlog.get_logger()

#: Where the knobs are read, and where one is set.
TUNING_PATH: Final = "/install/tuning"

#: The screen's name in a refusal. The console's own menu words, identical on every install.
TUNING_SCREEN: Final = "rate limits"

#: Where the Learning screen's figures are read, and where one is set.
LEARNING_SETTINGS_PATH: Final = "/govern/learning/settings"

#: The Learning screen's name, as `brain.console.screens` registers it and as a refusal says it.
LEARNING_SETTINGS_SCREEN: Final = "learning"


class KnobView(BaseModel):
    """One budget or window a person may set: what is in force, the default and the bounds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    kind: str
    label: str
    unit: str
    value: int
    default: int
    lowest: int
    highest: int
    #: Whether a saved value is what is in force, rather than the product's default.
    saved: bool
    bounds_because: str


class TuningView(BaseModel):
    """Every knob, whether this reader may set them, and when a change is in force, in words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    knobs: list[KnobView]
    may_change: bool
    in_force: str


class TuneAsked(BaseModel):
    """One value to save. A whole number: `StrictInt` refuses a string or a fraction here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: StrictInt


def knob_view(knob: Knob) -> KnobView:
    return KnobView(
        name=knob.name,
        kind=knob.kind.value,
        label=knob.label,
        unit=knob.unit,
        value=value(knob.name),
        default=knob.default,
        lowest=knob.lowest,
        highest=knob.highest,
        saved=is_saved(knob.name),
        bounds_because=knob.bounds_because,
    )


def tuning_view(*, may_change: bool, kinds: Set[KnobKind] = LIMIT_KINDS) -> TuningView:
    """The knobs of these kinds, in the product's order, and when a change is in force."""
    in_force = A_TUNED_VALUE_REACHES_EVERY_PROCESS_WITHIN_A_MINUTE
    if kinds == LEARNING_KINDS:
        in_force = f"{in_force} {lifetime_sentence()}"
    return TuningView(
        knobs=[knob_view(one) for one in KNOBS if one.kind in kinds],
        may_change=may_change,
        in_force=in_force,
    )


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def _not_answerable(named: str = TUNING_SCREEN) -> Absent:
    """The one refusal a caller without the authority gets. Names the screen and nothing else."""
    return Absent(f"the {named} screen's changes are not answerable for this caller")


def problem_on(name: str, amount: object, kinds: Set[KnobKind]) -> str:
    """`problem`'s sentence, and a name of another screen's knob refused as an unknown one is."""
    knob = KNOB_BY_NAME.get(name)
    if knob is None or knob.kind not in kinds:
        return NOT_A_KNOB
    return problem(name, amount)


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


router = APIRouter(prefix=API_PREFIX, tags=["install"])


@router.get(TUNING_PATH, response_model=TuningView, responses=COMMON_RESPONSES)
async def tuning(asked: Asked) -> TuningView:
    """Every budget and window a person may set, with what this process holds in force.

    Answered to a reader of the Rate limits screen or of the Settings screen, and refused
    identically to anybody else before anything is read.
    """
    may_change = may_configure(asked.reach, asked.now)
    if not may_change and not permitted(screen("limits").read, asked.reach, asked.now):
        raise _not_answerable()
    return tuning_view(may_change=may_change)


@router.put(f"{TUNING_PATH}/{{name}}", response_model=TuningView, responses=COMMON_RESPONSES)
async def tune(request: Request, name: str, body: TuneAsked, asked: Asked) -> JSONResponse:
    """Set one knob within its bounds, hold it for this process, and answer with every knob.

    The authority, then the name and value, then the write, in `brain.settings_routes.
    save_setting`'s order and for its reason: a caller without the authority is refused before
    the name is looked at, and a value outside the bounds is never written.
    """
    return await _set(request, name, body, asked, kinds=LIMIT_KINDS, named=TUNING_SCREEN)


@router.get(LEARNING_SETTINGS_PATH, response_model=TuningView, responses=COMMON_RESPONSES)
async def learning_settings(asked: Asked) -> TuningView:
    """The Learning screen's figures, with what this process holds in force and what it means.

    Answered to a reader of the Learning screen or holder of the Settings authority, and refused
    identically to anybody else before anything is read.
    """
    may_change = may_configure(asked.reach, asked.now)
    if not may_change and not permitted(
        screen(LEARNING_SETTINGS_SCREEN).read, asked.reach, asked.now
    ):
        raise _not_answerable(LEARNING_SETTINGS_SCREEN)
    return tuning_view(may_change=may_change, kinds=LEARNING_KINDS)


@router.put(
    f"{LEARNING_SETTINGS_PATH}/{{name}}", response_model=TuningView, responses=COMMON_RESPONSES
)
async def set_learning(request: Request, name: str, body: TuneAsked, asked: Asked) -> JSONResponse:
    """Set one of the Learning screen's figures within its bounds, as `tune` sets a limit."""
    return await _set(
        request, name, body, asked, kinds=LEARNING_KINDS, named=LEARNING_SETTINGS_SCREEN
    )


async def _set(
    request: Request,
    name: str,
    body: TuneAsked,
    asked: Asked,
    *,
    kinds: Set[KnobKind],
    named: str,
) -> JSONResponse:
    """One knob of these kinds saved, attributed and held, answered with the screen's knobs."""
    if not may_configure(asked.reach, asked.now):
        log.info("limit change refused", principal=asked.caller.principal.id)
        raise _not_answerable(named)
    said = problem_on(name, body.value, kinds)
    if said:
        told = ErrorBody(message=said, trace_id=_trace_id())
        return JSONResponse(status_code=422, content=told.model_dump())
    async with _require_sessions(request)() as session:
        for statement in attributed_to(
            actor_id=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
        ):
            await session.execute(statement)
        await save(session, name, body.value, updated_by=asked.caller.principal.id)
        saved = await load(session)
        await session.commit()
    hold(saved)
    log.info("limit changed", knob=name, principal=asked.caller.principal.id)
    page = tuning_view(may_change=True, kinds=kinds)
    return JSONResponse(status_code=200, content=page.model_dump(mode="json"))
