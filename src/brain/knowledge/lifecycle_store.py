"""The SQL under a stored document's lifecycle: reads at a person's reach, and the writes they make.

`brain.knowledge.lifecycle`, `promotion` and `solutions` decide; this reads and writes and decides
nothing, in the shape `item_store` and `chunk_store` take. Every function takes a session inside a
transaction somebody else opened, and none commits, so a route's attribution, its reads and its
writes are one transaction and the ledger entries the triggers append name the person who acted.

**Every statement here runs at the actor's reach, told to the database first.** `as_person` sets
`app.principal_id` and `app.departments` from `Authority.store_reach`, the union of what they read
and where they add, and `app.deciding_departments` from where they add alone, so `know.item`'s,
`know.chunk`'s, `know.steward_task`'s and `know.solution`'s policies each narrow on the same person
the Python decided about. Nothing here reads past a policy except through `0120`'s two history
reads and `0040`'s review read, and what those return is judged by `Authority` before anybody sees
it. See `THE_DATABASE_IS_TOLD_WHO_IS_ACTING_BEFORE_ANYTHING_IS_READ`.

**A new version and an approved solution are written under their steward's own reach.**
`chunk_store.write_document` refuses any other, for its own reason, so `reach_of` is resolved for
the
steward in the transaction the rows are written in, and `0120`'s `know.supersede_item` then judges
the predecessor against that same reach. The actor's attribution stays set, so the ledger names who
did it and the row names who answers for it.

**The Knowledge list and a document's history read two things past the policy, and judge nothing.**
`documents` adds every version a live document replaced, through `0120`'s `know.item_versions`, and
`ledger_entries` reads the entries `0120`'s trigger wrote about a chain. The route asks
`Authority.may_see` of every version and leaves every actor out of a history, so nothing read here
reaches a reader the detail route would not already answer.

Task ids: M7.4.4, M7.4.5, M7.4.6, M7.6.2, M7.7.2, M27.15.40
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, cast

from sqlalchemy import CursorResult, TextClause, text
from sqlalchemy.ext.asyncio import AsyncSession

from brain.core.entitlement import EntitlementSet
from brain.gate.leash import SuspendedAction
from brain.gate.suspension_store import (
    SuspensionStoreError,
    at_reach,
    put_suspension,
    stored_from,
)
from brain.knowledge.chunk_store import ChunkStoreError, reach_of, write_document
from brain.knowledge.chunking import Block
from brain.knowledge.item import KnowledgeItem, KnowledgeState
from brain.knowledge.kinds import KnowledgeKind
from brain.knowledge.lifecycle import (
    Authority,
    Outcome,
    StewardTask,
    StoredItem,
    TaskKind,
    Verification,
)
from brain.knowledge.promotion import PROMOTION_AGENT, is_promotion, promoted_item
from brain.knowledge.search import session_settings
from brain.knowledge.solutions import CapturedSolution, SolutionState
from brain.knowledge.visibility import KnowledgeVisibility, Visibility
from brain.ops.queue import Job

#: Why every function here starts by telling the database who is acting.
THE_DATABASE_IS_TOLD_WHO_IS_ACTING_BEFORE_ANYTHING_IS_READ: Final = (
    "know.item, know.chunk, know.steward_task and know.solution each have a policy keyed on "
    "session settings, and a transaction that set none sees company documents, nobody's tasks "
    "and nobody's solutions. So the actor's reach is set first in every transaction, and it is "
    "the same Authority the Python judged, so the second wall narrows on the same person."
)

#: The setting `0120`'s solution policy reads for who may decide. Its constant, held equal.
DECIDING_SETTING: Final = "app.deciding_departments"

#: The statements a stored item is read with, in `0120`'s `know.item_versions` column order.
#: Written out whole rather than built, so no statement here is assembled from strings.
ITEM_BY_ID: Final = (
    "SELECT item_id, title, owner_id, visibility, department, state, kind, verified_by, "
    "verified_at, review_by, supersedes, created_at FROM know.item WHERE item_id = :id"
)
ITEMS_IN_REACH: Final = (
    "SELECT item_id, title, owner_id, visibility, department, state, kind, verified_by, "
    "verified_at, review_by, supersedes, created_at FROM know.item "
    "ORDER BY title, item_id LIMIT :limit"
)
ITEM_VERSIONS: Final = (
    "SELECT item_id, title, owner_id, visibility, department, state, kind, verified_by, "
    "verified_at, review_by, supersedes, created_at FROM know.item_versions(:id)"
)

#: The most documents one "documents you look after" answer is assembled from, and the most tasks,
#: solutions and passages. Resource bounds on the caller's own rows, never a permission.
MAX_ITEMS: Final = 500
MAX_TASKS: Final = 200
MAX_SOLUTIONS: Final = 200
MAX_PASSAGES: Final = 400


class LifecycleStoreError(Exception):
    """A write that the database did not make as it was asked, which rolls the transaction back."""


def _set(name: str, value: str) -> TextClause:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


async def as_person(session: AsyncSession, authority: Authority) -> None:
    """Tell this transaction who is acting, what they reach and where they decide."""
    for setting in session_settings(authority.store_reach()):
        await session.execute(setting)
    await session.execute(_set(DECIDING_SETTING, authority.deciding_setting()))


# ------------------------------------------------------------------ rows to values
def stored_item(row: Mapping[Any, Any]) -> StoredItem:
    """One `know.item` row, or one `know.item_versions` row, as a value."""
    return StoredItem(
        item_id=row["item_id"],
        title=row["title"] or "",
        owner_id=row["owner_id"],
        visibility=KnowledgeVisibility(
            level=Visibility(row["visibility"]),
            owner_id=row["owner_id"],
            department=row["department"] or "",
        ),
        state=KnowledgeState(row["state"]),
        kind=KnowledgeKind(row["kind"]) if row["kind"] else None,
        verified_by=row["verified_by"] or "",
        verified_at=row["verified_at"],
        review_by=row["review_by"],
        supersedes=row["supersedes"] or "",
        added_at=row["created_at"],
    )


def captured(row: Mapping[Any, Any]) -> CapturedSolution:
    """One `know.solution` row as a value."""
    return CapturedSolution(
        solution_id=row["solution_id"],
        department=row["department"],
        problem=row["problem"],
        answer=row["answer"],
        captured_by=row["captured_by"],
        captured_at=row["captured_at"],
        conversation_ref=row["conversation_ref"] or "",
        state=SolutionState(row["state"]),
        decided_by=row["decided_by"] or "",
        decided_at=row["decided_at"],
    )


def task(row: Mapping[Any, Any]) -> StewardTask:
    """One `know.steward_task` row as a value."""
    return StewardTask(
        task_id=row["task_id"],
        kind=TaskKind(row["kind"]),
        item_id=row["item_id"],
        opened_at=row["opened_at"],
        due_at=row["due_at"],
        outcome=Outcome(row["outcome"]) if row["outcome"] else None,
    )


def _changed(result: Any) -> int:
    # `CursorResult` rather than `Result`: an UPDATE's is the one carrying `rowcount`. Cast at a
    # library boundary where proving the match buys nothing.
    return cast("CursorResult[Any]", result).rowcount


# ------------------------------------------------------------------ documents
async def live_item(session: AsyncSession, item_id: str) -> StoredItem | None:
    """One live document the policy admits at the reach this transaction was told, or None."""
    row = (await session.execute(text(ITEM_BY_ID), {"id": item_id})).mappings().one_or_none()
    return None if row is None else stored_item(row)


async def held_item(session: AsyncSession, item_id: str) -> StoredItem | None:
    """`live_item`, locked until the transaction ends, for an act that writes it.

    A separate function rather than a flag on the read, so the lock, which needs the table's
    UPDATE privilege, is taken only on the write paths that attribute their transaction.
    """
    row = (
        (
            await session.execute(
                text(
                    "SELECT item_id, title, owner_id, visibility, department, state, kind, "
                    "verified_by, verified_at, review_by, supersedes, created_at FROM know.item "
                    "WHERE item_id = :id FOR UPDATE"
                ),
                {"id": item_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else stored_item(row)


async def live_items(session: AsyncSession, *, limit: int = MAX_ITEMS) -> tuple[StoredItem, ...]:
    """Every live document the policy admits at this reach, by title, at most `limit`."""
    rows = await session.execute(
        text(ITEMS_IN_REACH),
        {"limit": limit},
    )
    return tuple(stored_item(row) for row in rows.mappings())


#: Every earlier version of these live documents, read past the policy through `0120`'s history
#: read. A live document has no later version, so its chain is itself and what it replaced.
EARLIER_VERSIONS: Final = (
    "SELECT v.item_id, v.title, v.owner_id, v.visibility, v.department, v.state, v.kind, "
    "v.verified_by, v.verified_at, v.review_by, v.supersedes, v.created_at "
    "FROM unnest(CAST(:ids AS character varying[])) AS live(item_id) "
    "CROSS JOIN LATERAL know.item_versions(live.item_id) AS v"
)


async def documents(
    session: AsyncSession, *, limit: int = MAX_ITEMS
) -> tuple[tuple[StoredItem, ...], bool]:
    """The live documents the policy admits at this reach, and every version each replaced.

    Answers the versions once each, live first by title, and whether the live load came back
    full. The earlier versions are read past the policy, as a history is, and nothing here judges
    who may see which: the caller asks `Authority.may_see` of every one, as the history route does.
    """
    live = await live_items(session, limit=limit)
    replaced = [one.item_id for one in live if one.supersedes]
    earlier: tuple[StoredItem, ...] = ()
    if replaced:
        rows = await session.execute(text(EARLIER_VERSIONS), {"ids": replaced})
        earlier = tuple(stored_item(row) for row in rows.mappings())
    kept: dict[str, StoredItem] = {}
    for one in (*live, *earlier):
        kept.setdefault(one.item_id, one)
    return tuple(kept.values()), len(live) >= limit


async def names_of(session: AsyncSession, principal_ids: Iterable[str]) -> dict[str, str]:
    """Display names by principal id, for the people a page names, asking nothing for nobody."""
    wanted = sorted({one for one in principal_ids if one})
    if not wanted:
        return {}
    rows = await session.execute(
        text("SELECT id, display_name FROM auth.principal WHERE id = ANY(:ids)"), {"ids": wanted}
    )
    return {row["id"]: row["display_name"] for row in rows.mappings() if row["display_name"]}


#: `0120`'s subject prefix for a document's ledger entries, and the longest id recorded as itself;
#: a longer one is recorded as its sha256. Held equal to the migration's by a test.
ITEM_SUBJECT_PREFIX: Final = "setting:knowledge_item."
ITEM_SUBJECT_ID_CHARS: Final = 128 - len("knowledge_item.")

#: The most ledger entries one history is read from, oldest first. A resource bound.
MAX_HISTORY: Final = 500


def item_subject(item_id: str) -> str:
    """The ledger subject `0120`'s trigger records one document's writes under."""
    if len(item_id) <= ITEM_SUBJECT_ID_CHARS:
        return f"{ITEM_SUBJECT_PREFIX}{item_id}"
    return f"{ITEM_SUBJECT_PREFIX}{hashlib.sha256(item_id.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True)
class LedgerEntry:
    """One ledger entry about one version: when, by whom, and the details the trigger wrote."""

    item_id: str
    at: datetime
    actor_id: str
    details: Mapping[str, object]


async def ledger_entries(
    session: AsyncSession, item_ids: Sequence[str], *, limit: int = MAX_HISTORY
) -> tuple[LedgerEntry, ...]:
    """Every ledger entry about these versions, in the order they were written, at most `limit`."""
    subjects = {item_subject(one): one for one in item_ids}
    if not subjects:
        return ()
    rows = await session.execute(
        text(
            "SELECT subject, at, actor_id, details FROM obs.audit_entry "
            "WHERE subject = ANY(:subjects) ORDER BY seq LIMIT :limit"
        ),
        {"subjects": sorted(subjects), "limit": limit},
    )
    return tuple(
        LedgerEntry(
            item_id=subjects[row["subject"]],
            at=row["at"],
            actor_id=row["actor_id"],
            details=row["details"] if isinstance(row["details"], Mapping) else {},
        )
        for row in rows.mappings()
    )


async def versions(session: AsyncSession, item_id: str) -> tuple[StoredItem, ...]:
    """Every version in this document's chain, oldest first, read past the policy.

    `0120`'s `know.item_versions`. Nothing here judges who may see which; the caller does, with
    `Authority.may_see`, version by version.
    """
    rows = await session.execute(text(ITEM_VERSIONS), {"id": item_id})
    return tuple(stored_item(row) for row in rows.mappings())


@dataclass(frozen=True)
class StoredPassage:
    """One passage of one version, as `know.version_passages` returns it."""

    chunk_id: str
    ordinal: int
    title: str
    section: str
    page: int | None
    body: str


async def passages(
    session: AsyncSession, item_id: str, *, limit: int = MAX_PASSAGES
) -> tuple[StoredPassage, ...]:
    """One version's passages in order, read past the policy. The caller has judged the reader."""
    rows = await session.execute(
        text(
            "SELECT chunk_id, ordinal, title, section, page, body "
            "FROM know.version_passages(:id, :limit)"
        ),
        {"id": item_id, "limit": limit},
    )
    return tuple(
        StoredPassage(
            chunk_id=row["chunk_id"],
            ordinal=row["ordinal"],
            title=row["title"] or "",
            section=row["section"] or "",
            page=row["page"],
            body=row["body"],
        )
        for row in rows.mappings()
    )


async def record_verification(session: AsyncSession, item: StoredItem, done: Verification) -> None:
    """Write a verification over a live document. Refuses when no live row changed."""
    changed = await session.execute(
        text(
            "UPDATE know.item SET verified_by = :by, verified_at = :at, review_by = :review, "
            "updated_at = now() WHERE item_id = :id AND state = 'published'"
        ),
        {
            "by": done.verified_by,
            "at": done.verified_at,
            "review": done.review_by,
            "id": item.item_id,
        },
    )
    if _changed(changed) != 1:
        msg = f"{item.item_id!r} was not verified: no live row at this reach changed"
        raise LifecycleStoreError(msg)


async def record_steward(session: AsyncSession, item: StoredItem, *, to: str) -> None:
    """Hand a document and its passages to a new steward. Refuses when the steward moved first."""
    changed = await session.execute(
        text(
            "UPDATE know.item SET owner_id = :to, updated_at = now() "
            "WHERE item_id = :id AND owner_id = :was AND state = 'published'"
        ),
        {"to": to, "id": item.item_id, "was": item.owner_id},
    )
    if _changed(changed) != 1:
        msg = f"{item.item_id!r} was not handed over: its steward changed first"
        raise LifecycleStoreError(msg)
    await session.execute(
        text(
            "UPDATE know.chunk SET owner_id = :to WHERE document_id = :id "
            "AND deleted_at IS NULL AND state IN ('draft', 'published')"
        ),
        {"to": to, "id": item.item_id},
    )


async def write_version(
    session: AsyncSession,
    predecessor: StoredItem,
    successor: KnowledgeItem,
    *,
    blocks: Sequence[Block],
    revision: str | None,
    now: datetime,
) -> Job | None:
    """Write a new version under its steward's reach and supersede the old one, in this transaction.

    The rows are written by `chunk_store.write_document`, which refuses a steward who cannot reach
    them; `0120`'s `know.supersede_item` then moves the predecessor and its passages under the
    same reach. Answers the embedding job to queue after the commit, or None.
    """
    reach = await reach_of(session, successor.owner_id, now=now)
    if reach is None:
        msg = f"{successor.owner_id!r} no longer reaches any part of the knowledge layer"
        raise ChunkStoreError(msg)
    job = await write_document(session, successor, reach=reach, revision=revision, blocks=blocks)
    await session.execute(
        text("SELECT know.supersede_item(:before, :after)"),
        {"before": predecessor.item_id, "after": successor.item_id},
    )
    return job


# ------------------------------------------------------------------ promotions
async def put_promotion(
    session: AsyncSession, suspension: SuspendedAction, *, reach: EntitlementSet, now: datetime
) -> None:
    """Raise a promotion as a suspension, under its proposer's reach, which `0042` insists on."""
    await at_reach(session, reach, now)
    await put_suspension(session, suspension)


async def promotions_asked(
    session: AsyncSession, *, reach: EntitlementSet, now: datetime
) -> dict[str, SuspendedAction]:
    """This person's own promotions, the newest per document, from the rows `0042` lets them read.

    A row that does not construct or is not a promotion is skipped, as the suspension store's own
    reads skip one: one bad row must not take the page down.
    """
    await at_reach(session, reach, now)
    rows = await session.execute(
        text(
            "SELECT * FROM gate.suspension WHERE principal_id = :me AND agent_id = :agent "
            "ORDER BY raised_at DESC, id"
        ),
        {"me": reach.principal_id, "agent": PROMOTION_AGENT},
    )
    newest: dict[str, SuspendedAction] = {}
    for row in rows.mappings():
        try:
            one = stored_from(dict(row))
        except SuspensionStoreError:
            continue
        if is_promotion(one):
            newest.setdefault(promoted_item(one), one)
    return newest


# ------------------------------------------------------------------ tasks
async def open_tasks(session: AsyncSession, *, limit: int = MAX_TASKS) -> tuple[StewardTask, ...]:
    """The open tasks addressed to the person this transaction was told of, newest first."""
    rows = await session.execute(
        text(
            "SELECT task_id, kind, item_id, opened_at, due_at, outcome FROM know.steward_task "
            "WHERE done_at IS NULL ORDER BY opened_at DESC, task_id LIMIT :limit"
        ),
        {"limit": limit},
    )
    return tuple(task(row) for row in rows.mappings())


async def close_task(session: AsyncSession, task_id: str, *, kinds: Iterable[TaskKind]) -> bool:
    """Close one of this person's own open tasks of these kinds. False when none changed."""
    allowed = sorted(one.value for one in kinds)
    if not allowed:
        return False
    changed = await session.execute(
        text(
            "UPDATE know.steward_task SET done_at = now(), updated_at = now() "
            "WHERE task_id = :id AND done_at IS NULL AND kind = ANY(:kinds)"
        ),
        {"id": task_id, "kinds": allowed},
    )
    return _changed(changed) == 1


async def titles(session: AsyncSession, item_ids: Iterable[str]) -> dict[str, str]:
    """The titles of the live documents among these the policy admits at this reach."""
    wanted = sorted(set(item_ids))
    if not wanted:
        return {}
    rows = await session.execute(
        text("SELECT item_id, title FROM know.item WHERE item_id = ANY(:ids)"), {"ids": wanted}
    )
    return {row["item_id"]: row["title"] or row["item_id"] for row in rows.mappings()}


# ------------------------------------------------------------------ solutions
async def put_solution(session: AsyncSession, solution: CapturedSolution) -> None:
    """Write a captured solution. `0120`'s policy refuses one captured in somebody else's name."""
    await session.execute(
        text(
            "INSERT INTO know.solution (solution_id, department, problem, answer, "
            "conversation_ref, captured_by, captured_at, state) VALUES (:id, :department, "
            ":problem, :answer, :conversation, :by, :at, 'pending')"
        ),
        {
            "id": solution.solution_id,
            "department": solution.department,
            "problem": solution.problem,
            "answer": solution.answer,
            "conversation": solution.conversation_ref or None,
            "by": solution.captured_by,
            "at": solution.captured_at,
        },
    )


SOLUTIONS_SHOWN: Final = (
    "SELECT solution_id, department, problem, answer, conversation_ref, captured_by, "
    "captured_at, state, decided_by, decided_at FROM know.solution "
    "WHERE state = 'pending' OR captured_by = :me "
    "ORDER BY captured_at DESC, solution_id LIMIT :limit"
)


async def solutions(
    session: AsyncSession, *, principal_id: str, limit: int = MAX_SOLUTIONS
) -> tuple[CapturedSolution, ...]:
    """The waiting solutions the policy admits, and this person's own, newest first."""
    rows = await session.execute(
        text(SOLUTIONS_SHOWN),
        {"me": principal_id, "limit": limit},
    )
    return tuple(captured(row) for row in rows.mappings())


async def solution_held(session: AsyncSession, solution_id: str) -> CapturedSolution | None:
    """One solution the policy admits, locked for the length of this transaction, or None."""
    row = (
        (
            await session.execute(
                text(
                    "SELECT solution_id, department, problem, answer, conversation_ref, "
                    "captured_by, captured_at, state, decided_by, decided_at FROM know.solution "
                    "WHERE solution_id = :id FOR UPDATE"
                ),
                {"id": solution_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else captured(row)


async def record_decision(session: AsyncSession, decided: CapturedSolution) -> None:
    """Write a decision over a waiting solution. Refuses when it was decided first."""
    changed = await session.execute(
        text(
            "UPDATE know.solution SET state = :state, decided_by = :by, decided_at = :at, "
            "item_id = :item, updated_at = now() WHERE solution_id = :id AND state = 'pending'"
        ),
        {
            "state": decided.state.value,
            "by": decided.decided_by,
            "at": decided.decided_at,
            "item": decided.item_id if decided.state is SolutionState.APPROVED else None,
            "id": decided.solution_id,
        },
    )
    if _changed(changed) != 1:
        msg = f"{decided.solution_id!r} was decided by somebody else first"
        raise LifecycleStoreError(msg)


async def write_solution_document(
    session: AsyncSession, item: KnowledgeItem, *, revision: str | None, now: datetime
) -> Job | None:
    """Write an approved solution's document under its steward's reach, in this transaction."""
    reach = await reach_of(session, item.owner_id, now=now)
    if reach is None:
        msg = f"{item.owner_id!r} no longer reaches any part of the knowledge layer"
        raise ChunkStoreError(msg)
    return await write_document(session, item, reach=reach, revision=revision)


async def solved(session: AsyncSession, item_ids: Iterable[str]) -> dict[str, str]:
    """What each approved solution among these documents solved, where the policy admits it."""
    wanted = sorted(set(item_ids))
    if not wanted:
        return {}
    rows = await session.execute(
        text(
            "SELECT item_id, problem FROM know.solution "
            "WHERE state = 'approved' AND item_id = ANY(:ids)"
        ),
        {"ids": wanted},
    )
    return {row["item_id"]: row["problem"] for row in rows.mappings()}


async def solution_titles(session: AsyncSession, solution_ids: Iterable[str]) -> dict[str, str]:
    """The first line of what each of these solutions solved, where the policy admits it."""
    wanted = sorted(set(solution_ids))
    if not wanted:
        return {}
    rows = await session.execute(
        text("SELECT solution_id, problem FROM know.solution WHERE solution_id = ANY(:ids)"),
        {"ids": wanted},
    )
    return {
        row["solution_id"]: str(row["problem"]).strip().splitlines()[0] for row in rows.mappings()
    }
