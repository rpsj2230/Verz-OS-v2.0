"""An OpenBao-backed vault: the thing that actually mints a lease.

`brain.ops.secrets` defines what a vault must do and what a lease is. This is the one
implementation that talks to a real server, and everything about it is shaped by one rule
from that module: **there is no read-by-path**. A vault that can hand over a standing
credential is a vault whose credentials live as long as the caller, and leasing exists so
they do not.

**Only dynamic engines, and that is a refusal rather than a limitation.** OpenBao's `kv`
engine stores a value you wrote and returns it forever; its `database` and cloud engines
mint a fresh credential per request with the server's own expiry attached. Asking `kv` for
a lease produces one with no `lease_id` and no TTL, which this treats as an error rather
than inventing an expiry for it. An invented expiry is worse than none: the caller believes
the credential stops working and it does not.

**Two clocks, and the vault's wins.** The lease carries an expiry computed from the
server's `lease_duration`, not from the TTL we asked for. Those differ whenever the mount's
maximum is shorter than the request, and taking our own number would have the application
believing it holds a working credential after the server has already withdrawn it -
credentials failing while the code is certain they should not.

**No retries on issue.** A credential request that failed is a request that may or may not
have created a credential on the far side; retrying it can leave orphaned leases nobody
will revoke, because the lease id we would need in order to revoke them came back only on
the response we did not get. `revoke` is different and does retry, because a failed
revocation leaves a live credential and that is the failure worth being noisy about.

**It writes under the static prefix, and reads that prefix's metadata, and neither is a way
back to a value.** Until 2026-09-16 this class could issue, read `providers/` and revoke, so
a provider key could only reach the vault through somebody at the server with a root token.
`write_static_kv` puts one slot's fields in and returns the version time the vault stamped;
`static_kv_version` reads the slot's metadata, which carries versions and times and no
field of the secret at all. The prefix refusal is the same one the read has and lives here
for the same reason: a writer that could put a value at `connectors/creds/xero` would be
writing over a path the leasing design says is minted, not stored. Why the application may
hold write at all is argued in `brain.ops.credentials`.

**A refusal and a silence are two types now**, `VaultRefusedError` and
`VaultUnreachableError`, both still `SecretsUnavailableError` so every existing handler
catches them unchanged. The difference is what a person is told to do: a vault that did not
answer is sealed, stopped or unreachable, and one that answered no is a token, a policy or an
engine that is not there. Reading the status out of a message string would work until
somebody reworded the message.

**A second static engine, `webhooks/`, for the one other kind of secret nothing can lease.**
A webhook subscriber's signing secret is shared with the receiver, which checks every request
against it, so a vault that minted a fresh one per delivery would sign requests no receiver
can verify. It is written from the console (`brain.ops.webhook_admin`) and is admitted by
`assert_static_path` as an exact second prefix beside `providers/`, so `connectors/creds/`
and every other leased path are refused exactly as before. See
`A_SIGNING_KEY_EVERY_RECEIVER_CHECKS_CANNOT_BE_MINTED`.

**A third, `connector_keys/`, for the key a source's vendor issued.** Connecting a source from the
console (`brain.ops.connector_admin`) keeps the key its vendor issued for this company, which no
engine can mint any more than it can mint a provider key: a helpdesk's agent key or a CRM's private
app token is valid until somebody revokes it in the vendor's own settings. It is a prefix of its
own and not a path under `connectors/`, because `connectors/creds/` is the leased path and a prefix
check reading `startswith` would admit every lease beside it. See
`A_KEY_A_VENDOR_ISSUED_IS_STORED_BECAUSE_NOTHING_CAN_MINT_IT`.

**It asks about its own token and renews it, and never anybody else's.** A periodic token lapses
when nobody renews it inside its period, and renewal is a call made *with* the token: OpenBao
renews a token by its value, at `auth/token/renew-self` or `auth/token/renew`, and offers no
renewal by accessor. So `token_standing` and `renew_self` take no argument naming a token, and
`brain.ops.vault_renewal` argues why each process renews the one it holds.

**A run is given a token of its own, and that token is the lease.** A vendor's key cannot be minted,
so what is leased for a connector run is the vault's authority to read it: `mint_role_token` asks
`auth/token/create/<role>` for a child of this client's token, carrying one policy, a TTL and no
renewal, and `holding` returns a client presenting it. `revoke_self` gives it back. The token is a
`SealedSecret`, so no rendering of the answer prints it. See `brain.ops.connector_lease`.

**The seal status is asked without trusting the token.** `seal_status` reads `sys/seal-status`,
which OpenBao answers for anybody, so a console can say sealed, open or silent even when the token
it holds has lapsed, which is exactly when somebody needs to know which of the three it is.

Task ids: M31.3.2.3, M31.3.2.4, M27.8.7, M27.8.12, M42.6.5, M42.6.2
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from brain.ops.leases import SealedSecret
from brain.ops.secrets import Lease, SecretRef, SecretsUnavailableError, VaultRole

#: How long to wait on the vault. Short on purpose: the vault sits on the same host on the
#: container network, so a slow answer means it is sealed, wedged or gone, and none of
#: those get better with waiting. A caller blocked here is a request the person is waiting
#: on.
TIMEOUT_SECONDS = 5.0

#: Engines that mint a fresh credential per request. Anything else stores and returns, and
#: is refused below.
DYNAMIC_MOUNTS = ("database/", "aws/", "gcp/", "azure/", "consul/")

#: The provider keys' prefix. With `SIGNING_PREFIX`, the only paths the kv methods touch.
STATIC_PREFIX = "providers/"

#: Webhook subscribers' signing secrets. See `A_SIGNING_KEY_EVERY_RECEIVER_CHECKS_CANNOT_BE_MINTED`.
SIGNING_PREFIX = "webhooks/"

#: The key a connected source's vendor issued. See
#: `A_KEY_A_VENDOR_ISSUED_IS_STORED_BECAUSE_NOTHING_CAN_MINT_IT`.
CONNECTOR_KEY_PREFIX = "connector_keys/"

#: Every prefix the kv methods admit, and nothing else in the vault is stored rather than leased.
STATIC_PREFIXES = (STATIC_PREFIX, SIGNING_PREFIX, CONNECTOR_KEY_PREFIX)

#: Why a subscriber's signing secret is kept in kv rather than leased like a connector's.
A_SIGNING_KEY_EVERY_RECEIVER_CHECKS_CANNOT_BE_MINTED = (
    "A signing secret is held by two parties: this system signs every delivery with it and the "
    "receiver verifies every delivery against it. A dynamic engine mints a different value per "
    "request, which no receiver could verify, so the secret is stored and replaced as a whole "
    "when an administrator rotates it. It is kept under an engine of its own rather than beside "
    "the provider keys, so a policy granting one never grants the other."
)


#: Why a connected source's key is kept in kv, and why under a prefix that is not `connectors/`.
A_KEY_A_VENDOR_ISSUED_IS_STORED_BECAUSE_NOTHING_CAN_MINT_IT = (
    "A source's vendor issues the key a connection reads with, and it stays valid until somebody "
    "revokes it in the vendor's own settings, so there is no engine that could mint a fresh one "
    "per run and nothing to lease. It is stored, written once from the console and never read "
    "back by the process that wrote it. It sits under connector_keys/ and not under connectors/, "
    "because connectors/creds/ is the leased path and a prefix check that admitted connectors/ "
    "would admit every lease beside the stored key."
)


class VaultRefusedError(SecretsUnavailableError):
    """The vault answered, and the answer was no. `status` is the HTTP status it gave.

    A subclass rather than a flag on the parent, so every `except SecretsUnavailableError`
    already written keeps catching it. 404 is among these: on a kv engine it is a slot never
    written, and on a write it is an engine that is not mounted at that prefix.
    """

    def __init__(self, message: str, *, status: int) -> None:
        super().__init__(message)
        self.status = status


class VaultUnreachableError(SecretsUnavailableError):
    """The vault did not answer inside `TIMEOUT_SECONDS`, or could not be connected to at all."""


@dataclass(frozen=True)
class TokenStanding:
    """What the vault says about the token this client presents, and nothing that is the token.

    `ttl_seconds` is how long it has left, `period_seconds` the period a renewal restores it to,
    zero for a token with none, and `renewable` whether the vault will renew it at all. Read from
    `auth/token/lookup-self`, whose answer also carries the token's id; that field is never read
    into this, so there is nowhere for it to go.
    """

    ttl_seconds: int
    period_seconds: int
    renewable: bool
    #: The policies the vault says the token carries, which is how the Secrets vault screen tells a
    #: token minted against its role's policy from a root token somebody pasted in. Empty when the
    #: vault did not say.
    policies: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoleToken:
    """A child token the vault minted against a token role: the lease a connector run holds.

    `token` is sealed, so `repr`, `str`, an f-string and `dataclasses.asdict` all render the seal.
    `accessor` is not a credential that reads anything and is still never logged by this module.
    `policies` is what the vault says the token carries, which the caller checks rather than
    trusting the role to have been configured as the installer wrote it.
    """

    token: SealedSecret
    accessor: str
    lease_seconds: int
    renewable: bool
    policies: tuple[str, ...]


@dataclass(frozen=True)
class SealStatus:
    """What `sys/seal-status` says: whether the vault was ever initialised, and whether sealed."""

    initialized: bool
    sealed: bool


def _seconds(value: object) -> int | None:
    """A whole number of seconds as the vault writes one, or None for anything else.

    A boolean is refused although Python counts it an integer, because `true` in a field that
    should hold a duration is a malformed answer and not one second.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


@dataclass(frozen=True)
class StaticVersion:
    """A kv slot's current version, as its metadata describes it: when it was written, if the
    vault said in a form this could read. No field could hold the secret, because metadata
    carries none."""

    written_at: datetime | None


def _instant(stamp: object) -> datetime | None:
    """An RFC 3339 time as the vault writes it, or None for anything else.

    kv v2 stamps nanoseconds and a `Z`; `datetime.fromisoformat` reads both on the interpreter
    this ships on. A value that does not parse is None rather than an exception, because the
    caller has already written the secret by the time it reads this and must not report a
    write that happened as one that failed. An empty string is not checked for separately: it
    does not parse, which is the same answer, and a mutation showed the second check changed
    nothing a caller could see.
    """
    if not isinstance(stamp, str):
        return None
    try:
        found = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return found if found.tzinfo is not None else found.replace(tzinfo=UTC)


def assert_static_path(path: str) -> None:
    """Refuse anything outside the static prefix.

    Public and separate so the refusal can be tested directly rather than only through a
    call that needs a server. `providers/anthropic` is a key nobody can lease;
    `connectors/creds/xero` is one somebody should, and reading the second one this way
    would work perfectly and be invisible. `webhooks/` and `connector_keys/` are the two other
    prefixes admitted; see `A_SIGNING_KEY_EVERY_RECEIVER_CHECKS_CANNOT_BE_MINTED` and
    `A_KEY_A_VENDOR_ISSUED_IS_STORED_BECAUSE_NOTHING_CAN_MINT_IT`.
    """
    if not any(path.startswith(prefix) for prefix in STATIC_PREFIXES):
        msg = (
            f"{path!r} is not a provider key, a signing secret or a connected source's key. "
            "Everything outside "
            f"{list(STATIC_PREFIXES)!r} is leased "
            "through brain.ops.secrets.borrow, which revokes it when the run ends; reading "
            "it here would hand back a standing credential nobody gives back."
        )
        raise SecretsUnavailableError(msg)


class OpenBaoVault:
    """Issues and revokes leases against a running OpenBao.

    Holds a token and never logs it. The token comes from the environment the container was
    started with, is read once here, and does not appear in `__repr__` for the same reason
    `Lease` overrides its own: the commonest way a credential reaches a log is an exception
    handler formatting the object that was holding it.
    """

    def __init__(self, address: str, token: str, *, role: VaultRole | None = None) -> None:
        if not address.startswith(("http://", "https://")):
            msg = f"vault address {address!r} is not a URL"
            raise ValueError(msg)
        if not token:
            # Refused at construction rather than at first use. An empty token produces a
            # 403 on the first credential request, which reads as a policy problem and
            # sends somebody to look at the wrong file.
            msg = "no vault token; the application cannot borrow a credential without one"
            raise ValueError(msg)
        self._address = address.rstrip("/")
        self._token = token
        self._role = role

    def __repr__(self) -> str:
        return f"OpenBaoVault(address={self._address!r}, role={self._role!r})"

    __str__ = __repr__

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._address}/v1/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)  # noqa: S310  scheme checked in __init__
        request.add_header("X-Vault-Token", self._token)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
                raw = response.read()
        except urllib.error.HTTPError as exc:
            # The body is read but never included in the message. OpenBao's error bodies
            # quote the path that failed, and a path names which credential was being
            # borrowed - which is exactly the fact the audit log takes care to hash.
            msg = f"vault refused {method} on a {self._mount_of(path)} path: HTTP {exc.code}"
            raise VaultRefusedError(msg, status=exc.code) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            msg = f"vault at {self._address} did not answer within {TIMEOUT_SECONDS}s"
            raise VaultUnreachableError(msg) from exc

        if not raw:
            return {}
        try:
            parsed: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            msg = "vault returned something that is not JSON"
            raise SecretsUnavailableError(msg) from exc
        return parsed

    @staticmethod
    def _mount_of(path: str) -> str:
        """The engine a path lives under, for error messages. Never the full path."""
        return path.lstrip("/").split("/", 1)[0] or "unknown"

    def issue(self, ref: SecretRef, ttl: timedelta) -> Lease:
        """Mint a credential. Fails rather than inventing anything it was not told."""
        if not any(ref.path.lstrip("/").startswith(m) for m in DYNAMIC_MOUNTS):
            msg = (
                f"{self._mount_of(ref.path)} is not a dynamic engine, so it returns a stored "
                "value rather than minting one. A stored value has no expiry the vault will "
                "enforce, and a lease over it would be a promise nothing keeps."
            )
            raise SecretsUnavailableError(msg)

        issued_at = datetime.now(UTC)
        payload = self._call("GET", f"{ref.path}?ttl={int(ttl.total_seconds())}s")

        lease_id = str(payload.get("lease_id", ""))
        if not lease_id:
            msg = (
                "the vault returned a credential with no lease id, so it cannot be revoked. "
                "That is what a static engine looks like from here."
            )
            raise SecretsUnavailableError(msg)

        # The server's duration, not the one we asked for. They differ whenever the mount's
        # maximum is shorter than the request, and believing our own number means holding a
        # credential the vault has already withdrawn.
        duration = payload.get("lease_duration")
        if not isinstance(duration, int) or duration <= 0:
            msg = "the vault returned no lease duration; refusing to invent an expiry"
            raise SecretsUnavailableError(msg)

        data = payload.get("data")
        if not isinstance(data, dict):
            msg = "the vault returned no credential data"
            raise SecretsUnavailableError(msg)
        secret = self._single_value(data)

        return Lease(
            lease_id=lease_id,
            ref=ref,
            secret=secret,
            issued_at=issued_at,
            expires_at=issued_at + timedelta(seconds=duration),
        )

    @staticmethod
    def _single_value(data: dict[str, Any]) -> str:
        """The credential out of the response body, as one string.

        A database engine returns `username` and `password` separately. They are joined
        rather than returned as a pair because `Lease.secret` is one string and widening it
        to a mapping would mean every caller decides which field is the secret - and the
        one that picks wrong picks the username, which is not secret, and logs it.
        """
        if "password" in data and "username" in data:
            return f"{data['username']}:{data['password']}"
        for key in ("password", "secret_key", "token", "value"):
            if key in data:
                return str(data[key])
        msg = f"the vault returned fields this does not recognise: {sorted(data)[:5]}"
        raise SecretsUnavailableError(msg)

    def read_static_kv(self, path: str) -> dict[str, Any]:
        """One value out of the kv engine, and only from under `STATIC_PREFIX`.

        This is read-by-path, which the `Vault` protocol deliberately does not have, so it
        lives here as a named exception with the refusal attached rather than as a general
        capability. A model provider's API key cannot be leased: OpenAI, Anthropic and
        Moonshot each issue a key that is valid until somebody revokes it in a dashboard,
        and there is no engine that mints a fresh one per request. Wrapping one in a `Lease`
        with an invented expiry would be worse than admitting it - the caller would believe
        the credential stops working at a time nothing enforces.

        **The prefix check is what stops this being the hole in the design.** Without it,
        `read_static_kv("connectors/creds/xero")` works perfectly, hands out a standing
        connector credential with nothing to revoke and no record of which run held it, and
        nothing anywhere notices. The guard is on this method rather than on the caller
        precisely because a caller can be bypassed.
        """
        assert_static_path(path)
        # kv version 2 answers on `<mount>/data/<rest>`, not on the logical path. Getting
        # this wrong returns a 404 that reads as "the slot is empty" rather than "the path
        # is wrong", and somebody then writes the key in twice.
        mount, _, rest = path.partition("/")
        payload = self._call("GET", f"{mount}/data/{rest}")
        data = payload.get("data")
        if isinstance(data, dict):
            inner = data.get("data")
            if isinstance(inner, dict):
                # kv v2 nests twice: {"data": {"data": {...}, "metadata": {...}}}.
                return inner
        return data if isinstance(data, dict) else {}

    def write_static_kv(self, path: str, fields: Mapping[str, str]) -> datetime | None:
        """Put one slot's fields into the kv engine, under `STATIC_PREFIX` only.

        Returns the time the vault stamped on the version it made, or None when its answer
        carried no time it could read. Never returns anything it was handed: the one caller
        that holds the value is the one that passed it in.

        **Not retried**, for `issue`'s reason turned round: a write that timed out may have
        landed, and a second write of the same value makes a second version whose time is not
        the time the person pressed save. The caller reports the silence and the person decides.

        The prefix refusal is `assert_static_path`, the read's own, because a writer that could
        reach `connectors/creds/xero` would be storing a value over a path the leasing design
        says the vault mints. kv version 2 takes writes on `<mount>/data/<rest>` and wraps the
        fields in `data`, which is the shape `read_static_kv` unwraps.
        """
        assert_static_path(path)
        mount, _, rest = path.partition("/")
        payload = self._call("POST", f"{mount}/data/{rest}", {"data": dict(fields)})
        data = payload.get("data")
        return _instant(data.get("created_time")) if isinstance(data, dict) else None

    def static_kv_version(self, path: str) -> StaticVersion | None:
        """The slot's current version, or None when it holds nothing.

        Read from `<mount>/metadata/<rest>`, which carries version numbers, times and deletion
        marks and **no field of the secret**, so the policy that lets the application ask this
        does not let it read a value. A slot never written answers 404 and is None; so is one
        whose current version was deleted or destroyed, because a version that cannot be read
        is not a key anything holds. A version whose time does not parse is still held, with
        no time: saying a written key is absent would send somebody to write it again.
        """
        assert_static_path(path)
        mount, _, rest = path.partition("/")
        try:
            payload = self._call("GET", f"{mount}/metadata/{rest}")
        except VaultRefusedError as refused:
            if refused.status == 404:
                return None
            raise
        data = payload.get("data")
        versions = data.get("versions") if isinstance(data, dict) else None
        current = data.get("current_version") if isinstance(data, dict) else None
        found = versions.get(str(current)) if isinstance(versions, dict) else None
        if not isinstance(found, dict):
            return None
        gone = bool(found.get("destroyed")) or bool(found.get("deletion_time"))
        if gone:
            return None
        return StaticVersion(written_at=_instant(found.get("created_time")))

    def token_standing(self) -> TokenStanding:
        """How long the token this client holds has left, as the vault answers for it.

        A malformed answer raises rather than reading as a token with no time left: a renewal
        decided on a figure the vault did not state is a renewal nobody can explain afterwards.
        """
        payload = self._call("GET", "auth/token/lookup-self")
        data = payload.get("data")
        if not isinstance(data, dict):
            msg = "the vault described this token with no data"
            raise SecretsUnavailableError(msg)
        ttl = _seconds(data.get("ttl"))
        period = _seconds(data.get("period", 0) or 0)
        renewable = data.get("renewable")
        if ttl is None or period is None or not isinstance(renewable, bool):
            msg = "the vault described this token without a readable ttl, period or renewable"
            raise SecretsUnavailableError(msg)
        named = data.get("policies")
        policies = (
            tuple(str(one) for one in named)
            if isinstance(named, list) and all(isinstance(one, str) for one in named)
            else ()
        )
        return TokenStanding(
            ttl_seconds=ttl, period_seconds=period, renewable=renewable, policies=policies
        )

    def renew_self(self) -> int:
        """Renew the token this client holds, and return the seconds the vault granted.

        Not retried, for `write_static_kv`'s reason: a renewal that timed out may have landed,
        and the next scheduled run asks again from the vault's own answer rather than from a
        guess about this one. The grant is the vault's `lease_duration`, not a period this
        process remembers, because the two differ whenever the token was minted differently.
        """
        payload = self._call("POST", "auth/token/renew-self", {})
        auth = payload.get("auth")
        granted = _seconds(auth.get("lease_duration")) if isinstance(auth, dict) else None
        if granted is None:
            msg = "the vault answered a renewal without saying how long it granted"
            raise SecretsUnavailableError(msg)
        return granted

    def seal_status(self) -> SealStatus:
        """Whether the vault is initialised and sealed. Answered by OpenBao for any caller."""
        payload = self._call("GET", "sys/seal-status")
        initialized = payload.get("initialized")
        sealed = payload.get("sealed")
        if not isinstance(initialized, bool) or not isinstance(sealed, bool):
            msg = "the vault described its seal without a readable initialized or sealed"
            raise SecretsUnavailableError(msg)
        return SealStatus(initialized=initialized, sealed=sealed)

    def static_kv_defined(self, path: str) -> bool:
        """Whether the slot exists at all, written or not: its metadata answers rather than 404.

        A slot the installer defined with its scopes and nobody has filled answers here and holds
        no version, which is the state `ops/openbao/credential-slots.md` calls empty until go-live.
        """
        assert_static_path(path)
        mount, _, rest = path.partition("/")
        try:
            self._call("GET", f"{mount}/metadata/{rest}")
        except VaultRefusedError as refused:
            if refused.status == 404:
                return False
            raise
        return True

    def mint_role_token(self, role: str, *, ttl: timedelta, meta: Mapping[str, str]) -> RoleToken:
        """A child token from `auth/token/create/<role>`, with this TTL and no renewal.

        Not retried, for `issue`'s reason: a create that timed out may have minted a token whose
        value came back only on the answer that never arrived, and it expires on its own TTL.
        The answer is refused whole when it carries no token, no duration or no policies, because a
        lease whose end this process cannot state is not one. Whether what it carries is what was
        asked for is `brain.ops.connector_lease.judge_minted`'s decision, not this parser's.
        """
        seconds = int(ttl.total_seconds())
        payload = self._call(
            "POST",
            f"auth/token/create/{role}",
            {
                "ttl": f"{seconds}s",
                "explicit_max_ttl": f"{seconds}s",
                "renewable": False,
                "no_default_policy": True,
                "meta": dict(meta),
            },
        )
        auth = payload.get("auth")
        if not isinstance(auth, dict):
            msg = "the vault answered a token request with no auth block"
            raise SecretsUnavailableError(msg)
        token = auth.get("client_token")
        accessor = auth.get("accessor")
        granted = _seconds(auth.get("lease_duration"))
        renewable = auth.get("renewable")
        policies = auth.get("policies")
        if (
            not isinstance(token, str)
            or not token
            or not isinstance(accessor, str)
            or granted is None
            or granted == 0
            or not isinstance(renewable, bool)
            or not isinstance(policies, list)
        ):
            msg = (
                "the vault answered a token request without a token, a bounded duration "
                "or its policies"
            )
            raise SecretsUnavailableError(msg)
        return RoleToken(
            token=SealedSecret(token),
            accessor=accessor,
            lease_seconds=granted,
            renewable=renewable,
            policies=tuple(str(one) for one in policies),
        )

    def holding(self, token: RoleToken) -> OpenBaoVault:
        """A client at this address presenting the child token instead of this one."""
        return OpenBaoVault(self._address, token.token.reveal(), role=self._role)

    def revoke_self(self) -> None:
        """Revoke the token this client presents. Retried, for `revoke`'s reason."""
        last: SecretsUnavailableError | None = None
        for _ in range(3):
            try:
                self._call("POST", "auth/token/revoke-self", {})
            except VaultRefusedError:
                # A refusal is an answer: the token is already gone or never was, and asking again
                # gets the same one. Raised at once so the caller can tell it from a silence.
                raise
            except SecretsUnavailableError as exc:
                last = exc
                continue
            return
        if last is not None:
            raise last

    def revoke(self, lease_id: str) -> None:
        """Give the credential back. Retries, unlike `issue`.

        A failed revocation leaves a live credential, so one network blip must not turn into
        a key that outlives the run that borrowed it. `issue` deliberately does not retry:
        a request that failed may still have minted something, and the id needed to revoke
        it came back only on the response that never arrived.
        """
        last: Exception | None = None
        for _ in range(3):
            try:
                self._call("PUT", f"sys/leases/revoke/{lease_id}")
            except SecretsUnavailableError as exc:
                last = exc
                continue
            return
        if last is not None:
            raise last
