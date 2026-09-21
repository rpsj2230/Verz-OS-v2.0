"""Service accounts over HTTP: an integration registered, given a key shown once, and taken away.

`brain.identity.sessions.ServiceAccount` and `brain.channels.api_keys` were written and tested and
nothing a browser or a script could reach made one, so no install had ever authenticated a caller
that was not a person (M1.1.7). These routes are the way one is made. What the account may reach
once made is `brain.identity.sessions.reach_for`, asked on every request by `brain.api_routes`.

**The authority is `admin:credential`, and the account is always the caller's own.** A key is a
credential this install issues, which is the capability the Credentials screen asks for, so no new
capability is put into the system from a route. And the owner is the caller and never a field:
an account acts at its owner's reach narrowed by its ceiling, so registering one for somebody else
would lend their reach without asking them. See
`brain.identity.service_account_store.AN_ACCOUNT_IS_ITS_OWNERS_AND_NOBODY_ELSES`.

**The ceiling is a list of capabilities, enumerated, and a capability the owner does not hold
confers nothing.** A wildcard is refused, so what an account could reach is a list somebody reads.
The answer names the capabilities in the ceiling the owner does not hold now, which is the caller's
own reach and nothing about anybody else's, so they are not surprised later by an account that
cannot do what its ceiling says.

**The key is in exactly one response.** The issue answers the full key once; the listing, every
other answer and the database hold its handle and its digest and never the secret. A lost key is
revoked and another issued.

**Every refusal over somebody else's account is the one 404.** An account another person owns, a
retired one and one that never existed are not found, for the reason every control in this console
gives.

Task ids: M1.1.7, M1.8.2
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final, Protocol, Self, runtime_checkable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody
from brain.api_routes import Asked, Asking
from brain.channels.api_keys import ApiKeyError, IssuedKey
from brain.core.entitlement import Capability
from brain.core.errors import Absent, Failed
from brain.identity.service_account_store import (
    AN_ACCOUNT_IS_ITS_OWNERS_AND_NOBODY_ELSES,
    AccountListed,
    Registered,
    StoredServiceAccounts,
)
from brain.identity.sessions import ServiceAccount
from brain.routing_routes import sessions_of
from brain.tables.service_account import CLIENT_ID_PATTERN, LABEL_CHARS, SUBJECT_CHARS

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: What an account can do, served on the listing.
AN_ACCOUNT_ACTS_AT_ITS_OWNERS_REACH: Final = (
    "A service account acts at your reach, narrowed to the capabilities it lists, and holds "
    "nothing of its own. Take a grant away from yourself and the account loses it on its next "
    "request; if you are disabled or leave, every account you own stops working."
)

#: What a key is, served beside one.
A_KEY_IS_SHOWN_ONCE: Final = (
    "This is the only time the key is shown. Keep it somewhere safe; if it is lost, revoke it and "
    "issue another."
)

#: The capability every route here asks for, held in any scope.
SERVICE_ACCOUNT_AUTHORITY: Final = Capability(value="admin:credential")

#: The most accounts one listing loads. A resource bound, not a permission one.
MAX_ROWS: Final = 200

#: The most capabilities one ceiling may list.
MAX_CEILING: Final = 50


# ------------------------------------------------------------------- the shapes

Label = Annotated[str, StringConstraints(strip_whitespace=True, max_length=LABEL_CHARS)]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        msg = "the lapse must carry a time zone"
        raise ValueError(msg)
    return value


class KeyView(BaseModel):
    """One live key: its handle, never its secret."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    handle: str
    label: str
    issued_at: datetime
    lapses_at: datetime


class AccountView(BaseModel):
    """One account the caller owns."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    client_id: str
    label: str
    ceiling: list[str]
    lapses_at: datetime
    created_at: datetime
    keys: list[KeyView]
    #: Capabilities in the ceiling the caller does not hold now, which the account cannot use.
    not_held_now: list[str]


class AccountsPage(BaseModel):
    """The caller's own accounts, and the sentence the screen says."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[AccountView]
    truncated: bool
    reach: str = AN_ACCOUNT_ACTS_AT_ITS_OWNERS_REACH
    ownership: str = AN_ACCOUNT_IS_ITS_OWNERS_AND_NOBODY_ELSES


class AccountAsked(BaseModel):
    """An account to register, owned by whoever asks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    client_id: str = Field(pattern=CLIENT_ID_PATTERN)
    label: Label = ""
    ceiling: list[str] = Field(min_length=1, max_length=MAX_CEILING)
    not_after: datetime
    #: The identity provider subject of a client-credentials client, when it has one.
    subject: str | None = Field(default=None, min_length=1, max_length=SUBJECT_CHARS)

    @field_validator("ceiling")
    @classmethod
    def _enumerated(cls, value: list[str]) -> list[str]:
        for one in value:
            if "*" in one:
                msg = f"{one!r} is a wildcard; list each capability the account may use"
                raise ValueError(msg)
            Capability(value=one)
        if len(set(value)) != len(value):
            msg = "a capability is listed twice"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _lapse(self) -> Self:
        _aware(self.not_after)
        return self


class KeyAsked(BaseModel):
    """A key to issue for one of the caller's accounts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    client_id: str = Field(pattern=CLIENT_ID_PATTERN)
    label: Label = ""
    not_after: datetime

    @model_validator(mode="after")
    def _lapse(self) -> Self:
        _aware(self.not_after)
        return self


class KeyIssued(BaseModel):
    """The key, whole, this once."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    client_id: str
    handle: str
    key: str
    lapses_at: datetime
    shown_once: str = A_KEY_IS_SHOWN_ONCE


class KeyRevocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    handle: str = Field(pattern=r"^[A-Za-z0-9_-]{6,32}$")


class AccountRetirement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    client_id: str = Field(pattern=CLIENT_ID_PATTERN)


class Done(BaseModel):
    """What changed, in a sentence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    told: str


# ------------------------------------------------------------------- the store


@runtime_checkable
class ServiceAccountStore(Protocol):
    """What these routes need of the two tables. `StoredServiceAccounts` implements it."""

    async def owned(self, owner: str, *, limit: int) -> tuple[tuple[AccountListed, ...], bool]: ...

    async def register(
        self,
        account: ServiceAccount,
        *,
        subject: str | None,
        label: str,
        ent_hash: str,
        trace_id: str,
    ) -> Registered: ...

    async def issue_key(
        self,
        client_id: str,
        *,
        owner: str,
        not_after: datetime,
        label: str,
        now: datetime,
        ent_hash: str,
        trace_id: str,
    ) -> IssuedKey | None: ...

    async def revoke_key(self, handle: str, *, owner: str) -> bool: ...

    async def retire(self, client_id: str, *, owner: str) -> bool: ...


def store_of(request: Request) -> ServiceAccountStore:
    """`app.state.service_accounts` when something put one there, the database otherwise."""
    found = getattr(request.app.state, "service_accounts", None)
    if isinstance(found, ServiceAccountStore):
        return found
    factory = sessions_of(request)
    if factory is None:
        raise Failed("no database on this process")
    return StoredServiceAccounts(factory)


def _trace_id() -> str:
    return str(structlog.contextvars.get_contextvars().get("trace_id", ""))


def _not_here() -> Absent:
    """The one refusal: no authority, or an account or key that is not the caller's."""
    return Absent("no such service account for this caller")


def _require_authority(asked: Asking) -> None:
    """Asked before any store, so a caller without it is refused alike with or without one."""
    if asked.reach.scope_for(SERVICE_ACCOUNT_AUTHORITY, asked.now) is None:
        log.info("service accounts refused", principal=asked.caller.principal_id)
        raise _not_here()


def not_held(ceiling: list[str], asked: Asking) -> list[str]:
    """The ceiling's capabilities the caller does not hold at this instant. Their own reach."""
    return [
        one for one in ceiling if asked.reach.scope_for(Capability(value=one), asked.now) is None
    ]


def account_view(one: AccountListed, asked: Asking) -> AccountView:
    ceiling = [capability.value for capability in one.account.ceiling]
    return AccountView(
        client_id=one.account.client_id,
        label=one.label,
        ceiling=ceiling,
        lapses_at=one.account.not_after,
        created_at=one.created_at,
        keys=[
            KeyView(handle=k.handle, label=k.label, issued_at=k.issued_at, lapses_at=k.not_after)
            for k in one.keys
        ],
        not_held_now=not_held(ceiling, asked),
    )


def _not_done(status: int, told: str) -> JSONResponse:
    """Nothing changed, and why, in the house error shape with the request's trace id."""
    body = ErrorBody(message=told, trace_id=_trace_id())
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


router = APIRouter(prefix=API_PREFIX, tags=["service accounts"])


@router.get("/govern/service-accounts", response_model=AccountsPage, responses=COMMON_RESPONSES)
async def accounts_page(request: Request, asked: Asked) -> AccountsPage:
    """The caller's own live accounts, newest first, each with its live keys."""
    _require_authority(asked)
    listed, full = await store_of(request).owned(asked.caller.principal_id, limit=MAX_ROWS)
    return AccountsPage(items=[account_view(one, asked) for one in listed], truncated=full)


@router.post(
    "/govern/service-accounts",
    response_model=AccountView,
    responses=COMMON_RESPONSES,
    status_code=201,
)
async def register_account(request: Request, body: AccountAsked, asked: Asked) -> JSONResponse:
    """Register an account owned by the caller. 409 when the id or subject is taken or past."""
    _require_authority(asked)
    if body.not_after <= asked.now:
        return _not_done(409, "That end date has already passed; choose one in the future.")
    owner = asked.caller.principal_id
    if asked.caller.service_account is not None or body.client_id == owner:
        raise _not_here()
    account = ServiceAccount(
        client_id=body.client_id,
        subject=body.subject or body.client_id,
        owner_principal_id=owner,
        ceiling=tuple(Capability(value=one) for one in body.ceiling),
        not_after=body.not_after,
    )
    outcome = await store_of(request).register(
        account,
        subject=body.subject,
        label=body.label,
        ent_hash=asked.reach.ent_hash(),
        trace_id=_trace_id(),
    )
    if outcome is Registered.TAKEN:
        return _not_done(409, "That id or identity provider subject is already in use.")
    view = AccountView(
        client_id=account.client_id,
        label=body.label,
        ceiling=list(body.ceiling),
        lapses_at=account.not_after,
        created_at=asked.now,
        keys=[],
        not_held_now=not_held(list(body.ceiling), asked),
    )
    return JSONResponse(status_code=201, content=view.model_dump(mode="json"))


@router.post(
    "/govern/service-accounts/keys",
    response_model=KeyIssued,
    responses=COMMON_RESPONSES,
    status_code=201,
)
async def issue_key(request: Request, body: KeyAsked, asked: Asked) -> JSONResponse:
    """Issue a key for one of the caller's accounts; its expiry is capped by the account's."""
    _require_authority(asked)
    try:
        minted = await store_of(request).issue_key(
            body.client_id,
            owner=asked.caller.principal_id,
            not_after=body.not_after,
            label=body.label,
            now=asked.now,
            ent_hash=asked.reach.ent_hash(),
            trace_id=_trace_id(),
        )
    except ApiKeyError as why:
        return _not_done(409, str(why))
    if minted is None:
        raise _not_here()
    issued = KeyIssued(
        client_id=minted.record.client_id,
        handle=minted.record.handle,
        key=minted.secret,
        lapses_at=minted.record.not_after,
    )
    return JSONResponse(status_code=201, content=issued.model_dump(mode="json"))


@router.post(
    "/govern/service-accounts/keys/revoke", response_model=Done, responses=COMMON_RESPONSES
)
async def revoke_key(request: Request, body: KeyRevocation, asked: Asked) -> Done:
    """Retire one key of the caller's; it is refused from its next use."""
    _require_authority(asked)
    if not await store_of(request).revoke_key(body.handle, owner=asked.caller.principal_id):
        raise _not_here()
    return Done(told="The key is revoked and is refused from its next use.")


@router.post("/govern/service-accounts/retire", response_model=Done, responses=COMMON_RESPONSES)
async def retire_account(request: Request, body: AccountRetirement, asked: Asked) -> Done:
    """Retire one of the caller's accounts and every key it has."""
    _require_authority(asked)
    if not await store_of(request).retire(body.client_id, owner=asked.caller.principal_id):
        raise _not_here()
    return Done(told="The account and all its keys are retired and refused from their next use.")
