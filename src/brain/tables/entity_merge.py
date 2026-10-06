"""`er.merge` and `er.unmerge`: who merged two entities, on what evidence, and what it undid.

Storage for `brain.resolution.merge.MergeAudit`, `PreImage` and `UnmergeAudit`, written by
`brain.resolution.merge_store` and nothing else. Every width and grammar is taken from the domain
or from the ledger rather than retyped, so a change there breaks a test rather than a deploy.

**The pre-image is one jsonb column on the merge row, and its one privacy rule is a constraint.**
A merge moves one pointer (`canonical.A_MERGE_MOVES_ONE_POINTER_AND_NOTHING_ELSE`), so the rows a
pre-image describes all still exist, and what it has to keep is how they stood: which entity each
link, alias and identifier named, and the link's confidence, at the instant of the merge. Three
child tables mirroring `er.link`, `er.alias` and `er.identifier` were the alternative, and they
were rejected for what they would hold: a second copy of the resolution graph whose only reader
is an unmerge, each needing its own policies, grants, erasure decision and model, to answer a
question one row answers. What three tables would have bought is `er.identifier`'s digest
constraint on the copy, and that is kept: `PRE_IMAGE_KEYS_ARE_DIGESTS` refuses a pre-image whose
identifiers carry anything but a sha256 hex digest, by a hand-written INSERT as much as by a bug.

**The evidence is field names and weights, and the column refuses any third key.** `guardrails.
Evidence` has nowhere to put what a field said, and `EVIDENCE_IS_NAMES_AND_WEIGHTS` holds the
stored copy to the same shape, so an auditor reads this row without reading either record.

**Who decided is the transaction's actor, by policy.** The INSERT policies require `decided_by`
and `performed_by` to equal `brain.actor_id`, which is the setting the ledger trigger names its
entry's actor from. So the merge row and the ledger entry cannot name two different people, and a
row written with no attribution at all is refused rather than recorded as unattributed: a merge
is a permission event, and one nobody will own is not one this table holds.

**An unmerge names its merge, and the pair it reverses is held to that merge by the key.** The
foreign key from `(merge_id, survivor_id, restored_id)` onto the merge's own three columns is
what `UnmergeAudit`'s docstring calls one story: an unmerge row cannot describe a different pair
than the merge it reverses. One unmerge per merge, by a unique key, because a merge reversed
twice is a pointer cleared by the second reversal that the first already cleared.

**Ids are 32 lowercase hex characters**, which is a `uuid4().hex`, and the shape is chosen for the
ledger: `brain.audit.ledger.redact_details` keeps a 32-hex digest and redacts anything else that
is not a field name, so a merge id in an entry's details survives to be looked up here.

**SELECT and INSERT, never UPDATE or DELETE.** These are audit rows, and an audit row that can be
edited is an account of events somebody can rewrite.

Task ids: M14.5.1, M14.5.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.db import Base
from brain.resolution.merge import MoneyBearing
from brain.tables.identity import one_of
from brain.tables.resolution import CONFIDENCE_IS_A_SHARE, CREATED_BY_CHARS, ENTITY_ID_CHARS

#: A merge's and an unmerge's id: a `uuid4().hex`. See the module docstring for why this shape.
RECORD_ID_PATTERN: Final = "^[0-9a-f]{32}$"
RECORD_ID_CHARS: Final = 32

#: Who decided: a principal or a job, at the width `er.canonical.created_by` and the ledger's
#: actor column share.
DECIDED_BY_CHARS: Final = CREATED_BY_CHARS

#: A review reference, at the width of an entity id: it names a review row, not a sentence.
REVIEW_REF_CHARS: Final = ENTITY_ID_CHARS

#: Why, in words. Bounded, as every text column here is; the store refuses a longer one first.
REASON_CHARS: Final = 500

#: The longest `MoneyBearing` value with room to spare. `one_of` is what restricts it.
MONEY_CHARS: Final = 32

#: Every identifier the pre-image holds is a sha256 hex digest, as `er.identifier` requires.
PRE_IMAGE_KEYS_ARE_DIGESTS: Final = (
    "jsonb_typeof(pre_image) = 'object' AND NOT jsonb_path_exists(pre_image, "
    "'$.identifiers[*].key_hash ? (!(@ like_regex \"^[0-9a-f]{64}$\"))')"
)

#: The evidence is an array of objects, each holding a field name and a weight and nothing else.
EVIDENCE_IS_NAMES_AND_WEIGHTS: Final = (
    "jsonb_typeof(evidence) = 'array' "
    "AND NOT jsonb_path_exists(evidence, '$[*] ? (@.type() != \"object\")') "
    "AND NOT jsonb_path_exists(evidence, "
    '\'$[*].keyvalue() ? (@.key != "field" && @.key != "weight")\')'
)

#: An automatic merge carries the cascade's confidence and no review; a reviewed one the reverse.
AUTOMATIC_CARRIES_A_CONFIDENCE: Final = "automatic = (confidence IS NOT NULL)"
REVIEWED_CARRIES_A_REFERENCE: Final = "automatic = (review_ref IS NULL)"

#: The setting the ledger trigger reads its actor from, which the INSERT policies compare against.
ACTOR: Final = "current_setting('brain.actor_id', true)"


def _present(column: str) -> str:
    return f"length(btrim({column})) > 0"


class EntityMergeRow(Base):
    """`er.merge` (M14.5.1, M14.5.4). One merge: the pair, who, when, on what, and the pre-image."""

    __tablename__ = "merge"

    merge_id: Mapped[str] = mapped_column(String(RECORD_ID_CHARS), primary_key=True)
    survivor_id: Mapped[str] = mapped_column(String(ENTITY_ID_CHARS), nullable=False)
    merged_id: Mapped[str] = mapped_column(String(ENTITY_ID_CHARS), nullable=False)

    #: The instant `er.canonical.merged_at` was set to, which is how the ledger trigger finds
    #: this row for the entry it appends.
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(DECIDED_BY_CHARS), nullable=False)

    #: Whether nobody looked. True only through `merge.AutomaticMerge`, which the store refuses
    #: while the unattended merge switch is off.
    automatic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_ref: Mapped[str | None] = mapped_column(String(REVIEW_REF_CHARS), nullable=True)

    #: `[{"field": ..., "weight": ...}]`. Names and weights; never what a field said.
    evidence: Mapped[Any] = mapped_column(JSONB, nullable=False)

    #: What was asked about each side's financial records, as the authority carried it.
    money_left: Mapped[str] = mapped_column(String(MONEY_CHARS), nullable=False)
    money_right: Mapped[str] = mapped_column(String(MONEY_CHARS), nullable=False)

    reason: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)

    #: `merge.PreImage` as `brain.resolution.merge_store.pre_image_document` writes it.
    pre_image: Mapped[Any] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(["survivor_id"], ["er.canonical.entity_id"]),
        ForeignKeyConstraint(["merged_id"], ["er.canonical.entity_id"]),
        # The target of `er.unmerge`'s key, which holds an unmerge to the pair it reverses.
        UniqueConstraint("merge_id", "survivor_id", "merged_id"),
        CheckConstraint(f"merge_id ~ '{RECORD_ID_PATTERN}'", name="merge_id_shape"),
        CheckConstraint("survivor_id <> merged_id", name="not_merged_into_itself"),
        CheckConstraint(f"decided_by ~ '{IDENTIFIER}'", name="decided_by_is_an_identifier"),
        CheckConstraint(
            f"confidence IS NULL OR ({CONFIDENCE_IS_A_SHARE})", name="confidence_is_a_share"
        ),
        CheckConstraint(AUTOMATIC_CARRIES_A_CONFIDENCE, name="automatic_carries_a_confidence"),
        CheckConstraint(REVIEWED_CARRIES_A_REFERENCE, name="reviewed_carries_a_reference"),
        CheckConstraint(
            f"review_ref IS NULL OR {_present('review_ref')}", name="review_ref_present"
        ),
        CheckConstraint(EVIDENCE_IS_NAMES_AND_WEIGHTS, name="evidence_is_names_and_weights"),
        CheckConstraint(one_of("money_left", MoneyBearing), name="money_left_known"),
        CheckConstraint(one_of("money_right", MoneyBearing), name="money_right_known"),
        CheckConstraint(PRE_IMAGE_KEYS_ARE_DIGESTS, name="pre_image_keys_are_digests"),
        # "Which merges has this entity been through" is the unmerge question and the trigger's.
        Index("ix_merge_merged_id", "merged_id"),
        {"schema": "er"},
    )


class EntityUnmergeRow(Base):
    """`er.unmerge` (M14.5.3, M14.5.4). One merge reversed: by whom, when, why."""

    __tablename__ = "unmerge"

    unmerge_id: Mapped[str] = mapped_column(String(RECORD_ID_CHARS), primary_key=True)
    merge_id: Mapped[str] = mapped_column(String(RECORD_ID_CHARS), nullable=False)
    survivor_id: Mapped[str] = mapped_column(String(ENTITY_ID_CHARS), nullable=False)
    restored_id: Mapped[str] = mapped_column(String(ENTITY_ID_CHARS), nullable=False)
    reversed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    performed_by: Mapped[str] = mapped_column(String(DECIDED_BY_CHARS), nullable=False)
    reason: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["merge_id", "survivor_id", "restored_id"],
            ["er.merge.merge_id", "er.merge.survivor_id", "er.merge.merged_id"],
        ),
        UniqueConstraint("merge_id"),
        CheckConstraint(f"unmerge_id ~ '{RECORD_ID_PATTERN}'", name="unmerge_id_shape"),
        CheckConstraint(f"performed_by ~ '{IDENTIFIER}'", name="performed_by_is_an_identifier"),
        CheckConstraint(_present("reason"), name="reason_present"),
        {"schema": "er"},
    )
