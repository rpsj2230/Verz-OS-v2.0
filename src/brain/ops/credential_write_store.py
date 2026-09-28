"""The record of a credential write: one row in `ops.credential_write`, in a transaction of its own.

`brain.ops.credentials` decides when a write is recorded and argues the order, and
`migrations/versions/0054_credential_and_retention_audit.py` argues the table and the trigger.
This module holds the SQL between them and decides nothing, for the split CLAUDE.md names:
nothing that decides policy owns a client.

**One transaction, three statements, and the ledger entry is the trigger's.** The request's trace
and the writer's reach are set as transaction-local settings first, because `0054`'s trigger reads
them there as every other trigger in this schema does, and then the row is inserted. The trigger
appends the `credential` entry inside the same transaction, so the row and the entry commit
together or not at all: a row with no entry would be a write the ledger never heard of, and the
table exists only to be the thing the entry is appended from.

**The transaction is short and holds nothing but itself.** It is opened after the vault has
answered and it makes no call outward, so the advisory lock the trigger takes to append is held
for the length of one insert and never across a network call. See
`brain.ops.credentials.THE_KEY_IS_KEPT_BEFORE_IT_IS_RECORDED_AND_A_LOST_RECORD_IS_LOUD`.

**Nothing here takes a value.** `record`'s parameters are the protocol's, and the protocol has no
parameter a value could arrive through; the statement is built from the slot and the actor alone,
and `test_credential_writes` compiles it and reads the columns it names.

Rejected: attributing the write through the `brain.actor_id` setting, as `0003`'s trigger does for a
revocation. The actor is on the row, which is better than a setting, because a setting is only as
right as the code that remembered to set it and a column is refused by its constraint when blank.

**The Credentials screen reads two things here, and neither is a value.** A slot's history is the
ledger's `credential` entries under its subject with each actor's display name, and when a slot's
value was last used is the latest instant a table that records a use holds for it: a provider's
health rings, a source's attempts that borrowed its key, a channel's deliveries. The object store
and the relay record no use, so nothing is read for them and the screen says so.

Task ids: M27.8.7, M27.11.10
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import Insert, TextClause, insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.tables.audit import ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.credential import CredentialWriteRow


def _set_config(name: str, value: str) -> Any:
    # Transaction-local, as `brain.gate.review_store` sets the same two for its trigger.
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


def written(slot: str, written_by: str) -> Insert:
    """The row a kept credential leaves: the slot and who wrote it. The time is the database's."""
    return insert(CredentialWriteRow).values(slot=slot, written_by=written_by)


class StoredCredentialWrites:
    """`brain.ops.credentials.CredentialWrites` over this install's database."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(self, *, slot: str, written_by: str, trace_id: str, ent_hash: str) -> None:
        """Insert the row, attributed to the request, in one short transaction of its own."""
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            await session.execute(written(slot, written_by))


def credential_writes_for(
    sessions: async_sessionmaker[AsyncSession] | None,
) -> StoredCredentialWrites | None:
    """Where this process records a kept credential: its database, or nowhere without one.

    A function the lifespan calls rather than a line in it, so which store a process with a
    database attaches is a claim a test can hold. Nowhere is the honest answer without a database,
    for the reason `brain.app.request_recorders_for` gives: a record kept in memory is a record
    that vanishes on restart and that no reader can reach.
    """
    if sessions is None:
        return None
    return StoredCredentialWrites(sessions)


# ------------------------------------------------------------------ the Credentials screen's reads

#: The most changes one slot's history is read from, newest first. A resource bound.
MAX_CHANGES: Final = 200

#: The ledger's word for a credential write, which `0054`'s trigger appends.
CREDENTIAL_ACTION: Final = "credential"


@dataclass(frozen=True)
class Change:
    """One credential write the ledger holds: when, the actor's id and their name where known."""

    at: datetime
    actor_id: str
    actor_name: str | None


def changes_of(subject: str, *, limit: int = MAX_CHANGES) -> TextClause:
    """The credential entries under one subject, newest first, with each actor's display name."""
    return text(
        "SELECT e.at, e.actor_id, p.display_name FROM obs.audit_entry AS e "
        "LEFT JOIN auth.principal AS p ON p.id = e.actor_id "
        "WHERE e.subject = :subject AND e.action = :action ORDER BY e.seq DESC LIMIT :limit"
    ).bindparams(subject=subject, action=CREDENTIAL_ACTION, limit=limit)


#: When each kind of slot's value was last used, where anything records it. Keyed by the kind's
#: value so this module needs nothing from the catalogue that decides which kind a slot is.
LAST_USED: Final[dict[str, str]] = {
    # A live call to the provider, recorded on its health rings.
    "provider": "SELECT max(last_live_at) FROM ops.provider_health WHERE provider = :name",
    # An attempt by the worker that borrowed the source's key.
    "connector": (
        "SELECT max(started_at) FROM ops.connector_sync WHERE connector = :name AND lease <> 'none'"
    ),
    # A delivery the secret verified or signed.
    "channel": (
        "SELECT max(recorded_at) FROM ops.channel_delivery WHERE channel = :name "
        "AND outcome IN ('accepted', 'redelivered', 'sent')"
    ),
}


class StoredCredentialHistory:
    """The Credentials screen's two reads over this install's database. Judges nothing.

    The route decides whose figures a reader may be shown; this reads what it is asked for.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def changes(self, subject: str) -> tuple[Change, ...]:
        async with self._sessions() as session, session.begin():
            rows = (await session.execute(changes_of(subject))).all()
        return tuple(
            Change(at=row[0], actor_id=str(row[1]), actor_name=row[2] or None) for row in rows
        )

    async def last_used(self, kind: str, name: str) -> datetime | None:
        statement = LAST_USED.get(kind)
        if statement is None or not name:
            return None
        async with self._sessions() as session, session.begin():
            found = (await session.execute(text(statement), {"name": name})).scalar()
        return found if isinstance(found, datetime) else None
