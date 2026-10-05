"""The install acceptance check for a source consented to by OAuth: consent, renewal, refusal.

M11.8.6 has a connector that authorises by OAuth consented to from the console, its refresh token
kept by reference in the vault, its access renewed before it expires without a person, and a
refused renewal or consent marking the source down in words. **No source this release ships
authorises by OAuth yet: Google Workspace (M11.7.6) will be the first.** So this check stands one up
for the run: Xero's own declaration, reading and manifest, with an OAuth consent declared on it and
its reading presenting `KeyScheme.OAUTH_REFRESH`, which is exactly what a connector module would
declare. Nothing about Xero's shipped connection changes, and the check steps aside where the
install has Xero connected. See `A_CONSENTED_SOURCE_IS_STOOD_UP_FOR_THE_RUN`.

**Each step is the product's own code.** The consent is started and answered by
`brain.connector_routes.start_consent` and `finish_consent`, which are the two console routes'
bodies, over the consent table `0180` made (`brain.ops.connector_consent.StoredConsents`) as the
application's role; the client secret and the refresh token are kept by `Credentials.keep`, which
records each write in the ledger; the worker's read is `brain.ops.connector_sync_run.attempt` under
`plan_for`, with `WorkerConnectorKeys` leasing every value. What the check stands in for is the
vendor and the vault: the vendor is a recorded token endpoint and a recorded Xero that open no
socket, and the vault is `_RoleVault`, which answers each token with what its policy file grants
(a run token reads and cannot patch, a rotation token patches and cannot read), so a code path that
used the wrong role fails here as it would on the vault. The route's authority check is the one
part not driven: `tests/unit/test_connector_routes.py` holds it.

Task ids: M11.8.6
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import parse_qs, urlsplit

from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_checks_connectors import (
    _no_wait,
    _Resolver,
    _search,
)
from brain.ops.acceptance_run import SET_UP_REACH

if TYPE_CHECKING:
    from brain.connectors.declaration import ConnectorDeclaration, PageReply, SourceReading
    from brain.connectors.oauth import OAuthConsent
    from brain.connectors.projection import ProjectedRecord
    from brain.connectors.rest import RestOperation
    from brain.ops.acceptance_run import Harness
    from brain.ops.connector_sync_run import SourceAnswer
    from brain.ops.openbao import RoleToken, StaticVersion
    from brain.tools.fetch import Resolver

# ------------------------------------------------------------------ written-down reasons
#: Where this module's check stands on the Install page, after the Google sources'.
CHECK_ORDER: Final = 335

#: Why the check stands a consented source up rather than finding one.
A_CONSENTED_SOURCE_IS_STOOD_UP_FOR_THE_RUN: Final = (
    "No source this release ships authorises by OAuth yet, so the check declares one for the run "
    "from Xero's own reading, manifest and form, with a consent and the OAuth key scheme added, "
    "and drives the consent routes' bodies and the worker's read over it. Google Workspace will "
    "be the first shipped source to use it, and this check is then pointed at that one."
)

#: What the check says where the install has Xero connected already.
XERO_IS_CONNECTED_HERE_ALREADY: Final = (
    "this install has Xero connected already, so the check does not stand a consented copy of it "
    "up beside the real one"
)

#: The made-up vendor's addresses, under a name reserved for examples, and the console's.
VENDOR_EXCHANGE: Final = "https://identity.oauth-vendor.example/connect/token"
AUTHORIZE_URL: Final = "https://login.oauth-vendor.example/connect/authorize"
CONSOLE_RETURN: Final = "https://console.example/connector-consent"

#: The setting the check's application client id is typed into.
CLIENT_ID_SETTING: Final = "client_id"


# ------------------------------------------------------------------------ the stand-ins
@dataclass
class _RoleVault:
    """The vault as the application's token and each child token present to it, by policy.

    The application's own token writes (`CredentialVault`); a token minted against a role carries
    that role's one policy, and its client reads only under the run policy and patches only under
    the rotate policy, each refused with the vault's 403 otherwise. Every read and patch is noted
    with the policy it was made under.
    """

    slots: dict[str, dict[str, str]] = field(default_factory=dict, repr=False)
    reads: list[tuple[str, str]] = field(default_factory=list)
    patches: list[tuple[str, str]] = field(default_factory=list)
    refused: list[tuple[str, str]] = field(default_factory=list)
    minted: list[str] = field(default_factory=list)
    revoked: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # The application's own token: `brain.ops.credentials.CredentialVault`.
    def write_static_kv(self, path: str, fields: Mapping[str, str]) -> datetime | None:
        with self._lock:
            self.slots[path] = dict(fields)
        return None

    def static_kv_version(self, path: str) -> StaticVersion | None:
        from brain.ops.openbao import StaticVersion

        return StaticVersion(written_at=None) if path in self.slots else None

    def read_static_kv(self, path: str) -> dict[str, Any]:
        from brain.ops.openbao import VaultRefusedError

        raise VaultRefusedError("the application's own token reads no source's key", status=403)

    # The worker's or the application's token minting a child: `RunTokenVault`.
    def mint_role_token(self, role: str, *, ttl: timedelta, meta: Mapping[str, str]) -> RoleToken:
        from brain.ops.connector_lease import ROTATE_POLICY, ROTATE_TOKEN_ROLE, RUN_POLICY
        from brain.ops.leases import SealedSecret
        from brain.ops.openbao import RoleToken

        del meta
        policy = ROTATE_POLICY if role == ROTATE_TOKEN_ROLE else RUN_POLICY
        with self._lock:
            self.minted.append(policy)
        return RoleToken(
            token=SealedSecret(secrets.token_hex(16)),
            accessor=secrets.token_hex(8),
            lease_seconds=int(ttl.total_seconds()),
            renewable=False,
            policies=(policy,),
        )

    def holding(self, token: RoleToken) -> _Holder:
        return _Holder(self, token.policies[0])


@dataclass
class _Holder:
    """One child token's client: what its one policy grants, and a 403 for everything else."""

    vault: _RoleVault
    policy: str

    def read_static_kv(self, path: str) -> dict[str, Any]:
        from brain.ops.connector_lease import RUN_POLICY
        from brain.ops.openbao import VaultRefusedError

        with self.vault._lock:
            if self.policy != RUN_POLICY:
                self.vault.refused.append((self.policy, "read"))
                raise VaultRefusedError("this token's policy grants no read", status=403)
            self.vault.reads.append((self.policy, path))
            held = self.vault.slots.get(path)
        if held is None:
            raise VaultRefusedError("the vault holds nothing at that slot", status=404)
        return dict(held)

    def patch_static_kv(self, path: str, fields: Mapping[str, str]) -> None:
        from brain.ops.connector_lease import ROTATE_POLICY
        from brain.ops.credentials import OAUTH_REFRESH_DIRECTORY
        from brain.ops.openbao import CONNECTOR_KEY_PREFIX, VaultRefusedError

        refresh = path.startswith(f"{CONNECTOR_KEY_PREFIX}{OAUTH_REFRESH_DIRECTORY}/")
        with self.vault._lock:
            if self.policy != ROTATE_POLICY or not refresh:
                self.vault.refused.append((self.policy, "patch"))
                raise VaultRefusedError("this token's policy grants no patch here", status=403)
            if path not in self.vault.slots:
                raise VaultRefusedError("a patch never creates a slot", status=404)
            self.vault.patches.append((self.policy, path))
            self.vault.slots[path] = {**self.vault.slots[path], **fields}

    def revoke_self(self) -> None:
        with self.vault._lock:
            self.vault.revoked += 1


@dataclass
class _Vendor:
    """The vendor's consent page, token endpoint and API, as recorded answers. No socket.

    It issues a code for a consent it was sent to, exchanges it only with the verifier whose S256
    challenge the consent carried and the client's own secret, rotates the refresh token on every
    renewal and voids the old one, as Xero documents, and answers Xero's invoice list only to the
    access token it issued last. `refusing` has it answer a renewal or a code with `invalid_grant`.
    """

    client_id: str
    client_secret: str = field(repr=False)
    invoice_id: str
    refusing: bool = False
    challenges: dict[str, str] = field(default_factory=dict, repr=False)
    refresh: str = field(default="", repr=False)
    access: str = field(default="", repr=False)
    exchanged: list[str] = field(default_factory=list)
    sent_to_api: list[str] = field(default_factory=list, repr=False)

    def consent(self, address: str) -> tuple[str, str]:
        """The person consenting on the vendor's page: the state and the code it sends back."""
        asked = {key: values[0] for key, values in parse_qs(urlsplit(address).query).items()}
        if not address.startswith(f"{AUTHORIZE_URL}?") or asked.get("client_id") != self.client_id:
            raise CheckFailedError("the console did not send the person to the vendor's own page")
        if asked.get("code_challenge_method") != "S256" or asked.get("redirect_uri") != (
            CONSOLE_RETURN
        ):
            raise CheckFailedError("the consent was not asked with an S256 challenge and the page")
        code = secrets.token_urlsafe(24)
        self.challenges[code] = asked["code_challenge"]
        return asked["state"], code

    def post(
        self, url: str, *, address: str, headers: Mapping[str, str], body: bytes, max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, headers, max_bytes
        form = {key: values[0] for key, values in parse_qs(body.decode("ascii")).items()}
        refused = SourceAnswer(status=400, headers={}, body=b'{"error": "invalid_grant"}')
        if (
            url != VENDOR_EXCHANGE
            or form.get("client_secret") != self.client_secret
            or self.refusing
        ):
            return refused
        grant = form.get("grant_type", "")
        self.exchanged.append(grant)
        if grant == "authorization_code":
            challenge = self.challenges.pop(form.get("code", ""), None)
            verifier = form.get("code_verifier", "")
            digest = hashlib.sha256(verifier.encode("ascii")).digest()
            if challenge != base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii"):
                return refused
        elif grant != "refresh_token" or form.get("refresh_token") != self.refresh:
            return refused
        self.refresh, self.access = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        issued = {
            "access_token": self.access,
            "token_type": "Bearer",
            "expires_in": 1800,
            "refresh_token": self.refresh,
        }
        return SourceAnswer(status=200, headers={}, body=json.dumps(issued).encode())

    def get(
        self, url: str, *, address: str, headers: Mapping[str, str], max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, max_bytes
        sent = headers.get("Authorization", "")
        self.sent_to_api.append(sent)
        if sent != f"Bearer {self.access}" or not self.access:
            return SourceAnswer(status=401, headers={}, body=b"{}")
        if "/Contacts" in url:
            return SourceAnswer(status=200, headers={}, body=b'{"Contacts": []}')
        invoice = {"InvoiceID": self.invoice_id, "InvoiceNumber": "INV-1", "Status": "AUTHORISED"}
        return SourceAnswer(
            status=200, headers={}, body=json.dumps({"Invoices": [invoice]}).encode()
        )


class _Consented:
    """Xero's own reading, presenting the OAuth scheme and the check's consent. Nothing else."""

    def __init__(self, inner: SourceReading, consent: OAuthConsent) -> None:
        self._inner = inner
        self._consent = consent

    def consent(self) -> OAuthConsent:
        return self._consent

    def key_scheme(self) -> Any:
        from brain.connectors.declaration import KeyScheme

        return KeyScheme.OAUTH_REFRESH

    def entities(self) -> tuple[str, ...]:
        return self._inner.entities()

    def refresh_interval(self) -> timedelta:
        return self._inner.refresh_interval()

    def operation(self, entity: str, *, settings: Mapping[str, str], resolver: Resolver) -> Any:
        return self._inner.operation(entity, settings=settings, resolver=resolver)

    def first_page(self, entity: str) -> Mapping[str, str]:
        return self._inner.first_page(entity)

    def next_page(
        self, entity: str, asked: Mapping[str, str], body: Any, returned: int
    ) -> Mapping[str, str] | None:
        return self._inner.next_page(entity, asked, body, returned)

    def call_headers(self, settings: Mapping[str, str]) -> Mapping[str, str]:
        return self._inner.call_headers(settings)

    def interpret(
        self, operation: RestOperation, *, status: int, body: Any, fetched_at: str
    ) -> PageReply:
        return self._inner.interpret(operation, status=status, body=body, fetched_at=fetched_at)

    def retry_after(self, headers: Mapping[str, str]) -> float | None:
        return self._inner.retry_after(headers)

    def allowance_spent(self, headers: Mapping[str, str]) -> bool:
        return self._inner.allowance_spent(headers)

    def projected(
        self, entity: str, row: Mapping[str, Any], *, seen_at: datetime
    ) -> ProjectedRecord | None:
        return self._inner.projected(entity, row, seen_at=seen_at)


def consented_xero() -> tuple[ConnectorDeclaration, _Consented]:
    """Xero's declaration with a consent declared on it, and the reading that renews by it."""
    from brain.connectors import xero
    from brain.connectors.declaration import Setting, ViewReading
    from brain.connectors.oauth import OAuthConsent

    declared = xero.CONNECTOR
    assert declared.console is not None and declared.reading is not None  # Xero declares both
    consent = OAuthConsent(
        authorize_url=AUTHORIZE_URL,
        token_url=VENDOR_EXCHANGE,
        scopes=("accounting.transactions.read", "offline_access"),
        client_id_setting=CLIENT_ID_SETTING,
    )
    inner = declared.reading
    if isinstance(inner, ViewReading):
        raise CheckFailedError("Xero's reading is no longer a REST reading")
    reading = _Consented(inner, consent)
    client_id = Setting(
        name=CLIENT_ID_SETTING,
        label="Client id",
        hint="The client id of the application registered at the vendor.",
        refused="That is not a client id.",
    )
    form = replace(declared.console, settings=(*declared.console.settings, client_id), example=None)
    return (
        replace(declared, console=form, reading=reading, guide=(), oauth=consent),
        reading,
    )


# ------------------------------------------------------------------------ the check
@check(
    leaves=("M11.8.6",),
    sentence=(
        "Because no shipped source uses OAuth yet (Google Workspace will be the first), one is "
        "stood up from Xero's declaration and consented to through the console's routes: a wrong "
        "or replayed state is refused, the code is exchanged, and the refresh token is kept in the "
        "vault and no table. The worker renews access with it, a rotated token is written back, "
        "and a refused renewal leaves the source down."
    ),
)
async def a_consented_source_is_renewed_by_its_read_and_a_refusal_is_said(h: Harness) -> None:
    from brain.audit.record import credential_subject_id
    from brain.connector_routes import (
        CONSENT_KEPT,
        ConsentExchange,
        ConsentRefusedError,
        finish_consent,
        start_consent,
    )
    from brain.connectors.contract import HealthState
    from brain.connectors.manifest import manifest_digest
    from brain.connectors.oauth import CONSENT_WITHDRAWN
    from brain.ops.connectable import manifest_for
    from brain.ops.connector_consent import StoredConsentHealth, StoredConsents
    from brain.ops.connector_lease import ROTATE_POLICY, RUN_POLICY
    from brain.ops.connector_store import Connection, StoredConnections, live
    from brain.ops.connector_sync import SyncOutcome, plan_for
    from brain.ops.connector_sync_run import WorkerConnectorKeys, attempt
    from brain.ops.connector_sync_store import attempt_row, read_live, read_states
    from brain.ops.credential_write_store import StoredCredentialHistory, StoredCredentialWrites
    from brain.ops.credentials import (
        KEY_FIELD,
        Credentials,
        connector_key_slot,
        connector_oauth_slot,
    )

    declared, reading = consented_xero()
    source = declared.name
    if (await h.execute(live(source))).scalar_one_or_none() is not None:
        raise CheckNotRunError(XERO_IS_CONNECTED_HERE_ALREADY)

    # The application registered at the vendor, and the vault both halves of the product ask.
    vendor = _Vendor(
        client_id=f"client-{secrets.token_hex(6)}",
        client_secret=secrets.token_urlsafe(32),
        invoice_id=str(uuid.uuid4()),
    )
    vault = _RoleVault()
    credentials = Credentials(vault, writes=StoredCredentialWrites(h.sessions))
    settings = {"tenant_id": str(uuid.uuid4()), CLIENT_ID_SETTING: vendor.client_id}
    connection = Connection(
        connector=source,
        settings=settings,
        digest=manifest_digest(manifest_for(source, settings)),
        connected_by=h.actor,
        connected_at=h.now,
    )

    async def keep_secret() -> datetime | None:
        kept = await credentials.keep(
            connector_key_slot(source), vendor.client_secret, actor=h.actor, trace_id=h.trace_id
        )
        return kept.set_at

    # Connected as the connect route connects it: settings with the client id, the secret kept.
    await StoredConnections(h.sessions).connect(
        connector=source,
        settings=settings,
        digest=connection.digest,
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        keep_key=keep_secret,
    )
    consents = StoredConsents(h.sessions)
    exchange = ConsentExchange(
        keys=WorkerConnectorKeys(vault),
        poster=vendor,
        resolver=_Resolver(),
        health=StoredConsentHealth(h.sessions),
    )

    async def connected(name: str) -> Connection | None:
        return connection if name == source else None

    async def answer(state: str, code: str, *, principal: str | None = None) -> Any:
        return await finish_consent(
            state=state,
            code=code,
            vendor_refused=False,
            principal_id=principal or h.actor,
            may_connect=lambda name: name == source,
            declarations={source: declared},
            connected=connected,
            consents=consents,
            exchange=exchange,
            credentials=credentials,
            trace_id=h.trace_id,
            ent_hash=SET_UP_REACH,
            now=h.now,
        )

    # The consent, started as the route starts it: the person goes to the vendor's own page.
    address = await start_consent(
        declared,
        connection,
        consents=consents,
        principal_id=h.actor,
        return_address=CONSOLE_RETURN,
        now=h.now,
    )
    if vendor.client_secret in address:
        raise CheckFailedError("the vendor's address carried the client secret")
    state, code = vendor.consent(address)

    # A state nobody issued, and the right state answered by somebody else, are refused alike.
    somebody_else = h.principal(RESERVED_DEPARTMENTS[0], "analyst")
    for wrong, principal in ((secrets.token_urlsafe(32), None), (state, somebody_else)):
        try:
            await answer(wrong, code, principal=principal)
        except ConsentRefusedError as refused:
            if refused.status != 404:
                raise CheckFailedError("a wrong state was refused as something else") from None
        else:
            raise CheckFailedError("a consent was taken with a state that was not the person's")
    if vendor.exchanged:
        raise CheckFailedError("a code was exchanged for a state that was refused")

    # The right one: the code exchanged with its verifier, the refresh token kept, once.
    done = await answer(state, code)
    if not done.kept or done.told != CONSENT_KEPT or vendor.exchanged != ["authorization_code"]:
        raise CheckFailedError("the vendor's code was not exchanged and kept")
    slot = connector_oauth_slot(source).path
    if vault.slots.get(slot, {}).get(KEY_FIELD) != vendor.refresh:
        raise CheckFailedError("the refresh token the vendor issued is not in its vault slot")
    history = StoredCredentialHistory(h.sessions)
    if not await history.changes(f"credential:{credential_subject_id(slot)}"):
        raise CheckFailedError("keeping the refresh token left no entry in the ledger")
    try:
        await answer(state, code)
    except ConsentRefusedError:
        pass
    else:
        raise CheckFailedError("a consent's state was used twice")

    # The worker's read: access renewed from the kept token, the rotated one written back.
    first_refresh = vendor.refresh
    plan = plan_for(connection, last=None, now=h.now, readings={source: reading})
    if plan.refused or not plan.due:
        raise CheckFailedError("the worker's plan would not read the consented source")
    async with h.sessions() as session:
        ids = {one.connection.connector: one for one in await read_live(session)}
    one = ids.get(source)
    if one is None:
        raise CheckFailedError("the connected source is not a live connection")

    async def read() -> Any:
        return await attempt(
            one,
            plan,
            previous=None,
            sessions=h.sessions,
            keys=WorkerConnectorKeys(vault),
            caller=vendor,
            resolver=_Resolver(),
            clock=lambda: h.now,
            sleep=_no_wait,
            poster=vendor,
        )

    read_once = await read()
    if read_once.outcome is not SyncOutcome.SYNCED or read_once.records < 1:
        raise CheckFailedError("the worker did not read the consented source with renewed access")
    if vendor.exchanged != ["authorization_code", "refresh_token"]:
        raise CheckFailedError("the worker's read did not renew access once from the refresh token")
    if vault.slots[slot][KEY_FIELD] != vendor.refresh or vendor.refresh == first_refresh:
        raise CheckFailedError("the refresh token the vendor rotated was not written back")
    if vault.patches != [(ROTATE_POLICY, slot)] or (RUN_POLICY, slot) not in vault.reads:
        raise CheckFailedError("the rotated token was not written by the rotate role alone")
    if vault.refused:
        raise CheckFailedError("a token was asked for something its policy does not grant")
    sent = set(vendor.sent_to_api)
    if not sent or sent != {f"Bearer {vendor.access}"}:
        raise CheckFailedError("the source was sent something other than the renewed access")
    for secret in (vendor.client_secret, first_refresh, vendor.refresh, state):
        if await _search(h, secret):
            raise CheckFailedError("a client secret, refresh token or state was found in a table")

    # The vendor withdraws the consent: the next read leaves the source down, in words.
    vendor.refusing = True
    withdrawn = await read()
    if withdrawn.health is not HealthState.DOWN or withdrawn.detail != CONSENT_WITHDRAWN:
        raise CheckFailedError("a refused renewal did not leave the source down, said in words")
    async with h.sessions() as session, session.begin():
        await session.execute(attempt_row(one.id, withdrawn))
    async with h.sessions() as session:
        shown = (await read_states(session)).get(one.id)
    if shown is None or shown.health is not HealthState.DOWN or shown.detail != CONSENT_WITHDRAWN:
        raise CheckFailedError(
            "the Connectors screen's record does not say the consent was withdrawn"
        )
