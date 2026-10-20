"""What a run made inside a personal project reads, and that no memory ever does (M40.7.7).

The reading half is driven through the real answer lane (`tests/unit/test_model_lane.py`'s own
harness), so the prompt a provider would receive is what is asserted on. The deciding half,
`follow_up_for`, is driven with the stand-in store `tests/unit/test_project_routes.py` shows is the
store's behaviour. The same path against PostgreSQL is the install check.

Task ids: M40.7.7
"""

from __future__ import annotations

import ast
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain import api_routes, project_context
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import TypedResult
from brain.gate.model_lane import FollowUp
from brain.knowledge.document_tools import (
    MAX_PASSAGES,
    READ_DOCUMENT,
    DocumentRead,
    KnowledgePassage,
)
from brain.member_projects import (
    FILE,
    FILES_READ_PER_TURN,
    MOST_ITEMS,
    MOST_PROJECTS,
    THREAD,
    ProjectItem,
    clean_name,
    files_to_read,
    is_kind,
    is_ref,
)
from brain.tables.project import KINDS, NAME_CHARS, REF_CHARS
from tests.unit.test_model_lane import (
    CALLER,
    NOW,
    READABLE_DOCUMENT,
    VISIBLE,
    WITHHELD,
    WITHHELD_DOCUMENT,
    Passages,
    ask,
    prompt,
)

THEN = datetime(2999, 1, 1, tzinfo=UTC)
SRC = Path(__file__).parents[2] / "src" / "brain"


def _item(kind: str, ref: str, days: int) -> ProjectItem:
    return ProjectItem(kind=kind, ref=ref, added_at=THEN + timedelta(days=days))


# ------------------------------------------------------------------------ the pure rule
def test_a_turn_reads_the_files_oldest_first_each_once_and_never_a_thread() -> None:
    """Files only, in the order they were added, each id once. Delete this and a thread is read as
    if it were a document, or a file listed twice is read twice, or the newest is read first."""
    items = [
        _item(FILE, "doc_a", 2),
        _item(THREAD, "t1", 0),
        _item(FILE, "doc_z", 1),
        _item(FILE, "doc_z", 3),
    ]
    assert files_to_read(items) == ("doc_z", "doc_a")
    assert files_to_read([_item(THREAD, "t1", 0)]) == ()


def test_a_turn_reads_no_more_files_than_the_cap_and_keeps_the_oldest() -> None:
    """With more files than the cap, the oldest are read and the rest are not. Delete this and a
    long project makes every question read every file."""
    items = [_item(FILE, f"doc_{n}", n) for n in range(FILES_READ_PER_TURN + 4)]
    read = files_to_read(items)
    assert len(read) == FILES_READ_PER_TURN
    assert read == tuple(f"doc_{n}" for n in range(FILES_READ_PER_TURN))
    assert 1 <= FILES_READ_PER_TURN <= 10
    # The limits on what a person keeps are small numbers stated outside the module that holds
    # them, so a typo of a zero too many is a failing test and not a larger shelf.
    assert 1 <= MOST_PROJECTS <= 100
    assert FILES_READ_PER_TURN <= MOST_ITEMS <= 500


def test_the_rule_holds_the_same_kinds_and_widths_the_tables_do() -> None:
    """The kinds the rule names are the table's, and a name or id it accepts fits a column. Delete
    this and the rule accepts what the database refuses, or refuses what it holds."""
    assert (FILE, THREAD) == KINDS
    assert is_kind(FILE) and is_kind(THREAD) and not is_kind("memory")
    assert is_ref("x" * REF_CHARS) and not is_ref("x" * (REF_CHARS + 1)) and not is_ref("   ")
    assert clean_name(" a   b ") == "a b"
    assert clean_name("x" * NAME_CHARS) is not None
    assert clean_name("x" * (NAME_CHARS + 1)) is None
    assert clean_name("   ") is None


# ------------------------------------------------------------------- the run reads the files
def test_a_project_file_is_read_at_the_run_reach_shown_and_cited() -> None:
    """The search finds nothing; the project's file is read through the document tool with the
    reach the answer runs at, passes the redactor, reaches the model and is cited. Delete this and a
    question inside a project is answered from a search that never reads the project's files."""
    read: list[tuple[str, EntitlementSet]] = []

    async def reading(
        document_id: str, *, entitlement: EntitlementSet, now: datetime | None = None
    ) -> TypedResult[KnowledgePassage]:
        del now
        read.append((document_id, entitlement))
        return TypedResult(records=(VISIBLE,), source="knowledge", fetched_at=NOW.isoformat())

    run = ask(
        "what does the handbook say",
        search=Passages(),
        follow_up=FollowUp(project_files=(READABLE_DOCUMENT,), read_project_file=reading),
    )

    assert read == [(READABLE_DOCUMENT, CALLER)]
    assert run.answered is not None and run.answered.composed is not None
    assert "Annual leave is twenty five days a year." in prompt(run)
    assert {one.record_id for one in run.answered.composed.citations} == {VISIBLE.id}


def test_a_project_file_the_reach_may_not_read_contributes_nothing_and_asks_no_model() -> None:
    """The sibling: the reader handed back a passage the caller may not read, the redactor
    withholds it, and nothing reaches a model and no sentence says one was left out. Delete this and
    a file the person lost the right to read could be the one passage that skips the redactor."""

    async def reading(
        document_id: str, *, entitlement: EntitlementSet, now: datetime | None = None
    ) -> TypedResult[KnowledgePassage]:
        del document_id, entitlement, now
        return TypedResult(records=(WITHHELD,), source="knowledge", fetched_at=NOW.isoformat())

    run = ask(
        "what does the file say",
        search=Passages(),
        follow_up=FollowUp(project_files=(WITHHELD_DOCUMENT,), read_project_file=reading),
    )

    assert run.sent == []
    assert WITHHELD_DOCUMENT not in prompt(run)


def test_a_follow_up_with_no_project_reader_reads_no_project_file() -> None:
    """Files named but no reader bound read nothing, rather than reading by some other path.
    Delete this and a process with no document tool reaches for files another way."""
    run = ask(
        "what does the handbook say",
        search=Passages(),
        follow_up=FollowUp(project_files=(READABLE_DOCUMENT,)),
    )
    assert run.sent == []


def test_the_files_of_a_project_are_shown_in_the_order_they_were_added() -> None:
    """Two project files are each read and the first added is shown first. Delete this and the
    order of a project's documents in the prompt is whatever the loop happens to leave."""
    second = VISIBLE.model_copy(
        update={"id": "c_two_1", "document": "The second file says banana."}
    )
    texts = {"doc_one": VISIBLE, "doc_two": second}

    async def reading(
        document_id: str, *, entitlement: EntitlementSet, now: datetime | None = None
    ) -> TypedResult[KnowledgePassage]:
        del entitlement, now
        return TypedResult(
            records=(texts[document_id],), source="knowledge", fetched_at=NOW.isoformat()
        )

    run = ask(
        "what do the files say",
        search=Passages(),
        follow_up=FollowUp(project_files=("doc_one", "doc_two"), read_project_file=reading),
    )

    shown = prompt(run)
    assert shown.index("Annual leave is twenty five days a year.") < shown.index("banana")


def test_without_a_database_projects_are_off() -> None:
    """The switch reader answers no for a process with no database. Delete this and such a
    process opens a session it does not have, or reads projects with no switch to ask."""
    assert asyncio.run(project_context.projects_are_on(None)) is False


# ------------------------------------------------------- the decision `/answer` takes to read them
class _Projects:
    """`StoredProjects.items_for_run`: the project named, or the one listing the thread."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str | None, str | None]] = []

    async def items_for_run(
        self, owner: str, *, project_id: str | None, thread_id: str | None
    ) -> tuple[ProjectItem, ...]:
        self.asked.append((owner, project_id, thread_id))
        if project_id == "mine" or thread_id == "in-project":
            return (_item(FILE, READABLE_DOCUMENT, 0), _item(THREAD, "in-project", 1))
        return ()


class _Registry:
    def __init__(self) -> None:
        self.handled: list[Any] = []
        self.limits: list[int] = []

    def has(self, name: str) -> bool:
        return name == READ_DOCUMENT

    def get(self, name: str) -> Any:
        async def handler(request: DocumentRead, *, entitlement: Any, now: Any) -> Any:
            self.handled.append((request.document_id, entitlement, now))
            self.limits.append(request.limit)
            return TypedResult[KnowledgePassage](records=(), source="knowledge")

        return SimpleNamespace(handler=handler)


@pytest.fixture
def projects(monkeypatch: pytest.MonkeyPatch) -> tuple[_Projects, list[bool]]:
    store, switch = _Projects(), [True]

    async def is_on(_sessions: object) -> bool:
        return switch[0]

    monkeypatch.setattr(project_context, "projects_are_on", is_on)
    monkeypatch.setattr(project_context, "StoredProjects", lambda _sessions: store)
    return store, switch


def _follow(question: api_routes.Question, registry: Any = None) -> FollowUp | None:
    state = SimpleNamespace(db_sessions=async_sessionmaker())
    asking = SimpleNamespace(principal=SimpleNamespace(id="p_priya"), reach=CALLER, now=NOW)
    return asyncio.run(
        api_routes.follow_up_for(state, asking, question, registry or _Registry())  # type: ignore[arg-type]
    )


def test_a_question_naming_a_project_brings_that_projects_files_read_by_the_document_tool(
    projects: tuple[_Projects, list[bool]],
) -> None:
    """With the switch on, a question naming the caller's project brings its files, and reading one
    goes through the registered `knowledge.read_document` handler with the entitlement it is handed.
    Delete this and `/answer` never reads a project, or reads it through a reader of its own."""
    store, _ = projects
    registry = _Registry()
    follow = _follow(api_routes.Question(question="and the leave?", project="mine"), registry)

    assert follow is not None and follow.project_files == (READABLE_DOCUMENT,)
    assert follow.earlier == () and follow.attached == ()
    assert store.asked == [("p_priya", "mine", None)]
    assert follow.read_project_file is not None
    read = follow.read_project_file

    async def reading() -> None:
        await read(READABLE_DOCUMENT, entitlement=CALLER, now=NOW)

    asyncio.run(reading())
    assert registry.handled == [(READABLE_DOCUMENT, CALLER, NOW)]
    assert 1 < registry.limits[0] <= MAX_PASSAGES


def test_a_question_in_a_thread_a_project_lists_brings_the_projects_files(
    projects: tuple[_Projects, list[bool]],
) -> None:
    """A question that only names a thread, and no project, still reads the files of the caller's
    project that lists that thread. Delete this and a person asking inside a thread they put in a
    project gets none of the project's context."""
    follow = _follow(api_routes.Question(question="and the leave?", thread="in-project"))
    assert follow is not None and follow.project_files == (READABLE_DOCUMENT,)


def test_without_the_switch_a_project_or_none_a_question_brings_no_project_file(
    projects: tuple[_Projects, list[bool]],
) -> None:
    """With the switch off, with no project and no thread, and with a project that is not the
    caller's, nothing is read and the follow-up is as it was before. Delete this and a switched-off
    install reads projects, or a plain question asks the store anything."""
    store, switch = projects
    assert _follow(api_routes.Question(question="plain")) is None
    assert store.asked == []
    assert _follow(api_routes.Question(question="x", project="someone-elses")) is None
    switch[0] = False
    assert _follow(api_routes.Question(question="x", project="mine")) is None


def test_without_a_document_tool_a_named_project_brings_nothing(
    projects: tuple[_Projects, list[bool]],
) -> None:
    """A registry with no `knowledge.read_document` yields no follow-up, so no other reader steps
    in. Delete this and the files could be read by a path that is not the registered tool."""
    follow = _follow(
        api_routes.Question(question="x", project="mine"),
        registry=SimpleNamespace(has=lambda _n: False),
    )
    assert follow is None


# ------------------------------------------------------------------------ never memory
MEMORY = SRC / "memory"
PROJECT_MODULES = {
    "brain.tables.project",
    "brain.member_projects",
    "brain.project_context",
    "brain.project_routes",
    "brain.ops.project_store",
}


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {one.name for one in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found |= {f"{node.module}.{one.name}" for one in node.names}
    return found


def test_nothing_in_memory_imports_a_project() -> None:
    """No module under `brain.memory` imports the project tables, the rule, the store, the routes or
    the context reader. Delete this and a project's files could become memory without a line of this
    test failing, which is the one thing a project must never be."""
    modules = sorted(MEMORY.glob("*.py"))
    assert modules
    for module in modules:
        assert not (_imports(module) & PROJECT_MODULES), module.name


def test_the_memory_store_and_formation_read_no_project_table() -> None:
    """The stores that write memory (`StoredFormations`) and read it (`StoredRecall`) import no
    project module either. Delete this and the two places memory is actually written or read can
    reach a project while the pure `brain.memory` modules stay clean."""
    for path in (SRC / "ops").glob("*memory*.py"):
        assert not (_imports(path) & PROJECT_MODULES), path.name
    for path in (SRC / "chat").glob("*.py"):
        assert not (_imports(path) & PROJECT_MODULES), path.name
