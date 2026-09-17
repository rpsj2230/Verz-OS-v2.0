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

**What a row may say is closed.** `outcome` is `synced`, `quota` or `failed`, `health` is the
connector health vocabulary (`brain.connectors.contract.HealthState`) less the one state a run
cannot produce, and `detail` is one of the constant sentences `brain.ops.connector_sync` writes.
Nothing from a response body, a setting or a key can reach this table, because nothing that builds
a row reads one: see `brain.ops.connector_sync.A_RUN_RECORD_CARRIES_NO_VALUE_FROM_THE_SOURCE`.

**No count of what was withheld, and no count per entity.** `records` and `documents` are what the
run wrote, which is a count of what this install now holds a copy of and never of what a reader
may not see, the argument `brain.console.connector_trust.
A_COUNT_OF_WHAT_IS_COPIED_IS_NOT_A_COUNT_OF_WHAT_IS_HIDDEN` makes about projected fields.

Task ids: M42.6.5
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

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
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.ops.credentials import CONNECTOR_NAME_PATTERN
from brain.tables.connector_connection import CONNECTOR_CHARS
from brain.tables.identity import one_of

#: What an attempt ended as. See `brain.ops.connector_sync.SyncOutcome`, which these mirror and a
#: test holds equal.
OUTCOMES: Final[tuple[str, ...]] = ("failed", "quota", "synced")

#: What the source was judged to be after the attempt. `unconfigured` is absent on purpose: it is
#: the state of a source nothing has tried, and a row here is a try.
HEALTH_STATES: Final[tuple[str, ...]] = ("degraded", "down", "ok")

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
    #: Projected records written, and documents handed to the corpus, by this attempt.
    records: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    documents: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    #: How many attempts in a row have failed, this one included. Zero after a read to the end.
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    #: The earliest instant the next attempt may be made.
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: One of `brain.ops.connector_sync`'s sentences.
    detail: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(f"connector ~ '{CONNECTOR_NAME_PATTERN}'", name="connector_shape"),
        CheckConstraint(one_of("outcome", OUTCOMES), name="outcome"),
        CheckConstraint(one_of("health", HEALTH_STATES), name="health"),
        CheckConstraint(
            "records >= 0 AND documents >= 0 AND consecutive_failures >= 0",
            name="counts_are_not_negative",
        ),
        # A read to the end is the one outcome that clears the count, and a failure is the one
        # that cannot leave it at zero. A quota refusal carries the count over unchanged.
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
