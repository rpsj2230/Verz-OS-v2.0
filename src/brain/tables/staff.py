"""`auth.staff_member` and `auth.staff_sync_run`: the roster the staff sync applied, and each run.

`brain.identity.staff_sync.dry_run` computes what a roster would change against what the system
already holds, and until these tables existed the system held nothing: its `known` argument had no
store, `last_applied` had no store, and so the scheduled sync could not run and the first-run rule
could never be told a second run from a first. `brain.ops.staff_sync_run` is the writer and
`migrations/versions/0096_staff_roster.py` holds the policies and grants.

**The work address is never stored, only its digest.** `address_hash` is
`brain.gate.ingress.identity_hash(Channel.EMAIL, address)`, the digest `auth.principal_identity`
already keeps for an email binding, so the join from a roster entry to a principal is one equality
on two digests and the table is not a company phone book: `brain.tables.identity` refuses to hold a
raw channel identity for that reason and this table keeps the rule. The address is read from the
source on each run and never written. See `brain.identity.staff_roster.THE_ROSTER_KEEPS_A_DIGEST`.

**A leaver is marked, never deleted, and marking revokes nothing.** `left_at` and `left_because`
record that the source said a person left, or a complete roster stopped naming them. The sync is
a second source of facts and entitlements are additive: the offboarding that removes grants is a
person's decision on the console, and the leaver's agents are listed for a new owner from this mark
(M1.8.9). See `brain.identity.staff_roster.A_LEAVER_IS_MARKED_AND_NOTHING_IS_REVOKED`.

**One run row per scheduled attempt that got as far as a chosen source.** `outcome` is closed,
`detail` is one sentence, and the four arrays carry display names and constant sentences, never an
address, a credential or a vendor payload. `last_applied` is read from here, which is what makes
the first run of a source add and never remove.

Task ids: M1.6.1, M1.6.7, M1.6.8, M1.6.12, M1.8.6, M1.8.9
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base, TimestampMixin
from brain.tables.identity import (
    DISPLAY_NAME_CHARS,
    IDENTITY_HASH_CHARS,
    IDENTITY_HASH_PATTERN,
    one_of,
)

#: A source's name as `brain.identity.staff_source.SELECTABLE` spells it.
SOURCE_CHARS: Final = 32
SOURCE_PATTERN: Final = r"^[a-z][a-z0-9_]{0,31}$"

#: The longest department name a roster row keeps, as `auth.principal.primary_department`.
DEPARTMENT_CHARS: Final = 120

#: The longest identifier a source issues that this keeps. Lark's union id, an Entra object id and
#: an LDAP entryUUID are all well under it.
STABLE_ID_CHARS: Final = 200

#: Why somebody was marked as having left. See `brain.identity.staff_roster.LeftBecause`, which a
#: test holds equal.
LEFT_BECAUSE: Final[tuple[str, ...]] = ("absent_from_complete_roster", "source_says_left")

#: What a run came to. See `brain.identity.staff_roster.RunOutcome`, which a test holds equal.
RUN_OUTCOMES: Final[tuple[str, ...]] = (
    "applied",
    "credential_refused",
    "misconfigured",
    "no_credential",
    "not_schedulable",
    "unchanged",
    "unreachable",
)

#: One sentence for whoever reads the Staff sources screen.
DETAIL_CHARS: Final = 500


class StaffMemberRow(TimestampMixin, Base):
    """`auth.staff_member`. One person one source has listed, by the digest of their address."""

    __tablename__ = "staff_member"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    source: Mapped[str] = mapped_column(String(SOURCE_CHARS), nullable=False)
    address_hash: Mapped[str] = mapped_column(String(IDENTITY_HASH_CHARS), nullable=False)
    display_name: Mapped[str] = mapped_column(String(DISPLAY_NAME_CHARS), nullable=False)
    #: Kept only when the source is trusted to assert departments. Null otherwise.
    department: Mapped[str | None] = mapped_column(String(DEPARTMENT_CHARS), nullable=True)
    #: The identifier the source issues for this person, which is what recognises a rename.
    stable_id: Mapped[str | None] = mapped_column(String(STABLE_ID_CHARS), nullable=True)
    first_listed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_listed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    left_because: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        CheckConstraint(f"source ~ '{SOURCE_PATTERN}'", name="source_shape"),
        CheckConstraint(f"address_hash ~ '{IDENTITY_HASH_PATTERN}'", name="address_is_a_digest"),
        CheckConstraint("length(btrim(display_name)) > 0", name="display_name_present"),
        CheckConstraint(
            f"left_because IS NULL OR {one_of('left_because', LEFT_BECAUSE)}", name="left_because"
        ),
        CheckConstraint(
            "(left_at IS NULL) = (left_because IS NULL)", name="left_at_and_left_because_together"
        ),
        CheckConstraint("last_listed_at >= first_listed_at", name="listed_in_order"),
        UniqueConstraint("source", "address_hash"),
        Index("ix_staff_member_left_at", "left_at"),
        {"schema": "auth"},
    )


class StaffSyncRunRow(Base):
    """`auth.staff_sync_run`. One scheduled attempt at the chosen staff source, appended once."""

    __tablename__ = "staff_sync_run"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    source: Mapped[str] = mapped_column(String(SOURCE_CHARS), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    #: Display names of the people this run added, or would have.
    added: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    #: Display names of the people this run marked as having left.
    marked_left: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    #: Display names of the people whose address moved under a stable identifier.
    renamed: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    #: Why removals were held back, and what a person has to look at, in constant sentences.
    withheld: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)

    __table_args__ = (
        CheckConstraint(f"source ~ '{SOURCE_PATTERN}'", name="source_shape"),
        CheckConstraint(one_of("outcome", RUN_OUTCOMES), name="outcome"),
        CheckConstraint("finished_at >= started_at", name="finished_after_it_started"),
        CheckConstraint(
            f"length(btrim(detail)) > 0 AND length(detail) <= {DETAIL_CHARS}",
            name="detail_is_a_sentence",
        ),
        CheckConstraint(
            "outcome IN ('applied', 'unchanged') OR (cardinality(added) = 0 "
            "AND cardinality(marked_left) = 0 AND cardinality(renamed) = 0)",
            name="only_an_applied_run_changes_anybody",
        ),
        Index("ix_staff_sync_run_source_finished", "source", "finished_at"),
        {"schema": "auth"},
    )
