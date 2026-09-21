"""An agent's model: its tier by default, and a provider and model an administrator pins for it.

M5.7.3: "an agent uses a model level by default, and an administrator may pin a specific provider
and model for it, tried first with the level's fallback behind it." The tier was already on the
agent and handed to routing by `brain.gate.model_lane`; this is the pin, written to
`agent.agent.model_pin_provider` and `model_pin_model` (`0097`) and read back by
`brain.agent_routes.record_of` into `AgentRecord.model_pin`, which the executor walks first
(`brain.models.calls`).

**The pin must name a model a rung on the ladder serves**, in any tier. A pin is a choice among
the models the ladder can call, not a way to reach one it cannot: the executor would pass over a
pin with no rung anyway, and refusing it here is what tells the administrator so rather than an
agent that quietly answers from its tier. A pin that later loses its rung is passed over, and the
Settings tab shows the pin as stored.

**Pinning is the matrix write held over everything**, as switching a provider is: it decides
which provider every question to this agent goes to first, whoever asks it.

Task ids: M5.7.3
"""

from __future__ import annotations

from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.attribution import attribute
from brain.core.errors import Absent, Failed
from brain.credential_routes import CredentialProblemsView, CredentialProblemView
from brain.models.registry import MODEL_NAME_PATTERN, ModelPin, RegistryError
from brain.provider_routes import _sessions, may_switch, models_of
from brain.tables.agent import AgentRow

log = structlog.get_logger()

#: Why a pin must name a rung the ladder has.
A_PIN_CHOOSES_AMONG_THE_LADDERS_MODELS: Final = (
    "The executor tries a pinned model through the rung that serves it, and passes over a pin no "
    "rung serves. Accepting such a pin would tell the administrator it took effect while every "
    "question went to the tier, so a pin naming no rung is refused with the reason."
)


class PinAsked(BaseModel):
    """A provider and model to pin, or both null to go back to the tier alone."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Annotated[str, Field(min_length=2, max_length=60)] | None
    model: Annotated[str, Field(min_length=1, max_length=120, pattern=MODEL_NAME_PATTERN)] | None


class PinView(BaseModel):
    """The agent's pin as stored, or nulls for the tier alone."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    provider: str | None
    model: str | None


def _refused(message: str) -> JSONResponse:
    told = CredentialProblemsView(
        problems=(CredentialProblemView(field="model_pin", code="refused", message=message),)
    )
    return JSONResponse(status_code=422, content=told.model_dump(mode="json"))


def _not_answerable() -> Absent:
    return Absent("this agent's model is not answerable for this caller")


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.put("/agents/{agent_id}/model-pin", response_model=PinView, responses=COMMON_RESPONSES)
async def pin_model(
    request: Request, agent_id: str, body: PinAsked, asked: Asked
) -> JSONResponse | PinView:
    """Pin a provider and model for an agent, or clear the pin. See the module docstring."""
    if not may_switch(asked.reach, asked.now):
        log.info("agent model pin refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    if (body.provider is None) != (body.model is None):
        return _refused("a pin is a provider and a model together, or neither")
    pin: ModelPin | None = None
    if body.provider is not None and body.model is not None:
        try:
            pin = ModelPin(provider=body.provider, model=body.model)
        except RegistryError as refused:
            return _refused(str(refused))
        plan = await models_of(request).calls.planned()
        served = {(one.provider, one.model) for one in plan.state.rungs}
        if (pin.provider, pin.model) not in served:
            return _refused(
                "no rung on the routing ladder serves this provider and model; add one on the "
                "Routing screen first"
            )
    factory = _sessions(request)
    if factory is None:
        raise Failed("no database on this process")
    async with factory() as session:
        # Attributed, because `agent.agent` carries a ledgering trigger since `0105`.
        await attribute(session, asked)
        found = (
            await session.execute(
                update(AgentRow)
                .where(AgentRow.id == agent_id)
                .values(
                    model_pin_provider=None if pin is None else pin.provider,
                    model_pin_model=None if pin is None else pin.model,
                )
                .returning(AgentRow.id)
            )
        ).scalar_one_or_none()
        if found is None:
            await session.rollback()
            raise _not_answerable()
        await session.commit()
    log.info(
        "agent model pinned",
        agent=agent_id,
        pinned=pin is not None,
        principal=asked.caller.principal.id,
    )
    return PinView(
        agent_id=agent_id,
        provider=None if pin is None else pin.provider,
        model=None if pin is None else pin.model,
    )
