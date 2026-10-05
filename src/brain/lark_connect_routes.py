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

**The chat channel is switched on as the channel it is, not as a connector.** Its secret, with
the Encrypt Key and Verification Token Lark's events are checked with, is kept at
`providers/channel_lark` through `brain.ops.channel_store.channel_secret_slot`, the one slot the
application reads when an event arrives, and the channel's own record is written through
`brain.channel_routes.records_of` with the App ID, the platform and the bot's open id. So Connect
Lark and the Channels screen are two views of one record, and the channel is governed by the one
authority both ask. See `THE_CHAT_CHANNEL_IS_ONE_RECORD_WHICHEVER_SCREEN_SWITCHES_IT`.

**The card says whether events are arriving (M10.2.1).** The events address to paste, and the
channel's newest deliveries read by `brain.ops.channel_store`: when the last message was received,
when the last one was refused and why in words, and what the last reply came to. Nothing of any
message, and only to a reader who may switch the chat channel on.

Task ids: M11.9.4, M11.9.1, M10.2.1, M10.6.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

import structlog
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, NoEchoRoute
from brain.api_routes import Asked, Asking, wiki_withheld_of
from brain.attribution import attribute, trace_of_request
from brain.channel_routes import deliveries_of, records_of
from brain.channels.adapter import BOT_ID
from brain.channels.lark import APP_ID_FIELD, PLATFORM_FIELD, LarkSecret
from brain.connectors.lark_wiki import SpaceDeclaration
from brain.connectors.staff_directories import LARK_PLATFORMS, Fetch
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import EntitlementSet
from brain.core.errors import Absent, Failed
from brain.credential_routes import credentials_of, may_manage
from brain.gate.context import Channel
from brain.guide_views import GuideStepView, step_view
from brain.install import InstallError, hold_saved, value_of
from brain.ops.channel_store import DeliveryView, channel_secret_slot
from brain.ops.connector_admin import may_connect_source
from brain.ops.credentials import (
    TOLD,
    CredentialProblemError,
    Credentials,
    CredentialsUnavailableError,
    KeySlot,
    VaultState,
    connector_key_slot,
)
from brain.ops.install_settings import load, save
from brain.ops.lark_connect import (
    A_TEST_LEAVES_ITS_VERDICTS_AND_NOTHING_IT_READ,
    APP_ID,
    KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED,
    REDO_WHEN_REFUSED,
    SWITCHING_A_USE_OFF,
    SWITCHING_THE_STAFF_LIST_OFF,
    THE_CHANNEL_ANSWERS_AT_EACH_READERS_OWN_REACH,
    THE_CHANNEL_IS_SAVED_BEFORE_LARK_CHECKS_ITS_ADDRESS,
    THE_TEST_ONLY_READS,
    USES,
    LastTest,
    Problem,
    Use,
    bot_open_id,
    credential_value,
    developer_console,
    events_address,
    input_problems,
    last_test_from,
    last_test_value,
    probe_connection,
    redo_for,
    scope_import,
    scopes_for,
    settings_after_switching_off,
    settings_for,
    steps_for,
    uses_from,
    uses_switched_on,
)
from brain.ops.lark_wiki_live import PAGES_SKIPPED_ARE_COUNTED_FOR_ADMINISTRATORS
from brain.ops.lark_wiki_spaces import (
    A_SPACE_IS_READ_ONLY_WHERE_SOMEBODY_DECLARED_ITS_REACH,
    DEPARTMENT,
    REACHES,
    declare_space,
    declared_spaces,
    readable,
    space_id_of,
)
from brain.ops.setting_store import put, read_namespace, values_under
from brain.ops.staff_sync_run import http_fetch
from brain.people_names import names_for
from brain.routing_routes import sessions_of
from brain.tables.channel import DeliveryOutcome, Direction, RefusedBecause
from brain.tables.config import SettingType

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Who may test or switch on each use.
EACH_USE_IS_SWITCHED_ON_UNDER_THE_AUTHORITY_THAT_ALREADY_GOVERNS_IT: Final = (
    "Testing and saving send the Lark app's secret out or keep it, so each chosen use asks the "
    "authority that already governs its credential: the staff list asks the credential authority "
    "the Staff sources screen asks, and each other use asks the connector installation authority "
    "over its own slot. Holding one does not switch on another."
)

#: Why the chat channel's secret and record are the channel's own.
THE_CHAT_CHANNEL_IS_ONE_RECORD_WHICHEVER_SCREEN_SWITCHES_IT: Final = (
    "Switching the chat channel on here keeps its App Secret, Encrypt Key and Verification Token "
    "together in the channel's own vault slot, the one the application reads when an event "
    "arrives, and writes the channel's record with the App ID, the platform and the bot's id. The "
    "Channels screen reads and switches that same record, so the two screens cannot disagree about "
    "whether Lark is on."
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
#: Not `/disconnect`: `brain.connector_routes` answers `/connectors/{connector}/disconnect` for a
#: source connected on its own form, and this switches uses off rather than removing a connection.
LARK_SWITCH_OFF_PATH: Final = LARK_PATH + "/switch-off"
#: The wiki spaces declared on this install, and declaring more. See `brain.ops.lark_wiki_spaces`.
LARK_WIKI_SPACES_PATH: Final = LARK_PATH + "/wiki-spaces"

#: The most spaces one save declares, which is more than the test lists.
MOST_SPACES_A_SAVE: Final = 100

#: Where the App ID and the last test are kept, in `ops.setting`. Neither is a secret.
FACTS_NAMESPACE: Final = "connector.lark_app"
APP_ID_KEY: Final = FACTS_NAMESPACE + ".app_id"
LAST_TEST_KEY: Final = FACTS_NAMESPACE + ".last_test"

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
#: What the card says about Lark's events, for each state the channel can be in.
EVENTS_OFF: Final = (
    "The chat channel is not switched on here yet, so Lark's check of the events address is "
    "refused. Save the chat channel with its Encrypt Key and Verification Token first."
)
EVENTS_NONE_YET: Final = (
    "No event has arrived yet. Once the events address is saved in Lark, the message event is "
    "added and the version is approved, send the bot a direct message and this changes."
)
EVENTS_ARRIVING: Final = "Events are arriving."
REFUSED_EVENT_TOLD: Final = {
    RefusedBecause.BAD_SIGNATURE: (
        "The last event was refused because it did not verify: the Encrypt Key or Verification "
        "Token saved here is not the one on Lark's Encryption Strategy tab. Paste both again and "
        "save."
    ),
    RefusedBecause.UNREADABLE: (
        "The last event was not one this channel reads: it reads text messages to the bot "
        "(im.message.receive_v1) from people. A picture, a file or another app's message is "
        "refused this way and needs nothing doing."
    ),
    RefusedBecause.NO_SECRET: (
        "The last event could not be checked because the chat channel's keys are not in the "
        "vault. Save the chat channel again."
    ),
    RefusedBecause.VAULT_UNAVAILABLE: (
        "The last event could not be checked because the vault did not answer. Lark sends it "
        "again later."
    ),
    RefusedBecause.TOO_LARGE: "The last event was larger than a message is and was refused.",
    RefusedBecause.SWITCHED_OFF: EVENTS_OFF,
    RefusedBecause.NOT_CONFIGURED: EVENTS_OFF,
}
REPLY_TOLD: Final = {
    DeliveryOutcome.SENT: "The last reply was sent.",
    DeliveryOutcome.UNKNOWN: "Lark did not answer the last reply, so it may not have arrived.",
    DeliveryOutcome.REFUSED: (
        "The last reply was not sent. If Lark refused it, check the four chat scopes are added "
        "and a version with them is approved."
    ),
}

SWITCHED_OFF: Final = (
    "Switched off. The app's credential is still in the vault; remove the app in Lark's developer "
    "console too if it should stop existing."
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


class LarkVerdictView(BaseModel):
    """What the last test found for one use, in a word."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str
    verdict: str


class LarkLastTestView(BaseModel):
    """When Lark was last tested from the console and what each use came to. Nothing read."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    at: datetime
    accepted: bool
    uses: list[LarkVerdictView]


class LarkEventsView(BaseModel):
    """Where Lark's events go and whether they are arriving. Nothing of any message."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The address to paste as Lark's Request URL, or empty when the install names none.
    address: str
    switched_on: bool
    last_received: datetime | None
    last_refused: datetime | None
    #: Why the last refused event was refused, as `ops.channel_delivery` records it.
    refused_because: str | None
    last_reply: datetime | None
    reply_outcome: str | None
    told: str


class LarkView(BaseModel):
    """The guide for the uses asked about, every use's standing, and what testing does."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uses: list[LarkUseView]
    chosen: list[str]
    #: Whether any use is switched on, which is when the card shows the connection, not Connect.
    connected: bool
    #: The App ID the steps' links are built from: the one asked about, else the one saved.
    app_id: str
    steps: list[GuideStepView]
    scopes: list[LarkScopeView]
    #: Every scope the chosen uses need, as the text Lark's batch import of scopes accepts.
    scope_import: str
    platforms: list[str]
    platform: str
    #: The Base token already saved, so the form starts from it; empty when none is named.
    base: str
    developer_console: str
    #: Where the chat channel's events will arrive, or empty when this install names no address.
    events_address: str
    channel_note: str
    #: The chat channel's events, for a reader who may switch it on; None for anybody else.
    events: LarkEventsView | None = None
    knowledge_note: str
    test_note: str
    staff_sources_screen: str
    vault_told: str
    #: When Lark was last tested from the console, or None when it never was.
    last_test: LarkLastTestView | None = None
    #: Wiki pages questions matched and skipped on this process, for a reader who may switch the
    #: Wiki on; None for anybody else. See `PAGES_SKIPPED_ARE_COUNTED_FOR_ADMINISTRATORS`.
    wiki_pages_skipped: int | None = None
    wiki_pages_skipped_note: str = ""
    #: What switching a use off does, for its confirmation.
    switch_off_note: str
    staff_off_note: str


class LarkAsked(BaseModel):
    """What a test and a save send. No length on any field, so every refusal is in words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    app_id: str
    app_secret: str
    uses: list[str]
    platform: str
    base_link: str = ""
    #: The chat channel's two event keys, from Lark's Encryption Strategy tab. Kept, never shown.
    encrypt_key: str = ""
    verification_token: str = ""


class LarkSpaceView(BaseModel):
    """One wiki space Lark showed the app: its id and its name. Nothing of its pages."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    space_id: str
    name: str


class LarkUseResultView(BaseModel):
    """What testing one use came to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str
    verdict: str
    told: str
    missing: list[str]
    #: The wiki spaces Lark showed the app, for the step that declares them; empty for others.
    spaces: list[LarkSpaceView] = []
    #: The steps to go back to, by key, in the order to do them. Empty when it works.
    redo: list[str]


class LarkTestView(BaseModel):
    """The token exchange and every chosen use. Nothing was written in Lark."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool
    told: str
    uses: list[LarkUseResultView]
    #: The steps to go back to when Lark refused the credential itself. Empty otherwise.
    redo: list[str]


class DeclaredSpaceView(BaseModel):
    """One declared wiki space: its id, its reach, and its steward by name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    space_id: str
    reach: str
    #: The department's short name for a department reach; empty for the whole company.
    department: str
    #: The steward's display name, or empty when the directory names nobody for them.
    steward: str


class DeclaredSpacesView(BaseModel):
    """The spaces declared on this install, and whether this reader may declare more."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spaces: list[DeclaredSpaceView]
    may_declare: bool
    #: Why a space is read only where somebody declared it, for the step's screen.
    told: str


class SpaceAsked(BaseModel):
    """One space to declare: its id or its settings link, a reach, and for one, a department."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    space: str
    reach: str
    department: str = ""


class SpacesAsked(BaseModel):
    """The spaces one save declares."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spaces: list[SpaceAsked]


class SpacesDeclaredView(BaseModel):
    """What a save declared, by id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    declared: list[str]
    told: str


class LarkSwitchOffAsked(BaseModel):
    """The uses to switch off."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    uses: list[str]


class LarkSwitchedOffView(BaseModel):
    """What switching off did. The key stays in the vault; the sentence says so."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    switched_off: list[str]
    told: str


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


@dataclass(frozen=True)
class LarkFacts:
    """What Connect Lark keeps about the app that is not a setting: its App ID, its last test."""

    app_id: str = ""
    last_test: LastTest | None = None


class LarkFactStore(Protocol):
    """Where the App ID and the last test are kept. `StoredLarkFacts` is the real one."""

    async def read(self) -> LarkFacts: ...

    async def keep(
        self, *, app_id: str | None, last_test: dict[str, object] | None, asked: Asking
    ) -> None: ...


class StoredLarkFacts:
    """`ops.setting` under `FACTS_NAMESPACE`, written with the request's attribution.

    Two rows and not install settings: neither is a value a person sets during setup, and
    `brain.install` is the list somebody reads to configure a server. Every write is a `setting`
    entry on the ledger through `0059`'s trigger, so who tested Lark and when is there too.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def read(self) -> LarkFacts:
        async with self._sessions() as session:
            rows = values_under(await read_namespace(session, FACTS_NAMESPACE), FACTS_NAMESPACE)
        app_id = rows.get("app_id")
        test = rows.get("last_test")
        kept = app_id.value if app_id is not None and isinstance(app_id.value, str) else ""
        return LarkFacts(
            app_id=kept if APP_ID.fullmatch(kept) else "",
            last_test=None if test is None else last_test_from(test.value),
        )

    async def keep(
        self, *, app_id: str | None, last_test: dict[str, object] | None, asked: Asking
    ) -> None:
        by = asked.caller.principal.id
        async with self._sessions() as session:
            await attribute(session, asked)
            if app_id is not None:
                await put(
                    session,
                    APP_ID_KEY,
                    value_type=SettingType.STRING,
                    value=app_id,
                    description="The App ID of the company's Lark app, which is not a secret.",
                    updated_by=by,
                )
            if last_test is not None:
                await put(
                    session,
                    LAST_TEST_KEY,
                    value_type=SettingType.JSON,
                    value=dict(last_test),
                    description=A_TEST_LEAVES_ITS_VERDICTS_AND_NOTHING_IT_READ,
                    updated_by=by,
                )
            await session.commit()


class NoLarkFacts:
    """A process with no database: nothing kept, nothing to read, and the save still answers."""

    async def read(self) -> LarkFacts:
        return LarkFacts()

    async def keep(
        self, *, app_id: str | None, last_test: dict[str, object] | None, asked: Asking
    ) -> None:
        log.info("lark facts not kept", reason="no database on this process")


def facts_of(request: Request) -> LarkFactStore:
    """What `app.state.lark_facts` holds, or the database, or nothing kept without one."""
    found = getattr(request.app.state, "lark_facts", None)
    if found is not None:
        return found  # type: ignore[no-any-return]
    sessions = sessions_of(request)
    return NoLarkFacts() if sessions is None else StoredLarkFacts(sessions)


@dataclass(frozen=True)
class SpaceEntry:
    """One space a save declares, once its id is read out of what was typed."""

    space_id: str
    reach: str
    department: str


class WikiSpaceStore(Protocol):
    """Where the declared wiki spaces are kept. `StoredWikiSpaces` is the real one."""

    async def declared(self) -> tuple[SpaceDeclaration, ...]: ...

    async def declare(self, entries: Sequence[SpaceEntry], asked: Asking) -> None: ...


class StoredWikiSpaces:
    """`brain.ops.lark_wiki_spaces` over this install's database, attributed to the request."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def declared(self) -> tuple[SpaceDeclaration, ...]:
        return await declared_spaces(self._sessions)

    async def declare(self, entries: Sequence[SpaceEntry], asked: Asking) -> None:
        async with self._sessions() as session:
            await attribute(session, asked)
            for one in entries:
                await declare_space(
                    session,
                    one.space_id,
                    reach=one.reach,
                    department=one.department,
                    updated_by=asked.caller.principal.id,
                )
            await session.commit()


def spaces_of(request: Request) -> WikiSpaceStore:
    """What `app.state.lark_wiki_spaces` holds, or the database; a 500 without either."""
    found = getattr(request.app.state, "lark_wiki_spaces", None)
    if found is not None:
        return found  # type: ignore[no-any-return]
    sessions = sessions_of(request)
    if sessions is None:
        raise Failed("no database on this process")
    return StoredWikiSpaces(sessions)


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
        return f"{SWITCHED_ON} {THE_CHANNEL_ANSWERS_AT_EACH_READERS_OWN_REACH}"
    return f"{SWITCHED_ON} {KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED}"


def _held(store: Credentials, uses: Sequence[Use]) -> tuple[VaultState, dict[Use, bool]]:
    """Whether each switched-on use's credential is held. Metadata only; one failure answers all."""
    if not store.configured:
        return VaultState.ABSENT, {}
    try:
        return VaultState.READY, {use: store.held(_slot_of(use)).held for use in uses}
    except CredentialsUnavailableError as unavailable:
        return unavailable.state, {}


def _slot_of(use: Use) -> KeySlot:
    """Where a use's credential is kept: the chat channel's own slot, or the use's connector's."""
    if use is Use.CHANNEL:
        return channel_secret_slot(Channel.LARK)
    return connector_key_slot(USES[use].slot)


def events_told(
    *, switched_on: bool, recent: Sequence[DeliveryView]
) -> tuple[str, DeliveryView | None, DeliveryView | None, DeliveryView | None]:
    """What the card says about events, and the newest received, refused and reply entries."""
    received = next(
        (
            one
            for one in recent
            if one.entry.direction is Direction.INBOUND
            and one.entry.outcome in (DeliveryOutcome.ACCEPTED, DeliveryOutcome.REDELIVERED)
        ),
        None,
    )
    refused = next(
        (
            one
            for one in recent
            if one.entry.direction is Direction.INBOUND
            and one.entry.outcome is DeliveryOutcome.REFUSED
        ),
        None,
    )
    reply = next((one for one in recent if one.entry.direction is Direction.OUTBOUND), None)
    if not switched_on:
        return EVENTS_OFF, received, refused, reply
    newest = recent[0] if recent else None
    if newest is not None and newest is refused and refused.entry.reason is not None:
        told = REFUSED_EVENT_TOLD.get(refused.entry.reason, EVENTS_ARRIVING)
    elif received is None:
        told = EVENTS_NONE_YET
    else:
        told = EVENTS_ARRIVING
    if reply is not None and received is not None:
        told = f"{told} {REPLY_TOLD[reply.entry.outcome]}"
    return told, received, refused, reply


async def _events_view(request: Request, may: bool) -> LarkEventsView | None:
    """The chat channel's events for a reader who may switch it on. See the module docstring."""
    if not may:
        return None
    try:
        record = await records_of(request).get(Channel.LARK)
        recent = await deliveries_of(request).recent(Channel.LARK) if record is not None else ()
    except Failed:
        record, recent = None, ()
    switched_on = record is not None and record.enabled
    told, received, refused, reply = events_told(switched_on=switched_on, recent=recent)
    return LarkEventsView(
        address=events_address(_saved("INSTALL_OIDC_REDIRECT_URIS")),
        switched_on=switched_on,
        last_received=None if received is None else received.recorded_at,
        last_refused=None if refused is None else refused.recorded_at,
        refused_because=(
            None if refused is None or refused.entry.reason is None else refused.entry.reason.value
        ),
        last_reply=None if reply is None else reply.recorded_at,
        reply_outcome=None if reply is None else reply.entry.outcome.value,
        told=told,
    )


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
        encrypt_key=body.encrypt_key,
        verification_token=body.verification_token,
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
    app_id: str = Query(default=""),
) -> LarkView:
    """The guide for the uses named in `uses` (comma-separated), and where each use stands.

    With no `uses`, the ones already switched on are the choice, so a returning administrator sees
    the steps for what they have. `app_id`, once typed, builds every step's link to the app's own
    page; an App ID not in Lark's shape is ignored and the saved one, if any, is used instead.
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
    facts = await facts_of(request).read()
    ident = app_id.strip() if APP_ID.fullmatch(app_id.strip()) else facts.app_id
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
        connected=bool(on),
        app_id=ident,
        steps=[step_view(one) for one in steps_for(chosen, platform=where, app_id=ident)],
        scopes=_scope_views(chosen),
        scope_import=scope_import(chosen),
        platforms=list(LARK_PLATFORMS),
        platform=where,
        base="" if _saved("INSTALL_LARK_BASE") in ("", "unset") else _saved("INSTALL_LARK_BASE"),
        developer_console=developer_console(where),
        events_address=events_address(_saved("INSTALL_OIDC_REDIRECT_URIS")),
        channel_note=THE_CHANNEL_IS_SAVED_BEFORE_LARK_CHECKS_ITS_ADDRESS,
        events=await _events_view(request, may_switch_on(asked.reach, Use.CHANNEL, asked.now)),
        knowledge_note=KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED,
        test_note=THE_TEST_ONLY_READS,
        staff_sources_screen=STAFF_SOURCES_SCREEN,
        vault_told="" if vault is VaultState.READY else TOLD[vault],
        last_test=None if facts.last_test is None else _last_test_view(facts.last_test),
        wiki_pages_skipped=(
            wiki_withheld_of(request.app.state).total
            if may_switch_on(asked.reach, Use.WIKI, asked.now)
            else None
        ),
        wiki_pages_skipped_note=PAGES_SKIPPED_ARE_COUNTED_FOR_ADMINISTRATORS,
        switch_off_note=SWITCHING_A_USE_OFF,
        staff_off_note=SWITCHING_THE_STAFF_LIST_OFF,
    )


def _last_test_view(test: LastTest) -> LarkLastTestView:
    return LarkLastTestView(
        at=test.at,
        accepted=test.accepted,
        uses=[
            LarkVerdictView(name=use.value, label=USES[use].label, verdict=verdict.value)
            for use, verdict in test.verdicts
        ],
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
    # The verdicts and the instant, never anything sent or read. See the named constant.
    await facts_of(request).keep(
        app_id=None, last_test=last_test_value(result, at=asked.now), asked=asked
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
                redo=list(redo_for(one)),
                spaces=[LarkSpaceView(space_id=sid, name=name) for sid, name in one.spaces],
            )
            for one in result.uses
        ],
        redo=[] if result.token_ok else list(REDO_WHEN_REFUSED),
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
    try:
        for use in chosen:
            await credentials.keep(
                _slot_of(use),
                _kept_for(use, body),
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
    await facts_of(request).keep(app_id=body.app_id.strip(), last_test=None, asked=asked)
    if Use.CHANNEL in chosen:
        await _switch_the_channel_on(request, body, asked, trace_id)
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


@router.post(LARK_SWITCH_OFF_PATH, response_model=LarkSwitchedOffView, responses=_WRITE_RESPONSES)
async def switch_lark_off(request: Request, body: LarkSwitchOffAsked, asked: Asked) -> JSONResponse:
    """Switch the named uses off. The credential stays in the vault; see `SWITCHING_A_USE_OFF`.

    Each named use asks the authority that switches it on, so holding one does not switch
    another off. The chat channel's record is switched off with its App ID and bot id kept, so
    switching it on again is one save.
    """
    named, problems = uses_from(body.uses)
    if problems:
        return _problems(problems)
    if not all(may_switch_on(asked.reach, use, asked.now) for use in named):
        log.info("lark switch off refused", principal=asked.caller.principal.id)
        raise _not_answerable("lark switch off")
    values = settings_after_switching_off(
        named,
        saved_uses=_saved("INSTALL_LARK_USES"),
        staff_source=_saved("INSTALL_STAFF_SOURCE"),
    )
    await settings_of(request).save(values, asked)
    if Use.CHANNEL in named:
        records = records_of(request)
        held = await records.get(Channel.LARK)
        if held is not None and held.enabled:
            await records.save(
                Channel.LARK,
                enabled=False,
                tenant=dict(held.tenant),
                actor=asked.caller.principal.id,
                ent_hash=asked.reach.ent_hash(),
                trace_id=trace_of_request(),
            )
    log.info(
        "lark uses switched off",
        principal=asked.caller.principal.id,
        uses=[use.value for use in named],
    )
    answered = LarkSwitchedOffView(
        switched_off=[use.value for use in named],
        told=SWITCHED_OFF,
    )
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))


SPACES_DECLARED: Final = (
    "The spaces are declared. The Brain answers from their pages at the reach you chose, and you "
    "are their steward."
)


@router.get(LARK_WIKI_SPACES_PATH, response_model=DeclaredSpacesView, responses=COMMON_RESPONSES)
async def lark_wiki_spaces(request: Request, asked: Asked) -> DeclaredSpacesView:
    """The wiki spaces declared on this install, each with its reach and its steward's name."""
    if not permitted(screen("connectors").read, asked.reach, asked.now):
        raise _not_answerable("lark wiki spaces")
    declared = await spaces_of(request).declared()
    names = await names_for(request, {one.owner_id for one in declared})
    return DeclaredSpacesView(
        spaces=[
            DeclaredSpaceView(
                space_id=one.space_id,
                reach=one.visibility.level.value,
                department=one.visibility.department or "",
                steward=names.get(one.owner_id, ""),
            )
            for one in declared
        ],
        may_declare=may_switch_on(asked.reach, Use.WIKI, asked.now),
        told=A_SPACE_IS_READ_ONLY_WHERE_SOMEBODY_DECLARED_ITS_REACH,
    )


def space_problems(body: SpacesAsked, by: str) -> tuple[list[SpaceEntry], list[Problem]]:
    """The spaces read out of what was typed, and a problem by field for each that cannot be.

    A space is judged by `brain.ops.lark_wiki_spaces.readable`, the check its writer makes, so a
    save either declares every space it names or none of them.
    """
    if not body.spaces:
        return [], [Problem("spaces", "blank", "Choose at least one space to declare.")]
    if len(body.spaces) > MOST_SPACES_A_SAVE:
        return [], [
            Problem("spaces", "too_many", f"Declare at most {MOST_SPACES_A_SAVE} spaces at once.")
        ]
    entries: dict[str, SpaceEntry] = {}
    problems: list[Problem] = []
    for index, one in enumerate(body.spaces):
        where = f"spaces.{index}"
        space_id = space_id_of(one.space)
        reach = one.reach.strip()
        department = one.department.strip()
        if not space_id:
            problems.append(
                Problem(
                    f"{where}.space",
                    "shape",
                    "Paste the link of the space's settings page, which contains /wiki/space/ "
                    "and a number, or the number itself.",
                )
            )
            continue
        if reach not in REACHES:
            problems.append(
                Problem(f"{where}.reach", "unknown", "Choose the whole company or one department.")
            )
            continue
        if reach == DEPARTMENT and not department:
            problems.append(
                Problem(
                    f"{where}.department",
                    "blank",
                    "Choose the department whose people may be told this space's pages.",
                )
            )
            continue
        if not readable(space_id, reach, department, by=by):
            problems.append(
                Problem(
                    f"{where}.department",
                    "shape",
                    "That is not a department's short name. Choose one from the list.",
                )
            )
            continue
        entries[space_id] = SpaceEntry(space_id, reach, department if reach == DEPARTMENT else "")
    return list(entries.values()), problems


@router.post(LARK_WIKI_SPACES_PATH, response_model=SpacesDeclaredView, responses=_WRITE_RESPONSES)
async def declare_lark_wiki_spaces(
    request: Request, body: SpacesAsked, asked: Asked
) -> JSONResponse:
    """Declare wiki spaces: each one's reach, with the caller as its steward. See the module."""
    if not may_switch_on(asked.reach, Use.WIKI, asked.now):
        log.info("lark wiki spaces refused", principal=asked.caller.principal.id)
        raise _not_answerable("lark wiki spaces")
    entries, problems = space_problems(body, asked.caller.principal.id)
    if problems:
        return _problems(problems)
    await spaces_of(request).declare(entries, asked)
    log.info("lark wiki spaces declared", principal=asked.caller.principal.id, count=len(entries))
    answered = SpacesDeclaredView(declared=[one.space_id for one in entries], told=SPACES_DECLARED)
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))


def _kept_for(use: Use, body: LarkAsked) -> str:
    """The value kept for a use: the chat channel's three secrets together, or the credential."""
    if use is Use.CHANNEL:
        return LarkSecret(
            app_secret=body.app_secret.strip(),
            encrypt_key=body.encrypt_key.strip(),
            verification_token=body.verification_token.strip(),
        ).kept()
    return credential_value(body.app_id, body.app_secret)


async def _switch_the_channel_on(
    request: Request, body: LarkAsked, asked: Asking, trace_id: str
) -> None:
    """Write the chat channel's record, switched on. See the named constant.

    The bot's id is read from Lark; an app whose version is not released yet has no bot to read,
    and then the id the record already holds is kept, so a second save after release fills it.
    """
    records = records_of(request)
    held = await records.get(Channel.LARK)
    bot = await bot_open_id(
        fetch_of(request),
        platform=body.platform,
        app_id=body.app_id,
        app_secret=body.app_secret,
        open_base=open_base_of(request),
    )
    known = bot or ("" if held is None else held.tenant.get(BOT_ID, ""))
    tenant = {APP_ID_FIELD: body.app_id.strip(), PLATFORM_FIELD: body.platform}
    if known:
        tenant[BOT_ID] = known
    await records.save(
        Channel.LARK,
        enabled=True,
        tenant=tenant,
        actor=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_id,
    )
    log.info("lark chat channel switched on", bot_known=bool(known))


__all__ = [
    "LARK_PATH",
    "LARK_SWITCH_OFF_PATH",
    "LARK_TEST_PATH",
    "LARK_WIKI_SPACES_PATH",
    "LarkAsked",
    "LarkView",
    "router",
]
