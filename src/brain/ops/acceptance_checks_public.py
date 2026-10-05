"""The install acceptance check for public knowledge: a visitor reads what an administrator marked
public and nothing else, the marking names who made it, and a department's administrator decides
only for their own department.

Two reserved departments, founded by the harness, and two administrators: `a`'s holds
`approve:knowledge.public` over `acceptance_a` and adds two documents there, each holding a word
nothing else on the install has; `b`'s reads both departments and holds the same decision over
`acceptance_b` alone. Everything is written inside the check's transaction and rolled back with it,
so no document of the install's is read or marked and no visitor is ever shown anything.

**The acts are the route's sequence, not a second copy of its rules**
(`acceptance_checks_lifecycle.A_CHECK_IS_THE_ROUTE_S_SEQUENCE_AND_NOT_A_SECOND_COPY_OF_ITS_RULES`):
the person's authority from their admitted reach and the live registry, the document held under
their reach, `brain.knowledge.public.marking_refusal`, then `public_store.record_marking` in a
transaction attributed to them. The visitor's question is `document_tools.public_searcher`, the
search the widget's route runs, and the answer is the route's own `answer_of`.

**What the check proves.** That `b`'s administrator, who can see `a`'s document, is refused its
marking in the rule's sentence and the row is untouched; that `a`'s marks it, the row names them,
and the ledger's entry names them and says it was made public; that a question about the marked
word is answered from it, while one about the unmarked word is answered exactly as a question about
nothing at all; that the database's own wall, asked as `brain_public` with no predicate, returns the
marked document's passages and item and nothing of the other; and that unmarking is recorded the
other way round and the marked word is then not found.

**What it does not prove**: the website's own widget calling the route across the internet, which
needs the install's `widget_origins` to name a site and is its owner's to set; the route itself is
held by `tests/unit/test_widget_routes.py`.

Task ids: M10.7.2
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from brain.core.scope import Clause, Op, Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _ledger, _upload
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from brain.core.entitlement import EntitlementSet
    from brain.knowledge.lifecycle import Authority

#: Where this module's checks stand on the Install page, after the widget's session check.
CHECK_ORDER: Final = 265

A, B = RESERVED_DEPARTMENTS

#: What `b`'s administrator reads: both departments, in one grant so the two do not intersect.
BOTH: Final = Scope(clauses=(Clause(field="department", op=Op.IN, value=(A, B)),))

#: The file name every document the check adds arrives under.
FILE_NAME: Final = "Acceptance public.md"


async def _authority(h: Harness, principal_id: str) -> tuple[EntitlementSet, Authority]:
    """`authority_of`: the reach through the one resolver, judged against the live registry."""
    from brain.knowledge.lifecycle import authority_for
    from brain.knowledge_routes import live_departments

    reach = await h.reach(principal_id)
    registry = await live_departments(h.sessions)
    return reach, authority_for(reach, departments=registry, now=h.now)


async def _as_person[T](
    h: Harness, principal_id: str, work: Callable[[AsyncSession], Awaitable[T]]
) -> T:
    """`in_transaction`, attributed: one transaction told who is acting, attributed to them."""
    from brain.knowledge.lifecycle_store import as_person
    from brain.tables.audit import attributed_to

    reach, authority = await _authority(h, principal_id)
    async with h.sessions() as session, session.begin():
        for statement in attributed_to(
            actor_id=principal_id,
            ent_hash=reach.ent_hash(),
            trace_id=h.trace_id,
        ):
            await session.execute(statement)
        await as_person(session, authority)
        return await work(session)


async def _marked(h: Harness, principal_id: str, item_id: str, *, public: bool) -> str | None:
    """The marking route's act: None when it was taken, else the sentence it was refused with."""
    from brain.knowledge.lifecycle_store import held_item
    from brain.knowledge.public import marking_refusal
    from brain.knowledge.public_store import marking_of, record_marking

    reach, authority = await _authority(h, principal_id)

    async def act(session: AsyncSession) -> str | None:
        item = await held_item(session, item_id)
        if item is None or not authority.may_see(item):
            return "the document was not one this person may see"
        marking = await marking_of(session, item_id)
        if marking is None:
            return "the document's marking could not be read at this person's reach"
        says = marking_refusal(item, marker=reach, now=h.now, public=public)
        if says is not None:
            return says
        await record_marking(session, item_id, public=public, by=principal_id, at=h.now)
        return None

    return await _as_person(h, principal_id, act)


async def _added(h: Harness, steward: str, word: str) -> str:
    from brain.knowledge.ingest import MediaType, ParseFailure
    from brain.ops.acceptance_documents import a_markdown_document

    read = await _upload(
        h,
        steward,
        filename=FILE_NAME,
        declared=MediaType.MARKDOWN.value,
        body=a_markdown_document("Acceptance public", f"This document says {word}."),
    )
    if isinstance(read, ParseFailure):
        raise CheckFailedError("a well-formed Markdown document could not be added")
    return str(read.item.item_id)


async def _walled(h: Harness, item_ids: tuple[str, ...]) -> tuple[set[str], set[str]]:
    """What `brain_public` reads of these documents with no predicate: passages' and items' ids."""
    from brain.knowledge.search import SET_PUBLIC_ROLE

    async with h.sessions() as session:
        await session.execute(text(SET_PUBLIC_ROLE))
        chunks = await session.execute(
            text("SELECT DISTINCT document_id FROM know.chunk WHERE document_id = ANY(:ids)"),
            {"ids": list(item_ids)},
        )
        found = {str(one) for one in chunks.scalars()}
        items = await session.execute(
            text("SELECT item_id FROM know.item WHERE item_id = ANY(:ids)"), {"ids": list(item_ids)}
        )
        return found, {str(one) for one in items.scalars()}


@check(
    leaves=("M10.7.2",),
    sentence=(
        "One of two documents marked public by its department's administrator: another "
        "department's administrator is refused, the marking and its ledger entry name who made "
        "it, a visitor finds the marked one and is told of the other what a question about "
        "nothing is told, the public role reads nothing else, and unmarking is recorded."
    ),
)
async def a_visitor_reads_only_what_an_administrator_marked_public(h: Harness) -> None:
    from brain.knowledge.document_tools import public_searcher
    from brain.knowledge.lifecycle_store import item_subject
    from brain.knowledge.public import OUTSIDE_YOUR_DEPARTMENT, PUBLIC_MARKING
    from brain.knowledge.row_store import SessionRowSource
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.widget_routes import answer_of

    await h.found_departments()
    ours, theirs = h.principal(A, "admin"), h.principal(B, "admin")
    await h.person(
        ours,
        department=A,
        grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value, PUBLIC_MARKING.value),
    )
    await h.person(
        theirs,
        department=B,
        grants=(*((one, BOTH) for one in KNOWLEDGE_READS), *_in(B, PUBLIC_MARKING.value)),
    )
    marked_word, kept_word = h.word(), h.word()
    marked, kept = await _added(h, ours, marked_word), await _added(h, ours, kept_word)

    if await _marked(h, theirs, marked, public=True) != OUTSIDE_YOUR_DEPARTMENT:
        raise CheckFailedError("another department's administrator was not refused the marking")
    if await _marked(h, ours, marked, public=True) is not None:
        raise CheckFailedError("a department's administrator could not mark its own document")
    row = (
        await h.execute(
            text("SELECT public_by, public_at FROM know.item WHERE item_id = :id").bindparams(
                id=marked
            )
        )
    ).one()
    if row[0] != ours or row[1] is None:
        raise CheckFailedError("the marking did not name the administrator who made it")
    entries = await _ledger(h, item_subject(marked))
    if not entries or entries[-1][0] != ours or entries[-1][1].get("public") is not True:
        raise CheckFailedError("the marking's ledger entry did not name its maker and say public")

    search = public_searcher(SessionRowSource(h.sessions))
    found = answer_of(await search(marked_word))
    if not found.passages or {one.document_id for one in found.passages} != {marked}:
        raise CheckFailedError("a visitor's question was not answered from the marked document")
    if answer_of(await search(kept_word)) != answer_of(await search(h.word())):
        raise CheckFailedError("a question about an unmarked document was told something")
    if await _walled(h, (marked, kept)) != ({marked}, {marked}):
        raise CheckFailedError("the public role read something that was not marked public")

    if await _marked(h, ours, marked, public=False) is not None:
        raise CheckFailedError("the administrator could not stop the document being public")
    entries = await _ledger(h, item_subject(marked))
    if entries[-1][0] != ours or entries[-1][1].get("public") is not False:
        raise CheckFailedError("unmarking was not recorded naming who did it")
    if answer_of(await search(marked_word)).passages:
        raise CheckFailedError("an unmarked document still answered a visitor")
