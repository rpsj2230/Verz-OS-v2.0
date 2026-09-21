"""Shipping the vault's audit log into the ledger, from the worker, on a schedule.

`brain.ops.vault_audit` said, until 2026-09-17, that shipping its entries into `brain.audit.ledger`
was a boundary rather than an omission: the ledger's vocabulary was about principals and grants,
and a vault read is made by a service's token. That left the vault's log as the only record of who
read which key, in a file on the vault's own volume that no screen reads and a `docker compose down
-v` deletes. M31.3.2.6 asks for the log to reach the ledger, so the vocabulary gained a member,
`vault_access`, argued in `brain.audit.ledger.AuditAction`, and this is the carrier.

**The worker reads the log, and nothing else does.** The worker's vault overlay mounts the vault's
log volume read-only at `VAULT_AUDIT_LOG`'s directory, and the file device is enabled with mode
0644 so a process running as another user can read it. The application never mounts it: a process
that could read its own access history could also be asked to explain it away.

**A row per entry, and the ledger entry is the row's trigger's.** Nothing in the application
appends to the ledger, and `0093` keeps that: each shipped entry is a row in `ops.vault_access`, and
its insert trigger appends the entry, filed under `credential:<slot>`, with the operation, the part
of the slot, whether it was refused and the token's HMAC as details.

**Where a run starts is read from what was shipped, not remembered.** A row carries the log file's
identity, a digest of its first line, and the byte offset just past its line, unique together. A run
starts from the furthest offset shipped for the file that is there now, so a worker restarted, a
second worker, or a run that died mid-way all start where the table says, and a repeated entry is
refused by the constraint rather than doubled. A file replaced by a new one, whose first line
differs, starts from its beginning; a file shorter than the offset was truncated and does too.
See `WHERE_A_RUN_STARTS_IS_WHAT_WAS_SHIPPED`.

**A line that is not an entry stops the run there, and the run fails saying so.** Skipping it would
make a corrupt or tampered log read as a quiet one. The run ships what came before it and records
the failure, and every later run stops at the same line, so the Scheduled jobs screen keeps saying
it until somebody looks.

**What this does not see, stated.** Chatter after the last shipped entry is read again by the next
run, because the offset moves only with a shipped row; a token renewing itself twice a day is all it
is. The stdout device's copy of the log is not read: it goes to the container's log, which the
worker cannot reach and should not. Rotating the file is not configured here, and a log that grows
for years is read from where it was left, never whole.

Task ids: M31.3.2.6
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.ops.vault_audit import AuditLogError, VaultAccess, parse_line
from brain.tables.vault_access import ONCE, VaultAccessRow

# ------------------------------------------------------------------ written-down reasons

#: Why a run's starting offset is read out of the table.
WHERE_A_RUN_STARTS_IS_WHAT_WAS_SHIPPED: Final = (
    "A worker restarts, a second worker runs the same schedule, and a run can die between reading "
    "and writing. An offset kept in memory or in a file beside the log is wrong after each of "
    "those, and the ledger would miss entries or record them twice. The furthest offset shipped "
    "for this file is in the table, unique with the file's identity, so every run starts where the "
    "ledger ends and a repeat is refused by the database."
)

#: Where the worker's overlay mounts the vault's log, as `brain.deployment.app_environment`
#: writes it. Restated for the import direction; a test holds the two equal.
VAULT_AUDIT_LOG: Final = "/vault-audit/audit.log"

#: How often the schedule ships. Five minutes: the ledger is minutes behind the vault at worst.
SHIP_EVERY: Final = timedelta(minutes=5)

#: At most this much of the log is read in one run, so a years-old log first mounted is shipped
#: over many runs rather than in one that holds a transaction for an hour.
MAX_BYTES_PER_RUN: Final = 8 * 1024 * 1024

#: How much of the first line identifies a file. A vault's first entry is well under this.
IDENTITY_BYTES: Final = 4096


class VaultAuditShipError(Exception):
    """A run that could not ship what it should have. The schedule records it as failed."""


@dataclass(frozen=True)
class Shipment:
    """What one read of the log found: entries, the offset past each, and where it stopped."""

    entries: tuple[tuple[VaultAccess, int], ...]
    reached: int
    #: The offset of a line that is not an entry, where the read stopped, or None.
    malformed_at: int | None = None
    #: Whether the byte bound stopped the read before the end of the file.
    more: bool = False


def log_identity(path: Path) -> str | None:
    """A digest of the log's first complete line, or None when the file has no complete line yet."""
    try:
        with path.open("rb") as handle:
            head = handle.readline(IDENTITY_BYTES)
    except OSError:
        return None
    if not head.endswith(b"\n"):
        return None
    return hashlib.sha256(head).hexdigest()


def read_since(path: Path, start: int, *, max_bytes: int = MAX_BYTES_PER_RUN) -> Shipment:
    """Every shippable entry after `start`, up to an incomplete line, a malformed one or the bound.

    A file shorter than `start` was truncated, and is read from its beginning. An incomplete last
    line is a line the vault is still writing, and is left for the next run.
    """
    entries: list[tuple[VaultAccess, int]] = []
    with path.open("rb") as handle:
        size = handle.seek(0, 2)
        offset = start if start <= size else 0
        handle.seek(offset)
        read = 0
        while True:
            if read >= max_bytes:
                return Shipment(tuple(entries), offset, more=offset < size)
            line = handle.readline()
            if not line or not line.endswith(b"\n"):
                return Shipment(tuple(entries), offset)
            try:
                entry = parse_line(line.decode("utf-8", errors="replace"))
            except AuditLogError:
                return Shipment(tuple(entries), offset, malformed_at=offset)
            offset += len(line)
            read += len(line)
            if entry is not None:
                entries.append((entry, offset))


# ---------------------------------------------------------------------- the store


def furthest_shipped(identity: str) -> Select[tuple[int]]:
    """The furthest offset shipped for the log file with this identity."""
    return select(func.max(VaultAccessRow.log_offset)).where(
        VaultAccessRow.log_identity == identity
    )


def access_rows(identity: str, entries: Sequence[tuple[VaultAccess, int]]) -> object:
    """One insert for every entry, each written once whatever else shipped it."""
    statement = insert(VaultAccessRow).values(
        [
            {
                "at": entry.at,
                "operation": entry.operation,
                "part": entry.part.value,
                "slot": entry.slot,
                "refused": entry.refused,
                "identity": entry.identity or None,
                "log_identity": identity,
                "log_offset": offset,
            }
            for entry, offset in entries
        ]
    )
    return statement.on_conflict_do_nothing(constraint=ONCE)


@dataclass(frozen=True)
class ShippedSince:
    """What reached the ledger from the vault's log over a window, as counts and one instant."""

    entries: int
    refused: int
    last_shipped_at: datetime | None


@runtime_checkable
class VaultAccessRecords(Protocol):
    """What the Secrets vault screen needs about shipping. `StoredVaultAccess` is one."""

    async def since(self, instant: datetime) -> ShippedSince:
        """Entries shipped since `instant`, how many were refusals, and when the last one landed."""
        ...


def shipped_since(instant: datetime) -> Select[tuple[int, int, datetime]]:
    return select(
        func.count(VaultAccessRow.id),
        func.count(VaultAccessRow.id).filter(VaultAccessRow.refused.is_(True)),
        func.max(VaultAccessRow.shipped_at),
    ).where(VaultAccessRow.shipped_at >= instant)


class StoredVaultAccess:
    """`VaultAccessRecords` over this install's database, and the shipper's writes."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def start_for(self, identity: str) -> int:
        async with self._sessions() as session, session.begin():
            found = (await session.execute(furthest_shipped(identity))).scalar_one_or_none()
        return 0 if found is None else int(found)

    async def ship(self, identity: str, entries: Sequence[tuple[VaultAccess, int]]) -> None:
        if not entries:
            return
        async with self._sessions() as session, session.begin():
            await session.execute(access_rows(identity, entries))  # type: ignore[call-overload]

    async def since(self, instant: datetime) -> ShippedSince:
        async with self._sessions() as session, session.begin():
            count, refused, last = (await session.execute(shipped_since(instant))).one()
        return ShippedSince(entries=int(count), refused=int(refused), last_shipped_at=last)


# ------------------------------------------------------------------------ one run


async def ship_once(store: StoredVaultAccess, path: Path) -> str:
    """Ship everything after the furthest shipped offset, and say what that came to."""
    identity = log_identity(path)
    if identity is None:
        if not path.exists():
            msg = (
                f"no audit log is readable at {path}. The worker's vault overlay mounts the "
                "vault's log volume there, and the file audit device declared in "
                "ops/openbao/compose.yml writes it"
            )
            raise VaultAuditShipError(msg)
        return "the audit log holds no complete entry yet"
    start = await store.start_for(identity)
    try:
        # A call in a lambda rather than the function as a value, so the registry's call index
        # follows the schedule's run down to the parse (`brain.ops.controls.chains_worth_checking`).
        found = await asyncio.to_thread(lambda: read_since(path, start))
    except PermissionError as refused:
        msg = (
            f"the audit log at {path} is not readable by the worker. The file audit device in "
            "ops/openbao/compose.yml declares mode 0644; a log written earlier at 0600 needs "
            "chmod 0644"
        )
        raise VaultAuditShipError(msg) from refused
    await store.ship(identity, found.entries)
    said = f"{len(found.entries)} vault entries shipped to the ledger"
    if found.malformed_at is not None:
        msg = (
            f"{said}, and the audit log has a line that is not an entry at byte "
            f"{found.malformed_at}, so nothing after it is shipped until somebody looks"
        )
        raise VaultAuditShipError(msg)
    return f"{said}, more waiting for the next run" if found.more else said


def run_vault_audit_ship_now(
    database_url: str,
    *,
    vault_address: str,
    log_path: str = VAULT_AUDIT_LOG,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
) -> str:
    """`ship_once` from a thread with no event loop, over the worker's own login, for the schedule.

    An install that names no vault has no log and succeeds saying so. The worker writes as the
    login its URL names, for `brain.ops.connector_sync_store`'s reason.
    """
    if not vault_address:
        return "this worker names no secrets vault, so there is no audit log to ship"
    from brain.session import make_app_engine, make_session_factory

    async def go() -> str:
        engine = make_app_engine(database_url)
        try:
            return await ship_once(StoredVaultAccess(make_session_factory(engine)), Path(log_path))
        finally:
            await engine.dispose()

    return asyncio.run(go(), loop_factory=loop_factory)
