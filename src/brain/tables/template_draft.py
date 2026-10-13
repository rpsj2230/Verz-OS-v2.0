"""`agent.template_draft`: an agent saved as a template, waiting on a person (M13.8.15).

`brain.agents.authoring` had the whole flow (`author`, `scan`, `decide`, `publish_authored`) as
values in a process, and its docstring says what that cost: "a draft does not survive a restart and
the author redoes the report." `0223` builds the table that closes it, and `brain.agents.
template_draft_store` is its one writer.

**One row per draft, holding the body as the agent's own document and the decisions made so far.**
The document is the same flat map a signed manifest holds, checked by the same two constraints
(`brain.tables.template`): every path present and none other. The decisions are one JSON object
keyed by item id, each a `brain.agents.authoring.Decision`, rewritten as a person decides item
after item. Rejected: one row per decision, which is the better history and a second table, for a
flow whose decisions are replaced when the author changes their mind and whose final record is the
`AuthoredTemplate` published.

**Only its author reads it, writes it and publishes it.** The document is an agent's persona and
configuration before anybody has looked for what is in it, so the policies admit the author and no
one else, including an administrator, and a draft is not a template. Nothing installs from this
table: an installation reads `agent.template_version`, which a draft reaches only when its author
publishes, which is what makes the leaf's last clause a property of where each thing lives.

**Published once.** A published draft names the version it became and when, and the policy admits
an update only to a draft that is still a draft.

Task ids: M13.8.15
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from brain.agents.model import AGENT_ID_CHARS, OWNER_ID_CHARS
from brain.db import Base
from brain.tables.identity import one_of
from brain.tables.template import _holds_every_path, _holds_no_other_path, _present

#: The widest state word, `published`, with room.
STATE_CHARS: Final = 16


class DraftState(enum.StrEnum):
    """Where a template draft stands. Two, and a published one is no longer edited."""

    DRAFT = "draft"
    PUBLISHED = "published"


class TemplateDraftRow(Base):
    """One agent saved as a template, the decisions taken about it, and what it became."""

    __tablename__ = "template_draft"
    __table_args__ = (
        CheckConstraint(_present("author"), name="author_present"),
        CheckConstraint(one_of("state", DraftState), name="state"),
        CheckConstraint("jsonb_typeof(document) = 'object'", name="document_shape"),
        CheckConstraint(_holds_every_path("document"), name="document_holds_every_path"),
        CheckConstraint(_holds_no_other_path("document"), name="document_holds_no_other_path"),
        CheckConstraint("jsonb_typeof(decisions) = 'object'", name="decisions_shape"),
        CheckConstraint(
            "(state = 'published') = (published_version IS NOT NULL)",
            name="a_published_draft_names_its_version",
        ),
        CheckConstraint(
            "(published_version IS NULL) = (published_at IS NULL)",
            name="a_published_draft_names_its_instant",
        ),
        Index("ix_agent_template_draft_author", "author", "updated_at"),
        {"schema": "agent"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    author: Mapped[str] = mapped_column(String(OWNER_ID_CHARS), nullable=False)
    #: The agent it was saved from, or null for a document that came from nowhere in this install.
    source_agent_id: Mapped[str | None] = mapped_column(String(AGENT_ID_CHARS), nullable=True)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    decisions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    state: Mapped[str] = mapped_column(
        String(STATE_CHARS), nullable=False, server_default=DraftState.DRAFT.value
    )
    published_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.statement_timestamp()
    )
