"""Install acceptance check for a member adding a document with a review cycle, and retiring it.

A member of acceptance_a adds a document for themselves alone and asks, as the route does, to be
asked about it again in ninety days. They find it on their own list due at that date, a colleague
of the same department is shown nothing of it and is refused retiring it exactly as for a document
nobody added, and the member retires it with the knowledge archive route. It is then off their
list, a second retirement is the one refusal, and the colleague still finds nothing.

**A document added to the department is retired by the person who added it and by nobody who only
reads it.** The personal document is kept from a colleague by the database's row policy before the
route's own rule is asked, so a second document, added to the department where the colleague can
read it, is what holds the route's rule: they may see it and are refused retiring it in the same
words as for one that is not there.

**Retiring needs no new stored thing.** The archive route and the database function behind it
(`know.archive_item`, migration 0216) were built for the Knowledge page's administrators; what this
adds is the proof that a person who added a document for themselves is the person it lets act on
it. The note that retiring wanted an archive and a migration was written before that route was
read, and is replaced by this check.

**What this does not prove.** That a retired document stops being quoted in an answer: the archive
check of M27.15.40 holds the passages' side of that, and this check holds the person's.

**The rows are written by the check and rolled back with it.** Nothing reaches a source.

Task ids: M40.3.1.2
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Final

from sqlalchemy.exc import DBAPIError

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_people_signed_in import console
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1980

A, _ = RESERVED_DEPARTMENTS

#: The cycle the member asks for, in days.
CYCLE_DAYS: Final = 90

#: How far the stored date may differ from the one asked for, for a clock that is not the
#: database's.
CLOCK_SLACK: Final = timedelta(seconds=2)


async def _refusal(call: Any) -> bool:
    """Whether a route call was answered with the one refusal, `Absent`, and nothing else."""
    from brain.core.errors import Absent

    try:
        await call
    except Absent:
        return True
    return False


@check(
    leaves=("M40.3.1.2",),
    sentence=(
        "A member of acceptance_a who adds a document for themselves with a ninety-day review "
        "cycle finds it listed due on that date, retires it, and it leaves their list; a "
        "colleague is refused retiring it, and refused retiring a department's document the "
        "member added that they can read."
    ),
)
async def a_member_adds_a_document_with_a_review_cycle_and_retires_it(h: Harness) -> None:
    from brain.knowledge.ingest import MediaType, ParseFailure
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.knowledge.visibility import Visibility
    from brain.knowledge_lifecycle_routes import archive, looked_after
    from brain.member_library import review_date_for
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _upload
    from brain.ops.acceptance_checks_lifecycle import FILE_NAME, _body

    try:
        await h.found_departments()
        c = await console(h)
        member, colleague = h.principal(A, "cycle_member"), h.principal(A, "cycle_colleague")
        for one in (member, colleague):
            grants = _in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value)
            await h.person(one, department=A, grants=grants)
    except DBAPIError:
        raise CheckFailedError("the database refused the step that places the people") from None

    due = review_date_for(CYCLE_DAYS, now=h.now)
    try:
        read = await _upload(
            h,
            member,
            filename=FILE_NAME,
            declared=MediaType.MARKDOWN.value,
            body=_body(h.word()),
            level=Visibility.PERSONAL,
            review_by=due,
        )
    except DBAPIError:
        raise CheckFailedError("the database refused the step that adds the document") from None
    if isinstance(read, ParseFailure):
        raise CheckFailedError("a well-formed document for a member alone could not be added")
    item_id = str(read.item.item_id)

    async def listed(who: str) -> dict[str, Any]:
        with c.as_route():
            page = await looked_after(c.request(), await c.asked(who, strong=False))
        return {one.item_id: one for one in page.items}

    try:
        mine, theirs = await listed(member), await listed(colleague)
    except DBAPIError:
        raise CheckFailedError("the database refused the step that lists the documents") from None
    row = mine.get(item_id)
    if row is None or row.review_by is None:
        raise CheckFailedError("a member's document was not listed with the cycle they asked for")
    if abs(row.review_by - due) > CLOCK_SLACK or row.due:
        raise CheckFailedError("a document was listed due on a day other than the cycle asked for")
    if item_id in theirs:
        raise CheckFailedError("a colleague was shown a document added for a member alone")

    async def retired(who: str, which: str) -> bool:
        asked = await c.asked(who, strong=False)
        with c.as_route():
            return await _refusal(archive(c.request("POST"), asked, which))

    try:
        colleague_refused = await retired(colleague, item_id)
        stranger_refused = await retired(colleague, "acceptance_item_nobody_added")
    except DBAPIError:
        raise CheckFailedError("the database refused the step that tries a colleague") from None
    if not (colleague_refused and stranger_refused):
        raise CheckFailedError("a colleague could retire a document added for a member alone")

    try:
        owner_refused = await retired(member, item_id)
        left = await listed(member)
        again = await retired(member, item_id)
        still_hidden = await listed(colleague)
    except DBAPIError:
        raise CheckFailedError("the database refused the step that retires the document") from None
    if owner_refused:
        raise CheckFailedError("a member could not retire the document they added")
    if item_id in left:
        raise CheckFailedError("a retired document was still on its member's list")
    if not again:
        raise CheckFailedError("a document was retired twice")
    if item_id in still_hidden:
        raise CheckFailedError("a colleague was shown a document a member retired")

    try:
        shared = await _upload(
            h,
            member,
            filename=FILE_NAME,
            declared=MediaType.MARKDOWN.value,
            body=_body(h.word()),
            level=Visibility.DEPARTMENT,
            review_by=due,
        )
    except DBAPIError:
        raise CheckFailedError(
            "the database refused the step that adds a department's document"
        ) from None
    if isinstance(shared, ParseFailure):
        raise CheckFailedError("a well-formed document for the department could not be added")
    department_item = str(shared.item.item_id)
    from brain.ops.acceptance_checks_lifecycle import _as, _live

    try:
        reader_refused = await retired(colleague, department_item)
        author_retired = not await retired(member, department_item)
        still_live = await _live(h, await _as(h, member), department_item)
    except DBAPIError:
        raise CheckFailedError(
            "the database refused the step that retires a department's document"
        ) from None
    if not reader_refused:
        raise CheckFailedError("a colleague who only reads a department's document could retire it")
    if not author_retired or still_live is not None:
        raise CheckFailedError("a member could not retire the department's document they added")
