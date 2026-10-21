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

**Why the token is looked for in the tables a disconnect and a keep write, and not in every table.**
This check used to ask `brain.ops.index_audit.tables_holding`, which reads every row of every table
as text, one statement each, under the statement timeout. The owner's install stopped the check on
an `OperationalError` on 2026-10-21 with no traceback to read; a scan of that size outrunning the
timeout on a table as large as the chunks, the trace or the ledger is the most likely cause and is
not confirmed, and the per-step sentences below are there to confirm or refute it on the next run.
The leaf's claim is that a disconnect leaves no token behind, and a token it leaves behind is in a
place it wrote or its keep wrote, so the search is over exactly those
(`WHERE_A_TOKEN_COULD_BE_LEFT`) and finishes in moments on any install. The claim is narrower than
"no table anywhere", and the sentence says so; the whole-database canary scan is
`brain.ops.index_audit`'s own job.

**Each step that can fail on a database says which one it was.** A statement the install refused
used to surface as the exception's type name alone. Each step now has its own sentence, so a failure
on an install names the step without quoting a row.

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

#: The tables a disconnect or the keep of a token writes, which are the only places this check can
#: honestly say a token was left behind. See the module docstring.
WHERE_A_TOKEN_COULD_BE_LEFT: Final = (
    "ops.credential_write",
    "ops.connector_connection",
    "ops.oauth_consent",
    "ops.setting",
    "obs.audit_entry",
    "obs.request_telemetry",
    "obs.trace_step",
)

#: What the check says when its database login cannot read every row, so the search could not look.
THE_LOGIN_CANNOT_READ_EVERY_ROW: Final = (
    "this run's database login cannot read every row, so the search for a left-behind token could "
    "not look; the worker's run can"
)

#: One sentence for each step of the disconnect check that talks to the database and can be refused
#: by it. A database error is named by the step it stopped, never by what it quoted.
DB_STAND_UP: Final = "the database refused the step that connects a source for the run"
DB_SET_UP_PEOPLE: Final = "the database refused the step that places the check's reserved people"
DB_KEEP_THE_SLOT: Final = "the database refused the step that keeps a person's token for the run"
DB_LIST: Final = "the database refused the step that lists a person's accounts"
DB_REFUSED_DISCONNECT: Final = "the database refused a step of a disconnect that was to be refused"
DB_FAILED_DISCONNECT: Final = "the database refused a step of a disconnect the vendor refused"
DB_DISCONNECT: Final = "the database refused a step of the disconnect that was to go through"
DB_RETIRE_GRANT: Final = "the database refused the step that withdraws a person's grant"
DB_SEARCH: Final = "the database refused the step that looks for the token in the tables"

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


async def _held_in(h: Harness, needle: str) -> tuple[str, ...]:
    """The tables of `WHERE_A_TOKEN_COULD_BE_LEFT` holding `needle` anywhere in a row.

    As the worker's login inside the check's transaction, for `A_SEARCH_THAT_CANNOT_SEE_EVERY_ROW_
    IS_NOT_RUN`, and bounded to a handful of tables so it ends inside the statement timeout on an
    install with a year of data. A table this release does not have is skipped.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from brain.ops.index_audit import _quoted, every_table, sees_every_row

    async with AsyncSession(bind=h.connection, join_transaction_mode="create_savepoint") as session:
        await session.execute(text("RESET ROLE"))
        if not await sees_every_row(session):
            raise CheckNotRunError(THE_LOGIN_CANNOT_READ_EVERY_ROW)
        present = set(await every_table(session))
        as_hex = needle.encode("utf-8").hex()
        holding: list[str] = []
        for qualified in WHERE_A_TOKEN_COULD_BE_LEFT:
            if qualified not in present:
                continue
            schema, table = qualified.split(".", 1)
            statement = text(
                f"SELECT 1 FROM {_quoted(schema)}.{_quoted(table)} AS r "  # noqa: S608
                "WHERE strpos(r::text, :needle) > 0 OR strpos(r::text, :as_hex) > 0 LIMIT 1"
            )
            found = await session.execute(statement, {"needle": needle, "as_hex": as_hex})
            if found.first() is not None:
                holding.append(qualified)
        await session.commit()
    return tuple(holding)


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
        "the tables a disconnect writes to."
    ),
)
async def a_member_disconnects_their_account_and_the_vendor_is_told_first(h: Harness) -> None:
    from sqlalchemy.exc import DBAPIError

    from brain.connector_routes import my_accounts
    from brain.core.scope import Scope
    from brain.govern_routes import retire_grant
    from brain.member_accounts_routes import (
        DISCONNECTED_AND_REVOKED,
        NOT_DISCONNECTED,
        disconnect_my_account,
    )
    from brain.ops.credentials import connector_person_oauth_slot

    base = consented_personally()
    assert base.oauth is not None  # declared just above
    declared = replace(base, oauth=replace(base.oauth, revoke_url=VENDOR_REVOKE))
    source = declared.name
    try:
        vendor, vault, c = await _stand_up(h, declared, department=A)
    except DBAPIError:
        raise CheckFailedError(DB_STAND_UP) from None
    reader = ((PERSONAL_READER, Scope.department(A)),)
    ada, bea, cal = (h.principal(A, one) for one in ("ada", "bea", "cal"))
    try:
        for person, grants in ((ada, reader), (bea, reader), (cal, ())):
            await h.person(person, department=A, grants=grants)
    except DBAPIError:
        raise CheckFailedError(DB_SET_UP_PEOPLE) from None

    ada_token = f"refresh-{secrets.token_urlsafe(24)}"
    ada_slot = connector_person_oauth_slot(source, ada).path
    credentials = c.app.state.credentials
    try:
        await credentials.keep(
            connector_person_oauth_slot(source, ada), ada_token, actor=ada, trace_id=h.trace_id
        )
    except DBAPIError:
        raise CheckFailedError(DB_KEEP_THE_SLOT) from None
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

    try:
        mine = await listed(ada)
        others = await listed(bea)
    except DBAPIError:
        raise CheckFailedError(DB_LIST) from None
    if [(one.provenance, one.disconnectable) for one in mine] != [("personal", True)]:
        raise CheckFailedError("an account whose token is kept was not offered a disconnect")
    if any(one.disconnectable for one in others):
        raise CheckFailedError("an account nobody connected was offered a disconnect")

    # A colleague who never connected it, and a person with no reach to the source: one refusal.
    try:
        for stranger in (bea, cal):
            if not await _refused(disconnecting(stranger)):
                raise CheckFailedError(
                    "somebody who never connected the account could disconnect it"
                )
    except DBAPIError:
        raise CheckFailedError(DB_REFUSED_DISCONNECT) from None
    if vendor.revocations or vault.removed:
        raise CheckFailedError("a refused disconnect touched the vendor or the vault")

    # A vendor that refuses leaves the account connected, in words that name no vendor error.
    vendor.refusing_revocation = True
    try:
        refused = await disconnecting(ada)
        still = [one.disconnectable for one in await listed(ada)]
    except DBAPIError:
        raise CheckFailedError(DB_FAILED_DISCONNECT) from None
    if getattr(refused, "status_code", 0) != 503 or NOT_DISCONNECTED.encode() not in refused.body:
        raise CheckFailedError("a revocation the vendor refused was not told in words")
    if ada_slot not in vault.slots or vault.removed:
        raise CheckFailedError("a revocation the vendor refused still removed the token")
    if still != [True]:
        raise CheckFailedError("a failed disconnect left the account unlisted")

    # Then it goes through: the vendor first, and this install's copy only after.
    vendor.refusing_revocation = False
    try:
        done = await disconnecting(ada)
        after = [(one.connected, one.disconnectable) for one in await listed(ada)]
        again = await _refused(disconnecting(ada))
    except DBAPIError:
        raise CheckFailedError(DB_DISCONNECT) from None
    if getattr(done, "told", "") != DISCONNECTED_AND_REVOKED or not done.vendor_revoked:
        raise CheckFailedError("a disconnect did not say the vendor had been asked")
    if vendor.revocations != [ada_token]:
        raise CheckFailedError("the vendor was not asked to revoke the person's own token")
    if any(removed for removed in vendor.removed_when_asked):
        raise CheckFailedError("the token was removed before the vendor was asked")
    if vault.removed != [ada_slot] or ada_slot in vault.slots:
        raise CheckFailedError("this install's copy of the token was not removed")
    if after != [(False, False)]:
        raise CheckFailedError("a disconnected account was still shown as connected")
    if not again:
        raise CheckFailedError("a second disconnect found something to disconnect")

    # Somebody who has left the department keeps the way to take their own token back.
    away = connector_person_oauth_slot(source, bea)
    bea_token = f"refresh-{secrets.token_urlsafe(24)}"
    try:
        await credentials.keep(away, bea_token, actor=bea, trace_id=h.trace_id)
    except DBAPIError:
        raise CheckFailedError(DB_KEEP_THE_SLOT) from None
    vendor.refresh[bea_token] = bea
    try:
        await h.execute(*h.attributed(), retire_grant(bea, PERSONAL_READER))
    except DBAPIError:
        raise CheckFailedError(DB_RETIRE_GRANT) from None
    try:
        still_listed = await listed(bea)
        taken_back = await disconnecting(bea)
    except DBAPIError:
        raise CheckFailedError(DB_DISCONNECT) from None
    if still_listed:
        raise CheckFailedError("a person without the reader capability was still listed the source")
    if getattr(taken_back, "vendor_revoked", False) is not True:
        raise CheckFailedError("a person who left the department could not take their token back")
    try:
        left_behind = await _held_in(h, ada_token)
    except DBAPIError:
        raise CheckFailedError(DB_SEARCH) from None
    if left_behind:
        raise CheckFailedError("a person's token was found in a table a disconnect writes to")


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
