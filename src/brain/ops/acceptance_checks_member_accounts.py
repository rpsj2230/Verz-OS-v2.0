"""Install acceptance checks for a member's own accounts: disconnecting one, and inherited ones.

Each is the route My workspace calls (`GET /me/accounts` and `POST /me/accounts/{connector}/
disconnect`) as a reserved member signed in through the install's own gate, over a source stood up
for the run from Xero's declaration (the stand-in `brain.ops.acceptance_checks_oauth` uses, because
no shipped source is consented to once, and the one shipped per person is Google's, which this
install may have connected for real). The vendor is a recorded endpoint that opens no socket and
the vault is the policy-by-role stand-in, so the order a disconnect must keep is observable.

**What the disconnect check is for is the one thing a disconnect must not do: remove the token
before the vendor has been asked.** The vendor stand-in notes what the vault held when the
revocation reached it, and the check refuses a run in which the slot was already gone. A vendor that
refuses leaves the account connected and listed, a colleague who never connected it and a person
with no reach get the one refusal, and a person who has since left the department can still take
their own token back.

**What the inherited check is for** is a department's connection being shown to the people it was
made for, as inherited and with no control, and to nobody else: a person in another department is
listed nothing, and asking to disconnect it is the one refusal.

**What this does not prove**, and the report says so: that a real vendor stops honouring the token,
and that the install's vault carries the application policy line that lets the slot be removed. Both
need a person on an install (the Google steps on needs item 173 for the first).

Task ids: M40.5.1.3, M40.5.1.4
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs

from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_checks_oauth import (
    CLIENT_ID_SETTING,
    PERSONAL_READER,
    _Accounts,
    _RoleVault,
    consented_personally,
    consented_xero,
)
from brain.ops.acceptance_people_signed_in import console
from brain.ops.acceptance_run import SET_UP_REACH, Harness

if TYPE_CHECKING:
    from brain.connectors.declaration import ConnectorDeclaration
    from brain.ops.connector_sync_run import SourceAnswer

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2780

A, B = RESERVED_DEPARTMENTS

#: The made-up vendor's revocation address, under a name reserved for examples.
VENDOR_REVOKE: Final = "https://identity.oauth-vendor.example/connect/revocation"

#: What the check says where the install has Xero connected already.
XERO_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has Xero connected already, so the check does not stand a copy of it up beside "
    "the real one"
)


@dataclass
class _RevokingVendor(_Accounts):
    """The per-person vendor of the OAuth check, with a revocation endpoint added to it.

    What the vault held when each revocation arrived is noted, so a run in which the slot was
    already removed is visible; `refusing_revocation` has the endpoint answer 503.
    """

    vault: Any = None
    revocations: list[str] = field(default_factory=list)
    removed_when_asked: list[list[str]] = field(default_factory=list)
    refusing_revocation: bool = False

    def post(
        self, url: str, *, address: str, headers: Any, body: bytes, max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        if url != VENDOR_REVOKE:
            return super().post(
                url, address=address, headers=headers, body=body, max_bytes=max_bytes
            )
        form = {key: values[0] for key, values in parse_qs(body.decode("ascii")).items()}
        self.removed_when_asked.append(list(self.vault.removed))
        if self.refusing_revocation:
            return SourceAnswer(status=503, headers={})
        token = form.get("token", "")
        self.revocations.append(token)
        self.refresh.pop(token, None)
        return SourceAnswer(status=200, headers={})


async def _refused(call: Any) -> bool:
    """Whether a call was answered with the one refusal, `Absent`, and nothing else."""
    from brain.core.errors import Absent

    try:
        await call
    except Absent:
        return True
    return False


async def _stand_up(
    h: Harness, declared: ConnectorDeclaration, *, department: str
) -> tuple[_RevokingVendor, _RoleVault, Any]:
    """Connect `declared` for the run, answering to `department`, and return the vendor, the vault
    and the console whose application holds them."""
    from brain.connector_routes import ConsentExchange
    from brain.connectors.manifest import manifest_digest
    from brain.ops.acceptance_checks_connectors import _Resolver
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_store import StoredConnections, live
    from brain.ops.connector_sync_run import WorkerConnectorKeys
    from brain.ops.credential_write_store import StoredCredentialWrites
    from brain.ops.credentials import Credentials, connector_key_slot

    source = declared.name
    if (await h.execute(live(source))).scalar_one_or_none() is not None:
        raise CheckNotRunError(XERO_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()
    vendor = _RevokingVendor(
        client_id=f"client-{secrets.token_hex(6)}", client_secret=secrets.token_urlsafe(32)
    )
    vault = _RoleVault()
    vendor.vault = vault
    credentials = Credentials(vault, writes=StoredCredentialWrites(h.sessions))
    settings = {
        "tenant_id": str(uuid.uuid4()),
        CLIENT_ID_SETTING: vendor.client_id,
        "department": department,
    }

    async def keep_secret() -> datetime | None:
        kept = await credentials.keep(
            connector_key_slot(source), vendor.client_secret, actor=h.actor, trace_id=h.trace_id
        )
        return kept.set_at

    await StoredConnections(h.sessions).connect(
        connector=source,
        settings=settings,
        digest=manifest_digest(manifest_for(source, settings)),
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        keep_key=keep_secret,
    )
    c = await console(h)
    c.app.state.connector_declarations = {source: declared}
    c.app.state.credentials = credentials
    c.app.state.vault = vault
    c.app.state.consent_exchange = ConsentExchange(
        keys=WorkerConnectorKeys(vault), poster=vendor, resolver=_Resolver(), health=None
    )
    return vendor, vault, c


@check(
    leaves=("M40.5.1.3",),
    sentence=(
        "A member disconnects their own account: the vendor is asked to revoke the token before "
        "this install's copy is removed, a vendor that refuses leaves the account connected, a "
        "colleague who never connected it is refused as if it did not exist, a person who has "
        "since left the department can still take their own token back, and no token is left in "
        "a table."
    ),
)
async def a_member_disconnects_their_account_and_the_vendor_is_told_first(h: Harness) -> None:
    from brain.connector_routes import my_accounts
    from brain.core.scope import Scope
    from brain.govern_routes import retire_grant
    from brain.member_accounts_routes import (
        DISCONNECTED_AND_REVOKED,
        NOT_DISCONNECTED,
        disconnect_my_account,
    )
    from brain.ops.acceptance_checks_connectors import _search
    from brain.ops.credentials import connector_person_oauth_slot

    base = consented_personally()
    assert base.oauth is not None  # declared just above
    declared = replace(base, oauth=replace(base.oauth, revoke_url=VENDOR_REVOKE))
    source = declared.name
    vendor, vault, c = await _stand_up(h, declared, department=A)
    reader = ((PERSONAL_READER, Scope.department(A)),)
    ada, bea, cal = (h.principal(A, one) for one in ("ada", "bea", "cal"))
    for person, grants in ((ada, reader), (bea, reader), (cal, ())):
        await h.person(person, department=A, grants=grants)

    ada_token = f"refresh-{secrets.token_urlsafe(24)}"
    ada_slot = connector_person_oauth_slot(source, ada).path
    credentials = c.app.state.credentials
    await credentials.keep(
        connector_person_oauth_slot(source, ada), ada_token, actor=ada, trace_id=h.trace_id
    )
    vendor.refresh[ada_token] = ada

    async def listed(who: str) -> list[Any]:
        with c.as_route():
            page = await my_accounts(c.request(), await c.asked(who, strong=False))
        return list(page.accounts)

    async def disconnecting(who: str) -> Any:
        with c.as_route():
            return await disconnect_my_account(
                c.request("POST"), source, await c.asked(who, strong=False)
            )

    mine = await listed(ada)
    if [(one.provenance, one.disconnectable) for one in mine] != [("personal", True)]:
        raise CheckFailedError("an account whose token is kept was not offered a disconnect")
    if any(one.disconnectable for one in await listed(bea)):
        raise CheckFailedError("an account nobody connected was offered a disconnect")

    # A colleague who never connected it, and a person with no reach to the source: one refusal.
    for stranger in (bea, cal):
        if not await _refused(disconnecting(stranger)):
            raise CheckFailedError("somebody who never connected the account could disconnect it")
    if vendor.revocations or vault.removed:
        raise CheckFailedError("a refused disconnect touched the vendor or the vault")

    # A vendor that refuses leaves the account connected, in words that name no vendor error.
    vendor.refusing_revocation = True
    refused = await disconnecting(ada)
    if getattr(refused, "status_code", 0) != 503 or NOT_DISCONNECTED.encode() not in refused.body:
        raise CheckFailedError("a revocation the vendor refused was not told in words")
    if ada_slot not in vault.slots or vault.removed:
        raise CheckFailedError("a revocation the vendor refused still removed the token")
    if [one.disconnectable for one in await listed(ada)] != [True]:
        raise CheckFailedError("a failed disconnect left the account unlisted")

    # Then it goes through: the vendor first, and this install's copy only after.
    vendor.refusing_revocation = False
    done = await disconnecting(ada)
    if getattr(done, "told", "") != DISCONNECTED_AND_REVOKED or not done.vendor_revoked:
        raise CheckFailedError("a disconnect did not say the vendor had been asked")
    if vendor.revocations != [ada_token]:
        raise CheckFailedError("the vendor was not asked to revoke the person's own token")
    if any(removed for removed in vendor.removed_when_asked):
        raise CheckFailedError("the token was removed before the vendor was asked")
    if vault.removed != [ada_slot] or ada_slot in vault.slots:
        raise CheckFailedError("this install's copy of the token was not removed")
    if [(one.connected, one.disconnectable) for one in await listed(ada)] != [(False, False)]:
        raise CheckFailedError("a disconnected account was still shown as connected")
    if not await _refused(disconnecting(ada)):
        raise CheckFailedError("a second disconnect found something to disconnect")

    # Somebody who has left the department keeps the way to take their own token back.
    away = connector_person_oauth_slot(source, bea)
    bea_token = f"refresh-{secrets.token_urlsafe(24)}"
    await credentials.keep(away, bea_token, actor=bea, trace_id=h.trace_id)
    vendor.refresh[bea_token] = bea
    await h.execute(*h.attributed(), retire_grant(bea, PERSONAL_READER))
    if await listed(bea):
        raise CheckFailedError("a person without the reader capability was still listed the source")
    if getattr(await disconnecting(bea), "vendor_revoked", False) is not True:
        raise CheckFailedError("a person who left the department could not take their token back")
    if await _search(h, ada_token):
        raise CheckFailedError("a person's token was found in a table")


@check(
    leaves=("M40.5.1.4",),
    sentence=(
        "A connection the member's own department made is listed to them as inherited with no "
        "disconnect, a person in another department is listed nothing, and asking to disconnect it "
        "is refused as if it did not exist."
    ),
)
async def a_departments_connection_is_inherited_and_not_detachable(
    h: Harness,
) -> None:
    from brain.connector_routes import my_accounts
    from brain.core.scope import Scope
    from brain.member_accounts_routes import disconnect_my_account

    declared, _ = consented_xero()
    source = declared.name
    _, vault, c = await _stand_up(h, declared, department=A)
    reader = ((PERSONAL_READER, Scope.department(A)),)
    other = ((PERSONAL_READER, Scope.department(B)),)
    ada, bea, cal = (h.principal(A, "ada"), h.principal(B, "bea"), h.principal(A, "cal"))
    await h.person(ada, department=A, grants=reader)
    await h.person(bea, department=B, grants=other)
    await h.person(cal, department=A, grants=())

    async def listed(who: str) -> list[Any]:
        with c.as_route():
            page = await my_accounts(c.request(), await c.asked(who, strong=False))
        return list(page.accounts)

    shown = await listed(ada)
    if len(shown) != 1:
        raise CheckFailedError("a department's connection was not listed as inherited")
    inherited = shown[0]
    if (inherited.connector, inherited.provenance, inherited.disconnectable) != (
        source,
        "department",
        False,
    ):
        raise CheckFailedError("a department's connection was not listed as inherited")
    for outsider in (bea, cal):
        if await listed(outsider):
            raise CheckFailedError("a department's connection was listed to somebody outside it")

    asked = await c.asked(ada, strong=False)
    with c.as_route():
        if not await _refused(disconnect_my_account(c.request("POST"), source, asked)):
            raise CheckFailedError("a department's connection could be disconnected by one member")
    if vault.removed:
        raise CheckFailedError("a refused disconnect removed something from the vault")
