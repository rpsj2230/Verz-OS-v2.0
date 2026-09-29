"""Setting a credential from the console, and seeing which are held, without reading one back.

`brain.ops.credentials` is the mechanism and argues the design. This module is the HTTP half: a
read that says, per slot, whether a secret is held and when it was written, and a write that puts
one in and answers with the same two facts. **Nothing a caller can send makes a response carry a
value**: the write's body is the only place a credential appears, its refusal by the model is
`brain.api.NoEchoRoute`'s and names the field without repeating it, and every other answer is
built from `Held`, `Kept` and a sentence.

**The capability is `admin:credential`, held over everything.** An `admin:` verb, so
`brain.gate.admission` already withholds it from a password-only session and from any channel
but the console, and neither ceiling is written here. Held over everything, because a provider
key is used by every question anybody in the company asks: a grant scoped to one department is a
grant to change what every other department's questions are sent with. The test is the one
`brain.identity.first_administrator.holds_everywhere` makes for signing people in. See
`A_KEY_EVERY_QUESTION_USES_IS_SET_BY_SOMEBODY_WHO_GOVERNS_EVERY_QUESTION`.

**The capability is asked before the vault is, and before the slot is looked up.** A caller who
may not manage credentials is refused in one set of words whether the slot exists, whether the
install runs a vault and whether it answers, so the difference between a 404, a 409 and a 503 is
never readable by somebody who could not have acted on it. That is
`brain.routing_routes`' order for the same reason. A slot that does not exist is the same refusal
again: the slots are a closed list in the source, so naming one is not a disclosure, and one
answer is still simpler to keep than two.

**What a write answers, and in which status.** 200 with the slot, that it is held, when, whether
this process now uses it and a sentence saying what that means for the others. 422 with problems
named by code and said in words, judged before anything was sent. 409 when the install runs no
vault or the vault refused, and 503 when it did not answer, each with the vault's state and the
sentence from `brain.ops.credentials.TOLD` as its message; nothing was stored anywhere in
any of the three.

**The sentences are English and the codes are stable.** This console has no language selection,
and `brain.locale` is where the wizard's sentences live; a code beside each sentence is what a
translated console would key on. That is a gap and not a decision.

Rejected: a DELETE. Removing a provider key takes an install's questions off that provider
between one request and the next, the policy grants the application no delete, and the thing an
administrator actually does is replace a key, which is a write.

Rejected: answering the write with the value's length, a prefix, or a fingerprint so a person can
tell which key they saved. Each is part of the secret, a fingerprint of a key is a lookup for
anybody holding a candidate, and the time it was written is what tells two saves apart.

**The Credentials screen reads these routes, and they cover every slot the install declares.**
`GET /credentials` is one page of `brain.ops.credential_catalogue`'s slots on `brain.listing`'s
contract, each with its holder, whether a value is held, when it was written and the environment
variable that outranks it, beside the vault's seal, the policies its token carries, whether
live reads are waiting for the policy to be loaded again, and whether this process holds the
install's template signing key (`brain.ops.template_key`), as a state and never the key.
`GET /credentials/{family}/{name}` is one slot's page: what it is for and what to ask for, when
its value was last used where anything
records that, and its history from the audit ledger. `PUT` writes any of them: the relay's
password under `password`, the object store's key pair as two fields in one version, and a
source's key or a channel's secret only once its slot holds one, because the first goes in where
the thing is set up (`A_FIRST_KEY_GOES_IN_WHERE_ITS_THING_IS_SET_UP`).

**A slot's history names who wrote it, and nothing else about anybody.** A reader here holds
`admin:credential` over everything, which is the authority to replace any of these keys, and the
architecture's I4 asks who wrote each one. Every other figure a person or a connection could be
learned from is asked only where the reader would be told of it anyway: a source's last read for
a connection the Connectors screen's rule admits, a channel's last delivery for a channel the
reader governs. A figure left out reads as one never recorded. See
`A_FIGURE_ABOUT_A_CONNECTION_IS_SHOWN_WHERE_THE_CONNECTION_IS`.

Task ids: M27.8.7, M27.11.10, M27.15.50, M13.8.10
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated, Final, Protocol

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody, NoEchoRoute
from brain.api_routes import Asked, Asking
from brain.audit.record import credential_subject_id
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.errors import Absent, BrainError, Failed
from brain.firstrun import GRANTED_BY
from brain.install import value_of
from brain.listing import Column, ListAsked, Listing
from brain.ops.credential_catalogue import (
    FIELD_LABELS,
    FIRST_SET_ELSEWHERE,
    FORMAT_TOLD,
    KIND_ORDER,
    LIVE_READS_SAY,
    VALUE_LABELS,
    CatalogueReport,
    DeclaredSlot,
    LiveReads,
    ReadBy,
    SlotKind,
    declared_at,
    declared_slots,
    offered,
    read_catalogue,
    takes_effect_told,
)
from brain.ops.credential_write_store import Change, StoredCredentialHistory
from brain.ops.credentials import (
    KEY_FIELD,
    TOLD,
    CredentialProblemError,
    Credentials,
    CredentialsUnavailableError,
    Held,
    InUse,
    Kept,
    VaultState,
    told_in_use,
)
from brain.ops.object_store import BACKEND_SETTING
from brain.ops.template_key import TEMPLATE_KEY_SAYS, TemplateKeyState
from brain.ops.template_key import state_of as template_key_state_of
from brain.ops.vault_status import Seal, SlotState, TokenPolicy, VaultStatusReader

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why a figure about a connection or a channel is asked only for a reader told of it.
A_FIGURE_ABOUT_A_CONNECTION_IS_SHOWN_WHERE_THE_CONNECTION_IS: Final = (
    "When a source's key was last used says the source is connected and being read, and when a "
    "channel's secret was last used says the channel is taking messages. Each is asked only for a "
    "reader the Connectors screen would tell of the connection, or who governs the channel, and "
    "is otherwise left out, which reads exactly as a figure nothing recorded."
)

#: Why the capability must be held over everything and not only held.
A_KEY_EVERY_QUESTION_USES_IS_SET_BY_SOMEBODY_WHO_GOVERNS_EVERY_QUESTION: Final = (
    "A provider key is sent with every question anybody in the company asks that provider. A "
    "grant of admin:credential scoped to one department would let its holder change what every "
    "other department's questions go out with, and redirect them to an account they chose, so a "
    "scoped grant is not a grant here. Held over everything is the test, as it is for signing "
    "people in."
)

# ----------------------------------------------------------------- the capability

#: Setting a credential and reading which are held. An `admin:` verb, over everything.
CREDENTIAL_AUTHORITY: Final = Capability(value="admin:credential")

#: Where the slots are listed. A write is one slot below it, as `{family}/{name}`.
CREDENTIALS_PATH: Final = "/credentials"

#: The status a write that kept nothing answers, by what the vault's state was.
NOT_KEPT_STATUS: Final = {
    VaultState.ABSENT: 409,
    VaultState.REFUSED: 409,
    VaultState.UNREACHABLE: 503,
}

# ------------------------------------------------------------------------ the shapes


class SlotView(BaseModel):
    """One slot: what it is for, whether it holds a secret, and when that was written.

    `held` and `set_at` are None when the vault could not be asked, which `CredentialsView.vault`
    says in words. A None here is "not known", and never "not held".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: str
    description: str
    held: bool | None
    set_at: datetime | None


class CredentialsView(BaseModel):
    """Every slot, and the state of the vault they were asked of."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vault: VaultState
    told: str
    slots: tuple[SlotView, ...]


class CredentialAsked(BaseModel):
    """What a write carries: `value` for a slot of one field, `values` by field for one of several.

    No length on the model: `problems_with` judges each in words. Exactly one of the two is used,
    and which is the slot's to say (`DeclaredSlot.fields`), so the model does not guess.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str | None = None
    values: dict[str, str] | None = None


class CredentialKeptView(BaseModel):
    """A secret is held in a slot. Never the secret, its length, or anything derived from it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: str
    held: bool
    set_at: datetime | None
    in_use: InUse
    told: str


class CredentialProblemView(BaseModel):
    """One thing wrong with what was sent: the field, a stable code, and what to do."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    code: str
    message: str


class CredentialProblemsView(BaseModel):
    """Everything wrong with what was sent. Nothing was stored."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    problems: tuple[CredentialProblemView, ...]


class CredentialNotKeptView(ErrorBody):
    """The vault could not take it. Nothing was stored anywhere.

    `ErrorBody`'s message and trace id, so a console drawing any failure draws this one's
    sentence and a reference somebody can quote, and two fields of its own, so a screen that
    knows this route can say which slot and which state. A shape of its own under the API
    prefix, named in `tests/unit/test_api.py` beside the one other route that has one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: str
    vault: VaultState


class VaultOverview(BaseModel):
    """The vault as the Credentials screen says it: its seal, its token, and live reads."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seal: Seal
    told: str
    #: Why every slot is unknown when the vault is open and they are, or empty.
    slots_unread: str
    token_policy: TokenPolicy
    #: The policies the vault says this process's token carries. Names, never the token.
    token_policies: tuple[str, ...]
    token_told: str
    live_reads: LiveReads
    live_reads_told: str
    #: Whether this process holds the install's template signing key, and the sentence saying so.
    #: A state and never the key: see `brain.ops.template_key`.
    template_key: TemplateKeyState
    template_key_told: str


class CredentialRow(BaseModel):
    """One slot on the Credentials list. Whether a value is held and when, never the value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: str
    family: str
    name: str
    kind: SlotKind
    holder: str
    state: SlotState
    #: None when the vault could not be asked, which `VaultOverview` says in words.
    held: bool | None
    set_at: datetime | None
    #: The environment variable that wins over this slot on every start, or None.
    outranked_by: str | None
    read_by: ReadBy
    #: Whether this screen offers a value for it now, and the sentence saying why not.
    writable: bool
    write_told: str


class CredentialsPage(BaseModel):
    """One page of the slots, and the vault they were read from. No count anywhere."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vault: VaultOverview
    items: tuple[CredentialRow, ...]
    next_cursor: str | None


class CredentialFieldView(BaseModel):
    """One field a slot's form asks for: its name in the request, its label, what it accepts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    label: str
    accepts: str


class CredentialChangeView(BaseModel):
    """One write the audit ledger holds for a slot: when, and who by name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    at: datetime
    by: str
    #: The ledger's id for who wrote it, for the page's Advanced section.
    by_id: str


class CredentialDetailView(BaseModel):
    """One slot's page. Nothing on it could hold a value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vault: VaultOverview
    row: CredentialRow
    description: str
    fields: tuple[CredentialFieldView, ...]
    ask_for: tuple[str, ...]
    never: tuple[str, ...]
    takes_effect: InUse
    takes_effect_told: str
    #: Whether anything records when this kind of value is used.
    use_recorded: bool
    last_used_at: datetime | None
    last_used_told: str
    #: Newest first. None when this process has no database to read the ledger from.
    history: tuple[CredentialChangeView, ...] | None
    history_told: str


# ------------------------------------------------------------------------ the decisions


def may_manage(reach: EntitlementSet, now: datetime) -> bool:
    """Whether this reach holds `CREDENTIAL_AUTHORITY` over everything, at this instant."""
    scope = reach.scope_for(CREDENTIAL_AUTHORITY, now)
    return scope is not None and scope.is_unrestricted()


def listing(store: Credentials) -> CredentialsView:
    """Every slot as `store` holds it, in path order, or every slot unknown with the reason.

    One failure answers for the whole list rather than per slot, because a vault that did not
    answer for one slot will not answer for the next, and a list half known and half not is a
    list somebody reads as half held.
    """
    slots = list(store.slots())
    try:
        found: list[Held] = [store.held(slot) for slot in slots]
    except CredentialsUnavailableError as unavailable:
        return CredentialsView(
            vault=unavailable.state,
            told=TOLD[unavailable.state],
            slots=tuple(
                SlotView(slot=one.path, description=one.description, held=None, set_at=None)
                for one in slots
            ),
        )
    return CredentialsView(
        vault=VaultState.READY,
        told=TOLD[VaultState.READY],
        slots=tuple(
            SlotView(slot=one.path, description=one.description, held=it.held, set_at=it.set_at)
            for one, it in zip(slots, found, strict=True)
        ),
    )


def _not_answerable() -> Absent:
    """The one refusal this router makes. See the module note on the order of the checks."""
    return Absent("credentials are not answerable for this caller")


#: What the list may search, filter and order by: the fields a row shows.
SLOT_LIST: Final[Listing[CredentialRow]] = Listing(
    name="credentials",
    columns=(
        Column("holder", lambda row: row.holder, search=True, sort=True),
        Column("slot", lambda row: row.slot, search=True, sort=True),
        Column("kind", lambda row: row.kind.value, filter=True),
        Column("group", lambda row: KIND_ORDER[row.kind], sort=True),
        Column("state", lambda row: row.state.value, filter=True, sort=True),
        Column("set_at", lambda row: row.set_at, sort=True),
        Column("outranked", lambda row: row.outranked_by is not None, filter=True),
    ),
    key=lambda row: row.slot,
    order="group",
)
SlotQuery = Annotated[ListAsked, Depends(SLOT_LIST.query())]

#: What "last used" means for each kind of slot, or why nothing records it.
LAST_USED_SAYS: Final[dict[SlotKind, str]] = {
    SlotKind.PROVIDER: "The last question sent to this provider, from its health record.",
    SlotKind.CONNECTOR: "The last time the worker read this source with its key.",
    SlotKind.CHANNEL: "The last message this secret verified or sent.",
    SlotKind.RELAY: "Nothing records when mail is sent with the password, so no time is shown.",
    SlotKind.STORE: "The key pair is read once, when the system starts, and nothing records it.",
}

#: The kinds whose use a table records. See `brain.ops.credential_write_store.LAST_USED`.
USE_RECORDED: Final = frozenset({SlotKind.PROVIDER, SlotKind.CONNECTOR, SlotKind.CHANNEL})

HISTORY_SAYS: Final = (
    "Every value written into this slot from the console or the setup wizard, from the audit "
    "ledger. A value written at the server with the vault's command line is in the vault's own "
    "audit log instead."
)
NO_HISTORY_READABLE: Final = "This process has no database, so the audit ledger cannot be read."

#: Who wrote a key, when the ledger's actor has no name on the staff list.
SETUP_WIZARD: Final = "The setup wizard"
NOBODY_NAMED: Final = "A person with no name on record"


def overview(report: CatalogueReport, template_key: TemplateKeyState) -> VaultOverview:
    return VaultOverview(
        seal=report.seal,
        told=report.told,
        slots_unread=report.slots_unread,
        token_policy=report.token.state,
        token_policies=report.token.policies,
        token_told=report.token.told,
        live_reads=report.live_reads,
        live_reads_told=LIVE_READS_SAY[report.live_reads],
        template_key=template_key,
        template_key_told=TEMPLATE_KEY_SAYS[template_key],
    )


def row_view(one: DeclaredSlot, report: CatalogueReport, store: Credentials) -> CredentialRow:
    """One slot as the list draws it, from what its metadata said and this process's environment."""
    reading = report.reading(one.path)
    why = offered(one, report)
    return CredentialRow(
        slot=one.path,
        family=one.family,
        name=one.name,
        kind=one.kind,
        holder=one.holder,
        state=reading.state,
        held=None if reading.state is SlotState.UNKNOWN else reading.state is SlotState.HELD,
        set_at=reading.set_at,
        outranked_by=one.env_var if one.env_var and one.env_var in store.outranking else None,
        read_by=one.read_by,
        writable=why == "",
        write_told=why,
    )


def field_views(one: DeclaredSlot) -> tuple[CredentialFieldView, ...]:
    """The form's fields: `value` for a slot of one field, each field's own name otherwise."""
    if len(one.fields) == 1:
        label = VALUE_LABELS.get(one.kind, "Value")
        return (CredentialFieldView(field="value", label=label, accepts=FORMAT_TOLD),)
    return tuple(
        CredentialFieldView(field=name, label=FIELD_LABELS.get(name, name), accepts=FORMAT_TOLD)
        for name in one.fields
    )


def change_view(one: Change) -> CredentialChangeView:
    by = SETUP_WIZARD if one.actor_id == GRANTED_BY else one.actor_name or NOBODY_NAMED
    return CredentialChangeView(at=one.at, by=by, by_id=one.actor_id)


def values_of(one: DeclaredSlot, body: CredentialAsked) -> dict[str, str] | CredentialProblemsView:
    """The fields to write, by the slot's own names, or what is wrong with the body's shape.

    A slot of one field takes `value` and refuses `values`; a slot of several takes `values`
    naming exactly its fields. Refused in words and never by quoting what was sent.
    """
    if len(one.fields) == 1:
        if body.values is not None or body.value is None:
            return CredentialProblemsView(
                problems=(
                    CredentialProblemView(
                        field="value",
                        code="one_value",
                        message="This slot takes one value, sent as value.",
                    ),
                )
            )
        return {one.fields[0]: body.value}
    given = body.values or {}
    if body.value is not None or set(given) != set(one.fields):
        return CredentialProblemsView(
            problems=(
                CredentialProblemView(
                    field="values",
                    code="these_fields",
                    message=f"This slot takes {' and '.join(one.fields)}, each sent under values.",
                ),
            )
        )
    return {name: given[name] for name in one.fields}


# ------------------------------------------------------------------------- the wiring


def credentials_of(request: Request) -> Credentials:
    """What this process was built with, or a store with no vault.

    A process whose lifespan attached nothing is a process that can keep no credential, which is
    exactly what `Credentials(None)` answers, so there is no second spelling of "no vault" here.
    """
    found = getattr(request.app.state, "credentials", None)
    return found if isinstance(found, Credentials) else Credentials(None)


def _trace_id() -> str:
    # The id the trace middleware vouched for or minted, as `brain.setup_routes` reads it.
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def reader_of(request: Request) -> VaultStatusReader | None:
    """`brain.vault_routes.vault_reader_of`'s answer, written again because that module imports
    this one: a test's reader, or the vault client the lifespan attached, or None with no vault."""
    found = getattr(request.app.state, "vault_reader", None)
    if found is None:
        found = getattr(request.app.state, "vault", None)
    return found


class CredentialHistory(Protocol):
    """What the Credentials screen reads of the database. `StoredCredentialHistory` is one."""

    async def changes(self, subject: str) -> tuple[Change, ...]:
        """The ledger's credential entries under one subject, newest first."""
        ...

    async def last_used(self, kind: str, name: str) -> datetime | None:
        """When a slot of this kind, for this name, was last used, where anything records it."""
        ...


def history_of(request: Request) -> CredentialHistory | None:
    """A test's reader, or the database, or None without one."""
    found = getattr(request.app.state, "credential_history", None)
    if found is not None:
        return found  # type: ignore[no-any-return]
    sessions = getattr(request.app.state, "db_sessions", None)
    if not isinstance(sessions, async_sessionmaker):
        return None
    typed: async_sessionmaker[AsyncSession] = sessions
    return StoredCredentialHistory(typed)


def declared_of(request: Request) -> tuple[DeclaredSlot, ...]:
    """Every slot this install declares, with the store backend its settings name."""
    return declared_slots(credentials_of(request), backend=value_of(BACKEND_SETTING))


async def may_see_use(request: Request, one: DeclaredSlot, asked: Asking) -> bool:
    """Whether this reader may be shown when this slot's value was last used.

    See `A_FIGURE_ABOUT_A_CONNECTION_IS_SHOWN_WHERE_THE_CONNECTION_IS`. Imported here rather than
    at the top because both route modules import this one for `credentials_of`.
    """
    if one.kind is SlotKind.CONNECTOR:
        from brain.connector_routes import records_of
        from brain.console.connector_trust import admitted_connections

        records = records_of(request)
        if records is None:
            return False
        shown = admitted_connections(await records.connected(), asked.reach, asked.now)
        return any(connection.connector == one.used_by for connection in shown)
    if one.kind is SlotKind.CHANNEL:
        from brain.channel_routes import channel_named
        from brain.channel_routes import may_manage as may_manage_channel

        channel = channel_named(one.used_by)
        return channel is not None and may_manage_channel(asked.reach, channel, asked.now)
    return one.kind in USE_RECORDED


router = APIRouter(prefix=API_PREFIX, tags=["credentials"], route_class=NoEchoRoute)

_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    409: {"model": CredentialNotKeptView, "description": "No vault, or the vault refused."},
    422: {"model": CredentialProblemsView, "description": "What is wrong with what was sent."},
    503: {"model": CredentialNotKeptView, "description": "The vault did not answer."},
}


@router.get(CREDENTIALS_PATH, response_model=CredentialsPage, responses=COMMON_RESPONSES)
async def credentials(request: Request, asked: Asked, listed: SlotQuery) -> CredentialsPage:
    """Every slot the install declares, which hold a value and when each was written. Never one."""
    if not may_manage(asked.reach, asked.now):
        log.info("credentials not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    plan = SLOT_LIST.plan(listed, reader=asked.caller.principal.id)
    slots = declared_of(request)
    report = await asyncio.to_thread(read_catalogue, reader_of(request), slots)
    store = credentials_of(request)
    page = plan.page([row_view(one, report, store) for one in slots])
    vault = overview(report, template_key_state_of(request.app.state))
    return CredentialsPage(vault=vault, items=page.items, next_cursor=page.next_cursor)


@router.get(
    CREDENTIALS_PATH + "/{family}/{name}",
    response_model=CredentialDetailView,
    responses=COMMON_RESPONSES,
)
async def credential(
    request: Request, family: str, name: str, asked: Asked
) -> CredentialDetailView:
    """One slot: what it is for, when it was written and last used, and its history. No value."""
    if not may_manage(asked.reach, asked.now):
        log.info("credentials not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    one = declared_at(declared_of(request), f"{family}/{name}")
    if one is None:
        raise _not_answerable()
    report = await asyncio.to_thread(read_catalogue, reader_of(request), [one])
    row = row_view(one, report, credentials_of(request))
    history = history_of(request)
    changes: tuple[CredentialChangeView, ...] | None = None
    last_used: datetime | None = None
    if history is not None:
        if one.recordable:
            found = await history.changes(f"credential:{credential_subject_id(one.path)}")
            changes = tuple(change_view(change) for change in found)
        else:
            changes = ()
        if one.kind in USE_RECORDED and await may_see_use(request, one, asked):
            last_used = await history.last_used(one.kind.value, one.used_by)
    in_use = InUse.OUTRANKED if row.outranked_by is not None else one.takes_effect
    provider = one.provider
    return CredentialDetailView(
        vault=overview(report, template_key_state_of(request.app.state)),
        row=row,
        description=one.slot.description,
        fields=field_views(one),
        ask_for=one.ask_for,
        never=one.never,
        takes_effect=in_use,
        takes_effect_told=told_in_use(provider, in_use)
        if provider is not None
        else takes_effect_told(one.kind, in_use, backend=one.backend),
        use_recorded=one.kind in USE_RECORDED,
        last_used_at=last_used,
        last_used_told=LAST_USED_SAYS[one.kind],
        history=changes,
        history_told=HISTORY_SAYS if history is not None else NO_HISTORY_READABLE,
    )


@router.put(
    CREDENTIALS_PATH + "/{family}/{name}", response_model=CredentialKeptView, responses=_TOLD
)
async def set_credential(
    request: Request, family: str, name: str, body: CredentialAsked, asked: Asked
) -> JSONResponse:
    """Put a value into one slot and say that it is held. Nothing sent comes back."""
    if not may_manage(asked.reach, asked.now):
        log.info("credentials not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    store = credentials_of(request)
    # Every slot the install declares: a built-in provider's, an added provider's (M5.7.2), the
    # relay's, the store's and each source's and channel's. One the ledger cannot name is not one.
    one = declared_at(declared_of(request), f"{family}/{name}")
    if one is None or not one.recordable:
        log.info("credential slot not answerable", principal=asked.caller.principal.id)
        raise _not_answerable()
    values = values_of(one, body)
    if isinstance(values, CredentialProblemsView):
        return JSONResponse(status_code=422, content=values.model_dump(mode="json"))
    actor = asked.reach.principal_id
    try:
        if one.replace_only and not await first_set(store, one, actor=actor):
            view = CredentialNotKeptView(
                message=FIRST_SET_ELSEWHERE[one.kind],
                trace_id=_trace_id(),
                slot=one.path,
                vault=VaultState.READY,
            )
            return JSONResponse(status_code=409, content=view.model_dump(mode="json"))
        kept = await store.keep_fields(
            one.slot,
            values,
            actor=actor,
            trace_id=_trace_id(),
            ent_hash=asked.reach.ent_hash(),
        )
        provider = one.provider
        in_use = one.takes_effect
        if provider is not None:
            in_use = store.put_to_use(provider, values[KEY_FIELD])
    except CredentialProblemError as refused:
        told = CredentialProblemsView(
            problems=tuple(
                CredentialProblemView(
                    field="value" if len(one.fields) == 1 else problem.field,
                    code=problem.code,
                    message=problem.message,
                )
                for problem in refused.problems
            )
        )
        return JSONResponse(status_code=422, content=told.model_dump(mode="json"))
    except CredentialsUnavailableError as unavailable:
        view = CredentialNotKeptView(
            message=TOLD[unavailable.state],
            trace_id=_trace_id(),
            slot=one.path,
            vault=unavailable.state,
        )
        return JSONResponse(
            status_code=NOT_KEPT_STATUS[unavailable.state], content=view.model_dump(mode="json")
        )
    except BrainError:
        raise
    except Exception as exc:
        # Broad for the reason `brain.api_routes.answer` gives, and the type name alone for the
        # reason this module exists: an exception's message is a place a value can be quoted.
        raise Failed(f"keeping a credential: {type(exc).__name__}") from exc
    return JSONResponse(
        status_code=200, content=kept_view(one, kept, in_use).model_dump(mode="json")
    )


async def first_set(store: Credentials, one: DeclaredSlot, *, actor: str) -> bool:
    """Whether a slot whose first value goes in elsewhere holds one, so it may be replaced here.

    See `A_FIRST_KEY_GOES_IN_WHERE_ITS_THING_IS_SET_UP`. A vault that cannot be asked raises as a
    write would, and is logged as one, so the answer is the write's answer for that state.
    """
    try:
        held = await asyncio.to_thread(store.held, one.slot)
    except CredentialsUnavailableError as unavailable:
        log.info("credential not kept", slot=one.path, actor=actor, vault=unavailable.state)
        raise
    if not held.held:
        log.info("credential not first set here", slot=one.path, actor=actor)
    return held.held


def kept_view(one: DeclaredSlot, kept: Kept, in_use: InUse) -> CredentialKeptView:
    provider = one.provider
    return CredentialKeptView(
        slot=kept.slot,
        held=True,
        set_at=kept.set_at,
        in_use=in_use,
        told=told_in_use(provider, in_use)
        if provider is not None
        else takes_effect_told(one.kind, in_use, backend=one.backend),
    )
