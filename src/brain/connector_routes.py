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

**The module's list and one source's page are two more reads, under `/console/connectors`.** The
list is every source this release ships, as `brain.console.connector_detail.source_rows` narrows
it, over the list contract (`brain.listing`), so it searches, filters and orders like every other
module's list. A source's page is its declaration, what its connection keeps and reads live, the
department it answers to, its history, and the agents and skills that use it; its export is the
same record as a document, with no key in it. They are under `/console/` rather than beside
`/connectors/{connector}/disconnect`, because a read at `/connectors/{connector}` would answer
`GET /connectors/lark-app` before Connect Lark's router is asked, which is registered after this
one.

**Two more writes, each asked of the authority a connection asks.** An edit is a disconnection and
a connection in one transaction (`brain.ops.connector_store.
AN_EDIT_IS_A_DISCONNECTION_AND_A_CONNECTION_IN_ONE_TRANSACTION`) and leaves the key alone; replacing
a key is a credential write through `brain.ops.credentials.Credentials.keep`, recorded in the
ledger by its own trigger, and leaves the connection alone. A source with no live connection is the
one refusal for both, for a caller who may manage it and so can see the list.

Rejected, and kept from the first version of this module: building a registry out of the manifest
builders in `brain.connectors` at start. Each takes the identifiers of one company's install, so a
module calling them with values of its own would be this repository holding a client's
configuration. The identifiers arrive from the person connecting the source, and are kept in that
install's database.

Task ids: M42.6.5, M27.9.9, M38.4.1.1, M27.11.9, M27.15.39, M27.15.58, M11.7.7, M11.2.6
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, model_validator

from brain.agent_routes import (
    _tool_registry,
    every_agent,
    install_of,
    installs_for,
    record_of,
    steward_names,
    viewer_of,
)
from brain.agents.model import visible_agent_ids
from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, NoEchoRoute, Page
from brain.api_routes import Asked, Asking
from brain.audit.record import ConnectorChange
from brain.connectors.contract import ConnectorContractError
from brain.connectors.declaration import shipped
from brain.connectors.manifest import ConnectorManifest, manifest_digest
from brain.connectors.registry import may_install
from brain.console.connector_detail import (
    LARK_SOURCES,
    NO_DEPARTMENT,
    ConnectFrom,
    SourceRow,
    SourceStatus,
    agents_naming,
    ceiling_for,
    kept_index,
    may_be_told_of,
    read_live,
    reading_in_words,
    skills_from,
    source_rows,
)
from brain.console.connector_trust import (
    ACCESS_SAYS,
    COPY_POLICY,
    NOTHING_HERE_CAN_SAY_WHICH_SOURCES_ARE_CONNECTED,
    NOTHING_HERE_COUNTS_TODAYS_CALLS,
    PERMISSION_SYNC_SAYS,
    ConnectedRow,
    EvidenceRow,
    TrustRow,
    admitted_connections,
    connected_rows,
    evidence_rows,
    scope_in_words,
)
from brain.console.reads import permitted
from brain.console.screens import screen
from brain.console.skill_library import may_read_library
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, BrainError, Failed
from brain.credential_routes import credentials_of
from brain.identity.data_steward import declared_capabilities
from brain.install import InstallError, value_of
from brain.listing import Column, ListAsked, Listing
from brain.ops.connectable import (
    CONNECTABLE,
    MAX_SETTING_CHARS,
    NOT_FROM_THE_CONSOLE,
    NotConnectableError,
    SettingProblem,
    blank_sentence,
    given,
    key_reference,
    manifest_for,
    settings_problems,
)
from brain.ops.connector_admin import (
    CONNECTED,
    CONNECTING_A_SOURCE,
    DISCONNECTED,
    DISCONNECTING_A_SOURCE,
    EDITED,
    EDITING_A_SOURCE,
    KEY_REPLACED,
    KEY_SENTENCES,
    NO_KEY_IS_EXPORTED,
    NOTHING_TO_EDIT,
    REPLACING_A_KEY,
    SOURCE_FIELD,
    TOLD,
    VAULT_SAYS,
    WHAT_CONNECTING_A_SOURCE_STARTS,
    connection_problems,
    key_problems,
    may_connect_source,
)
from brain.ops.connector_recordings import recorded_in_words
from brain.ops.connector_store import (
    Connection,
    ConnectionRecord,
    ConnectorChanges,
    ConnectorRecords,
    ConnectorTakenError,
    NotConnectedError,
    StoredConnections,
)
from brain.ops.connector_sync import SyncState
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
from brain.ops.lark_connect import uses_switched_on
from brain.routing_routes import sessions_of
from brain.skill_routes import SkillLibrary

log = structlog.get_logger()


# ------------------------------------------------------------------ the capability

#: Every source this install reads, and what each was connected to.
CONNECTORS_READ: Final[Capability] = screen("connectors").read.requires

#: Where the screen is read and a source connected, and where one is disconnected.
CONNECTORS_PATH: Final = "/connectors"
DISCONNECT_PATH: Final = CONNECTORS_PATH + "/{connector}/disconnect"
#: Where a connected source's settings are edited, and its key replaced.
EDIT_PATH: Final = CONNECTORS_PATH + "/{connector}/edit"
KEY_PATH: Final = CONNECTORS_PATH + "/{connector}/key"

#: The module's list, one source's page and its export. See the module docstring for the prefix.
SOURCES_PATH: Final = "/console/connectors"
SOURCE_PATH: Final = SOURCES_PATH + "/{connector}"
EXPORT_PATH: Final = SOURCE_PATH + "/export"

#: The Install setting Connect Lark saves its switched-on uses under.
LARK_USES_SETTING: Final = "INSTALL_LARK_USES"

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


class EvidenceView(BaseModel):
    """One connector in this release: tested against recorded responses, and live on this install.

    `brain.console.connector_trust.EvidenceRow`, field by field. Every connector in the release is
    listed, connected or not, and a source this reader may not be told of carries the same live
    sentence as one nobody connected. See `brain.console.connector_trust.RECORDED_IS_NOT_LIVE`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str
    #: What this release tested it against, from `brain.ops.connector_recordings`.
    recorded: str
    #: Whether a live credential is held on this install, or why that is not shown.
    credential: str
    #: Whether it has been read live here. Empty when no connection is shown.
    live_read: str
    last_read_live_at: datetime | None


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
    #: Every connector in this release, tested against recorded responses or not, and live or not.
    evidence: list[EvidenceView]
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


class ConnectorEditAsked(BaseModel):
    """An edit: the settings the source should be connected with. No key: an edit leaves it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    settings: dict[str, str]


class ConnectorKeyAsked(BaseModel):
    """A replacement key. No length on the field, for `ConnectAsked`'s reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    credential: str


class ConnectorEditedView(BaseModel):
    """What an edit changed: the source connected again with new settings, and when."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connector: str
    changed_at: datetime
    told: str


class ConnectorKeyReplacedView(BaseModel):
    """When a replaced key was written, and what that means. Never the key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connector: str
    key_written_at: datetime | None
    told: str


class ConnectorSourceRowView(BaseModel):
    """One source on the module's list. `brain.console.connector_detail.SourceRow`, by field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str
    status: SourceStatus
    health: str | None
    department: str | None
    last_read_at: datetime | None
    connected_at: datetime | None
    declaration_changed: bool
    connect_from: ConnectFrom
    may_manage: bool


class ConnectorSourcesPage(Page[ConnectorSourceRowView]):
    """One page of every source this release ships. No count, of either half."""


class ConnectorSettingValueView(BaseModel):
    """One identifier a source is connected with: its name, its label, and what was typed.

    An identifier the source gave the company (an organisation id, a helpdesk address), which is
    what the manifest was built from. Never a key: a key is not a setting and has no field here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    label: str
    value: str


class ConnectorKeptEntityView(BaseModel):
    """One kind of record a connection keeps an index of, by field name. Never a value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity: str
    fields: list[str]


class ConnectorLiveReadView(BaseModel):
    """One thing a connection reads live when a question needs it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool: str
    entity: str
    description: str


class ConnectorHistoryView(BaseModel):
    """One connection of a source, live or ended, with who and when. Actors are principal ids."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connected_at: datetime
    connected_by: str
    disconnected_at: datetime | None
    disconnected_by: str | None
    settings: list[ConnectorSettingValueView]


class ConnectorAgentView(BaseModel):
    """An agent whose manifest names this source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    display_name: str


class ConnectorSkillView(BaseModel):
    """A skill whose tools come from this source: its newest version and that version's state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str
    state: str


class ConnectorSourceView(BaseModel):
    """One source whole: its row, its declaration, its connection's index, history and users.

    Everything about the connection is empty for a source this reader may not be told is
    connected, exactly as for one nobody connected. The confirmations are the words a person
    agrees to before an edit or a key replacement.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: ConnectorSourceRowView
    #: Why it is not connected from this screen, or empty when it is.
    elsewhere: str
    #: How it is read, from its own declaration.
    reading: str
    #: Its verified call ceiling in words, or that nobody has verified one.
    ceiling: str
    #: What this release tested it against.
    recorded: str
    #: What the department line says when the connection names none; empty when not connected.
    department_says: str
    settings: list[ConnectorSettingValueView]
    keeps: list[ConnectorKeptEntityView]
    reads_live: list[ConnectorLiveReadView]
    history: list[ConnectorHistoryView]
    #: Display names by principal id, for the actors in `history`. Missing where none is known.
    people: dict[str, str]
    agents: list[ConnectorAgentView]
    skills: list[ConnectorSkillView]
    confirm_edit: str
    confirm_key: str


class ConnectorExportedConnectionView(BaseModel):
    """The live connection in an export: its settings, the digest agreed to, who and when."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    settings: dict[str, str]
    digest: str
    connected_at: datetime
    connected_by: str
    #: Whether what it declares today is what was agreed to.
    declaration_agreed: bool


class ConnectorExportedDeclarationView(BaseModel):
    """What the live connection's manifest declares today, in the words the screen uses."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    wiring: str
    access: str
    reaches: str
    permission_sync: str
    department: str | None
    keeps: list[ConnectorKeptEntityView]
    reads_live: list[ConnectorLiveReadView]


class ConnectorExportView(BaseModel):
    """A connection record as a document: its declaration and history, and no key (M27.15.39)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connector: str
    label: str
    exported_at: datetime
    #: Why there is no key in it.
    credential: str
    connection: ConnectorExportedConnectionView | None
    declaration: ConnectorExportedDeclarationView | None
    reading: str
    ceiling: str
    recorded: str
    history: list[ConnectorHistoryView]


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


def evidence_views(rows: tuple[ConnectedRow, ...] | None) -> list[EvidenceView]:
    """Every connector this release names, with both halves of its evidence, in the form's order."""
    labels = {one.name: one.label for one in CONNECTABLE.values()}
    labels.update({one.name: one.label for one in NOT_FROM_THE_CONSOLE.values()})
    return [evidence_view(one) for one in evidence_rows(rows, labels)]


def evidence_view(one: EvidenceRow) -> EvidenceView:
    """One row, copied field by field, for `TrustView`'s reason."""
    return EvidenceView(
        name=one.name,
        label=one.label,
        recorded=one.recorded,
        credential=one.credential,
        live_read=one.live_read,
        last_read_live_at=one.last_read_live_at,
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
    evidence: list[EvidenceView],
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
        evidence=evidence,
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
        return _page(
            asked.reach, asked.now, connections=None, vault=vault, evidence=evidence_views(None)
        )
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
        evidence=evidence_views(rows),
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


# ------------------------------------------------------------------ the module's list


#: What the module's list may search, filter and order by: the fields a row shows.
SOURCES: Final[Listing[ConnectorSourceRowView]] = Listing(
    name="connector-sources",
    columns=(
        Column("label", lambda row: row.label, search=True, sort=True),
        Column("name", lambda row: row.name, search=True),
        Column("status", lambda row: row.status.value, filter=True, sort=True),
        Column("health", lambda row: row.health, filter=True),
        Column("department", lambda row: row.department, search=True, filter=True, sort=True),
        Column("connect_from", lambda row: row.connect_from.value, filter=True),
        Column("last_read_at", lambda row: row.last_read_at, sort=True),
    ),
    key=lambda row: row.name,
    order="label",
)
SourcesQuery = Annotated[ListAsked, Depends(SOURCES.query())]


def changes_of(request: Request) -> ConnectorChanges | None:
    """What `app.state.connector_records` holds when it edits too, or the database, or None."""
    found = getattr(request.app.state, "connector_records", None)
    if isinstance(found, ConnectorChanges):
        return found
    sessions = sessions_of(request)
    return None if sessions is None else StoredConnections(sessions)


def _library_of(request: Request) -> SkillLibrary | None:
    """What `app.state.skill_library` holds, or the database's library, or None without one."""
    found = getattr(request.app.state, "skill_library", None)
    if isinstance(found, SkillLibrary):
        return found
    sessions = sessions_of(request)
    if sessions is None:
        return None
    from brain.ops.skill_store import StoredSkills

    return StoredSkills(sessions)


def lark_switched_on() -> frozenset[str]:
    """The shipped sources Connect Lark has switched on, by name, or none when nothing says so."""
    try:
        saved = value_of(LARK_USES_SETTING)
    except InstallError:
        return frozenset()
    on = uses_switched_on(saved)
    return frozenset(name for name, use in LARK_SOURCES.items() if use in on)


def manifest_or_none(one: Connection | None) -> ConnectorManifest | None:
    """The manifest a connection's settings build today, or None when this build cannot."""
    if one is None:
        return None
    try:
        return manifest_for(one.connector, one.settings)
    except (NotConnectableError, ConnectorContractError):
        return None


def row_view(one: SourceRow) -> ConnectorSourceRowView:
    """One row, copied field by field, for `TrustView`'s reason."""
    return ConnectorSourceRowView(
        name=one.name,
        label=one.label,
        status=one.status,
        health=one.health,
        department=one.department,
        last_read_at=one.last_read_at,
        connected_at=one.connected_at,
        declaration_changed=one.declaration_changed,
        connect_from=one.connect_from,
        may_manage=one.may_manage,
    )


def settings_view(connector: str, settings: Mapping[str, str]) -> list[ConnectorSettingValueView]:
    """A connection's settings under the labels its form asks for them by, in the form's order."""
    declared = CONNECTABLE[connector].settings if connector in CONNECTABLE else ()
    labels = {one.name: one.label for one in declared}
    order = [one.name for one in declared]
    names = [*(name for name in order if name in settings), *sorted(set(settings) - set(order))]
    return [
        ConnectorSettingValueView(name=name, label=labels.get(name, name), value=settings[name])
        for name in names
    ]


def history_view(one: ConnectionRecord) -> ConnectorHistoryView:
    """One connection of the source's history, copied field by field."""
    return ConnectorHistoryView(
        connected_at=one.connected_at,
        connected_by=one.connected_by,
        disconnected_at=one.disconnected_at,
        disconnected_by=one.disconnected_by,
        settings=settings_view(one.connector, one.settings),
    )


@dataclass(frozen=True)
class _Source:
    """Everything one source's page and its export are built from, already narrowed."""

    row: SourceRow
    live: Connection | None
    manifest: ConnectorManifest | None
    history: tuple[ConnectionRecord, ...]
    told_of: bool


async def _one_source(request: Request, connector: str, asked: Asking) -> _Source:
    """One shipped source as this reader may be told of it.

    The live connection is looked up only among the admitted ones and the history only for a
    source `may_be_told_of` admits, so a source the reader may not see is described exactly as one
    nobody connected. See `brain.console.connector_detail.
    A_SOURCE_NOBODY_CONNECTED_AND_ONE_YOU_MAY_NOT_SEE_READ_ALIKE`.
    """
    records = records_of(request)
    if records is None:
        raise Failed("no database on this process")
    admitted = admitted_connections(await records.connected(), asked.reach, asked.now)
    live = next((one for one in admitted if one.connector == connector), None)
    manifest = manifest_or_none(live)
    sync = sync_records_of(request)
    synced: Mapping[str, SyncState] = {} if sync is None or live is None else await sync.states()
    [row] = [
        one
        for one in source_rows(
            connections=() if live is None else (live,),
            synced=synced,
            lark_on=lark_switched_on(),
            manifests={} if manifest is None else {connector: manifest},
            reader=asked.reach,
            now=asked.now,
        )
        if one.name == connector
    ]
    told_of = may_be_told_of(connector, asked.reach, asked.now)
    changes = changes_of(request)
    history = await changes.history(connector) if told_of and changes is not None else ()
    return _Source(row=row, live=live, manifest=manifest, history=history, told_of=told_of)


async def _people(request: Request, principal_ids: Collection[str]) -> dict[str, str]:
    """Display names for the actors a history names, or none without a database."""
    sessions = sessions_of(request)
    if sessions is None or not principal_ids:
        return {}
    async with sessions() as session:
        return await steward_names(session, sorted(principal_ids))


async def _agents_naming(
    request: Request, connector: str, asked: Asking
) -> list[ConnectorAgentView]:
    """The agents this reader may see whose effective manifest names this source (M27.15.58).

    The audience is decided before an install is read, the roster's own order, so nothing about an
    agent this reader may not see is fetched on their behalf.
    """
    sessions = sessions_of(request)
    if sessions is None:
        return []
    async with sessions() as session:
        rows = (await session.execute(every_agent())).scalars().all()
        records = [record for record in (record_of(row) for row in rows) if record is not None]
        visible = visible_agent_ids(records, viewer_of(asked))
        shown = {one.agent_id: one for one in records if one.agent_id in visible}
        pairs = (await session.execute(installs_for(list(shown)))).all() if shown else []
    named: dict[str, tuple[str, ...]] = {}
    for instance_row, version_row in pairs:
        record = shown.get(instance_row.id)
        install = None if record is None else install_of(instance_row, version_row, record)
        if record is not None and install is not None:
            named[record.agent_id] = install.connectors
    found = agents_naming(
        connector,
        connectors_by_agent=named,
        names={agent_id: one.display_name for agent_id, one in shown.items()},
        visible=frozenset(shown),
    )
    return [
        ConnectorAgentView(agent_id=one.agent_id, display_name=one.display_name) for one in found
    ]


async def _skills_from(request: Request, connector: str, asked: Asking) -> list[ConnectorSkillView]:
    """The skills whose tools come from this source, for a reader of the skill library."""
    registry = _tool_registry(request)
    library = _library_of(request)
    if registry is None or library is None or not may_read_library(asked.reach, asked.now):
        return []
    found = skills_from(connector, await library.library(), registry)
    return [
        ConnectorSkillView(name=one.name, version=one.version, state=one.state) for one in found
    ]


def _kept(manifest: ConnectorManifest | None) -> list[ConnectorKeptEntityView]:
    return [
        ConnectorKeptEntityView(entity=one.entity, fields=list(one.fields))
        for one in kept_index(manifest)
    ]


def _live(manifest: ConnectorManifest | None) -> list[ConnectorLiveReadView]:
    return [
        ConnectorLiveReadView(tool=one.tool, entity=one.entity, description=one.description)
        for one in read_live(manifest)
    ]


@router.get(SOURCES_PATH, response_model=ConnectorSourcesPage, responses=COMMON_RESPONSES)
async def connector_sources(
    request: Request, asked: Asked, listed: SourcesQuery
) -> ConnectorSourcesPage:
    """Every source this release ships, each with what this reader may be told of it (M27.11.9).

    The screen's read first, then the connections the reader may be told of, then the worker's
    attempts only when there is a connection to describe.
    """
    _permitted(asked.reach, asked.now)
    plan = SOURCES.plan(listed, reader=asked.caller.principal.id)
    records = records_of(request)
    if records is None:
        raise Failed("no database on this process")
    admitted = admitted_connections(await records.connected(), asked.reach, asked.now)
    sync = sync_records_of(request)
    synced: Mapping[str, SyncState] = {} if sync is None or not admitted else await sync.states()
    manifests = {
        one.connector: built for one in admitted if (built := manifest_or_none(one)) is not None
    }
    rows = source_rows(
        connections=admitted,
        synced=synced,
        lark_on=lark_switched_on(),
        manifests=manifests,
        reader=asked.reach,
        now=asked.now,
    )
    page = plan.page([row_view(one) for one in rows])
    return ConnectorSourcesPage(items=list(page.items), next_cursor=page.next_cursor)


@router.get(SOURCE_PATH, response_model=ConnectorSourceView, responses=COMMON_RESPONSES)
async def connector_source(request: Request, connector: str, asked: Asked) -> ConnectorSourceView:
    """One source whole: its declaration, index, history and the agents and skills that use it.

    A name this release does not ship is the screen's one refusal. A shipped source this reader may
    not be told is connected is answered as one nobody connected, with no history and no users.
    """
    _permitted(asked.reach, asked.now)
    declared = shipped().get(connector)
    if declared is None:
        raise _not_answerable("connector source")
    one = await _one_source(request, connector, asked)
    actors = {
        actor
        for entry in one.history
        for actor in (entry.connected_by, entry.disconnected_by)
        if actor
    }
    return ConnectorSourceView(
        source=row_view(one.row),
        elsewhere=declared.not_from_the_console,
        reading=reading_in_words(connector),
        ceiling=ceiling_for(connector, one.manifest),
        recorded=recorded_in_words(connector),
        department_says=(
            NO_DEPARTMENT if one.live is not None and one.row.department is None else ""
        ),
        settings=[] if one.live is None else settings_view(connector, one.live.settings),
        keeps=_kept(one.manifest),
        reads_live=_live(one.manifest),
        history=[history_view(entry) for entry in one.history],
        people=await _people(request, actors),
        agents=await _agents_naming(request, connector, asked) if one.told_of else [],
        skills=await _skills_from(request, connector, asked) if one.told_of else [],
        confirm_edit=EDITING_A_SOURCE,
        confirm_key=REPLACING_A_KEY,
    )


@router.get(EXPORT_PATH, response_model=ConnectorExportView, responses=COMMON_RESPONSES)
async def export_connector(request: Request, connector: str, asked: Asked) -> ConnectorExportView:
    """One source's connection record as a document, with its declaration and history (M27.15.39).

    No key, whatever the vault holds: the document is built from the connection rows and the
    manifest, neither of which has anywhere to hold one, and says so in `credential`.
    """
    _permitted(asked.reach, asked.now)
    declared = shipped().get(connector)
    if declared is None:
        raise _not_answerable("connector export")
    one = await _one_source(request, connector, asked)
    manifest = one.manifest
    log.info("connection record exported", connector=connector, principal=asked.reach.principal_id)
    return ConnectorExportView(
        connector=connector,
        label=declared.label,
        exported_at=asked.now,
        credential=NO_KEY_IS_EXPORTED,
        connection=(
            None
            if one.live is None
            else ConnectorExportedConnectionView(
                settings=dict(one.live.settings),
                digest=one.live.digest,
                connected_at=one.live.connected_at,
                connected_by=one.live.connected_by,
                declaration_agreed=manifest is not None
                and manifest_digest(manifest) == one.live.digest,
            )
        ),
        declaration=(
            None
            if manifest is None
            else ConnectorExportedDeclarationView(
                version=manifest.version,
                wiring=manifest.transport.value,
                access=ACCESS_SAYS[manifest.credential.mode],
                reaches=scope_in_words(manifest.scope),
                permission_sync=PERMISSION_SYNC_SAYS[manifest.permission_sync],
                department=one.row.department,
                keeps=_kept(manifest),
                reads_live=_live(manifest),
            )
        ),
        reading=reading_in_words(connector),
        ceiling=ceiling_for(connector, manifest),
        recorded=recorded_in_words(connector),
        history=[history_view(entry) for entry in one.history],
    )


# ------------------------------------------------------------ editing and replacing a key


async def _live_connection(request: Request, connector: str) -> Connection | None:
    records = records_of(request)
    if records is None:
        raise Failed("no database on this process")
    return next((one for one in await records.connected() if one.connector == connector), None)


@router.post(EDIT_PATH, response_model=ConnectorEditedView, responses=_WRITE_RESPONSES)
async def edit(
    request: Request, connector: str, body: ConnectorEditAsked, asked: Asked
) -> JSONResponse:
    """Connect a source again with new settings, as one change, or write nothing and say why.

    Asked of the authority a connection asks, before anything is judged. See
    `brain.ops.connector_store.AN_EDIT_IS_A_DISCONNECTION_AND_A_CONNECTION_IN_ONE_TRANSACTION`.
    """
    if not may_connect_source(asked.reach, connector, asked.now):
        log.info("editing a source not answerable", principal=asked.caller.principal.id)
        raise _not_answerable("edit")
    kind = CONNECTABLE.get(connector)
    if kind is None:
        # `connection_problems`' own answer for a source this screen cannot connect, which is the
        # first problem it finds and the only one it judges.
        return _problems(connection_problems(connector, body.settings, ""))
    found = settings_problems(kind, body.settings)
    if found:
        return _problems(found)
    changes = changes_of(request)
    current = await _live_connection(request, connector)
    if changes is None:
        raise Failed("no database on this process")
    if current is None:
        raise _not_answerable("edit")
    settings = given(kind, body.settings)
    manifest = kind.build(settings, key_reference(kind.name))
    digest = manifest_digest(manifest)
    if dict(current.settings) == settings and current.digest == digest:
        return _problems(
            (SettingProblem(field=SOURCE_FIELD, code="unchanged", message=NOTHING_TO_EDIT),)
        )
    actor = asked.reach.principal_id
    try:
        connection = await changes.reconnect(
            connector=kind.name,
            settings=settings,
            digest=digest,
            actor=actor,
            trace_id=_trace_id(),
            ent_hash=asked.reach.ent_hash(),
            declared=declared_capabilities(manifest),
        )
    except NotConnectedError as absent:
        raise _not_answerable("edit") from absent
    except BrainError:
        raise
    except Exception as exc:
        # The type name alone, for `connect`'s reason.
        raise Failed(f"editing a source: {type(exc).__name__}") from exc
    log.info("source edited", connector=kind.name, principal=actor)
    answered = ConnectorEditedView(
        connector=kind.name, changed_at=connection.connected_at, told=EDITED
    )
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))


@router.post(KEY_PATH, response_model=ConnectorKeyReplacedView, responses=_WRITE_RESPONSES)
async def replace_key(
    request: Request, connector: str, body: ConnectorKeyAsked, asked: Asked
) -> JSONResponse:
    """Write a new key for a connected source, and change nothing about the connection (M11.2.6).

    The key is judged before the vault is asked, the vault before the database, and a source with
    no live connection is the one refusal: a key for a source nothing reads is a key nobody asked
    for. The write is recorded by `ops.credential_write`'s own trigger.
    """
    if not may_connect_source(asked.reach, connector, asked.now):
        log.info("replacing a key not answerable", principal=asked.caller.principal.id)
        raise _not_answerable("replace key")
    found = key_problems(body.credential)
    if found:
        return _problems(found)
    credentials = credentials_of(request)
    if not credentials.configured:
        return _not_kept(VaultState.ABSENT)
    if await _live_connection(request, connector) is None:
        raise _not_answerable("replace key")
    actor = asked.reach.principal_id
    try:
        kept = await credentials.keep(
            connector_key_slot(connector),
            body.credential,
            actor=actor,
            trace_id=_trace_id(),
            ent_hash=asked.reach.ent_hash(),
        )
    except CredentialProblemError:
        return _problems(key_problems(body.credential))
    except CredentialsUnavailableError as unavailable:
        return _not_kept(unavailable.state)
    log.info("source key replaced", connector=connector, principal=actor)
    answered = ConnectorKeyReplacedView(
        connector=connector, key_written_at=kept.set_at, told=KEY_REPLACED
    )
    return JSONResponse(status_code=200, content=answered.model_dump(mode="json"))
