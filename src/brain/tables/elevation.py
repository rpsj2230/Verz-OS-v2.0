"""Elevation requests: who asked for more, what they were given, and when it lapses.

`brain.gate.elevation_store` writes this table and `migrations/versions/0062_organisation_and_
elevation.py` holds the argument for its policies and its trigger; what is here is the model that
mirrors it. `brain.console.elevation` decides the rules a break-glass session is held to, and until
this table nothing stored one, so the Elevation screen said no request could be approved or denied.

**A request is one row, decided once, and what it gave is a grant row with a lapse.** The decision,
who made it and when move from nothing to a value in one update, which is the only update the
application role may make. An approval also points `grant_id` at the `gate.capability_grant` row it
wrote and copies that row's `not_after` into `lapses_at`, so "what were they given and when does it
stop" is read off one row, and the reach itself is the ordinary grant the resolver already honours
and lets lapse on its own. There is no session state here that a request consults: the grant is the
session, and `gate.held_grants` stops returning it at `not_after` with nobody doing anything.

**The table refuses the shapes a hurried statement would write.** A decision with no decider or no
instant. A decision by the person who asked, which `not_decided_by_its_requester` refuses beside the
route's own refusal, for the reason `gate.review_decision` gives about its twin. An approval with no
grant, a denial with one, or a pending row with one. And a lapse later than the window asked for,
because the hours on the request are the longest the grant may run, which is
`brain.identity.roles.BREAK_GLASS_MAX` applied to the row rather than remembered by a caller.

**The scope is named and the reason is a code.** `scope_slug` is a `gate.scope` slug, resolved by
whoever approves, for `brain.govern_routes`' reason that a typed predicate is one nobody named, and
because resolving it for the requester would tell somebody holding nothing which scopes exist.
`reason` is `BreakGlassReason`, so the ledger entry says something; `explanation` is the sentence
the requester typed, kept on the row and never put in the ledger, which would reduce it to a marker.

**No foreign key on the decider**, for the reason `brain.tables.review` gives about `decided_by`.
The requester is a foreign key, as a grant's principal is: a request by nobody this install knows
is not a request.

Task ids: M27.7.8
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Final

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from brain.audit.ledger import IDENTIFIER
from brain.core.entitlement import VERBS
from brain.db import Base
from brain.identity.roles import BREAK_GLASS_MAX, BreakGlassReason
from brain.tables.gate import (
    CAPABILITY_CHARS,
    CAPABILITY_PATTERN,
    SLUG_CHARS,
    SLUG_SQL_PATTERN,
)
from brain.tables.identity import PRINCIPAL_ID_CHARS, one_of


class ElevationDecision(enum.StrEnum):
    """What a request can come to. Two words, and pending is the absence of either."""

    APPROVED = "approved"
    DENIED = "denied"


#: Wide enough for the longer of the two words and no wider.
DECISION_CHARS: Final = 8

#: Wide enough for the longest `BreakGlassReason`, with room for one more code.
REASON_CHARS: Final = 32

#: The longest sentence a requester may type about what the elevation is for.
EXPLANATION_CHARS: Final = 500

#: The longest window a request may ask for, in whole hours: `BREAK_GLASS_MAX`, read rather than
#: restated, so the table and the session rules are one bound.
LONGEST_HOURS: Final = int(BREAK_GLASS_MAX.total_seconds() // 3600)


class ElevationRequestRow(Base):
    """`gate.elevation_request`. One request, its decision, and the grant an approval wrote."""

    __tablename__ = "elevation_request"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    #: Who asked. The subject of every ledger entry about this request.
    principal_id: Mapped[str] = mapped_column(
        String(PRINCIPAL_ID_CHARS),
        ForeignKey("auth.principal.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    capability: Mapped[str] = mapped_column(String(CAPABILITY_CHARS), nullable=False)
    scope_slug: Mapped[str] = mapped_column(String(SLUG_CHARS), nullable=False)
    reason: Mapped[str] = mapped_column(String(REASON_CHARS), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    hours: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decision: Mapped[str | None] = mapped_column(String(DECISION_CHARS), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(PRINCIPAL_ID_CHARS), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: The grant an approval wrote. Null while pending and for a denial.
    grant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("gate.capability_grant.id", ondelete="RESTRICT"),
        nullable=True,
    )
    #: That grant's `not_after`, copied so the screen reads one row. Null exactly when `grant_id`
    #: is.
    lapses_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"capability ~ '{CAPABILITY_PATTERN}'", name="capability_grammar"),
        CheckConstraint(one_of("split_part(capability, ':', 1)", VERBS), name="capability_verb"),
        CheckConstraint(f"scope_slug ~ '{SLUG_SQL_PATTERN}'", name="scope_slug_grammar"),
        CheckConstraint(one_of("reason", BreakGlassReason), name="reason"),
        CheckConstraint(
            f"length(btrim(explanation)) > 0 AND length(explanation) <= {EXPLANATION_CHARS}",
            name="explained",
        ),
        CheckConstraint(f"hours BETWEEN 1 AND {LONGEST_HOURS}", name="hours_within_the_bound"),
        # A pending row's null passes, as a null passes every check constraint.
        CheckConstraint(one_of("decision", ElevationDecision), name="decision"),
        CheckConstraint(
            "(decision IS NULL) = (decided_by IS NULL) "
            "AND (decision IS NULL) = (decided_at IS NULL)",
            name="a_decision_names_who_and_when",
        ),
        CheckConstraint(f"decided_by IS NULL OR decided_by ~ '{IDENTIFIER}'", name="decider_shape"),
        CheckConstraint(
            "decided_by IS NULL OR decided_by <> principal_id", name="not_decided_by_its_requester"
        ),
        CheckConstraint(
            "(decision IS NOT DISTINCT FROM 'approved') = (grant_id IS NOT NULL)",
            name="an_approval_and_only_an_approval_names_its_grant",
        ),
        CheckConstraint("(grant_id IS NULL) = (lapses_at IS NULL)", name="a_grant_lapses"),
        CheckConstraint(
            "lapses_at IS NULL OR lapses_at <= decided_at + make_interval(hours => hours::int)",
            name="no_longer_than_asked",
        ),
        {"schema": "gate"},
    )
