"""The Secrets vault screen's read: the seal, every slot, each source's leases, the audit shipping.

`brain.ops.vault_status` decides what the vault is and what each slot holds, `brain.ops.
connector_sync_store` counts how each attempt's lease ended, and `brain.ops.vault_audit_ship`
counts what reached the ledger. This is the one read that puts them on a screen, and it writes
nothing.

**The capability is `admin:credential`, held over everything**, the credentials route's, for its
reason: the slots are the install's keys, and a scoped grant over them is not a grant. It is asked
before the vault, the database or the settings are, so a caller who may not open the screen is
refused in one set of words whatever the install runs.

**Leases are counted only for the sources this reader may be told are connected.** A lease tally is
a fact about a connection, so the Connectors screen's rule decides which connections a reader is
told of (`brain.console.connector_trust.admitted_connections`), and a tally is looked up for those
and no others. No count of what was left out. See
`A_LEASE_COUNT_IS_A_FACT_ABOUT_A_CONNECTION_AND_IS_SHOWN_AS_ONE`.

**Never a value, and never a token.** The slots come from metadata, the leases are counts of four
words, the shipping is counts and an instant; no field on the answer could hold more.

**Which policies the application's own token carries is on the screen**, and whether that is the
application policy alone. See
`brain.ops.vault_status.A_ROLES_POLICY_HOLDS_ONLY_WHILE_ITS_PROCESS_CARRIES_IT_ALONE`.

Task ids: M31.3.2.1, M31.3.2.2, M31.3.2.3, M31.3.2.4, M31.3.2.5, M31.3.2.6, M38.4.1.3
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked
from brain.connector_routes import records_of
from brain.console.connector_trust import admitted_connections
from brain.core.errors import Absent
from brain.credential_routes import may_manage
from brain.ops.connector_lease import RUN_LEASE_TTL
from brain.ops.connector_sync_store import LeaseCounts, StoredLeaseCounts
from brain.ops.credentials import A_KEY_REPLACED_IN_THE_VAULT_IS_USED_WITHOUT_A_RESTART
from brain.ops.vault_audit_ship import StoredVaultAccess, VaultAccessRecords
from brain.ops.vault_status import (
    Seal,
    SlotReport,
    SlotState,
    TokenPolicy,
    VaultStatusReader,
    report,
)
from brain.routing_routes import sessions_of

log = structlog.get_logger()

# ------------------------------------------------------------ written-down reasons

#: Why a lease tally is narrowed like a connection.
A_LEASE_COUNT_IS_A_FACT_ABOUT_A_CONNECTION_AND_IS_SHOWN_AS_ONE: Final = (
    "How many times the worker leased a source's key says the source is connected and is being "
    "read. So a tally is shown for exactly the connections the Connectors screen would tell this "
    "reader of, by the same rule, and for no others, with no count of what was left out."
)

#: Where the screen is served.
VAULT_PATH: Final = "/vault"

#: The window every count on the screen covers.
WINDOW: Final = timedelta(hours=24)

LEASES_SAY: Final = (
    "Each time the worker reads a connected source it mints a run token for that attempt, with a "
    "TTL of {minutes} minutes and no renewal, reads the source's key with it, and revokes it when "
    "the attempt ends. Counted over the last 24 hours: revoked at the end, expired before the end, "
    "and not revoked, which lives on until its TTL and is the one to look at."
)
NO_LEASES_READABLE: Final = "This process has no database, so no lease can be counted."
AUDIT_SAYS: Final = (
    "The worker ships the vault's audit log into the audit ledger every five minutes, one entry "
    "per call the vault answered about a slot, with no value in any of them. Counted over the "
    "last 24 hours; the entries are on the Audit screen under the action vault_access."
)
NO_AUDIT_READABLE: Final = "This process has no database, so nothing shipped can be counted."


# ------------------------------------------------------------------------ the shapes


class VaultSlotView(BaseModel):
    """One slot: its path, what it is for, what it holds, when that was written, and its scopes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    slot: str
    description: str
    state: SlotState
    set_at: datetime | None
    request: tuple[str, ...]
    refuse: tuple[str, ...]


class LeaseView(BaseModel):
    """How one connected source's leases ended over the window."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    connector: str
    issued: int
    revoked: int
    expired: int
    not_revoked: int


class AuditShippingView(BaseModel):
    """What reached the ledger from the vault's log over the window."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: int | None
    refused: int | None
    last_shipped_at: datetime | None
    told: str


class VaultView(BaseModel):
    """The Secrets vault screen."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seal: Seal
    told: str
    slots_unread: str
    token_policy: TokenPolicy
    token_policies: tuple[str, ...]
    token_told: str
    providers: tuple[VaultSlotView, ...]
    connectors: tuple[VaultSlotView, ...]
    leases: tuple[LeaseView, ...] | None
    leases_told: str
    lease_ttl_minutes: int
    rotation: str
    audit: AuditShippingView


def slot_view(one: SlotReport) -> VaultSlotView:
    return VaultSlotView(
        slot=one.slot,
        description=one.description,
        state=one.state,
        set_at=one.set_at,
        request=one.request,
        refuse=one.refuse,
    )


# ------------------------------------------------------------------------- the wiring


def vault_reader_of(request: Request) -> VaultStatusReader | None:
    """What `app.state.vault_reader` holds (a test's reader), or the vault client the lifespan
    attached as `app.state.vault`, or None with no vault. One client for the process, built at
    start, rather than one per request from the settings."""
    found = getattr(request.app.state, "vault_reader", None)
    if found is None:
        found = getattr(request.app.state, "vault", None)
    return found


def lease_counts_of(request: Request) -> LeaseCounts | None:
    found = getattr(request.app.state, "lease_counts", None)
    if isinstance(found, LeaseCounts):
        return found
    sessions = sessions_of(request)
    return None if sessions is None else StoredLeaseCounts(sessions)


def vault_access_of(request: Request) -> VaultAccessRecords | None:
    found = getattr(request.app.state, "vault_access", None)
    if isinstance(found, VaultAccessRecords):
        return found
    sessions = sessions_of(request)
    return None if sessions is None else StoredVaultAccess(sessions)


router = APIRouter(prefix=API_PREFIX, tags=["vault"])


@router.get(VAULT_PATH, response_model=VaultView, responses=COMMON_RESPONSES)
async def vault(request: Request, asked: Asked) -> VaultView:
    """The seal, every slot, each admitted source's leases and the audit log's shipping."""
    if not may_manage(asked.reach, asked.now):
        log.info("vault screen not answerable", principal=asked.caller.principal.id)
        raise Absent("the secrets vault screen is not answerable for this caller")
    found = await asyncio.to_thread(report, vault_reader_of(request))
    since = asked.now - WINDOW

    counts = lease_counts_of(request)
    records = records_of(request)
    leases: tuple[LeaseView, ...] | None = None
    if counts is not None and records is not None:
        shown = {
            one.connector
            for one in admitted_connections(await records.connected(), asked.reach, asked.now)
        }
        tallies = await counts.tallies(since) if shown else {}
        leases = tuple(
            LeaseView(
                connector=name,
                issued=tallies[name].issued,
                revoked=tallies[name].revoked,
                expired=tallies[name].expired,
                not_revoked=tallies[name].not_revoked,
            )
            for name in sorted(shown)
            if name in tallies
        )

    shipped = vault_access_of(request)
    if shipped is None:
        audit = AuditShippingView(
            entries=None, refused=None, last_shipped_at=None, told=NO_AUDIT_READABLE
        )
    else:
        since_then = await shipped.since(since)
        audit = AuditShippingView(
            entries=since_then.entries,
            refused=since_then.refused,
            last_shipped_at=since_then.last_shipped_at,
            told=AUDIT_SAYS,
        )

    minutes = int(RUN_LEASE_TTL.total_seconds() // 60)
    return VaultView(
        seal=found.seal,
        told=found.told,
        slots_unread=found.slots_unread,
        token_policy=found.token.state,
        token_policies=found.token.policies,
        token_told=found.token.told,
        providers=tuple(slot_view(one) for one in found.providers),
        connectors=tuple(slot_view(one) for one in found.connectors),
        leases=leases,
        leases_told=LEASES_SAY.format(minutes=minutes)
        if leases is not None
        else NO_LEASES_READABLE,
        lease_ttl_minutes=minutes,
        rotation=A_KEY_REPLACED_IN_THE_VAULT_IS_USED_WITHOUT_A_RESTART,
        audit=audit,
    )
