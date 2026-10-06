"""A newer version of an agent's template, read, accepted or declined, from the agent's own page.

`brain.agents.upgrade` has said since M13.4.1 what an upgrade is: a decision, a three-column diff
and a durable no, and until 2026-10-06 nothing called any of it, so a published version changed a
badge nobody could see and an agent stayed on the version it was made from for ever. This module
orders the questions, reads the shelf and the declines from the tables that hold them and writes
what an acceptance changes, and adds no rule of its own about what an upgrade may do: each refusal
a person reads is the domain's sentence or one of the few named below.

**Who may act is `brain.agent_lifecycle_routes`' three questions, and all three failing look the
same.** The agent lifecycle authority from the reach alone, before anything is read; then the
agent's audience; then the authority again in a scope admitting the agent's row. A missing agent, a
hidden one and one outside the caller's authority are one 404 with `Absent`'s one body. See
`A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_REFUSAL_HERE_TOO`. Reading the review is the same
question as accepting it: the diff shows the agent's own configuration values, which is what its
Settings tab shows only to a reader who may change it.

**An acceptance names what the page drew, and the write compares it.** The review carries the
install's `effective_hash` and the version on offer; accepting or declining sends both back. A
mismatch is a 409 that writes nothing, and the write itself is a compare-and-set on the hash and the
pinned version, so two administrators pressing at once cannot both win. See
`WHAT_YOU_SAW_IS_NOT_WHAT_IS_THERE`.

**An upgrade never raises a rung** (`brain.agents.upgrade.AN_UPGRADE_NEVER_RAISES_A_RUNG`). The
review says which targets a version would raise and that it cannot be accepted, in words, before
anybody presses; declining is still possible, and is the only thing that quiets the badge for it.

**An upgrade that reaches further waits for somebody who could have written it.** A version whose
settled agent may reach more than the agent did, a capability, a tool or a bigger side effect, is
held to the rule a builder's publish is held to, `brain.builder.agent_drafts.approval_refusal`: the
person accepting is not the person who published that version, and their own reach covers the whole
new ceiling. Nothing here computes a reach, and **an agent is a lens and never a principal**: every
run through the upgraded agent is still `E(caller) intersect agent_ceiling`, computed only by
`EntitlementSet.intersect` where the run happens.

**Accepting writes the install and the agent in one transaction, and a ledger trigger records it.**
The instance row is moved to the new pin with its overlay, owners, effective document and hash, and
the agent row takes the configuration the version decides, the same columns a builder's edit
writes. Everything about the agent that is its own, the steward, the audience, the channels, the
model pin, its bounds and whether it is switched on, is left as it was, except that an agent
the new version leaves incomplete is switched off, as an install is. A decline is one insert and
nothing else. **A pin moved and a decline inserted are on the ledger by the triggers `0204` adds**,
told who, at what reach and for which request by `brain.tables.audit.attributed_to` in the
transaction that writes.

**Accepting needs this install's template signing key**, for the reason
`brain.agent_lifecycle_routes.INSTALLING_NEEDS_THE_KEY_THIS_INSTALL_VERIFIES_WITH` gives: an
accepted version becomes configuration at that moment, and its signature is verified with the key
that signed it. A process without one says so, and a decline needs none.

**A new module rather than `brain.agent_lifecycle_routes`**, because those moves change an agent's
state and this one changes what the agent is; they share its three questions and its 409 body.

Task ids: M13.4.2, M13.4.3, M13.4.4, M13.4.5
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, Protocol, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_lifecycle_routes import (
    NO_SIGNING_KEY_HERE,
    FoundAgent,
    connectors_of,
    holds,
    template_key_of,
    visible,
)
from brain.agent_routes import record_of
from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY, ARCHIVE_IS_TERMINAL
from brain.agents.model import AgentRecord, AgentState
from brain.agents.template import TemplateError
from brain.agents.upgrade import (
    Decline,
    Declines,
    Resolution,
    UpgradeBadge,
    Upgraded,
    UpgradeReview,
    VersionShelf,
    accept,
    decline,
    review,
    rungs_an_upgrade_would_raise,
)
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.audit.ledger import DIGEST
from brain.automation_schedule_routes import NotChangedView
from brain.builder.agent_drafts import approval_refusal, ceiling_of, where, widenings
from brain.builder.draft_store import _configuration
from brain.core.errors import Absent, Failed
from brain.prompt_routes import installed, signed_of
from brain.routing_routes import sessions_of
from brain.tables.agent import AgentRow
from brain.tables.audit import attributed_to
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow
from brain.tables.upgrade import UpgradeDeclineRow
from brain.tools.registry import ToolRegistry

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why every reason a caller may not act on an agent is one answer.
A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_REFUSAL_HERE_TOO: Final = (
    "A caller without the authority, a caller whose audience does not cover the agent, a caller "
    "whose authority does not reach its row and a caller naming an agent that does not exist are "
    "one 404 with one body, so that a review of an upgrade is not an oracle for which agents "
    "exist or what they are made from."
)

#: Why accepting and declining name what the page drew.
WHAT_YOU_SAW_IS_NOT_WHAT_IS_THERE: Final = (
    "A review is a reading from some time ago. Accepting a version that has since been replaced "
    "by a newer one, or onto an agent somebody changed after the page was drawn, would act on a "
    "diff the person never saw, so each move sends the version and the configuration it was "
    "shown, the write compares both again, and a mismatch changes nothing."
)

# ------------------------------------------------------------------------------ the figures
#: The addresses, under `API_PREFIX`. `console/src/pages/agentUpgradeQuery.ts` names the same.
UPGRADE_PATH: Final = "/agents/{agent_id}/upgrade"
ACCEPT_PATH: Final = "/agents/{agent_id}/upgrade/accept"
DECLINE_PATH: Final = "/agents/{agent_id}/upgrade/decline"

#: The words a 409 carries, `brain.agent_lifecycle_routes`' three.
MOVED: Final = "moved"
REFUSED: Final = "refused"
UNAVAILABLE: Final = "unavailable"

#: What a person reads, each once.
IT_MOVED: Final = (
    "This agent, or the version on offer, changed after you opened it, so nothing was changed. "
    "Look again and choose."
)
NOTHING_TO_UPGRADE: Final = (
    "This agent is already on the newest version, so there is nothing to do."
)
NO_INSTALL_TO_UPGRADE: Final = (
    "This agent was not made from a published version, so there is nothing to upgrade."
)
DOES_NOT_SETTLE: Final = (
    "That version cannot be applied to this agent as it is configured. Nothing was changed."
)
WRITTEN_AND_SWITCHED_OFF: Final = (
    "The agent is on the new version and has been switched off, because something it now needs is "
    "not available on this install yet."
)
WRITTEN: Final = "The agent is on the new version. Whether it is switched on has not changed."
DECLINED: Final = "You said no to this version. It will not be offered again; a newer one will be."
THIS_RAISES_A_RUNG: Final = (
    "This version holds an action at a higher rung than this agent is on. A rung is raised from "
    "evidence of the agent's own runs and never by a new version, so it cannot be accepted as it "
    "is. You can say no to it, and the agent stays as it is."
)


# ------------------------------------------------------------------------------ the shapes
class UpgradeOwnerView(BaseModel):
    """Who last set a value, and when. Provenance, never a value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    set_by: str
    set_at: datetime


class UpgradeConflictView(BaseModel):
    """One path this install had claimed and the new version moves: the three columns."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    #: The place on the builder's form, in its own words.
    where: str
    was: Any
    now: Any
    local: Any
    owner: UpgradeOwnerView


class UpgradeChangeView(BaseModel):
    """One path the new version moves that nothing here had claimed: it applies on acceptance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    where: str
    was: Any
    now: Any
    #: One of the paths an install may never overlay, so the version's value is the only one.
    sealed: bool


class UpgradeView(BaseModel):
    """What is waiting for one agent, and what accepting it would do."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str
    #: `brain.agents.upgrade.UpgradeBadge`: current, available or declined.
    badge: str
    from_version: int
    #: The version on offer, or null when the agent is on the newest.
    to_version: int | None = None
    #: The configuration this review was read against. Send it back.
    expected_hash: str | None = None
    conflicts: list[UpgradeConflictView]
    updates: list[UpgradeChangeView]
    #: Why this cannot be accepted now, when it cannot. Declining is not affected.
    accept_unavailable: str | None = None
    #: Why there is nothing to review at all, for an agent with no install.
    nothing: str | None = None


class UpgradeAccepted(BaseModel):
    """The version and configuration the page drew, and the answer for every conflict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    to_version: int = Field(ge=1)
    expected_hash: str = Field(pattern=DIGEST)
    #: Every conflicting path, each keeping the local value or taking the version's. Never a merge.
    resolutions: dict[str, Literal["keep_local", "take_template"]] = Field(default_factory=dict)


class UpgradeDeclined(BaseModel):
    """The version and configuration the page drew."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    to_version: int = Field(ge=1)
    expected_hash: str = Field(pattern=DIGEST)


class UpgradeDone(BaseModel):
    """What accepting or declining did."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    #: `upgraded` or `declined`.
    outcome: str
    sentence: str
    from_version: int
    to_version: int
    #: Whether the agent was switched off because the new version leaves it incomplete here.
    switched_off: bool = False


# ------------------------------------------------------------------------------ the store
@dataclass(frozen=True)
class Reading:
    """One agent, its install, and what a review is built from: the shelf and the declines."""

    found: FoundAgent
    shelf: VersionShelf
    declines: Declines


@runtime_checkable
class AgentUpgrades(Protocol):
    """What these routes need of the tables. `StoredAgentUpgrades` implements it."""

    async def read(self, agent_id: str) -> Reading | None: ...

    async def accept(
        self,
        upgraded: Upgraded,
        *,
        from_version: int,
        expected_hash: str,
        disabled_at: datetime | None,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool: ...

    async def decline(
        self, made: Decline, *, actor_id: str, ent_hash: str, trace_id: str
    ) -> bool: ...


class _MovedError(Exception):
    """The row was not what the write was decided against. Rolls the transaction back."""


class StoredAgentUpgrades:
    """`AgentUpgrades` over the agent, install, version and decline tables."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def read(self, agent_id: str) -> Reading | None:
        from brain.prompt_routes import every_agent_with_install

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
            lineage = installed(instance_row, version_row)
            newest: TemplateVersionRow | None = None
            declined: list[UpgradeDeclineRow] = []
            if instance_row is not None:
                newest = (
                    await session.execute(
                        select(TemplateVersionRow)
                        .where(TemplateVersionRow.template_id == instance_row.template_id)
                        .order_by(TemplateVersionRow.version.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                declined = list(
                    (
                        await session.execute(
                            select(UpgradeDeclineRow).where(
                                UpgradeDeclineRow.instance_id == agent_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
        shelf, declines = VersionShelf(), Declines()
        if lineage is not None:
            shelf.publish(lineage[0])
            if newest is not None and newest.version > lineage[0].manifest.identity.version:
                try:
                    shelf.publish(signed_of(newest))
                except (KeyError, ValueError, TemplateError) as exc:
                    # A version that does not construct is not offered, as one that is not there.
                    log.warning(
                        "published version does not construct",
                        template=newest.template_id,
                        error=type(exc).__name__,
                    )
        for row in declined:
            declines.record(
                Decline(
                    instance_id=row.instance_id,
                    template_id=row.template_id,
                    version=row.version,
                    content_digest=row.content_digest,
                    declined_by=row.declined_by,
                    declined_at=row.declined_at,
                )
            )
        return Reading(
            found=FoundAgent(
                record=record,
                install=lineage,
                effective_hash=None if instance_row is None else instance_row.effective_hash,
            ),
            shelf=shelf,
            declines=declines,
        )

    async def accept(
        self,
        upgraded: Upgraded,
        *,
        from_version: int,
        expected_hash: str,
        disabled_at: datetime | None,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool:
        """Move the pin and the agent together, or write nothing and say so.

        A compare-and-set on the hash the page drew and the version the agent was on, so a row
        that moved between the read and this statement matches nothing. The agent row takes only
        the columns a manifest decides, `brain.builder.draft_store.CONFIGURATION_COLUMNS`.
        """
        instance = upgraded.instance
        agent_id = instance.instance_id
        try:
            async with self._sessions() as session, session.begin():
                for statement in attributed_to(
                    actor_id=actor_id, ent_hash=ent_hash, trace_id=trace_id
                ):
                    await session.execute(statement)
                pinned = (
                    await session.execute(
                        update(TemplateInstanceRow)
                        .where(
                            TemplateInstanceRow.id == agent_id,
                            TemplateInstanceRow.effective_hash == expected_hash,
                            TemplateInstanceRow.template_version == from_version,
                        )
                        .values(
                            template_id=instance.template_id,
                            template_version=instance.template_version,
                            content_digest=instance.content_digest,
                            overlay=dict(instance.overlay),
                            field_owners={
                                path: owner.model_dump(mode="json")
                                for path, owner in instance.overlay_owners.items()
                            },
                            effective_document=dict(upgraded.effective.document),
                            effective_hash=upgraded.effective.config_hash,
                        )
                        .returning(TemplateInstanceRow.id)
                    )
                ).scalar_one_or_none()
                if pinned is None:
                    raise _MovedError
                written = (
                    await session.execute(
                        update(AgentRow)
                        .where(AgentRow.id == agent_id, AgentRow.archived_at.is_(None))
                        .values(**_configuration(upgraded.record), disabled_at=disabled_at)
                        .returning(AgentRow.id)
                    )
                ).scalar_one_or_none()
                if written is None:
                    raise _MovedError
        except _MovedError:
            return False
        return True

    async def decline(self, made: Decline, *, actor_id: str, ent_hash: str, trace_id: str) -> bool:
        """Insert the decline, and say whether this wrote it or it was already there."""
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(actor_id=actor_id, ent_hash=ent_hash, trace_id=trace_id):
                await session.execute(statement)
            written = (
                await session.execute(
                    insert(UpgradeDeclineRow)
                    .values(
                        instance_id=made.instance_id,
                        template_id=made.template_id,
                        version=made.version,
                        content_digest=made.content_digest,
                        declined_by=made.declined_by,
                        declined_at=made.declined_at,
                    )
                    .on_conflict_do_nothing()
                    .returning(UpgradeDeclineRow.version)
                )
            ).scalar_one_or_none()
        return written is not None


def upgrades_of(request: Request) -> AgentUpgrades:
    """`app.state.agent_upgrades` when something put one there, and the database otherwise."""
    found = getattr(request.app.state, "agent_upgrades", None)
    if isinstance(found, AgentUpgrades):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredAgentUpgrades(factory)


# ------------------------------------------------------------------------ the decisions
router = APIRouter(prefix=API_PREFIX, tags=["agents"])

_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": NotChangedView, "description": "Nothing was changed, and why."},
}


def _no_agent_here(asked: Asking, reason: str) -> Absent:
    """The one refusal about an agent. The reason reaches a log and never a response."""
    log.info("agent upgrade not answerable", reason=reason, principal=asked.caller.principal.id)
    return Absent("no agent is answerable for this caller")


def _not_changed(outcome: str, sentence: str) -> JSONResponse:
    body = NotChangedView(outcome=outcome, sentence=sentence)
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def _tools(request: Request) -> ToolRegistry:
    from brain.agent_routes import _tool_registry

    tools = _tool_registry(request)
    if tools is None:
        raise Failed("no tool registry on this process")
    return tools


async def _actionable(
    request: Request, agent_id: str, asked: Asking
) -> tuple[AgentUpgrades, Reading]:
    """The agent, for a caller who holds the lifecycle authority over it and whose audience covers
    it, or the one 404. See `A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_REFUSAL_HERE_TOO`."""
    if asked.reach.scope_for(AGENT_LIFECYCLE_CAPABILITY, asked.now) is None:
        raise _no_agent_here(asked, "capability")
    store = upgrades_of(request)
    reading = await store.read(agent_id)
    if reading is None or not visible(reading.found.record, asked):
        raise _no_agent_here(asked, "agent")
    if not holds(AGENT_LIFECYCLE_CAPABILITY, reading.found.record, asked):
        raise _no_agent_here(asked, "scope")
    return store, reading


def _reviewed(reading: Reading) -> UpgradeReview | None:
    """The review of the agent's install, or None for an agent with none that constructs."""
    install = reading.found.install
    if install is None:
        return None
    try:
        return review(install[1], shelf=reading.shelf, declines=reading.declines)
    except TemplateError as refused:
        log.warning("agent upgrade does not review", error=type(refused).__name__)
        return None


def accept_unavailable(reviewed: UpgradeReview, record: AgentRecord, key: str | None) -> str | None:
    """Why this version cannot be accepted now, or None. Not asked of a decline."""
    if reviewed.candidate is None:
        return NOTHING_TO_UPGRADE
    if record.state is AgentState.ARCHIVED:
        return ARCHIVE_IS_TERMINAL
    if rungs_an_upgrade_would_raise(reviewed):
        return THIS_RAISES_A_RUNG
    if key is None:
        return NO_SIGNING_KEY_HERE
    return None


def _view(reading: Reading, key: str | None) -> UpgradeView:
    record = reading.found.record
    reviewed = _reviewed(reading)
    if reviewed is None:
        return UpgradeView(
            agent_id=record.agent_id,
            display_name=record.display_name,
            badge=UpgradeBadge.CURRENT.value,
            from_version=1,
            conflicts=[],
            updates=[],
            nothing=NO_INSTALL_TO_UPGRADE,
        )
    return UpgradeView(
        agent_id=record.agent_id,
        display_name=record.display_name,
        badge=reviewed.badge.value,
        from_version=reviewed.from_version,
        to_version=reviewed.to_version,
        expected_hash=reading.found.effective_hash,
        conflicts=[
            UpgradeConflictView(
                path=one.path,
                where=where(one.path),
                was=one.was,
                now=one.now,
                local=one.local,
                owner=UpgradeOwnerView(
                    source=one.owner.source.value, set_by=one.owner.set_by, set_at=one.owner.set_at
                ),
            )
            for one in reviewed.conflicts
        ],
        updates=[
            UpgradeChangeView(
                path=one.path, where=where(one.path), was=one.was, now=one.now, sealed=one.sealed
            )
            for one in reviewed.updates
        ],
        accept_unavailable=accept_unavailable(reviewed, record, key),
    )


@router.get(UPGRADE_PATH, response_model=UpgradeView, responses=COMMON_RESPONSES)
async def agent_upgrade(request: Request, agent_id: str, asked: Asked) -> UpgradeView:
    """What is waiting for one agent: the badge, what the version changes and what it asks."""
    _, reading = await _actionable(request, agent_id, asked)
    return _view(reading, template_key_of(request))


def _stale(reading: Reading, reviewed: UpgradeReview, to_version: int, expected: str) -> bool:
    """Whether the page was drawn against something other than what is there now."""
    return reading.found.effective_hash != expected or reviewed.to_version != to_version


@router.post(ACCEPT_PATH, response_model=UpgradeDone, responses=_TOLD)
async def accept_agent_upgrade(
    request: Request, agent_id: str, body: UpgradeAccepted, asked: Asked
) -> JSONResponse:
    """Move the agent to the version on offer, one conflicting path at a time.

    Refused, before anything is written, when the page is stale, when there is nothing on offer,
    when the agent is archived, when the version would raise a rung, when this process holds no
    signing key, when the answers do not cover the conflicts exactly, and when the settled agent
    reaches further than the agent did and the person accepting could not have written it.
    """
    store, reading = await _actionable(request, agent_id, asked)
    record = reading.found.record
    reviewed = _reviewed(reading)
    if reviewed is None or reviewed.candidate is None:
        return _not_changed(
            REFUSED, NO_INSTALL_TO_UPGRADE if reviewed is None else NOTHING_TO_UPGRADE
        )
    if _stale(reading, reviewed, body.to_version, body.expected_hash):
        return _not_changed(MOVED, IT_MOVED)
    key = template_key_of(request)
    unavailable = accept_unavailable(reviewed, record, key)
    if unavailable is not None:
        outcome = UNAVAILABLE if key is None and unavailable == NO_SIGNING_KEY_HERE else REFUSED
        return _not_changed(outcome, unavailable)
    me = asked.caller.principal.id
    try:
        upgraded = accept(
            reviewed,
            resolutions={path: Resolution(one) for path, one in body.resolutions.items()},
            key=key or "",
            audience=record.audience,
            registry=await connectors_of(request),
            tools=_tools(request),
            by=me,
            at=asked.now,
        )
    except TemplateError as refused:
        return _not_changed(REFUSED, str(refused))
    except ValueError:
        return _not_changed(REFUSED, DOES_NOT_SETTLE)
    reach = widenings(record, upgraded.record, now=asked.now)
    if reach:
        stopped = approval_refusal(
            author_id=reviewed.candidate.signed_by,
            approver_id=me,
            ceiling=ceiling_of(upgraded.record),
            approver_reach=asked.reach,
            now=asked.now,
        )
        if stopped is not None:
            return _not_changed(REFUSED, stopped)
    disabled_at = record.disabled_at
    switched_off = disabled_at is None and not upgraded.completeness.is_ready
    if switched_off:
        disabled_at = asked.now
    written = await store.accept(
        upgraded,
        from_version=reviewed.from_version,
        expected_hash=body.expected_hash,
        disabled_at=disabled_at,
        actor_id=me,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    )
    if not written:
        return _not_changed(MOVED, IT_MOVED)
    log.info(
        "agent upgraded",
        agent=agent_id,
        by=me,
        to=reviewed.to_version,
        switched_off=switched_off,
    )
    done = UpgradeDone(
        agent_id=agent_id,
        outcome="upgraded",
        sentence=WRITTEN_AND_SWITCHED_OFF if switched_off else WRITTEN,
        from_version=reviewed.from_version,
        to_version=body.to_version,
        switched_off=switched_off,
    )
    return JSONResponse(status_code=200, content=done.model_dump(mode="json"))


@router.post(DECLINE_PATH, response_model=UpgradeDone, responses=_TOLD)
async def decline_agent_upgrade(
    request: Request, agent_id: str, body: UpgradeDeclined, asked: Asked
) -> JSONResponse:
    """Say no to the version on offer, for good: the badge comes back for the next one only.

    Allowed whatever stops it being accepted, because a version that cannot be accepted is the one
    somebody most needs to be able to turn away.
    """
    store, reading = await _actionable(request, agent_id, asked)
    reviewed = _reviewed(reading)
    if reviewed is None or reviewed.candidate is None:
        return _not_changed(
            REFUSED, NO_INSTALL_TO_UPGRADE if reviewed is None else NOTHING_TO_UPGRADE
        )
    if _stale(reading, reviewed, body.to_version, body.expected_hash):
        return _not_changed(MOVED, IT_MOVED)
    me = asked.caller.principal.id
    try:
        made = decline(reviewed, declines=reading.declines, by=me, at=asked.now)
    except TemplateError as refused:
        return _not_changed(REFUSED, str(refused))
    await store.decline(made, actor_id=me, ent_hash=asked.reach.ent_hash(), trace_id=_trace_id())
    log.info("agent upgrade declined", agent=agent_id, by=me, version=made.version)
    done = UpgradeDone(
        agent_id=agent_id,
        outcome="declined",
        sentence=DECLINED,
        from_version=reviewed.from_version,
        to_version=made.version,
    )
    return JSONResponse(status_code=200, content=done.model_dump(mode="json"))
