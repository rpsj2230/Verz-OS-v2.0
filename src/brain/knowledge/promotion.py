"""Asking for a document to be readable by the whole company waits on the Approvals screen.

`brain.knowledge.visibility` has held the promotion gate since M7.4.4 was first written: a
proposal, an approval by a second principal holding `approve:knowledge.visibility`, and
`apply_promotion`. `brain.member_library.request_promotion` asks for one at the tier its blast
radius names. Nothing carried a request to a person who could decide it, and the audit of
2026-09-17 reopened M7.4.4 for that. This is the carrying.

**A promotion is a suspended action, so it waits where every other approval waits.** The
Approvals screen reads `gate.suspension`, offers a card to whoever holds the action's capability in
a scope admitting its row, and records the decision through `0083`'s trigger. A promotion raised
as a suspension whose tool requires `approve:knowledge.visibility`, with the document's department
as its row, is offered to exactly the people `approve_promotion` would admit, on the screen they
already watch, with no second queue and no second statement of who may approve. Rejected: a
promotions table and a section of its own on that screen, which would be a second approval
mechanism beside the one M35 built, and the screen's module is not this package's to widen. See
`A_PROMOTION_WAITS_WHERE_EVERY_APPROVAL_WAITS`.

**The widening is applied in the transaction that approves it, by the database.** The Approvals
route decides a card and writes the row; it runs nothing afterwards, because an approved agent
action is resumed by the agent. A promotion has no agent to resume it, so `0120`'s trigger on
`gate.suspension` applies it when the row moves to approved: the document and its passages become
company-wide, the approver's decision and the widening commit together or not at all, and the
ledger records both. The trigger refuses an approval by the person who asked, and one whose
document has moved since it was asked, by raising, so an approval that cannot be carried out is
not recorded as given. See `A_WIDENING_IS_APPLIED_WHERE_IT_IS_APPROVED`.

**A moved document's refusal reaches the approver as a sentence, and closes the card.** Until
2026-09-29 the decision route turned it into a 500, and the card stayed on the screen to fail the
same way for the next approver. `brain.gate.suspension_store` now recognises the trigger's refusal
by `THE_DOCUMENT_MOVED` and raises `NoLongerAppliesError`, and `brain.approval_routes` answers
that the request no longer applies and closes it as rejected under the reason no approver
chooses, which the trigger's own hint asks for: the steward is told, and asks again for the
document as it is now.

**Nor is the person who asked ever offered their own card.** A steward who also holds
`approve:knowledge.visibility` where their document sits reaches the card by the capability alone,
and until 2026-09-29 the Approvals screen offered it to them: approving it met the trigger's
refusal, which the decision route turned into a fault. `asked_by` is the question the queue, the
single card and the decision now ask through `brain.console.role_surfaces.pending_for`, so their
own card is absent for them in the words any card they may not decide gets, and the trigger stays
as the database's second wall. See `THE_PERSON_WHO_ASKED_IS_NEVER_OFFERED_THEIR_OWN_PROMOTION`.

**The approver reads the document's title on the card.** Nobody can judge "make this readable by
everyone" without knowing what this is, and the card is written once, when the promotion is
raised, and shown verbatim. The title of a department document reaches a person holding
`approve:knowledge.visibility` over that department, which is the authority to publish it to
everybody and so to them. The text is never on the card. See
`AN_APPROVER_READS_WHAT_WILL_BE_PUBLISHED`.

**The window is the leash's maximum, a day.** An approval that can stand indefinitely is a
standing grant, which `brain.gate.leash.MAX_APPROVAL_WINDOW` refuses for every action; a
promotion that lapsed is asked for again, and the page says it lapsed.

Task ids: M7.4.4
"""

from __future__ import annotations

import enum
from datetime import datetime, timedelta
from typing import Final
from uuid import uuid4

from brain.core.department import DEPARTMENT_FIELD
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import SideEffect, ToolDefinition
from brain.gate.leash import (
    MAX_APPROVAL_WINDOW,
    Action,
    ApprovalState,
    SuspendedAction,
)
from brain.knowledge.kinds import KIND_LABELS, KnowledgeKind
from brain.knowledge.visibility import PROMOTION_CAPABILITY, PromotionProposal, Visibility

# ------------------------------------------------------------------ written-down reasons
#: Why a promotion is a suspension rather than a queue of its own.
A_PROMOTION_WAITS_WHERE_EVERY_APPROVAL_WAITS: Final = (
    "The Approvals screen offers a card to whoever holds the action's capability in a scope "
    "admitting its row, and records the decision in the ledger. A promotion raised as a "
    "suspension requiring approve:knowledge.visibility over the document's department is offered "
    "to exactly the people the promotion gate admits, on the screen they already watch. A queue "
    "of its own would be a second approval mechanism and a second statement of who may approve."
)

#: Why the database applies the widening.
A_WIDENING_IS_APPLIED_WHERE_IT_IS_APPROVED: Final = (
    "An approved agent action is resumed by its agent, and a promotion has no agent. So the "
    "trigger 0120 puts on gate.suspension applies it in the transaction that approves the card: "
    "the approval and the widening commit together or not at all. An approval by the person who "
    "asked, or of a document that moved since, is refused by raising, so nothing is recorded as "
    "approved that could not be carried out."
)

#: Why the asker is never offered their own card.
THE_PERSON_WHO_ASKED_IS_NEVER_OFFERED_THEIR_OWN_PROMOTION: Final = (
    "A promotion is widened on a second person's say-so, and the trigger 0120 puts on "
    "gate.suspension refuses an approval by the person who asked. Offering them the card anyway, "
    "because they hold the approval where the document sits, puts a button on their screen that "
    "can only fail. So the card is not offered to its asker at all, and they are answered as for "
    "any card they may not decide; everybody else holding the approval there is offered it."
)

#: Why the card names the document.
AN_APPROVER_READS_WHAT_WILL_BE_PUBLISHED: Final = (
    "Nobody can judge making something readable by everyone without knowing what it is, so the "
    "card names the document, its kind, where it sits now, its steward, its next review and why it "
    "was asked for. The approver holds the authority to publish it to everybody, which includes "
    "them. The text is never on the card, and the card is written once and shown verbatim."
)

# ------------------------------------------------------------------ the action
#: The suspension's agent id. Not an agent: a promotion is asked for by a person, and the column
#: needs an identifier, so it names the act. Held equal to `0120`'s trigger by a test.
PROMOTION_AGENT: Final = "knowledge.promotion"

#: What the action is aimed at, in the leash's target grammar.
PROMOTION_TARGET: Final = "knowledge_item"

#: The tool a promotion is. Its capability is the gate's own, so the Approvals screen offers the
#: card to exactly the people `brain.knowledge.visibility.approve_promotion` would admit.
PROMOTION_TOOL: Final = ToolDefinition(
    name="knowledge.publish_item",
    description="Make one knowledge document readable by the whole company.",
    entity=PROMOTION_TARGET,
    required_capability=PROMOTION_CAPABILITY.value,
    side_effect=SideEffect.WRITE,
)

#: How long a promotion waits. See the module docstring.
PROMOTION_WINDOW: Final = MAX_APPROVAL_WINDOW

#: The arguments the action carries, which `0120`'s trigger reads by these names.
PROMOTION_ARGS: Final[tuple[str, ...]] = (
    "from_level",
    "item_id",
    "owner_id",
    "proposer_id",
    "reason",
    "review_by",
    "to_level",
)

#: What a suspension id for a promotion begins with, so a card's id says what it is.
PROMOTION_ID_PREFIX: Final = "promotion."

#: The words `0120`'s trigger refuses an approval in when the document is no longer as it was
#: asked for: another steward, another place, a newer version, or verified past the review date.
#: `brain.gate.suspension_store` recognises the refusal by them, so a test holds them equal to the
#: migration's.
THE_DOCUMENT_MOVED: Final = "the document moved after its promotion was asked for"


class PromotionError(Exception):
    """A promotion that cannot be raised as asked."""


def promotion_action(proposal: PromotionProposal, *, department: str) -> Action:
    """The action a promotion is: its proposal as arguments, its department as its row.

    The row is what an approver's scope is matched against, so a department-scoped grant of the
    capability is offered its own department's promotions and an unrestricted one every one. A
    document with no department has an empty row, which only an unrestricted grant admits.
    """
    args = {
        "item_id": proposal.item_id,
        "from_level": proposal.from_level.value,
        "to_level": proposal.to_level.value,
        "owner_id": proposal.owner_id,
        "review_by": proposal.review_by.isoformat(),
        "reason": proposal.reason,
        "proposer_id": proposal.proposer_id,
    }
    return Action(
        agent_id=PROMOTION_AGENT,
        tool=PROMOTION_TOOL,
        target=PROMOTION_TARGET,
        touched_fields=tuple(sorted(args)),
        row={DEPARTMENT_FIELD: department} if department else {},
        args=args,
    )


def _place_words(level: Visibility, department: str) -> str:
    match level:
        case Visibility.DEPARTMENT:
            return f"the {department} department"
        case Visibility.PERSONAL:
            return "its steward only"
        case Visibility.COMPANY:
            return "the whole company"


def promotion_artefact(
    proposal: PromotionProposal, *, title: str, kind: KnowledgeKind | None, department: str
) -> str:
    """What the approver reads. See `AN_APPROVER_READS_WHAT_WILL_BE_PUBLISHED`."""
    lines = (
        "Make this document readable by the whole company.",
        f"Document: {title or proposal.item_id}",
        f"Kind: {KIND_LABELS[kind] if kind is not None else 'not recorded'}",
        f"Readable now by: {_place_words(proposal.from_level, department)}",
        f"Steward: {proposal.owner_id}",
        f"Next review by: {proposal.review_by.date().isoformat()}",
        f"Asked for by: {proposal.proposer_id}",
        f"Reason: {proposal.reason}",
    )
    return "\n".join(lines)


def raise_promotion(
    proposal: PromotionProposal,
    *,
    title: str,
    kind: KnowledgeKind | None,
    department: str,
    reach: EntitlementSet,
    trace_id: str,
    now: datetime,
    window: timedelta = PROMOTION_WINDOW,
) -> SuspendedAction:
    """The suspension a promotion waits as, raised under the proposer's own reach.

    Refuses a reach that is not the proposer's: the card says whose reach it was raised under,
    and a promotion raised under somebody else's would put their name on it. Refuses anything but
    a promotion to the whole company, because that is the only widening this path carries.
    """
    if reach.principal_id != proposal.proposer_id:
        msg = (
            f"a promotion asked for by {proposal.proposer_id!r} was raised under "
            f"{reach.principal_id!r}'s reach; the card names whose it is"
        )
        raise PromotionError(msg)
    if proposal.to_level is not Visibility.COMPANY:
        msg = "only a promotion to the whole company waits on the Approvals screen"
        raise PromotionError(msg)
    action = promotion_action(proposal, department=department)
    return SuspendedAction(
        id=f"{PROMOTION_ID_PREFIX}{uuid4().hex}",
        trace_id=trace_id,
        action=action,
        principal_id=proposal.proposer_id,
        ent_hash=reach.ent_hash(),
        artefact=promotion_artefact(proposal, title=title, kind=kind, department=department),
        action_digest=action.digest(),
        raised_at=now,
        expires_at=now + window,
    )


# ------------------------------------------------------------------ reading one back
class PromotionStatus(enum.StrEnum):
    """Where a promotion has got to, as its proposer reads it."""

    WAITING = "waiting"
    APPROVED = "approved"
    REJECTED = "rejected"
    #: Nobody decided it inside its window. Asked for again, not approved late.
    LAPSED = "lapsed"


def is_promotion(suspension: SuspendedAction) -> bool:
    """Whether a suspension is a promotion, by the act it names and the capability it needs."""
    return (
        suspension.action.agent_id == PROMOTION_AGENT
        and suspension.action.tool.required_capability == PROMOTION_CAPABILITY.value
    )


def asked_by(suspension: SuspendedAction, principal_id: str) -> bool:
    """Whether this suspension is a promotion this principal asked for, and so not theirs to decide.

    The asker is the suspension's `principal_id`, which `raise_promotion` holds equal to the
    proposer and which `0120`'s trigger compares the approver with. False for every suspension that
    is not a promotion: an agent's action is approved by the person it runs for, which is what
    Assisted means. See `THE_PERSON_WHO_ASKED_IS_NEVER_OFFERED_THEIR_OWN_PROMOTION`.
    """
    return is_promotion(suspension) and suspension.principal_id == principal_id


def promoted_item(suspension: SuspendedAction) -> str:
    """The document a promotion names. Refuses a suspension that is not one."""
    if not is_promotion(suspension):
        msg = f"suspension {suspension.id!r} is not a promotion"
        raise PromotionError(msg)
    return suspension.action.args["item_id"]


def status_of(suspension: SuspendedAction, *, now: datetime) -> PromotionStatus:
    """Waiting, approved, rejected, or lapsed when nobody decided it inside its window."""
    match suspension.state:
        case ApprovalState.APPROVED:
            return PromotionStatus.APPROVED
        case ApprovalState.REJECTED:
            return PromotionStatus.REJECTED
        case ApprovalState.PENDING:
            if suspension.is_expired(now):
                return PromotionStatus.LAPSED
            return PromotionStatus.WAITING
