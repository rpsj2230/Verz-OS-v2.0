"""An agent enabled, disabled, archived, handed on or duplicated, and a published version installed.

`brain.agents.lifecycle` has decided enable, disable, archive and transfer since M13.1.4, and
`brain.agents.install_store.StoredAgentInstalls.finish` writes an install, and no route called any
of them, so the agent workspace could show an agent and could not switch it off. This module orders
the questions and writes through a store, and adds no rule of its own about any of the moves: each
refusal a person reads is the domain's sentence or one of the five named below.

**Who may act on an agent is three questions, asked in this order, and all three failing look the
same.** The capability from the reach alone, before anything is read, so a caller holding no grant
is refused identically on a process with a database and one without. Then the agent's audience,
`brain.agents.model.visible_agent_ids` through `brain.agent_routes.viewer_of`, so an agent the
workspace would not open is not one this module will move. Then the capability again, in a scope
admitting the agent's row, `brain.console.govern._in_reach` over `brain.prompt_routes.
agent_scope_row`, which is the Prompts screen's question about the same row. A missing agent, a
hidden one and one outside the caller's authority are one 404 with `Absent`'s one body, the body
`brain.agent_routes` answers for an agent that does not exist. See
`A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_REFUSAL_HERE_TOO`.

**Two capabilities, and neither is a new idea.** `brain.agents.lifecycle.AGENT_LIFECYCLE_CAPABILITY`
enables, disables, archives and transfers; `brain.agents.creation.AGENT_INSTALL_CAPABILITY` installs
and duplicates. Both are `admin:` verbs, which `brain.gate.admission` admits only at strong
assurance, so the second factor is required without a line here asking for it, and both are in
`brain.identity.first_administrator.ADMINISTRATION`, so the first administrator's reconciliation
grants them at the next start.

**Publishing an agent to the whole company is served since 2026-10-06 (M33.1.2.1), and it is a
second person's act by construction.** `brain.agents.lifecycle.publish` refuses the agent's own
steward and anybody without `AGENT_PUBLICATION_CAPABILITY`, which is
`A_GATE_ONE_PERSON_PASSES_ALONE_IS_NOT_A_GATE`: the steward asks, and somebody else holding the
visibility authority publishes. The capability is asked with no scope, as
`brain.console.global_surfaces.may_publish` argues, because an audience is not a row. The write is a
compare-and-set on the audience columns, and `0137`'s trigger records it as `published`. Retiring
a published agent is the archive route, unchanged.

**A stale page cannot act, and each move names what it was shown.** Enable, disable and archive
send the state the page drew; transfer sends the steward it drew; a duplicate sends the install's
`effective_hash`; an install sends the version's content digest, which `GET` on the version serves
beside the sentence a person confirms. A mismatch is a 409 and writes nothing, and the write itself
is a compare-and-set on the lifecycle columns, so two administrators pressing at once cannot both
win. See `WHAT_YOU_SAW_IS_NOT_WHAT_IS_THERE`.

**A refusal to a caller who may act is a 409 with a word and a sentence**, which is
`brain.automation_schedule_routes`' shape: a stale page, an archived agent somebody tried to enable
(the domain's own sentence, `brain.agents.lifecycle.ARCHIVE_IS_TERMINAL`), a steward who cannot take
the agent, a copy that would reach more than its source, and an install this process cannot make.

**Every move reaches the ledger from `0137`'s trigger on `agent.agent`**, told who, at what reach
and for which request by `brain.tables.audit.attributed_to` in the transaction that writes, as the
Prompts screen tells `0059`'s. An install and a duplicate are recorded as `created` with the row's
own `created_by`, which is the caller. A transfer is recorded by `0105`'s trigger as
`agent_owner`, with both owners, and not a second time by `0137`'s.

**Installing and duplicating need this install's template signing key.**
`brain.agents.template.install` verifies a version's signature at the moment it becomes
configuration, with the key that signed it. The key is read from `app.state.template_key`, which
`brain.app`'s lifespan fills from the install's write-once vault slot (`brain.ops.template_key`,
since 2026-09-29), and both routes answer a process without one, on an install with no vault or
one whose policy was not reloaded, with `NO_SIGNING_KEY_HERE` rather than signing with a key kept
somewhere weaker. See `INSTALLING_NEEDS_THE_KEY_THIS_INSTALL_VERIFIES_WITH`.

**What an install is told about connectors, and what it is not.** `complete` reads connector
readiness from a `brain.connectors.registry.ConnectorRegistry`, which `connectors_of` builds from
the install's connections on each request (since 2026-09-30; until then this process held none, so
every declared connector read as not installed whatever the Connectors screen showed). A source
connected under this release's declaration serves; one connected under another is quarantined.
The agent is written disabled anyway
(`brain.agents.install_store.AN_INSTALLED_AGENT_IS_WRITTEN_DISABLED`), and the answer carries no
list of what is missing. `app.state.connector_registry` still wins when a test puts one there.

**A new module rather than `brain.agent_routes`**, because that router is the agent page's data and
is changing under another package; these are writes, and a write and the read it changes are
already separate modules for the Prompts screen and the Skills screen.

Task ids: M27.11.6, M27.11.7, M11.9.4, M13.7.4, M39.2.4.2
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import (
    TEMPLATE_SCREEN,
    _tool_registry,
    declared_channels,
    product_field_policy,
    record_of,
    viewer_of,
)
from brain.agents.creation import (
    AGENT_INSTALL_CAPABILITY,
    duplicate_draft,
    install_draft,
    mint_agent_id,
    new_audience,
    widened,
)
from brain.agents.install import InstallDraft
from brain.agents.install_store import (
    INSTALLED_RUNG,
    Finished,
    InstallStoreError,
    StoredAgentInstalls,
    prepared,
    rungs_above_the_start,
)
from brain.agents.lifecycle import (
    AGENT_LIFECYCLE_CAPABILITY,
    archive,
    disable,
    enable,
    publish,
    transfer_ownership,
)
from brain.agents.model import (
    ASKING_CHANNELS,
    DISPLAY_NAME_CHARS,
    AgentAudience,
    AgentError,
    AgentRecord,
    EnabledChannels,
    answering_on,
    enabled_channels,
)
from brain.agents.model import visible_agent_ids as _visible_agent_ids
from brain.agents.template import SignedManifest, TemplateError, TemplateInstance
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking, base_schema_of
from brain.audit.ledger import DIGEST

# The automations' own 409 body, reused rather than copied: two classes of one name are one schema
# only while every word matches, and the first edit to either would rename both in the document.
from brain.automation_schedule_routes import NotChangedView
from brain.connectors.contract import ConnectorContractError
from brain.connectors.manifest import ManifestError, manifest_digest
from brain.connectors.registry import ConnectorRegistry, ConnectorState, RegisteredConnector
from brain.console.agent_tabs import channel_rows
from brain.console.global_surfaces import may_publish, publishable
from brain.console.govern import _in_reach
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import Capability
from brain.core.errors import Absent, Failed
from brain.core.principal import Principal
from brain.gate.context import Channel
from brain.gate.leash import Leash
from brain.identity.principal_store import StoredPrincipals
from brain.ops.connectable import NotConnectableError, manifest_for
from brain.ops.connector_store import Connection, StoredConnections
from brain.ops.lark_base_index import switched_on
from brain.ops.learning_signal_store import StoredLearningPauses
from brain.prompt_routes import agent_scope_row, every_agent_with_install, installed, signed_of
from brain.routing_routes import sessions_of
from brain.tables.agent import AgentRow
from brain.tables.audit import attributed_to
from brain.tables.learning_signal import REASON_CHARS
from brain.tables.template import TemplateVersionRow
from brain.tools.registry import ToolRegistry

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons

#: Why every reason a caller may not act on an agent is one answer.
A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_REFUSAL_HERE_TOO: Final = (
    "A caller without the capability, a caller whose audience does not cover the agent, a caller "
    "whose authority does not reach its row, and a caller naming an agent that does not exist are "
    "one 404 with one body. A lifecycle route that answered 'not yours' where the workspace "
    "answers 'not found' would be the oracle the workspace was written to close, one address along."
)

#: Why a move names what the page showed.
WHAT_YOU_SAW_IS_NOT_WHAT_IS_THERE: Final = (
    "A page is a reading from some time ago. Enabling an agent somebody archived since, handing "
    "on an agent somebody else already handed on, or duplicating a configuration that has changed "
    "would each act on a state the person never saw, so each move sends what was shown, the write "
    "compares it again, and a mismatch changes nothing."
)

#: Why installing is unavailable on a process with no key, and not made available with another one.
INSTALLING_NEEDS_THE_KEY_THIS_INSTALL_VERIFIES_WITH: Final = (
    "A version becomes an agent only after its signature is verified with the key this install "
    "signs with. That key lives only in the install's write-once vault slot, so a process that "
    "holds none, with no vault or before the vault's policy was reloaded, says installing is "
    "unavailable here rather than verifying with a key kept somewhere weaker."
)

# ------------------------------------------------------------------------------ the figures

#: The addresses, under `API_PREFIX`. `console/src/pages/agentLifecycleQuery.ts` names the same.
LIFECYCLE_PATH: Final = "/agents/{agent_id}/lifecycle"
ENABLE_PATH: Final = "/agents/{agent_id}/enable"
DISABLE_PATH: Final = "/agents/{agent_id}/disable"
ARCHIVE_PATH: Final = "/agents/{agent_id}/archive"
PUBLICATION_PATH: Final = "/agents/{agent_id}/publish"
TRANSFER_PATH: Final = "/agents/{agent_id}/transfer"
DUPLICATE_PATH: Final = "/agents/{agent_id}/duplicate"
LEARNING_PATH: Final = "/agents/{agent_id}/learning"
CHANNELS_PATH: Final = "/agents/{agent_id}/channels"
VERSION_PATH: Final = "/agent-templates/{template_id}/versions/{version}"
INSTALL_PATH: Final = "/agent-templates/{template_id}/versions/{version}/install"

#: How many hex characters of randomness follow a minted id's stem.
ID_SUFFIX_BYTES: Final = 3

#: The words a 409 carries.
MOVED: Final = "moved"
REFUSED: Final = "refused"
UNAVAILABLE: Final = "unavailable"

#: What a stale page is told.
IT_MOVED: Final = (
    "This agent changed after you opened it, so nothing was changed. Look again and choose."
)

#: What a version that is not the body confirmed is told.
NOT_THE_VERSION_CONFIRMED: Final = (
    "The version is not the one you confirmed, so nothing was installed. Look again and confirm."
)

#: What a process with no signing key says, to a caller who may install.
NO_SIGNING_KEY_HERE: Final = (
    "Installing and duplicating are unavailable on this install: it holds no template signing key "
    "yet, and a version becomes an agent only once this install's key has verified it."
)

#: What a duplicate of an agent with no install record says.
NOTHING_TO_DUPLICATE_FROM: Final = (
    "This agent has no install record that constructs, so there is no version to duplicate it from."
)

#: What a transfer to somebody who cannot take the agent says, whoever they are or are not.
CANNOT_TAKE_IT: Final = (
    "Nothing was handed on: nobody by that id is here and active to answer for this agent."
)

#: What a maker with no department is told when they ask for a department's agent.
NO_DEPARTMENT_TO_SHOW_IT_TO: Final = (
    "Nothing was made: you sit in no department, so the new agent can be seen by you alone."
)

#: What a maker whose authority does not reach the new agent's audience is told.
AUTHORITY_DOES_NOT_REACH_THAT_AUDIENCE: Final = (
    "Nothing was made: your authority to make agents does not reach an agent seen by that "
    "audience. Choose the other one."
)

#: What a minted id that was somehow taken says. It names no agent.
PRESS_AGAIN: Final = "Nothing was made: the name minted for it was in use. Press again."

#: What a new agent starts as, said before it is made.
STARTS_DISABLED_AT_SHADOW: Final = (
    "It is made as a new agent that starts disabled and at Shadow on every target: it answers "
    "nobody until somebody enables it, and it acts on nothing without a person until a rung is "
    "raised with evidence."
)


# ------------------------------------------------------------------------ the shapes
#: What each channel an agent may be enabled on is called on a screen (M13.7.4). A product word,
#: the same on every install, and the same word `brain.binding_routes.CHANNEL_LABELS` uses for
#: every channel both name, which a test holds. Keyed by `ASKING_CHANNELS`, which a test holds too.
AGENT_CHANNEL_LABELS: Final[Mapping[str, str]] = {
    Channel.CONSOLE.value: "Web console",
    Channel.LARK.value: "Lark",
    Channel.WHATSAPP.value: "WhatsApp",
    Channel.EMAIL.value: "Email",
    Channel.TELEGRAM.value: "Telegram",
    Channel.API.value: "Programs using a service key",
    Channel.WEBHOOK.value: "Webhook",
    Channel.WIDGET.value: "Website widget",
    Channel.SLACK.value: "Slack",
    Channel.TEAMS.value: "Microsoft Teams",
}

#: The one sentence beside the boxes, so nobody makes a mute agent without being told.
NO_CHANNEL_ANSWERS_NOWHERE: Final = (
    "An agent with no channel ticked answers nowhere: nobody can ask it anything until one is."
)


class ChannelChoiceView(BaseModel):
    """One channel a new agent may be switched on for, as a box on the page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str


def channel_choices() -> list[ChannelChoiceView]:
    """Every channel an agent may answer on, in `Channel`'s order, none of them ticked."""
    return [
        ChannelChoiceView(name=name, label=AGENT_CHANNEL_LABELS[name]) for name in ASKING_CHANNELS
    ]


class LifecycleView(BaseModel):
    """One agent's state, its steward and what this reader may do with it.

    Served only to a reader who may do something, which is why a lifecycle word appears here
    and never on the roster: `brain.agent_routes` rejected a state on a roster entry because a
    member reading "disabled" beside a name is told why an agent is not chosen, and an
    administrator deciding whether to enable it is exactly the reader who needs the word.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str
    #: `brain.agents.model.AgentState`: enabled, disabled or archived.
    state: str
    owner_id: str
    #: The install's configuration digest, which a duplicate must name. Null with no install.
    effective_hash: str | None
    #: Holds the lifecycle authority over this agent's row.
    may_change: bool
    #: Holds the install authority over this row, the agent has an install and this process can
    #: install. Presentation only: the route asks every question again.
    may_duplicate: bool
    #: Why a reader holding the install authority over this row may still not duplicate it.
    duplicate_unavailable: str | None = None
    #: Who may find the agent: personal, department or company. What a publication names.
    level: str = ""
    #: Holds the visibility authority, is not the steward, and the agent is neither archived nor
    #: already company-wide. Presentation only: `publish_agent` asks every question again.
    may_publish: bool = False
    #: The channels this agent answers on now (M13.7.4), as stored: sorted names.
    channels: list[str] = Field(default_factory=list)
    #: Every channel it could be switched on for, as boxes. See `channel_choices`.
    channel_choices: list[ChannelChoiceView] = Field(default_factory=channel_choices)
    #: `NO_CHANNEL_ANSWERS_NOWHERE`.
    channels_note: str = NO_CHANNEL_ANSWERS_NOWHERE
    #: Its steward, or a holder of the lifecycle authority over its row. Presentation only: the
    #: route asks again. See `A_STEWARD_OR_AN_ADMINISTRATOR_SWITCHES_AN_AGENT_S_CHANNELS`.
    may_change_channels: bool = False


class ChannelsAsked(BaseModel):
    """The channels an agent should answer on, and the channels the page drew."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    channels: list[str] = Field(max_length=len(ASKING_CHANNELS))
    expected: list[str] = Field(max_length=len(ASKING_CHANNELS))

    @field_validator("channels", "expected")
    @classmethod
    def _askable(cls, value: list[str]) -> list[str]:
        return list(enabled_channels(value))


class LeashRungView(BaseModel):
    """One target of a new agent's leash, and the rung it starts on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str
    rung: str


class CreatedView(BaseModel):
    """A new agent, as the reader who made it may act on it, and the leash it starts on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent: LifecycleView
    #: Every target the version's leash names, each at `INSTALLED_RUNG`. Empty is Shadow on every
    #: target too, which is `brain.gate.leash.MISSING_ENTRY_RUNG`.
    leash: list[LeashRungView]


class TemplateVersionView(BaseModel):
    """A published version, the digest an install must name, and what installing it makes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str
    version: int
    display_name: str
    summary: str | None = None
    content_digest: str
    #: `STARTS_DISABLED_AT_SHADOW`, the sentence a person confirms.
    starts: str
    #: Why this version cannot be installed here, when it cannot.
    unavailable: str | None = None
    #: The channels the new agent may be switched on for, offered unticked (M13.7.4).
    channels: list[ChannelChoiceView] = Field(default_factory=channel_choices)
    #: `NO_CHANNEL_ANSWERS_NOWHERE`.
    channels_note: str = NO_CHANNEL_ANSWERS_NOWHERE


class LifecycleStateAsked(BaseModel):
    """The state the page drew. See `WHAT_YOU_SAW_IS_NOT_WHAT_IS_THERE`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_state: Literal["enabled", "disabled", "archived"]


class PublicationAsked(BaseModel):
    """The audience the page drew, so a stale page cannot publish. See
    `WHAT_YOU_SAW_IS_NOT_WHAT_IS_THERE`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_level: Literal["personal", "department", "company"]


class LearningSwitchAsked(BaseModel):
    """Pause or resume what one agent's runs may teach, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    paused: bool
    reason: str = Field(min_length=1, max_length=REASON_CHARS)


class LearningSwitchView(BaseModel):
    """Whether one agent's runs may teach anything now."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    paused: bool


class TransferAsked(BaseModel):
    """Who takes the agent, and the steward the page drew."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    to_owner: str = Field(min_length=1, max_length=128)
    expected_owner: str = Field(min_length=1, max_length=128)


class DuplicateAsked(BaseModel):
    """The copy's name, the configuration the page drew, and who sees the copy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    display_name: str = Field(min_length=1, max_length=DISPLAY_NAME_CHARS)
    expected_hash: str = Field(pattern=DIGEST)
    #: False: the maker alone. True: the maker's own department.
    for_department: bool = False


class TemplateInstallAsked(BaseModel):
    """The new agent's name, the digest confirmed, and who sees the new agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    display_name: str | None = Field(default=None, max_length=DISPLAY_NAME_CHARS)
    expected_digest: str = Field(pattern=DIGEST)
    for_department: bool = False
    #: The channels the new agent answers on, as the person ticked them; none answers nowhere.
    channels: EnabledChannels = ()


# ------------------------------------------------------------------------ the store
@dataclass(frozen=True)
class FoundAgent:
    """One stored agent, its install when one constructs, and the install's configuration hash."""

    record: AgentRecord
    install: tuple[SignedManifest, TemplateInstance] | None
    effective_hash: str | None


@runtime_checkable
class AgentLifecycles(Protocol):
    """What these routes need of the agent tables. `StoredAgentLifecycles` implements it."""

    async def agent(self, agent_id: str) -> FoundAgent | None: ...

    async def version(self, template_id: str, version: int) -> SignedManifest | None: ...

    async def live_principal(self, principal_id: str) -> Principal | None: ...

    async def change(
        self,
        before: AgentRecord,
        after: AgentRecord,
        *,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool: ...

    async def widen(
        self,
        before: AgentRecord,
        after: AgentRecord,
        *,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool: ...

    async def create(
        self,
        draft: InstallDraft,
        *,
        key: str,
        registry: ConnectorRegistry,
        tools: ToolRegistry,
        at: datetime,
        ent_hash: str,
        trace_id: str,
        audience: AgentAudience,
        channels: tuple[str, ...] = (),
    ) -> Finished: ...

    async def change_channels(
        self,
        before: AgentRecord,
        after: AgentRecord,
        *,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool: ...


class StoredAgentLifecycles:
    """`AgentLifecycles` over `agent.agent`, its install rows and `auth.principal`."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def agent(self, agent_id: str) -> FoundAgent | None:
        async with self._sessions() as session:
            found = (
                await session.execute(every_agent_with_install().where(AgentRow.id == agent_id))
            ).one_or_none()
        if found is None:
            return None
        agent_row, instance_row, version_row = found
        record = record_of(agent_row)
        if record is None:
            return None
        return FoundAgent(
            record=record,
            install=installed(instance_row, version_row),
            effective_hash=None if instance_row is None else instance_row.effective_hash,
        )

    async def version(self, template_id: str, version: int) -> SignedManifest | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(TemplateVersionRow).where(
                        TemplateVersionRow.template_id == template_id,
                        TemplateVersionRow.version == version,
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        try:
            return signed_of(row)
        except (KeyError, ValueError, TemplateError) as exc:
            log.warning(
                "published template does not construct",
                template=template_id,
                error=type(exc).__name__,
            )
            return None

    async def live_principal(self, principal_id: str) -> Principal | None:
        return await StoredPrincipals(self._sessions).live_principal(principal_id)

    async def change(
        self,
        before: AgentRecord,
        after: AgentRecord,
        *,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool:
        """Write the lifecycle columns and the steward if they still hold what `before` read.

        A compare-and-set rather than a lock, because the three columns compared are the whole of
        what a lifecycle move reads: a row that moved between the read and this statement matches
        nothing, and the route answers that it moved. See `WHAT_YOU_SAW_IS_NOT_WHAT_IS_THERE`.
        """
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(actor_id=actor_id, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            written = (
                await session.execute(
                    update(AgentRow)
                    .where(
                        AgentRow.id == before.agent_id,
                        AgentRow.disabled_at.is_not_distinct_from(before.disabled_at),
                        AgentRow.archived_at.is_not_distinct_from(before.archived_at),
                        AgentRow.owner_id == before.audience.owner_id,
                    )
                    .values(
                        disabled_at=after.disabled_at,
                        archived_at=after.archived_at,
                        owner_id=after.audience.owner_id,
                    )
                    .returning(AgentRow.id)
                )
            ).scalar_one_or_none()
        return written is not None

    async def widen(
        self,
        before: AgentRecord,
        after: AgentRecord,
        *,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool:
        """Write the audience if it, and the agent's archive, still hold what `before` read.

        `change`'s compare-and-set, over the two audience columns a publication moves: a row
        whose audience moved, or that was archived, between the read and this statement matches
        nothing, and the route answers that it moved.
        """
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(actor_id=actor_id, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            written = (
                await session.execute(
                    update(AgentRow)
                    .where(
                        AgentRow.id == before.agent_id,
                        AgentRow.visibility == before.audience.level.value,
                        AgentRow.department.is_not_distinct_from(
                            before.audience.department or None
                        ),
                        AgentRow.archived_at.is_(None),
                    )
                    .values(
                        visibility=after.audience.level.value,
                        department=after.audience.department or None,
                    )
                    .returning(AgentRow.id)
                )
            ).scalar_one_or_none()
        return written is not None

    async def change_channels(
        self,
        before: AgentRecord,
        after: AgentRecord,
        *,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool:
        """Write the channels if they still hold what `before` read. A compare-and-set, as `change`.

        `0190`'s trigger appends `channels_changed` to the ledger from this statement, attributed
        by the same three settings.
        """
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(actor_id=actor_id, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            written = (
                await session.execute(
                    update(AgentRow)
                    .where(
                        AgentRow.id == before.agent_id,
                        AgentRow.channels == list(before.channels),
                    )
                    .values(channels=list(after.channels))
                    .returning(AgentRow.id)
                )
            ).scalar_one_or_none()
        return written is not None

    async def create(
        self,
        draft: InstallDraft,
        *,
        key: str,
        registry: ConnectorRegistry,
        tools: ToolRegistry,
        at: datetime,
        ent_hash: str,
        trace_id: str,
        audience: AgentAudience,
        channels: tuple[str, ...] = (),
    ) -> Finished:
        return await StoredAgentInstalls(self._sessions).finish(
            draft,
            key=key,
            audience=audience,
            registry=registry,
            tools=tools,
            at=at,
            ent_hash=ent_hash,
            trace_id=trace_id,
            channels=channels,
        )


def lifecycles_of(request: Request) -> AgentLifecycles:
    """`app.state.agent_lifecycles` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "agent_lifecycles", None)
    if isinstance(found, AgentLifecycles):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredAgentLifecycles(factory)


def template_key_of(request: Request) -> str | None:
    """This install's template signing key, or None. See
    `INSTALLING_NEEDS_THE_KEY_THIS_INSTALL_VERIFIES_WITH`."""
    found = getattr(request.app.state, "template_key", None)
    return found if isinstance(found, str) and found else None


async def connectors_of(request: Request) -> ConnectorRegistry:
    """What this install has connected, read from its connections on this request.

    A registry a test put on the process wins; otherwise each source connected on the Connectors
    screen, serving when its stored digest is this release's declaration and quarantined when it
    is not. Empty on a process with no database, or one whose connection table cannot be read.
    See `brain.connectors.registry.CONNECTED_IS_WHAT_AN_AGENT_INSTALL_READS`.
    """
    found = getattr(request.app.state, "connector_registry", None)
    if isinstance(found, ConnectorRegistry):
        return found
    sessions = sessions_of(request)
    if sessions is None:
        return ConnectorRegistry()
    try:
        connected = await StoredConnections(sessions).connected()
    except SQLAlchemyError as exc:
        log.warning("connections unread for an agent's connectors", error=type(exc).__name__)
        return ConnectorRegistry()
    entries = [one for one in (_registered(c) for c in connected) if one is not None]
    base = await _switched_on_base(request)
    return ConnectorRegistry.of_connected((*entries, *(() if base is None else (base,))))


async def _switched_on_base(request: Request) -> RegisteredConnector | None:
    """A Lark Base switched on in Connect Lark, serving, or None where none is or it cannot be read.

    Connect Lark registers no connection row for a Base (`brain.ops.lark_base_index`), so without
    this an agent needing `lark_base` read it as not installed whatever Connect Lark said. It is
    serving when its schema can be read, under the manifest this release builds for its first
    table: the Base has no agreed digest to disagree with, because it was never connected on the
    Connectors screen.
    """
    use = switched_on()
    if use is None:
        return None
    known = await base_schema_of(request.app.state).tables(use)
    if not known:
        return None
    manifest = use.manifest(known[0].table)
    return RegisteredConnector(
        manifest=manifest, digest=manifest_digest(manifest), state=ConnectorState.ENABLED
    )


def _registered(connection: Connection) -> RegisteredConnector | None:
    """One connection as the registry holds it, or None for a source this release cannot build."""
    try:
        manifest = manifest_for(connection.connector, connection.settings)
    except (NotConnectableError, ConnectorContractError, ManifestError):
        return None
    state = (
        ConnectorState.ENABLED
        if manifest_digest(manifest) == connection.digest
        else ConnectorState.QUARANTINED
    )
    return RegisteredConnector(manifest=manifest, digest=connection.digest, state=state)


# ------------------------------------------------------------------------ the decisions
def _no_agent_here(asked: Asking, reason: str) -> Absent:
    """The one refusal about an agent. The reason reaches a log and never a response."""
    log.info("agent lifecycle not answerable", reason=reason, principal=asked.caller.principal.id)
    return Absent("no agent is answerable for this caller")


def _no_version_here(asked: Asking, reason: str) -> Absent:
    """The one refusal about a template version to a caller who may not install."""
    log.info("template install not answerable", reason=reason, principal=asked.caller.principal.id)
    return Absent(f"the {TEMPLATE_SCREEN} screen is not answerable for this caller")


def _not_changed(outcome: str, sentence: str) -> JSONResponse:
    body = NotChangedView(outcome=outcome, sentence=sentence)
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def holds(capability: Capability, record: AgentRecord, asked: Asking) -> bool:
    """Whether this reach holds `capability` in a scope admitting this agent's row."""
    return _in_reach(asked.reach, capability, agent_scope_row(record), asked.now)


#: Who may switch an agent's channels, and why the steward is enough.
A_STEWARD_OR_AN_ADMINISTRATOR_SWITCHES_AN_AGENT_S_CHANNELS: Final = (
    "An agent's channels are changed by its steward or by a holder of the lifecycle authority "
    "over its row, and by nobody else. The steward is enough because a channel moves where people "
    "who may already ask the agent can ask it, never who may find it or what it may reach: its "
    "audience and its ceiling are untouched. Anybody else is answered as an agent that does not "
    "exist, and the change reaches the ledger from the row as channels_changed."
)


#: The surfaces an agent answers on that no channel adapter declares, and why each is offered.
ANSWERED_IN_THE_ASKERS_OWN_SESSION: Final[frozenset[str]] = frozenset(
    {Channel.CONSOLE.value, Channel.API.value}
)

#: Where a channel may be switched on (M39.2.4.2), and the one place that decides it.
A_CHANNEL_IS_SWITCHED_ON_ONLY_WHERE_ITS_RUN_COULD_BE_CARRIED: Final = (
    "A channel with an adapter is switched on only where brain.console.agent_tabs.channel_rows "
    "offers it: the channel's own may_carry asked of the most sensitive thing a run of this "
    "agent by this reader could return, which is the workspace's one decision and not a copy. "
    "The web console and a service key's API answer the person who asked, in their own "
    "session, through the gate's redaction at their reach, and declare no adapter; they are "
    "offered by name. Every other surface with no adapter (the website widget today) is not "
    "offered until it declares what it can carry. Only switching a channel on is judged: one "
    "already on may stay on or be switched off."
)


def switchable_channels(record: AgentRecord, asked: Asking) -> frozenset[str]:
    """The channels this reader may switch this agent on for. See the reason constant above."""
    rows = channel_rows(
        asked.reach,
        record,
        declared_channels(),
        product_field_policy(),
        enabled=(),
        now=asked.now,
    )
    return frozenset(row.channel.value for row in rows) | ANSWERED_IN_THE_ASKERS_OWN_SESSION


#: What a switch onto a channel that cannot carry this agent's answers is told.
CANNOT_CARRY_IT: Final = (
    "That channel cannot carry what this agent may answer, so it was not switched on and "
    "nothing was changed."
)


def may_change_channels(record: AgentRecord, asked: Asking) -> bool:
    """Whether this caller may switch this agent's channels. See the reason constant."""
    return record.audience.owner_id == asked.caller.principal.id or holds(
        AGENT_LIFECYCLE_CAPABILITY, record, asked
    )


def visible(record: AgentRecord, asked: Asking) -> bool:
    """Whether the caller's audience covers this agent, by the one answer to that question."""
    return record.agent_id in _visible_agent_ids((record,), viewer_of(asked))


def duplicate_unavailable(found: FoundAgent, key: str | None) -> str | None:
    """Why this agent cannot be duplicated on this process, or None when it can."""
    if found.install is None or found.effective_hash is None:
        return NOTHING_TO_DUPLICATE_FROM
    if key is None:
        return NO_SIGNING_KEY_HERE
    return None


def lifecycle_view(found: FoundAgent, asked: Asking, key: str | None) -> LifecycleView:
    """One agent as a reader who may act on it sees it."""
    record = found.record
    installs = holds(AGENT_INSTALL_CAPABILITY, record, asked)
    unavailable = duplicate_unavailable(found, key) if installs else None
    return LifecycleView(
        agent_id=record.agent_id,
        display_name=record.display_name,
        state=record.state.value,
        owner_id=record.audience.owner_id,
        effective_hash=found.effective_hash,
        may_change=holds(AGENT_LIFECYCLE_CAPABILITY, record, asked),
        may_duplicate=installs and unavailable is None,
        duplicate_unavailable=unavailable,
        level=record.audience.level.value,
        may_publish=bool(publishable((record,), asked.reach, asked.now)),
        channels=list(record.channels),
        channel_choices=channel_choices_for(record, asked),
        may_change_channels=may_change_channels(record, asked),
    )


def channel_choices_for(record: AgentRecord, asked: Asking) -> list[ChannelChoiceView]:
    """The boxes: every channel this reader may switch on, and every one already on, so a channel
    on today can be switched off whatever it would be offered now."""
    shown = switchable_channels(record, asked) | frozenset(record.channels)
    return [one for one in channel_choices() if one.name in shown]


def leash_view(leash: Leash) -> list[LeashRungView]:
    """The new agent's leash as targets and rung names, in target order."""
    return [
        LeashRungView(target=one.target, rung=one.rung.name.lower())
        for one in sorted(leash.entries, key=lambda entry: entry.target)
    ]


async def _actionable(
    request: Request, agent_id: str, asked: Asking, capability: Capability
) -> tuple[AgentLifecycles, FoundAgent]:
    """The agent, for a caller who holds `capability` over it and whose audience covers it, or
    the one 404. See `A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_REFUSAL_HERE_TOO`."""
    if asked.reach.scope_for(capability, asked.now) is None:
        raise _no_agent_here(asked, "capability")
    store = lifecycles_of(request)
    found = await store.agent(agent_id)
    if found is None or not visible(found.record, asked):
        raise _no_agent_here(asked, "agent")
    if not holds(capability, found.record, asked):
        raise _no_agent_here(asked, "scope")
    return store, found


router = APIRouter(prefix=API_PREFIX, tags=["agents"])

_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": NotChangedView, "description": "Nothing was changed, and why."},
}


@router.get(LIFECYCLE_PATH, response_model=LifecycleView, responses=COMMON_RESPONSES)
async def agent_lifecycle(request: Request, agent_id: str, asked: Asked) -> LifecycleView:
    """One agent's state, steward and channels, for a reader who may change any of them.

    Either authority over the agent's row opens it, and so does being its steward, who may switch
    its channels; anybody else is the one 404.
    """
    found = await lifecycles_of(request).agent(agent_id)
    if found is None or not visible(found.record, asked):
        raise _no_agent_here(asked, "agent")
    if not (
        holds(AGENT_LIFECYCLE_CAPABILITY, found.record, asked)
        or holds(AGENT_INSTALL_CAPABILITY, found.record, asked)
        or may_change_channels(found.record, asked)
    ):
        raise _no_agent_here(asked, "scope")
    return lifecycle_view(found, asked, template_key_of(request))


async def _move(
    request: Request, agent_id: str, body: LifecycleStateAsked, asked: Asking, verb: str
) -> JSONResponse:
    store, found = await _actionable(request, agent_id, asked, AGENT_LIFECYCLE_CAPABILITY)
    before = found.record
    if before.state.value != body.expected_state:
        return _not_changed(MOVED, IT_MOVED)
    try:
        if verb == "enable":
            after = enable(before)
        elif verb == "disable":
            after = disable(before, now=asked.now)
        else:
            after = archive(before, now=asked.now)
    except AgentError as refused:
        return _not_changed(REFUSED, str(refused))
    if after != before and not await store.change(
        before,
        after,
        actor_id=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    ):
        return _not_changed(MOVED, IT_MOVED)
    log.info("agent moved", verb=verb, agent=agent_id, principal=asked.caller.principal.id)
    moved = FoundAgent(record=after, install=found.install, effective_hash=found.effective_hash)
    view = lifecycle_view(moved, asked, template_key_of(request))
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))


@router.post(ENABLE_PATH, response_model=LifecycleView, responses=_TOLD)
async def enable_agent(
    request: Request, agent_id: str, body: LifecycleStateAsked, asked: Asked
) -> JSONResponse:
    """Make a disabled agent selectable again. An archived one is refused in the domain's words."""
    return await _move(request, agent_id, body, asked, "enable")


@router.post(DISABLE_PATH, response_model=LifecycleView, responses=_TOLD)
async def disable_agent(
    request: Request, agent_id: str, body: LifecycleStateAsked, asked: Asked
) -> JSONResponse:
    """Stop an agent being selected, reversibly."""
    return await _move(request, agent_id, body, asked, "disable")


@router.post(ARCHIVE_PATH, response_model=LifecycleView, responses=_TOLD)
async def archive_agent(
    request: Request, agent_id: str, body: LifecycleStateAsked, asked: Asked
) -> JSONResponse:
    """Retire an agent for good. Nothing undoes it: `brain.agents.lifecycle.ARCHIVE_IS_TERMINAL`."""
    return await _move(request, agent_id, body, asked, "archive")


@router.post(PUBLICATION_PATH, response_model=LifecycleView, responses=_TOLD)
async def publish_agent(
    request: Request, agent_id: str, body: PublicationAsked, asked: Asked
) -> JSONResponse:
    """Show an agent to the whole company, as somebody other than its steward (M33.1.2.1).

    The capability from the reach alone, then the agent's audience, as every move here asks; a
    caller without either is the one 404. `lifecycle.publish` refuses the steward and an archived
    agent in its own words, and publishing a company agent again changes nothing.
    """
    if not may_publish(asked.reach, asked.now):
        raise _no_agent_here(asked, "capability")
    store = lifecycles_of(request)
    found = await store.agent(agent_id)
    if found is None or not visible(found.record, asked):
        raise _no_agent_here(asked, "agent")
    before = found.record
    if before.audience.level.value != body.expected_level:
        return _not_changed(MOVED, IT_MOVED)
    try:
        after = publish(before, publisher=asked.reach, now=asked.now)
    except AgentError as refused:
        return _not_changed(REFUSED, str(refused))
    if after != before and not await store.widen(
        before,
        after,
        actor_id=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    ):
        return _not_changed(MOVED, IT_MOVED)
    log.info("agent published", agent=agent_id, principal=asked.caller.principal.id)
    moved = FoundAgent(record=after, install=found.install, effective_hash=found.effective_hash)
    view = lifecycle_view(moved, asked, template_key_of(request))
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))


@router.post(TRANSFER_PATH, response_model=LifecycleView, responses=_TOLD)
async def transfer_agent(
    request: Request, agent_id: str, body: TransferAsked, asked: Asked
) -> JSONResponse:
    """Hand an agent to a new steward who is here and active.

    Somebody who does not exist and somebody disabled, deleted or ended are one sentence, so the
    route is not a way to ask who works here.
    """
    store, found = await _actionable(request, agent_id, asked, AGENT_LIFECYCLE_CAPABILITY)
    before = found.record
    if before.audience.owner_id != body.expected_owner:
        return _not_changed(MOVED, IT_MOVED)
    steward = await store.live_principal(body.to_owner)
    if steward is None or not steward.is_active(asked.now):
        return _not_changed(REFUSED, CANNOT_TAKE_IT)
    try:
        after = transfer_ownership(before, to_owner=steward, now=asked.now)
    except AgentError as refused:
        return _not_changed(REFUSED, str(refused))
    if not await store.change(
        before,
        after,
        actor_id=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    ):
        return _not_changed(MOVED, IT_MOVED)
    log.info("agent handed on", agent=agent_id, principal=asked.caller.principal.id)
    moved = FoundAgent(record=after, install=found.install, effective_hash=found.effective_hash)
    view = lifecycle_view(moved, asked, template_key_of(request))
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))


@router.post(CHANNELS_PATH, response_model=LifecycleView, responses=_TOLD)
async def change_agent_channels(
    request: Request, agent_id: str, body: ChannelsAsked, asked: Asked
) -> JSONResponse:
    """Switch the channels an agent answers on (M13.7.4), for its steward or an administrator.

    See `A_STEWARD_OR_AN_ADMINISTRATOR_SWITCHES_AN_AGENT_S_CHANNELS`. The page sends the channels
    it drew; a row that moved since is a 409 and nothing is written.
    """
    store = lifecycles_of(request)
    found = await store.agent(agent_id)
    if found is None or not visible(found.record, asked):
        raise _no_agent_here(asked, "agent")
    if not may_change_channels(found.record, asked):
        raise _no_agent_here(asked, "scope")
    before = found.record
    if tuple(body.expected) != before.channels:
        return _not_changed(MOVED, IT_MOVED)
    switched_on = frozenset(body.channels) - frozenset(before.channels)
    if not switched_on <= switchable_channels(before, asked):
        return _not_changed(REFUSED, CANNOT_CARRY_IT)
    after = answering_on(before, body.channels)
    if after.channels != before.channels and not await store.change_channels(
        before,
        after,
        actor_id=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    ):
        return _not_changed(MOVED, IT_MOVED)
    log.info("agent channels switched", agent=agent_id, principal=asked.caller.principal.id)
    moved = FoundAgent(record=after, install=found.install, effective_hash=found.effective_hash)
    view = lifecycle_view(moved, asked, template_key_of(request))
    return JSONResponse(status_code=200, content=view.model_dump(mode="json"))


def _audience_for(asked: Asking, for_department: bool) -> AgentAudience | str:
    """The new agent's audience, or the sentence saying why it cannot be the one asked for."""
    department = asked.caller.principal.primary_department
    if for_department and not department:
        return NO_DEPARTMENT_TO_SHOW_IT_TO
    return new_audience(asked.caller.principal.id, department if for_department else None)


async def _create(
    request: Request,
    store: AgentLifecycles,
    draft_for: Callable[[str], InstallDraft],
    *,
    display_name: str | None,
    for_department: bool,
    asked: Asking,
    source: AgentRecord | None,
    channels: tuple[str, ...],
) -> JSONResponse:
    """Make one agent from a draft, for a caller already admitted, or say why not.

    `draft_for` builds the draft from a minted id, so the id is minted here and nowhere else.
    `channels` has no default, so each way of making an agent says where it answers (M13.7.4).
    """
    key = template_key_of(request)
    if key is None:
        return _not_changed(UNAVAILABLE, NO_SIGNING_KEY_HERE)
    tools = _tool_registry(request)
    if tools is None:
        raise Failed("no tool registry on this process")
    audience = _audience_for(asked, for_department)
    if isinstance(audience, str):
        return _not_changed(REFUSED, audience)
    agent_id = mint_agent_id(display_name or "", suffix=secrets.token_hex(ID_SUFFIX_BYTES))
    row = {"agent_id": agent_id}
    if audience.department:
        row["department"] = audience.department
    if not _in_reach(asked.reach, AGENT_INSTALL_CAPABILITY, row, asked.now):
        return _not_changed(REFUSED, AUTHORITY_DOES_NOT_REACH_THAT_AUDIENCE)
    registry = await connectors_of(request)
    try:
        draft = draft_for(agent_id)
        if source is not None:
            copy = prepared(
                draft, key=key, audience=audience, registry=registry, tools=tools, at=asked.now
            ).record
            grown = widened(source, copy, now=asked.now)
            if grown:
                return _not_changed(
                    REFUSED,
                    "Nothing was duplicated: the copy would reach more than the agent it copies, "
                    f"in {', '.join(grown)}, because of what this install has registered since.",
                )
        finished = await store.create(
            draft,
            key=key,
            audience=audience,
            registry=registry,
            tools=tools,
            at=asked.now,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
            channels=channels,
        )
    except (InstallStoreError, TemplateError) as refused:
        return _not_changed(REFUSED, str(refused))
    except ValueError:
        return _not_changed(REFUSED, "Nothing was made: the install refused this agent.")
    if not finished.created:
        return _not_changed(MOVED, PRESS_AGAIN)
    installation = finished.installation
    made = FoundAgent(
        record=installation.record,
        install=(draft.offer.signed, installation.instance),
        effective_hash=installation.effective.config_hash,
    )
    view = CreatedView(agent=lifecycle_view(made, asked, key), leash=leash_view(installation.leash))
    log.info(
        "agent made",
        agent=agent_id,
        duplicate=source is not None,
        principal=asked.caller.principal.id,
    )
    return JSONResponse(status_code=201, content=view.model_dump(mode="json"))


@router.post(DUPLICATE_PATH, status_code=201, response_model=CreatedView, responses=_TOLD)
async def duplicate_agent(
    request: Request, agent_id: str, body: DuplicateAsked, asked: Asked
) -> JSONResponse:
    """A new agent from the version this one pins, with its overlay and a new name, disabled.

    Admitted by the install authority over the source's row, and made only where the same
    authority reaches the copy's audience. See
    `brain.agents.creation.A_DUPLICATE_NEVER_REACHES_MORE_THAN_ITS_SOURCE`.
    """
    store, found = await _actionable(request, agent_id, asked, AGENT_INSTALL_CAPABILITY)
    if found.install is None or found.effective_hash is None:
        return _not_changed(REFUSED, NOTHING_TO_DUPLICATE_FROM)
    if body.expected_hash != found.effective_hash:
        return _not_changed(MOVED, IT_MOVED)
    signed, instance = found.install

    def draft_for(new_id: str) -> InstallDraft:
        return duplicate_draft(
            signed,
            instance,
            agent_id=new_id,
            maker_id=asked.caller.principal.id,
            display_name=body.display_name,
        )

    return await _create(
        request,
        store,
        draft_for,
        display_name=body.display_name,
        for_department=body.for_department,
        asked=asked,
        source=found.record,
        # A copy answers where the agent it copies answers, so duplicating never makes a mute one.
        channels=found.record.channels,
    )


async def _installable(
    request: Request, template_id: str, version: int, asked: Asking
) -> tuple[AgentLifecycles, SignedManifest]:
    """The version, for a caller who may open the gallery and holds the install authority."""
    if not permitted(screen(TEMPLATE_SCREEN).read, asked.reach, asked.now):
        raise _no_version_here(asked, "screen")
    if asked.reach.scope_for(AGENT_INSTALL_CAPABILITY, asked.now) is None:
        raise _no_version_here(asked, "capability")
    store = lifecycles_of(request)
    signed = await store.version(template_id, version)
    if signed is None:
        sentence = "No published version by that number is available to install."
        raise Absent(sentence, public_message=sentence)
    return store, signed


def version_unavailable(signed: SignedManifest, key: str | None) -> str | None:
    """Why this version cannot be installed on this process, or None when it can."""
    raised = rungs_above_the_start(signed)
    if raised:
        return (
            f"This version starts {', '.join(raised)} above Shadow, and a new agent starts at "
            f"{INSTALLED_RUNG.name.title()} on every target, so it cannot be installed."
        )
    if key is None:
        return NO_SIGNING_KEY_HERE
    return None


@router.get(VERSION_PATH, response_model=TemplateVersionView, responses=COMMON_RESPONSES)
async def template_version(
    request: Request, template_id: str, version: int, asked: Asked
) -> TemplateVersionView:
    """One published version, with the digest an install names and the sentence it confirms."""
    _, signed = await _installable(request, template_id, version, asked)
    identity = signed.manifest.identity
    return TemplateVersionView(
        template_id=identity.template_id,
        version=identity.version,
        display_name=identity.display_name,
        summary=identity.summary or None,
        content_digest=signed.content_digest,
        starts=STARTS_DISABLED_AT_SHADOW,
        unavailable=version_unavailable(signed, template_key_of(request)),
    )


@router.post(INSTALL_PATH, status_code=201, response_model=CreatedView, responses=_TOLD)
async def install_version(
    request: Request, template_id: str, version: int, body: TemplateInstallAsked, asked: Asked
) -> JSONResponse:
    """A published version installed as a new agent, disabled and at Shadow, through
    `StoredAgentInstalls.finish`."""
    store, signed = await _installable(request, template_id, version, asked)
    if body.expected_digest != signed.content_digest:
        return _not_changed(MOVED, NOT_THE_VERSION_CONFIRMED)
    name = body.display_name or signed.manifest.identity.display_name

    def draft_for(new_id: str) -> InstallDraft:
        return install_draft(
            signed, agent_id=new_id, maker_id=asked.caller.principal.id, display_name=name
        )

    return await _create(
        request,
        store,
        draft_for,
        display_name=name,
        for_department=body.for_department,
        asked=asked,
        source=None,
        channels=body.channels,
    )


# -------------------------------------------------------------- the learning switch (M16.7.13)
#: Why the switch is the lifecycle's authority and nothing new.
WHO_MAY_SWITCH_AN_AGENT_OFF_MAY_PAUSE_WHAT_IT_LEARNS: Final = (
    "Pausing what an agent's runs teach is a narrower act than switching the agent off, and "
    "the person who may do the second may do the first, over the same row, by the same three "
    "questions. So the switch asks brain.agents.lifecycle.AGENT_LIFECYCLE_CAPABILITY and adds "
    "no capability, and a hidden agent, a missing one and one outside the caller's authority "
    "are the one 404 the lifecycle answers."
)


def learning_pauses_of(request: Request) -> StoredLearningPauses:
    """`app.state.learning_pauses` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "learning_pauses", None)
    if isinstance(found, StoredLearningPauses):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredLearningPauses(factory)


@router.get(LEARNING_PATH, response_model=LearningSwitchView, responses=COMMON_RESPONSES)
async def agent_learning(request: Request, agent_id: str, asked: Asked) -> LearningSwitchView:
    """Whether one agent's learning is paused, for a caller who may switch the agent off."""
    _, found = await _actionable(request, agent_id, asked, AGENT_LIFECYCLE_CAPABILITY)
    paused = await learning_pauses_of(request).paused((found.record.agent_id,))
    return LearningSwitchView(agent_id=found.record.agent_id, paused=bool(paused))


@router.post(LEARNING_PATH, response_model=LearningSwitchView, responses=COMMON_RESPONSES)
async def switch_agent_learning(
    request: Request, agent_id: str, body: LearningSwitchAsked, asked: Asked
) -> LearningSwitchView:
    """Pause or resume what one agent's runs may teach, with a reason, in the caller's name.

    A pause stops memories forming from the agent's runs from the next turn
    (`brain.ops.memory_store.StoredFormations`), and nothing else, so it can only narrow what is
    learned. See `WHO_MAY_SWITCH_AN_AGENT_OFF_MAY_PAUSE_WHAT_IT_LEARNS`.
    """
    _, found = await _actionable(request, agent_id, asked, AGENT_LIFECYCLE_CAPABILITY)
    reason = body.reason.strip()
    if not reason:
        raise _no_agent_here(asked, "reason")
    pauses = learning_pauses_of(request)
    await pauses.set(
        agent_id=found.record.agent_id,
        paused=body.paused,
        reason=reason,
        by=asked.caller.principal.id,
    )
    log.info(
        "agent learning switched",
        agent=found.record.agent_id,
        paused=body.paused,
        principal=asked.caller.principal.id,
    )
    paused = await pauses.paused((found.record.agent_id,))
    return LearningSwitchView(agent_id=found.record.agent_id, paused=bool(paused))
