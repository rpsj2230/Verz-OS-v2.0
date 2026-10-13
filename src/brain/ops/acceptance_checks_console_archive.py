"""Install acceptance check for archiving a document from the Knowledge page.

The check adds a document as a steward of acceptance_a and then does what the page's Archive does,
through the route's own acts (`brain.ops.acceptance_checks_lifecycle._acted_on` over
`brain.knowledge.lifecycle_store.record_archive`, which is the call `0216`'s `know.archive_item`
answers). **A person who may only read it, and a person of another department, are refused in the
words a document that is not there gets**, so the check holds the refusal beside the success and a
route that archived for everybody fails it. Afterwards the document is off the live items, a text
search finds nothing of it and answers as it answers for a word nobody wrote, its text stays on
file, its history ends with the archived step naming nobody, and a second press finds nothing to
archive.

Every row written is in the check's rolled-back transaction, for reserved people of acceptance_a
and acceptance_b. Nothing is embedded and nothing is queued, as `acceptance_checks_lifecycle`
argues for every lifecycle check.

Task ids: M27.15.40
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _ledger
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from brain.knowledge.lifecycle import StoredItem

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1380

A, B = RESERVED_DEPARTMENTS


@check(
    leaves=("M27.15.40",),
    sentence=(
        "A steward in acceptance_a archives their document: a plain reader and a reader elsewhere "
        "are refused, the document leaves the live items, a text search finds nothing of it, its "
        "text stays on file, its history ends with the archived step and the ledger names its "
        "steward, and a second archive finds nothing to archive."
    ),
)
async def a_document_is_archived_and_nothing_answers_from_it_afterwards(h: Harness) -> None:
    from brain.knowledge.lifecycle import HistoryEvent, event_of
    from brain.knowledge.lifecycle_store import item_subject, passages, record_archive
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.ops.acceptance_checks_lifecycle import (
        _acted_on,
        _added,
        _answered,
        _as,
        _in_transaction,
        _live,
        _silent,
    )

    await h.found_departments()
    steward, member, elsewhere = (
        h.principal(A, "steward"),
        h.principal(A, "member"),
        h.principal(B, "member"),
    )
    await h.person(steward, department=A, grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value))
    await h.person(member, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(elsewhere, department=B, grants=_in(B, *KNOWLEDGE_READS))
    word = h.word()
    document = await _added(h, steward, word)
    stewarding, reading = await _as(h, steward), await _as(h, member)

    async def archive(session: AsyncSession, item: StoredItem) -> None:
        await record_archive(session, item)

    for refused_by in (reading, await _as(h, elsewhere)):
        if await _acted_on(h, refused_by, document, archive) is not None:
            raise CheckFailedError("somebody who neither stewards nor administers it archived it")
    if await _live(h, stewarding, document) is None or not await _answered(
        h, member, word, document
    ):
        raise CheckFailedError("a refused archive moved the document or stopped it answering")

    if await _acted_on(h, stewarding, document, archive) is None:
        raise CheckFailedError("the steward could not archive their own document")
    if await _live(h, stewarding, document) is not None:
        raise CheckFailedError("an archived document was still among the live items")
    if not await _silent(h, member, word):
        raise CheckFailedError("a text search still answered from the archived document")

    async def kept(session: AsyncSession) -> int:
        return sum(1 for one in await passages(session, document) if word in one.body)

    if not await _in_transaction(h, stewarding, kept):
        raise CheckFailedError("the archived document's text was not kept on file")
    steps = [
        (actor, event_of(details))
        for actor, details in await _ledger(h, item_subject(document))
        if event_of(details) is HistoryEvent.ARCHIVED
    ]
    if steps != [(steward, HistoryEvent.ARCHIVED)]:
        raise CheckFailedError("the archive was not in the ledger once, naming its steward")
    if await _acted_on(h, stewarding, document, archive) is not None:
        raise CheckFailedError("a document already archived was archived again")
