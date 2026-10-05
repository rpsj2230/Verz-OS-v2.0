"""A send from the worker borrows its channel's secret through a token minted for that send, reads
the record's own slot and nothing else, and gives the token back.

Task ids: M38.3.3.4
"""

from __future__ import annotations

import http.client
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from brain.gate.context import Channel
from brain.ops.channel_lease import (
    NO_VAULT,
    NOT_A_CHANNEL_SLOT,
    SEND_LEASE_TTL,
    SEND_POLICY,
    SEND_TOKEN_ROLE,
    SLOT_EMPTY,
    WorkerChannelSecrets,
)
from brain.ops.channel_store import ChannelRecord
from brain.ops.connector_lease import LeaseOutcome
from brain.ops.leases import SealedSecret
from brain.ops.openbao import RoleToken, VaultRefusedError
from brain.ops.secrets import SecretRef, SecretsUnavailableError, VaultRole

NOW = datetime(2999, 1, 1, tzinfo=UTC)


def a_record(path: str = "providers/channel_lark") -> ChannelRecord:
    return ChannelRecord(
        channel=Channel.LARK,
        enabled=True,
        tenant={},
        secret=SecretRef(path=path, role=VaultRole.APPLICATION),
        updated_by="u_admin",
        updated_at=NOW,
    )


class Reader:
    def __init__(self, fields: Mapping[str, Any] | None, *, refuse: int | None = None) -> None:
        self.fields = fields
        self.refuse = refuse
        self.read: list[str] = []
        self.revoked = 0

    def read_static_kv(self, path: str) -> dict[str, Any]:
        self.read.append(path)
        if self.refuse is not None:
            raise VaultRefusedError("refused", status=self.refuse)
        return dict(self.fields or {})

    def revoke_self(self) -> None:
        self.revoked += 1


class Vault:
    def __init__(self, reader: Reader, *, policies: tuple[str, ...] = (SEND_POLICY,)) -> None:
        self.reader = reader
        self.policies = policies
        self.minted: list[tuple[str, timedelta, Mapping[str, str]]] = []

    def mint_role_token(self, role: str, *, ttl: timedelta, meta: Mapping[str, str]) -> RoleToken:
        self.minted.append((role, ttl, meta))
        return RoleToken(
            token=SealedSecret("child"),
            accessor="acc",
            lease_seconds=int(ttl.total_seconds()),
            renewable=False,
            policies=self.policies,
        )

    def holding(self, token: RoleToken) -> Reader:
        return self.reader


def test_a_send_mints_a_token_reads_its_own_channels_slot_and_gives_the_token_back() -> None:
    """**The leaf's lease.** One mint against the send role for the send's TTL, one read of the
    record's slot, the secret for the send, and a revocation that forgets it. Delete this and the
    worker could read a channel secret some other way, or keep the token."""
    reader = Reader({"api_key": "the-secret"})
    vault = Vault(reader)

    lease = WorkerChannelSecrets(vault).lease(a_record(), now=NOW)

    assert vault.minted == [(SEND_TOKEN_ROLE, SEND_LEASE_TTL, {"channel": "lark"})]
    assert reader.read == ["providers/channel_lark"]
    assert lease.secret() == "the-secret" and lease.failure == ""
    assert "the-secret" not in repr(lease)
    assert lease.close(NOW) is LeaseOutcome.REVOKED and reader.revoked == 1
    assert lease.secret() is None
    assert lease.close(NOW) is LeaseOutcome.REVOKED and reader.revoked == 1


def test_a_token_the_vault_widened_is_given_back_unread() -> None:
    """Delete this and a role configured with another policy hands a send the worker's reach."""
    reader = Reader({"api_key": "the-secret"})
    lease = WorkerChannelSecrets(Vault(reader, policies=(SEND_POLICY, "worker"))).lease(
        a_record(), now=NOW
    )

    assert lease.secret() is None and "policies other than" in lease.failure
    assert reader.read == []
    assert lease.close(NOW) is LeaseOutcome.REVOKED


def test_a_record_that_does_not_name_a_channel_slot_is_refused_before_the_vault_is_asked() -> None:
    """Delete this and a record pointed at a model key's slot would have the send token read it."""
    reader = Reader({"api_key": "x"})
    vault = Vault(reader)
    lease = WorkerChannelSecrets(vault).lease(a_record("providers/anthropic"), now=NOW)

    assert lease.failure == NOT_A_CHANNEL_SLOT and vault.minted == []
    assert lease.close(NOW) is LeaseOutcome.NONE


def test_an_empty_slot_a_refused_read_and_no_vault_are_each_said_and_nothing_is_kept() -> None:
    """Delete this and an empty slot and a vault that refused read the same, and an operator is
    sent to the vault for a secret nobody saved."""
    empty = WorkerChannelSecrets(Vault(Reader({}))).lease(a_record(), now=NOW)
    missing = WorkerChannelSecrets(Vault(Reader(None, refuse=http.client.NOT_FOUND))).lease(
        a_record(), now=NOW
    )
    refused = WorkerChannelSecrets(Vault(Reader(None, refuse=403))).lease(a_record(), now=NOW)

    assert (empty.failure, missing.failure, refused.failure) == (SLOT_EMPTY, SLOT_EMPTY, NO_VAULT)
    assert WorkerChannelSecrets(None).lease(a_record(), now=NOW).failure == NO_VAULT
    assert all(one.close(NOW) is LeaseOutcome.REVOKED for one in (empty, missing, refused))


def test_a_revocation_the_vault_did_not_confirm_is_told_apart_from_one_that_lapsed() -> None:
    """Delete this and a token still live after a failed revocation reads as given back."""

    class Stubborn(Reader):
        def revoke_self(self) -> None:
            raise SecretsUnavailableError("no")

    live = WorkerChannelSecrets(Vault(Stubborn({"api_key": "s"}))).lease(a_record(), now=NOW)
    lapsed = WorkerChannelSecrets(Vault(Stubborn({"api_key": "s"}))).lease(a_record(), now=NOW)

    assert live.close(NOW) is LeaseOutcome.NOT_REVOKED
    assert lapsed.close(NOW + SEND_LEASE_TTL) is LeaseOutcome.EXPIRED
