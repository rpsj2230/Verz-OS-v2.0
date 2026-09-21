"""Connect Lark over HTTP: the steps for the uses chosen, a read-only test, and switching them on.

`brain.ops.lark_connect` holds the steps, the scopes, the test and the settings a use is switched
on with; `brain.ops.credentials` keeps the credential; `brain.ops.install_settings` keeps the
settings. This module asks them in order and adds no opinion of its own.

**The screen's read first, then each chosen use's own authority, before anything is judged.** The
guide is served to whoever may open the Connectors screen, because knowing what connecting would
do is not a power. Testing and saving send the app's secret out or keep it, so each chosen use
asks the authority that already governs it: the staff list asks `brain.credential_routes.
may_manage`, which is what replacing the staff source's credential already asks, and each other
use asks `brain.ops.connector_admin.may_connect_source` over its own slot. A caller short of any
of them is refused in the one way this router refuses anybody. See
`EACH_USE_IS_SWITCHED_ON_UNDER_THE_AUTHORITY_THAT_ALREADY_GOVERNS_IT`.

**The secret is in two request bodies and nowhere else.** The router is `brain.api.NoEchoRoute`,
so a refused body names the field and never repeats it; no response model has a field that could
carry it; what is logged is the uses, the verdicts and the principal. It is kept once per chosen
use, the same value in each use's own slot, because each consumer already reads its own slot: the
staff sync reads `connector_keys/staff_source`, and the Lark connectors name `lark_wiki` and
`lark_base`. See `ONE_CREDENTIAL_KEPT_WHERE_EACH_USE_ALREADY_READS_IT`.

**The vault first, and a use is switched on only after its credential is kept.** A vault that is
absent, refused or silent answers 409 or 503 with `brain.ops.credentials.TOLD`'s sentence and no
setting is written, so no use is ever switched on without a key behind it.

**Every write carries its attribution.** The settings are written in a transaction that first runs
`brain.attribution.attribute`, so `ops.setting`'s trigger records who switched Lark on, at what
reach, in which request, rather than `0003`'s placeholders (`brain.ops.write_attribution`).

Task ids: M11.9.4, M11.9.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Final, Protocol

import structlog
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, NoEchoRoute
from brain.api_routes import Asked, Asking
from brain.attribution import attribute, trace_of_request
from brain.connectors.staff_directories import LARK_PLATFORMS, Fetch
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.credential_routes import credentials_of, may_manage
from brain.install import InstallError, hold_saved, value_of
from brain.ops.connector_admin import may_connect_source
from brain.ops.credentials import (
    TOLD,
    CredentialProblemError,
    Credentials,
    CredentialsUnavailableError,
    VaultState,
    connector_key_slot,
)
from brain.ops.install_settings import load, save
from brain.ops.lark_connect import (
    KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED,
    THE_CHANNEL_RECEIVER_IS_NOT_BUILT_YET,
    THE_TEST_ONLY_READS,
    USES,
    Problem,
    Use,
    credential_value,
    developer_console,
    events_address,
    input_problems,
    probe_connection,
    scopes_for,
    settings_for,
    steps_for,
    uses_from,
    uses_switched_on,
)
from brain.ops.staff_sync_run import http_fetch
from brain.routing_routes import sessions_of

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Who may test or switch on each use.
EACH_USE_IS_SWITCHED_ON_UNDER_THE_AUTHORITY_THAT_ALREADY_GOVERNS_IT: Final = (
    "Testing and saving send the Lark app's secret out or keep it, so each chosen use asks the "
    "authority that already governs its credential: the staff list asks the credential authority "
    "the Staff sources screen asks, and each other use asks the connector installation authority "
    "over its own slot. Holding one does not switch on another."
)

#: Why the one credential is kept more than once.
ONE_CREDENTIAL_KEPT_WHERE_EACH_USE_ALREADY_READS_IT: Final = (
    "The company creates one Lark app and pastes its credential once. It is kept in the slot each "
    "use's reader already reads: the staff sync's, the Wiki connector's, the Base connector's and "
    "the channel's. A second slot shared by all of them would be a key the existing readers do "
    "not know about, and switching one use off could not leave the others their key."
)

# --------------------------------------------------------------------- the figures

#: `lark-app` rather than `lark`: these are console writes about the company's Lark app, and a
#: path segment naming a channel is what `tests/unit/test_inbound_webhooks.py` reads as a receiver.
LARK_PATH: Final = "/connectors/lark-app"
LARK_TEST_PATH: Final = LARK_PATH + "/test"

#: Where the staff list's runs and dry run are, the Staff sources screen's own address.
STAFF_SOURCES_SCREEN: Final = "/staff_sources"

#: The status each chosen use answers with the vault's state, for a save that kept nothing.
NOT_KEPT_STATUS: Final = {
    VaultState.ABSENT: 409,
    VaultState.REFUSED: 409,
    VaultState.UNREACHABLE: 503,
}

SWITCHED_ON: Final = "Switched on."
NOT_SWITCHED_ON: Final = "Not switched on."
NO_KEY_BEHIND_IT: Final = (
    "Switched on, but its credential is not in the vault. Run Connect Lark again and save."
)
KEY_NOT_KNOWN: Final = (
    "Switched on. Whether its credential is held is not known: the vault did not answer."
)
STAFF_ON: Final = (
    "The staff list is read on its schedule with this app. Its runs, a dry run and the leavers are "
    "on the Staff sources screen."
)
STAFF_ELSEWHERE: Final = (
    "Switched on here, but the Staff sources screen has since chosen another staff source, so "
    "the staff list is not read from Lark."
)
SAVED: Final = (
    "The credential is in the vault and the uses you chose are switched on. Nothing was copied "
    "from Lark."
)


# ------------------------------------------------------------------------ the shapes


class LarkScopeView(BaseModel):
    """One scope: its exact name, what it lets the app do, and whether it only reads."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    what: str
    read_only: bool


class LarkUseView(BaseModel):
    """One use: its words, its scopes, and where it stands on this install."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str
    what: str
    scopes: list[LarkScopeView]
    switched_on: bool
    #: Whether its credential is held, or None when the vault could not be asked or it is off.
    key_held: bool | None
    status: str
    #: Whether this reader may test and switch on this use. Their own grant; it narrows nothing.
    may_switch_on: bool


class LarkStepView(BaseModel):
    """One thing to do in Lark."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    text: str


class LarkView(BaseModel):
    """The guide for the uses asked about, every use's standing, and what testing does."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uses: list[LarkUseView]
    chosen: list[str]
    steps: list[LarkStepView]
    scopes: list[LarkScopeView]
    platforms: list[str]
    platform: str
    #: The Base token already saved, so the form starts from it; empty when none is named.
    base: str
    developer_console: str
    #: Where the chat channel's events will arrive, or empty when this install names no address.
    events_address: str
    channel_note: str
    knowledge_note: str
    test_note: str
    staff_sources_screen: str
    vault_told: str


class LarkAsked(BaseModel):
    """What a test and a save send. No length on any field, so every refusal is in words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    app_id: str
    app_secret: str
    uses: list[str]
    platform: str
    base_link: str = ""


class LarkUseResultView(BaseModel):
    """What testing one use came to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str
    verdict: str
    told: str
    missing: list[str]


class LarkTestView(BaseModel):
    """The token exchange and every chosen use. Nothing was written."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool
    told: str
    uses: list[LarkUseResultView]


class LarkSavedView(BaseModel):
    """What a save switched on. Never the credential."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    switched_on: list[str]
    told: str
    staff_sources_screen: str


class LarkProblemView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    code: str
    message: str


class LarkProblemsView(BaseModel):
    """Everything wrong with what was sent. Nothing was sent to Lark and nothing was written."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    problems: list[LarkProblemView]


# ------------------------------------------------------------------------ the wiring


class LarkSettings(Protocol):
    """Where a save's installation settings are written. `StoredLarkSettings` is the real one."""

    async def save(self, values: dict[str, str], asked: Asking) -> None: ...


class StoredLarkSettings:
    """`ops.setting`, written with the request's attribution, then held for this process."""

    def __init__(self, request: Request) -> None:
        self._request = request

    async def save(self, values: dict[str, str], asked: Asking) -> None:
        factory = sessions_of(self._request)
        if factory is None:
            raise Failed("no database on this process")
        async with factory() as session:
            await attribute(session, asked)
            await save(session, values, updated_by=asked.caller.principal.id)
            saved = await load(session)
            await session.commit()
        hold_saved(saved)


def settings_of(request: Request) -> LarkSettings:
    """What `app.state.lark_settings` holds, or the database."""
    found = getattr(request.app.state, "lark_settings", None)
    return found if found is not None else StoredLarkSettings(request)


def fetch_of(request: Request) -> Fetch:
    """What `app.state.lark_fetch` holds, or the real one, which follows no redirect."""
    found = getattr(request.app.state, "lark_fetch", None)
    return found if found is not None else http_fetch


def open_base_of(request: Request) -> str | None:
    """A test's fake Lark address from `app.state.lark_open_base`, or None on every install."""
    found = getattr(request.app.state, "lark_open_base", None)
    return found if isinstance(found, str) else None


# ---------------------------------------------------------------------- the decisions


def _not_answerable(surface: str) -> Absent:
    log.info("lark connect not answerable", surface=surface)
    return Absent("this part of the console is not answerable for this caller")


def may_switch_on(reach: EntitlementSet, use: Use, now: datetime) -> bool:
    """Whether this reach may test and switch on this use. See the named constant."""
    if use is Use.STAFF_LIST:
        return may_manage(reach, now)
    return may_connect_source(reach, USES[use].slot, now)


def _saved(name: str) -> str:
    try:
        return value_of(name)
    except InstallError:
        return ""


def _status(use: Use, *, on: bool, held: bool | None) -> str:
    if not on:
        return NOT_SWITCHED_ON
    if held is None:
        return KEY_NOT_KNOWN
    if not held:
        return NO_KEY_BEHIND_IT
    if use is Use.STAFF_LIST:
        return STAFF_ON if _saved("INSTALL_STAFF_SOURCE") == "lark" else STAFF_ELSEWHERE
    if use is Use.CHANNEL:
        return f"{SWITCHED_ON} {THE_CHANNEL_RECEIVER_IS_NOT_BUILT_YET}"
    return f"{SWITCHED_ON} {KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED}"


def _held(store: Credentials, uses: Sequence[Use]) -> tuple[VaultState, dict[Use, bool]]:
    """Whether each switched-on use's credential is held. Metadata only; one failure answers all."""
    if not store.configured:
        return VaultState.ABSENT, {}
    try:
        return VaultState.READY, {
            use: store.held(connector_key_slot(USES[use].slot)).held for use in uses
        }
    except CredentialsUnavailableError as unavailable:
        return unavailable.state, {}


def _scope_views(uses: Sequence[Use]) -> list[LarkScopeView]:
    return [
        LarkScopeView(name=one.name, what=one.what, read_only=one.read_only)
        for one in scopes_for(uses)
    ]


def _problems(found: Sequence[Problem]) -> JSONResponse:
    told = LarkProblemsView(
        problems=[
            LarkProblemView(field=one.field, code=one.code, message=one.message) for one in found
        ]
    )
    return JSONResponse(status_code=422, content=told.model_dump(mode="json"))


def _judged(
    body: LarkAsked, asked: Asking, surface: str
) -> tuple[tuple[Use, ...], JSONResponse | None]:
    """The chosen uses once the caller may switch every one on and the body is sound, or a 422.

    Unknown names are refused before the authority is asked, as a problem in words; an authority
    missing for any chosen use is the one refusal, before anything else is looked at.
    """
    chosen, named = uses_from(body.uses)
    if named:
        return chosen, _problems(named)
    if not all(may_switch_on(asked.reach, use, asked.now) for use in chosen):
        log.info("lark connect refused", surface=surface, principal=asked.caller.principal.id)
        raise _not_answerable(surface)
    found = input_problems(
        app_id=body.app_id,
        app_secret=body.app_secret,
        uses=chosen,
        platform=body.platform,
        base_link=body.base_link,
    )
    return chosen, (_problems(found) if found else None)


# ----------------------------------------------------------------------- the routes

router = APIRouter(prefix=API_PREFIX, tags=["connectors"], route_class=NoEchoRoute)

_WRITE_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    422: {"model": LarkProblemsView, "description": "What is wrong with what was sent."},
}


@router.get(LARK_PATH, response_model=LarkView, responses=COMMON_RESPONSES)
async def lark(
    request: Request,
    asked: Asked,
    uses: str = Query(default=""),
    platform: str = Query(default=""),
) -> LarkView:
    """The guide for the uses named in `uses` (comma-separated), and where each use stands.

    With no `uses`, the ones already switched on are the choice, so a returning administrator sees
    the steps for what they have.
    """
    if not permitted(screen("connectors").read, asked.reach, asked.now):
        raise _not_answerable("lark")
    on = uses_switched_on(_saved("INSTALL_LARK_USES"))
    chosen, _ = uses_from([one.strip() for one in uses.split(",") if one.strip()])
    # No `uses` asks for what is switched on; `uses=none` is an explicit choice of nothing.
    chosen = chosen if uses.strip() else on
    saved_platform = _saved("INSTALL_LARK_PLATFORM")
    where = platform if platform in LARK_PLATFORMS else saved_platform
    where = where if where in LARK_PLATFORMS else next(iter(LARK_PLATFORMS))
    vault, held = await asyncio.to_thread(_held, credentials_of(request), on)
    return LarkView(
        uses=[
            LarkUseView(
                name=use.value,
                label=USES[use].label,
                what=USES[use].what,
                scopes=[
                    LarkScopeView(name=one.name, what=one.what, read_only=one.read_only)
                    for one in USES[use].scopes
                ],
                switched_on=use in on,
                key_held=held.get(use) if use in on else None,
                status=_status(use, on=use in on, held=held.get(use)),
                may_switch_on=may_switch_on(asked.reach, use, asked.now),
            )
            for use in Use
        ],
        chosen=[use.value for use in chosen],
        steps=[
            LarkStepView(title=one.title, text=one.text)
            for one in steps_for(chosen, platform=where)
        ],
        scopes=_scope_views(chosen),
        platforms=list(LARK_PLATFORMS),
        platform=where,
        base="" if _saved("INSTALL_LARK_BASE") in ("", "unset") else _saved("INSTALL_LARK_BASE"),
        developer_console=developer_console(where),
        events_address=events_address(_saved("INSTALL_OIDC_REDIRECT_URIS")),
        channel_note=THE_CHANNEL_RECEIVER_IS_NOT_BUILT_YET,
        knowledge_note=KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED,
        test_note=THE_TEST_ONLY_READS,
        staff_sources_screen=STAFF_SOURCES_SCREEN,
        vault_told="" if vault is VaultState.READY else TOLD[vault],
    )


@router.post(LARK_TEST_PATH, response_model=LarkTestView, responses=_WRITE_RESPONSES)
async def try_lark(request: Request, body: LarkAsked, asked: Asked) -> JSONResponse:
    """Exchange the credential for a token and try each chosen use. Reads only; writes nothing."""
    chosen, refused = _judged(body, asked, "lark test")
    if refused is not None:
        return refused
    result = await probe_connection(
        fetch_of(request),
        platform=body.platform,
        app_id=body.app_id,
        app_secret=body.app_secret,
        uses=chosen,
        base_link=body.base_link,
        open_base=open_base_of(request),
    )
    log.info(
        "lark connection tested",
        principal=asked.caller.principal.id,
        accepted=result.token_ok,
        verdicts={one.use.value: one.verdict.value for one in result.uses},
    )
    told = LarkTestView(
        accepted=result.token_ok,
        told=result.told,
        uses=[
            LarkUseResultView(
                name=one.use.value,
                label=USES[one.use].label,
                verdict=one.verdict.value,
                told=one.told,
                missing=list(one.missing),
            )
            for one in result.uses
        ],
    )
    return JSONResponse(status_code=200, content=told.model_dump(mode="json"))


@router.post(LARK_PATH, response_model=LarkSavedView, responses=_WRITE_RESPONSES)
async def save_lark(request: Request, body: LarkAsked, asked: Asked) -> JSONResponse:
    """Keep the credential for each chosen use, then switch the uses on. Never copies content."""
    chosen, refused = _judged(body, asked, "lark save")
    if refused is not None:
        return refused
    credentials = credentials_of(request)
    trace_id = trace_of_request()
    value = credential_value(body.app_id, body.app_secret)
    try:
        for use in chosen:
            await credentials.keep(
                connector_key_slot(USES[use].slot),
                value,
                actor=asked.reach.principal_id,
                trace_id=trace_id,
                ent_hash=asked.reach.ent_hash(),
            )
    except CredentialProblemError:
        # Judged above by `input_problems`, so this is the two judgements parting company.
        return _problems(
            (Problem("app_secret", "shape", "That App Secret cannot be kept. Copy it again."),)
        )
    except CredentialsUnavailableError as unavailable:
        told = ErrorBody(message=TOLD[unavailable.state], trace_id=trace_id)
        return JSONResponse(
            status_code=NOT_KEPT_STATUS[unavailable.state], content=told.model_dump()
        )
    values = settings_for(chosen, platform=body.platform, base_link=body.base_link)
    await settings_of(request).save(values, asked)
    log.info(
        "lark uses switched on",
        principal=asked.caller.principal.id,
        uses=[use.value for use in chosen],
    )
    answered = LarkSavedView(
        switched_on=[use.value for use in chosen],
        told=SAVED,
        staff_sources_screen=STAFF_SOURCES_SCREEN,
    )
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))


__all__ = [
    "LARK_PATH",
    "LARK_TEST_PATH",
    "LarkAsked",
    "LarkView",
    "router",
]
