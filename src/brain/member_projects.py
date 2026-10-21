"""A person's own project: what it may hold and what a run reads of it (M40.7.7).

A project is a name, its owner and a list of references to the person's own threads and to
documents they may read. The tables were made first (`0233`); this is the rule over them, kept apart
from the store and the routes so it can be asked without a database.

**A project is context for a run and never memory.** The list names a thread or a document by id and
copies neither. A run made inside a project reads the project's documents through the one reader
every document goes through (`knowledge.read_document`), at the reach the run holds when it is
made, so a document the person has since lost the right to read is still on the list and is simply
not read: the run is shown nothing for it and nothing says so beyond what the list already shows.
Nothing in `brain.memory` reads a project, a project item or this module, and a test holds that by
reading the source.

**Rejected: copying a project's files into the thread when it is added.** A copy outlives the grant
that let the person read the original, which a reference cannot. **Rejected as well: a second
retrieval path for project files.** The documents are read by the registered document
tool the agent already holds, in `brain.gate.model_lane`, ahead of the search like an attached file,
so redaction, the byte bound and the citation record apply to them as they do to anything else.

**Bounded reads.** A project may list many documents but a turn reads the first
`FILES_READ_PER_TURN` of them, oldest added first, so a long list cannot make every question read
everything. The cap is on what is read, not on what may be listed, and it is the same for every
project.

Task ids: M40.7.7
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.tables.project import KINDS, NAME_CHARS, REF_CHARS

#: Why a project is read by reference at the reach held when a run is made.
A_PROJECT_IS_CONTEXT_FOR_A_RUN_AND_NEVER_MEMORY: Final = (
    "A project lists a person's own threads and the documents they may read by id. A run made "
    "inside it reads those documents as project context, at the reach the run holds at that "
    "moment, and a document the person can no longer reach is left on the list and not read. "
    "Nothing in a project is ever copied, and nothing in it is read by memory."
)

#: The most active projects one person holds, and the most items one project lists.
MOST_PROJECTS: Final = 50
MOST_ITEMS: Final = 200

#: The most of a project's documents one turn reads, oldest added first.
FILES_READ_PER_TURN: Final = 5

FILE: Final = "file"
THREAD: Final = "thread"

#: What a person is told, in the product's words, when a request cannot be kept.
NAME_NEEDED: Final = "A project needs a name."
TOO_MANY_PROJECTS: Final = "You have as many projects as you can keep. Put one away first."
TOO_MANY_ITEMS: Final = "That project lists as much as it can. Take something out first."
NOT_AVAILABLE: Final = "Projects are not switched on for this install."


@dataclass(frozen=True)
class Project:
    """One project as its owner sees it."""

    project_id: str
    name: str
    created_at: datetime
    archived_at: datetime | None = None

    @property
    def archived(self) -> bool:
        return self.archived_at is not None


@dataclass(frozen=True)
class ProjectItem:
    """One thing a project lists: a thread or a file, by id."""

    kind: str
    ref: str
    added_at: datetime


def clean_name(name: str) -> str | None:
    """The name as it is kept, or None when there is none to keep or it is too long.

    Whitespace is trimmed and runs of it collapsed, so two spellings of one name are one.
    """
    kept = " ".join(name.split())
    if not kept or len(kept) > NAME_CHARS:
        return None
    return kept


def is_kind(kind: str) -> bool:
    """Whether this is one of the two things a project may list."""
    return kind in KINDS


def is_ref(ref: str) -> bool:
    """Whether this is an id the table can hold."""
    return bool(ref.strip()) and len(ref) <= REF_CHARS


def files_to_read(items: Iterable[ProjectItem]) -> tuple[str, ...]:
    """The documents a turn reads: the project's files, oldest added first, each once, capped.

    Threads are not read as context: they are the person's own conversations, and a run reads the
    one it continues through the thread path. See
    `A_PROJECT_IS_CONTEXT_FOR_A_RUN_AND_NEVER_MEMORY`.
    """
    files = sorted((one for one in items if one.kind == FILE), key=lambda one: one.added_at)
    return tuple(dict.fromkeys(one.ref for one in files))[:FILES_READ_PER_TURN]
