"""The install acceptance check for a correction carrying the right answer: held, grouped, offered
to the steward, decided as a new version, and refused to everybody else (M16.6.5, M16.6.6, M16.7.6).

The check drives the routes' own functions, `brain.thread_routes.correct_my_thread` and
`brain.candidate_routes`, with the request shape `brain.ops.acceptance_checks_review` builds, so the
correction, the candidate, the steward's task, the new version and the ledger entry are the
install's own, written through `0198`'s function and policies, and all of it is rolled back. The
document is added through the upload route's sequence by `acceptance_checks_lifecycle._added`, and
the answer the correction is about is a thread exchange written by `brain.chat.thread_store`, citing
a passage the corrector's own search found.

**What a person may not do is asked beside what succeeds.** The person whose correction it is may
not read it as a reviewer and may not decide it; an administrator of acceptance_b may do neither;
the steward reads the words beside who will read them, and approves them into a new version that
answers from then on. A second correction of another document is rejected with a reason, and the
same answer corrected again proposes nothing, because it is the evidence the rejection kept.

Task ids: M16.6.5, M16.6.6, M16.7.6
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Final, cast

from sqlalchemy import text

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _found, _in
from brain.ops.acceptance_checks_lifecycle import REVIEW_AHEAD, _added, _as, _tasks
from brain.ops.acceptance_checks_review import _app, _request
from brain.ops.acceptance_run import Harness

#: Where this module's check stands on the Install page.
CHECK_ORDER: Final = 444

A, B = RESERVED_DEPARTMENTS

#: How long after an answer the check's people correct it.
CORRECTED_AFTER: Final = timedelta(minutes=1)

NOT_HELD: Final = (
    "a correction carrying the right answer was not held as a candidate about its document"
)
NOT_GROUPED: Final = "two corrections to the same words were not one candidate carrying both"
NOT_ASKED: Final = "the document's steward was not asked to review the correction"
SHOWN_TO_ITS_PROPOSER: Final = (
    "a person whose correction a candidate holds, or an administrator elsewhere, could read or "
    "decide it"
)
NO_AUDIENCE: Final = "the reviewer was not shown the words beside who will read them"
NOT_APPLIED: Final = (
    "an approved correction did not become a new version answering with its words, once, on the "
    "ledger under its reviewer"
)
NOT_ONE_S_OWN: Final = (
    "a correction was proposed in one person's name from another person's conversation"
)
NOT_REJECTED: Final = (
    "a rejected correction did not keep its reason, or its evidence proposed it again"
)


async def _asking(h: Harness, principal_id: str, *, later: timedelta = timedelta(0)) -> Any:
    """What the routes read of a signed-in person: who, the admitted reach and the instant."""
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.STRONG)
    # A cast at the routes' boundary, as `acceptance_checks_review._reader` makes it.
    return cast(
        Any,
        SimpleNamespace(caller=SimpleNamespace(principal=person), reach=reach, now=h.now + later),
    )


async def _corrected(
    h: Harness, person: str, word: str, right: str, *, after: timedelta = CORRECTED_AFTER
) -> str:
    """`person` asks about the document holding `word`, is answered citing its passage, and
    corrects that answer with `right` through the correction route. The thread's id."""
    from brain.chat.thread_store import Exchange, StoredThreads
    from brain.chat.turns import CorrectionKind, RecordRef
    from brain.core.entitlement import Capability
    from brain.gate.context import Channel
    from brain.knowledge.document_tools import KNOWLEDGE_ENTITY
    from brain.thread_routes import CorrectionAsked, correct_my_thread

    found, _ = await _found(h, person, word)
    if not found.records:
        raise CheckFailedError("a reader of acceptance_a could not find the document to ask about")
    cited = RecordRef(
        entity=KNOWLEDGE_ENTITY,
        record_id=str(found.records[0].id),
        required=Capability(value="read:knowledge.document"),
    )
    thread = await StoredThreads(h.sessions).record(
        person,
        thread_id=None,
        channel=Channel.CONSOLE,
        exchange=Exchange(
            question=f"What does it say about {word}?", answer="Three.", refs=(cited,)
        ),
        now=h.now,
    )
    # A minute after the answer, as a person reads it and then says it was wrong: a correction
    # dated before its answer is refused by `record_correction`.
    asked = await _asking(h, person, later=after)
    await correct_my_thread(
        _request(_app(h)),
        asked,
        thread,
        CorrectionAsked(kind=CorrectionKind.WRONG_FACT, right_answer=right),
    )
    return thread


async def _refused(call: Any) -> bool:
    from brain.core.errors import Absent

    try:
        await call
    except Absent:
        return True
    return False


@check(
    leaves=("M16.6.5", "M16.6.6", "M16.7.6"),
    sentence=(
        "Two readers of acceptance_a correct an answer to the same words: one candidate holds "
        "both, its steward is asked, neither reader nor acceptance_b's administrator may read or "
        "decide it, and the steward sees who will read the words and approves a new version "
        "answering with them, on the ledger. A rejection keeps its reason; the same answer, or "
        "another's conversation, proposes nothing."
    ),
)
async def a_correction_is_held_grouped_and_decided_as_a_new_version(h: Harness) -> None:
    from brain.candidate_routes import (
        CorrectionDecisionAsked,
        correction,
        corrections,
        decide_correction,
    )
    from brain.knowledge.lifecycle import TaskKind
    from brain.knowledge.search import KNOWLEDGE_UPLOAD

    await h.found_departments()
    steward, first, second, other = (
        h.principal(A, "steward"),
        h.principal(A, "first"),
        h.principal(A, "second_admin"),
        h.principal(B, "admin"),
    )
    await h.person(steward, department=A, grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value))
    # The second corrector administers acceptance_a's knowledge, so they could decide any other
    # correction of the document, and the four-eyes rule alone stops them deciding this one.
    await h.person(first, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(second, department=A, grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value))
    await h.person(other, department=B, grants=_in(B, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value))
    word, fix_word = h.word(), h.word()
    item_id = await _added(h, steward, word)
    right = f"The handover takes {fix_word} working days."

    await _corrected(h, first, word, right)
    # Later, so the two proposals are told apart by everything but the fix itself.
    await _corrected(h, second, word, right.upper(), after=2 * CORRECTED_AFTER)
    request = _request(_app(h))
    stewarding = await _asking(h, steward)

    listed = (await corrections(request, stewarding)).items
    mine = [one for one in listed if one.item_id == item_id]
    if not mine:
        raise CheckFailedError(NOT_HELD)
    if len(mine) != 1 or mine[0].instances != 2:
        raise CheckFailedError(NOT_GROUPED)
    candidate = mine[0].candidate_id
    tasks = await _tasks(h, await _as(h, steward))
    if not any(
        task.kind is TaskKind.CORRECTION_PROPOSED and task.item_id == item_id for task, _ in tasks
    ):
        raise CheckFailedError(NOT_ASKED)

    for nobody in (first, second, other):
        asked = await _asking(h, nobody)
        decision = CorrectionDecisionAsked(approve=True, review_by=h.now + REVIEW_AHEAD)
        if not (
            await _refused(correction(request, asked, candidate))
            and await _refused(decide_correction(request, asked, candidate, decision))
        ):
            raise CheckFailedError(SHOWN_TO_ITS_PROPOSER)

    review = await correction(request, stewarding, candidate)
    if review.words != right or review.audience != f"Everyone in {A} will see these words.":
        raise CheckFailedError(NO_AUDIENCE)

    approved = await decide_correction(
        request,
        stewarding,
        candidate,
        CorrectionDecisionAsked(approve=True, review_by=h.now + REVIEW_AHEAD),
    )
    applied = getattr(approved, "applied_item_id", None)
    found, kept = await _found(h, first, fix_word)
    ledger = await h.execute(
        text("SELECT actor_id, details FROM obs.audit_entry WHERE subject = :subject").bindparams(
            subject=f"setting:knowledge_candidate.{candidate}"
        )
    )
    entries = [
        str(actor) for actor, details in ledger.all() if dict(details).get("change") == "approved"
    ]

    if (
        not applied
        or not found.records
        or any(one.document_id != applied for one in found.records)
        or not any(fix_word in str(one.get("document", "")) for one in kept)
        or list(entries) != [steward]
        or not await _refused(correction(request, stewarding, candidate))
    ):
        raise CheckFailedError(NOT_APPLIED)

    other_word = h.word()
    second_item = await _added(h, steward, other_word)
    thread = await _corrected(h, first, other_word, f"It is {h.word()}.")
    pending = [
        one for one in (await corrections(request, stewarding)).items if one.item_id == second_item
    ]
    if len(pending) != 1:
        raise CheckFailedError(NOT_HELD)
    rejected = await decide_correction(
        request,
        stewarding,
        pending[0].candidate_id,
        CorrectionDecisionAsked(approve=False, reason="The document is already right."),
    )
    from brain.chat.turns import CorrectionKind
    from brain.thread_routes import CorrectionAsked, correct_my_thread

    await correct_my_thread(
        request,
        await _asking(h, first, later=CORRECTED_AFTER),
        thread,
        CorrectionAsked(kind=CorrectionKind.WRONG_FACT, right_answer="It is something else."),
    )
    kept_reason = (
        await h.execute(
            text(
                "SELECT state, reason FROM know.learning_candidate WHERE candidate_id = :c"
            ).bindparams(c=pending[0].candidate_id)
        )
    ).one()
    again_listed = [
        one for one in (await corrections(request, stewarding)).items if one.item_id == second_item
    ]
    if (
        getattr(rejected, "state", None) != "rejected"
        or tuple(kept_reason) != ("rejected", "The document is already right.")
        or again_listed
    ):
        raise CheckFailedError(NOT_REJECTED)

    # The one write function in the database refuses a proposal from a conversation that is not
    # the proposer's own, even from a reader of the cited document: the second corrector reads
    # it, and borrows the first's conversation.
    from brain.chat.turns import Correction, RecordRef
    from brain.core.entitlement import Capability
    from brain.knowledge.candidate_store import propose
    from brain.knowledge.document_tools import KNOWLEDGE_ENTITY
    from brain.knowledge.row_store import SessionRowSource

    found, _ = await _found(h, second, other_word)
    if not found.records:
        raise CheckFailedError(NOT_HELD)
    borrowing = await _asking(h, second, later=CORRECTED_AFTER)
    borrowed = await propose(
        h.sessions,
        SessionRowSource(h.sessions),
        correction=Correction(
            answer_at=h.now,
            at=borrowing.now,
            principal_id=second,
            kind=CorrectionKind.WRONG_FACT,
            refs=(
                RecordRef(
                    entity=KNOWLEDGE_ENTITY,
                    record_id=str(found.records[0].id),
                    required=Capability(value="read:knowledge.document"),
                ),
            ),
        ),
        thread_id=thread,
        words=f"It is {h.word()}.",
        reach=borrowing.reach,
        now=borrowing.now,
        trace_id="acceptance.corrections",
    )
    if borrowed is not None:
        raise CheckFailedError(NOT_ONE_S_OWN)
