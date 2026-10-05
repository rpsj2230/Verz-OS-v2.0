"""A send from the worker holds the vault's authority to read its channel's secret for that send and
no longer, which is the rule a connector run already follows.

The application reads a channel's secret with its own token, because it answers the channel's
events and sends every reply. The worker had no read of it at all (`ops/openbao/policies/
worker.hcl` names the model providers one at a time and nothing else under `providers/`), and a
message the worker's schedule sends, the evening digest first, needs one. Granting the worker's own
token the read would make it a standing read of every channel's secret for as long as the worker
runs, renewed for ever, which is exactly what `brain.ops.connector_lease` removed for source keys.

**So the reading is leased, in the connector run's shape.** Each send mints a child of the worker's
token against the `channel-send` token role, with `SEND_LEASE_TTL`, no renewal and one policy,
`channel-send`, which reads the channel wires' secret slots and revokes itself. The secret is read
through that token, and the token is revoked when the send ends, in a `finally`, whatever the send
came to. The worker's own policy may mint that token and reads nothing under `providers/` for a
channel itself. The role and the policy are applied by `ops/openbao/apply-release.sh`, so every
install has them from the release that ships this, with no key ceremony. See
`A_CHANNEL_IS_READ_BY_THE_WORKER_ONLY_THROUGH_A_SEND_LEASE`.

**The minted token is checked, not trusted**, by `brain.ops.connector_lease.judge_minted` with this
role's policy: a role configured renewable, wider or longer-lived than asked is given back unused.

**What this does not do, stated.** The secret, once read, is a string in the worker's memory for
the rest of the send, and the vendor accepts it for as long as the vendor does.

Task ids: M38.3.3.4
"""

from __future__ import annotations

import http.client
from datetime import datetime, timedelta
from typing import Final, Protocol

from brain.ops.channel_store import ChannelRecord
from brain.ops.connector_lease import LeaseOutcome, judge_minted
from brain.ops.connector_sync_run import RunTokenVault
from brain.ops.credentials import KEY_FIELD
from brain.ops.leases import SealedSecret
from brain.ops.openbao import OpenBaoVault, VaultRefusedError
from brain.ops.secrets import MAX_LEASE, SecretsUnavailableError, VaultRole
from brain.tables.channel import CHANNEL_SECRET_PREFIX

# ------------------------------------------------------------------ written-down reasons
#: Why the worker's policy has no read of a channel's secret.
A_CHANNEL_IS_READ_BY_THE_WORKER_ONLY_THROUGH_A_SEND_LEASE: Final = (
    "The worker's token is renewed for as long as the worker runs, so a read granted to it is a "
    "read of every channel's secret at any moment for ever. The read is granted to the "
    "channel-send policy instead, which only a child token minted per send carries, with a TTL, "
    "no renewal and revocation when the send ends."
)

# ------------------------------------------------------------------------ the lease
#: The token role the release defines and the worker mints against for one send.
SEND_TOKEN_ROLE: Final = "channel-send"  # noqa: S105

#: The one policy a send token may carry. Its file is `ops/openbao/policies/channel-send.hcl`.
SEND_POLICY: Final = "channel-send"

#: How long a send token lives if nothing revokes it. A send reads its secret in its first second
#: and posts once; five minutes covers a vendor answering slowly and bounds a lost revocation.
SEND_LEASE_TTL: Final = timedelta(minutes=5)

#: The token role's own ceiling, as the release writes it. `MAX_LEASE`, one hour.
SEND_ROLE_MAX_TTL_SECONDS: Final = int(MAX_LEASE.total_seconds())

#: Said when a send cannot borrow its channel's secret, by kind and never by value.
NO_VAULT: Final = "this worker has no vault to borrow the channel's secret from"
NOT_A_CHANNEL_SLOT: Final = "the record's secret is not a channel's slot"
SLOT_EMPTY: Final = "the channel's secret is not in the vault"


class SendLease:
    """One send's hold on its channel's secret: the secret, or why none, and the token's ending.

    Its representation names whether a token is held and how it ended, never the secret.
    """

    def __init__(
        self,
        *,
        failure: str = "",
        reader: object | None = None,
        expires_at: datetime | None = None,
        secret: SealedSecret | None = None,
    ) -> None:
        self._failure = failure
        self._reader = reader
        self._expires_at = expires_at
        self._secret = secret
        self._ended: LeaseOutcome | None = None

    def __repr__(self) -> str:
        return f"SendLease(held={self._reader is not None}, ended={self._ended})"

    __str__ = __repr__

    @property
    def failure(self) -> str:
        """Why there is no secret, or empty when there is one."""
        return self._failure

    def secret(self) -> str | None:
        """The secret for this send, or None. None after `close`, which forgets it."""
        return None if self._secret is None else self._secret.reveal()

    def close(self, now: datetime) -> LeaseOutcome:
        """Give the token back and say how that went. A second call answers the first's outcome."""
        if self._ended is not None:
            return self._ended
        reader, self._reader, self._secret = self._reader, None, None
        revoke = getattr(reader, "revoke_self", None)
        if revoke is None:
            self._ended = LeaseOutcome.NONE
            return self._ended
        try:
            revoke()
        except SecretsUnavailableError:
            lapsed = self._expires_at is not None and now >= self._expires_at
            self._ended = LeaseOutcome.EXPIRED if lapsed else LeaseOutcome.NOT_REVOKED
            return self._ended
        self._ended = LeaseOutcome.REVOKED
        return self._ended


class ChannelSecretLeases(Protocol):
    """Whatever lends the worker one channel's secret for one send."""

    def lease(self, record: ChannelRecord, *, now: datetime) -> SendLease: ...


class WorkerChannelSecrets:
    """`ChannelSecretLeases` over the worker's vault, or over no vault at all."""

    def __init__(self, vault: RunTokenVault | None) -> None:
        self._vault = vault

    def __repr__(self) -> str:
        return f"WorkerChannelSecrets(configured={self._vault is not None})"

    __str__ = __repr__

    def lease(self, record: ChannelRecord, *, now: datetime) -> SendLease:
        """A lease on the record's own slot, never another. Never raises: a failure is held."""
        path = record.secret.path
        if not path.startswith(CHANNEL_SECRET_PREFIX) or path == CHANNEL_SECRET_PREFIX:
            return SendLease(failure=NOT_A_CHANNEL_SLOT)
        if self._vault is None:
            return SendLease(failure=NO_VAULT)
        try:
            minted = self._vault.mint_role_token(
                SEND_TOKEN_ROLE, ttl=SEND_LEASE_TTL, meta={"channel": record.channel.value}
            )
        except SecretsUnavailableError:
            return SendLease(failure=NO_VAULT)
        reader = self._vault.holding(minted)
        expires_at = now + timedelta(seconds=minted.lease_seconds)
        verdict = judge_minted(
            renewable=minted.renewable,
            policies=minted.policies,
            lease_seconds=minted.lease_seconds,
            asked=SEND_LEASE_TTL,
            policy=SEND_POLICY,
        )
        if verdict:
            return SendLease(failure=verdict, reader=reader, expires_at=expires_at)
        try:
            fields = reader.read_static_kv(path)
        except VaultRefusedError as refused:
            empty = refused.status == http.client.NOT_FOUND
            return SendLease(
                failure=SLOT_EMPTY if empty else NO_VAULT, reader=reader, expires_at=expires_at
            )
        except SecretsUnavailableError:
            return SendLease(failure=NO_VAULT, reader=reader, expires_at=expires_at)
        value = fields.get(KEY_FIELD)
        if not isinstance(value, str) or not value:
            return SendLease(failure=SLOT_EMPTY, reader=reader, expires_at=expires_at)
        return SendLease(reader=reader, expires_at=expires_at, secret=SealedSecret(value))


def worker_channel_secrets(address: str, token: str) -> WorkerChannelSecrets:
    """The worker's lender, from the two settings the worker's environment carries."""
    if not address or not token:
        return WorkerChannelSecrets(None)
    try:
        return WorkerChannelSecrets(OpenBaoVault(address, token, role=VaultRole.WORKER))
    except ValueError:
        return WorkerChannelSecrets(None)
