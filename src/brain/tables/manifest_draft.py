"""`agent.manifest_draft`, `agent.manifest_revision` and `agent.manifest_act`: an agent's drafts.

`brain.builder.drafts` argues that a draft is a sequence of revisions and never an edit in place,
and named the tables it would need: revisions keyed by draft and number, and what was done to each
revision keyed by draft and revision, granted SELECT and INSERT and never UPDATE or DELETE. These
are those tables, for a draft of one agent (`brain.builder.agent_drafts`).

**Three tables and no state column.** Where a draft stands (drafted, checked, waiting for a second
person, sent back, published) is read off its latest revision's acts by
`brain.builder.agent_drafts.state_of`. A state column would be overwritten by each step, and "who
asked, who approved and when" is the question asked after an agent does something unexpected.

**A row is written only as the session's own principal**: the draft's owner, the revision's saver
and the act's actor each have to be `app.principal_id`, which `0136` asks of a halt. A row saying
somebody else saved a draft, or approved one, is refused by the database.

**No foreign key to `agent.agent`.** A new agent's id is minted when its draft starts and the agent
row exists only once it is published, and an edit's draft outlives nothing it could point at.

The vocabularies are the domain's own through `one_of`, and `0149` copies each; `tests/unit/
test_agent_draft_store.py` holds the copy to these.

Task ids: M27.11.6, M13.7.4
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.agents.model import AGENT_ID_CHARS
from brain.builder.draft_words import DraftAct, DraftKind
from brain.core.department import SLUG_PATTERN
from brain.db import Base
from brain.tables.agent import CHANNEL_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of

#: `edit` is the longest kind.
KIND_CHARS: Final = 8

#: `published` and `requested` are the longest acts, with room for one more.
ACT_CHARS: Final = 16

#: A configuration digest, `brain.agents.template.config_hash`.
HASH_CHARS: Final = 64

#: The slug grammar over `agent_id`, with the colon escaped for the reason
#: `brain.tables.agent._ESCAPED_COLON` gives.
AGENT_ID_GRAMMAR: Final = "agent_id ~ '" + SLUG_PATTERN.replace(":", "\\:") + "'"

#: An edit names the configuration it started from, and a new agent has none.
BASE_HASH_IFF_EDIT: Final = "(kind = 'edit') = (base_hash IS NOT NULL)"


class ManifestDraftRow(Base):
    """`agent.manifest_draft`. One draft: whose, which agent, and what it started from."""

    __tablename__ = "manifest_draft"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: The agent it makes, minted when it started, or the agent it changes.
    agent_id: Mapped[str] = mapped_column(String(AGENT_ID_CHARS), nullable=False)
    kind: Mapped[str] = mapped_column(String(KIND_CHARS), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: For an edit, the configuration digest of the agent when the draft started.
    base_hash: Mapped[str | None] = mapped_column(String(HASH_CHARS), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(AGENT_ID_GRAMMAR, name="agent_id_grammar"),
        CheckConstraint(one_of("kind", DraftKind), name="kind"),
        CheckConstraint(BASE_HASH_IFF_EDIT, name="base_hash_iff_edit"),
        Index("ix_agent_manifest_draft_owner_id", "owner_id"),
        Index("ix_agent_manifest_draft_agent_id", "agent_id"),
        {"schema": "agent"},
    )


class ManifestRevisionRow(Base):
    """`agent.manifest_revision`. One save: the whole document, who saved it, and when."""

    __tablename__ = "manifest_revision"

    draft_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent.manifest_draft.id"), primary_key=True
    )
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: A manifest document in the manifest's own nesting, whole or not yet.
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    saved_by: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint("number >= 1", name="number_from_one"),
        CheckConstraint("jsonb_typeof(body) = 'object'", name="body_is_an_object"),
        {"schema": "agent"},
    )


class ManifestActRow(Base):
    """`agent.manifest_act`. One act on one revision, at most once per revision."""

    __tablename__ = "manifest_act"

    draft_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    act: Mapped[str] = mapped_column(String(ACT_CHARS), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    #: Whether the revision reached further than the agent did, when the act was taken.
    widened: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    #: For a new agent: seen by the author's department rather than the author alone.
    for_department: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    #: For a new agent: the channels its author ticked, since `0189` (M13.7.4).
    channels: Mapped[list[str]] = mapped_column(
        ARRAY(String(CHANNEL_CHARS)), nullable=False, server_default=text("'{}'")
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_id", "revision"],
            ["agent.manifest_revision.draft_id", "agent.manifest_revision.number"],
        ),
        CheckConstraint(one_of("act", DraftAct), name="act"),
        {"schema": "agent"},
    )
