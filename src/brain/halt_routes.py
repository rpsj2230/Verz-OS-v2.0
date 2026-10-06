"""The Stop screen's three routes: what is stopped, stop, and resume.

`brain.ops.halt` decided what a halt is and `brain.ops.halt_store` reads and writes `ops.halt`.
Until this module no route reached either, so the Stop screen the registry declares could not be
opened and nobody could stop anything from the console. These are the routes it needs and
nothing more: everything they decide is decided in those two modules, so the console and the
install check ask the same functions.

**Stopping is one request, with nothing to confirm and no reason required.** A stop with no
reason is stored with `brain.ops.halt_store.STOPPED_FROM_THE_CONSOLE`, and who and when are on
the row. Resuming is refused without a written reason and answers in the sentence that says
whose stop it lifted. See `brain.ops.halt_store.A_STOP_NEEDS_NO_WORDS_AND_A_RESUME_DOES`.

**A reader who may not open the Stop screen is told it is not there.** The same 404 as an
address that does not exist, which is the rule that a refusal names nothing. A reader who may
open it and asks to stop something their grant does not reach gets the same 404: telling them
it exists and is not theirs would say which departments a scoped administrator is outside.

**What the screen lists is `brain.console.operate.stopped_for`**, which decides it, at this
reader's scope, with the axes nothing asks yet named beside it (M27.15.16), so an administrator
is never offered a stop that would stop nothing.

Task ids: M27.15.10, M27.15.15, M27.15.16, M27.15.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, bound_trace_id
from brain.api_routes import Asked
from brain.attribution import of_request
from brain.console.operate import stop_is_unknown, stopped_for
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.errors import Absent
from brain.ops.halt import ENFORCED_AXES, Halt, HaltScope, halt_gaps
from brain.ops.halt_store import HaltRefusedError, may_act, read_state, resume, stop
from brain.routing_routes import sessions_of

#: The addresses, under `API_PREFIX`. The console's query file names the same three.
HALTS_PATH: Final = "/halts"
RESUME_PATH: Final = "/halts/resume"

#: The registered screen these routes are.
HALT_SCREEN: Final = "halt"

#: The longest target a halt names, as `ops.halt` holds it.
TARGET_CHARS: Final = 128

#: The longest reason a person may type.
REASON_CHARS: Final = 2000

router = APIRouter(prefix=API_PREFIX, tags=["halt"])


class HaltView(BaseModel):
    """One halt in force, as an administrator who may see it reads it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: HaltScope
    target: str
    declared_by: str
    at: datetime
    reason: str


class HaltsView(BaseModel):
    """What is stopped that this reader may see, and what cannot be stopped yet.

    `known` false is the store that could not be read, which refuses all work, and is said in
    words on the screen rather than as an empty list. `not_asked_yet` is every axis nothing that
    starts work consults, so the screen does not offer it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    known: bool
    halts: list[HaltView]
    gaps: list[str]
    not_asked_yet: list[HaltScope]
    may_stop_everything: bool


class StopAsked(BaseModel):
    """A stop: what, and, if the person gives one, why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: HaltScope
    target: str = Field(default="", max_length=TARGET_CHARS)
    reason: str = Field(default="", max_length=REASON_CHARS)


class ResumeAsked(BaseModel):
    """A resume: what, and why, which is required."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: HaltScope
    target: str = Field(default="", max_length=TARGET_CHARS)
    reason: str = Field(max_length=REASON_CHARS)


class ResumedView(BaseModel):
    """What was lifted, in the sentence an administrator reads afterwards."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    said: str
    overrides_somebody_else: bool


_REFUSED: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    422: {"model": ErrorBody, "description": "Nothing was stopped or resumed, and why."},
}


def _view(one: Halt) -> HaltView:
    return HaltView(
        scope=one.scope,
        target=one.target,
        declared_by=one.declared_by,
        at=one.at,
        reason=one.reason,
    )


def _opened(asked: Asked) -> None:
    """The screen's own read, or the 404 every other refusal here is."""
    if not permitted(screen(HALT_SCREEN).read, asked.reach, asked.now):
        raise Absent("no such screen")


def _refused(request: Request, refused: HaltRefusedError) -> JSONResponse:
    body = ErrorBody(message=str(refused), trace_id=bound_trace_id(request))
    return JSONResponse(status_code=422, content=body.model_dump())


@router.get(HALTS_PATH, response_model=HaltsView, responses=COMMON_RESPONSES)
async def halts(request: Request, asked: Asked) -> HaltsView:
    """Everything stopped this reader may see, read fresh, and what cannot be stopped yet."""
    _opened(asked)
    state = await read_state(sessions_of(request))
    shown = stopped_for(state, asked.reach, asked.now)
    return HaltsView(
        known=not stop_is_unknown(state),
        halts=[_view(one) for one in shown],
        gaps=list(halt_gaps(shown)),
        not_asked_yet=[one for one in HaltScope if one not in ENFORCED_AXES],
        may_stop_everything=may_act(asked.reach, HaltScope.EVERYTHING, "", asked.now),
    )


@router.post(HALTS_PATH, status_code=201, response_model=HaltView, responses=_REFUSED)
async def stop_now(request: Request, asked: Asked, body: StopAsked) -> HaltView | JSONResponse:
    """Stop something at once. No confirmation, and no reason required."""
    _opened(asked)
    if not may_act(asked.reach, body.scope, body.target.strip(), asked.now):
        raise Absent("no such screen")
    sessions = sessions_of(request)
    if sessions is None:
        raise Absent("no such screen")
    try:
        halt = await stop(
            sessions,
            asked.reach,
            scope=body.scope,
            target=body.target,
            reason=body.reason,
            now=asked.now,
            attributed=of_request(asked),
        )
    except HaltRefusedError as refused:
        return _refused(request, refused)
    return _view(halt)


@router.post(RESUME_PATH, response_model=ResumedView, responses=_REFUSED)
async def resume_now(
    request: Request, asked: Asked, body: ResumeAsked
) -> ResumedView | JSONResponse:
    """Lift a halt, with a written reason, saying whose stop it lifts."""
    _opened(asked)
    if not may_act(asked.reach, body.scope, body.target.strip(), asked.now):
        raise Absent("no such screen")
    sessions = sessions_of(request)
    if sessions is None:
        raise Absent("no such screen")
    try:
        lifted = await resume(
            sessions,
            asked.reach,
            scope=body.scope,
            target=body.target,
            reason=body.reason,
            now=asked.now,
            attributed=of_request(asked),
        )
    except HaltRefusedError as refused:
        return _refused(request, refused)
    return ResumedView(
        said=lifted.render(), overrides_somebody_else=lifted.overrides_somebody_else()
    )
