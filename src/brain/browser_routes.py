"""The websites an agent's browser may be pointed at, and what is signed for them, over HTTP.

`brain.browsing.targets` says a target is a declaration by a person, and `brain.browsing.autonomy`
and `brain.browsing.skill_gate` say a surface exception and a skill exemption are signed. Until
this module nothing kept either, so the only way to give a browser a website was a line of code.
This is the door: a person who administers browsers declares a website with the pages on it,
signs an exception or an exemption, and takes either back, and `brain.browsing.declared` keeps
what they did.
**Nothing here opens a browser.** `browser_runs` is the switch for that, and a declaration with it
off is a record the driver will read.

**One authority for the read and every write, held over everything**, `admin:browser`, for the
reason `brain.plugin_routes` gives about `admin:plugin`: a website is declared for the whole
install, so there is no department's version of one. A caller without it is answered
identically with a database and without one, and the refusal names the screen and never the
capability.

**An exception is signed by the person who presses it, and they must be able to do the write
themselves.** `autonomy.sign` is asked of the caller's own reach, so an administrator of browsers
who may not perform a write on a surface cannot sign for an agent to perform it unattended. The
authority to administer and the authority to write are two things and both are needed.

**The switch gates what opens a permission and never what takes one back.** Declaring a website,
signing an exception and signing an exemption are behind `browser_declarations`, which ships off.
Retiring a declaration and revoking a grant never are, so turning the switch off cannot leave a
permission nobody can withdraw.

**A document is refused where its words still exist.** The codec names the key, the verb, the
origin or the vault path that is wrong, and a credential is shown as the placeholder, the origin
and the kind, never the vault path's contents (a path is a reference, and it is shown because the
person who wrote it needs to read it back).

Task ids: M19.2.4, M19.6.7, M19.7.3, M19.9.7
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any, Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.browsing import declared
from brain.browsing.declared import DeclarationError
from brain.browsing.skill_gate import MAX_EXEMPTION
from brain.console.govern import NOWHERE, _in_reach
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, Failed
from brain.ops.features import is_on
from brain.ops.features_declared.browser_declarations import BROWSER_DECLARATIONS
from brain.routing_routes import sessions_of

log = structlog.get_logger()

#: The one authority, over everything.
BROWSER_ADMIN: Final = Capability(value="admin:browser")

#: The screen's name in a refusal. The console's own menu word, identical on every install.
BROWSER_SCREEN: Final = "browser"

#: The most days an exception or an exemption may run, which is `skill_gate.MAX_EXEMPTION`.
MOST_DAYS: Final = MAX_EXEMPTION.days


def may_administer(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach may read what is declared and change it: the authority, everywhere."""
    return _in_reach(reach, BROWSER_ADMIN, NOWHERE, now)


async def declarations_are_on(session: AsyncSession) -> bool:
    """Whether this install lets a website be declared and a permission be signed."""
    return await is_on(session, BROWSER_DECLARATIONS)


class BrowserSurfaceView(BaseModel):
    """One declared page, as the screen lists it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    origin: str
    path: str
    verbs: list[str]
    reads: list[str]
    read_back: str
    #: What each write is done on, as `verb role "name"`. A credential is its placeholder.
    controls: list[str]


class BrowserBindingView(BaseModel):
    """A sign-in a target uses. The placeholder, where it applies and the vault reference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    placeholder: str
    origin: str
    kind: str
    path: str


class BrowserTargetView(BaseModel):
    """One declared website."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    origins: list[str]
    api_tools: list[str]
    surfaces: list[BrowserSurfaceView]
    bindings: list[BrowserBindingView]
    declared_by: str
    declared_at: datetime


class BrowserGrantView(BaseModel):
    """One permission in force: who signed it, why, and when it lapses."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: int
    #: `exception` or `exemption`.
    kind: str
    target: str
    #: The surface an exception is for, or the skill an exemption is for.
    what: str
    signed_by: str
    reason: str
    expires_at: datetime


class BrowserPage(BaseModel):
    """The declared websites, the permissions in force and the facts this screen cannot change."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    targets: list[BrowserTargetView]
    #: Names of declarations this release cannot read. They are not declared, and are listed so
    #: that a person knows to declare them again.
    unreadable: list[str]
    grants: list[BrowserGrantView]
    #: Whether declaring and signing are switched on. Retiring and revoking are always offered.
    declarations_are_on: bool
    most_days: int = MOST_DAYS


class BrowserRetired(BaseModel):
    """A declared website that no longer is. The name, so the page can say which."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str


class BrowserRevoked(BaseModel):
    """A permission that ended now. The number, so the page can say which."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: int


class DeclarationAsked(BaseModel):
    """A website to declare. Raw, because the codec's refusals are the ones that name the key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    declaration: dict[str, Any]


class ExceptionAsked(BaseModel):
    """Writes on one page may run without waiting for a person, for some days."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    surface: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    days: Annotated[int, Field(ge=1, le=MOST_DAYS)]
    reason: Annotated[str, StringConstraints(min_length=1, max_length=240)]


class ExemptionAsked(BaseModel):
    """A skill may drive a website that has an API, for some days."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    skill: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    target: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    days: Annotated[int, Field(ge=1, le=MOST_DAYS)]
    reason: Annotated[str, StringConstraints(min_length=1, max_length=240)]


def _surface_view(surface: Any) -> BrowserSurfaceView:
    return BrowserSurfaceView(
        name=surface.name,
        origin=surface.origin,
        path=surface.path,
        verbs=sorted(verb.value for verb in surface.verbs),
        reads=list(surface.reads),
        read_back=surface.read_back,
        controls=[
            f'{one.verb.value} {one.role} "{one.label}"'
            + (f" {one.placeholder}" if one.placeholder else "")
            for one in surface.controls
        ],
    )


def target_view(stored: declared.Stored) -> BrowserTargetView:
    target = stored.declared.target
    return BrowserTargetView(
        name=target.name,
        origins=sorted(target.origins),
        api_tools=list(target.api_tools),
        surfaces=[_surface_view(one) for one in target.surfaces],
        bindings=[
            BrowserBindingView(
                placeholder=one.placeholder,
                origin=one.origin,
                kind=one.kind.value,
                path=one.ref.path,
            )
            for one in stored.declared.bindings.bindings
        ],
        declared_by=stored.set_by,
        declared_at=stored.at,
    )


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", "")) or "unassigned"


def _require_sessions(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return factory


def _not_answerable() -> Absent:
    """The one refusal a caller without the authority gets. Names the screen and nothing else."""
    return Absent(f"the {BROWSER_SCREEN} screen is not answerable for this caller")


def _refused_because(reason: str) -> Absent:
    """A refusal for a caller holding the authority, naming what to fix."""
    message = f"that was not changed: {reason}"
    return Absent(message, public_message=message)


async def _switched_on(session: AsyncSession) -> None:
    """Refuse when declaring and signing are switched off. Asked of the switch, not of a copy."""
    if not await declarations_are_on(session):
        raise _refused_because(
            "declaring websites and signing permissions is switched off for this install; "
            "switch it on from Features"
        )


router = APIRouter(prefix=API_PREFIX, tags=["install"])


@router.get("/install/browser", response_model=BrowserPage, responses=COMMON_RESPONSES)
async def browser_page(request: Request, asked: Asked) -> BrowserPage:
    """Every declared website and every permission in force, for a caller who administers them."""
    if not may_administer(asked.reach, asked.now):
        log.info("browser screen not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        loaded = await declared.load(session)
        grants = await declared.listing(session, asked.now)
        declarations = await declarations_are_on(session)
    return BrowserPage(
        targets=[target_view(loaded.declared[name]) for name in sorted(loaded.declared)],
        unreadable=list(loaded.unreadable),
        grants=[
            BrowserGrantView(
                seq=one.seq,
                kind=one.kind,
                target=one.target,
                what=one.what,
                signed_by=one.signed_by,
                reason=one.reason,
                expires_at=one.expires_at,
            )
            for one in grants
        ],
        declarations_are_on=declarations,
    )


@router.post(
    "/install/browser/targets",
    status_code=201,
    response_model=BrowserTargetView,
    responses=COMMON_RESPONSES,
)
async def declare_target(
    request: Request, body: DeclarationAsked, asked: Asked
) -> BrowserTargetView:
    """Declare a website, or declare it again, which replaces what the screen shows for it.

    The authority first, then the switch, then the document, and the order is the property: a
    caller without the authority learns nothing, and one with it is told the switch is off before
    anything about the document it sent.
    """
    if not may_administer(asked.reach, asked.now):
        log.info("browser declaration refused", principal=asked.caller.principal.id)
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        await _switched_on(session)
        try:
            read = declared.declared_from(body.declaration)
            await declared.declare(session, read, by=asked.caller.principal.id)
        except DeclarationError as refused:
            raise _refused_because(str(refused)) from None
        await session.commit()
        stored = (await declared.load(session)).declared[read.target.name]
    log.info("browser target declared", target=read.target.name)
    return target_view(stored)


@router.post(
    "/install/browser/targets/{name}/retire",
    response_model=BrowserRetired,
    responses=COMMON_RESPONSES,
)
async def retire_target(request: Request, name: str, asked: Asked) -> BrowserRetired:
    """Withdraw a declared website. Never behind the switch: an act that takes back is not gated by
    the act that gave."""
    if not may_administer(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        if not await declared.retire(session, name, by=asked.caller.principal.id):
            raise _refused_because(f"{name} is not declared")
        await session.commit()
    log.info("browser target retired", target=name)
    return BrowserRetired(name=name)


@router.post(
    "/install/browser/exceptions",
    status_code=201,
    response_model=BrowserGrantView,
    responses=COMMON_RESPONSES,
)
async def sign_exception(request: Request, body: ExceptionAsked, asked: Asked) -> BrowserGrantView:
    """Sign an exception for one declared page's writes to run without waiting for a person."""
    if not may_administer(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        await _switched_on(session)
        held = (await declared.load(session)).declared.get(body.target)
        if held is None:
            raise _refused_because(f"{body.target} is not declared")
        expires = asked.now + timedelta(days=body.days)
        try:
            await declared.sign_exception(
                session,
                held.declared.target,
                body.surface,
                signer=asked.reach,
                expires_at=expires,
                reason=body.reason,
                now=asked.now,
                trace_id=_trace_id(),
            )
        except DeclarationError as refused:
            raise _refused_because(str(refused)) from None
        await session.commit()
        made = [
            one
            for one in await declared.listing(session, asked.now)
            if one.kind == declared.EXCEPTION
            and one.target == body.target
            and one.what == body.surface
        ][-1]
    log.info("browser exception signed", target=body.target, surface=body.surface)
    return _grant_view(made)


@router.post(
    "/install/browser/exemptions",
    status_code=201,
    response_model=BrowserGrantView,
    responses=COMMON_RESPONSES,
)
async def sign_exemption(request: Request, body: ExemptionAsked, asked: Asked) -> BrowserGrantView:
    """Sign an exemption for a skill to drive a website that has an API."""
    if not may_administer(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        await _switched_on(session)
        if body.target not in (await declared.load(session)).declared:
            raise _refused_because(f"{body.target} is not declared")
        try:
            await declared.sign_exemption(
                session,
                skill=body.skill,
                target=body.target,
                approver=asked.caller.principal.id,
                expires_at=asked.now + timedelta(days=body.days),
                reason=body.reason,
                now=asked.now,
                ent_hash=asked.reach.ent_hash(),
                trace_id=_trace_id(),
            )
        except DeclarationError as refused:
            raise _refused_because(str(refused)) from None
        await session.commit()
        made = [
            one
            for one in await declared.listing(session, asked.now)
            if one.kind == declared.EXEMPTION
            and one.target == body.target
            and one.what == body.skill
        ][-1]
    log.info("browser exemption signed", target=body.target, skill=body.skill)
    return _grant_view(made)


def _grant_view(one: declared.GrantView) -> BrowserGrantView:
    return BrowserGrantView(
        seq=one.seq,
        kind=one.kind,
        target=one.target,
        what=one.what,
        signed_by=one.signed_by,
        reason=one.reason,
        expires_at=one.expires_at,
    )


@router.post(
    "/install/browser/grants/{seq}/revoke",
    response_model=BrowserRevoked,
    responses=COMMON_RESPONSES,
)
async def revoke_grant(request: Request, seq: int, asked: Asked) -> BrowserRevoked:
    """End a permission now. Never behind the switch."""
    if not may_administer(asked.reach, asked.now):
        raise _not_answerable()
    async with _require_sessions(request)() as session:
        if not await declared.revoke(
            session,
            seq,
            by=asked.caller.principal.id,
            now=asked.now,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
        ):
            raise _refused_because("that permission is not in force")
        await session.commit()
    log.info("browser grant revoked", seq=seq)
    return BrowserRevoked(seq=seq)
