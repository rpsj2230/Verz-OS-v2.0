"""Where the skill library is kept: a skill, a decision about it, and its assignments to agents.

`brain.console.skill_library` decides what a skill is, who may decide about it and what assigning
it writes, and `migrations/versions/0056_skill_library.py` argues the tables, their policies and
their triggers. This module holds the SQL between them and decides nothing, which is the split
CLAUDE.md names: nothing that decides policy owns a client.

**One transaction per write, and the ledger entry is the trigger's.** The session's principal, the
request's trace and the writer's reach are set as transaction-local settings first, because
`0056`'s insert policies read the first and its triggers read the other two, and then the row is
inserted. The entries commit with the row or not at all.

**A second import or a second decision is answered by the key and never by a read first**, for the
reason `brain.ops.agent_automation_store` gives about two presses of one button: the read in each
would find nothing. The insert says `ON CONFLICT DO NOTHING` on the key and returns the key it
wrote, and nothing back means nothing was written.

**An assignment writes the install only if it is the install the decision was made about.** The
route reads the agent, decides, and hands over the install to write with the hash it read. The
instance row is locked and its hash compared inside the transaction that writes, so an edit made in
between, an instruction replaced or another skill assigned, is answered "changed since" rather than
overwritten. The comparison is the one thing this module decides, and it is about rows rather than
about anybody's reach.

**A stored skill that no longer constructs is absent for everybody**, for
`brain.agent_routes.A_ROW_THAT_DOES_NOT_CONSTRUCT_IS_ABSENT_FOR_EVERYBODY`'s reason: one row an
operator broke by hand should not take the library away from the person who came to find out what
is wrong with it.

**A retirement is written as a decision is, and a detachment as an assignment is** (`0088`). The
retirement's key answers a second press; the detachment writes the install only if it is the
install the decision was made about, under the same lock and the same comparison.

**History is two bounded reads folded into one order.** The newest assignments and the newest
detachments, each bounded by `MAX_HISTORY`, become events newest first, cut to the same bound,
so an event is never dropped from the middle of what is returned: anything older than the oldest
event kept is older than everything either read held. The caller is told the bound was reached and
never how much lies past it.

Task ids: M42.6.4, M27.11.8
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

import structlog
from pydantic import ValidationError
from sqlalchemy import Select, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.dml import ReturningInsert

from brain.console.skill_library import (
    Assignment,
    AssignmentChange,
    Detachment,
    LibrarySkill,
    Retirement,
    SkillEvent,
)
from brain.ops.automation_owner_store import PRINCIPAL_SETTING
from brain.tables.audit import ENT_HASH_SETTING, TRACE_ID_SETTING
from brain.tables.skill import (
    APPROVED,
    SkillAssignmentRow,
    SkillDetachmentRow,
    SkillRetirementRow,
    SkillReviewRow,
    SkillRow,
)
from brain.tables.template import TemplateInstanceRow
from brain.tools.skills import ImportedSkill, Skill, SkillSource, SkillState, SourceKind

log = structlog.get_logger()

#: The most skills one reading of the library holds. A resource bound, as the roster's is, and the
#: caller is told the load came back full without being told what was in the rest of it.
MAX_LIBRARY: Final = 500

#: The most events one reading of the assignment history holds, for `MAX_LIBRARY`'s reason.
MAX_HISTORY: Final = 1000


def _set_config(name: str, value: str) -> Any:
    # Transaction-local, as `brain.ops.agent_automation_store` sets the same settings.
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


# ------------------------------------------------------------------------- the statements
def library_of(limit: int) -> Select[tuple[SkillRow, SkillReviewRow, SkillRetirementRow]]:
    """Every skill with its decision and its retirement, if it has either, newest first, bounded."""
    # Each outer join's right side is None for a skill without one, whatever the type says.
    return (
        select(SkillRow, SkillReviewRow, SkillRetirementRow)
        .outerjoin(SkillReviewRow, SkillReviewRow.digest == SkillRow.digest)
        .outerjoin(SkillRetirementRow, SkillRetirementRow.digest == SkillRow.digest)
        .order_by(SkillRow.created_at.desc(), SkillRow.digest)
        .limit(limit)
    )


def one_skill(digest: str) -> Select[tuple[SkillRow, SkillReviewRow, SkillRetirementRow]]:
    """One skill by the digest it is stored under, with its decision and its retirement."""
    return (
        select(SkillRow, SkillReviewRow, SkillRetirementRow)
        .outerjoin(SkillReviewRow, SkillReviewRow.digest == SkillRow.digest)
        .outerjoin(SkillRetirementRow, SkillRetirementRow.digest == SkillRow.digest)
        .where(SkillRow.digest == digest)
    )


def skill_values(one: LibrarySkill) -> dict[str, Any]:
    """What adding a skill writes: the fields a reviewer reads, where they came from, and who."""
    skill, source = one.imported.skill, one.imported.source
    return {
        "digest": one.digest,
        "name": skill.name,
        "version": skill.version,
        "description": skill.description,
        "body": skill.body,
        "tools": list(skill.tools),
        "source_kind": source.kind.value,
        "source_location": source.location,
        "source_content_digest": source.content_digest,
        "submitted_by": one.submitted_by,
    }


def adding(one: LibrarySkill) -> ReturningInsert[tuple[str]]:
    """The insert, which writes nothing and returns nothing when these bytes are already held."""
    return (
        insert(SkillRow)
        .values(**skill_values(one))
        .on_conflict_do_nothing(index_elements=["digest"])
        .returning(SkillRow.digest)
    )


def review_values(one: LibrarySkill) -> dict[str, Any]:
    """What a decision writes. The importer is copied so the table can refuse them as decider."""
    return {
        "digest": one.digest,
        "submitted_by": one.submitted_by,
        "decision": one.imported.state.value,
        "decided_by": one.imported.reviewer,
    }


def deciding(one: LibrarySkill) -> ReturningInsert[tuple[str]]:
    """The insert, which writes nothing and returns nothing when the skill is already decided."""
    return (
        insert(SkillReviewRow)
        .values(**review_values(one))
        .on_conflict_do_nothing(index_elements=["digest"])
        .returning(SkillReviewRow.digest)
    )


def assignment_values(made: Assignment) -> dict[str, Any]:
    """What an assignment records. `approval` is the column's own default and is not sent."""
    return {
        "agent_id": made.agent_id,
        "skill_name": made.skill_name,
        "digest": made.digest,
        "replaces_digest": made.replaces_digest,
        "assigned_by": made.assigned_by,
    }


def assigning(made: Assignment) -> Any:
    return insert(SkillAssignmentRow).values(**assignment_values(made))


def install_hash_locked(agent_id: str) -> Select[tuple[str]]:
    """The agent's install hash, with its row locked for the rest of the transaction."""
    return (
        select(TemplateInstanceRow.effective_hash)
        .where(TemplateInstanceRow.id == agent_id)
        .with_for_update()
    )


def retirement_values(one: LibrarySkill) -> dict[str, Any]:
    """What a retirement writes: the version and who retired it. The instant is the table's."""
    if one.retirement is None:
        msg = "a skill with no retirement on it writes no retirement row"
        raise ValueError(msg)
    return {"digest": one.digest, "retired_by": one.retirement.by}


def retiring(one: LibrarySkill) -> ReturningInsert[tuple[str]]:
    """The insert, which writes nothing and returns nothing when the version is already retired."""
    return (
        insert(SkillRetirementRow)
        .values(**retirement_values(one))
        .on_conflict_do_nothing(index_elements=["digest"])
        .returning(SkillRetirementRow.digest)
    )


def detachment_values(made: Detachment) -> dict[str, Any]:
    """What a detachment records: the agent, the skill and its bytes, and who took it off."""
    return {
        "agent_id": made.agent_id,
        "skill_name": made.skill_name,
        "digest": made.digest,
        "detached_by": made.detached_by,
    }


def detaching(made: Detachment) -> Any:
    return insert(SkillDetachmentRow).values(**detachment_values(made))


def assignments_newest(limit: int) -> Select[tuple[SkillAssignmentRow]]:
    """The newest assignments, bounded, with the key breaking a tie in the instant."""
    return (
        select(SkillAssignmentRow)
        .order_by(SkillAssignmentRow.created_at.desc(), SkillAssignmentRow.id)
        .limit(limit)
    )


def detachments_newest(limit: int) -> Select[tuple[SkillDetachmentRow]]:
    """The newest detachments, bounded, with the key breaking a tie in the instant."""
    return (
        select(SkillDetachmentRow)
        .order_by(SkillDetachmentRow.created_at.desc(), SkillDetachmentRow.id)
        .limit(limit)
    )


def events_of(
    assigned: Sequence[SkillAssignmentRow], detached: Sequence[SkillDetachmentRow], limit: int
) -> tuple[SkillEvent, ...]:
    """Assignment and detachment rows as what happened to each version, newest first, bounded.

    An assignment is an event for the bytes it names, and, when it replaced another version, an
    event for the bytes it replaced, at the same instant and by the same person: that is when those
    bytes stopped being what the agent ran. A detachment is an event for the bytes it names.
    """
    events: list[SkillEvent] = []
    for row in assigned:
        events.append(
            SkillEvent(
                digest=row.digest,
                skill_name=row.skill_name,
                agent_id=row.agent_id,
                change=AssignmentChange.ASSIGNED,
                by=row.assigned_by,
                at=row.created_at,
            )
        )
        if row.replaces_digest is not None:
            events.append(
                SkillEvent(
                    digest=row.replaces_digest,
                    skill_name=row.skill_name,
                    agent_id=row.agent_id,
                    change=AssignmentChange.REPLACED,
                    by=row.assigned_by,
                    at=row.created_at,
                )
            )
    events.extend(
        SkillEvent(
            digest=row.digest,
            skill_name=row.skill_name,
            agent_id=row.agent_id,
            change=AssignmentChange.DETACHED,
            by=row.detached_by,
            at=row.created_at,
        )
        for row in detached
    )
    events.sort(key=lambda one: one.at, reverse=True)
    return tuple(events[:limit])


def install_values(made: Assignment | Detachment) -> dict[str, Any]:
    """The install's overlay, owners and cached effective document, written together, as
    `brain.prompt_routes.write_install` writes them."""
    return {
        "overlay": dict(made.instance.overlay),
        "field_owners": {
            path: owner.model_dump(mode="json")
            for path, owner in made.instance.overlay_owners.items()
        },
        "effective_document": dict(made.effective_document),
        "effective_hash": made.effective_hash,
    }


def writing_install(made: Assignment | Detachment) -> Any:
    return (
        update(TemplateInstanceRow)
        .where(TemplateInstanceRow.id == made.agent_id)
        .values(**install_values(made))
    )


# ------------------------------------------------------------------------ rows to the domain
def library_skill_of(
    row: SkillRow, review: SkillReviewRow | None, retirement: SkillRetirementRow | None = None
) -> LibrarySkill | None:
    """The stored skill as the library holds it, or None when it does not construct.

    The approved digest is the key the decision row names, never the digest of the fields, so a
    row edited after its approval reads as moved: `ImportedSkill.is_executable` compares the two.
    A retirement is read off its own row and never off the skill's.
    """
    try:
        skill = Skill(
            name=row.name,
            description=row.description,
            version=row.version,
            tools=tuple(row.tools),
            body=row.body,
        )
        source = SkillSource(
            kind=SourceKind(row.source_kind),
            location=row.source_location,
            content_digest=row.source_content_digest,
        )
        if review is None:
            imported = ImportedSkill(skill=skill, source=source)
        else:
            state = SkillState(review.decision)
            imported = ImportedSkill(
                skill=skill,
                source=source,
                state=state,
                reviewer=review.decided_by,
                reviewed_at=review.created_at,
                approved_digest=review.digest if review.decision == APPROVED else "",
            )
    except (ValidationError, ValueError, TypeError) as exc:
        log.warning("stored skill does not construct", digest=row.digest, error=type(exc).__name__)
        return None
    return LibrarySkill(
        imported=imported,
        digest=row.digest,
        submitted_by=row.submitted_by,
        submitted_at=row.created_at,
        retirement=(
            None
            if retirement is None
            else Retirement(by=retirement.retired_by, at=retirement.created_at)
        ),
    )


def _constructed(rows: Sequence[Any]) -> tuple[LibrarySkill, ...]:
    found = (library_skill_of(*row) for row in rows)
    return tuple(one for one in found if one is not None)


class StoredSkills:
    """`brain.skill_routes.SkillLibrary` over this install's database."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def library(self, limit: int = MAX_LIBRARY) -> tuple[LibrarySkill, ...]:
        async with self._sessions() as session:
            rows = (await session.execute(library_of(limit))).all()
        return _constructed(rows)

    async def skill(self, digest: str) -> LibrarySkill | None:
        async with self._sessions() as session:
            rows = (await session.execute(one_skill(digest))).all()
        found = _constructed(rows)
        return found[0] if found else None

    async def add(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> bool:
        """Write the skill, or say these bytes are already in the library."""
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, one.submitted_by))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            written = (await session.execute(adding(one))).scalar_one_or_none()
        return written is not None

    async def decide(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> bool:
        """Write the decision, or say the skill was already decided."""
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, one.imported.reviewer))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            written = (await session.execute(deciding(one))).scalar_one_or_none()
        return written is not None

    async def assign(
        self, made: Assignment, *, expected_hash: str, ent_hash: str, trace_id: str
    ) -> bool:
        """Record the assignment and write the install, or say the install has changed since.

        See the module docstring for why the hash is compared under the lock.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, made.assigned_by))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            current = (
                await session.execute(install_hash_locked(made.agent_id))
            ).scalar_one_or_none()
            if current != expected_hash:
                return False
            await session.execute(assigning(made))
            await session.execute(writing_install(made))
        return True

    async def retire(self, one: LibrarySkill, *, ent_hash: str, trace_id: str) -> bool:
        """Write the retirement, or say the version was already retired."""
        if one.retirement is None:
            msg = "a skill with no retirement on it writes no retirement row"
            raise ValueError(msg)
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, one.retirement.by))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            written = (await session.execute(retiring(one))).scalar_one_or_none()
        return written is not None

    async def detach(
        self, made: Detachment, *, expected_hash: str, ent_hash: str, trace_id: str
    ) -> bool:
        """Record the detachment and write the install, or say the install has changed since.

        `assign`'s lock and comparison, for its reason.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(_set_config(PRINCIPAL_SETTING, made.detached_by))
            await session.execute(_set_config(TRACE_ID_SETTING, trace_id))
            await session.execute(_set_config(ENT_HASH_SETTING, ent_hash))
            current = (
                await session.execute(install_hash_locked(made.agent_id))
            ).scalar_one_or_none()
            if current != expected_hash:
                return False
            await session.execute(detaching(made))
            await session.execute(writing_install(made))
        return True

    async def history(self, limit: int = MAX_HISTORY) -> tuple[SkillEvent, ...]:
        """What happened to every version on every agent, newest first, bounded. Nobody narrowed."""
        async with self._sessions() as session:
            assigned = (await session.execute(assignments_newest(limit))).scalars().all()
            detached = (await session.execute(detachments_newest(limit))).scalars().all()
        return events_of(assigned, detached, limit)
