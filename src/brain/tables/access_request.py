"""`gate.access_request`: a refusal somebody asked to have reconsidered, addressed to its decider.

`brain.core.access_route.route_access_request` turns a locked field into an owner's notice and a
reply that says nothing, and until this table the notice went nowhere: the route existed as domain
logic with no caller (M4.3.4). A row is one notice, delivered by being on its owner's list in the
console, `brain.access_request_routes`.

**One subject per row, a field or a department.** A field is `entity` and `field`, the lock the
asker was shown; a department is `department`, the gap an answer stated (M2.2.4). The check
refuses a row naming both or neither, so a request cannot be about something unnamed.

**The question is kept, for its owner.** The owner is deciding whether this person should see this
for this reason, and the reason is the question; see `brain.core.redaction.OwnerNotice`. It is
read by the owner's list and by nothing that reaches the asker, whose reply is a constant.

**Insert and read, and marked handled once; never deleted.** A request is a record that it was
made; a decision is a grant written on the People or Roles screens, which is where an owner acts on
it. Since `0146` its owner may mark it handled, once: `handled_at` and `handled_by` are the only
columns the application may update, both or neither, and only to the owner's own id.

Task ids: M4.3.4, M2.2.4, M27.16.1
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import CheckConstraint, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from brain.db import Base
from brain.tables.gate import CAPABILITY_CHARS, CAPABILITY_PATTERN, SLUG_CHARS
from brain.tables.identity import PRINCIPAL_ID_CHARS

#: `brain.core.redaction.AccessRequest.question`'s bound.
QUESTION_CHARS: Final = 2000
#: An entity or a field name, `brain.core.redaction`'s name grammar.
NAME_CHARS: Final = 120
NAME_PATTERN: Final = "^[a-z][a-z0-9_]*$"

#: Exactly one subject: a field on an entity, or a department.
ONE_SUBJECT: Final = (
    "(entity IS NOT NULL AND field IS NOT NULL AND department IS NULL) OR "
    "(entity IS NULL AND field IS NULL AND department IS NOT NULL)"
)


#: A request is handled whole, and only by its own owner (`0146`).
HANDLED_WHOLE: Final = "(handled_at IS NULL) = (handled_by IS NULL)"
HANDLED_BY_ITS_OWNER: Final = "handled_by IS NULL OR handled_by = owner_id"


class AccessRequestRow(Base):
    """`gate.access_request`. One request, addressed to one owner."""

    __tablename__ = "access_request"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    asker_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=False, index=True)
    entity: Mapped[str | None] = mapped_column(String(NAME_CHARS), nullable=True)
    field: Mapped[str | None] = mapped_column(String(NAME_CHARS), nullable=True)
    department: Mapped[str | None] = mapped_column(String(SLUG_CHARS), nullable=True)
    question: Mapped[str] = mapped_column(String(QUESTION_CHARS), nullable=False)
    requested_capability: Mapped[str] = mapped_column(String(CAPABILITY_CHARS), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: When its owner marked it handled, and who; both or neither, and only the owner (`0146`).
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handled_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)

    __table_args__ = (
        CheckConstraint(ONE_SUBJECT, name="one_subject"),
        CheckConstraint(f"entity IS NULL OR entity ~ '{NAME_PATTERN}'", name="entity_name"),
        CheckConstraint(f"field IS NULL OR field ~ '{NAME_PATTERN}'", name="field_name"),
        CheckConstraint(
            f"department IS NULL OR department ~ '{NAME_PATTERN}'", name="department_name"
        ),
        CheckConstraint("length(btrim(question)) >= 1", name="question_present"),
        CheckConstraint(
            f"requested_capability ~ '{CAPABILITY_PATTERN}'", name="requested_capability_grammar"
        ),
        CheckConstraint(HANDLED_WHOLE, name="handled_whole"),
        CheckConstraint(HANDLED_BY_ITS_OWNER, name="handled_by_its_owner"),
        {"schema": "gate"},
    )
