"""`ops.model_server_peak`: what the model server held at its peak, batch by batch, in a ring.

The model server is sized from judgements (`brain.ops.model_server.SIZING`) and says so; this is
where the judgements stop. The server measures its own peak memory for every batch it serves and
puts it in the answer, and `brain.ops.model_server_store` writes it here, so the limit an
administrator is shown beside the one that was guessed is the limit the install's own work asked
for. **A figure here is a measurement of something that ran, and the only figures in this product
about the model server that are.**

**A ring and not a log, and the reason is a grant.** One row per part per slot, the newest batch
overwriting the oldest of its part's fifty, so the table holds at most fifty rows for each of five
parts however long the server runs. A log of every batch would need a retention sweep, and a sweep
needs the DELETE grant, which `tests/unit/test_directory_role_grant.py` holds to a short argued
list and which a table of resource figures has no business joining. A ring needs UPDATE, which is
a smaller thing to grant, and fifty batches of each part is more than a person tuning a limit reads.

**No row names a person, a document, a trace or a passage.** A part, a model name, a count of items,
a number of bytes, a duration and three memory figures. Nothing a batch carried reaches this table,
which is why it is in `ops` and not `obs`: it is a fact about a machine and not about a request.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.ops.model_server import Part
from brain.tables.identity import one_of

#: The widths. The part is one of five short words; the model is a name and a quantisation.
PART_CHARS: Final = 16
MODEL_CHARS: Final = 80

#: How many batches of each part are kept. See the module docstring.
RING_SLOTS: Final = 50


class ModelServerPeakRow(Base):
    """One batch's peak, in the slot its number lands in. See the module docstring."""

    __tablename__ = "model_server_peak"
    __table_args__ = (
        PrimaryKeyConstraint("part", "slot"),
        CheckConstraint(one_of("part", [one.value for one in Part]), name="part"),
        CheckConstraint(f"slot >= 0 AND slot < {RING_SLOTS}", name="slot_in_the_ring"),
        CheckConstraint("batch_no >= 1", name="batch_is_counted_from_one"),
        CheckConstraint("length(btrim(model)) > 0", name="model_present"),
        CheckConstraint("items >= 0", name="items_not_negative"),
        CheckConstraint("request_bytes >= 0", name="request_not_negative"),
        CheckConstraint("duration_ms >= 0", name="duration_not_negative"),
        CheckConstraint("anon_peak_mib >= 0", name="anonymous_not_negative"),
        CheckConstraint("cache_peak_mib >= 0", name="cache_not_negative"),
        CheckConstraint(
            "cgroup_limit_mib IS NULL OR cgroup_limit_mib > 0", name="limit_positive_when_known"
        ),
        {"schema": "ops"},
    )

    part: Mapped[str] = mapped_column(String(PART_CHARS), nullable=False)
    slot: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    batch_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model: Mapped[str] = mapped_column(String(MODEL_CHARS), nullable=False)
    items: Mapped[int] = mapped_column(Integer, nullable=False)
    request_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    #: What the container held that nothing could take back, at the batch's high-water mark, in MiB.
    anon_peak_mib: Mapped[int] = mapped_column(Integer, nullable=False)
    #: What the kernel had charged to the container as cache at the same moment, in MiB.
    cache_peak_mib: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The limit the container was running under, when the kernel said, in MiB.
    cgroup_limit_mib: Mapped[int | None] = mapped_column(Integer, nullable=True)
