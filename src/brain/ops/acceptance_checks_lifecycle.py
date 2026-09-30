"""The install acceptance checks for a document's life: replaced, published, reviewed, solved.

Each check drives the functions `brain.knowledge_lifecycle_routes` calls, in the order it calls
them, against the install's own schema and data: `brain.knowledge.lifecycle`, `promotion` and
`solutions` decide, `brain.knowledge.lifecycle_store` writes, and `0120`'s policies, triggers and
functions do the rest, through the harness's sessions as the application role, so every row, task
and ledger entry is the install's and all of it is rolled back. The promotion is decided through
the Approvals route's own `decide_once` on `brain.gate.suspension_store.StoredSuspensions`, and the
review falls due through the worker's own `brain.knowledge.item_store.run_reverification`. See
`A_CHECK_IS_THE_ROUTE_S_SEQUENCE_AND_NOT_A_SECOND_COPY_OF_ITS_RULES`.

**Four checks, one per leaf, because each leaf's sentence is one flow.** A newer version and what
answers use afterwards (M7.4.5); a request for company scope, the card, and who may approve it
(M7.4.4); a review date passing, the worker's run and the task it opens (M7.4.6); a captured
solution, who may decide it and what it answers as once approved (M7.6.2). Rejected: one check
walking a document through all four, which would report one red row for four leaves and say
nothing about which of them broke.

**Every refusal a sentence implies is asked, and beside it the act that succeeds.** A reader who
neither stewards nor administers the document may not replace it, the file already on file is not
a new version, an unverified document is not put to the Approvals screen, the person who asked
cannot approve their own card, an approver in another department is not offered it, a review task
cannot be dismissed, a capturer cannot decide their own solution, and a waiting solution answers
nothing. A guard asked only for its refusal is satisfied by a product that refuses everything.

**A review is made due by recording a verification at an earlier moment, through the product.**
The owner's sentence needs a review date in the past, and waiting half a year is not a check. The
verification is `verification_for` and `record_verification`, the verification route's own two
calls, handed an earlier `at`, which the product admits because a review date is judged against the
verification it belongs to. Rejected: moving `review_by` with an UPDATE as the database owner, as
`tests/unit/test_knowledge_lifecycle_db.py` does, which writes past every policy and proves the
sweep over a row the product could never have written. See
`A_REVIEW_IS_MADE_DUE_BY_A_VERIFICATION_RECORDED_EARLIER`.

**The sweep runs as the worker's login, and on any other login it is not run.** The scheduled
control runs `run_reverification` in a session with no application role, as the login the worker
holds, because `know.items_for_review` and the outbox are read and written past the policies a
request runs under. The check sends RESET ROLE in its own savepoint to be that login, and says it
was not run when the login cannot read past a policy, which is the acceptance run started by hand
in the application container. See `THE_SWEEP_RUNS_AS_THE_WORKER_S_LOGIN_OR_IS_NOT_RUN`.

**The sweep reads every due document on the install, as the control does, and commits nothing.**
It cannot be pointed at the check's document alone without being a different sweep. What it records
for anybody else's document, the nag, its deliveries and the steward's task `0120` opens from it, is
written in the check's transaction and rolled back with it, so no subscriber is told and no real
steward sees a task. See `THE_SWEEP_READS_EVERY_DUE_DOCUMENT_AND_COMMITS_NOTHING`.

**Nothing is embedded and nothing is queued.** The new version and the approved solution are written
with no embedding revision, which is the install with no worker that M7.6.3 names and the way
`brain.ops.acceptance_checks` stores its uploads, and a check fails if the product hands back a job
to queue. See `NOTHING_A_LIFECYCLE_CHECK_WRITES_IS_EMBEDDED_OR_QUEUED`.

Task ids: M38.5.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from brain.ops.acceptance import (
    RESERVED_DEPARTMENTS,
    CheckFailedError,
    CheckNotRunError,
    check,
)
from brain.ops.acceptance_checks import KNOWLEDGE_READS, _found, _in, _ledger, _upload
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from brain.core.entitlement import EntitlementSet
    from brain.gate.leash import SuspendedAction
    from brain.knowledge.item_store import NagRun
    from brain.knowledge.lifecycle import Authority, StewardTask, StoredItem
    from brain.knowledge.lifecycle_store import StoredPassage
    from brain.knowledge.promotion import PromotionStatus
    from brain.knowledge.solutions import CapturedSolution

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 100

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------ written-down reasons
#: Why a check calls the route's functions rather than restating what they decide.
A_CHECK_IS_THE_ROUTE_S_SEQUENCE_AND_NOT_A_SECOND_COPY_OF_ITS_RULES: Final = (
    "Each act is the route's own functions in the route's order: the authority from the admitted "
    "reach and the live registry, the transaction told who is acting and attributed to them, the "
    "decision, then the write. A check that restated a rule would prove its own copy, and the "
    "install could break the route's with every check green."
)

#: How a review is made due without waiting for one.
A_REVIEW_IS_MADE_DUE_BY_A_VERIFICATION_RECORDED_EARLIER: Final = (
    "The steward's verification is recorded through verification_for and record_verification "
    "with an earlier moment and a review date that has since passed, which the product admits "
    "because a review date is judged against the verification it belongs to. No row is moved "
    "past a policy, so the sweep is proved over a row the product itself wrote."
)

#: Why the sweep is run as the login, and not run on any other.
THE_SWEEP_RUNS_AS_THE_WORKER_S_LOGIN_OR_IS_NOT_RUN: Final = (
    "The worker runs the re-verification control as its own login, with no application role, "
    "because the due documents and the outbox are read and written past the policies a request "
    "runs under. The check does the same in a savepoint of its transaction, and on a login that "
    "cannot read past a policy it says it was not run rather than proving a different sweep."
)

#: Why reading every due document is safe.
THE_SWEEP_READS_EVERY_DUE_DOCUMENT_AND_COMMITS_NOTHING: Final = (
    "The control reads every document due on the install and records a nag for each it may. "
    "Inside the check that happens in the check's transaction, so the nags, their deliveries and "
    "the tasks they open are rolled back with it: no subscriber is told and no steward is shown "
    "a task."
)

#: Why the writes carry no embedding revision.
NOTHING_A_LIFECYCLE_CHECK_WRITES_IS_EMBEDDED_OR_QUEUED: Final = (
    "A new version and an approved solution are written with no embedding revision, which is the "
    "install with no worker, so the product hands back no job and nothing is queued. The text "
    "path finds both, which is what answers use when there is no vector leg."
)

#: Why a database refusal of an approval fails the check rather than counting as a refusal.
AN_APPROVAL_THE_DATABASE_REFUSES_IS_A_FAULT_ON_THE_SCREEN: Final = (
    "0120's trigger on gate.suspension refuses an approval by the person who asked by raising, "
    "and the Approvals route answers a raise as a fault. The screen never offers the asker their "
    "own card, so the route refuses that approval before the database is asked; an approval that "
    "reaches the trigger's refusal is a card offered that could only fail, and the check fails."
)

#: What the promotion check says when the database, not the screen, refused an approval.
THE_DATABASE_REFUSED_AN_APPROVAL_THE_SCREEN_OFFERED: Final = (
    "the database refused an approval the Approvals screen let through, which the route answers "
    "as a fault"
)

#: Why the check approves a card whose document it moved first.
A_CARD_WHOSE_DOCUMENT_MOVED_IS_ANSWERED_AND_CLOSED: Final = (
    "0120's trigger refuses the approval of a promotion whose document moved after it was asked "
    "for, and until 2026-09-29 the Approvals route answered that as a fault and left the card to "
    "fail the next approver the same way. So the check asks for a second document, adds a newer "
    "version of it, and approves the card through the route's own decision: it must be answered "
    "that the request no longer applies, closed as rejected, and absent to a second press."
)

#: What the promotion check says when that card is not answered and closed.
A_MOVED_DOCUMENT_S_CARD_WAS_NOT_ANSWERED_AND_CLOSED: Final = (
    "approving a card whose document had a newer version since it was asked for was not answered "
    "that the request no longer applies and closed as rejected"
)

# ------------------------------------------------------------------------ the figures
#: How far ahead every review date the checks set lies, as a steward would set one. Past the
#: sweep's lead time, so a review this far ahead is one the worker's run does not ask about yet.
REVIEW_AHEAD: Final = timedelta(days=180)

#: When the verification that falls due was recorded, and how long ago its review date passed.
VERIFIED_LONG_AGO: Final = timedelta(days=400)
FELL_DUE: Final = timedelta(days=1)

#: The file name every document the checks add arrives under, as the upload header carries it.
FILE_NAME: Final = "Acceptance lifecycle.md"

#: The heading every document the checks add carries, so a newer version is of the same document.
HEADING: Final = "Acceptance lifecycle"

#: `0120`'s ledger subject prefix for a solution. Restated because only the migration holds it.
SOLUTION_SUBJECT_PREFIX: Final = "setting:knowledge_solution."

#: Why the checks ask for company scope, as the card shows it. Names no document and no person.
PROMOTION_REASON: Final = "An install acceptance check asks for this document to be company-wide"


# ------------------------------------------------------------------------ the helpers
@dataclass(frozen=True)
class _Person:
    """One reserved principal as a lifecycle route sees them: admitted reach and authority."""

    reach: EntitlementSet
    authority: Authority


async def _as(h: Harness, principal_id: str) -> _Person:
    """`authority_of`: the reach through the one resolver, judged against the live registry."""
    from brain.knowledge.lifecycle import authority_for
    from brain.knowledge_routes import live_departments

    reach = await h.reach(principal_id)
    registry = await live_departments(h.sessions)
    return _Person(reach, authority_for(reach, departments=registry, now=h.now))


async def _in_transaction[T](
    h: Harness,
    person: _Person,
    work: Callable[[AsyncSession], Awaitable[T]],
    *,
    attributed: bool = False,
) -> T:
    """`in_transaction`: one transaction told who is acting, attributed to them when it writes."""
    from brain.knowledge.lifecycle_store import as_person
    from brain.tables.audit import attributed_to

    async with h.sessions() as session, session.begin():
        if attributed:
            for statement in attributed_to(
                actor_id=person.reach.principal_id,
                ent_hash=person.reach.ent_hash(),
                trace_id=h.trace_id,
            ):
                await session.execute(statement)
        await as_person(session, person.authority)
        return await work(session)


def _body(word: str) -> bytes:
    """A Markdown document under the one heading, holding a word nothing else on the install has."""
    from brain.ops.acceptance_documents import a_markdown_document

    return a_markdown_document(HEADING, f"This version of the acceptance document says {word}.")


async def _added(h: Harness, steward: str, word: str) -> str:
    """A document added in acceptance_a by `steward` through the upload route's sequence."""
    from brain.knowledge.ingest import MediaType, ParseFailure

    read = await _upload(
        h, steward, filename=FILE_NAME, declared=MediaType.MARKDOWN.value, body=_body(word)
    )
    if isinstance(read, ParseFailure):
        raise CheckFailedError("a well-formed Markdown document could not be added to change")
    return str(read.item.item_id)


async def _live(h: Harness, person: _Person, item_id: str) -> StoredItem | None:
    """`live_item` at this person's reach: the document as a policy admits it to them, or None."""
    from brain.knowledge.lifecycle_store import live_item

    async def load(session: AsyncSession) -> StoredItem | None:
        return await live_item(session, item_id)

    return await _in_transaction(h, person, load)


async def _acted_on(
    h: Harness,
    person: _Person,
    item_id: str,
    act: Callable[[AsyncSession, StoredItem], Awaitable[None]],
) -> StoredItem | None:
    """The route's `_acted_on`: hold a live document this person may act on, act, read it back.

    None where the route answers absent. The lifecycle's own refusals are None as well: the route
    answers them in words, and a check only needs to know the act was not taken.
    """
    from brain.knowledge.lifecycle import LifecycleError
    from brain.knowledge.lifecycle_store import LifecycleStoreError, held_item, live_item

    async def work(session: AsyncSession) -> StoredItem | None:
        item = await held_item(session, item_id)
        if item is None or not person.authority.may_act(item):
            return None
        await act(session, item)
        return await live_item(session, item_id) or item

    try:
        return await _in_transaction(h, person, work, attributed=True)
    except (LifecycleError, LifecycleStoreError):
        return None


async def _handed_over(h: Harness, by: _Person, item_id: str, to: str) -> StoredItem | None:
    """The hand-over route's act (M7.7.2): the named person's authority read as it stands, the
    hand-over judged, then recorded. None where the route refuses."""
    from brain.knowledge.lifecycle import assert_may_hand_over, authority_for
    from brain.knowledge.lifecycle_store import as_person, record_steward
    from brain.knowledge_lifecycle_routes import entitlement_of
    from brain.knowledge_routes import live_departments

    registry = await live_departments(h.sessions)

    async def act(session: AsyncSession, item: StoredItem) -> None:
        theirs = await entitlement_of(session, to, h.now)
        await as_person(session, by.authority)
        named = authority_for(theirs, departments=registry, now=h.now)
        assert_may_hand_over(item, to=to, theirs=named)
        await record_steward(session, item, to=to)

    return await _acted_on(h, by, item_id, act)


async def _verify(
    h: Harness,
    person: _Person,
    item_id: str,
    *,
    review_by: datetime,
    at: datetime | None = None,
) -> StoredItem | None:
    """The verification route's act, by this person at `at`, which is now unless said otherwise.

    An earlier `at` is `A_REVIEW_IS_MADE_DUE_BY_A_VERIFICATION_RECORDED_EARLIER`, and nothing else.
    """
    from brain.knowledge.lifecycle import verification_for
    from brain.knowledge.lifecycle_store import record_verification

    moment = h.now if at is None else at

    async def act(session: AsyncSession, item: StoredItem) -> None:
        done = verification_for(
            item, by=person.authority.principal_id, at=moment, review_by=review_by
        )
        await record_verification(session, item, done)

    return await _acted_on(h, person, item_id, act)


async def _silent(h: Harness, reader: str, word: str) -> bool:
    """Whether a text search for `word` tells this reader what a search for nothing tells them."""
    found, _ = await _found(h, reader, word)
    nothing, _ = await _found(h, reader, h.word())
    return (found.records, found.truncated, found.source) == (
        nothing.records,
        nothing.truncated,
        nothing.source,
    )


async def _answered(h: Harness, reader: str, word: str, item_id: str) -> bool:
    """Whether a text search for `word` finds this document alone and lets the reader read it."""
    found, kept = await _found(h, reader, word)
    return (
        bool(found.records)
        and all(one.document_id == item_id for one in found.records)
        and any(word in str(one.get("document", "")) for one in kept)
    )


async def _tasks(h: Harness, person: _Person) -> list[tuple[StewardTask, str]]:
    """`my_tasks`: this person's open tasks, each with the title a task is shown under.

    A task about something the person no longer reaches is left out, as the route leaves it out.
    """
    from brain.knowledge.lifecycle import TaskKind
    from brain.knowledge.lifecycle_store import open_tasks, solution_titles, titles

    async def load(
        session: AsyncSession,
    ) -> tuple[tuple[StewardTask, ...], dict[str, str], dict[str, str]]:
        found = await open_tasks(session)
        solved = [one.item_id for one in found if one.kind is TaskKind.SOLUTION_DECIDED]
        documents = [one.item_id for one in found if one.kind is not TaskKind.SOLUTION_DECIDED]
        return found, await titles(session, documents), await solution_titles(session, solved)

    found, named, solutions_named = await _in_transaction(h, person, load)
    shown: list[tuple[StewardTask, str]] = []
    for one in found:
        title = (
            solutions_named.get(one.item_id)
            if one.kind is TaskKind.SOLUTION_DECIDED
            else named.get(one.item_id)
        )
        if title is not None:
            shown.append((one, title))
    return shown


def _no_revision() -> str | None:
    """The embedding revision the checks write under. See the module on nothing being queued."""
    from brain.knowledge.embed_policy import REVISION_SETTING, REVISION_UNSET, embedding_revision

    return embedding_revision({REVISION_SETTING: REVISION_UNSET})


# ------------------------------------------------------------ 1. a newer version (M7.4.5)
async def _new_version(
    h: Harness, person: _Person, item_id: str, *, body: bytes, review_by: datetime
) -> str | None:
    """The new-version route, in its order: the newer version's id, or None where it refuses."""
    from sqlalchemy.exc import DBAPIError

    from brain.knowledge.chunk_store import ChunkStoreError
    from brain.knowledge.ingest import (
        IngestRefused,
        MediaType,
        ParseFailure,
        admit_upload,
        ceiling_for,
    )
    from brain.knowledge.item import KnowledgeError, KnowledgeItem
    from brain.knowledge.kinds import KindError
    from brain.knowledge.lifecycle import LifecycleError, successor_place
    from brain.knowledge.lifecycle_store import (
        LifecycleStoreError,
        held_item,
        live_item,
        versions,
        write_version,
    )
    from brain.knowledge.uploads import ReceivedUpload, assert_safe_filename, text_path_type
    from brain.knowledge.visibility import VisibilityError
    from brain.knowledge_routes import read_one_at_a_time
    from brain.member_library import LibraryError, assert_replaceable

    async def load(session: AsyncSession) -> tuple[StoredItem | None, tuple[StoredItem, ...]]:
        return await live_item(session, item_id), await versions(session, item_id)

    predecessor, chain = await _in_transaction(h, person, load)
    if predecessor is None or not person.authority.may_act(predecessor):
        return None
    if review_by.tzinfo is None or review_by <= h.now:
        return None
    chosen = predecessor.kind
    if chosen is None:
        return None
    try:
        placement = successor_place(predecessor)
        assert_safe_filename(FILE_NAME)
        media_type = text_path_type(MediaType.MARKDOWN.value)
        if len(body) > ceiling_for(media_type):
            return None
        received = ReceivedUpload(
            upload=admit_upload(filename=FILE_NAME, declared_type=media_type.value, content=body),
            body=body,
        )
        read = await asyncio.to_thread(
            read_one_at_a_time,
            received,
            kind=chosen,
            placement=placement,
            owner_id=predecessor.owner_id,
        )
    except (LifecycleError, IngestRefused, KindError):
        return None
    if isinstance(read, ParseFailure):
        return None
    successor = KnowledgeItem.model_validate({**read.item.model_dump(), "review_by": review_by})
    if successor.item_id in {one.item_id for one in chain}:
        return None
    try:
        assert_replaceable(predecessor, successor)
    except (LibraryError, KnowledgeError, VisibilityError):
        return None
    revision = _no_revision()

    async def write(session: AsyncSession) -> object:
        again = await held_item(session, item_id)
        if again is None or again.owner_id != predecessor.owner_id:
            msg = "the document changed while its new version was being read"
            raise LifecycleStoreError(msg)
        return await write_version(
            session, predecessor, successor, blocks=read.blocks, revision=revision, now=h.now
        )

    try:
        job = await _in_transaction(h, person, write, attributed=True)
    except (LifecycleStoreError, ChunkStoreError, DBAPIError):
        return None
    if job is not None:
        raise CheckFailedError("a new version written with no embedding revision queued work")
    return successor.item_id


@check(
    leaves=("M7.4.5",),
    sentence=(
        "A steward in acceptance_a adds a newer version of their document: the older reads as "
        "superseded in the document's history and its text stays on file, a text search finds "
        "the newer's words and nothing of the older's, and the replacement is in the ledger; a "
        "plain reader, a reader elsewhere, the same file again and a review date not ahead are "
        "refused."
    ),
)
async def a_newer_version_supersedes_the_older_and_answers_use_the_newer(h: Harness) -> None:
    from brain.knowledge.item import KnowledgeState
    from brain.knowledge.lifecycle_store import item_subject, passages, versions
    from brain.knowledge.search import KNOWLEDGE_UPLOAD

    await h.found_departments()
    steward, member, elsewhere = (
        h.principal(A, "steward"),
        h.principal(A, "member"),
        h.principal(B, "member"),
    )
    await h.person(steward, department=A, grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value))
    await h.person(member, department=A, grants=_in(A, *KNOWLEDGE_READS))
    await h.person(elsewhere, department=B, grants=_in(B, *KNOWLEDGE_READS))
    old_word, new_word = h.word(), h.word()
    older = await _added(h, steward, old_word)
    stewarding, reading = await _as(h, steward), await _as(h, member)
    ahead = h.now + REVIEW_AHEAD

    for refused_by in (reading, await _as(h, elsewhere)):
        if await _new_version(h, refused_by, older, body=_body(new_word), review_by=ahead):
            raise CheckFailedError("somebody who neither stewards nor administers it replaced it")
    if await _new_version(h, stewarding, older, body=_body(old_word), review_by=ahead):
        raise CheckFailedError("the file already on file was accepted as its own newer version")
    if await _new_version(h, stewarding, older, body=_body(new_word), review_by=h.now):
        raise CheckFailedError("a new version whose review date is not ahead was accepted")
    newer = await _new_version(h, stewarding, older, body=_body(new_word), review_by=ahead)
    if newer is None:
        raise CheckFailedError("the steward could not add a newer version of their document")

    async def history(
        session: AsyncSession,
    ) -> tuple[tuple[StoredItem, ...], tuple[StoredPassage, ...]]:
        return await versions(session, newer), await passages(session, older)

    chain, older_text = await _in_transaction(h, reading, history)
    states = {one.item_id: one.state for one in chain if reading.authority.may_see(one)}
    if states.get(older) is not KnowledgeState.SUPERSEDED:
        raise CheckFailedError("the older version was not shown superseded by the newer one")
    # A set and not an order: the history orders by when a version was added, and inside one
    # check's transaction both were added at the same instant.
    if states.get(newer) is not KnowledgeState.PUBLISHED or set(states) != {older, newer}:
        raise CheckFailedError("the document's history did not show the newer beside the older")
    live = await _live(h, reading, newer)
    if live is None or live.supersedes != older or await _live(h, reading, older) is not None:
        raise CheckFailedError("the newer version did not replace the older as the live document")
    if not await _answered(h, member, new_word, newer):
        raise CheckFailedError("a text search did not answer from the newer version")
    if not await _silent(h, member, old_word):
        raise CheckFailedError("a text search still answered from the superseded version")
    if not any(old_word in one.body for one in older_text):
        raise CheckFailedError("the superseded version's text was not kept on file")
    replaced = [
        actor
        for actor, details in await _ledger(h, item_subject(older))
        if "state" in str(details.get("changed", "")).split(",")
        and details.get("state") == KnowledgeState.SUPERSEDED.value
    ]
    if replaced != [steward]:
        raise CheckFailedError("the replacement was not in the ledger naming its steward")
    if await _new_version(h, stewarding, older, body=_body(h.word()), review_by=ahead):
        raise CheckFailedError("a superseded version was given another newer version")


# ------------------------------------------------------- 2. company scope (M7.4.4)
async def _propose(h: Harness, person: _Person, item_id: str) -> str | None:
    """The promotion route, in its order: the card's id, or None where the route refuses."""
    from brain.knowledge.lifecycle import LifecycleError, assert_may_propose
    from brain.knowledge.lifecycle_store import live_item, promotions_asked, put_promotion
    from brain.knowledge.promotion import (
        PromotionError,
        PromotionStatus,
        raise_promotion,
        status_of,
    )
    from brain.knowledge.visibility import Visibility, VisibilityError, propose_promotion
    from brain.member_library import (
        LibraryError,
        PromotionRequest,
        promotion_tier,
        request_promotion,
    )

    async def load(session: AsyncSession) -> tuple[StoredItem | None, SuspendedAction | None]:
        item = await live_item(session, item_id)
        asked_for = await promotions_asked(session, reach=person.reach, now=h.now)
        return item, asked_for.get(item_id)

    item, earlier = await _in_transaction(h, person, load)
    if item is None or not person.authority.may_act(item):
        return None
    if earlier is not None and status_of(earlier, now=h.now) is PromotionStatus.WAITING:
        return None
    review_by = h.now + REVIEW_AHEAD
    try:
        assert_may_propose(item)
        if person.authority.stewards(item):
            asking = request_promotion(
                item,
                proposer_id=person.authority.principal_id,
                review_by=review_by,
                reason=PROMOTION_REASON,
                now=h.now,
            )
        else:
            asking = PromotionRequest(
                proposal=propose_promotion(
                    item_id=item.item_id,
                    from_level=item.visibility.level,
                    to_level=Visibility.COMPANY,
                    proposer_id=person.authority.principal_id,
                    owner_id=item.owner_id,
                    review_by=review_by,
                    reason=PROMOTION_REASON,
                    now=h.now,
                ),
                tier=promotion_tier(),
            )
        suspension = raise_promotion(
            asking.proposal,
            title=item.title,
            kind=item.kind,
            department=item.visibility.department,
            reach=person.reach,
            trace_id=h.trace_id,
            now=h.now,
        )
    except (LifecycleError, VisibilityError, LibraryError, PromotionError):
        return None

    async def write(session: AsyncSession) -> None:
        await put_promotion(session, suspension, reach=person.reach, now=h.now)

    await _in_transaction(h, person, write, attributed=True)
    return suspension.id


async def _status(h: Harness, person: _Person, item_id: str) -> PromotionStatus | None:
    """Where this person's own promotion of the document has got to, as their page reads it."""
    from brain.knowledge.lifecycle_store import promotions_asked
    from brain.knowledge.promotion import status_of

    async def load(session: AsyncSession) -> SuspendedAction | None:
        return (await promotions_asked(session, reach=person.reach, now=h.now)).get(item_id)

    mine = await _in_transaction(h, person, load)
    return None if mine is None else status_of(mine, now=h.now)


async def _offered(h: Harness, person: _Person, suspension_id: str) -> bool:
    """Whether the Approvals queue this person reads carries the card, as `GET /approvals` does."""
    from brain.approval_routes import queue
    from brain.gate.suspension_store import StoredSuspensions

    source = StoredSuspensions(h.sessions).reading_as(person.reach, h.now)
    shown = queue(await source.open_suspensions(), person.reach, h.now)
    return any(one.suspension_id == suspension_id for one in shown.items)


async def _decided(h: Harness, person: _Person, suspension_id: str) -> str:
    """The Approvals decision route approving the card as this person, through the route's own
    `take_decision`: empty when it was written, else the words the route refused it in.

    The database refusing the approval in a way the route answers as a fault fails the check: see
    `AN_APPROVAL_THE_DATABASE_REFUSES_IS_A_FAULT_ON_THE_SCREEN`.
    """
    from brain.approval_routes import DecidableVerdict, DecisionAsked, take_decision
    from brain.core.errors import Absent, Failed
    from brain.gate.suspension_store import StoredSuspensions

    try:
        await take_decision(
            StoredSuspensions(h.sessions),
            suspension_id,
            person.reach,
            DecisionAsked(verdict=DecidableVerdict.APPROVED),
            trace_id=h.trace_id,
            now=h.now,
        )
    except Absent as refused:
        return refused.public_message
    except Failed:
        raise CheckFailedError(THE_DATABASE_REFUSED_AN_APPROVAL_THE_SCREEN_OFFERED) from None
    return ""


async def _approve(h: Harness, person: _Person, suspension_id: str) -> bool:
    """Whether the decision route wrote this person's approval of the card."""
    return await _decided(h, person, suspension_id) == ""


async def _moved_card_is_answered_and_closed(
    h: Harness, asking: _Person, approving: _Person, steward: str
) -> None:
    """See `A_CARD_WHOSE_DOCUMENT_MOVED_IS_ANSWERED_AND_CLOSED`."""
    from brain.approval_routes import A_REQUEST_THAT_NO_LONGER_APPLIES
    from brain.core.errors import Absent
    from brain.knowledge.promotion import PromotionStatus

    moving = await _added(h, steward, h.word())
    if await _verify(h, asking, moving, review_by=h.now + REVIEW_AHEAD) is None:
        raise CheckFailedError("the steward could not verify their own document")
    card = await _propose(h, asking, moving)
    if card is None:
        raise CheckFailedError("a steward's verified document could not be asked for company-wide")
    newer = await _new_version(
        h, asking, moving, body=_body(h.word()), review_by=h.now + REVIEW_AHEAD
    )
    if newer is None:
        raise CheckFailedError("the steward could not add a newer version of their own document")
    if (
        await _decided(h, approving, card) != A_REQUEST_THAT_NO_LONGER_APPLIES
        or await _decided(h, approving, card) != Absent.public_message
        or await _status(h, asking, moving) is not PromotionStatus.REJECTED
    ):
        raise CheckFailedError(A_MOVED_DOCUMENT_S_CARD_WAS_NOT_ANSWERED_AND_CLOSED)


@check(
    leaves=("M7.4.4",),
    sentence=(
        "A steward in acceptance_a asks for their verified document to be company-wide: it waits "
        "on the Approvals screen of another holder of approve:knowledge.visibility there, never "
        "the asker's; it stays in its department until that holder approves, then is readable "
        "from acceptance_b. Unverified, it is not asked; given a newer version once asked, its "
        "approval is answered that it no longer applies."
    ),
)
async def a_company_wide_request_waits_until_another_approver_approves_it(h: Harness) -> None:
    from brain.audit.record import subject
    from brain.knowledge.lifecycle import Outcome, TaskKind
    from brain.knowledge.lifecycle_store import item_subject
    from brain.knowledge.promotion import PromotionStatus
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.knowledge.visibility import PROMOTION_CAPABILITY, Visibility

    await h.found_departments()
    steward, approver, elsewhere, reader = (
        h.principal(A, "steward"),
        h.principal(A, "approver"),
        h.principal(B, "approver"),
        h.principal(B, "member"),
    )
    approves = PROMOTION_CAPABILITY.value
    await h.person(
        steward,
        department=A,
        grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value, approves),
    )
    await h.person(approver, department=A, grants=_in(A, approves))
    await h.person(elsewhere, department=B, grants=_in(B, approves))
    await h.person(reader, department=B, grants=_in(B, *KNOWLEDGE_READS))
    word = h.word()
    item = await _added(h, steward, word)
    asking, approving, outside, reading = (
        await _as(h, steward),
        await _as(h, approver),
        await _as(h, elsewhere),
        await _as(h, reader),
    )

    if await _propose(h, asking, item) is not None:
        raise CheckFailedError("a document nobody had verified was put to the Approvals screen")
    if await _verify(h, asking, item, review_by=h.now + REVIEW_AHEAD) is None:
        raise CheckFailedError("the steward could not verify their own document")
    card = await _propose(h, asking, item)
    if card is None:
        raise CheckFailedError("a steward's verified document could not be asked for company-wide")
    if await _propose(h, asking, item) is not None:
        raise CheckFailedError("a document already waiting was asked for a second time")
    if await _status(h, asking, item) is not PromotionStatus.WAITING:
        raise CheckFailedError("the steward's page did not say their promotion was waiting")
    if not await _silent(h, reader, word):
        raise CheckFailedError("a reader elsewhere was answered from a document still waiting")
    if not await _offered(h, approving, card):
        raise CheckFailedError("the card was not on the Approvals screen of a holder where it sits")
    if await _offered(h, outside, card) or await _offered(h, reading, card):
        raise CheckFailedError("the card was offered to somebody who may not approve it")
    if await _offered(h, asking, card):
        raise CheckFailedError("the person who asked was offered their own card to approve")

    if await _approve(h, asking, card):
        raise CheckFailedError("the person who asked approved their own promotion")
    if await _approve(h, outside, card):
        raise CheckFailedError("a holder of the approval in another department decided the card")
    held = await _live(h, asking, item)
    if held is None or held.visibility.level is not Visibility.DEPARTMENT:
        raise CheckFailedError("the document left its department before another holder approved")
    if await _status(h, asking, item) is not PromotionStatus.WAITING:
        raise CheckFailedError("a refused approval moved the card out of waiting")

    if not await _approve(h, approving, card):
        raise CheckFailedError("another holder of the approval could not approve the card")
    widened = await _live(h, reading, item)
    if widened is None or widened.visibility.level is not Visibility.COMPANY:
        raise CheckFailedError("an approved promotion did not make the document company-wide")
    found, _ = await _found(h, reader, word)
    if not any(one.document_id == item for one in found.records):
        raise CheckFailedError("a reader elsewhere did not find the document once it was approved")
    if await _status(h, asking, item) is not PromotionStatus.APPROVED:
        raise CheckFailedError("the steward's page did not say their promotion was approved")
    told = [one for one, _ in await _tasks(h, asking) if one.item_id == item]
    if [(one.kind, one.outcome) for one in told] != [
        (TaskKind.PROMOTION_DECIDED, Outcome.APPROVED)
    ]:
        raise CheckFailedError("the steward was not told their promotion was approved")
    decisions = [
        (actor, details.get("verdict"))
        for actor, details in await _ledger(h, subject("leash", card))
    ]
    applied = [
        actor
        for actor, details in await _ledger(h, item_subject(item))
        if details.get("level") == Visibility.COMPANY.value
    ]
    if decisions != [(approver, "approved")] or applied != [approver]:
        raise CheckFailedError("the approval and the widening were not in the ledger by approver")
    await _moved_card_is_answered_and_closed(h, asking, approving, steward)


# ------------------------------------------------- 3. a review falling due (M7.4.6)
async def _swept(h: Harness) -> NagRun:
    """The worker's re-verification control, in a savepoint of the check's transaction.

    A plain session on the check's connection with the role reset to the login, which is how the
    schedule runs it. See `THE_SWEEP_RUNS_AS_THE_WORKER_S_LOGIN_OR_IS_NOT_RUN` and
    `THE_SWEEP_READS_EVERY_DUE_DOCUMENT_AND_COMMITS_NOTHING`.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from brain.knowledge.item_store import run_reverification

    async with (
        AsyncSession(
            bind=h.connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
            autoflush=False,
        ) as session,
        session.begin(),
    ):
        await session.execute(text("RESET ROLE"))
        return await run_reverification(session, now=h.now)


async def _dismissed(h: Harness, person: _Person, task_id: str) -> bool:
    """The task route closing one task by saying it was read. A review is not one it closes."""
    from brain.knowledge.lifecycle import DISMISSABLE
    from brain.knowledge.lifecycle_store import close_task

    async def work(session: AsyncSession) -> bool:
        return await close_task(session, task_id, kinds=DISMISSABLE)

    return await _in_transaction(h, person, work, attributed=True)


@check(
    leaves=("M7.4.6",),
    sentence=(
        "A document in acceptance_a verified with a review date ahead gets no task from the "
        "worker's re-verification run; once its review date has passed the run opens a review "
        "task on its steward's list and nobody else's, which cannot be dismissed, and verifying "
        "it again with a new date closes it and the next run opens nothing."
    ),
)
async def a_review_that_fell_due_opens_its_steward_s_task_until_verified(h: Harness) -> None:
    from brain.knowledge.lifecycle import TaskKind
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.session import LOGIN_BYPASSES_ROW_SECURITY

    if not (await h.execute(LOGIN_BYPASSES_ROW_SECURITY)).scalar_one():
        raise CheckNotRunError(
            "this login cannot run the worker's re-verification control, so it was not asked; "
            "the worker's own run asks it"
        )
    await h.found_departments()
    steward, member = h.principal(A, "steward"), h.principal(A, "member")
    await h.person(steward, department=A, grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value))
    await h.person(member, department=A, grants=_in(A, *KNOWLEDGE_READS))
    item = await _added(h, steward, h.word())
    stewarding, reading = await _as(h, steward), await _as(h, member)

    async def reviews(person: _Person) -> list[tuple[StewardTask, str]]:
        return [(one, title) for one, title in await _tasks(h, person) if one.item_id == item]

    if await _verify(h, stewarding, item, review_by=h.now + REVIEW_AHEAD) is None:
        raise CheckFailedError("the steward could not verify their own document")
    if (await _swept(h)).switched_off:
        raise CheckNotRunError(
            "an administrator has switched the re-verification notice off on this install, so "
            "its run records nothing to prove this by"
        )
    if await reviews(stewarding):
        raise CheckFailedError("the re-verification run opened a task for a review still ahead")

    # A_REVIEW_IS_MADE_DUE_BY_A_VERIFICATION_RECORDED_EARLIER.
    fell_due = h.now - FELL_DUE
    if await _verify(h, stewarding, item, review_by=fell_due, at=h.now - VERIFIED_LONG_AGO) is None:
        raise CheckFailedError("a verification recorded at an earlier moment was refused")
    await _swept(h)
    opened = await reviews(stewarding)
    if [(one.kind, one.due_at) for one, _ in opened] != [(TaskKind.REVERIFY, fell_due)]:
        raise CheckFailedError(
            "the re-verification run opened no task for the steward of a document past its "
            "review date"
        )
    if await reviews(reading):
        raise CheckFailedError("a review task was opened for somebody other than the steward")
    [(task, _)] = opened
    if await _dismissed(h, stewarding, task.task_id) or not await reviews(stewarding):
        raise CheckFailedError("a review task was closed by dismissing it rather than verifying")

    if await _verify(h, stewarding, item, review_by=h.now + REVIEW_AHEAD) is None:
        raise CheckFailedError("the steward could not verify their document again")
    if await reviews(stewarding):
        raise CheckFailedError("verifying the document again did not close its review task")
    await _swept(h)
    if await reviews(stewarding):
        raise CheckFailedError("the next re-verification run opened a task for a verified document")


# ---------------------------------------------------- 4. a captured solution (M7.6.2)
async def _capture(
    h: Harness, person: _Person, *, department: str, problem: str, answer: str
) -> CapturedSolution | None:
    """The capture route, in its order: the captured solution, or None where it refuses."""
    from brain.knowledge.lifecycle import LifecycleError
    from brain.knowledge.lifecycle_store import put_solution
    from brain.knowledge.solutions import SolutionNotOffered, capture

    try:
        solution = capture(
            problem=problem,
            answer=answer,
            department=department,
            conversation_ref="",
            by=person.authority,
            now=h.now,
        )
    except (SolutionNotOffered, LifecycleError):
        return None

    async def write(session: AsyncSession) -> None:
        await put_solution(session, solution)

    await _in_transaction(h, person, write, attributed=True)
    return solution


async def _approve_solution(
    h: Harness, person: _Person, solution_id: str
) -> CapturedSolution | None:
    """The decision route approving a solution, in its order: the decided solution, or None."""
    from brain.knowledge.chunk_store import ChunkStoreError
    from brain.knowledge.lifecycle import LifecycleError
    from brain.knowledge.lifecycle_store import (
        LifecycleStoreError,
        record_decision,
        solution_held,
        write_solution_document,
    )
    from brain.knowledge.solutions import (
        SolutionNotOffered,
        SolutionState,
        approved_item,
        decided,
        may_decide,
    )

    revision = _no_revision()

    async def work(session: AsyncSession) -> CapturedSolution | None:
        held = await solution_held(session, solution_id)
        if held is None or not may_decide(held, person.authority):
            return None
        item = approved_item(held, by=person.authority, review_by=h.now + REVIEW_AHEAD, now=h.now)
        job = await write_solution_document(session, item, revision=revision, now=h.now)
        if job is not None:
            raise CheckFailedError("an approved solution written with no revision queued work")
        moved = decided(held, by=person.authority, outcome=SolutionState.APPROVED, at=h.now)
        await record_decision(session, moved)
        return moved

    try:
        return await _in_transaction(h, person, work, attributed=True)
    except (SolutionNotOffered, LifecycleError, LifecycleStoreError, ChunkStoreError):
        return None


async def _solutions(
    h: Harness, person: _Person
) -> tuple[dict[str, CapturedSolution], dict[str, CapturedSolution]]:
    """The solutions page: what waits for this person's decision, and what they captured."""
    from brain.knowledge.lifecycle_store import solutions
    from brain.knowledge.solutions import may_decide

    async def load(session: AsyncSession) -> tuple[CapturedSolution, ...]:
        return await solutions(session, principal_id=person.authority.principal_id)

    found = await _in_transaction(h, person, load)
    waiting = {one.solution_id: one for one in found if may_decide(one, person.authority)}
    yours = {
        one.solution_id: one for one in found if one.captured_by == person.authority.principal_id
    }
    return waiting, yours


@check(
    leaves=("M7.6.2",),
    sentence=(
        "A solution captured in acceptance_a answers nothing and waits for an admin:knowledge "
        "holder there who did not capture it; the capturer and an administrator elsewhere cannot "
        "decide it. Approved, it answers as a verified approved-solution document, recording what "
        "it solved, who approved it and when, and its capturer is told."
    ),
)
async def a_solution_answers_only_once_somebody_else_approves_it(h: Harness) -> None:
    from brain.knowledge.item import KnowledgeState, VerificationState
    from brain.knowledge.kinds import KnowledgeKind
    from brain.knowledge.lifecycle import Outcome, TaskKind
    from brain.knowledge.lifecycle_store import solved
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.knowledge.solutions import SolutionState
    from brain.knowledge.verification import disclose

    await h.found_departments()
    capturer, approver, elsewhere, reader = (
        h.principal(A, "capturer"),
        h.principal(A, "approver"),
        h.principal(B, "admin"),
        h.principal(A, "member"),
    )
    administers = (*KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value)
    await h.person(capturer, department=A, grants=_in(A, *administers))
    await h.person(approver, department=A, grants=_in(A, *administers))
    await h.person(elsewhere, department=B, grants=_in(B, *administers))
    await h.person(reader, department=A, grants=_in(A, *KNOWLEDGE_READS))
    word = h.word()
    problem = "An acceptance check needed the answer to one question"
    answer = f"The acceptance check answers it with {word}."
    capturing, approving, outside, reading = (
        await _as(h, capturer),
        await _as(h, approver),
        await _as(h, elsewhere),
        await _as(h, reader),
    )

    if await _capture(h, capturing, department=B, problem=problem, answer=answer) is not None:
        raise CheckFailedError("a solution was captured for a department its capturer is not in")
    captured = await _capture(h, capturing, department=A, problem=problem, answer=answer)
    if captured is None:
        raise CheckFailedError("a member of the department could not capture a solution there")
    solution = captured.solution_id
    if not await _silent(h, reader, word):
        raise CheckFailedError("a captured solution answered a question before anybody approved it")
    if solution not in (await _solutions(h, approving))[0]:
        raise CheckFailedError("a waiting solution was not offered to an administrator there")
    if solution in (await _solutions(h, outside))[0]:
        raise CheckFailedError("a waiting solution was offered to an administrator elsewhere")
    if solution not in (await _solutions(h, capturing))[1]:
        raise CheckFailedError("a capturer was not shown the solution they captured")

    for refused_by in (capturing, outside):
        if await _approve_solution(h, refused_by, solution) is not None:
            raise CheckFailedError("a solution was approved by its capturer or from elsewhere")
    if solution not in (await _solutions(h, approving))[0]:
        raise CheckFailedError("a refused decision took the solution out of waiting")

    moved = await _approve_solution(h, approving, solution)
    if moved is None:
        raise CheckFailedError("another administrator of the department could not approve it")
    if not await _answered(h, reader, word, solution):
        raise CheckFailedError("an approved solution was not answered from by a text search")
    item = await _live(h, reading, solution)
    if (
        item is None
        or item.kind is not KnowledgeKind.APPROVED_SOLUTION
        or item.state is not KnowledgeState.PUBLISHED
        or (item.owner_id, item.verified_by, item.verified_at) != (approver, approver, h.now)
        or disclose(item, reader=reading.reach, now=h.now).state is not VerificationState.VERIFIED
    ):
        raise CheckFailedError(
            "an approved solution did not answer as verified by the person who approved it"
        )

    async def solving(session: AsyncSession) -> dict[str, str]:
        return await solved(session, [solution])

    if (await _in_transaction(h, reading, solving)).get(solution) != problem:
        raise CheckFailedError("an approved solution did not record what it solved")
    kept = (await _solutions(h, capturing))[1].get(solution)
    if kept is None or (kept.state, kept.decided_by, kept.decided_at) != (
        SolutionState.APPROVED,
        approver,
        h.now,
    ):
        raise CheckFailedError("an approved solution did not record who approved it and when")
    told = [one for one, _ in await _tasks(h, capturing) if one.item_id == solution]
    if [(one.kind, one.outcome) for one in told] != [(TaskKind.SOLUTION_DECIDED, Outcome.APPROVED)]:
        raise CheckFailedError("the capturer was not told their solution was approved")
    changes = [
        (actor, details.get("change"))
        for actor, details in await _ledger(h, f"{SOLUTION_SUBJECT_PREFIX}{solution}")
    ]
    if changes != [(capturer, "captured"), (approver, "approved")]:
        raise CheckFailedError("the capture and the approval were not in the ledger by name")
