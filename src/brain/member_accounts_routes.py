"""A member disconnecting their own account, with the vendor told first (M40.5.1.3).

`GET /me/accounts` and `POST /me/accounts/{connector}/consent` (`brain.connector_routes`) let a
person attach their own account at a vendor, and nothing let them take it back:
`brain.member.connections.disconnect` was written and tested with no `TokenRevoker` behind it. This
is the route, and `brain.ops.person_token_revoker.VaultTokenRevoker` is the implementation it hands
`disconnect`.

**The undo of a capability that is already live is not behind a switch.** Attaching an account has
no switch, so a disconnect that needed one could leave a person's token standing because an
administrator had not turned something on. `brain.ops.features.
A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED` is the rule; this route is the "withdraw"
path it names.

**It is a POST to `.../disconnect` and not a DELETE.** The console sends no DELETE
(`console/tests/destructive-labels.test.ts`): a destructive act is a labelled POST the page can
describe before it is pressed, and the label here says what happens to the token.

**What it refuses is one refusal.** An unknown source, a source each person does not consent to
for themselves, and an account this person never connected (or has already disconnected) are all
`Absent`: nothing says which, so the route cannot be used to ask which sources exist or whether
somebody else connected one. It does not ask whether the person still holds the source's reader
capability, because a person who has moved department must still be able to take their own token
back. A vault that cannot be asked is a 503 with a sentence, not an absence.

**A revocation that fails leaves the connection exactly as it was** and says so in one fixed
sentence that names no vendor error. That is `disconnect`'s ordering, held here by a test that
drives the real route with a revoker that answers False and reads the slot afterwards.

**What this cannot prove.** Against a fake vendor and a fake vault the order, the retry and the
refusals are proved in CI. That a real vendor stops honouring the token, and that the install's
vault holds the policy line that lets the application remove the slot, are things only a person on
an install can show; the install check says so when the vault is not there.

Task ids: M40.5.1.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Final, cast

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES, ErrorBody
from brain.api_routes import Asked
from brain.connector_routes import (
    MY_ACCOUNTS_PATH,
    consent_exchange_of,
    declarations_of,
)
from brain.connectors.oauth import ConsentKind
from brain.core.errors import Absent
from brain.credential_routes import credentials_of
from brain.member.connections import (
    MemberConnectionError,
    PersonalConnection,
    Provenance,
    TokenRevoker,
    disconnect,
)
from brain.ops.credentials import (
    CredentialsUnavailableError,
    VaultState,
    connector_person_oauth_slot,
)
from brain.ops.erasure_store import RemovesSlots
from brain.ops.person_token_revoker import VaultTokenRevoker

log = structlog.get_logger()

router = APIRouter(prefix=API_PREFIX, tags=["member"])

MY_DISCONNECT_PATH: Final = MY_ACCOUNTS_PATH + "/{connector}/disconnect"

#: What a person is told when the vendor or the vault would not let the account go.
NOT_DISCONNECTED: Final = (
    "Your account could not be disconnected just now, so it is still connected. Nothing was "
    "removed. Try again in a moment."
)

#: What they are told when the vendor was asked to revoke and did.
DISCONNECTED_AND_REVOKED: Final = (
    "Your account is disconnected. The vendor was asked to revoke the access it gave, and the copy "
    "this install held has been removed."
)

#: What they are told when the vendor publishes no way to revoke, so only the copy here was removed.
DISCONNECTED_NOT_REVOKED_AT_THE_VENDOR: Final = (
    "Your account is disconnected and the copy this install held has been removed. This vendor "
    "offers no way to revoke access from here, so remove this install from your account's "
    "security settings at the vendor as well."
)

_RESPONSES: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    503: {"model": ErrorBody, "description": "The account could not be disconnected just now."},
}


class DisconnectedView(BaseModel):
    """What a disconnect did, in words. `vendor_revoked` is whether the vendor was asked."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connector: str
    vendor_revoked: bool
    told: str


def revoker_of(request: Request, *, connector: str, principal_id: str) -> TokenRevoker | None:
    """The revoker for this person's slot at this source, or None when this process has no vault.

    `app.state.account_revoker` is a factory a test puts there; otherwise the real one over this
    process's vault, the consent exchange's keys, poster and resolver. The vault must be able to
    remove a slot, which only the real vault client can.
    """
    made = getattr(request.app.state, "account_revoker", None)
    if callable(made):
        # `app.state` is untyped; only a factory of this shape is put there under this name.
        return cast("Callable[[str, str], TokenRevoker]", made)(connector, principal_id)
    vault = getattr(request.app.state, "vault", None)
    declared = declarations_of(request).get(connector)
    if declared is None or declared.oauth is None or not isinstance(vault, RemovesSlots):
        return None
    exchange = consent_exchange_of(request)
    return VaultTokenRevoker(
        connector=connector,
        principal_id=principal_id,
        consent=declared.oauth,
        keys=exchange.keys,
        remover=vault,
        poster=exchange.poster,
        resolver=exchange.resolver,
    )


@router.post(MY_DISCONNECT_PATH, response_model=DisconnectedView, responses=_RESPONSES)
async def disconnect_my_account(
    request: Request, connector: str, asked: Asked
) -> DisconnectedView | JSONResponse:
    """Disconnect the asker's own account at a source: revoke it at the vendor, then remove it.

    Asked of the person themselves and of nobody on their behalf; the principal is the one the
    token resolved. See the module docstring for the one refusal and the ordering.
    """
    me = asked.reach.principal_id
    declared = declarations_of(request).get(connector)
    consent = None if declared is None else declared.oauth
    if consent is None or consent.kind is not ConsentKind.PERSON:
        log.info("own disconnect not answerable", principal=me)
        raise Absent("your account is not answerable for this caller")
    slot = connector_person_oauth_slot(connector, me)
    credentials = credentials_of(request)
    try:
        held = credentials.held(slot)
    except CredentialsUnavailableError as unavailable:
        body = ErrorBody(message=NOT_DISCONNECTED)
        log.info("own disconnect: vault not asked", state=unavailable.state)
        return JSONResponse(status_code=503, content=body.model_dump())
    if not held.held:
        raise Absent("your account is not answerable for this caller")
    revoker = revoker_of(request, connector=connector, principal_id=me)
    if revoker is None:
        body = ErrorBody(message=NOT_DISCONNECTED)
        log.info("own disconnect: nothing to revoke with", state=VaultState.ABSENT)
        return JSONResponse(status_code=503, content=body.model_dump())
    connection = PersonalConnection(
        principal_id=me,
        source=connector,
        provenance=Provenance.PERSONAL,
        connected_at=held.set_at or asked.now,
        token_ref=slot.path,
    )
    try:
        await asyncio.to_thread(disconnect, connection, revoker=revoker, at=asked.now)
    except MemberConnectionError:
        body = ErrorBody(message=NOT_DISCONNECTED)
        return JSONResponse(status_code=503, content=body.model_dump())
    asked_the_vendor = bool(consent.revoke_url)
    return DisconnectedView(
        connector=connector,
        vendor_revoked=asked_the_vendor,
        told=DISCONNECTED_AND_REVOKED
        if asked_the_vendor
        else DISCONNECTED_NOT_REVOKED_AT_THE_VENDOR,
    )
