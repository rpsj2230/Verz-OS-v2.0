"""The Settings screen over HTTP: every installation value, where it came from, and branding saved.

`brain.console.configuration` decides what the screen shows and what may be written; this is the
read, the one write, and the starter set the install was furnished with. The owner asked to see
branding, the identity provider, the model profile and the storage locations with their current
values, never a secret, each saying whether a change needs a restart.

**One authority for the read and the write, held over everything.** `admin:install_setting` is
asked through `brain.console.govern._in_reach` at `brain.console.govern.NOWHERE` before anything is
read, which is `brain.feature_routes`' shape and its argument: an installation value is the whole
company's, there is no department's version of the company name, and a `read:` capability for a
list whose only readers can change it would be a screen the first administrator, who holds every
`admin:` capability and no `read:` one, could not open. It is an `admin:` verb, so
`brain.gate.admission` already withholds it from a password-only session and from every channel
but the console.

**A save is written to `ops.setting` and held by this process in the same request.** The row goes
through `brain.ops.install_settings.save`, the wizard's own writer, inside the audit attribution
`brain.tables.audit.attributed_to` sets, so `0059`'s trigger records who changed the value and
under which request. After the commit the saved values are re-read and handed to
`brain.install.hold_saved`, which is what `brain.install.value_of` resolves first, so the next page
this process serves draws the new name. Another application process reads it when it next
starts, and the row says so. See
`brain.ops.install_settings.A_SAVED_SETTING_IS_NOT_A_MESSAGE_TO_ANOTHER_WORKER`.

**Every setting safe to change while the install runs is written, each by its own rule, and a
refusal says why in the product's words** (branding alone until 2026-09-28). A name that is not a
declared setting and a setting this screen does not change are refused with the same sentence
`brain.console.configuration.setting_problem` gives, which names no value this install holds: the
declared names are product text, identical on every install. The console confirms each save
before sending it; this route judges it whatever the console did.

**A saved value is taken back with its own act, "return to default"** (needs-rupash gap (e),
2026-09-29). Until then the only way back was to type the default, which saves a row equal to it
and so goes on outranking the environment. The act retires the saved row through
`brain.ops.install_settings.retire`, attributed as a save is, so `0059`'s trigger records `retired`
against the person who pressed it; the setting then reads the environment's value or the declared
default, and each row says in advance which (`without_saved`). It is offered for exactly the
settings the screen changes, and refused with `setting_problem`'s sentence for any other name.

**The starter set is shown with the one thing it does not furnish, stated exactly.** Roles, the
starter pack and the company scope are furnished at every start by `brain.ops.starter_store`. The
standard agents are not installed, because an agent is an install of a signed template somebody
chooses; the built-in templates are signed with the key M13.8.10 mints at every start that holds
it (`brain.ops.builtin_templates`) and offered; the sentence is
`brain.ops.starter_store.NO_TEMPLATE_IS_SIGNED_BEFORE_THE_INSTALL_HOLDS_A_KEY_OF_ITS_OWN`.

**Leaving is on the same screen, because it is the same authority.** The handover of this install
(export everything, remove every part, certify) is carried out by `brain.ops.handover_run` on the
server, not from a browser: a button that drops every schema is one misclick from the end of the
company's data. The screen shows what that command would export and remove, who removes each part
and how, and the retention that sets the certificate's backup date, so an owner can read the
procedure before anybody runs it.

Task ids: M41.1.4, M41.1.5, M41.1.6, M41.1.7, M41.2.6, M41.4.1, M27.12.7
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody
from brain.api_routes import Asked
from brain.console.configuration import (
    SECTION_ORDER,
    SECTION_TITLES,
    THE_SCREEN_SHOWS_NO_CREDENTIAL,
    WHAT_IS_CHANGED_HERE_AND_WHAT_IS_NOT,
    Row,
    default_problem,
    findings,
    normalised,
    profile_told,
    rows,
    setting_problem,
)
from brain.console.govern import NOWHERE, _in_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.install import hold_saved, value_of
from brain.knowledge.embed_policy import REVISION_SETTING, embedding_revision
from brain.knowledge.embedding import EmbeddingError
from brain.ops.features import is_on
from brain.ops.features_declared.model_server import MODEL_SERVER
from brain.ops.handover import Residue
from brain.ops.handover_run import preview_steps
from brain.ops.install_settings import load, retire, save
from brain.ops.model_server import SETTINGS as MODEL_SERVER_SETTINGS
from brain.ops.model_server import (
    ModelServerConfig,
    ModelServerError,
    Part,
    config_from,
    read_config,
    requirement,
)
from brain.ops.model_server_client import held_embedding_revision, server_readiness
from brain.ops.model_server_peaks import PeakSummary, suggested_overall_mib, summarise
from brain.ops.model_server_store import recorded_peaks
from brain.ops.overlays import SERVICES_SETTING, memory_problem, runtime_problem
from brain.ops.retention import BACKUP_RETENTION_DAYS, facts_for
from brain.ops.setting_store import read_namespace
from brain.ops.starter import COMPANY_SCOPE, PACKS, agents, roles
from brain.ops.starter_store import (
    FURNISHED_KEY,
    NO_TEMPLATE_IS_SIGNED_BEFORE_THE_INSTALL_HOLDS_A_KEY_OF_ITS_OWN,
)
from brain.routing_routes import sessions_of
from brain.tables.audit import attributed_to

log = structlog.get_logger()

#: Reads the Settings screen and saves a branding value. Held over everything or not at all.
INSTALL_SETTING_AUTHORITY: Final = Capability(value="admin:install_setting")

#: The screen's name in a refusal. The console's own menu word, identical on every install.
SETTINGS_SCREEN: Final = "settings"

#: Where the screen is read, and where one value is saved.
SETTINGS_PATH: Final = "/install/settings"

#: Said when there is no saved value to take away. Names the setting's own label only.
NOTHING_SAVED_HERE: Final = (
    "Nothing is saved for this setting on this screen, so it already reads its default."
)

#: Why the standard agents are not on a freshly furnished install: they are offered, signed with
#: the key M13.8.10 mints, and installed only when somebody chooses one.
STANDARD_AGENTS_WAIT_FOR_THE_SIGNING_KEY: Final = (
    "The standard agents are not installed. An agent is an install of a signed template that "
    "somebody chooses; the built-in templates are signed with this install's key at start and "
    "offered in the gallery. " + NO_TEMPLATE_IS_SIGNED_BEFORE_THE_INSTALL_HOLDS_A_KEY_OF_ITS_OWN
)


def may_configure(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may read the Settings screen and save branding: the authority, over
    everything."""
    return _in_reach(reach, INSTALL_SETTING_AUTHORITY, NOWHERE, now)


# ------------------------------------------------------------------------------ the shapes


class SettingRowView(BaseModel):
    """One installation setting as the screen draws it. Never a credential."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    #: The setting as a person calls it; `name` is the variable, drawn beside it for support.
    label: str
    meaning: str
    value: str
    #: `saved`, `environment`, `default` or `missing`.
    source: str
    default: str
    required: bool
    editable: bool
    #: Why this screen does not change it, in one line. Empty for a setting it changes.
    read_only_because: str
    #: When a change to this value takes effect, in a sentence.
    applies: str
    #: The modules that read it, as dotted paths.
    read_by: list[str]
    #: What it reads once the saved value is taken away, and where that comes from.
    without_saved: str
    without_saved_source: str


class SettingGroupView(BaseModel):
    """One section of settings, by what they are for, and whether any of them is changed here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: A `brain.console.configuration.Section` value.
    group: str
    title: str
    #: Whether any setting in it is changed on this screen. Each row says so for itself.
    editable: bool
    settings: list[SettingRowView]


class StarterView(BaseModel):
    """What a new install is furnished with, and the part it is not."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    roles: list[str]
    packs: list[str]
    scopes: list[str]
    #: Whether the furnishing's record is in the database, or null with no database.
    furnished: bool | None
    #: The template ids the catalogue ships, none of which is installed.
    agent_templates: list[str]
    agents_installed: bool
    agents_told: str


#: Where the handover procedure is written, and the command that carries it out.
HANDOVER_PROCEDURE: Final = "docs/install/handover.md"
HANDOVER_COMMANDS: Final = (
    "python -m brain.ops.handover_run export <dir> --handover-id <id> --reason <reason> "
    "--instructed-by <who> --instruction-reference <where>",
    "python -m brain.ops.handover_run plan <dir>",
    "python -m brain.ops.handover_run remove <dir> --confirm <id>",
    "python -m brain.ops.handover_run record <dir> <part>",
    "python -m brain.ops.handover_run certify <dir>",
)
LEAVING_TOLD: Final = (
    "A company that leaves takes every store and the audit ledger as CSV and files, with a "
    "manifest and SHA256SUMS it can check, and the install is then removed part by part. The "
    "command runs on the server, never from this screen, and refuses to remove anything until "
    "the export has reached every store and still verifies."
)


class LeavingStepView(BaseModel):
    """One store or install part a handover removes, who removes it, and how."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    what: str
    #: `store` for where data rests, `part` for what the install leaves outside the database.
    kind: str
    #: What a store holds, in a line. Empty for a part.
    holds: str
    #: `command` or `operator`.
    by: str
    how: str


class LeavingView(BaseModel):
    """The handover of this install as the Settings screen describes it before anyone runs it."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    told: str
    steps: list[LeavingStepView]
    #: Days a backup is kept, which is how far past removal the certificate's date falls.
    backup_retention_days: int
    procedure: str
    commands: list[str]


def leaving_view(*, realm: str) -> LeavingView:
    return LeavingView(
        told=LEAVING_TOLD,
        steps=[
            LeavingStepView(
                what=one.what.value,
                kind="part" if isinstance(one.what, Residue) else "store",
                holds="" if isinstance(one.what, Residue) else facts_for(one.what).holds,
                by=one.by.value,
                how=one.how,
            )
            for one in preview_steps(realm=realm)
        ],
        backup_retention_days=BACKUP_RETENTION_DAYS,
        procedure=HANDOVER_PROCEDURE,
        commands=list(HANDOVER_COMMANDS),
    )


class SettingsPage(BaseModel):
    """The Settings screen."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    groups: list[SettingGroupView]
    #: Inconsistencies an owner can act on, in sentences. Empty when there are none.
    findings: list[str]
    #: Where text may go under the current model profile.
    profile: str
    starter: StarterView
    credentials: str
    editable_because: str
    leaving: LeavingView


class SaveAsked(BaseModel):
    """One setting's value. Required, so what is saved is what the person typed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str


# ------------------------------------------------------------------------------ the decisions


def row_view(one: Row) -> SettingRowView:
    return SettingRowView(
        name=one.name,
        label=one.label,
        meaning=one.meaning,
        value=one.value,
        source=one.source.value,
        default=one.default,
        required=one.required,
        editable=one.editable,
        read_only_because=one.read_only_because,
        applies=one.applies,
        read_by=list(one.read_by),
        without_saved=one.without_saved,
        without_saved_source=one.without_saved_source.value,
    )


def settings_page(*, furnished: bool | None, saved: dict[str, str] | None = None) -> SettingsPage:
    """The screen, from the declaration, this process's environment and the values saved.

    `saved` defaults to what this process holds, which is what every reader resolves against, so
    the screen shows the value a page served now would draw.
    """
    resolved_rows = rows(saved=saved)
    groups = [
        SettingGroupView(
            group=section.value,
            title=SECTION_TITLES[section],
            editable=any(one.editable for one in resolved_rows if one.section is section),
            settings=[row_view(one) for one in resolved_rows if one.section is section],
        )
        for section in SECTION_ORDER
    ]
    return SettingsPage(
        groups=groups,
        findings=list(findings(saved=saved)),
        profile=profile_told(saved=saved),
        starter=StarterView(
            roles=[one.value for one in roles()],
            packs=[one.slug for one in PACKS],
            scopes=[COMPANY_SCOPE.slug],
            furnished=furnished,
            agent_templates=list(agents()),
            agents_installed=False,
            agents_told=STANDARD_AGENTS_WAIT_FOR_THE_SIGNING_KEY,
        ),
        credentials=THE_SCREEN_SHOWS_NO_CREDENTIAL,
        editable_because=WHAT_IS_CHANGED_HERE_AND_WHAT_IS_NOT,
        leaving=leaving_view(realm=value_of("INSTALL_OIDC_REALM", saved=saved)),
    )


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def _not_answerable() -> Absent:
    """The one refusal a caller without the authority gets. Names the screen and nothing else."""
    return Absent(f"the {SETTINGS_SCREEN} screen is not answerable for this caller")


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


async def _furnished(session: AsyncSession) -> bool:
    namespace = FURNISHED_KEY.partition(".")[0]
    return FURNISHED_KEY in await read_namespace(session, namespace)


# ------------------------------------------------------------------------------ the routes

router = APIRouter(prefix=API_PREFIX, tags=["install"])


@router.get(SETTINGS_PATH, response_model=SettingsPage, responses=COMMON_RESPONSES)
async def settings(request: Request, asked: Asked) -> SettingsPage:
    """Every installation value and where it came from, for a caller who may change branding.

    The authority first. With no database the screen still answers from the environment and says
    the furnishing is unknown, because the values a process resolves do not need one.
    """
    if not may_configure(asked.reach, asked.now):
        log.info("settings screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    factory = sessions_of(request)
    furnished: bool | None = None
    if factory is not None:
        async with factory() as session:
            furnished = await _furnished(session)
    return settings_page(furnished=furnished)


class MeasuredPartView(BaseModel):
    """What the ring says about one part of the model server: its largest batch and the limit it
    suggests. A measurement of something that ran, and never a figure somebody reckoned."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    part: str
    batches: int
    largest_anonymous_mib: int
    largest_total_mib: int
    suggested_limit_mib: int | None


class ModelServerPage(BaseModel):
    """The model server as this install chose it, what that costs, and what has been measured."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The `model_server` feature, which says whether documents and passages are sent at all.
    switched_on: bool
    parts: list[str]
    idle_seconds: int
    upload_mb: int
    #: The limit the plan costs and the container starts with, and whether it is worked out.
    limit_mib: int
    worked_out: bool
    worked_out_limit_mib: int
    #: What the host must be able to give and cannot take back, for the largest part chosen.
    non_reclaimable_mib: int
    measured: list[MeasuredPartView]
    #: The limit the measurements suggest, never applied by itself. None before any measurement.
    suggested_limit_mib: int | None
    #: The embedding revision this install declares (`INSTALL_EMBEDDING_REVISION`), the one the
    #: server's own weights have, and what to do about it. The held one is None when the server was
    #: not asked (the embedding part is not chosen) or did not say.
    declared_revision: str | None
    held_revision: str | None
    revision_note: str
    #: Non-empty when the four settings are not a configuration, and then the figures are the
    #: product's defaults and say nothing about this install.
    problem: str
    note: str


#: Said beside every page, so a figure is never read as more than it is.
THE_FIGURES_ARE_JUDGEMENTS_UNTIL_MEASURED: Final = (
    "Every limit here is worked out from judgements (brain.ops.model_server.SIZING) until the "
    "server has measured itself; the measured rows are the only figures about its memory that "
    "describe something that ran. A suggested limit is a measurement with a margin and is never "
    "applied by itself: change INSTALL_MODEL_MEMORY_MIB to follow it, or leave it on auto."
)


@router.get("/install/model-server", response_model=ModelServerPage, responses=COMMON_RESPONSES)
async def model_server(request: Request, asked: Asked) -> ModelServerPage:
    """The model server as chosen, what it costs and what it measured, for who may change settings.

    The same authority as the screen it sits beside, asked first. A configuration that cannot be
    read is a page that says so and shows the defaults, not an error: the person is here to fix it.
    """
    if not may_configure(asked.reach, asked.now):
        log.info("model server page not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    problem = ""
    try:
        config = read_config()
    except ModelServerError as error:
        problem, config = str(error), config_from()
    needs = requirement(config)
    switched = False
    summaries: tuple[PeakSummary, ...] = ()
    declared, held = await _revisions(config)
    factory = sessions_of(request)
    if factory is not None:
        async with factory() as session:
            switched = await is_on(session, MODEL_SERVER)
            summaries = summarise(await recorded_peaks(session))
    return ModelServerPage(
        switched_on=switched,
        parts=[one.value for one in config.parts],
        idle_seconds=config.idle_seconds,
        upload_mb=config.upload_mb,
        limit_mib=config.memory_override_mib or needs.limit_mib,
        worked_out=config.memory_override_mib is None,
        worked_out_limit_mib=needs.limit_mib,
        non_reclaimable_mib=needs.non_reclaimable_mib,
        measured=[
            MeasuredPartView(
                part=one.part.value,
                batches=one.batches,
                largest_anonymous_mib=one.largest_anon_mib,
                largest_total_mib=one.largest_total_mib,
                suggested_limit_mib=one.suggested_limit_mib,
            )
            for one in summaries
        ],
        suggested_limit_mib=suggested_overall_mib(summaries),
        declared_revision=declared,
        held_revision=held,
        revision_note=revision_note(declared, held),
        problem=problem,
        note=THE_FIGURES_ARE_JUDGEMENTS_UNTIL_MEASURED,
    )


def revision_note(declared: str | None, held: str | None) -> str:
    """What a person should do about the embedding revision, in words, or nothing to do.

    **The held revision is the server's own statement of its weights and the declared one is the
    install's claim about them.** A vector is recorded under the declared one and refused if the
    server states another, so the two have to be one, and the person who has to make them one is
    the person who reads this.
    """
    if held is None:
        return ""
    if declared is None:
        return (
            f"The model server holds embedding weights with the revision {held}. Set "
            f"{REVISION_SETTING} to it and nothing is embedded until you do."
        )
    if declared == held:
        return "The revision declared for this install is the one the model server holds."
    return (
        f"{REVISION_SETTING} says {declared} and the model server holds {held}, so every vector it "
        "returns is refused. Set the setting to the one the server holds, or fetch the weights "
        "the setting names."
    )


async def _revisions(config: ModelServerConfig) -> tuple[str | None, str | None]:
    """The revision this install declares and the one its server says it holds, each if known."""
    try:
        declared = embedding_revision()
    except EmbeddingError:
        declared = None
    if Part.EMBEDDING not in config.parts:
        return declared, None
    answered = await server_readiness()
    return declared, None if answered is None else held_embedding_revision(answered[1])


@router.put(f"{SETTINGS_PATH}/{{name}}", response_model=SettingsPage, responses=COMMON_RESPONSES)
async def save_setting(request: Request, name: str, body: SaveAsked, asked: Asked) -> JSONResponse:
    """Save one setting, hold it for this process, and answer with the screen as it now is.

    The authority, then the name and value, then the write, and the order is the property: a caller
    without the authority is refused before the name is looked at, and a value that would be
    refused is never written.
    """
    if not may_configure(asked.reach, asked.now):
        log.info("setting save refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    problem = setting_problem(name, body.value)
    if problem:
        told = ErrorBody(message=problem, trace_id=_trace_id())
        return JSONResponse(status_code=422, content=told.model_dump())
    async with _require_sessions(request)() as session:
        # A service whose runtime the server lacks is refused before anything is written, from the
        # deploy step's last report of the server (brain.ops.overlays.runtime_problem).
        # And one that would not all fit in the memory the server last measured, by the same
        # costing the deploy uses (brain.ops.overlays.memory_problem).
        #
        # **The model server's four settings go through the same costing**, with the setting as it
        # would be saved: choosing larger parts or a larger document changes what the server costs
        # and so whether the services named would all fit, and that is judged by the one costing
        # the deploy uses (`brain.ops.overlays.plan_in_room`) and not by a second sum.
        if name == SERVICES_SETTING or name in MODEL_SERVER_SETTINGS:
            candidate = {**await load(session), name: normalised(name, body.value)}
            services = value_of(SERVICES_SETTING, saved=candidate)
            lacking = (
                await runtime_problem(session, services) if name == SERVICES_SETTING else ""
            ) or await memory_problem(session, services, saved=candidate)
            if lacking:
                told = ErrorBody(message=lacking, trace_id=_trace_id())
                return JSONResponse(status_code=422, content=told.model_dump())
        for statement in attributed_to(
            actor_id=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
        ):
            await session.execute(statement)
        await save(
            session, {name: normalised(name, body.value)}, updated_by=asked.caller.principal.id
        )
        saved = await load(session)
        furnished = await _furnished(session)
        await session.commit()
    hold_saved(saved)
    log.info("installation setting saved", setting=name, principal=asked.caller.principal.id)
    page = settings_page(furnished=furnished, saved=saved)
    return JSONResponse(status_code=200, content=page.model_dump(mode="json"))


@router.post(
    f"{SETTINGS_PATH}/{{name}}/default", response_model=SettingsPage, responses=COMMON_RESPONSES
)
async def return_to_default(request: Request, name: str, asked: Asked) -> JSONResponse:
    """Take one setting's saved value away, so it reads the environment or its default again.

    The authority, then the name, then the retirement, in `save_setting`'s order and for its
    reason. A setting with nothing saved answers 409 and writes nothing.
    """
    if not may_configure(asked.reach, asked.now):
        log.info("setting default refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    problem = default_problem(name)
    if problem:
        told = ErrorBody(message=problem, trace_id=_trace_id())
        return JSONResponse(status_code=422, content=told.model_dump())
    async with _require_sessions(request)() as session:
        for statement in attributed_to(
            actor_id=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
        ):
            await session.execute(statement)
        retired = await retire(session, name, updated_by=asked.caller.principal.id)
        if not retired:
            await session.rollback()
            told = ErrorBody(message=NOTHING_SAVED_HERE, trace_id=_trace_id())
            return JSONResponse(status_code=409, content=told.model_dump())
        saved = await load(session)
        furnished = await _furnished(session)
        await session.commit()
    hold_saved(saved)
    log.info(
        "installation setting returned to default",
        setting=name,
        principal=asked.caller.principal.id,
    )
    page = settings_page(furnished=furnished, saved=saved)
    return JSONResponse(status_code=200, content=page.model_dump(mode="json"))


__all__ = [
    "INSTALL_SETTING_AUTHORITY",
    "SETTINGS_PATH",
    "SaveAsked",
    "SettingsPage",
    "may_configure",
    "router",
    "settings_page",
]
