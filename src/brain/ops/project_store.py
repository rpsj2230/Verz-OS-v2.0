"""A person's projects, kept and read as the person who owns them (`0233`).

Every method names the owner to row-level security first (`app.principal_id`, per transaction), so a
project that is not the caller's is not a row the caller can see: asking for another person's
project finds nothing, which is the same answer as a project that never existed. The policies in
`0233` hold an insert, an update of the name and the putting away, and a delete of an item to the
owner alone, and the grants give nobody a delete of a project.

**A row here is a reference.** `project_item` holds `(kind, ref)` and nothing else of the thread or
the file, so nothing in this module can hand a run content: it hands back the ids, and the run reads
the documents through the document tool at its own reach (`brain.project_context`).

Task ids: M40.7.7
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.knowledge.search import PRINCIPAL_SETTING
from brain.member_projects import MOST_ITEMS, MOST_PROJECTS, Project, ProjectItem
from brain.tables.project import ProjectItemRow, ProjectRow


def _as(principal_id: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(
        name=PRINCIPAL_SETTING, value=principal_id
    )


def _project(row: ProjectRow) -> Project:
    return Project(
        project_id=str(row.id),
        name=row.name,
        created_at=row.created_at,
        archived_at=row.archived_at,
    )


def _item(row: ProjectItemRow) -> ProjectItem:
    return ProjectItem(kind=row.kind, ref=row.ref, added_at=row.added_at)


class ProjectFullError(Exception):
    """The person holds as many active projects as they may, or one lists as much as it may."""


class StoredProjects:
    """`agent.project` and `agent.project_item`, read and written as their owner."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, owner: str, name: str) -> Project:
        """Make one project for this person. Raises `ProjectFullError` past `MOST_PROJECTS`."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(owner))
            held = await session.scalar(
                select(func.count())
                .select_from(ProjectRow)
                .where(ProjectRow.owner_id == owner, ProjectRow.archived_at.is_(None))
            )
            if (held or 0) >= MOST_PROJECTS:
                raise ProjectFullError
            row = ProjectRow(owner_id=owner, name=name)
            session.add(row)
            await session.flush()
            await session.refresh(row)
            return _project(row)

    async def projects(self, owner: str, *, archived: bool = False) -> tuple[Project, ...]:
        """This person's projects, newest first; the active ones unless `archived` is asked."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(owner))
            marked = (
                ProjectRow.archived_at.is_not(None)
                if archived
                else ProjectRow.archived_at.is_(None)
            )
            rows = (
                (
                    await session.execute(
                        select(ProjectRow)
                        .where(ProjectRow.owner_id == owner, marked)
                        .order_by(ProjectRow.created_at.desc(), ProjectRow.id)
                    )
                )
                .scalars()
                .all()
            )
        return tuple(_project(one) for one in rows)

    async def one(
        self, owner: str, project_id: str
    ) -> tuple[Project, tuple[ProjectItem, ...]] | None:
        """One project and what it lists, or None for one that is not theirs or does not exist."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(owner))
            row = await self._owned(session, owner, project_id)
            if row is None:
                return None
            items = (
                (
                    await session.execute(
                        select(ProjectItemRow)
                        .where(ProjectItemRow.project_id == row.id)
                        .order_by(ProjectItemRow.added_at, ProjectItemRow.kind, ProjectItemRow.ref)
                    )
                )
                .scalars()
                .all()
            )
            return _project(row), tuple(_item(one) for one in items)

    async def rename(self, owner: str, project_id: str, name: str) -> bool:
        """Change the name of one of this person's projects. False when it is not theirs."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(owner))
            row = await self._owned(session, owner, project_id)
            if row is None:
                return False
            await session.execute(
                update(ProjectRow).where(ProjectRow.id == row.id).values(name=name)
            )
            return True

    async def archive(self, owner: str, project_id: str, at: datetime) -> bool:
        """Put one of this person's projects away. False when it is not theirs or is away."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(owner))
            row = await self._owned(session, owner, project_id)
            if row is None or row.archived_at is not None:
                return False
            await session.execute(
                update(ProjectRow).where(ProjectRow.id == row.id).values(archived_at=at)
            )
            return True

    async def add(self, owner: str, project_id: str, kind: str, ref: str) -> bool:
        """List one thread or file in one of this person's active projects.

        False when the project is not theirs or is put away. Listing the same thing twice is one
        row. Raises `ProjectFullError` past `MOST_ITEMS`.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(_as(owner))
            row = await self._owned(session, owner, project_id)
            if row is None or row.archived_at is not None:
                return False
            held = await session.scalar(
                select(func.count())
                .select_from(ProjectItemRow)
                .where(ProjectItemRow.project_id == row.id)
            )
            if (held or 0) >= MOST_ITEMS:
                raise ProjectFullError
            await session.execute(
                pg_insert(ProjectItemRow)
                .values(project_id=row.id, kind=kind, ref=ref)
                .on_conflict_do_nothing(index_elements=["project_id", "kind", "ref"])
            )
            return True

    async def remove(self, owner: str, project_id: str, kind: str, ref: str) -> bool:
        """Take one thing out of one of this person's projects. False when it was not there."""
        async with self._sessions() as session, session.begin():
            await session.execute(_as(owner))
            row = await self._owned(session, owner, project_id)
            if row is None:
                return False
            gone = await session.execute(
                delete(ProjectItemRow)
                .where(
                    ProjectItemRow.project_id == row.id,
                    ProjectItemRow.kind == kind,
                    ProjectItemRow.ref == ref,
                )
                .returning(ProjectItemRow.ref)
            )
            return gone.first() is not None

    async def items_for_run(
        self, owner: str, *, project_id: str | None, thread_id: str | None
    ) -> tuple[ProjectItem, ...]:
        """What the active project a run is made in lists, or nothing.

        The project is the one named, or else the first active one of this person's that lists the
        thread the run continues. A project put away, one that is not theirs and one that does not
        exist are the same empty answer.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(_as(owner))
            found: ProjectRow | None = None
            if project_id is not None:
                found = await self._owned(session, owner, project_id)
            elif thread_id is not None:
                found = (
                    await session.execute(
                        select(ProjectRow)
                        .join(ProjectItemRow, ProjectItemRow.project_id == ProjectRow.id)
                        .where(
                            ProjectRow.owner_id == owner,
                            ProjectRow.archived_at.is_(None),
                            ProjectItemRow.kind == "thread",
                            ProjectItemRow.ref == thread_id,
                        )
                        .order_by(ProjectRow.created_at, ProjectRow.id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
            if found is None or found.archived_at is not None:
                return ()
            rows = (
                (
                    await session.execute(
                        select(ProjectItemRow).where(ProjectItemRow.project_id == found.id)
                    )
                )
                .scalars()
                .all()
            )
        return tuple(_item(one) for one in rows)

    @staticmethod
    async def _owned(session: AsyncSession, owner: str, project_id: str) -> ProjectRow | None:
        """The project when it is this person's and the id is a UUID, else None."""
        import uuid

        try:
            wanted = uuid.UUID(project_id)
        except ValueError:
            return None
        return (
            await session.execute(
                select(ProjectRow).where(ProjectRow.id == wanted, ProjectRow.owner_id == owner)
            )
        ).scalar_one_or_none()
