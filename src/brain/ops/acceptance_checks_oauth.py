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

**And a person's own consent is checked the same way (`a_persons_own_consent_is_read_for_them_
alone`).** The same Xero declaration, consented to by each person for themselves
(`consented_personally`), over a vendor holding one account per person (`_Accounts`): a person
holding the reader capability consents through `start_consent` and `finish_consent`, their read is
`brain.ops.connector_sync_run.personal_access` leasing their own slot under the person role, a
second person's read leases only theirs and is told they have not connected, a withdrawal at the
vendor is said to that person alone with the source's health untouched, and erasing them is
`brain.ops.erasure_store.erase_own_refresh_tokens` removing their slot and nobody else's.

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
    removed: list[str] = field(default_factory=list)
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
        from brain.ops.connector_lease import (
            PERSON_POLICY,
            PERSON_TOKEN_ROLE,
            ROTATE_POLICY,
            ROTATE_TOKEN_ROLE,
            RUN_POLICY,
        )
        from brain.ops.leases import SealedSecret
        from brain.ops.openbao import RoleToken

        del meta
        policy = {ROTATE_TOKEN_ROLE: ROTATE_POLICY, PERSON_TOKEN_ROLE: PERSON_POLICY}.get(
            role, RUN_POLICY
        )
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

    # The worker's own token on erasure: delete on a person's slot's metadata and nothing else.
    def remove_static_kv(self, path: str) -> None:
        from brain.ops.connector_sync_run import is_person_slot
        from brain.ops.openbao import VaultRefusedError

        with self._lock:
            if not is_person_slot(path):
                self.refused.append(("worker", "delete"))
                raise VaultRefusedError(
                    "the worker's policy deletes no slot but a person's", status=403
                )
            self.removed.append(path)
            self.slots.pop(path, None)


@dataclass
class _Holder:
    """One child token's client: what its one policy grants, and a 403 for everything else."""

    vault: _RoleVault
    policy: str

    def read_static_kv(self, path: str) -> dict[str, Any]:
        from brain.ops.connector_lease import PERSON_POLICY, RUN_POLICY
        from brain.ops.connector_sync_run import is_person_slot
        from brain.ops.openbao import VaultRefusedError

        # The run policy reads a source's key and its own refresh token, and the person policy a
        # person's slot alone: each line of `ops/openbao/policies`, by the path's depth.
        reads = PERSON_POLICY if is_person_slot(path) else RUN_POLICY
        with self.vault._lock:
            if self.policy != reads:
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
            may_consent_personally=lambda declared, connection: False,
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


# ------------------------------------------------------------------ a person's own consent
#: The capability a person holds in the connection's department to connect their own account.
PERSONAL_READER: Final = "read:consented_account"


@dataclass
class _Accounts:
    """A vendor holding one account per person: a consent page, a token endpoint and an API.

    A code is issued for the account that signed in; a refresh token renews that account's access
    alone and is rotated on every renewal; the API answers each access token with its own
    account's words and nothing else. `revoked` names accounts whose consent the vendor withdrew.
    """

    client_id: str
    client_secret: str = field(repr=False)
    codes: dict[str, tuple[str, str]] = field(default_factory=dict, repr=False)
    refresh: dict[str, str] = field(default_factory=dict, repr=False)
    access: dict[str, str] = field(default_factory=dict, repr=False)
    revoked: set[str] = field(default_factory=set)
    renewed_for: list[str] = field(default_factory=list)

    def consent(self, address: str, account: str) -> tuple[str, str]:
        """`account` signing in on the vendor's page: the state and the code sent back."""
        asked = {key: values[0] for key, values in parse_qs(urlsplit(address).query).items()}
        if not address.startswith(f"{AUTHORIZE_URL}?") or asked.get("client_id") != self.client_id:
            raise CheckFailedError("the person was not sent to the vendor's own page")
        code = secrets.token_urlsafe(24)
        self.codes[code] = (account, asked["code_challenge"])
        return asked["state"], code

    def _issue(self, account: str) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        refresh, access = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.refresh[refresh], self.access[access] = account, account
        issued = {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": 1800,
            "refresh_token": refresh,
        }
        return SourceAnswer(status=200, headers={}, body=json.dumps(issued).encode())

    def post(
        self, url: str, *, address: str, headers: Mapping[str, str], body: bytes, max_bytes: int
    ) -> SourceAnswer:
        from brain.ops.connector_sync_run import SourceAnswer

        del address, headers, max_bytes
        form = {key: values[0] for key, values in parse_qs(body.decode("ascii")).items()}
        refused = SourceAnswer(status=400, headers={}, body=b'{"error": "invalid_grant"}')
        if url != VENDOR_EXCHANGE or form.get("client_secret") != self.client_secret:
            return refused
        if form.get("grant_type") == "authorization_code":
            account, challenge = self.codes.pop(form.get("code", ""), ("", ""))
            digest = hashlib.sha256(form.get("code_verifier", "").encode("ascii")).digest()
            if not account or challenge != base64.urlsafe_b64encode(digest).rstrip(b"=").decode():
                return refused
            return self._issue(account)
        account = self.refresh.pop(form.get("refresh_token", ""), "")
        if not account or account in self.revoked:
            return refused
        self.renewed_for.append(account)
        return self._issue(account)

    def mailbox(self, access: str) -> str:
        """What the vendor's API answers an access token: its own account's words, or nothing."""
        return f"mail of {self.access[access]}" if access in self.access else ""


def consented_personally() -> ConnectorDeclaration:
    """Xero's declaration, consented to by each person for their own account, with the department
    its readers are held to. Its scheduled reading is Xero's own: a person's consent renews no read
    made with nobody present."""
    from brain.connectors import xero
    from brain.connectors.declaration import PERSONAL_DEPARTMENT_SETTING, Setting
    from brain.connectors.oauth import ConsentKind, OAuthConsent

    declared = xero.CONNECTOR
    assert declared.console is not None  # Xero declares its form
    consent = OAuthConsent(
        authorize_url=AUTHORIZE_URL,
        token_url=VENDOR_EXCHANGE,
        scopes=("offline_access",),
        client_id_setting=CLIENT_ID_SETTING,
        kind=ConsentKind.PERSON,
        reader=PERSONAL_READER,
    )
    added = tuple(
        Setting(name=name, label=label, hint=f"The {label.lower()}.", refused="That is not one.")
        for name, label in (
            (CLIENT_ID_SETTING, "Client id"),
            (PERSONAL_DEPARTMENT_SETTING, "Department"),
        )
    )
    form = replace(declared.console, settings=(*declared.console.settings, *added), example=None)
    return replace(declared, console=form, guide=(), oauth=consent)


@check(
    leaves=("M11.8.6",),
    sentence=(
        "A source each person connects for their own account, stood up from Xero's declaration: a "
        "person holding its reader capability consents for themselves and their read uses their "
        "own token alone, another person's read never touches it, a consent the vendor withdraws "
        "leaves only that person's reads down in words, and erasing them removes their token."
    ),
)
async def a_persons_own_consent_is_read_for_them_alone(h: Harness) -> None:
    from sqlalchemy import func, select, text

    from brain.connector_routes import (
        YOUR_CONSENT_KEPT,
        ConsentExchange,
        ConsentRefusedError,
        finish_consent,
        may_consent_for_themselves,
        start_consent,
    )
    from brain.connectors.manifest import manifest_digest
    from brain.connectors.oauth import (
        NOT_CONNECTED_FOR_YOU,
        YOUR_CONSENT_WITHDRAWN,
        ConsentNotHeldError,
        ConsentWithdrawnError,
    )
    from brain.core.scope import Scope
    from brain.ops.acceptance_checks_tables import _console
    from brain.ops.connectable import manifest_for, person_refresh_reference
    from brain.ops.connector_consent import StoredConsentHealth, StoredConsents
    from brain.ops.connector_lease import PERSON_POLICY
    from brain.ops.connector_store import Connection, StoredConnections, live
    from brain.ops.connector_sync_run import (
        PersonalKeys,
        WorkerConnectorKeys,
        personal_access,
        personal_words,
    )
    from brain.ops.credential_write_store import StoredCredentialWrites
    from brain.ops.credentials import (
        KEY_FIELD,
        Credentials,
        connector_key_slot,
        connector_oauth_slot,
        connector_person_oauth_slot,
    )
    from brain.ops.erasure_store import REMOVED, SUBJECT_COLUMNS, erase_own_refresh_tokens
    from brain.ops.secrets import SecretsUnavailableError
    from brain.tables.oauth_consent import OAuthConsentRow

    declared = consented_personally()
    consent = declared.oauth
    assert consent is not None  # declared just above
    source = declared.name
    if (await h.execute(live(source))).scalar_one_or_none() is not None:
        raise CheckNotRunError(XERO_IS_CONNECTED_HERE_ALREADY)
    await h.found_departments()
    department = RESERVED_DEPARTMENTS[0]

    vendor = _Accounts(
        client_id=f"client-{secrets.token_hex(6)}", client_secret=secrets.token_urlsafe(32)
    )
    vault = _RoleVault()
    credentials = Credentials(vault, writes=StoredCredentialWrites(h.sessions))
    settings = {
        "tenant_id": str(uuid.uuid4()),
        CLIENT_ID_SETTING: vendor.client_id,
        "department": department,
    }
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

    await StoredConnections(h.sessions).connect(
        connector=source,
        settings=settings,
        digest=connection.digest,
        actor=h.actor,
        trace_id=h.trace_id,
        ent_hash=SET_UP_REACH,
        keep_key=keep_secret,
    )

    # Two readers of the department, and a third person holding nothing there.
    ada, bea, cal = (h.principal(department, one) for one in ("ada", "bea", "cal"))
    reader = ((PERSONAL_READER, Scope.department(department)),)
    for person, grants in ((ada, reader), (bea, reader), (cal, ())):
        await h.person(person, department=department, grants=grants)
    reaches = {one: await _console(h, one, second_factor=False) for one in (ada, bea, cal)}
    if may_consent_for_themselves(reaches[cal], declared, connection, h.now):
        raise CheckFailedError("a person without the reader capability may connect their account")

    consents = StoredConsents(h.sessions)
    exchange = ConsentExchange(
        keys=WorkerConnectorKeys(vault),
        poster=vendor,
        resolver=_Resolver(),
        health=StoredConsentHealth(h.sessions),
    )

    async def connected(name: str) -> Connection | None:
        return connection if name == source else None

    async def own_consent(person: str) -> Any:
        address = await start_consent(
            declared,
            connection,
            consents=consents,
            principal_id=person,
            return_address=CONSOLE_RETURN,
            now=h.now,
        )
        state, code = vendor.consent(address, person)
        return await finish_consent(
            state=state,
            code=code,
            vendor_refused=False,
            principal_id=person,
            may_connect=lambda name: False,
            may_consent_personally=lambda one, live_one: may_consent_for_themselves(
                reaches[person], one, live_one, h.now
            ),
            declarations={source: declared},
            connected=connected,
            consents=consents,
            exchange=exchange,
            credentials=credentials,
            trace_id=h.trace_id,
            ent_hash=SET_UP_REACH,
            now=h.now,
        )

    def read_for(person: str) -> str:
        """`person`'s own read: their access renewed and the vendor's API asked with it."""
        token = personal_access(
            consent,
            connector=source,
            principal_id=person,
            settings=settings,
            keys=WorkerConnectorKeys(vault),
            poster=vendor,
            resolver=_Resolver(),
            now=h.now,
        )
        return vendor.mailbox(token.value)

    # Somebody without the capability cannot answer a consent of their own into the source.
    try:
        await own_consent(cal)
    except ConsentRefusedError as refused:
        if refused.status != 404:
            raise CheckFailedError(
                "a person without the capability was refused as something else"
            ) from None
    else:
        raise CheckFailedError("a person without the reader capability kept a consent")

    # Ada consents for herself: her token is kept in her slot, the source's own slot is untouched.
    done = await own_consent(ada)
    ada_slot = connector_person_oauth_slot(source, ada).path
    if not done.kept or done.told != YOUR_CONSENT_KEPT or not done.personal:
        raise CheckFailedError("a person's own consent was not kept as theirs")
    if vault.slots.get(ada_slot, {}).get(KEY_FIELD) not in vendor.refresh:
        raise CheckFailedError("a person's refresh token is not in their own slot")
    if connector_oauth_slot(source).path in vault.slots:
        raise CheckFailedError("a person's own consent was kept where every read would use it")

    # Her read uses her own token, leased under the person role, and answers her account alone.
    if read_for(ada) != f"mail of {ada}" or vendor.renewed_for != [ada]:
        raise CheckFailedError("a person's read did not use their own consent")
    if (PERSON_POLICY, ada_slot) not in vault.reads:
        raise CheckFailedError("a person's token was not read under the person role")

    # Bea has not consented: her read is told so, and never leases or renews with Ada's token.
    reads_before = list(vault.reads)
    try:
        read_for(bea)
    except ConsentNotHeldError as refused:
        if personal_words(refused) != NOT_CONNECTED_FOR_YOU:
            raise CheckFailedError("a person with no consent was not told so in words") from None
    else:
        raise CheckFailedError("a person with no consent of their own was read for")
    if any(path == ada_slot for _, path in vault.reads[len(reads_before) :]):
        raise CheckFailedError("one person's read leased another person's token")
    if vendor.renewed_for != [ada]:
        raise CheckFailedError("one person's read renewed another person's consent")
    # And asked outright for Ada's slot, Bea's keys refuse before the vault is asked.
    theirs = PersonalKeys(WorkerConnectorKeys(vault), connector=source, principal_id=bea)
    asked = len(vault.reads)
    leased = theirs.lease(person_refresh_reference(source, ada), now=h.now)
    try:
        leased.key()
    except SecretsUnavailableError:
        refused_there = True
    else:
        refused_there = False
    finally:
        leased.close(h.now)
    if not refused_there:
        raise CheckFailedError("a person's keys leased another person's slot")
    if len(vault.reads) != asked:
        raise CheckFailedError("another person's slot was asked of the vault at all")

    # Bea consents too, and each read answers its own account.
    await own_consent(bea)
    if read_for(bea) != f"mail of {bea}" or read_for(ada) != f"mail of {ada}":
        raise CheckFailedError("two people's reads did not each use their own consent")

    # The vendor withdraws Ada's consent: her reads are down in words, Bea's and the source are not.
    vendor.revoked.add(ada)
    try:
        read_for(ada)
    except ConsentWithdrawnError as refused:
        if personal_words(refused) != YOUR_CONSENT_WITHDRAWN:
            raise CheckFailedError("a withdrawn consent was not said in words") from None
    else:
        raise CheckFailedError("a consent the vendor withdrew was still read")
    if read_for(bea) != f"mail of {bea}":
        raise CheckFailedError("one person's withdrawn consent took another person's reads down")
    if await StoredConsentHealth(h.sessions).latest(source) is None:
        raise CheckFailedError("the connected source is not a live connection")
    marked = await StoredConsentHealth(h.sessions).latest(source)
    if marked is not None and marked.previous is not None:
        raise CheckFailedError("one person's withdrawn consent was marked on the source")

    # Erasing Ada removes her slot, every version, and nobody else's.
    bea_slot = connector_person_oauth_slot(source, bea).path
    erase_own_refresh_tokens(vault, ada, (source,))
    if ada_slot in vault.slots or bea_slot not in vault.slots or vault.removed != [ada_slot]:
        raise CheckFailedError("erasing a person did not remove their own token and only theirs")
    if vault.refused:
        raise CheckFailedError("a token was asked for something its policy does not grant")
    # And her consent rows: the erasure queue removes them, by her principal, and the application
    # may never delete one. The queue runs as the database owner on a schedule, outside this
    # check's transaction, so what is asked here is what it decides by; the removal itself is
    # `tests/unit/test_own_consent.py`'s, at head.
    if (
        REMOVED.get("ops.oauth_consent") is None
        or SUBJECT_COLUMNS.get("ops.oauth_consent") != "principal_id"
    ):
        raise CheckFailedError("erasing a person would not remove their consent rows")
    may_delete = await h.execute(
        text("SELECT has_table_privilege(current_user, 'ops.oauth_consent', 'DELETE')")
    )
    if may_delete.scalar_one():
        raise CheckFailedError("the application may delete a person's consent rows")
    held = await h.execute(
        *h.attributed(ada),
        select(func.count())
        .select_from(OAuthConsentRow)
        .where(OAuthConsentRow.principal_id == ada),
    )
    if held.scalar_one() < 1:
        raise CheckFailedError(
            "a person's consent is not held as theirs, so erasure cannot find it"
        )
    for secret in (vendor.client_secret, *vendor.refresh, *vendor.access):
        if await _search(h, secret):
            raise CheckFailedError("a client secret or a person's token was found in a table")
