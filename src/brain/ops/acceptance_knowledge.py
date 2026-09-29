"""The install acceptance check for a document's whole life, walked as one person would walk it.

Every stage of a document's life has a check of its own already: a link fetched and found
(`brain.ops.acceptance_ingest`), a passage cited with its freshness and badge
(`brain.ops.acceptance_answers`), a newer version superseding the older and a review falling due
(`brain.ops.acceptance_checks_lifecycle`). M7.7.6 asks for something none of them is: the stages in
the order an administrator meets them, each one starting from what the stage before it left, so
that a stage which passes on a document built for it and fails on one the stage before produced is
found. That is the only thing this check adds, and it is why it is one flow and one leaf.

**It reuses every stage's own helpers and restates no rule.** The upload is the upload route's
sequence, the link the link route's, the hand-over and the verification the lifecycle routes', the
question `/answer`'s own function with the stand-in model, the newer version the new-version route's
and the review the worker's own re-verification run. A stage whose rules change changes here with
it, because nothing here is a second copy of them. See
`A_STAGE_S_OWN_CHECK_SAYS_WHICH_RULE_BROKE_AND_THIS_ONE_SAYS_THE_FLOW_DID`.

**The stages it cannot run are said, not skipped.** The question needs the stand-in model, so an
install keeping text on its own hardware does not run it, as it does not run any stand-in check;
the link needs the documentation domain to answer; the review needs the worker's login. Each of
those is a `CheckNotRunError` with the reason in words, raised before anything is written, so a
not-run row never hides a stage that ran and failed.

Task ids: M38.5.1
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _found, _in, _upload
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.gate.answer import Answered
    from brain.gate.provenance import Evidence

A, B = RESERVED_DEPARTMENTS

#: Why this check exists beside the checks of each stage, and why it fails in the flow's words.
A_STAGE_S_OWN_CHECK_SAYS_WHICH_RULE_BROKE_AND_THIS_ONE_SAYS_THE_FLOW_DID: Final = (
    "Each stage of a document's life is checked on its own, on a document built for that stage, "
    "and says which of its rules broke. This check walks one document through every stage in the "
    "order an administrator does, each from what the last one left, and fails naming the stage "
    "the flow stopped at. It restates no rule: a stage is the same helpers its own check calls."
)

#: The row the document's table holds, keyed by a word nothing else on the install holds.
TABLE: Final = "| Service | Turnaround |\n| --- | --- |\n| {key} | {value} |"

#: What the member asks. Every word a text search keeps is in the table's passage, the header's
#: included, so the passage is found by the question a person would ask of the table.
ASKED_OF_THE_TABLE: Final = "What is the turnaround for {key}?"


def a_document_holding_a_table(key: str, value: str) -> bytes:
    """The lifecycle checks' document, under their heading, holding one table and a sentence.

    Under `brain.ops.acceptance_checks_lifecycle.HEADING`, so a newer version is a version of the
    same document by the new-version route's own rule.
    """
    from brain.ops.acceptance_checks_lifecycle import HEADING
    from brain.ops.acceptance_documents import a_markdown_document

    table = TABLE.format(key=key, value=value)
    return a_markdown_document(HEADING, f"The turnaround for each service.\n\n{table}")


async def _cited(h: Harness, app: FastAPI, reader: str, question: str, n: int) -> Answered:
    """The question asked on Ask as `reader`, at the moment it is asked."""
    from brain.ops.acceptance_models import asked

    return await asked(h, app, reader, question, n, at=datetime.now(UTC))


def _documents(answered: Answered) -> tuple[Evidence, ...]:
    if answered.composed is None or answered.provenance is None:
        raise CheckFailedError("a question the document answers was not answered")
    return answered.provenance.documents


def _cites(answered: Answered, document_id: str, value: str) -> bool:
    """Whether the answer was shown the table's row and cites this document alone, live, with the
    verified badge, which is what the owner's sentence asks an answer to say."""
    from brain.gate.provenance import Freshness
    from brain.knowledge.item import VerificationState
    from brain.ops.acceptance_models import shown

    cited = _documents(answered)
    return (
        value in shown(answered)
        and bool(cited)
        and {one.view().get("document_id") for one in cited} == {document_id}
        and all(one.freshness.state is Freshness.LIVE for one in cited)
        and all(
            one.vouched_for and one.view()["badge_state"] == VerificationState.VERIFIED.value
            for one in cited
        )
    )


async def _linked(h: Harness, administrator: str, reader: str) -> str:
    """The link route's sequence for the documentation domain, as `administrator`, found by the
    reader by a phrase on the page. Not run when the domain does not answer."""
    from brain.knowledge.ingest import IngestRefused, ParseFailure
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.uploads import placement_for_upload, read_for_link, receive_page
    from brain.knowledge.visibility import Visibility
    from brain.knowledge_intake_routes import make_fetcher, make_resolver
    from brain.knowledge_routes import live_departments, may_add, reads_knowledge
    from brain.ops.acceptance_ingest import LINK_CHECKED, LINK_PHRASE, _stored

    try:
        page = await asyncio.to_thread(
            receive_page, LINK_CHECKED, fetcher=make_fetcher(), resolver=make_resolver()
        )
    except IngestRefused as refused:
        if "could not be fetched" in str(refused):
            raise CheckNotRunError(
                "this install could not reach the documentation domain, so the link stage of a "
                "document's life was not run"
            ) from None
        raise CheckFailedError("the documentation domain's page was refused at the door") from None
    reach = await h.reach(administrator)
    placement = placement_for_upload(
        Visibility.DEPARTMENT,
        department=A,
        owner_id=administrator,
        may_add=may_add(reach, await live_departments(h.sessions), h.now),
        reads_knowledge=reads_knowledge(reach, h.now),
    )
    read = await asyncio.to_thread(
        read_for_link,
        page,
        kind=KnowledgeKind.SOP,
        placement=placement,
        owner_id=administrator,
        taken_on=h.now.date(),
    )
    if isinstance(read, ParseFailure):
        raise CheckFailedError("the documentation domain's page could not be read")
    await _stored(h, administrator, read)
    item = str(read.item.item_id)
    _, kept = await _found(h, reader, LINK_PHRASE)
    if not any(one.get("document_id") == item for one in kept):
        raise CheckFailedError("the member did not find the linked page by a phrase on it")
    return item


@check(
    leaves=("M7.7.6",),
    sentence=(
        "An administrator of acceptance_a adds a document holding a table and a link, and hands "
        "it to a steward who verifies it; a member's question is answered citing the table's "
        "passage, live and verified; the steward's newer version supersedes it and the next "
        "answer cites only the newer; once its review date passes, the worker's run opens the "
        "steward's re-verification task."
    ),
)
async def a_document_is_added_answered_replaced_and_falls_due_for_review(h: Harness) -> None:
    from brain.knowledge.ingest import MediaType, ParseFailure
    from brain.knowledge.item import KnowledgeState
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.lifecycle import TaskKind
    from brain.ops.acceptance_answers import asking_with_a_stand_in
    from brain.ops.acceptance_checks_lifecycle import (
        FELL_DUE,
        FILE_NAME,
        REVIEW_AHEAD,
        VERIFIED_LONG_AGO,
        _as,
        _handed_over,
        _live,
        _new_version,
        _swept,
        _tasks,
        _verify,
    )
    from brain.ops.acceptance_models import pinned, shown
    from brain.ops.acceptance_routing import ANSWERS, step
    from brain.session import LOGIN_BYPASSES_ROW_SECURITY

    # Every stage this install cannot run is said before anything is written.
    if not (await h.execute(LOGIN_BYPASSES_ROW_SECURITY)).scalar_one():
        raise CheckNotRunError(
            "this login cannot run the worker's re-verification control, so a document's whole "
            "life was not walked; the worker's own run asks it"
        )
    s = await asking_with_a_stand_in(h)
    await pinned(h, (step(ANSWERS),))
    administrator, member = s.library, s.reader
    steward = h.principal(A, "steward")
    await h.person(steward, department=A, grants=_in(A, *KNOWLEDGE_READS))

    # 1. Added: a document holding a table, as an SOP, and a link.
    key, value = h.word(), h.word()
    read = await _upload(
        h,
        administrator,
        filename=FILE_NAME,
        declared=MediaType.MARKDOWN.value,
        body=a_document_holding_a_table(key, value),
        kind=KnowledgeKind.SOP,
    )
    if isinstance(read, ParseFailure):
        raise CheckFailedError("a Markdown document holding a table could not be added")
    document = str(read.item.item_id)
    if read.item.kind is not KnowledgeKind.SOP:
        raise CheckFailedError("the document was not kept as the kind it was added as")
    await _linked(h, administrator, member)

    # 2. Owned and dated: handed to a steward, who verifies it with a review date ahead.
    administering, stewarding = await _as(h, administrator), await _as(h, steward)
    handed = await _handed_over(h, administering, document, steward)
    if handed is None or handed.owner_id != steward:
        raise CheckFailedError("the administrator could not hand the document to its steward")
    ahead = h.now + REVIEW_AHEAD
    if await _verify(h, stewarding, document, review_by=ahead) is None:
        raise CheckFailedError("the steward the document was handed to could not verify it")

    # 3. Answered: citing the table's passage, live, with the verified badge.
    question = ASKED_OF_THE_TABLE.format(key=key)
    if not _cites(await _cited(h, s.app, member, question, 1), document, value):
        raise CheckFailedError(
            "the member's question was not answered citing the table's passage, live and verified"
        )

    # 4. Replaced: the steward's newer version supersedes it, and answers cite the newer alone.
    newer_value = h.word()
    newer = await _new_version(
        h,
        stewarding,
        document,
        body=a_document_holding_a_table(key, newer_value),
        review_by=ahead,
    )
    if newer is None:
        raise CheckFailedError("the steward could not add a newer version of the document")
    live = await _live(h, stewarding, newer)
    if live is None or live.supersedes != document or live.state is not KnowledgeState.PUBLISHED:
        raise CheckFailedError("the newer version did not replace the older as the live document")
    if await _verify(h, stewarding, newer, review_by=ahead) is None:
        raise CheckFailedError("the steward could not verify the newer version")
    again = await _cited(h, s.app, member, question, 2)
    if not _cites(again, newer, newer_value) or value in shown(again):
        raise CheckFailedError("the next answer did not cite the newer version alone")

    # 5. Fallen due: a verification whose review date has passed opens the steward's task.
    fell_due = h.now - FELL_DUE
    earlier = h.now - VERIFIED_LONG_AGO
    if await _verify(h, stewarding, newer, review_by=fell_due, at=earlier) is None:
        raise CheckFailedError("a verification recorded at an earlier moment was refused")
    if (await _swept(h)).switched_off:
        raise CheckNotRunError(
            "an administrator has switched the re-verification notice off on this install, so "
            "the last stage of a document's life records nothing to prove it by"
        )
    opened = [
        (one.kind, one.due_at) for one, _ in await _tasks(h, stewarding) if one.item_id == newer
    ]
    if opened != [(TaskKind.REVERIFY, fell_due)]:
        raise CheckFailedError(
            "the worker's run opened no re-verification task for the steward of a document past "
            "its review date"
        )
