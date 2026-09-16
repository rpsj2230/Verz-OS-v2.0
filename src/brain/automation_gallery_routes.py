"""The automation gallery over HTTP: what an agent could take on, what installing it would do, and
the one confirmed request that installs it.

`brain.console.automation_gallery` decides every question these three routes ask, and this module
adds no rule of its own. It orders the questions, reaches for a store only once the cheap ones have
been answered, and turns the answers into the shapes the console's Automations tab reads.

**The order is the design.** Every route asks first the question that needs nothing but the
caller's reach, and refuses with one sentence for every agent id when the answer is no: may this
reader open the Automations tab, and, for the preview and the install, may they install this
template onto this agent at all. Only then is the agent read, and an agent outside the caller's
audience is answered exactly as one that does not exist, which is `brain.agent_routes`'
`A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER` at this address too. A caller who may not
install learns nothing about which agents exist by trying, and neither does one who may.

**Every refusal over a thing is the one 404**, whose body `brain.app.handle_brain_error` writes
from `Absent.public_message` whatever this module logged. A template that is not in the catalogue,
an agent that is not there or not visible, a tab the reader may not open and an authority they do
not hold are one answer.

**Two refusals are not 404s, because they are about the request rather than about a thing, and
both write nothing.** A confirmation that does not match what would be installed now is a 409
saying to look again, which only a caller who holds the authority and can see the agent can reach.
A second install of the same template onto the same agent by the same person is a 409 naming the
automation they already have, which is their own. See `INSTALLING_TWICE_IS_ANSWERED_WITH_THE_FIRST`.

**A request with no confirmation never reaches the handler.** `InstallAsked.confirmation` is
required and shaped as a digest, so its absence is refused by validation, after the caller is
authenticated and before anything is read.

**Proved to reach the system in three places.** The row and its registry entry are one row, written
by `brain.ops.agent_automation_store.StoredAgentAutomations.install`; the ledger entry is `0055`'s
trigger, appended in the same transaction; and the behaviour the Automations tab shows changes,
because the gallery reads the reader's installs back and marks the card. What it does not change
is anything that runs, and the gallery says so in words: see
`NOTHING_RUNS_AN_INSTALLED_AUTOMATION_YET`.

Task ids: M39.6.1.3
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Final, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import one_agent, record_of, viewer_of
from brain.agents.model import AgentRecord, visible_agent_ids
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.console.automation_gallery import (
    IT_STARTS_PAUSED,
    ITS_REACH_IS_YOURS_NARROWED_BY_THIS_AGENT,
    NOTHING_RUNS_AN_INSTALLED_AUTOMATION_YET,
    TEMPLATE_ID,
    AutomationTemplate,
    Installation,
    InstallPreview,
    NotConfirmedError,
    gallery,
    install,
    may_install,
    may_open_gallery,
    new_automation_id,
    preview,
    template_by_id,
)
from brain.core.errors import Absent, Failed
from brain.ops.agent_automation_store import Installed, StoredAgentAutomations
from brain.routing_routes import sessions_of

log = structlog.get_logger()

#: The addresses, under `API_PREFIX`. The console's query file names the same three.
GALLERY_PATH: Final = "/agents/{agent_id}/automation-templates"
PREVIEW_PATH: Final = "/agents/{agent_id}/automation-templates/{template_id}/preview"
INSTALL_PATH: Final = "/agents/{agent_id}/automations"

#: What a refused confirmation says. A sentence a person can act on, naming nothing else.
LOOK_AGAIN: Final = (
    "What you confirmed is not what would be installed now: the template, your access or this "
    "agent's ceiling has changed since you looked. Nothing was installed. Look again and confirm."
)

#: What a second install of the same thing says. About the caller's own automation and nothing else.
ALREADY_YOURS: Final = (
    "You have already installed this on this agent, so nothing new was installed. It is the "
    "automation named here."
)

#: A confirmation's shape: the SHA-256 `InstallPreview.confirmation` produces.
CONFIRMATION: Final = r"^[0-9a-f]{64}$"


# ------------------------------------------------------------------------ the shapes
class AutomationTemplateView(BaseModel):
    """One card of the gallery: the outcome, its cadence, and this reader's own install of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str
    version: int
    name: str
    summary: str
    schedule: str
    #: The automation this reader installed from it on this agent, or null.
    installed_as: str | None = None
    #: This reader holds the authority to install it here. Presentation only: decided again.
    installable: bool


class AutomationGalleryView(BaseModel):
    """Every template an agent could take on, and what installing one does and does not do."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[AutomationTemplateView]
    installing: str = NOTHING_RUNS_AN_INSTALLED_AUTOMATION_YET


class InstallPreviewView(BaseModel):
    """Everything the person confirms, and the digest their confirmation must carry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    template_id: str
    version: int
    name: str
    summary: str
    schedule: str
    runs_as: str
    runs_as_name: str
    starts_paused: bool
    paused_because: str = IT_STARTS_PAUSED
    #: What the automation would reach, by capability. Every one is covered by the reader's own.
    reach: list[str]
    reach_rule: str = ITS_REACH_IS_YOURS_NARROWED_BY_THIS_AGENT
    guards: str
    installing: str = NOTHING_RUNS_AN_INSTALLED_AUTOMATION_YET
    confirmation: str


class InstallAsked(BaseModel):
    """Which template, and the confirmation of what was shown. Nothing that could say who."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str = Field(min_length=3, max_length=64, pattern=TEMPLATE_ID)
    confirmation: str = Field(min_length=64, max_length=64, pattern=CONFIRMATION)


class RegistryEntryView(BaseModel):
    """The scheduled job registry's row for what was installed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    automation_id: str
    agent_id: str
    task: str
    runs_as_id: str
    next_run_at: datetime | None
    guards: str


class InstalledView(BaseModel):
    """What was installed, as it was written, and its registry entry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    automation_id: str
    agent_id: str
    template_id: str
    version: int
    name: str
    runs_as: str
    next_run_at: datetime | None
    registry: RegistryEntryView
    installing: str = NOTHING_RUNS_AN_INSTALLED_AUTOMATION_YET


class NotInstalledView(BaseModel):
    """Why nothing was written, in a word and a sentence, naming nothing but the caller's own."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: str
    sentence: str
    #: The automation the caller already has, when that is why.
    automation_id: str | None = None


#: The two words a 409 carries.
UNCONFIRMED: Final = "unconfirmed"
ALREADY_INSTALLED: Final = "already_installed"


# ------------------------------------------------------------------------ the stores
@runtime_checkable
class AgentRecords(Protocol):
    """One stored agent as the domain type, or None when it is not there or does not construct."""

    async def agent(self, agent_id: str) -> AgentRecord | None: ...


@runtime_checkable
class AutomationInstalls(Protocol):
    """What these routes need of `agent.automation`. `StoredAgentAutomations` implements it."""

    async def installed_by(self, agent_id: str, principal_id: str) -> Mapping[str, str]: ...

    async def install(
        self, installation: Installation, *, ent_hash: str, trace_id: str
    ) -> Installed: ...


class StoredAgentRecords:
    """`AgentRecords` over `agent.agent`, read the way `brain.agent_routes` reads one agent."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def agent(self, agent_id: str) -> AgentRecord | None:
        async with self._sessions() as session:
            row = (await session.execute(one_agent(agent_id))).scalar_one_or_none()
        return None if row is None else record_of(row)


def _sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    """The pool, or one fault identical for every caller and every agent id."""
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def agent_records_of(request: Request) -> AgentRecords:
    """`app.state.agent_records` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "agent_records", None)
    if isinstance(found, AgentRecords):
        return found
    return StoredAgentRecords(_sessions(request))


def installs_of(request: Request) -> AutomationInstalls:
    """`app.state.automation_installs` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "automation_installs", None)
    if isinstance(found, AutomationInstalls):
        return found
    return StoredAgentAutomations(_sessions(request))


# ------------------------------------------------------------------------ the refusals
def _not_here(reason: str, asked: Asking) -> Absent:
    """The one refusal these routes make about a thing. The reason reaches a log and no body."""
    log.info("automation gallery refused", reason=reason, principal=asked.caller.principal.id)
    return Absent("no automation gallery is answerable here for this caller")


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.session_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


async def _visible_agent(request: Request, agent_id: str, asked: Asking) -> AgentRecord:
    """The agent, if it is there and this caller's audience covers it, or the one refusal."""
    record = await agent_records_of(request).agent(agent_id)
    if record is None or agent_id not in visible_agent_ids((record,), viewer_of(asked)):
        raise _not_here("agent", asked)
    return record


def _installable_template(agent_id: str, template_id: str, asked: Asking) -> AutomationTemplate:
    """The template, if this caller may open the tab and install it here, or the one refusal.

    Asked of the reach alone, before any store, so the refusal is the same on every process.
    """
    if not may_open_gallery(asked.reach, asked.now):
        raise _not_here("tab", asked)
    # No separate question about holding the authority at all: `may_install` answers it first,
    # and a second copy here would be a guard whose refusal is always the one below.
    template = template_by_id(template_id)
    if template is None:
        raise _not_here("template", asked)
    if not may_install(agent_id, template, asked.reach, asked.now):
        raise _not_here("scope", asked)
    return template


def preview_view(shown: InstallPreview) -> InstallPreviewView:
    template = shown.template
    return InstallPreviewView(
        agent_id=shown.agent_id,
        template_id=template.template_id,
        version=template.version,
        name=template.name,
        summary=template.summary,
        schedule=template.cadence.words(),
        runs_as=shown.runs_as.id,
        runs_as_name=shown.runs_as.display_name,
        starts_paused=shown.next_run_at is None,
        reach=list(shown.capabilities),
        guards=template.guards,
        confirmation=shown.confirmation,
    )


def installed_view(installation: Installation) -> InstalledView:
    automation, entry = installation.automation, installation.entry
    return InstalledView(
        automation_id=automation.automation_id,
        agent_id=automation.agent_id,
        template_id=installation.template_id,
        version=installation.template_version,
        name=automation.name,
        runs_as=automation.runs_as.id,
        next_run_at=automation.next_run_at,
        registry=RegistryEntryView(
            automation_id=entry.automation_id,
            agent_id=entry.agent_id,
            task=entry.task,
            runs_as_id=entry.runs_as_id,
            next_run_at=entry.next_run_at,
            guards=entry.guards,
        ),
    )


def _not_installed(outcome: str, sentence: str, automation_id: str | None = None) -> JSONResponse:
    view = NotInstalledView(outcome=outcome, sentence=sentence, automation_id=automation_id)
    return JSONResponse(status_code=409, content=view.model_dump(mode="json"))


router = APIRouter(prefix=API_PREFIX, tags=["automations"])


# ------------------------------------------------------------------------ the routes
@router.get(GALLERY_PATH, response_model=AutomationGalleryView, responses=COMMON_RESPONSES)
async def automation_gallery(
    request: Request, agent_id: str, asked: Asked
) -> AutomationGalleryView:
    """Every template this agent could take on, each marked with this reader's own install."""
    if not may_open_gallery(asked.reach, asked.now):
        raise _not_here("tab", asked)
    await _visible_agent(request, agent_id, asked)
    installed = await installs_of(request).installed_by(agent_id, asked.caller.principal.id)
    return AutomationGalleryView(
        items=[
            AutomationTemplateView(
                template_id=card.template.template_id,
                version=card.template.version,
                name=card.template.name,
                summary=card.template.summary,
                schedule=card.template.cadence.words(),
                installed_as=card.installed_as,
                installable=may_install(agent_id, card.template, asked.reach, asked.now),
            )
            for card in gallery(installed)
        ]
    )


@router.get(PREVIEW_PATH, response_model=InstallPreviewView, responses=COMMON_RESPONSES)
async def automation_install_preview(
    request: Request, agent_id: str, template_id: str, asked: Asked
) -> InstallPreviewView:
    """What installing this template onto this agent would write, and the digest confirming it."""
    template = _installable_template(agent_id, template_id, asked)
    record = await _visible_agent(request, agent_id, asked)
    shown = preview(template, record, installer=asked.caller.principal, installer_reach=asked.reach)
    return preview_view(shown)


_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": NotInstalledView, "description": "Nothing was installed, and why."},
}


@router.post(INSTALL_PATH, status_code=201, response_model=InstalledView, responses=_TOLD)
async def install_automation(
    request: Request, agent_id: str, body: InstallAsked, asked: Asked
) -> JSONResponse:
    """Install one template onto one agent, confirmed, as the caller. A row, a registry entry
    and a ledger entry, or a refusal that wrote nothing.

    The preview is computed again here, from the server's own reading of the template, the agent
    and the caller's reach now, and the confirmation is compared with that rather than with
    anything the request carried beside it.
    """
    template = _installable_template(agent_id, body.template_id, asked)
    record = await _visible_agent(request, agent_id, asked)
    shown = preview(template, record, installer=asked.caller.principal, installer_reach=asked.reach)
    try:
        installation = install(
            shown, confirmation=body.confirmation, automation_id=new_automation_id()
        )
    except NotConfirmedError:
        log.info("automation install unconfirmed", principal=asked.caller.principal.id)
        return _not_installed(UNCONFIRMED, LOOK_AGAIN)

    done = await installs_of(request).install(
        installation, ent_hash=asked.reach.ent_hash(), trace_id=_trace_id()
    )
    if not done.created:
        return _not_installed(ALREADY_INSTALLED, ALREADY_YOURS, done.automation_id)
    return JSONResponse(
        status_code=201, content=installed_view(installation).model_dump(mode="json")
    )
