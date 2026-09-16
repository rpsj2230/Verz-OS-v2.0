"""The Prompts screen over HTTP: the instructions every agent is given, and the one edit that can
be real.

There are two kinds of instruction in this product and they are not the same kind of thing.
**The system instructions are product text.** `brain.gate.prefix.HOUSE_RULES` opens every prompt
and restates the rules the platform is built on, never saying that something was withheld and
never counting what was not shown, and `brain.gate.effort.OUTPUT_LENGTHS` says how long an answer
may be. An install that could edit the first could instruct its model to narrate around the
redactor, which is the one leak `brain.gate.prefix` says enforcement cannot close, so both are
shown and neither is editable. See
`THE_SYSTEM_INSTRUCTIONS_ARE_THE_PRODUCTS_AND_ARE_SHOWN_NOT_EDITED`.

**An agent's instructions are its persona, and they are versioned the way the product already
versions an agent.** Every agent is an install of a signed template (`brain.agents.template`; a
hand-built one installs the blank template), the template's persona is the signed text at a
version, and an install's own change is an overlay path owned by whoever set it and when. So an
edit here is `set_field(instance, "persona", ...)`, the effective agent is `materialise`d from the
pin and the overlay, and the row is written with the effective document and its hash together, as
`EffectiveAgent` says the two cached columns must be. Giving the instructions back is
`clear_field`. Nothing new is invented: a local edit is recorded as a divergence from the template
rather than lost at the next upgrade, which is what SCREEN 5 of `docs/screens.html` draws.

**What an agent is given changes, and the answer proves it with the hash the answer cache keys
on.** `brain.gate.prefix.build_prefix` is where a persona enters a prompt, and it takes the
effective agent's persona; the edit is validated by calling it, so a persona `build_prefix` would
refuse is refused here rather than at the first run. `effective_hash` is
`brain.agents.template.config_hash`, the `agent_config_hash` in `brain.gate.cache_key`, so an
answer cached under the old instructions is never served under the new ones. **What does not
exist yet is said on the answer:** nothing in this repository sends a prompt to a model, so the
instructions change what a run would be given rather than an answer anybody has received.

**Who may see and who may edit, and none of it decided here.** An agent is listed when its
audience covers the reader (`brain.agents.model.visible_agent_ids`) and the reader may open an
agent's Settings tab (`brain.console.workspace.tab`), which are the two questions the agent
workspace asks before it shows the same composition. Editing adds `admin:agent_instructions` in a
scope matching the agent's row, through `brain.console.govern._in_reach`, so a department's
administrator may be granted their department's agents and no others. Every refusal to a caller
who may not edit is one refusal, identical for an agent that does not exist.

**Editing is behind the `prompt_editing` feature and giving back is not**, on
`brain.ops.features.A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED`.

**Two administrators cannot overwrite each other in silence.** An edit names the effective hash
the editor was shown, and the row is read under a lock and refused when the hash has moved.

**Recorded on the install, and in the ledger.** The overlay's owner is who set the persona and
when, and the previous override is replaced; `0059`'s trigger on `agent.template_instance` appends
an `instructions` entry about the agent for every edit and every give-back, with the digest of the
configuration put in force and never the text. `AuditAction.PUBLISH` is the builder's for a
published version, and `COMPOSE_CHANGE` is an attachment added or removed, and neither is this,
which `brain.audit.ledger.AuditAction` argues. A give-back removes the overlay's owner, so the row
no longer says who gave the instructions back: the route sets who, at what reach and for which
request in the transaction before it writes, and the trigger reads them.

Task ids: M27.8.9
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final, cast

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_routes import manifest_of, record_of, viewer_of
from brain.agents.model import PERSONA_CHARS, AgentRecord, visible_agent_ids
from brain.agents.template import (
    FieldOwner,
    SignedManifest,
    TemplateError,
    TemplateInstance,
    clear_field,
    materialise,
    ownership,
    set_field,
)
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.console.govern import _in_reach
from brain.console.reads import permitted
from brain.console.workspace import Tab, tab
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.gate.effort import OUTPUT_LENGTHS
from brain.gate.prefix import HOUSE_RULES, UnshareablePrefixError, build_prefix
from brain.ops.features import PROMPT_EDITING, is_on
from brain.routing_routes import sessions_of
from brain.tables.agent import AgentRow
from brain.tables.audit import attributed_to
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: Why the house rules are shown and never edited.
THE_SYSTEM_INSTRUCTIONS_ARE_THE_PRODUCTS_AND_ARE_SHOWN_NOT_EDITED: Final = (
    "The house rules tell every model never to say that something was withheld and never to "
    "count what it was not shown. The redactor enforces both, and the rules exist because a "
    "model narrating around a guard is the one leak enforcement cannot close. An install that "
    "could edit them could remove that sentence from every prompt at once, so they are product "
    "text: identical on every install, shown so an administrator knows what every agent is "
    "told, and changed only by a release."
)

# ------------------------------------------------------------------------ the figures
#: Edits an agent's instructions, in a scope matching the agent.
INSTRUCTIONS_AUTHORITY: Final = Capability(value="admin:agent_instructions")

#: The manifest path an agent's instructions are.
PERSONA_PATH: Final = "persona"

#: The screen's word in a refusal, identical on every install.
PROMPTS_SCREEN: Final = "prompts"


# ------------------------------------------------------------------------ the shapes
class OutputLengthView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    instruction: str


class AgentInstructionsView(BaseModel):
    """One agent's instructions: the template's, this install's, and who set what is in force."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str
    department: str | None
    #: The instructions in force, which is what `build_prefix` is given.
    instructions: str
    #: Null when the agent has no install record that constructs; see `installed`.
    template_id: str | None
    template_version: int | None
    template_instructions: str | None
    #: True when this install replaced the template's instructions.
    overridden: bool
    #: Who set the instructions in force and when: this install's editor, or the template's signer.
    set_by: str | None
    set_at: datetime | None
    #: The hash an edit must name. `brain.agents.template.config_hash`, which the cache keys on.
    effective_hash: str | None
    #: False for an agent whose install record is missing or does not construct.
    installed: bool
    #: Presentation only: the edit route asks every question again.
    editable: bool


class PromptsPage(BaseModel):
    """The system instructions, and every agent's instructions this reader may see."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    house_rules: list[str]
    output_lengths: list[OutputLengthView]
    agents: list[AgentInstructionsView]
    max_chars: int
    editing_switched_on: bool
    #: The house rules and output lengths are product text. See the reason constant.
    system_instructions_are_product_text: bool = True
    #: Nothing in the product sends a prompt to a model yet.
    no_model_is_called_yet: bool = True
    #: The install keeps the current override and who set it, and every edit and give-back is an
    #: entry in the audit trail, from `0059`'s trigger.
    every_change_is_in_the_audit_trail: bool = True


class InstructionsEdit(BaseModel):
    """Replace an agent's instructions. The hash is the one the editor was shown."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    instructions: str = Field(max_length=PERSONA_CHARS * 2)
    expected_hash: str = Field(min_length=1, max_length=128)


class InstructionsGiveBack(BaseModel):
    """Give an agent's instructions back to its template."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected_hash: str = Field(min_length=1, max_length=128)


# ---------------------------------------------------------------- the statements
#: One agent and, from the outer joins, its install and pinned version or None for each.
AgentWithInstall = tuple[AgentRow, TemplateInstanceRow | None, TemplateVersionRow | None]


def every_agent_with_install() -> Select[AgentWithInstall]:
    """Every agent with its install and the version it pins, when it has one."""
    # Cast at a library boundary: an outer join's right side is None for an agent with no
    # install, and SQLAlchemy types the selected entities as present whatever the join.
    return cast(
        "Select[AgentWithInstall]",
        select(AgentRow, TemplateInstanceRow, TemplateVersionRow)
        .outerjoin(TemplateInstanceRow, TemplateInstanceRow.id == AgentRow.id)
        .outerjoin(
            TemplateVersionRow,
            and_(
                TemplateVersionRow.template_id == TemplateInstanceRow.template_id,
                TemplateVersionRow.version == TemplateInstanceRow.template_version,
            ),
        )
        .order_by(AgentRow.id),
    )


#: Why the install is locked by a statement of its own before the agent is read with it.
THE_INSTALL_IS_LOCKED_BEFORE_IT_IS_READ: Final = (
    "The install is the nullable side of the outer join that reads an agent with it, and "
    "PostgreSQL refuses FOR UPDATE on the nullable side of an outer join, so locking both in the "
    "joined read failed every edit and every give-back on a real database while every stub test "
    "passed. Locking the agent alone in the join would not do instead: a read that waited for the "
    "agent's lock re-reads the agent and not the install joined to it, so a second editor would "
    "compare their hash with the install as it was before the first edit and overwrite it in "
    "silence. So the install row is locked first, and the joined read that follows is a new "
    "statement that sees whatever the edit it waited for committed."
)


def one_install_locked(agent_id: str) -> Select[tuple[str]]:
    """The install row for one agent, locked. See `THE_INSTALL_IS_LOCKED_BEFORE_IT_IS_READ`."""
    return (
        select(TemplateInstanceRow.id).where(TemplateInstanceRow.id == agent_id).with_for_update()
    )


def one_agent_locked(agent_id: str) -> Select[AgentWithInstall]:
    """One agent, its install and its version, with the agent row locked.

    Only the agent row, and the install is already held by `one_install_locked`: see
    `THE_INSTALL_IS_LOCKED_BEFORE_IT_IS_READ` for why the join cannot lock it.
    """
    return every_agent_with_install().where(AgentRow.id == agent_id).with_for_update(of=AgentRow)


def write_install(agent_id: str, row: Mapping[str, Any]) -> Any:
    """The install's overlay, owners and cached effective document, written together."""
    return (
        update(TemplateInstanceRow)
        .where(TemplateInstanceRow.id == agent_id)
        .values(
            overlay=row["overlay"],
            field_owners=row["field_owners"],
            effective_document=row["effective_document"],
            effective_hash=row["effective_hash"],
        )
    )


def write_persona(agent_id: str, persona: str) -> Any:
    """The agent row's copy of the persona, kept equal to the effective one."""
    return update(AgentRow).where(AgentRow.id == agent_id).values(persona=persona)


# ---------------------------------------------------------------- the domain
def signed_of(version: TemplateVersionRow) -> SignedManifest:
    """The signed manifest a version row holds. `SignedManifest` rechecks the digest."""
    return SignedManifest(
        manifest=manifest_of(version.document),
        content_digest=version.content_digest,
        signature=version.signature,
        signed_by=version.signed_by,
        signed_at=version.signed_at,
    )


def instance_of(row: TemplateInstanceRow) -> TemplateInstance:
    """The install an instance row holds, as `brain.agent_routes.install_of` builds it."""
    return TemplateInstance(
        instance_id=row.id,
        template_id=row.template_id,
        template_version=row.template_version,
        content_digest=row.content_digest,
        overlay=row.overlay,
        overlay_owners={
            path: FieldOwner.model_validate(owner) for path, owner in row.field_owners.items()
        },
        created_by=row.created_by,
    )


def installed(
    instance_row: TemplateInstanceRow | None, version_row: TemplateVersionRow | None
) -> tuple[SignedManifest, TemplateInstance] | None:
    """The signed manifest and install, or None when either is missing or does not construct."""
    if instance_row is None or version_row is None:
        return None
    try:
        return signed_of(version_row), instance_of(instance_row)
    except (KeyError, ValueError, TemplateError):
        return None


def agent_scope_row(record: AgentRecord) -> dict[str, str]:
    """The fields an instructions grant's scope may be written against.

    The agent and, for a department's agent, the department. The department is left out rather
    than blank for any other agent, so a grant scoped to a department fails closed on a company
    agent: `brain.console.operate._unattended_row` makes the same choice about a person.
    """
    row = {"agent_id": record.agent_id}
    if record.audience.department:
        row["department"] = record.audience.department
    return row


def may_read_settings(reach: EntitlementSet, now: datetime) -> bool:
    """The agent workspace's own question for the Settings tab, where the composition is shown."""
    return permitted(tab(Tab.SETTINGS).read, reach, now)


def may_edit(record: AgentRecord, reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach holds the instructions authority in a scope admitting this agent."""
    return _in_reach(reach, INSTRUCTIONS_AUTHORITY, agent_scope_row(record), now)


def instructions_view(
    record: AgentRecord,
    install: tuple[SignedManifest, TemplateInstance] | None,
    *,
    effective_hash: str | None,
    editable: bool,
) -> AgentInstructionsView:
    """One agent's instructions. When the install constructs, what is in force is the
    materialised persona; when it does not, the row's own copy, and nothing is editable."""
    if install is not None:
        signed, instance = install
        try:
            effective = materialise(signed, instance, audience=record.audience)
        except (ValueError, TemplateError):
            install = None
        else:
            owner = ownership(signed, instance)[PERSONA_PATH]
            return AgentInstructionsView(
                agent_id=record.agent_id,
                display_name=record.display_name,
                department=record.audience.department or None,
                instructions=effective.record.persona,
                template_id=instance.template_id,
                template_version=instance.template_version,
                template_instructions=signed.manifest.persona,
                overridden=PERSONA_PATH in instance.overlay,
                set_by=owner.set_by,
                set_at=owner.set_at,
                effective_hash=effective_hash,
                installed=True,
                editable=editable,
            )
    return AgentInstructionsView(
        agent_id=record.agent_id,
        display_name=record.display_name,
        department=record.audience.department or None,
        instructions=record.persona,
        template_id=None,
        template_version=None,
        template_instructions=None,
        overridden=False,
        set_by=None,
        set_at=None,
        effective_hash=None,
        installed=False,
        editable=False,
    )


def instruction_refusal(text: str, current: str) -> str:
    """Why this text cannot be an agent's instructions, or empty when it can.

    The prompt builder's own check is called rather than restated, so what is refused here is
    exactly what `build_prefix` would refuse at the first run.
    """
    wanted = text.strip()
    if not wanted:
        return "instructions cannot be empty; give the agent back to its template instead"
    if len(wanted) > PERSONA_CHARS:
        return f"instructions are at most {PERSONA_CHARS} characters, and these are {len(wanted)}"
    if wanted == current.strip():
        return "these are the instructions already in force"
    try:
        build_prefix((), persona=wanted)
    except UnshareablePrefixError as refused:
        return str(refused).split(". ", 1)[0]
    return ""


def written(
    signed: SignedManifest, instance: TemplateInstance, record: AgentRecord
) -> tuple[dict[str, Any], str, str]:
    """The install row to write, the persona in force, and the new hash, from one materialise."""
    effective = materialise(signed, instance, audience=record.audience)
    row = {
        "overlay": dict(instance.overlay),
        "field_owners": {
            path: owner.model_dump(mode="json") for path, owner in instance.overlay_owners.items()
        },
        "effective_document": dict(effective.document),
        "effective_hash": effective.config_hash,
    }
    return row, effective.record.persona, effective.config_hash


# ------------------------------------------------------------------------ the wiring
def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _not_editable() -> Absent:
    """The one refusal a caller who may not edit this agent gets, whatever the reason."""
    return Absent("those instructions are not editable by this caller")


def _refused_because(reason: str) -> Absent:
    """A refusal for a caller who may edit this agent, naming what to fix."""
    message = f"those instructions were not changed: {reason}"
    return Absent(message, public_message=message)


#: What a caller who may edit is told when the feature is off.
SWITCHED_OFF: Final = (
    "editing instructions from the console is switched off on this install, and an "
    "administrator switches it on under Install, Features"
)


router = APIRouter(prefix=API_PREFIX, tags=["govern"])


@router.get("/govern/prompts", response_model=PromptsPage, responses=COMMON_RESPONSES)
async def prompts(request: Request, asked: Asked) -> PromptsPage:
    """The system instructions, and every agent's instructions this reader may see.

    The agents are read for everybody and narrowed by audience and by the Settings tab, in that
    order, so a reader who may see no agent's settings is answered the list an install with no
    agents is answered.
    """
    factory = _require_sessions(request)
    async with factory() as session:
        rows = (await session.execute(every_agent_with_install())).all()
        switched_on = await is_on(session, PROMPT_EDITING)
    viewer = viewer_of(asked)
    settings = may_read_settings(asked.reach, asked.now)
    agents: list[AgentInstructionsView] = []
    for agent_row, instance_row, version_row in rows:
        record = record_of(agent_row)
        if record is None or not settings:
            continue
        if record.agent_id not in visible_agent_ids((record,), viewer):
            continue
        install = installed(instance_row, version_row)
        agents.append(
            instructions_view(
                record,
                install,
                effective_hash=instance_row.effective_hash if instance_row is not None else None,
                editable=switched_on and may_edit(record, asked.reach, asked.now),
            )
        )
    return PromptsPage(
        house_rules=list(HOUSE_RULES),
        output_lengths=[
            OutputLengthView(name=one.name, instruction=one.instruction) for one in OUTPUT_LENGTHS
        ],
        agents=agents,
        max_chars=PERSONA_CHARS,
        editing_switched_on=switched_on,
    )


async def _editable_install(
    session: AsyncSession, agent_id: str, asked: Asking, expected_hash: str
) -> tuple[AgentRecord, SignedManifest, TemplateInstance]:
    """The locked agent and its install, for a caller who may edit it, or a refusal.

    Every reason a caller may not edit is one refusal. A caller who may is told when the agent has
    no install, and when somebody else changed it since they opened it.
    """
    await session.execute(one_install_locked(agent_id))
    found = (await session.execute(one_agent_locked(agent_id))).one_or_none()
    record = record_of(found[0]) if found is not None else None
    if (
        found is None
        or record is None
        or record.agent_id not in visible_agent_ids((record,), viewer_of(asked))
        or not may_edit(record, asked.reach, asked.now)
    ):
        log.info("instructions not editable", principal=asked.caller.principal.id)
        raise _not_editable()
    install = installed(found[1], found[2])
    if install is None:
        raise _refused_because(
            "this agent has no install record that constructs, so its instructions have no "
            "template to be recorded against"
        )
    if found[1].effective_hash != expected_hash:
        raise _refused_because(
            "somebody changed this agent after you opened it; reload to see what is in force"
        )
    return record, install[0], install[1]


async def _attribute(session: AsyncSession, asked: Asking) -> None:
    """Who is changing the instructions, at what reach, for which request, for `0059`'s trigger.

    A give-back leaves no owner on the row to name, so without these the entry would be attributed
    to the database role and marked inferred.
    """
    trace_id = str(structlog.contextvars.get_contextvars().get("trace_id", ""))
    for statement in attributed_to(
        actor_id=asked.caller.principal.id, ent_hash=asked.reach.ent_hash(), trace_id=trace_id
    ):
        await session.execute(statement)


def _asked_to_edit(asked: Asking) -> None:
    """The two questions that need no row, asked before the database."""
    if asked.reach.scope_for(INSTRUCTIONS_AUTHORITY, asked.now) is None or not may_read_settings(
        asked.reach, asked.now
    ):
        log.info("instructions not editable", principal=asked.caller.principal.id)
        raise _not_editable()


@router.post(
    "/govern/prompts/{agent_id}", response_model=AgentInstructionsView, responses=COMMON_RESPONSES
)
async def edit_instructions(
    request: Request, agent_id: str, body: InstructionsEdit, asked: Asked
) -> AgentInstructionsView:
    """Replace one agent's instructions with a local change recorded against its template."""
    _asked_to_edit(asked)
    async with _require_sessions(request)() as session:
        try:
            record, signed, instance = await _editable_install(
                session, agent_id, asked, body.expected_hash
            )
            if not await is_on(session, PROMPT_EDITING):
                raise _refused_because(SWITCHED_OFF)
            current = materialise(signed, instance, audience=record.audience).record.persona
            refusal = instruction_refusal(body.instructions, current)
            if refusal:
                raise _refused_because(refusal)
            changed = set_field(
                instance,
                PERSONA_PATH,
                body.instructions.strip(),
                by=asked.caller.principal.id,
                at=asked.now,
            )
            row, persona, new_hash = written(signed, changed, record)
        except (ValueError, TemplateError):
            await session.rollback()
            raise _refused_because("the agent's install refused them") from None
        except Absent:
            await session.rollback()
            raise
        await _attribute(session, asked)
        await session.execute(write_install(agent_id, row))
        await session.execute(write_persona(agent_id, persona))
        await session.commit()
    log.info("instructions edited", agent=agent_id, principal=asked.caller.principal.id)
    return instructions_view(record, (signed, changed), effective_hash=new_hash, editable=True)


@router.post(
    "/govern/prompts/{agent_id}/give-back",
    response_model=AgentInstructionsView,
    responses=COMMON_RESPONSES,
)
async def give_back_instructions(
    request: Request, agent_id: str, body: InstructionsGiveBack, asked: Asked
) -> AgentInstructionsView:
    """Give one agent's instructions back to its template. Not behind the feature switch."""
    _asked_to_edit(asked)
    async with _require_sessions(request)() as session:
        try:
            record, signed, instance = await _editable_install(
                session, agent_id, asked, body.expected_hash
            )
            if PERSONA_PATH not in instance.overlay:
                raise _refused_because("this agent already uses its template's instructions")
            changed = clear_field(instance, PERSONA_PATH)
            row, persona, new_hash = written(signed, changed, record)
        except (ValueError, TemplateError):
            await session.rollback()
            raise _refused_because("the install refused the template's instructions") from None
        except Absent:
            await session.rollback()
            raise
        # Read for the answer's `editable` and never as a gate: see the module docstring.
        switched_on = await is_on(session, PROMPT_EDITING)
        await _attribute(session, asked)
        await session.execute(write_install(agent_id, row))
        await session.execute(write_persona(agent_id, persona))
        await session.commit()
    log.info("instructions given back", agent=agent_id, principal=asked.caller.principal.id)
    return instructions_view(
        record, (signed, changed), effective_hash=new_hash, editable=switched_on
    )
