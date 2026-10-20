"""A person's own skills, kept and read as the person who made them (`0232`).

`brain.ops.skill_store` keeps the library; this keeps the half of a skill that says it is
somebody's.
**A personal skill is one row in `agent.skill` and one in `agent.skill_personal`, and the two are
written in the same transaction.** The skill row alone is a skill in the library, and the library
reads cannot yet tell it from one an administrator imported, so a write that committed the first and
failed the second would leave a person's unfinished work in front of every reviewer. Writing them
together is the only ordering that has no moment at which the skill is both stored and unclaimed.

**Reads are the owner's, and are not the library's.** `mine` joins the personal row to the skill
and its decision for one owner, and `brain.ops.skill_store.library_of` leaves the same skill out
until it is offered; the two statements are each other's complement and a test holds them to it.
A person reads their own skill's body and scripts' hashes through here and nobody else is ever
offered the path.

**Offering sets one column once**, as the person: `0232` admits the update only to the row's owner,
only while it is unset, and only to a value that is set. Nothing here reads a clock; the instant is
the request's.

**A second add of the same bytes is answered by the key.** The insert says `ON CONFLICT DO NOTHING`
as `StoredSkills.add` does, and the difference is what is said afterwards: bytes that are already
the caller's own are "yours already", and bytes anybody else holds, personal or not, are one
answer, so the route cannot be used to ask who else added a file.

Rejected: a trigger or a view that hides the unoffered skills from the library. A view the
application reads instead of `agent.skill` would have to be matched by every statement that
inserts, and the library's own statements already carry the clause, which is where a reader looks.

Task ids: M40.3.2.1, M40.3.2.2, M40.3.2.3, M40.3.2.4
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import Select, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.console.skill_library import LibrarySkill
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.ops.skill_store import adding, library_skill_of, script_hashes_of, script_values
from brain.tables.audit import ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.skill import SkillReviewRow, SkillRow, SkillScriptRow
from brain.tables.skill_personal import SkillPersonalRow

#: The most of a person's own skills one reading returns. A resource bound, as the library's is.
MAX_PERSONAL: Final = 200

#: The most skills a person may hold that they have not offered. **A skill is never deleted**
#: (`0232` grants no DELETE, on purpose: a skill the department has decided about stays decided), so
#: without a bound one person could add skills for ever and the table would keep them all. Offering
#: a skill takes it out of the count, which is the way to add more.
MOST_UNOFFERED: Final = 25


class Claim(enum.StrEnum):
    """What adding a personal skill came to."""

    #: Stored, and now the person's.
    ADDED = "added"
    #: The person already holds as many unoffered skills as one person may.
    TOO_MANY = "too_many"
    #: These exact bytes were already this person's own.
    YOURS_ALREADY = "yours_already"
    #: These exact bytes are held by somebody or something else. One answer for every case.
    HELD_ALREADY = "held_already"


@dataclass(frozen=True)
class PersonalEntry:
    """One of a person's own skills as the store holds it, with when they offered it."""

    skill: LibrarySkill
    made_at: datetime
    offered_at: datetime | None

    @property
    def offered(self) -> bool:
        return self.offered_at is not None


def _set_config(name: str, value: str) -> Any:
    # Transaction-local, as `brain.ops.skill_store` sets the same settings.
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


def mine_of(
    owner_id: str, limit: int, digest: str | None = None
) -> Select[tuple[SkillRow, SkillReviewRow, SkillPersonalRow]]:
    """One person's skills with their decisions, newest first, bounded; or one of them by digest."""
    statement = (
        select(SkillRow, SkillReviewRow, SkillPersonalRow)
        .join(SkillPersonalRow, SkillPersonalRow.digest == SkillRow.digest)
        .outerjoin(SkillReviewRow, SkillReviewRow.digest == SkillRow.digest)
        .where(SkillPersonalRow.owner_id == owner_id)
    )
    if digest is not None:
        statement = statement.where(SkillRow.digest == digest)
    return statement.order_by(SkillPersonalRow.made_at.desc(), SkillRow.digest).limit(limit)


def _entries(
    rows: Sequence[Any], scripts: Sequence[tuple[str, str, str]]
) -> tuple[PersonalEntry, ...]:
    held: dict[str, list[tuple[str, str]]] = {}
    for digest, path, sha256 in scripts:
        held.setdefault(digest, []).append((path, sha256))
    found: list[PersonalEntry] = []
    for skill_row, review_row, personal_row in rows:
        one = library_skill_of(skill_row, review_row, held.get(skill_row.digest, ()))
        if one is not None:
            found.append(
                PersonalEntry(
                    skill=one, made_at=personal_row.made_at, offered_at=personal_row.submitted_at
                )
            )
    return tuple(found)


class StoredPersonalSkills:
    """`agent.skill_personal` and the skills it names, read and written as one person."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def mine(self, owner_id: str, limit: int = MAX_PERSONAL) -> tuple[PersonalEntry, ...]:
        """This person's own skills, newest first. Nobody else's, whatever the key."""
        async with self._sessions() as session:
            rows = (await session.execute(mine_of(owner_id, limit))).all()
            digests = [skill_row.digest for skill_row, _, _ in rows]
            scripts = (await session.execute(script_hashes_of(digests))).all() if digests else []
        return _entries(rows, [(str(a), str(b), str(c)) for a, b, c in scripts])

    async def one_of_mine(self, owner_id: str, digest: str) -> PersonalEntry | None:
        """One of this person's own skills by its key, or None when it is not theirs."""
        async with self._sessions() as session:
            rows = (await session.execute(mine_of(owner_id, 1, digest))).all()
            scripts = (await session.execute(script_hashes_of([digest]))).all() if rows else []
        found = _entries(rows, [(str(a), str(b), str(c)) for a, b, c in scripts])
        return found[0] if found else None

    async def add(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> Claim:
        """Store the skill and make it the person's in one transaction, or say who holds it.

        `one.submitted_by` is the person: it is the principal the transaction names, so the
        insert policies of both tables hold the two rows to the same person.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, one.submitted_by))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            holder = (
                await session.execute(
                    select(SkillPersonalRow.owner_id).where(SkillPersonalRow.digest == one.digest)
                )
            ).scalar_one_or_none()
            if holder is not None:
                return Claim.YOURS_ALREADY if holder == one.submitted_by else Claim.HELD_ALREADY
            unoffered = (
                await session.execute(
                    select(func.count())
                    .select_from(SkillPersonalRow)
                    .where(
                        SkillPersonalRow.owner_id == one.submitted_by,
                        SkillPersonalRow.submitted_at.is_(None),
                    )
                )
            ).scalar_one()
            if unoffered >= MOST_UNOFFERED:
                return Claim.TOO_MANY
            written = (await session.execute(adding(one))).scalar_one_or_none()
            if written is None:
                return Claim.HELD_ALREADY
            if one.scripts:
                await session.execute(insert(SkillScriptRow), script_values(one))
            await session.execute(
                insert(SkillPersonalRow).values(digest=one.digest, owner_id=one.submitted_by)
            )
            return Claim.ADDED

    async def offer(self, owner_id: str, digest: str, at: datetime) -> bool:
        """Offer one of this person's own skills to the department, once. False when it was not
        theirs to offer or already offered; the two are one answer."""
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, owner_id))
            moved = await session.execute(
                update(SkillPersonalRow)
                .where(
                    SkillPersonalRow.digest == digest,
                    SkillPersonalRow.owner_id == owner_id,
                    SkillPersonalRow.submitted_at.is_(None),
                )
                .values(submitted_at=at)
                .returning(SkillPersonalRow.digest)
            )
            return moved.first() is not None
