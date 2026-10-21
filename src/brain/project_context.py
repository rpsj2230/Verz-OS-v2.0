"""What a run made inside a personal project brings, and the switch that lets it (M40.7.7).

This is the one place `/answer` asks a project anything. `follow_up_for` calls `project_files_for`
and puts the answer on the `FollowUp` it already builds, so **a project's documents travel the path
an attached file travels** and are read in `brain.gate.model_lane` by the registered
`knowledge.read_document` handler, at the reach the run holds (the person's, narrowed by the agent's
ceiling), ahead of the search and through the same redactor. Rejected: a retrieval of its own for
project files, which would be a second place for reach to be decided; and reading through
`chat.read_attachment`, which answers only for a file a conversation names.

**A file the person can no longer reach is on the list and contributes nothing.** The reader returns
no passages for it, exactly as it does for a document that does not exist, and the answer is not
told that one was left out. Whether anything was left out is a fact about what the person may no
longer read.

**A project is read for a run and never kept.** Nothing here writes, and `brain.memory` does not
import this module or the tables (a test reads the source to hold that).

Task ids: M40.7.7
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Final, cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.knowledge.document_tools import (
    DEFAULT_PASSAGES,
    READ_DOCUMENT,
    DocumentRead,
    KnowledgePassage,
)
from brain.member_projects import files_to_read
from brain.ops.features import is_on
from brain.ops.features_declared.personal_projects import PERSONAL_PROJECTS
from brain.ops.project_store import StoredProjects

#: The most passages one project document gives a turn: the tool's own default for a document.
PASSAGES_PER_FILE: Final = DEFAULT_PASSAGES


async def projects_are_on(sessions: async_sessionmaker[AsyncSession] | None) -> bool:
    """Whether `personal_projects` is switched on now. Off with no database or no row."""
    if sessions is None:
        return False
    async with sessions() as session:
        return await is_on(session, PERSONAL_PROJECTS)


async def project_files_for(
    state: Any, *, owner: str, project_id: str | None, thread_id: str | None
) -> tuple[str, ...]:
    """The documents a run in this person's project reads, or nothing.

    Nothing with the switch off, with no database, for a project that is not theirs or is put
    away, and when the run names neither a project nor a thread that one of theirs lists.
    """
    sessions = getattr(state, "db_sessions", None)
    if not isinstance(sessions, async_sessionmaker):
        return ()
    if project_id is None and thread_id is None:
        return ()
    if not await projects_are_on(sessions):
        return ()
    items = await StoredProjects(sessions).items_for_run(
        owner, project_id=project_id, thread_id=thread_id
    )
    return files_to_read(items)


def project_file_handler(
    registry: Any,
) -> Callable[..., Awaitable[TypedResult[KnowledgePassage]]] | None:
    """The registry's `knowledge.read_document` handler taking a document's id, or None.

    The tool the agent itself reads documents with: **the one reader**, so a project file is read
    at exactly the reach any other document is. None where the registry has no such tool.
    """
    if registry is None or not registry.has(READ_DOCUMENT):
        return None
    # The registry keeps a handler as an untyped callable; this is the one it registered.
    handler = cast(
        "Callable[..., Awaitable[TypedResult[KnowledgePassage]]]",
        registry.get(READ_DOCUMENT).handler,
    )

    async def read(
        document_id: str, *, entitlement: EntitlementSet, now: datetime | None = None
    ) -> TypedResult[KnowledgePassage]:
        return await handler(
            DocumentRead(document_id=document_id, limit=PASSAGES_PER_FILE),
            entitlement=entitlement,
            now=now,
        )

    return read
