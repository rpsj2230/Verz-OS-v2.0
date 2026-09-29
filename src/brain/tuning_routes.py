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

Task ids: M22.4.1, M22.1.2
"""

from __future__ import annotations

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
    KNOBS,
    Knob,
    hold,
    is_saved,
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


def tuning_view(*, may_change: bool) -> TuningView:
    return TuningView(
        knobs=[knob_view(one) for one in KNOBS],
        may_change=may_change,
        in_force=A_TUNED_VALUE_REACHES_EVERY_PROCESS_WITHIN_A_MINUTE,
    )


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def _not_answerable() -> Absent:
    """The one refusal a caller without the authority gets. Names the screen and nothing else."""
    return Absent(f"the {TUNING_SCREEN} screen's changes are not answerable for this caller")


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
    if not may_configure(asked.reach, asked.now):
        log.info("limit change refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    said = problem(name, body.value)
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
    page = tuning_view(may_change=True)
    return JSONResponse(status_code=200, content=page.model_dump(mode="json"))
