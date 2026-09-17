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

**Only branding is written, and a refusal says why in the product's words.** A name that is not a
declared setting and a setting in another group are refused with the same sentence
`brain.console.configuration.branding_problem` gives, which names no value this install holds:
the declared names are product text, identical on every install.

**The starter set is shown with the one thing it does not furnish, stated exactly.** Roles, the
starter pack and the company scope are furnished at every start by `brain.ops.starter_store`. The
standard agents are not installed, because an agent is an install of a signed template and the
install has no signing key until M13.8.10 mints one; the sentence is
`brain.ops.starter_store.NO_TEMPLATE_IS_SIGNED_BEFORE_THE_INSTALL_HOLDS_A_KEY_OF_ITS_OWN`.

**Leaving is on the same screen, because it is the same authority.** The handover of this install
(export everything, remove every part, certify) is carried out by `brain.ops.handover_run` on the
server, not from a browser: a button that drops every schema is one misclick from the end of the
company's data. The screen shows what that command would export and remove, who removes each part
and how, and the retention that sets the certificate's backup date, so an owner can read the
procedure before anybody runs it.

Task ids: M41.1.4, M41.1.5, M41.1.6, M41.1.7, M41.2.6, M41.4.1
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
    CHANGED_ELSEWHERE,
    EDITABLE_GROUPS,
    GROUP_ORDER,
    GROUP_TITLES,
    ONLY_BRANDING_IS_CHANGED_HERE,
    THE_SCREEN_SHOWS_NO_CREDENTIAL,
    Row,
    branding_problem,
    findings,
    profile_told,
    rows,
)
from brain.console.govern import NOWHERE, _in_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.install import hold_saved, value_of
from brain.ops.handover import Residue
from brain.ops.handover_run import preview_steps
from brain.ops.install_settings import load, save
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

#: Why the standard agents are not on a freshly furnished install. M13.8.10 is the leaf that
#: mints the key they need.
STANDARD_AGENTS_WAIT_FOR_THE_SIGNING_KEY: Final = (
    "The standard agents are not installed. An agent is an install of a signed template, and this "
    "install holds no template signing key yet. "
    + NO_TEMPLATE_IS_SIGNED_BEFORE_THE_INSTALL_HOLDS_A_KEY_OF_ITS_OWN
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
    meaning: str
    value: str
    #: `saved`, `environment`, `default` or `missing`.
    source: str
    default: str
    required: bool
    editable: bool
    #: When a change to this value takes effect, in a sentence.
    applies: str
    #: The modules that read it, as dotted paths.
    read_by: list[str]


class SettingGroupView(BaseModel):
    """One group of settings, whether this screen changes it, and where it is changed if not."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    group: str
    title: str
    editable: bool
    #: Where a value in this group is changed instead, or empty for a group changed here.
    changed_elsewhere: str
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
    """One branding value. Required, so what is saved is what the person typed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str


# ------------------------------------------------------------------------------ the decisions


def row_view(one: Row) -> SettingRowView:
    return SettingRowView(
        name=one.name,
        meaning=one.meaning,
        value=one.value,
        source=one.source.value,
        default=one.default,
        required=one.required,
        editable=one.editable,
        applies=one.applies,
        read_by=list(one.read_by),
    )


def settings_page(*, furnished: bool | None, saved: dict[str, str] | None = None) -> SettingsPage:
    """The screen, from the declaration, this process's environment and the values saved.

    `saved` defaults to what this process holds, which is what every reader resolves against, so
    the screen shows the value a page served now would draw.
    """
    resolved_rows = rows(saved=saved)
    groups = [
        SettingGroupView(
            group=group.value,
            title=GROUP_TITLES[group],
            editable=group in EDITABLE_GROUPS,
            changed_elsewhere=CHANGED_ELSEWHERE.get(group, ""),
            settings=[row_view(one) for one in resolved_rows if one.group is group],
        )
        for group in GROUP_ORDER
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
        editable_because=ONLY_BRANDING_IS_CHANGED_HERE,
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


@router.put(f"{SETTINGS_PATH}/{{name}}", response_model=SettingsPage, responses=COMMON_RESPONSES)
async def save_setting(request: Request, name: str, body: SaveAsked, asked: Asked) -> JSONResponse:
    """Save one branding value, hold it for this process, and answer with the screen as it now is.

    The authority, then the name and value, then the write, and the order is the property: a caller
    without the authority is refused before the name is looked at, and a value that would be
    refused is never written.
    """
    if not may_configure(asked.reach, asked.now):
        log.info("setting save refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    problem = branding_problem(name, body.value)
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
        await save(session, {name: body.value.strip()}, updated_by=asked.caller.principal.id)
        saved = await load(session)
        furnished = await _furnished(session)
        await session.commit()
    hold_saved(saved)
    log.info("installation setting saved", setting=name, principal=asked.caller.principal.id)
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
