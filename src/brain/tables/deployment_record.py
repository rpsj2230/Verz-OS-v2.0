"""`ops.deployment_record`: the deployment history, one link of a hash chain per deploy.

`brain.ops.deployments` holds the chain and `brain.ops.deployment_store` writes it; this is where
it survives, so the Version and updates screen can show what went out, when, which tasks it
carried and how it ended. `migrations/versions/0091_deployment_record.py` holds the policy and
the grant.

**In `ops` and not beside `obs.audit_entry`, and that placement is the requirement.** The
permission ledger answers who could see what, its vocabulary is closed and the compliance export
is built from it; a deploy has no principal, no entitlement and no scope. `brain.ops.deployments`
argues the separation at length. A table of its own in another schema is the construction that
keeps it out of the ledger's triggers, the ledger's view and the export by default, rather than by
a filter somebody has to remember.

**Written by the deploy, as the database owner, and only read by the application.** The deploy
script runs `python -m brain.ops.deployment_store` inside the container once it answers ready,
on the login rather than on `brain_app`, so no request the console serves can add or change a
deploy. The application role holds SELECT and nothing else.

**The digests are stored rather than recomputed, and the fingerprint is unique.** Storing
`entry_hash` is what lets an edited row disagree with itself (the audit ledger's argument), and a
unique fingerprint makes a second reconcile of the same file a no-op in the database as well as
in Python, which matters because the deploy reconciles the whole file every time.

Task ids: M38.1.3.5
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.ops.deployments import OUTCOMES
from brain.tables.identity import one_of

#: A sha256 in hex. The chain's digests and the fingerprint are all this shape.
DIGEST_PATTERN: Final = "^[0-9a-f]{64}$"
#: An image reference or an image id; a registry path with a digest fits well inside this.
IMAGE_CHARS: Final = 255
#: A full or short git SHA, or `unknown` when the container could not say.
COMMIT_CHARS: Final = 64
OUTCOME_CHARS: Final = 24


class DeploymentRecordRow(Base):
    """`ops.deployment_record`. One deploy, in its place in the chain (M38.1.3.5)."""

    __tablename__ = "deployment_record"

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: One of `brain.ops.deployments.OUTCOMES`.
    outcome: Mapped[str] = mapped_column(String(OUTCOME_CHARS), nullable=False)
    commit: Mapped[str] = mapped_column(String(COMMIT_CHARS), nullable=False)
    image: Mapped[str] = mapped_column(String(IMAGE_CHARS), nullable=False)
    previous: Mapped[str] = mapped_column(String(IMAGE_CHARS), nullable=False)
    #: Sorted, as `Deployment.task_ids` is, because the chain digests them in that order.
    task_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        CheckConstraint("seq >= 0", name="seq_is_not_negative"),
        CheckConstraint(one_of("outcome", sorted(OUTCOMES)), name="outcome"),
        CheckConstraint(f"prev_hash ~ '{DIGEST_PATTERN}'", name="prev_hash_is_a_digest"),
        CheckConstraint(f"entry_hash ~ '{DIGEST_PATTERN}'", name="entry_hash_is_a_digest"),
        CheckConstraint(f"fingerprint ~ '{DIGEST_PATTERN}'", name="fingerprint_is_a_digest"),
        UniqueConstraint("fingerprint"),
        {"schema": "ops"},
    )
