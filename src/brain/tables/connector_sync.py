"""`ops.connector_sync`: one row for every time the worker tried to read a connected source.

`brain.ops.connector_sync` decides what a run is owed and what its outcome means, and
`brain.ops.connector_sync_run` performs it. This is where the answer survives: when a source was
last read to the end, what the last attempt found, how many attempts in a row have failed, and
when the next one may be made. `migrations/versions/0068_connector_sync.py` holds the policies and
the grants.

**One row per attempt, appended when the attempt ends, and never edited.** `ops.control_run` gives
the reason at length: a last-sync column updated in place says a source was tried an hour ago
whether or not it was read, so a source that has failed every hour for a week shows a recent time
on the Connectors screen. The outcome is on the row, and the row stays. There is no `started_at`
without a `finished_at`, unlike a control run, because the worker's own run of the control is
already recorded that way in `ops.control_run`: a sync the process died inside is a control run
that never finished, and a second half-written row here would be a second record of one event.

**It names the connection, not the source.** A source disconnected and connected
again is a new `ops.connector_connection` row with a new key, so the failures counted against the
old key must not follow the new one into a backoff it did nothing to earn. Keyed by the name, a
source whose expired key was replaced would wait out the old key's day of retries before anybody
saw the new one work. The id is a value and not a foreign key, for the rule
`tests/unit/test_tables.py::test_no_grant_table_points_at_a_connector` holds over every table: a
connector table is not something another table's rows hang from, and a connection is never removed
in any case, so there is nothing for the key to protect.

**A test of the connection is a row here too** (`0142`). A person pressing Test connection asks the
worker for one call, and its row says `probed`, carries the health that call found and copies the
schedule's figures from the attempt before it, so the screen's newest attempt is the test and the
next scheduled read is exactly as late as it was. See
`brain.ops.connector_sync.A_TEST_LEAVES_THE_SCHEDULE_AS_IT_FOUND_IT`.

**What a row may say is closed.** `outcome` is `synced`, `quota`, `failed` or `probed`, `health` is
the connector health vocabulary (`brain.connectors.contract.HealthState`) less the one state a run
cannot produce, and `detail` is one of the constant sentences `brain.ops.connector_sync` writes.
Nothing from a response body, a setting or a key can reach this table, because nothing that builds
a row reads one: see `brain.ops.connector_sync.A_RUN_RECORD_CARRIES_NO_VALUE_FROM_THE_SOURCE`.

**Where a read stands is kept on the attempt that left it there** (`0178`). The instant the last
complete read began, and the page each entity would be read from next when a read stopped
part-way, so the worker asks a source only for what changed since it last read everything to the
end (M11.4.6) and a read cut short carries on where it stopped (M11.4.8). A page is named by the
arguments its request carries, which are the worker's own (a page number, a size, the instant it
asks for changes since) or, for a source that pages by token, the token the source handed out: a
pointer to a position in a listing, never a value a record holds. It is read by the worker and by
nothing on the Connectors screen.

**No count of what was withheld, and no count per entity.** `records` and `documents` are what the
run wrote, which is a count of what this install now holds a copy of and never of what a reader
may not see, the argument `brain.console.connector_trust.
A_COUNT_OF_WHAT_IS_COPIED_IS_NOT_A_COUNT_OF_WHAT_IS_HIDDEN` makes about projected fields.

Task ids: M42.6.5, M27.15.8, M11.4.6, M11.4.8
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.ops.credentials import CONNECTOR_NAME_PATTERN
from brain.tables.connector_connection import CONNECTOR_CHARS
from brain.tables.identity import one_of

#: What an attempt ended as. See `brain.ops.connector_sync.SyncOutcome`, which these mirror and a
#: test holds equal.
OUTCOMES: Final[tuple[str, ...]] = ("failed", "probed", "quota", "synced")

#: What the source was judged to be after the attempt. `unconfigured` is absent on purpose: it is
#: the state of a source nothing has tried, and a row here is a try.
HEALTH_STATES: Final[tuple[str, ...]] = ("degraded", "down", "ok")

#: How the attempt's vault lease ended. See `brain.ops.connector_lease.LeaseOutcome`, which these
#: mirror and a test holds equal. Added by `0093`.
LEASE_OUTCOMES: Final[tuple[str, ...]] = ("expired", "none", "not_revoked", "revoked")

#: A sentence for whoever reads the Connectors screen, and never a payload.
DETAIL_CHARS: Final = 500


class ConnectorSyncRow(Base):
    """`ops.connector_sync`. One attempt to read one connected source, kept (M42.6.5)."""

    __tablename__ = "connector_sync"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: The connection this attempt read with. See the module docstring for why not the name.
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    #: The source's name, carried so the screen's read is one index and no join to a settings row.
    connector: Mapped[str] = mapped_column(String(CONNECTOR_CHARS), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: One of `OUTCOMES`.
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    #: One of `HEALTH_STATES`.
    health: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Projected records written by this attempt. `documents` counted rows handed to the corpus
    #: until 2026-09-28, when that leg was removed; it is written as zero since.
    records: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    documents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    #: How many attempts in a row have failed, this one included. Zero after a read to the end.
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    #: The earliest instant the next attempt may be made.
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: One of `brain.ops.connector_sync`'s sentences.
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    #: One of `LEASE_OUTCOMES`. `none` for an attempt that held no lease, and all before `0093`.
    lease: Mapped[str] = mapped_column(String(16), nullable=False, server_default="none")
    #: Where reading the source stood when this attempt ended: the instant the last complete read
    #: began, which the next read asks for changes since, and the page each entity would be read
    #: from next when a read stopped part-way. `brain.ops.connector_sync.ReadState` writes and
    #: reads it. Null on a test of the connection and on every row before `0178`, and the worker
    #: reads the newest row that holds one. See the module docstring on what it may hold.
    #: `none_as_null`, so a state of None is SQL's null and not JSON's `null`, which `IS NOT NULL`
    #: admits: without it a test of the connection would be the newest state, and the next read
    #: would start again from the beginning.
    read_state: Mapped[Any] = mapped_column(JSONB(none_as_null=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"connector ~ '{CONNECTOR_NAME_PATTERN}'", name="connector_shape"),
        CheckConstraint(one_of("outcome", OUTCOMES), name="outcome"),
        CheckConstraint(one_of("health", HEALTH_STATES), name="health"),
        CheckConstraint(one_of("lease", LEASE_OUTCOMES), name="lease"),
        CheckConstraint(
            "records >= 0 AND documents >= 0 AND consecutive_failures >= 0",
            name="counts_are_not_negative",
        ),
        # A read to the end is the one outcome that clears the count, and a failure is the one
        # that cannot leave it at zero. A quota refusal and a test carry the count over unchanged.
        CheckConstraint(
            "(outcome <> 'synced' OR consecutive_failures = 0) "
            "AND (outcome <> 'failed' OR consecutive_failures > 0)",
            name="failures_follow_the_outcome",
        ),
        CheckConstraint("finished_at >= started_at", name="finished_after_it_started"),
        CheckConstraint("next_attempt_at >= finished_at", name="next_attempt_is_after_this_one"),
        CheckConstraint(
            f"length(btrim(detail)) > 0 AND length(detail) <= {DETAIL_CHARS}",
            name="detail_is_a_sentence",
        ),
        Index("ix_connector_sync_connection_finished", "connection_id", "finished_at"),
        {"schema": "ops"},
    )
