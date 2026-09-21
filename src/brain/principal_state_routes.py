"""Disabling and enabling a person over HTTP, from the Departments and teams screen (M1.2.3).

`brain.identity.principal_state_store` sets and clears `auth.principal.disabled_at`, whose `0003`
cascade ends the person's sessions, and `brain.console.global_surfaces.may_disable` decides who may
press it. This module asks the second before the first and decides nothing itself.

**The authority is the grant decision, `approve:grant`, in a scope admitting the person's row.**
`global_surfaces.CONFIRMING_A_ROLE_AND_DISABLING_A_PRINCIPAL_ARE_BOTH_THE_GRANT_DECISION` argues
it: a disable takes every grant a person holds out of force at once. Asked cheaply first, so a
caller holding it nowhere is refused identically with a database and without, and properly under
the row's lock with the person's department.

**Nobody disables themselves.** `global_surfaces.disable_principal` refuses it for the reason that
it is the one act with no reviewer left afterwards; this refuses it the same way, with a 409 and a
sentence, because it is something the caller can understand and act on and it names nobody else.

**Every other refusal is the one 404**: somebody out of reach, retired, or never here.

Task ids: M1.2.3
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Final, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody
from brain.api_routes import Asked, Asking
from brain.console.global_surfaces import GOVERNANCE_CONTROL, may_disable
from brain.core.errors import Absent, Failed
from brain.identity.principal_state_store import (
    A_DISABLE_IS_REVERSIBLE_AND_A_LEAVER_IS_NOT,
    PrincipalState,
    StateChange,
    StoredPrincipalStates,
)
from brain.routing_routes import sessions_of

log = structlog.get_logger()

#: What refusing a self-disable says.
NOBODY_DISABLES_THEMSELVES: Final = (
    "You cannot disable yourself: it would end the session you are using and leave nobody to undo "
    "it. Ask another administrator."
)


class StateAsked(BaseModel):
    """Whose sign-in to disable or enable. An id, and nothing that could say who asked."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str = Field(min_length=1, max_length=128)


class StateView(BaseModel):
    """The person's state after the press, the database's instant, and what it means."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    disabled: bool
    disabled_at: datetime | None
    outcome: StateChange
    #: The database's instant for the change; absent when nothing changed.
    at: datetime | None = None
    told: str = A_DISABLE_IS_REVERSIBLE_AND_A_LEAVER_IS_NOT


@runtime_checkable
class PrincipalStateStore(Protocol):
    """What these routes need. `StoredPrincipalStates` implements it."""

    async def set_disabled(
        self,
        principal_id: str,
        *,
        disabled: bool,
        may: Callable[[str | None], bool],
        by: str,
        ent_hash: str,
        trace_id: str,
    ) -> PrincipalState | None: ...


def store_of(request: Request) -> PrincipalStateStore:
    """`app.state.principal_states` when something put one there, the database otherwise."""
    found = getattr(request.app.state, "principal_states", None)
    if isinstance(found, PrincipalStateStore):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredPrincipalStates(factory)


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def _not_here() -> Absent:
    return Absent("nobody is disableable here by this caller")


router = APIRouter(prefix=API_PREFIX, tags=["people"])


async def _press(
    request: Request, body: StateAsked, asked: Asking, *, disabled: bool
) -> JSONResponse:
    if asked.reach.scope_for(GOVERNANCE_CONTROL, asked.now) is None:
        log.info("principal state refused", principal=asked.caller.principal_id)
        raise _not_here()
    if body.principal_id == asked.caller.principal_id:
        refusal = ErrorBody(message=NOBODY_DISABLES_THEMSELVES, trace_id=_trace_id())
        return JSONResponse(status_code=409, content=refusal.model_dump(mode="json"))
    reach, now = asked.reach, asked.now

    def may(department: str | None) -> bool:
        where = {} if department is None else {"department": department}
        return may_disable(reach, where, now)

    state = await store_of(request).set_disabled(
        body.principal_id,
        disabled=disabled,
        may=may,
        by=asked.caller.principal_id,
        ent_hash=reach.ent_hash(),
        trace_id=_trace_id(),
    )
    if state is None:
        raise _not_here()
    view = StateView(
        principal_id=state.principal_id,
        disabled=state.disabled_at is not None,
        disabled_at=state.disabled_at,
        outcome=state.outcome,
        at=state.at,
    )
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))


@router.post("/govern/people/disable", response_model=StateView, responses=COMMON_RESPONSES)
async def disable_person(request: Request, body: StateAsked, asked: Asked) -> JSONResponse:
    """Disable one person's sign-in: their sessions end now and their grants stop counting."""
    return await _press(request, body, asked, disabled=True)


@router.post("/govern/people/enable", response_model=StateView, responses=COMMON_RESPONSES)
async def enable_person(request: Request, body: StateAsked, asked: Asked) -> JSONResponse:
    """Enable a disabled person again: their grants count again and they may sign in."""
    return await _press(request, body, asked, disabled=False)


#: The two addresses, for the console and the tests.
DISABLE_PATH: Final = f"{API_PREFIX}/govern/people/disable"
ENABLE_PATH: Final = f"{API_PREFIX}/govern/people/enable"
