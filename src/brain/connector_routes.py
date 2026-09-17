"""The connectors screen over HTTP: what this install connected, what each may read, and two writes.

`brain.console.connector_trust` decides what a reader may be told about a connected source,
`brain.ops.connector_admin` decides who may connect one and what a connection must be,
`brain.ops.credentials` keeps its key and `brain.ops.connector_store` holds the rows. This module
asks each of them in order and adds no second opinion about any of it.

**A router of its own, and the reason is the act rather than the noun.** `brain.install_routes`
answers about the deployment, where there is no name to guess and no row belonging to anybody.
This answers about which outside systems this company reads, where a name is exactly the thing a
refusal must not confirm: `brain.connectors.federation.NAMING_A_SOURCE_IS_A_DISCLOSURE` is the
rule, and `brain.console.operate.reachable_connectors` is where it is applied.

**The screen's read is asked before anything else is.** The capability is read out of the screen
registry, for `brain.install_routes.A_SECOND_SPELLING_OF_A_CAPABILITY_IS_THE_ONE_THAT_GOES_STALE`'s
reason, and it is asked with the console plane through `brain.console.reads.permitted`, before
the database or the vault is: a caller holding no grant is refused identically on an install with
twelve connections, with none, and with no database, so nobody learns whether this company reads
anything at all by reaching the port.

**Each write asks `brain.ops.connector_admin.may_connect_source` before it judges what was sent**,
and a caller it refuses is refused in the one way this router refuses anybody, whether or not the
source is connected, whether the install runs a vault, and whether the source is one the console
can connect. That order is `brain.credential_routes`' for the same reason.

**What a connect answers, and in which status.** 200 with the source, when, when its key was
written and what that means. 422 with every problem by field and code, of which a source already
connected is one, because disconnecting it first is something the person does. 409 when the
install runs no vault or the vault refused, and 503 when it did not answer, each as `ErrorBody`
with `brain.ops.connector_admin.TOLD`'s sentence, and nothing recorded as connected in any of the
three. A disconnect answers 200 or the one refusal: a source that is not connected is a 404 for a
caller who may manage it, who can see the list, so the refusal hides nothing from them.

**A connection grants the data steward the source's declared reads**, computed here from the
manifest the connection is pinned to and written by the store in the connection's transaction.
See `brain.identity.data_steward.A_CONNECTION_GRANTS_THE_STEWARD_WHAT_THE_SOURCE_DECLARES`.

**No credential out, and none in a log.** The router is `brain.api.NoEchoRoute`, so a body refused
by its model names the field and does not repeat the key. Every answer is built from a source's
name, times, booleans and sentences. What is logged is the surface, the source's name and the
principal, never the settings and never the key.

**What connecting starts and what it still does not is served beside the screen**, as
`connecting`, for `brain.skill_routes`' reason: the worker began reading connected sources on
2026-09-17 and the sentence changed in the same commit as the behaviour. So are the two
confirmations, so the words a person agrees to are the words of the system that does it.

**How reading each source went is the worker's record, read after the connections the reader may be
told of.** `brain.ops.connector_sync_store.StoredSyncStates` answers the newest attempt per live
connection, and `brain.console.connector_trust.connected_rows` looks one up only for a connection it
admitted, so an attempt against a source this reader may not be told of reaches no response.

**A process with no database answers a sentence and never an empty list**, which is
`brain.install_routes.AN_UNREAD_SOURCE_IS_NOT_AN_EMPTY_ONE`: an empty list of connectors reads as an
install that reads nothing, which is the reassuring answer to "what does this system have access
to".

Rejected, and kept from the first version of this module: building a registry out of the manifest
builders in `brain.connectors` at start. Each takes the identifiers of one company's install, so a
module calling them with values of its own would be this repository holding a client's
configuration. The identifiers arrive from the person connecting the source, and are kept in that
install's database.

Task ids: M42.6.5, M27.9.9
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import Final

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, model_validator

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, NoEchoRoute
from brain.api_routes import Asked
from brain.audit.record import ConnectorChange
from brain.connectors.manifest import manifest_digest
from brain.connectors.registry import may_install
from brain.console.connector_trust import (
    COPY_POLICY,
    NOTHING_HERE_CAN_SAY_WHICH_SOURCES_ARE_CONNECTED,
    NOTHING_HERE_COUNTS_TODAYS_CALLS,
    ConnectedRow,
    TrustRow,
    admitted_connections,
    connected_rows,
)
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, BrainError, Failed
from brain.credential_routes import credentials_of
from brain.identity.data_steward import declared_capabilities
from brain.ops.connectable import (
    CONNECTABLE,
    MAX_SETTING_CHARS,
    NOT_FROM_THE_CONSOLE,
    SettingProblem,
    blank_sentence,
    given,
    key_reference,
)
from brain.ops.connector_admin import (
    CONNECTED,
    CONNECTING_A_SOURCE,
    DISCONNECTED,
    DISCONNECTING_A_SOURCE,
    KEY_SENTENCES,
    SOURCE_FIELD,
    TOLD,
    VAULT_SAYS,
    WHAT_CONNECTING_A_SOURCE_STARTS,
    connection_problems,
    key_problems,
    may_connect_source,
)
from brain.ops.connector_store import (
    Connection,
    ConnectorRecords,
    ConnectorTakenError,
    NotConnectedError,
    StoredConnections,
)
from brain.ops.connector_sync_store import ConnectorSyncRecords, StoredSyncStates
from brain.ops.credentials import (
    MAX_CREDENTIAL_CHARS,
    CredentialProblemError,
    Credentials,
    CredentialsUnavailableError,
    Held,
    VaultState,
    connector_key_slot,
)
from brain.routing_routes import sessions_of

log = structlog.get_logger()


# ------------------------------------------------------------------ the capability

#: Every source this install reads, and what each was connected to.
CONNECTORS_READ: Final[Capability] = screen("connectors").read.requires

#: Where the screen is read and a source connected, and where one is disconnected.
CONNECTORS_PATH: Final = "/connectors"
DISCONNECT_PATH: Final = CONNECTORS_PATH + "/{connector}/disconnect"

#: The status a connect that kept nothing answers, by what the vault's state was.
NOT_KEPT_STATUS: Final = {
    VaultState.ABSENT: 409,
    VaultState.REFUSED: 409,
    VaultState.UNREACHABLE: 503,
}


# ------------------------------------------------------------------------ the shapes


class TrustView(BaseModel):
    """One connector, with what it is trusted to read said in words.

    `brain.console.connector_trust.TrustRow`, copied field by field rather than from `__dict__`,
    for the reason `brain.install_routes.fact_view` gives: a field added to `TrustRow` would
    otherwise arrive in a response because a copy loop was generous, and the fields this screen
    has refused are exactly the ones somebody would add.

    No field for a credential, a vault path, a host or an endpoint. See
    `brain.console.connector_trust.A_VAULT_PATH_IS_NOT_A_CREDENTIAL_AND_IS_STILL_NOT_A_CONSOLE_ROW`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    wiring: str
    credential: str
    budget: str
    projected_fields: int
    checked_at: str | None
    health: str
    lifecycle: str
    serving: bool
    version: str
    reaches: str
    access: str
    permission_sync: str


class ConnectedView(BaseModel):
    """One source this install connected: who, when, its key, and what it may read.

    `key_held` is None when the vault could not be asked, which `ConnectorsView.vault_told` says in
    words; None is "not known" and never "not held". `trust` is None when this release cannot
    rebuild what the source was connected as, and `declaration` says so.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    connected_by: str
    connected_at: datetime
    key_held: bool | None
    key_written_at: datetime | None
    pinned: bool
    declaration: str
    trust: TrustView | None
    #: Whether this reader may disconnect it. Their own grant, and it narrows nothing.
    may_disconnect: bool
    #: When the worker last read it to the end, or None when it never has.
    last_synced_at: datetime | None
    #: When the worker may next attempt it, or None when nothing has attempted it.
    next_sync_at: datetime | None
    #: What reading it came to, or why nothing reads it, in the worker's own words.
    sync: str


class CopyLineView(BaseModel):
    """One line of what this system copies out of a source and what it never does.

    `brain.console.connector_trust.CopyLine`, field by field. Served rather than written into a
    page, because it is the answer to the question a client's own auditor asks and it must be
    one document: a console holding its own copy of it is a second policy, edited by whoever is
    next in the browser.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    what: str
    verdict: str
    why: str


class SettingView(BaseModel):
    """One identifier a source is connected with, as the form asks for it.

    `blank` is the sentence the connect route answers when this setting is left blank, served so a
    console can say it beside the field before the confirmation opens, in the route's own words.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str
    hint: str
    max_chars: int
    blank: str


class ConnectableView(BaseModel):
    """A source the console can connect, and what the form asks for. The same on every install."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str
    settings: list[SettingView]
    credential_label: str
    credential_hint: str
    #: Whether this reader may connect it. Their own grant over this source.
    may_connect: bool


class NotConnectableView(BaseModel):
    """A source this release has a connector for and the console cannot connect, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str
    why: str


class ConnectorsView(BaseModel):
    """The connected sources this reader may be told exist, or why there is no list.

    Exactly one of a list and a sentence, refused in the model rather than left to whatever
    draws it, which is `brain.install_routes.LimitsView`'s construction and its reason: an empty
    list of connectors and an absent one draw the same nothing, and one of them means this
    install reads no outside system while the other means nothing here looked.

    Everything else is on every response, including the unread one: what connecting does and does
    not do, the sources that could be connected and why the others cannot, and the copy policy,
    because each is a statement about this release rather than about this install.

    No count and no total, on either half.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    connectors: list[ConnectedView] | None = None
    #: Why there is no list. Required when there is none, empty when there is one.
    unread: str = ""
    #: What connecting a source does and what still does not happen.
    connecting: str
    #: The confirmations' consequences, in the words a person agrees to.
    confirm_connect: str
    confirm_disconnect: str
    #: What is copied out of any source and what never is.
    copy_policy: list[CopyLineView]
    #: Why the budget column states a ceiling and draws no bar of today's use.
    budget_unread: str
    #: Whether this reader holds the authority to connect any source. It narrows nothing.
    may_connect: bool
    #: The vault's state, and a sentence when there is something to say about it.
    vault: VaultState
    vault_told: str
    connectable: list[ConnectableView]
    not_connectable: list[NotConnectableView]
    #: The longest key the form accepts, which the server refuses above in words.
    key_max_chars: int
    #: What the connect route answers for a blank key, for the reason `SettingView.blank` gives.
    key_blank: str

    @model_validator(mode="after")
    def _exactly_one(self) -> ConnectorsView:
        if self.connectors is not None and self.unread:
            msg = (
                "a connector list is set and a reason for having none is set beside it, so a "
                "reader cannot tell an install that reads nothing from one nothing looked at"
            )
            raise ValueError(msg)
        if self.connectors is None and not self.unread:
            msg = (
                "no connector list and nothing saying why, which renders as an install that "
                f"reads no outside system. {NOTHING_HERE_CAN_SAY_WHICH_SOURCES_ARE_CONNECTED}"
            )
            raise ValueError(msg)
        return self


class ConnectAsked(BaseModel):
    """A connection: the source, its settings, and its key. No length on any field on purpose.

    `brain.ops.connector_admin.connection_problems` judges every one in words, and a length on the
    model would be refused by FastAPI in a shape that names no sentence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    connector: str
    settings: dict[str, str]
    credential: str


class ConnectorProblemView(BaseModel):
    """One thing wrong with what was sent: the field, a stable code, and what to do."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    code: str
    message: str


class ConnectorProblemsView(BaseModel):
    """Everything wrong with what was sent. Nothing was written."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    problems: list[ConnectorProblemView]


class ConnectorChangedView(BaseModel):
    """What one write changed, when, and what that means. Never a key, never a setting."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connector: str
    change: ConnectorChange
    changed_at: datetime
    key_written_at: datetime | None
    told: str


def trust_view(one: TrustRow) -> TrustView:
    """One row, copied field by field. See `TrustView` for why it is written out."""
    return TrustView(
        name=one.name,
        wiring=one.wiring,
        credential=one.credential,
        budget=one.budget,
        projected_fields=one.projected_fields,
        checked_at=None if one.checked_at is None else one.checked_at.isoformat(),
        health=one.health,
        lifecycle=one.lifecycle,
        serving=one.serving,
        version=one.version,
        reaches=one.reaches,
        access=one.access,
        permission_sync=one.permission_sync,
    )


def connected_view(one: ConnectedRow, *, may_disconnect: bool) -> ConnectedView:
    """One connection, copied field by field, for `TrustView`'s reason."""
    return ConnectedView(
        name=one.name,
        connected_by=one.connected_by,
        connected_at=one.connected_at,
        key_held=one.key_held,
        key_written_at=one.key_written_at,
        pinned=one.pinned,
        declaration=one.declaration,
        trust=None if one.trust is None else trust_view(one.trust),
        may_disconnect=may_disconnect,
        last_synced_at=one.last_synced_at,
        next_sync_at=one.next_sync_at,
        sync=one.sync,
    )


# ---------------------------------------------------------------------- the refusals


def _not_answerable(surface: str) -> Absent:
    """The one refusal this router makes.

    `surface` reaches a log and never a response, which is `brain.install_routes._not_answerable`
    rule: `brain.app.handle_brain_error` sends `Absent.public_message`, and a body naming the
    screen would tell a caller which capability they are short of. Nothing about a connector
    reaches either, which matters more here than on any other console surface: a refusal that
    named one would be the disclosure the whole list is filtered to prevent.
    """
    log.info("connector surface not answerable", surface=surface)
    return Absent("this part of the console is not answerable for this caller")


def _permitted(reach: EntitlementSet, now: datetime) -> None:
    """Refuse unless this caller may open this screen, before anything else is consulted.

    `brain.console.reads.permitted` rather than a `holds` call on the capability, because a
    console read asks for the plane as well; see
    `brain.install_routes.A_SCREENS_CAPABILITY_IS_HALF_OF_WHAT_IT_ASKS_FOR`.
    """
    if not permitted(screen("connectors").read, reach, now):
        raise _not_answerable("connectors")


# ------------------------------------------------------------------------- the wiring


def records_of(request: Request) -> ConnectorRecords | None:
    """What `app.state.connector_records` holds, or the database, or None without one.

    None rather than a fault, because the read answers a process with no database in a sentence;
    the writes turn it into a process fault.
    """
    found = getattr(request.app.state, "connector_records", None)
    if isinstance(found, ConnectorRecords):
        return found
    sessions = sessions_of(request)
    return None if sessions is None else StoredConnections(sessions)


def sync_records_of(request: Request) -> ConnectorSyncRecords | None:
    """What `app.state.connector_sync_records` holds, or the database, or None without one.

    None is answered as no attempt recorded, which the row says in words, rather than as a fault:
    the listing is still true without it.
    """
    found = getattr(request.app.state, "connector_sync_records", None)
    if isinstance(found, ConnectorSyncRecords):
        return found
    sessions = sessions_of(request)
    return None if sessions is None else StoredSyncStates(sessions)


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.credential_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def keys_held(store: Credentials, names: Sequence[str]) -> tuple[VaultState, dict[str, Held]]:
    """Whether each named source's key is held, or nothing known and the vault's state.

    One failure answers for the whole list, for `brain.credential_routes.listing`'s reason. An
    install naming no vault is `ABSENT` without asking, and a list with nothing on it asks nothing.
    """
    if not store.configured:
        return VaultState.ABSENT, {}
    try:
        return VaultState.READY, {one: store.held(connector_key_slot(one)) for one in names}
    except CredentialsUnavailableError as unavailable:
        return unavailable.state, {}


def _problems(found: Sequence[SettingProblem]) -> JSONResponse:
    told = ConnectorProblemsView(
        problems=[
            ConnectorProblemView(field=one.field, code=one.code, message=one.message)
            for one in found
        ]
    )
    return JSONResponse(status_code=422, content=told.model_dump(mode="json"))


def _not_kept(state: VaultState) -> JSONResponse:
    body = ErrorBody(message=TOLD[state], trace_id=_trace_id())
    return JSONResponse(status_code=NOT_KEPT_STATUS[state], content=body.model_dump())


def _page(
    reach: EntitlementSet,
    now: datetime,
    *,
    connections: list[ConnectedView] | None,
    vault: VaultState,
) -> ConnectorsView:
    return ConnectorsView(
        connectors=connections,
        unread="" if connections is not None else NOTHING_HERE_CAN_SAY_WHICH_SOURCES_ARE_CONNECTED,
        connecting=WHAT_CONNECTING_A_SOURCE_STARTS,
        confirm_connect=CONNECTING_A_SOURCE,
        confirm_disconnect=DISCONNECTING_A_SOURCE,
        copy_policy=[
            CopyLineView(what=one.what, verdict=one.verdict, why=one.why) for one in COPY_POLICY
        ],
        budget_unread=NOTHING_HERE_COUNTS_TODAYS_CALLS,
        may_connect=may_install(reach, now),
        vault=vault,
        vault_told=VAULT_SAYS[vault],
        connectable=[
            ConnectableView(
                name=kind.name,
                label=kind.label,
                settings=[
                    SettingView(
                        name=one.name,
                        label=one.label,
                        hint=one.hint,
                        max_chars=MAX_SETTING_CHARS,
                        blank=blank_sentence(one),
                    )
                    for one in kind.settings
                ],
                credential_label=kind.credential_label,
                credential_hint=kind.credential_hint,
                may_connect=may_connect_source(reach, kind.name, now),
            )
            for kind in CONNECTABLE.values()
        ],
        not_connectable=[
            NotConnectableView(name=one.name, label=one.label, why=one.why)
            for one in NOT_FROM_THE_CONSOLE.values()
        ],
        key_max_chars=MAX_CREDENTIAL_CHARS,
        key_blank=KEY_SENTENCES["blank"],
    )


router = APIRouter(prefix=API_PREFIX, tags=["connectors"], route_class=NoEchoRoute)

_WRITE_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    422: {"model": ConnectorProblemsView, "description": "What is wrong with what was sent."},
}


# ----------------------------------------------------------------------- the routes


@router.get(CONNECTORS_PATH, response_model=ConnectorsView, responses=COMMON_RESPONSES)
async def connectors(request: Request, asked: Asked) -> ConnectorsView:
    """Which sources this install connected, and what each one is trusted to read (M42.6.5).

    The screen's read first, then the database, then the vault for the keys of the connections
    this reader may be told of and no others, then the worker's attempts, which are asked only when
    there is a connection to describe.
    """
    _permitted(asked.reach, asked.now)
    credentials = credentials_of(request)
    records = records_of(request)
    if records is None:
        vault = VaultState.READY if credentials.configured else VaultState.ABSENT
        return _page(asked.reach, asked.now, connections=None, vault=vault)
    found: tuple[Connection, ...] = await records.connected()
    shown = admitted_connections(found, asked.reach, asked.now)
    vault, held = await asyncio.to_thread(keys_held, credentials, [one.connector for one in shown])
    sync = sync_records_of(request)
    synced = {} if sync is None or not shown else await sync.states()
    rows = connected_rows(shown, asked.reach, now=asked.now, held=held, vault=vault, synced=synced)
    return _page(
        asked.reach,
        asked.now,
        connections=[
            connected_view(one, may_disconnect=may_connect_source(asked.reach, one.name, asked.now))
            for one in rows
        ],
        vault=vault,
    )


@router.post(CONNECTORS_PATH, response_model=ConnectorChangedView, responses=_WRITE_RESPONSES)
async def connect(request: Request, body: ConnectAsked, asked: Asked) -> JSONResponse:
    """Connect a source and keep its key, or write nothing and say why."""
    if not may_connect_source(asked.reach, body.connector, asked.now):
        log.info("connecting a source not answerable", principal=asked.caller.principal.id)
        raise _not_answerable("connect")
    found = connection_problems(body.connector, body.settings, body.credential)
    if found:
        return _problems(found)
    credentials = credentials_of(request)
    if not credentials.configured:
        return _not_kept(VaultState.ABSENT)
    records = records_of(request)
    if records is None:
        raise Failed("no database on this process")
    kind = CONNECTABLE[body.connector]
    settings = given(kind, body.settings)
    manifest = kind.build(settings, key_reference(kind.name))
    digest = manifest_digest(manifest)
    slot = connector_key_slot(kind.name)
    actor = asked.reach.principal_id
    trace_id = _trace_id()
    ent_hash = asked.reach.ent_hash()
    written: list[datetime | None] = []

    async def keep_key() -> datetime | None:
        kept = await credentials.keep(
            slot, body.credential, actor=actor, trace_id=trace_id, ent_hash=ent_hash
        )
        written.append(kept.set_at)
        return kept.set_at

    try:
        connection = await records.connect(
            connector=kind.name,
            settings=settings,
            digest=digest,
            actor=actor,
            trace_id=trace_id,
            ent_hash=ent_hash,
            keep_key=keep_key,
            declared=declared_capabilities(manifest),
        )
    except ConnectorTakenError:
        return _problems(
            (
                SettingProblem(
                    field=SOURCE_FIELD,
                    code="connected",
                    message=(
                        f"{kind.label} is already connected. Disconnect it first to connect it "
                        "again with other settings or a new key."
                    ),
                ),
            )
        )
    except CredentialProblemError:
        # Judged above, so this is unreachable unless the two judgements part company; answered
        # in this router's words rather than as a fault, because nothing was written.
        return _problems(key_problems(body.credential))
    except CredentialsUnavailableError as unavailable:
        return _not_kept(unavailable.state)
    except BrainError:
        raise
    except Exception as exc:
        # Broad for `brain.api_routes.answer`'s reason, and the type name alone for
        # `brain.credential_routes`': an exception's message is a place a value can be quoted.
        raise Failed(f"connecting a source: {type(exc).__name__}") from exc
    log.info("source connected", connector=kind.name, principal=actor)
    answered = ConnectorChangedView(
        connector=connection.connector,
        change=ConnectorChange.CONNECTED,
        changed_at=connection.connected_at,
        key_written_at=written[0] if written else None,
        told=CONNECTED,
    )
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))


@router.post(DISCONNECT_PATH, response_model=ConnectorChangedView, responses=COMMON_RESPONSES)
async def disconnect(request: Request, connector: str, asked: Asked) -> ConnectorChangedView:
    """Disconnect a source and record who did. Its key stays in the vault, as the answer says."""
    if not may_connect_source(asked.reach, connector, asked.now):
        log.info("disconnecting a source not answerable", principal=asked.caller.principal.id)
        raise _not_answerable("disconnect")
    records = records_of(request)
    if records is None:
        raise Failed("no database on this process")
    try:
        at = await records.disconnect(
            connector,
            actor=asked.reach.principal_id,
            trace_id=_trace_id(),
            ent_hash=asked.reach.ent_hash(),
        )
    except NotConnectedError as absent:
        raise _not_answerable("disconnect") from absent
    log.info("source disconnected", connector=connector, principal=asked.reach.principal_id)
    return ConnectorChangedView(
        connector=connector,
        change=ConnectorChange.DISCONNECTED,
        changed_at=at,
        key_written_at=None,
        told=DISCONNECTED,
    )
