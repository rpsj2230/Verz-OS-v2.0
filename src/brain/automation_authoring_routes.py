"""New automation over HTTP: what a person may choose, the preview they confirm, and the write.

`brain.console.automation_authoring` decides every question these three routes ask and this module
adds no rule of its own. It orders the questions, reaches for a store only once the cheap ones are
answered, and turns the answers into the shapes the console's Automations tab reads. It follows
`brain.automation_gallery_routes` in everything it can, because the two write the same row.

**The order is the design, as it is there.** Every route first asks the question that needs nothing
but the switch and the caller's reach: is New automation on, may this reader open the Automations
tab, and may they write an automation onto this agent as themselves. Each answer that is no is the
one 404, and only then is the agent read, so a caller who may not author learns nothing about which
agents exist by trying. A switch that is off is the same 404 for the preview and the write, and the
options route says `enabled: false` with nothing else, because the console has to know whether to
draw the button and that fact is not a secret.

**The options are the install's, narrowed to this agent.** The fields a condition may name are the
projected fields of the connectors this agent is bound to and that are serving, so a field the agent
could never read is not offered. The tools are exactly the agent's own allowed list. The templates
are the product's. Nothing here is a count of anything the reader may not see.

**Two refusals are not 404s and both write nothing.** What a person wrote may be unfit, and that
is a 422 carrying every finding in words, because a form is edited and not debugged. A confirmation
that does not match what would be written now is a 409 saying to look again, which only a caller
who holds the authority and can see the agent can reach.

**The preview carries the rehearsal and the write does not recompute it.** The rehearsal changes
with the clock and is not a term, so it is shown with the preview and left out of the digest; see
`brain.console.automation_authoring`.

Task ids: M39.9.2.1, M39.9.2.2, M39.9.2.3, M39.9.2.4, M17.4.1, M17.4.2
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Final, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_lifecycle_routes import connectors_of
from brain.agent_routes import viewer_of
from brain.agents.model import AgentRecord, visible_agent_ids
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.automation_gallery_routes import CONFIRMATION, agent_records_of
from brain.console.automation_authoring import (
    A_REHEARSAL_WRITES_AND_SENDS_NOTHING,
    AUTHORED_TASK,
    DAY_OPS,
    FIELD_KEY,
    IT_STARTS_PAUSED,
    MAXIMUM_INSTRUCTION,
    MAXIMUM_TOOLS,
    NOTHING_FIRES_THIS_YET,
    WRITES_WAIT_FOR_A_PERSON,
    Authored,
    Authoring,
    AuthoringPreview,
    AuthoringRefusedError,
    Condition,
    ConditionField,
    ConditionOp,
    TriggerChoice,
    authoring_of,
    compose,
    default_cadence,
    may_author,
    preview,
    rehearse,
    template_for,
)
from brain.console.automation_gallery import (
    BUILT_IN,
    TEMPLATE_ID,
    Cadence,
    Every,
    GalleryError,
    NotConfirmedError,
    may_open_gallery,
    new_automation_id,
)
from brain.core.errors import Absent, Failed
from brain.ops.agent_automation_store import StoredAgentAutomations
from brain.ops.features import AUTOMATION_AUTHORING, is_on
from brain.orchestration.unattended import TriggerKind
from brain.routing_routes import sessions_of

log = structlog.get_logger()

#: The addresses, under `API_PREFIX`. The console's query file names the same three.
OPTIONS_PATH: Final = "/agents/{agent_id}/automation-authoring"
PREVIEW_PATH: Final = "/agents/{agent_id}/automation-authoring/preview"
CREATE_PATH: Final = "/agents/{agent_id}/automations/authored"

#: What a refused confirmation says. A sentence a person can act on, naming nothing else.
LOOK_AGAIN: Final = (
    "What you confirmed is not what would be written now: your access, this agent's ceiling or "
    "what you wrote has changed since you looked. Nothing was written. Look again and confirm."
)

#: What each trigger kind is called on the form.
TRIGGER_LABELS: Final[Mapping[TriggerKind, str]] = {
    TriggerKind.SCHEDULE: "On a schedule",
    TriggerKind.CONNECTOR_EVENT: "When something changes in a connected source",
    TriggerKind.WEBHOOK: "When another system calls it",
}

#: What each comparison is called on the form.
OP_LABELS: Final[Mapping[ConditionOp, str]] = {
    ConditionOp.EQUALS: "is",
    ConditionOp.IS_OVER: "is more than ... days ago",
    ConditionOp.IS_UNDER: "is less than ... days ago",
    ConditionOp.CONTAINS: "contains",
    ConditionOp.WITHIN_DAYS: "is within ... days of now",
}


# ------------------------------------------------------------------------ what is asked
class CadenceAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    every: Every
    hour_utc: int = Field(ge=0, le=23)
    #: Monday is nought. Required for a weekly cadence and refused for any other.
    weekday: int | None = Field(default=None, ge=0, le=6)


class TriggerAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: TriggerKind
    cadence: CadenceAsked | None = None
    #: The connector or the endpoint, for a kind that has one.
    source: str = Field(default="", max_length=63)


class ConditionAsked(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str = Field(min_length=5, max_length=190, pattern=FIELD_KEY)
    op: ConditionOp
    value: str = Field(min_length=1, max_length=200)


class AuthoringAsked(BaseModel):
    """What a person wrote. Nothing in it could say who it runs as, or what it may reach."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The template it starts from, or null to start from words.
    template_id: str | None = Field(default=None, min_length=3, max_length=64, pattern=TEMPLATE_ID)
    #: Blank means the template's, and is refused for words.
    name: str = Field(default="", max_length=200)
    instruction: str = Field(default="", max_length=MAXIMUM_INSTRUCTION + 400)
    guards: str = Field(default="", max_length=1000)
    trigger: TriggerAsked
    condition: ConditionAsked | None = None
    tools: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=MAXIMUM_TOOLS + 20
    )


class CreateAsked(AuthoringAsked):
    """What a person wrote, and the digest of what they were shown."""

    confirmation: str = Field(min_length=64, max_length=64, pattern=CONFIRMATION)


# ------------------------------------------------------------------------ what is answered
class TemplateOption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str
    name: str
    summary: str
    guards: str
    every: Every
    hour_utc: int
    weekday: int | None


class TriggerOption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: TriggerKind
    label: str
    #: Whether anything on this install fires this kind. Presentation only: the write decides.
    fires: bool


class OpOption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    op: ConditionOp
    label: str
    #: Whether the value is a number of days.
    in_days: bool


class FieldOption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    label: str
    shape: str
    ops: list[OpOption]


class AuthoringOptions(BaseModel):
    """Everything a form needs, and whether to draw it at all."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool
    templates: list[TemplateOption] = []
    triggers: list[TriggerOption] = []
    fields: list[FieldOption] = []
    #: The tools this agent's own ceiling allows, and so the only ones an automation may name.
    tools: list[str] = []
    #: The connectors an event trigger may listen to: those this agent is bound to that serve.
    connectors: list[str] = []
    starts_paused: str = IT_STARTS_PAUSED
    writes_wait: str = WRITES_WAIT_FOR_A_PERSON


class AuthoringRehearsalView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    at: datetime | None
    #: `holds`, `does_not_hold`, `cannot_tell`, or null when there is no condition.
    condition: str | None
    says: str


class AuthoringPreviewView(BaseModel):
    """Everything the person confirms, what it would have done, and the digest that confirms it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    from_template: str | None
    name: str
    instruction: str
    guards: str
    task: str
    trigger: str
    fires: bool
    #: Set when nothing fires this kind of trigger, in words.
    nothing_fires: str | None
    condition: str | None
    tools: list[str]
    runs_as: str
    runs_as_name: str
    reach: list[str]
    starts_paused: str = IT_STARTS_PAUSED
    writes_wait: str = WRITES_WAIT_FOR_A_PERSON
    rehearsal: list[AuthoringRehearsalView]
    rehearsal_rule: str = A_REHEARSAL_WRITES_AND_SENDS_NOTHING
    confirmation: str


class AuthoringWrittenView(BaseModel):
    """What was written."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    automation_id: str
    agent_id: str
    name: str
    runs_as: str
    next_run_at: datetime | None
    starts_paused: str = IT_STARTS_PAUSED


class AuthoringRefusedView(BaseModel):
    """Why what was written cannot be an automation: every reason, in words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: str
    sentences: list[str]


class AuthoringNotWrittenView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: str
    sentence: str


REFUSED: Final = "refused"
UNCONFIRMED: Final = "unconfirmed"

_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": AuthoringNotWrittenView, "description": "Nothing was written, and why."},
    422: {
        "model": AuthoringRefusedView,
        "description": "What was written cannot be an automation.",
    },
}


# ------------------------------------------------------------------------ the stores
@runtime_checkable
class AutomationAuthors(Protocol):
    """What these routes need of `agent.automation`. `StoredAgentAutomations` implements it."""

    async def author(self, authoring: Authoring, *, ent_hash: str, trace_id: str) -> str: ...


def _sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def authors_of(request: Request) -> AutomationAuthors:
    """`app.state.automation_authors` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "automation_authors", None)
    if isinstance(found, AutomationAuthors):
        return found
    return StoredAgentAutomations(_sessions(request))


async def authoring_is_on(request: Request) -> bool:
    """Whether New automation is switched on. Off on every install until somebody turns it on.

    `app.state.automation_authoring_on` wins when something put a boolean there, as every other
    store here does, so a test can say it without a database. Otherwise the switch is read.
    """
    found = getattr(request.app.state, "automation_authoring_on", None)
    if isinstance(found, bool):
        return found
    async with _sessions(request)() as session:
        return await is_on(session, AUTOMATION_AUTHORING)


# ------------------------------------------------------------------------ the refusals
def _not_here(reason: str, asked: Asking) -> Absent:
    """The one refusal these routes make about a thing. The reason reaches a log and no body."""
    log.info("automation authoring refused", reason=reason, principal=asked.caller.principal.id)
    return Absent("no new automation is answerable here for this caller")


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


async def _visible_agent(request: Request, agent_id: str, asked: Asking) -> AgentRecord:
    record = await agent_records_of(request).agent(agent_id)
    if record is None or agent_id not in visible_agent_ids((record,), viewer_of(asked)):
        raise _not_here("agent", asked)
    return record


async def _fields_of(request: Request, agent: AgentRecord) -> dict[str, ConditionField]:
    """The fields a condition on this agent may name: its serving connectors' projected fields.

    A connector this agent is not bound to is not offered, because the agent's ceiling would not
    let a run read it, and a field with no comparison its shape allows is left out rather than
    drawn with an empty list.
    """
    registry = await connectors_of(request)
    serving = set(registry.serving())
    found: dict[str, ConditionField] = {}
    for name in agent.authority.connectors:
        if name not in serving:
            continue
        for projection in registry.get(name).manifest.projections:
            for projected in projection.fields:
                one = ConditionField(
                    connector=name,
                    entity=projection.entity,
                    name=projected.name,
                    shape=projected.shape,
                )
                if one.ops:
                    found[one.key] = one
    return found


def _serving_connectors(agent: AgentRecord, serving: set[str]) -> list[str]:
    return sorted(name for name in agent.authority.connectors if name in serving)


def _cadence_of(asked: CadenceAsked | None) -> Cadence | None:
    return (
        None
        if asked is None
        else Cadence(every=asked.every, hour_utc=asked.hour_utc, weekday=asked.weekday)
    )


def _authored_from(
    body: AuthoringAsked, agent: AgentRecord, fields: Mapping[str, ConditionField]
) -> Authored:
    """What was written, or `AuthoringRefusedError` carrying every reason."""
    template = template_for(body.template_id)
    name = body.name.strip() or ("" if template is None else template.name)
    instruction = body.instruction.strip() or ("" if template is None else template.summary)
    guards = body.guards.strip() or ("" if template is None else template.guards)
    try:
        trigger = TriggerChoice(
            kind=body.trigger.kind,
            cadence=_cadence_of(body.trigger.cadence),
            source=body.trigger.source.strip(),
        )
        condition = (
            None
            if body.condition is None
            else Condition(
                field=body.condition.field, op=body.condition.op, value=body.condition.value
            )
        )
    except GalleryError as exc:
        raise AuthoringRefusedError([str(exc)]) from exc
    return compose(
        agent=agent,
        name=name,
        instruction=instruction,
        guards=guards,
        trigger=trigger,
        tools=body.tools,
        condition=condition,
        fields=fields,
        template=template,
    )


def _refused(findings: tuple[str, ...]) -> JSONResponse:
    view = AuthoringRefusedView(outcome=REFUSED, sentences=list(findings))
    return JSONResponse(status_code=422, content=view.model_dump(mode="json"))


def _authoring_door(agent_id: str, body: AuthoringAsked, asked: Asking) -> None:
    """The cheap questions, before the agent is read. A missing template is the one 404."""
    if not may_open_gallery(asked.reach, asked.now):
        raise _not_here("tab", asked)
    template = template_for(body.template_id)
    if body.template_id is not None and template is None:
        raise _not_here("template", asked)
    task = AUTHORED_TASK if template is None else template.task
    if not may_author(agent_id, task, asked.reach, asked.now):
        raise _not_here("scope", asked)


def preview_view(
    shown: AuthoringPreview, asked: Asking, fields: Mapping[str, ConditionField]
) -> AuthoringPreviewView:
    one = shown.authored
    lines = rehearse(
        one,
        reach_words=shown.capabilities,
        now=asked.now,
        fields=fields,
    )
    return AuthoringPreviewView(
        agent_id=shown.agent_id,
        from_template=one.template_id,
        name=one.name,
        instruction=one.instruction_text,
        guards=one.guards.strip(),
        task=one.task,
        trigger=one.trigger.words(),
        fires=one.trigger.fires,
        nothing_fires=None if one.trigger.fires else NOTHING_FIRES_THIS_YET,
        condition=None if one.condition is None else one.condition.words(),
        tools=list(one.tools),
        runs_as=shown.runs_as.id,
        runs_as_name=shown.runs_as.display_name,
        reach=list(shown.capabilities),
        rehearsal=[
            AuthoringRehearsalView(
                at=line.at,
                condition=None if line.verdict is None else line.verdict.value,
                says=line.says,
            )
            for line in lines
        ],
        confirmation=shown.confirmation,
    )


router = APIRouter(prefix=API_PREFIX, tags=["automations"])


# ------------------------------------------------------------------------ the routes
@router.get(OPTIONS_PATH, response_model=AuthoringOptions, responses=COMMON_RESPONSES)
async def authoring_options(request: Request, agent_id: str, asked: Asked) -> AuthoringOptions:
    """What a person may choose when writing a new automation on this agent, if they may at all."""
    if not may_open_gallery(asked.reach, asked.now):
        raise _not_here("tab", asked)
    if not await authoring_is_on(request):
        return AuthoringOptions(enabled=False)
    if not may_author(agent_id, AUTHORED_TASK, asked.reach, asked.now):
        raise _not_here("scope", asked)
    agent = await _visible_agent(request, agent_id, asked)
    fields = await _fields_of(request, agent)
    serving = set((await connectors_of(request)).serving())
    return AuthoringOptions(
        enabled=True,
        templates=[
            TemplateOption(
                template_id=one.template_id,
                name=one.name,
                summary=one.summary,
                guards=one.guards,
                every=default_cadence(one).every,
                hour_utc=default_cadence(one).hour_utc,
                weekday=default_cadence(one).weekday,
            )
            for one in sorted(BUILT_IN, key=lambda t: (t.name, t.template_id))
        ],
        triggers=[
            TriggerOption(kind=kind, label=TRIGGER_LABELS[kind], fires=kind is TriggerKind.SCHEDULE)
            for kind in TriggerKind
        ],
        fields=[
            FieldOption(
                key=one.key,
                label=one.label,
                shape=one.shape.value,
                ops=[OpOption(op=op, label=OP_LABELS[op], in_days=op in DAY_OPS) for op in one.ops],
            )
            for one in sorted(fields.values(), key=lambda f: f.key)
        ],
        tools=sorted(agent.authority.allowed_tools),
        connectors=_serving_connectors(agent, serving),
    )


@router.post(PREVIEW_PATH, response_model=AuthoringPreviewView, responses=_TOLD)
async def authoring_preview(
    request: Request, agent_id: str, body: AuthoringAsked, asked: Asked
) -> JSONResponse:
    """What writing this would store, as the caller, what it would have done at its last few
    triggers, and the digest confirming it. Writes nothing."""
    if not await authoring_is_on(request):
        raise _not_here("switch", asked)
    _authoring_door(agent_id, body, asked)
    agent = await _visible_agent(request, agent_id, asked)
    fields = await _fields_of(request, agent)
    try:
        authored = _authored_from(body, agent, fields)
    except AuthoringRefusedError as exc:
        return _refused(exc.findings)
    shown = preview(authored, agent, author=asked.caller.principal, author_reach=asked.reach)
    return JSONResponse(
        status_code=200, content=preview_view(shown, asked, fields).model_dump(mode="json")
    )


@router.post(CREATE_PATH, status_code=201, response_model=AuthoringWrittenView, responses=_TOLD)
async def author_automation(
    request: Request, agent_id: str, body: CreateAsked, asked: Asked
) -> JSONResponse:
    """Write one automation onto one agent, confirmed, as the caller, paused. A row, its registry
    entry and a ledger entry, or a refusal that wrote nothing.

    The preview is computed again here, from the server's own reading of the agent, the install and
    the caller's reach now, and the confirmation is compared with that rather than with anything the
    request carried beside it.
    """
    if not await authoring_is_on(request):
        raise _not_here("switch", asked)
    _authoring_door(agent_id, body, asked)
    agent = await _visible_agent(request, agent_id, asked)
    fields = await _fields_of(request, agent)
    try:
        authored = _authored_from(body, agent, fields)
    except AuthoringRefusedError as exc:
        return _refused(exc.findings)
    shown = preview(authored, agent, author=asked.caller.principal, author_reach=asked.reach)
    try:
        written = authoring_of(
            shown, confirmation=body.confirmation, automation_id=new_automation_id()
        )
    except NotConfirmedError:
        log.info("automation authoring unconfirmed", principal=asked.caller.principal.id)
        view = AuthoringNotWrittenView(outcome=UNCONFIRMED, sentence=LOOK_AGAIN)
        return JSONResponse(status_code=409, content=view.model_dump(mode="json"))
    automation_id = await authors_of(request).author(
        written, ent_hash=asked.reach.ent_hash(), trace_id=_trace_id()
    )
    automation = written.installation.automation
    return JSONResponse(
        status_code=201,
        content=AuthoringWrittenView(
            automation_id=automation_id,
            agent_id=automation.agent_id,
            name=automation.name,
            runs_as=automation.runs_as.id,
            next_run_at=automation.next_run_at,
        ).model_dump(mode="json"),
    )
