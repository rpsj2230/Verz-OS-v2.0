"""The auditor's two derived views: a subject's permission history, and refusal statistics.

Both are readings of `brain.audit.view.AuditView` and neither is a second view. That module
already decides what one reader may see, entry by entry, and it argues at length about what an
`AuditRow` deliberately does not carry: no chain numbers, because a reader who sees the numbers
of the entries they may read has been told how many lie between them; no entitlement hash,
because to a reader it is a grouping key and therefore the permission map with the labels
rubbed off; and no total on a page, because the subtraction between a total and the rows shown
is the hidden count no part of this system may emit.

Everything here is computed from rows that survived that decision. A derived view that read the
entries directly would be a second answer to who may see what, and the permissive copy is the
one on the screen somebody trusts.

**A history is a filter and a statistic is not, which is the whole difficulty.** M33.4.1.2 asks
for grant and leash history, and that is a narrowing: fewer rows, each of which the reader
could already have read one at a time. M33.4.1.3 asks for redaction and refusal statistics, and
a statistic is an aggregate over rows, which means it can say something the rows do not.

**So a refusal statistic is a count of denials, and a count of denials is one question away
from a count of hidden things.** "Forty refusals against nine targets" tells a reader there are
nine things they cannot see and roughly how much traffic goes at them, which is nine facts they
did not have. `brain.ops.denial_alerts` reached this first and answers it by naming the shape
of a pattern and never the capability or the object; `brain.console.govern.friction` carries
that on to a screen and collapses repeated runs, because two identical rows are the same count
spelled with repetition. This module is the third place the same rule applies and it does not
restate it: `DENIAL_SHAPE` is `denial_alerts`' own vocabulary and the statistics are grouped by
it.

**What that leaves is a statistic about the reader's own visible slice, and it is honest.** A
denial the reader may see is one they hold the audit grant over, so counting those tells them
about entries they could have read individually and the count is arithmetic rather than
disclosure. A denial they may not see contributes nothing, and contributes nothing *silently*:
there is no residual bucket, no "and others", and no total to subtract from. That is the same
shape as `AuditPage` having no total, one aggregation up.

**Rejected: a per-capability or per-object breakdown of refusals.** It is the obvious thing an
auditor asks for and it is a map of what exists: a capability that appears in a refusal
breakdown is a capability, and an object that appears is an object. The shape is what an
auditor can act on anyway, because the question a refusal statistic answers is "is somebody
repeatedly hitting a boundary", and the answer to that is a pattern rather than a name.

**Rejected: a redaction count per field.** Redaction statistics are per entry and never per
field for the same reason. A field name appearing in a redaction count says that field exists
and that somebody was refused it, which is `brain.core.redaction`'s whole subject arriving
through a report.

Task ids: M33.4.1.2, M33.4.1.3
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.audit.ledger import AuditAction
from brain.audit.view import MAX_PAGE_SIZE, AuditFilter, AuditRow, AuditView
from brain.ops.denial_alerts import ALERT_TEXT
from brain.ops.limits import DenialShape

#: The actions that change what somebody may do, as opposed to recording what they did.
#:
#: Grant and revoke move a capability; a leash change moves a rung; break glass is a reach
#: taken for a window. Read as a set rather than as four `if`s so the history and the test that
#: pins it are one list, and so a ninth action added to `AuditAction` has to be classified
#: deliberately rather than silently falling outside the history.
PERMISSION_ACTIONS: Final[frozenset[AuditAction]] = frozenset(
    {
        AuditAction.GRANT,
        AuditAction.REVOKE,
        AuditAction.LEASH_CHANGE,
        AuditAction.BREAK_GLASS,
    }
)

#: Why a refusal statistic is grouped by shape and never by what was refused.
A_COUNT_OF_REFUSALS_BY_NAME_IS_A_MAP_OF_WHAT_EXISTS: Final = (
    "A refusal statistic broken down by capability or by object tells the reader that those "
    "capabilities and objects exist and that somebody was refused them, which is a list of "
    "things they cannot see arrived at through a report. The shape is what an auditor can act "
    "on anyway: the question a refusal statistic answers is whether somebody is repeatedly "
    "hitting a boundary, and the answer to that is a pattern rather than a name. This is "
    "brain.ops.denial_alerts' rule, applied a third time and not restated."
)

#: Why there is no residual bucket, no total, and no note that anything was left out.
NOTHING_COUNTS_WHAT_THE_READER_MAY_NOT_SEE: Final = (
    "Every figure here is computed from rows brain.audit.view already admitted for this "
    "reader. An entry they may not see contributes nothing and contributes it silently: a "
    "residual bucket, an 'and others' line or a total to subtract from would each be the "
    "hidden count that brain.audit.view.AuditPage refuses to carry, one aggregation up."
)


@dataclass(frozen=True)
class PermissionEvent:
    """One row of a subject's permission history, as an auditor reads it."""

    at: datetime
    action: AuditAction
    actor_id: str
    subject_kind: str
    subject_id: str
    #: The ledger's own details, already redacted twice by the time they arrive here.
    details: dict[str, str]


@dataclass(frozen=True)
class RefusalStatistic:
    """How often one shape of refusal happened, and the sentence that names the shape."""

    shape: DenialShape
    occurrences: int
    #: `denial_alerts`' own wording for this shape. Carried rather than re-derived, so a
    #: screen cannot render a shape under a sentence this repository did not write.
    reads_as: str


def permission_history(
    view: AuditView,
    *,
    subject_kind: str,
    subject_id: str,
    limit: int = MAX_PAGE_SIZE,
) -> tuple[PermissionEvent, ...]:
    """Everything that changed what this subject may do, oldest first (M33.4.1.2).

    A narrowing of `AuditView.page` and nothing more: the actions are `PERMISSION_ACTIONS`,
    the subject is required, and every row comes back through the view's own visibility
    decision. A reader who could not read an entry one at a time does not acquire it by asking
    for a history.

    **The subject is required and there is no value meaning everybody.** A permission history
    over no subject is the whole ledger filtered to the four actions that matter most, which
    is the grant graph of the company, and it is exactly the query an auditor would type first.
    `brain.console.govern_estate` made the same decision about the memory viewer and
    `brain.console.agent_automations` about a listing with no agent id.

    Oldest first, matching the view, because a permission history read newest first shows the
    revocation above the grant and reads as though the person never held it.
    """
    if not subject_kind.strip() or not subject_id.strip():
        msg = (
            "a permission history needs a subject; asked about nobody it is the company's "
            "grant graph filtered to the four actions that carry the most"
        )
        raise ValueError(msg)

    page = view.page(
        AuditFilter(
            actions=frozenset(PERMISSION_ACTIONS),
            subject_kinds=frozenset({subject_kind}),
        ),
        limit=limit,
    )
    return tuple(
        PermissionEvent(
            at=row.at,
            action=row.action,
            actor_id=row.actor_id,
            subject_kind=row.subject_kind,
            subject_id=row.subject_id,
            details=dict(row.details),
        )
        for row in page.rows
        if row.subject_id == subject_id
    )


def refusal_statistics(
    view: AuditView,
    *,
    shapes: dict[str, DenialShape],
    limit: int = MAX_PAGE_SIZE,
) -> tuple[RefusalStatistic, ...]:
    """How often each shape of refusal happened, in this reader's own view (M33.4.1.3).

    `shapes` maps an entry's subject reference to the shape `brain.ops.denial_alerts` assessed
    it as. It is handed in rather than computed here because assessing a pattern is that
    module's question and this one must not have a second opinion about it; what is decided
    here is only what a screen may show once it has the answer.

    See `A_COUNT_OF_REFUSALS_BY_NAME_IS_A_MAP_OF_WHAT_EXISTS` and
    `NOTHING_COUNTS_WHAT_THE_READER_MAY_NOT_SEE`.

    A shape with no occurrences in this reader's view is absent rather than reported at zero.
    A row reading "impersonation: 0" is a reader being told that shape exists and that nobody
    they can see has produced it, which is a fact about the vocabulary and a fact about the
    rest of the ledger at once.

    Ordered by shape rather than by count, because ordering by count puts the busiest boundary
    first and that ordering is itself a figure: a reader comparing two runs learns which shape
    moved without either count being shown to them.
    """
    page = view.page(AuditFilter(actions=frozenset({AuditAction.DENY})), limit=limit)

    seen: Counter[DenialShape] = Counter()
    for row in page.rows:
        shape = shapes.get(row.subject_id)
        if shape is None:
            # A denial nobody assessed is not a shape, and guessing one here would be this
            # module forming the opinion the paragraph above says it must not.
            continue
        seen[shape] += 1

    return tuple(
        RefusalStatistic(shape=shape, occurrences=count, reads_as=ALERT_TEXT[shape])
        for shape, count in sorted(seen.items(), key=lambda pair: pair[0].value)
        if shape in ALERT_TEXT
    )


def redaction_statistics(
    rows: tuple[AuditRow, ...],
) -> int:
    """How many of these entries carried a redaction, and nothing about which field (M33.4.1.3).

    An integer rather than a mapping, and that is the whole decision. A redaction count per
    field says that field exists and that somebody was refused it, which is
    `brain.core.redaction`'s subject arriving through a report.

    Counted over rows the caller already holds, so this cannot widen anything: it is given
    what a reader may see and returns a property of it.
    """
    return sum(1 for row in rows if any(value == "<redacted>" for value in row.details.values()))
