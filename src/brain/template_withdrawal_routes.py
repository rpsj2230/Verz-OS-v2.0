"""Withdrawing a template version, undoing it, and exporting or importing a template, over HTTP.

`brain.agents.template_withdrawal` decides what each of these is and `brain.ops.
template_withdrawal_store` keeps the rows; this is the door, and it decides who may open it. The
Templates page had a "Withdraw version" button that said it was coming (`templateActions.ts`), and
`docs/admin-console-architecture.md` (C2) named the missing halves: withdraw a version and undo it
as insert-only rows, hide a withdrawn version from new installs while installed agents stay pinned,
and a template as a signed document another install imports.

**One authority: the install authority held over everything.** `admin:agent_install` is what lets a
person turn a published version into an agent, so it is what lets a person say a version is no
longer to be turned into one. Held over a department it would let one department hide a version
from every other, so the scope must be the whole company. Rejected: a capability of its own, which
is a grant the administrator would hold beside the one that already means this, and a second thing
for the first administrator's list to name. Every refusal is the one answer the install route
gives a caller who may not install, whether the caller lacks the screen, the authority or a version
to act on, so the address is not a way to learn which versions exist.

**The switch gates the door and never traps what it opened.** Withdrawing, exporting and importing
are behind `template_withdrawal`, which ships off. Reading a version's state and undoing a
withdrawal are not: a switch turned off must not leave a version hidden with nobody able to bring it
back. See `brain.ops.features.A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED`.

**Withdrawn means not offered, and nothing else.** The gallery, a version's install page and an
agent's upgrade offer leave a withdrawn version out; an agent installed from it is read, run and
duplicated as before (`AN_INSTALLED_AGENT_STAYS_PINNED_TO_WHAT_IT_WAS_INSTALLED_FROM`). The people
who may withdraw see the withdrawn list here, which the gallery no longer holds, so there is
somewhere to undo from.

**An import is two steps, and the second names what the first showed.** The first call, with no
digest, reads the document and answers what it asks for and what looks like a company's own detail,
and writes nothing. The second names the digest it was shown, which is the install route's
confirmation (`expected_digest`), and writes one version, signed by this install's key with the
importer as publisher. A document that fails the digest, names an id this install ships or holds
differently, or carries a shaped literal is refused with a sentence that names no value. See
`brain.agents.template_withdrawal`'s own account of why the exporter's signature is reported
and not relied on.

Task ids: M27.15.35
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Final

import structlog
from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.agent_lifecycle_routes import NO_SIGNING_KEY_HERE, template_key_of
from brain.agent_routes import TEMPLATE_SCREEN, _require_session_factory
from brain.agents.creation import AGENT_INSTALL_CAPABILITY
from brain.agents.template import (
    SignedManifest,
    TemplateError,
    TemplateManifest,
    manifest_from_document,
    publish,
    verify,
)
from brain.agents.template_withdrawal import (
    COMPANY_DETAILS_IN_THE_DOCUMENT,
    NOT_A_NAME_THIS_INSTALL_MAY_TAKE,
    REASON_CHARS,
    TemplateWithdrawalError,
    arrival,
    company_details,
    export_document,
    may_take_the_name,
    read_export,
    reason_of,
    same_body,
)
from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.automation_schedule_routes import NotChangedView
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.errors import Absent
from brain.ops.features import is_on
from brain.ops.features_declared.template_withdrawal import TEMPLATE_WITHDRAWAL
from brain.ops.template_withdrawal_store import StoredTemplateWithdrawals
from brain.prompt_routes import signed_of

log = structlog.get_logger()

# ------------------------------------------------------------------ written-down reasons
#: What a person with the authority and the switch off is told.
WITHDRAWING_IS_SWITCHED_OFF: Final = (
    "Withdrawing, exporting and importing templates are switched off on this install. An "
    "administrator can turn them on in Features. A version already withdrawn can still be put back."
)

#: What the confirmed digest not matching the document says.
NOT_THE_DOCUMENT_SHOWN: Final = (
    "That is not the document you were shown, so nothing was imported. Read it again and confirm."
)

#: What an import says when it is only a reading.
NOTHING_WRITTEN_YET: Final = (
    "Nothing has been imported. Confirm to sign this template with this install's key and add it "
    "to the catalogue."
)

#: The outcomes a refused change carries. `MOVED` is `agent_lifecycle_routes`' word for the same.
REFUSED: Final = "refused"
MOVED: Final = "moved"

# ------------------------------------------------------------------------------ the figures
WITHDRAWAL_PATH: Final = "/agent-templates/{template_id}/versions/{version}/withdrawal"
UNDO_PATH: Final = "/agent-templates/{template_id}/versions/{version}/withdrawal/undo"
EXPORT_PATH: Final = "/agent-templates/{template_id}/versions/{version}/export"
WITHDRAWN_PATH: Final = "/agent-template-withdrawals"
IMPORT_PATH: Final = "/agent-template-imports"

TemplateId = Annotated[str, Path(min_length=2, max_length=60)]
VersionNumber = Annotated[int, Path(ge=1, le=1_000_000)]


# ------------------------------------------------------------------------ the shapes
class WithdrawalChangeView(BaseModel):
    """One change to whether a version is offered, in the order it was made."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    withdrawn: bool
    set_by: str
    at: datetime
    reason: str


class TemplateWithdrawalView(BaseModel):
    """Whether one version is offered to new installs, and every change that made it so.

    `may_withdraw` is true for a version that is offered while the switch is on, and `may_undo` for
    one that is withdrawn whatever the switch says, so the page can draw each button as pressable
    or say why it is not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str
    version: int
    withdrawn: bool
    changes: list[WithdrawalChangeView]
    may_withdraw: bool
    may_undo: bool
    #: Why Withdraw cannot be pressed, when it cannot; empty otherwise.
    unavailable: str = ""


class WithdrawAsked(BaseModel):
    """A withdrawal's reason: a sentence, required."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=REASON_CHARS)


class WithdrawnVersionView(BaseModel):
    """One version that is withdrawn now: which, why, by whom and when."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str
    version: int
    display_name: str
    reason: str
    set_by: str
    at: datetime


class WithdrawnVersionsView(BaseModel):
    """The versions withdrawn now, for the people who may undo it. No count of anything else."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    versions: list[WithdrawnVersionView]


class TemplateExportView(BaseModel):
    """A version as a signed document: what is stored of it, to be carried to another install."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str
    version: int
    document: dict[str, Any]


class TemplateImportAsked(BaseModel):
    """A document brought in, and, to write it, the digest of the document that was shown."""

    model_config = ConfigDict(extra="forbid")

    document: dict[str, Any]
    expected_digest: str | None = Field(default=None, min_length=64, max_length=64)


class TemplateCompanyDetailView(BaseModel):
    """One kind of company detail a document holds and where, never what it says."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    places: list[str]


class TemplateImportView(BaseModel):
    """What an import read, or did: the template, whether it was written, and what to look at."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    imported: bool
    #: False for an import that found this install already held the same template.
    created: bool
    template_id: str
    version: int
    display_name: str
    summary: str | None
    #: The digest of the body in the document, which is what a confirmation names.
    content_digest: str
    #: Whether this install's own key made the document's signature. False means it could not be
    #: checked here, which is what a document from another install always says.
    signed_by_this_install: bool
    company_details: list[TemplateCompanyDetailView]
    says: str


# ------------------------------------------------------------------------------ the doors
def _not_here(asked: Asking, reason: str) -> Absent:
    """The one refusal about a template version, to a caller who may not manage them."""
    log.info(
        "template withdrawal not answerable", reason=reason, principal=asked.caller.principal.id
    )
    return Absent(f"the {TEMPLATE_SCREEN} screen is not answerable for this caller")


def may_manage(asked: Asking) -> bool:
    """The gallery's screen and the install authority over the whole company, and nothing less."""
    if not permitted(screen(TEMPLATE_SCREEN).read, asked.reach, asked.now):
        return False
    held = asked.reach.scope_for(AGENT_INSTALL_CAPABILITY, asked.now)
    return held is not None and held.is_unrestricted()


async def withdrawal_is_on(request: Request) -> bool:
    """Whether withdrawing, exporting and importing templates are switched on. Off until turned on.

    Asked before a withdrawal, an export and an import, and never before an undo or a reading: see
    `brain.ops.features.A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED`.
    """
    found = getattr(request.app.state, "template_withdrawal_on", None)
    if isinstance(found, bool):
        return found
    factory = _require_session_factory(request)
    async with factory() as session:
        return await is_on(session, TEMPLATE_WITHDRAWAL)


def _store(request: Request) -> StoredTemplateWithdrawals:
    found = getattr(request.app.state, "template_withdrawals", None)
    if isinstance(found, StoredTemplateWithdrawals):
        return found
    return StoredTemplateWithdrawals(_require_session_factory(request))


def _changed(outcome: str, sentence: str) -> JSONResponse:
    body = NotChangedView(outcome=outcome, sentence=sentence)
    return JSONResponse(status_code=409, content=body.model_dump(mode="json"))


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


async def _view(
    request: Request, store: StoredTemplateWithdrawals, template_id: str, version: int
) -> TemplateWithdrawalView:
    changes = await store.history(template_id, version)
    standing = bool(changes) and changes[-1].withdrawn
    on = await withdrawal_is_on(request)
    return TemplateWithdrawalView(
        template_id=template_id,
        version=version,
        withdrawn=standing,
        changes=[
            WithdrawalChangeView(
                withdrawn=one.withdrawn, set_by=one.set_by, at=one.at, reason=one.reason
            )
            for one in changes
        ],
        may_withdraw=on and not standing,
        may_undo=standing,
        unavailable="" if on else WITHDRAWING_IS_SWITCHED_OFF,
    )


router = APIRouter(prefix=API_PREFIX, tags=["agents"])


@router.get(WITHDRAWAL_PATH, response_model=TemplateWithdrawalView, responses=COMMON_RESPONSES)
async def template_withdrawal(
    request: Request, template_id: TemplateId, version: VersionNumber, asked: Asked
) -> TemplateWithdrawalView:
    """Whether one published version is offered, and its changes."""
    if not may_manage(asked):
        raise _not_here(asked, "authority")
    store = _store(request)
    if await store.row_of(template_id, version) is None:
        raise _not_here(asked, "version")
    return await _view(request, store, template_id, version)


@router.post(WITHDRAWAL_PATH, response_model=TemplateWithdrawalView, responses=COMMON_RESPONSES)
async def withdraw_template_version(
    request: Request,
    template_id: TemplateId,
    version: VersionNumber,
    body: WithdrawAsked,
    asked: Asked,
) -> Any:
    """Withdraw a published version from new installs, with a reason, as an inserted row.

    The authority and the version first, so a caller without either is refused as a missing one;
    then the switch; then the reason. Agents installed from the version are not touched.
    """
    if not may_manage(asked):
        raise _not_here(asked, "authority")
    store = _store(request)
    if await store.row_of(template_id, version) is None:
        raise _not_here(asked, "version")
    if not await withdrawal_is_on(request):
        return _changed(REFUSED, WITHDRAWING_IS_SWITCHED_OFF)
    try:
        reason = reason_of(body.reason)
        moved = await store.change(
            template_id,
            version,
            withdraw=True,
            reason=reason,
            by=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
        )
    except TemplateWithdrawalError as refused:
        return _changed(REFUSED, str(refused))
    if moved is None:
        raise _not_here(asked, "version")
    log.info("template version withdrawn", principal=asked.caller.principal.id)
    return await _view(request, store, template_id, version)


@router.post(UNDO_PATH, response_model=TemplateWithdrawalView, responses=COMMON_RESPONSES)
async def undo_template_withdrawal(
    request: Request, template_id: TemplateId, version: VersionNumber, asked: Asked
) -> Any:
    """Put a withdrawn version back on offer, as an inserted row. Never behind the switch."""
    if not may_manage(asked):
        raise _not_here(asked, "authority")
    store = _store(request)
    if await store.row_of(template_id, version) is None:
        raise _not_here(asked, "version")
    try:
        moved = await store.change(
            template_id,
            version,
            withdraw=False,
            reason="",
            by=asked.caller.principal.id,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
        )
    except TemplateWithdrawalError as refused:
        return _changed(REFUSED, str(refused))
    if moved is None:
        raise _not_here(asked, "version")
    log.info("template withdrawal undone", principal=asked.caller.principal.id)
    return await _view(request, store, template_id, version)


@router.get(WITHDRAWN_PATH, response_model=WithdrawnVersionsView, responses=COMMON_RESPONSES)
async def withdrawn_template_versions(request: Request, asked: Asked) -> WithdrawnVersionsView:
    """The versions withdrawn now, newest withdrawal first, for the people who may undo one."""
    if not may_manage(asked):
        raise _not_here(asked, "authority")
    store = _store(request)
    standing = [one for one in (await store.newest()).values() if one.withdrawn]
    names = {
        (row.template_id, row.version): _display_name(row.document)
        for row in await store.rows_named([(one.template_id, one.version) for one in standing])
    }
    return WithdrawnVersionsView(
        versions=[
            WithdrawnVersionView(
                template_id=one.template_id,
                version=one.version,
                display_name=names.get((one.template_id, one.version), one.template_id),
                reason=one.reason,
                set_by=one.set_by,
                at=one.at,
            )
            for one in sorted(standing, key=lambda one: one.at, reverse=True)
        ]
    )


def _display_name(document: dict[str, Any]) -> str:
    named = document.get("identity.display_name")
    return named if isinstance(named, str) else ""


@router.get(EXPORT_PATH, response_model=TemplateExportView, responses=COMMON_RESPONSES)
async def export_template_version(
    request: Request, template_id: TemplateId, version: VersionNumber, asked: Asked
) -> Any:
    """A published version as a signed document, for another install to import."""
    if not may_manage(asked):
        raise _not_here(asked, "authority")
    row = await _store(request).row_of(template_id, version)
    if row is None:
        raise _not_here(asked, "version")
    if not await withdrawal_is_on(request):
        return _changed(REFUSED, WITHDRAWING_IS_SWITCHED_OFF)
    try:
        signed = signed_of(row)
    except (KeyError, ValueError, TemplateError):
        raise _not_here(asked, "unreadable") from None
    log.info("template version exported", principal=asked.caller.principal.id)
    return TemplateExportView(
        template_id=template_id, version=version, document=export_document(signed)
    )


@router.post(IMPORT_PATH, response_model=TemplateImportView, responses=COMMON_RESPONSES)
async def import_template(request: Request, body: TemplateImportAsked, asked: Asked) -> Any:
    """Read a template document, and with the digest it was shown, add it to this catalogue.

    See the module docstring. The reading names no value from the document and writes nothing; the
    writing is one inserted version, signed here, as version one of an id this install does not
    hold, or the version already there when it holds this very template.
    """
    if not may_manage(asked):
        raise _not_here(asked, "authority")
    if not await withdrawal_is_on(request):
        return _changed(REFUSED, WITHDRAWING_IS_SWITCHED_OFF)
    try:
        received = read_export(body.document)
    except TemplateWithdrawalError as refused:
        return _changed(REFUSED, str(refused))
    manifest = received.manifest
    template_id = manifest.identity.template_id
    key = template_key_of(request)
    store = _store(request)
    held = {
        row.version: manifest_from_document(row.document)
        for row in await store.rows_of(template_id)
    }
    found = [
        TemplateCompanyDetailView(kind=one.kind.value, places=list(one.locations))
        for one in company_details(manifest)
    ]
    ours = key is not None and key != "" and _verifies(received, key)
    same = next((number for number, then in held.items() if same_body(manifest, then)), None)
    shown = _import_view(
        manifest,
        digest=received.content_digest,
        signed_by_this_install=ours,
        details=found,
        version=same or 1,
    )
    if body.expected_digest is None:
        return shown.model_copy(update={"says": NOTHING_WRITTEN_YET})
    if body.expected_digest != received.content_digest:
        return _changed(MOVED, NOT_THE_DOCUMENT_SHOWN)
    if found:
        return _changed(REFUSED, COMPANY_DETAILS_IN_THE_DOCUMENT)
    if same is not None:
        return shown.model_copy(
            update={"imported": True, "created": False, "says": "This install already holds it."}
        )
    if not may_take_the_name(manifest, held or None):
        return _changed(REFUSED, NOT_A_NAME_THIS_INSTALL_MAY_TAKE)
    if not key:
        return _changed(REFUSED, NO_SIGNING_KEY_HERE)
    me = asked.caller.principal.id
    signed = publish(arrival(received, by=me), key=key, signed_by=me, at=asked.now)
    written = await store.keep_version(
        signed, by=me, ent_hash=asked.reach.ent_hash(), trace_id=_trace_id()
    )
    log.info("template imported", principal=me, written=written)
    return shown.model_copy(
        update={
            "imported": True,
            "created": written,
            "says": "Added to the catalogue, signed by this install.",
        }
    )


def _verifies(received: SignedManifest, key: str) -> bool:
    try:
        verify(received, key=key)
    except TemplateError:
        return False
    return True


def _import_view(
    manifest: TemplateManifest,
    *,
    digest: str,
    signed_by_this_install: bool,
    details: list[TemplateCompanyDetailView],
    version: int,
) -> TemplateImportView:
    identity = manifest.identity
    return TemplateImportView(
        imported=False,
        created=False,
        template_id=identity.template_id,
        version=version,
        display_name=identity.display_name,
        summary=identity.summary or None,
        content_digest=digest,
        signed_by_this_install=signed_by_this_install,
        company_details=details,
        says="",
    )
