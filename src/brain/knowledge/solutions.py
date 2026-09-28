"""A solution found in a conversation becomes company knowledge only once a named person approves.

The owner's brief asks for an approved previous solution to become company knowledge only after a
named person approves it, recording what it solved, who approved it and when (M7.6.2). The kind
was there already, `KnowledgeKind.APPROVED_SOLUTION`, and the upload door refuses it, because an
upload naming it would carry the label with none of the approval behind it. This is the path that
sets it.

**Captured is not knowledge.** A captured solution is a row in `know.solution` holding what it
solved and how, in the capturer's words, with the conversation it came from when they name one. It
is in no search and answers nothing. Only its capturer and the people who may decide it read it
while it waits, which `0120`'s policy holds as well as `may_decide` below.

**Approved is a document like any other, verified by the person who approved it.** On approval
the solution becomes a `KnowledgeItem` of the approved-solution kind, published in the department
it was captured for, verified by the approver at the moment of approval with a review date they
set, and stewarded by them. The item's text opens with what it solved, so the record of the
problem travels with the passage an answer cites, and the solution's row keeps the problem, who
decided and when beside the document's id, which is the solution's own. It is then retrieved
exactly as every verified item is, because it is one. See
`AN_APPROVED_SOLUTION_IS_VERIFIED_BY_THE_PERSON_WHO_APPROVED_IT`.

**The named person is somebody else, who may add a document where it would go.** The capturer
cannot approve their own, which is the promotion gate's rule for the same reason; and the approver
holds `admin:knowledge` over the department, the grant K1's upload asks, so the people who could
have added the document by hand are the people who decide whether it is added. Rejected: letting
the capturer name their approver, which would make the form a directory of who administers what,
and would let a capturer pick the one colleague least likely to read it.

**Refused is recorded and nothing is added.** The capturer is told either way, by the task `0120`
opens when the row is decided.

Task ids: M7.6.2
"""

from __future__ import annotations

import enum
import hashlib
import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final

from brain.knowledge.item import ITEM_ID_PATTERN, KnowledgeItem, KnowledgeState
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.lifecycle import (
    Authority,
    LifecycleError,
    StoredItem,
    Verification,
    verification_of,
)
from brain.knowledge.search import TITLE_CHARS
from brain.knowledge.visibility import KnowledgeVisibility

# ------------------------------------------------------------------ written-down reasons
#: Why the approver is the verifier and the steward.
AN_APPROVED_SOLUTION_IS_VERIFIED_BY_THE_PERSON_WHO_APPROVED_IT: Final = (
    "Approving a solution is a named person vouching that it is right, which is what a "
    "verification records, so the document is verified by the approver at the moment they "
    "approved it, with the review date they chose, and they steward it: they are who is asked "
    "when it falls due. What it solved opens the document's text, so an answer citing it carries "
    "the problem with the fix, and the solution's own row keeps who decided and when."
)

#: Why the capturer cannot decide their own.
A_SOLUTION_IS_DECIDED_BY_SOMEBODY_WHO_DID_NOT_CAPTURE_IT: Final = (
    "A solution becomes company knowledge on a named person's word, and the capturer's own word "
    "is what it already had. So the person who decides is somebody else, holding admin:knowledge "
    "where the document would go, and the database refuses a decision by the capturer as well."
)

# ------------------------------------------------------------------ the shape
#: The longest problem statement, and the longest solution. Bounded because both are shown on a
#: card and stored whole; a document is added by upload, not pasted here.
PROBLEM_CHARS: Final = 2000
ANSWER_CHARS: Final = 20000

#: What a solution's id, and the id of the document it becomes, begins with.
SOLUTION_ID_PREFIX: Final = "solution."

#: How much of the digest names a solution: 160 bits, far inside the reference grammar.
SOLUTION_DIGEST_CHARS: Final = 40

#: The two headings the approved document's text is laid out under, blank-line separated so the
#: chunker keeps each as its own block.
SOLVED_HEADING: Final = "What it solved"
SOLUTION_HEADING: Final = "The solution"

_REFERENCE = re.compile(ITEM_ID_PATTERN)


class SolutionState(enum.StrEnum):
    """Where a captured solution has got to. Held equal to `0120`'s check by a test."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SolutionNotOffered(Exception):  # noqa: N818 - a refusal, named like the ones beside it
    """Capturing a solution there, or deciding this one, is not this person's.

    Answered as absent, in one sentence, so it never says which departments exist or which
    solutions are waiting.
    """


#: The one refusal every solution a person may not decide gets, and every one that is not there.
NOT_DECIDABLE: Final = "that solution is not one you may decide"

#: The one refusal capturing into a department this person does not reach gets.
NOT_CAPTURABLE: Final = "capturing a solution there is not offered to you"


@dataclass(frozen=True)
class CapturedSolution:
    """One captured solution, as `know.solution` holds it."""

    solution_id: str
    department: str
    problem: str
    answer: str
    captured_by: str
    captured_at: datetime
    conversation_ref: str = ""
    state: SolutionState = SolutionState.PENDING
    decided_by: str = ""
    decided_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.problem.strip() or len(self.problem) > PROBLEM_CHARS:
            msg = f"say what the solution solved, in at most {PROBLEM_CHARS} characters"
            raise LifecycleError(msg)
        if not self.answer.strip() or len(self.answer) > ANSWER_CHARS:
            msg = f"say what the solution is, in at most {ANSWER_CHARS} characters"
            raise LifecycleError(msg)
        if self.conversation_ref and not _REFERENCE.match(self.conversation_ref):
            msg = (
                "a conversation is named by its reference, letters, digits and . _ @ - only, "
                "as the Ask page shows it"
            )
            raise LifecycleError(msg)
        if self.captured_at.tzinfo is None:
            msg = "a capture is dated in a timezone; a naive date is a silent bug"
            raise LifecycleError(msg)
        if bool(self.decided_by) != (self.decided_at is not None):
            msg = "a decision is a person and a date, or it is nothing"
            raise LifecycleError(msg)
        if bool(self.decided_by) == (self.state is SolutionState.PENDING):
            named = "names a" if self.decided_by else "names no"
            msg = f"a {self.state.value} solution {named} decider"
            raise LifecycleError(msg)
        if self.decided_by and self.decided_by == self.captured_by:
            raise LifecycleError(A_SOLUTION_IS_DECIDED_BY_SOMEBODY_WHO_DID_NOT_CAPTURE_IT)

    @property
    def title(self) -> str:
        """What the solution is called: the first line of what it solved, as a title fits."""
        first = self.problem.strip().splitlines()[0].strip()
        return first[:TITLE_CHARS]

    @property
    def item_id(self) -> str:
        """The document it becomes when approved. The solution's own id."""
        return self.solution_id


def solution_id_for(*, captured_by: str, department: str, problem: str, at: datetime) -> str:
    """A capture's id: a digest of who, where, what and when, never the words themselves."""
    parts = (captured_by, department, at.isoformat(), problem)
    digest = hashlib.sha256(chr(10).join(parts).encode("utf-8")).hexdigest()
    return SOLUTION_ID_PREFIX + digest[:SOLUTION_DIGEST_CHARS]


def capture(
    *,
    problem: str,
    answer: str,
    department: str,
    conversation_ref: str,
    by: Authority,
    now: datetime,
) -> CapturedSolution:
    """Capture one solution for one department this person reads or adds to (M7.6.2).

    A department outside their reach is refused in one sentence, the same for one that does not
    exist, so the form is not a way to ask which departments exist.
    """
    if department not in by.store_reach().departments:
        raise SolutionNotOffered(NOT_CAPTURABLE)
    problem, answer = problem.strip(), answer.strip()
    return CapturedSolution(
        solution_id=solution_id_for(
            captured_by=by.principal_id, department=department, problem=problem, at=now
        ),
        department=department,
        problem=problem,
        answer=answer,
        captured_by=by.principal_id,
        captured_at=now,
        conversation_ref=conversation_ref.strip(),
    )


def may_decide(solution: CapturedSolution, by: Authority) -> bool:
    """Whether this person may approve or refuse this solution now.

    Waiting, not theirs, and in a department they hold `admin:knowledge` over. See
    `A_SOLUTION_IS_DECIDED_BY_SOMEBODY_WHO_DID_NOT_CAPTURE_IT`.
    """
    return (
        solution.state is SolutionState.PENDING
        and solution.captured_by != by.principal_id
        and by.adds is not None
        and solution.department in by.adds.departments
    )


def solution_text(solution: CapturedSolution) -> str:
    """The approved document's text: what it solved, then the solution, each under its heading."""
    return chr(10).join(
        (SOLVED_HEADING, "", solution.problem, "", SOLUTION_HEADING, "", solution.answer)
    )


def approved_item(
    solution: CapturedSolution, *, by: Authority, review_by: datetime, now: datetime
) -> KnowledgeItem:
    """The document an approved solution becomes (M7.6.2).

    Verified by the approver now, with their review date, stewarded by them, published in the
    solution's department, of the approved-solution kind. See
    `AN_APPROVED_SOLUTION_IS_VERIFIED_BY_THE_PERSON_WHO_APPROVED_IT`.
    """
    if not may_decide(solution, by):
        raise SolutionNotOffered(NOT_DECIDABLE)
    placed = KnowledgeVisibility.of_department(solution.department, owner_id=by.principal_id)
    item = KnowledgeItem(
        item_id=solution.item_id,
        content=solution_text(solution),
        title=solution.title,
        visibility=placed,
        owner_id=by.principal_id,
        state=KnowledgeState.PUBLISHED,
        kind=KnowledgeKind.APPROVED_SOLUTION,
    )
    about_to_be_stored = StoredItem(
        item_id=item.item_id,
        title=item.title,
        owner_id=item.owner_id,
        visibility=item.visibility,
        state=item.state,
        kind=item.kind,
    )
    vouched: Verification = verification_of(
        about_to_be_stored, by=by.principal_id, at=now, review_by=review_by
    )
    return item.verified(
        by=vouched.verified_by, at=vouched.verified_at, review_by=vouched.review_by
    )


def decided(
    solution: CapturedSolution, *, by: Authority, outcome: SolutionState, at: datetime
) -> CapturedSolution:
    """The solution as decided. Refuses a decision this person may not take, or one that says
    nothing."""
    if not may_decide(solution, by):
        raise SolutionNotOffered(NOT_DECIDABLE)
    if outcome is SolutionState.PENDING:
        msg = "a decision approves or refuses; leaving it waiting is not one"
        raise LifecycleError(msg)
    return replace(solution, state=outcome, decided_by=by.principal_id, decided_at=at)
