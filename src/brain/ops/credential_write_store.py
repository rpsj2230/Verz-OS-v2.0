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

Task ids: M27.8.7
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Insert, insert, text
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
