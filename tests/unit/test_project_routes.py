"""A person's own projects over the real application: who may reach one, and what the switch gates.

The store is a faithful in-memory stand-in with the same ownership and putting-away rules as
`brain.ops.project_store.StoredProjects`; the same rules against PostgreSQL and row-level security
are the install check in `tests/unit/test_acceptance_checks_member_projects.py`. Every refusal has a
sibling that succeeds.

Task ids: M40.7.7
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, Grant
from brain.core.scope import Scope
from brain.member.shell import member_capability
from brain.member_projects import MOST_ITEMS, MOST_PROJECTS, Project, ProjectItem
from brain.ops.project_store import ProjectFullError
from tests.fixtures.console_http import gate_wiring, headers

#: Far outside any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
NOW = datetime(2999, 1, 1, 9, 0, tzinfo=UTC)

ADA = "u_wide"
BEN = "u_narrow"
NOBODY = "u_none"
#: The member screen's own read and the member content plane it is admitted by, as a member holds.
MEMBER = (
    Grant(capability=member_capability("home"), scope=Scope.unrestricted()),
    Grant(capability=Capability(value="read:member.content"), scope=Scope.unrestricted()),
)
GRANTS = {ADA: MEMBER, BEN: MEMBER, NOBODY: ()}
BASE = f"{API_PREFIX}/me/projects"
A_FILE = "doc_report.1"


@dataclass
class _Rows:
    project: Project
    owner: str
    items: dict[tuple[str, str], datetime] = field(default_factory=dict)


class Memory:
    """The rules of `StoredProjects`, kept in a dict."""

    def __init__(self) -> None:
        self.rows: dict[str, _Rows] = {}

    async def create(self, owner: str, name: str) -> Project:
        if (
            sum(1 for one in self.rows.values() if one.owner == owner and not one.project.archived)
            >= MOST_PROJECTS
        ):
            raise ProjectFullError
        made = Project(project_id=str(uuid.uuid4()), name=name, created_at=NOW)
        self.rows[made.project_id] = _Rows(made, owner)
        return made

    async def projects(self, owner: str, *, archived: bool = False) -> tuple[Project, ...]:
        return tuple(
            one.project
            for one in self.rows.values()
            if one.owner == owner and one.project.archived == archived
        )

    async def one(
        self, owner: str, project_id: str
    ) -> tuple[Project, tuple[ProjectItem, ...]] | None:
        held = self.rows.get(project_id)
        if held is None or held.owner != owner:
            return None
        return held.project, tuple(ProjectItem(k, r, at) for (k, r), at in held.items.items())

    async def rename(self, owner: str, project_id: str, name: str) -> bool:
        held = self.rows.get(project_id)
        if held is None or held.owner != owner:
            return False
        held.project = Project(project_id, name, held.project.created_at, held.project.archived_at)
        return True

    async def archive(self, owner: str, project_id: str, at: datetime) -> bool:
        held = self.rows.get(project_id)
        if held is None or held.owner != owner or held.project.archived:
            return False
        held.project = Project(project_id, held.project.name, held.project.created_at, at)
        return True

    async def add(self, owner: str, project_id: str, kind: str, ref: str) -> bool:
        held = self.rows.get(project_id)
        if held is None or held.owner != owner or held.project.archived:
            return False
        if len(held.items) >= MOST_ITEMS:
            raise ProjectFullError
        held.items.setdefault((kind, ref), NOW)
        return True

    async def remove(self, owner: str, project_id: str, kind: str, ref: str) -> bool:
        held = self.rows.get(project_id)
        if held is None or held.owner != owner:
            return False
        return held.items.pop((kind, ref), None) is not None


class _Threads:
    """The caller's own threads: ADA has one, BEN has none."""

    async def thread(self, principal_id: str, thread_id: str) -> Any:
        if principal_id == ADA and thread_id == "0" * 8 + "-0000-0000-0000-" + "0" * 12:

            class _One:
                title = "What does the report say"

            return _One()
        return None


A_THREAD = "0" * 8 + "-0000-0000-0000-" + "0" * 12


@dataclass
class Console:
    client: TestClient
    store: Memory
    switched_on: list[bool]
    readable: set[str]

    def get(self, who: str, path: str = "") -> Any:
        return self.client.get(BASE + path, headers=headers(who))

    def post(self, who: str, path: str, body: dict[str, Any]) -> Any:
        return self.client.post(BASE + path, json=body, headers=headers(who))

    def make(self, who: str, name: str = "Quarter") -> str:
        made = self.post(who, "", {"name": name})
        assert made.status_code == 201, made.text
        return str(made.json()["project_id"])


@pytest.fixture
def console(monkeypatch: pytest.MonkeyPatch) -> Iterator[Console]:
    """The real application, projects switched on, over the in-memory store."""
    store = Memory()
    switched_on = [True]
    readable = {A_FILE}

    async def is_on(_sessions: object) -> bool:
        return switched_on[0]

    class Reads:
        records: tuple[str, ...]

        def __init__(self, records: tuple[str, ...]) -> None:
            self.records = records

    def reading(_records: object) -> Any:
        async def read(request: Any, *, entitlement: Any, now: Any) -> Reads:
            del entitlement, now
            return Reads(("passage",) if request.document_id in readable else ())

        return read

    monkeypatch.setattr("brain.project_routes.projects_are_on", is_on)
    monkeypatch.setattr("brain.project_routes._store", lambda _request: store)
    monkeypatch.setattr("brain.project_routes.threads_of", lambda _state: _Threads())
    monkeypatch.setattr("brain.project_routes.reader", reading)
    monkeypatch.setattr("brain.project_routes.SessionRowSource", lambda _sessions: object())
    monkeypatch.setattr("brain.project_routes.sessions_of", lambda _request: object())
    app = create_app(Settings(env="development"))
    with TestClient(app) as client:
        app.state.gate = gate_wiring(GRANTS)
        app.state.db_sessions = None
        yield Console(client, store, switched_on, readable)


def test_a_person_makes_names_fills_and_puts_away_a_project_of_their_own(console: Console) -> None:
    """The positive case for every refusal below: make, list, rename, add a thread and a file,
    read the project back with the thread's title, take the file out, and put it away.

    Delete this and every refusal is satisfied by routes that refuse everybody."""
    project_id = console.make(ADA)
    assert console.post(ADA, f"/{project_id}/rename", {"name": "  Q3   plan "}).status_code == 200
    assert (
        console.post(ADA, f"/{project_id}/items", {"kind": "thread", "ref": A_THREAD}).status_code
        == 201
    )
    assert (
        console.post(ADA, f"/{project_id}/items", {"kind": "file", "ref": A_FILE}).status_code
        == 201
    )

    listed = console.get(ADA).json()
    assert [(one["project_id"], one["name"]) for one in listed["projects"]] == [
        (project_id, "Q3 plan")
    ]
    shown = console.get(ADA, f"/{project_id}").json()
    assert {(one["kind"], one["ref"], one["title"]) for one in shown["items"]} == {
        ("thread", A_THREAD, "What does the report say"),
        ("file", A_FILE, ""),
    }

    assert (
        console.post(
            ADA, f"/{project_id}/items/remove", {"kind": "file", "ref": A_FILE}
        ).status_code
        == 200
    )
    assert [one["kind"] for one in console.get(ADA, f"/{project_id}").json()["items"]] == ["thread"]
    assert console.post(ADA, f"/{project_id}/archive", {}).status_code == 200
    assert console.get(ADA).json()["projects"] == []
    assert console.get(ADA, f"/{project_id}").status_code == 404


def test_somebody_elses_project_is_answered_as_one_never_made_on_every_route(
    console: Console,
) -> None:
    """Ben, holding the same grant, is told the same sentence for Ada's project as for an id that
    was never made, on the read, the rename, the archive, the add and the remove, and nothing of
    Ada's changes. A person holding nothing is refused alike.

    Delete this and a project's existence leaks by the difference in what a stranger is told, or
    a colleague changes another person's project."""
    mine = console.make(ADA)
    never = str(uuid.uuid4())
    calls: tuple[Callable[[str, str], Any], ...] = (
        lambda who, pid: console.get(who, f"/{pid}"),
        lambda who, pid: console.post(who, f"/{pid}/rename", {"name": "Taken"}),
        lambda who, pid: console.post(who, f"/{pid}/archive", {}),
        lambda who, pid: console.post(who, f"/{pid}/items", {"kind": "file", "ref": A_FILE}),
        lambda who, pid: console.post(who, f"/{pid}/items/remove", {"kind": "file", "ref": A_FILE}),
    )
    for call in calls:
        theirs, nothing = call(BEN, mine), call(BEN, never)
        assert theirs.status_code == nothing.status_code == 404
        assert theirs.json()["message"] == nothing.json()["message"]
        assert call(NOBODY, mine).status_code == 404
    assert console.get(BEN).json()["projects"] == []
    assert [one["name"] for one in console.get(ADA).json()["projects"]] == ["Quarter"]
    assert console.get(ADA, f"/{mine}").status_code == 200


def test_with_the_switch_off_nothing_new_is_made_and_nothing_made_is_trapped(
    console: Console,
) -> None:
    """Off, making a project and adding to one are refused in a sentence; the list, the read, the
    rename, taking something out and putting a project away still work, and the list says it is off.

    Delete this and either a switched-off install makes projects, or turning the switch off locks
    people out of seeing and tidying what they made."""
    project_id = console.make(ADA)
    console.post(ADA, f"/{project_id}/items", {"kind": "file", "ref": A_FILE})
    console.switched_on[0] = False

    assert console.post(ADA, "", {"name": "Another"}).status_code == 409
    assert (
        console.post(ADA, f"/{project_id}/items", {"kind": "thread", "ref": A_THREAD}).status_code
        == 409
    )
    listed = console.get(ADA).json()
    assert listed["switched_on"] is False and len(listed["projects"]) == 1
    assert console.get(ADA, f"/{project_id}").status_code == 200
    assert console.post(ADA, f"/{project_id}/rename", {"name": "Renamed"}).status_code == 200
    assert (
        console.post(
            ADA, f"/{project_id}/items/remove", {"kind": "file", "ref": A_FILE}
        ).status_code
        == 200
    )
    assert console.post(ADA, f"/{project_id}/archive", {}).status_code == 200


def test_only_a_thread_of_their_own_and_a_file_they_can_read_may_be_listed(
    console: Console,
) -> None:
    """A thread that is not the caller's, a file the caller cannot read and one that does not exist
    are the one 404, so the answer says nothing of which exist; the same file listed once it is
    readable succeeds. A project put away takes nothing more.

    Delete this and a person lists somebody's thread or a document they may not read, or learns by
    the difference in the refusal that it exists."""
    project_id = console.make(ADA)
    other = console.make(BEN)
    unreadable = console.post(ADA, f"/{project_id}/items", {"kind": "file", "ref": "doc_secret"})
    missing = console.post(ADA, f"/{project_id}/items", {"kind": "file", "ref": "doc_absent"})
    not_mine = console.post(BEN, f"/{other}/items", {"kind": "thread", "ref": A_THREAD})
    odd = console.post(ADA, f"/{project_id}/items", {"kind": "file", "ref": "not/an/item"})
    assert unreadable.status_code == missing.status_code == not_mine.status_code == 404
    assert odd.status_code == 404
    assert unreadable.json()["message"] == missing.json()["message"]

    console.readable.add("not/an/item")
    assert (
        console.post(
            ADA, f"/{project_id}/items", {"kind": "file", "ref": "not/an/item"}
        ).status_code
        == 404
    )
    console.readable.add("doc_secret")
    assert (
        console.post(ADA, f"/{project_id}/items", {"kind": "file", "ref": "doc_secret"}).status_code
        == 201
    )
    console.post(ADA, f"/{project_id}/archive", {})
    assert (
        console.post(ADA, f"/{project_id}/items", {"kind": "file", "ref": A_FILE}).status_code
        == 404
    )


def test_a_name_that_is_blank_is_refused_in_words_and_a_full_shelf_says_so(
    console: Console,
) -> None:
    """A blank name is a sentence rather than a project called nothing, and the fifty-first active
    project is refused in words; putting one away makes room. Delete this and a project can be made
    with no name, or the number of projects is unbounded."""
    assert console.post(ADA, "", {"name": "   "}).status_code == 422
    for number in range(MOST_PROJECTS):
        console.make(ADA, f"P{number}")
    assert console.post(ADA, "", {"name": "One more"}).status_code == 422
    first = console.get(ADA).json()["projects"][0]["project_id"]
    console.post(ADA, f"/{first}/archive", {})
    assert console.post(ADA, "", {"name": "One more"}).status_code == 201


def test_no_view_carries_a_count_of_anything() -> None:
    """The views list the caller's own projects and items and have no field counting anything
    hidden, left out or unreadable. Delete this and a count of what the person can no longer read
    can be added to a view without anyone deciding to."""
    from brain.project_routes import (
        MemberProjectDetailView,
        MemberProjectItemView,
        MemberProjectsView,
        MemberProjectView,
    )

    names = {
        name
        for view in (
            MemberProjectsView,
            MemberProjectView,
            MemberProjectDetailView,
            MemberProjectItemView,
        )
        for name in view.model_fields
    }
    assert names == {
        "projects",
        "switched_on",
        "project_id",
        "name",
        "created_at",
        "items",
        "kind",
        "ref",
        "title",
        "added_at",
    }


def test_a_project_lists_no_more_than_it_may_and_a_blank_new_name_is_refused(
    console: Console,
) -> None:
    """The two hundred and first thing is refused in words and taking one out makes room; renaming
    to a blank is a sentence. Delete this and a project's list is unbounded, or a rename can empty a
    name."""
    project_id = console.make(ADA)
    held = console.store.rows[project_id]
    for number in range(MOST_ITEMS):
        held.items[("file", f"doc_{number}")] = NOW
    over = console.post(ADA, f"/{project_id}/items", {"kind": "file", "ref": A_FILE})
    assert over.status_code == 422
    assert (
        console.post(
            ADA, f"/{project_id}/items/remove", {"kind": "file", "ref": "doc_0"}
        ).status_code
        == 200
    )
    assert (
        console.post(ADA, f"/{project_id}/items", {"kind": "file", "ref": A_FILE}).status_code
        == 201
    )
    assert console.post(ADA, f"/{project_id}/rename", {"name": "  "}).status_code == 422
