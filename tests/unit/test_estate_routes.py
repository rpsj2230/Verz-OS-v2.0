"""The knowledge library, the learning review and the memory viewer over HTTP.

Driven through the real application, with the token machinery and the key source borrowed from
`tests/unit/test_api_routes.py`, for the reason `tests/unit/test_skill_routes.py` gives about
borrowing them. What is under test is three screens assembled from decisions
`brain.console.govern_estate` owns, so the rows here are the rows the tables would hold and the
readers are entitlement sets, and nothing in this file restates what those decisions decide.

**Every refusal has a sibling proving the permitted case is answered**, because a route that
refused everybody would satisfy every refusal and none of the positives.

**Two claims are held against something outside the module under test.** That there is no
write on these three screens is read off the application's own OpenAPI document, and that
nothing stores a correction is read off the migrations directory, so the flag saying so goes
red the day a migration creates one.

**The disclosure properties are compared byte for byte.** A reader who may not see an item or
recall a memory is shown the same response as a reader asking about something that was never
there, and that is asserted on `response.content` rather than on a count read off one of them.

The present is the wall clock here, and deliberately. The routes read `datetime.now` through
`brain.api_routes.asking`, and what is under test for the memory viewer is recall, which decays
from the instant a memory was formed. So a memory in this file is formed an hour or four
hundred days before the test runs, never on a date, and nothing here can go off on a schedule.

Task ids: M27.7.20, M27.7.21, M27.7.22
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from brain import estate_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.reach_view import Revision
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.workspace import intersections_in
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.estate_routes import (
    MAX_ITEMS_CONSIDERED,
    MAX_MEMORIES_CONSIDERED,
    LearningReviewView,
    LibraryPage,
    LibraryRowView,
    MemoryTextView,
    RevisionView,
    SubjectMemoryView,
    TierOneView,
    TierRuleView,
    TierThreeView,
    TierTwoView,
    inferred_about,
    recorded_corrections,
    recorded_learnings,
    retrievable_items,
    revision_view,
    stated_about,
    stored_memory,
)
from brain.identity.bearer import TokenAuthority
from brain.memory.correction import Correction
from brain.memory.digest import COUNTING_FIELD_NAMES
from brain.memory.formation import RECALL_FLOOR, MemoryKind
from brain.memory.signals import Signal
from brain.memory.tiers import CHANGES_WHAT_ANYBODY_MAY_SEE, Change
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.tables.knowledge import KnowledgeItemRow
from brain.tables.memory import AdaptiveMemoryRow, PersistentMemoryRow
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

LIBRARY = f"{API_PREFIX}/govern/library"
LEARNING = f"{API_PREFIX}/govern/learning"
MEMORY = f"{API_PREFIX}/govern/memory"

#: A PostgreSQL dialect to compile statements against, from an engine that never connects.
DIALECT = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: The repository root, for the one test that reads the migrations directory.
REPO = Path(__file__).resolve().parents[2]

DOCUMENT_READ = screen("library").read.requires
LEARNING_READ = screen("learning").read.requires
MEMORY_READ = screen("memory").read.requires
SCOPES_READ = screen("scopes").read.requires
EXISTENCE = plane_capability(Plane.EXISTENCE)
CONFIGURATION = plane_capability(Plane.CONFIGURATION)
CONTENT = plane_capability(Plane.CONTENT)

#: The capability every memory in this file was formed under, so recall has something to ask.
CLIENT_NAME = Capability(value="read:client.name")


def _everywhere(*capabilities: Capability) -> tuple[Grant, ...]:
    return tuple(Grant(capability=one, scope=Scope.unrestricted()) for one in capabilities)


#: What each person holds.
#:
#: `u_admin` holds every screen here, the Scopes screen and every plane, company-wide, and the
#: capability the memories were formed under: the widest reader. `u_narrow` holds the three
#: screens with the library scoped to web, the planes they need and nothing else, so the
#: grouping is withheld and no memory is recalled. `u_prefix` holds all three screens with only
#: the existence plane, which is the reader a bare capability check would let into a content
#: screen. `u_wide` holds the library and the Scopes screen with the second scoped to web, which
#: is a grant that passes `permitted` and still may not group. `u_none` holds nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_admin": _everywhere(
        DOCUMENT_READ,
        LEARNING_READ,
        MEMORY_READ,
        SCOPES_READ,
        CLIENT_NAME,
        EXISTENCE,
        CONFIGURATION,
        CONTENT,
    ),
    "u_narrow": (
        Grant(capability=DOCUMENT_READ, scope=Scope.department("web")),
        *_everywhere(LEARNING_READ, MEMORY_READ, EXISTENCE, CONTENT),
    ),
    "u_prefix": _everywhere(DOCUMENT_READ, LEARNING_READ, MEMORY_READ, EXISTENCE),
    "u_wide": (
        Grant(capability=SCOPES_READ, scope=Scope.department("web")),
        *_everywhere(DOCUMENT_READ, EXISTENCE, CONFIGURATION),
    ),
    "u_none": (),
    "u_elsewhere": (),
}


class Store:
    """A `brain.gate.resolve.EntitlementStore` over `GRANTS`."""

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


# ------------------------------------------------------------------------ the rows


def an_item(
    item_id: str,
    *,
    visibility: str = "department",
    department: str | None = "web",
    state: str = "published",
) -> KnowledgeItemRow:
    """One `know.item` row, shaped as that table's constraints admit."""
    return KnowledgeItemRow(
        item_id=item_id,
        title=f"The title of {item_id}",
        owner_id="u_steward",
        visibility=visibility,
        department=department,
        state=state,
        verified_by=None,
        verified_at=None,
        review_by=None,
        supersedes=None,
    )


def ago(**delta: float) -> datetime:
    """An instant before now. See the module docstring on why these are never dates."""
    return datetime.now(UTC) - timedelta(**delta)


def stated(
    memory_id: str,
    statement: str,
    *,
    subject: str = "u_subject",
    tags: tuple[str, ...] = (CLIENT_NAME.value,),
    kind: str = MemoryKind.PERSISTENT.value,
    formed_at: datetime | None = None,
) -> PersistentMemoryRow:
    """One `mem.persistent` row: something a person stated."""
    return PersistentMemoryRow(
        id=memory_id,
        principal_id=subject,
        statement=statement,
        capability_tags=list(tags),
        scope=Scope.unrestricted().model_dump(mode="json"),
        ent_hash="e" * 32,
        kind=kind,
        formed_at=formed_at or ago(hours=1),
    )


def inferred(
    memory_id: str,
    statement: str,
    *,
    subject: str = "u_subject",
    confidence: float = 0.9,
    formed_at: datetime | None = None,
) -> AdaptiveMemoryRow:
    """One `mem.adaptive` row: something the system inferred, with the confidence it had."""
    return AdaptiveMemoryRow(
        id=memory_id,
        principal_id=subject,
        statement=statement,
        capability_tags=[CLIENT_NAME.value],
        scope=Scope.unrestricted().model_dump(mode="json"),
        ent_hash="e" * 32,
        kind=MemoryKind.ADAPTIVE.value,
        formed_confidence=confidence,
        formed_at=formed_at or ago(hours=2),
    )


# ------------------------------------------------------------------- the stub session


class Stored:
    """What the stub database holds, and every statement it was asked."""

    def __init__(self) -> None:
        self.items: list[KnowledgeItemRow] = []
        self.stated: list[PersistentMemoryRow] = []
        self.inferred: list[AdaptiveMemoryRow] = []
        self.statements: list[Any] = []


_STORED = Stored()


class StubResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> StubResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


def _bound(statement: Any, rows: list[Any]) -> list[Any]:
    """The rows a real database would return for a statement's `LIMIT`, honoured here.

    Honoured rather than ignored, so `truncated` is computed against a load that really came
    back full, and a route that stopped passing its bound would be answered every row.
    """
    limit = statement._limit
    return rows if limit is None else rows[:limit]


class StubSession(AsyncSession):
    """An `AsyncSession` answering the three loads these routes make, and no other.

    Each load is told apart by the table it selects from. The WHERE clause is read off the
    statement rather than assumed: the library's states and the memory loads' subject are
    applied here, so a route that stopped narrowing its load would be answered rows it did not
    ask for and a test below would see them.
    """

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        _STORED.statements.append(statement)
        if not hasattr(statement, "column_descriptions"):
            # `brain.ops.replica_store` opens every console read with `SET TRANSACTION READ
            # ONLY`, which selects nothing.
            return StubResult([])
        table = statement.column_descriptions[0]["entity"]
        if table is KnowledgeItemRow:
            states = set(statement.whereclause.right.value)
            rows = sorted(
                (one for one in _STORED.items if one.state in states), key=lambda one: one.item_id
            )
            return StubResult(_bound(statement, rows))
        subject = statement.whereclause.right.value
        held: list[Any] = _STORED.stated if table is PersistentMemoryRow else _STORED.inferred
        remembered = sorted(
            (one for one in held if one.principal_id == subject),
            key=lambda one: (-one.formed_at.timestamp(), one.id),
        )
        return StubResult(_bound(statement, remembered))

    async def close(self) -> None:
        return None


@pytest.fixture
def stored() -> Iterator[Stored]:
    """A fresh store per test, so one test's rows are never another's evidence."""
    global _STORED
    _STORED = Stored()
    yield _STORED


def _wiring() -> GateWiring:
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER, audience=AUDIENCE, keys=Keys(), verify=verifier, directory=Directory()
        ),
        versions=Versions(),
        store=Store(),
        cache=NoCache(),
    )


@pytest.fixture
def client(stored: Stored) -> Iterator[TestClient]:
    """The real application, its router registration included, with the stub where the pool is.

    `console_reads` is cleared for `tests/unit/test_govern_routes.py`'s reason: the lifespan
    built one over whatever `DATABASE_URL` names, and CI names a real database.
    """
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        app.state.console_reads = None
        yield c


@pytest.fixture
def unwired(stored: Stored) -> Iterator[TestClient]:
    """The same application with no session factory at all."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = None
        app.state.console_reads = None
        yield c


def get(c: TestClient, pid: str, path: str, **params: Any) -> Response:
    response: Response = c.get(
        path, headers={"authorization": f"Bearer {token_for(pid)}"}, params=params or {}
    )
    return response


def item_ids(response: Response) -> list[str]:
    return [one["item_id"] for one in response.json()["items"]]


# ------------------------------------------------------------ the library (M27.7.20)


def test_the_library_lists_every_retrievable_item_with_how_widely_each_reaches(
    client: TestClient, stored: Stored
) -> None:
    """The positive case for every refusal below: three items at three levels, each named with
    its level, grouped by the departments they sit in for a reader who may be shown that.

    Delete this and every refusal here is satisfied by a route that lists nothing at all, which
    is the library of a company that has written nothing down."""
    stored.items = [
        an_item("doc_company", visibility="company", department="sales"),
        an_item("doc_web", visibility="department", department="web"),
        an_item("doc_mine", visibility="personal", department="web"),
    ]

    response = get(client, "u_admin", LIBRARY)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == [
        {"item_id": "doc_company", "level": "company"},
        {"item_id": "doc_mine", "level": "personal"},
        {"item_id": "doc_web", "level": "department"},
    ]
    assert body["departments"] == ["sales", "web"]
    assert body["truncated"] is False
    assert body["total"] is None
    assert body["only_existence_and_reach_are_shown"] is True
    assert body["freshness_and_use_are_not_measured"] is True


def test_a_library_row_carries_neither_the_title_nor_the_owner_nor_the_department(
    client: TestClient, stored: Stored
) -> None:
    """The row the API sends has the two keys `LibraryRow` has and no third, whatever the
    stored row holds.

    Delete this and a route edit copying the title or the owner on to the response passes every
    other test here, and a screen registered on the existence plane starts showing what a
    document says and who stewards it, which is the decision `brain.console.govern_estate`
    refused to make."""
    stored.items = [an_item("doc_web")]

    row = get(client, "u_admin", LIBRARY).json()["items"][0]

    assert set(row) == {"item_id", "level"}
    assert set(LibraryRowView.model_fields) == {"item_id", "level"}


def test_an_item_in_a_department_the_reader_does_not_reach_changes_nothing_on_their_page(
    client: TestClient, stored: Stored
) -> None:
    """A reader whose document grant is web is answered the same bytes whether or not finance
    holds a document.

    Delete this and the library narrows nothing, which is the existence plane of every
    department handed to whoever can open the screen, and the sibling assertion that the admin
    does see the finance item proves the absence is the reader's reach and not a row nobody
    can see."""
    stored.items = [an_item("doc_web")]
    without = get(client, "u_narrow", LIBRARY)

    stored.items.append(an_item("doc_finance", department="finance"))
    with_hidden = get(client, "u_narrow", LIBRARY)

    assert without.status_code == with_hidden.status_code == 200
    assert with_hidden.content == without.content
    assert item_ids(with_hidden) == ["doc_web"]
    assert item_ids(get(client, "u_admin", LIBRARY)) == ["doc_finance", "doc_web"]


def test_an_item_that_names_no_department_is_known_only_to_a_company_wide_reader(
    client: TestClient, stored: Stored
) -> None:
    """A company item with no department is placed nowhere, so a department-scoped reader is
    not told it exists and a company-wide one is.

    Delete this and `placed_item` can put such an item in reach of every scoped grant, which is
    the fail-open direction `brain.console.govern.NOWHERE` exists to refuse: a row with no place
    matching a scope because nothing was there to fail the match."""
    stored.items = [an_item("doc_everyone", visibility="company", department=None)]

    assert item_ids(get(client, "u_narrow", LIBRARY)) == []
    assert item_ids(get(client, "u_admin", LIBRARY)) == ["doc_everyone"]


def test_the_grouping_is_null_for_a_reader_who_may_not_be_shown_it_and_never_a_short_list(
    client: TestClient, stored: Stored
) -> None:
    """The grouping is the departments list for a reader holding the Scopes screen company-wide,
    and null, rather than an empty or shortened list, for one holding it at a department's scope.

    Delete this and a scoped reader is shown the departments they happen to reach under a
    heading reading every department, which `brain.console.govern_estate.
    A_LISTING_HEADED_EVERY_DEPARTMENT_AND_SHOWING_FOUR_IS_A_CLAIM_NOBODY_CAN_CHECK` refuses. Both
    readers see the same rows, so the basis is the only thing that differs."""
    stored.items = [an_item("doc_web"), an_item("doc_sales", department="sales")]

    wide = get(client, "u_wide", LIBRARY).json()
    admin = get(client, "u_admin", LIBRARY).json()

    assert wide["items"] == admin["items"]
    assert wide["departments"] is None
    assert admin["departments"] == ["sales", "web"]


def test_a_superseded_or_archived_item_is_not_in_the_library(
    client: TestClient, stored: Stored
) -> None:
    """Only the states an item may be retrieved from are listed.

    Delete this and an archived item appears at the level it used to reach, which says it still
    reaches that audience; the stub applies the statement's own state list, so a route that
    dropped the filter is answered the archived rows."""
    stored.items = [
        an_item("doc_draft", state="draft"),
        an_item("doc_live", state="published"),
        an_item("doc_old", state="superseded"),
        an_item("doc_gone", state="archived"),
    ]

    assert item_ids(get(client, "u_admin", LIBRARY)) == ["doc_draft", "doc_live"]


def test_truncated_is_the_load_coming_back_full_and_not_the_rows_that_survived(
    client: TestClient, stored: Stored
) -> None:
    """With a bound of two and two stored items the load is full, whatever the reader sees of
    it, and with a bound of three it is not.

    Delete this and `truncated` can be computed over the rows `library_rows` returned, which is
    a count of what the decision withheld spelled as a boolean: the scoped reader here sees one
    row and would be told there is no more exactly when there is."""
    stored.items = [an_item("doc_finance", department="finance"), an_item("doc_web")]

    full = get(client, "u_narrow", LIBRARY, limit=2).json()
    room = get(client, "u_narrow", LIBRARY, limit=3).json()

    assert full["items"] == room["items"] == [{"item_id": "doc_web", "level": "department"}]
    assert full["truncated"] is True
    assert room["truncated"] is False


def test_the_library_load_asks_for_retrievable_states_in_reference_order_and_bounded() -> None:
    """The statement, compiled against PostgreSQL.

    Delete this and the order can be dropped, after which the rows that fall off a full load
    are whichever the database returns first and two readings of one table are two pages."""
    sql = str(retrievable_items(7).compile(dialect=DIALECT, compile_kwargs={"literal_binds": True}))

    assert "FROM know.item" in sql
    assert "know.item.state IN ('draft', 'published')" in sql
    assert "ORDER BY know.item.item_id" in sql
    assert "LIMIT 7" in sql


def test_the_library_asks_for_no_more_than_its_bound(client: TestClient, stored: Stored) -> None:
    """A page larger than `MAX_ITEMS_CONSIDERED` is refused as a request, and the bound itself
    is answered.

    Delete this and a caller can ask the database for the whole table in one statement."""
    assert get(client, "u_admin", LIBRARY, limit=MAX_ITEMS_CONSIDERED + 1).status_code == 422
    assert get(client, "u_admin", LIBRARY, limit=MAX_ITEMS_CONSIDERED).status_code == 200


# ------------------------------------------------------- the learning review (M27.7.21)


def test_the_learning_review_answers_three_empty_tiers_and_says_nothing_is_recorded(
    client: TestClient,
) -> None:
    """The positive case: a reader who may open the screen is answered the three tiers apart,
    the vocabulary that sorts them, and the two sentences about what this install stores.

    Delete this and every refusal below is satisfied by a route that refuses everybody."""
    response = get(client, "u_admin", LEARNING)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_one"] == []
    assert body["tier_two"] == []
    assert body["tier_three"] == []
    assert body["basis"] == "everyone"
    assert body["learnings_are_not_recorded"] is True
    assert body["undo_is_not_writable"] is True


def test_tier_three_is_null_for_a_reader_who_may_not_be_grouped_by_department(
    client: TestClient,
) -> None:
    """A reader without the Scopes screen's grant gets `tier_three` null and basis own; the
    admin gets a list and basis everyone.

    Delete this and the one per-reader decision on this screen is gone: the list of where gated
    changes were routed is the routing table for every access decision in the company, and
    `learning_review` withholds it on the narrower basis only if the route passes that basis
    through."""
    narrow = get(client, "u_narrow", LEARNING).json()
    admin = get(client, "u_admin", LEARNING).json()

    assert narrow["basis"] == "own"
    assert narrow["tier_three"] is None
    assert admin["tier_three"] == []


def test_the_tier_vocabulary_puts_every_change_once_at_the_tier_its_reach_needs(
    client: TestClient,
) -> None:
    """Four tiers in order, every change named exactly once, and every change that alters who
    may see what at tier three.

    Asserted against `CHANGES_WHAT_ANYBODY_MAY_SEE`, which `brain.memory.tiers` writes out
    separately from the map the route reads, so this is not the map compared with itself.
    Delete this and a change drawn under the wrong tier on this screen tells an administrator a
    scope widening applies by itself."""
    tiers = get(client, "u_admin", LEARNING).json()["tiers"]

    assert [one["tier"] for one in tiers] == [0, 1, 2, 3]
    named = [change for one in tiers for change in one["changes"]]
    assert sorted(named) == sorted(one.value for one in Change)
    assert len(named) == len(set(named))
    assert {one.value for one in CHANGES_WHAT_ANYBODY_MAY_SEE} <= set(tiers[3]["changes"])
    assert "preference" in tiers[1]["changes"]


def test_the_flag_saying_no_correction_is_stored_agrees_with_the_migrations() -> None:
    """No migration creates a table for a supersession, a demotion or a learning's tier, and the
    route says so; `recorded_learnings` and `recorded_corrections` are empty.

    Held against the migrations directory rather than against the constant, so the day a
    migration creates a correction table this goes red and whoever wrote it has to decide what
    the undo control and the history's diffs now say. Delete this and the page keeps telling an
    administrator that nothing is recorded after something is."""
    created = [
        found.group(1)
        for path in sorted((REPO / "migrations" / "versions").glob("*.py"))
        for found in re.finditer(r'create_table\(\s*"([a-z_]+)"', path.read_text(encoding="utf-8"))
    ]
    about_learning = [
        one for one in created if re.search(r"correction|supersession|demotion|learning", one)
    ]

    assert about_learning == []
    assert "adaptive" in created
    recorded = recorded_learnings()
    assert recorded.visible == ()
    assert dict(recorded.tier_one) == {}
    assert dict(recorded.tier_two) == {}
    assert dict(recorded.tier_three) == {}
    assert recorded_corrections() == ((), ())


# -------------------------------------------------------- the memory viewer (M27.7.22)


def test_the_memory_viewer_shows_a_subjects_memory_split_by_where_it_came_from(
    client: TestClient, stored: Stored
) -> None:
    """The positive case: a stated memory under curated, an inferred one under extracted, each
    in its own words, and a history entry for each.

    Delete this and every refusal below is satisfied by a route that returns nothing, which is
    the opaque store `brain.console.reach_view` says memory must never be."""
    stored.stated = [stated("m_stated", "Prefers invoices by post")]
    stored.inferred = [inferred("m_inferred", "Usually asks about renewals on Mondays")]

    response = get(client, "u_admin", MEMORY, subject="u_subject")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["subject_id"] == "u_subject"
    assert [one["statement"] for one in body["curated"]] == ["Prefers invoices by post"]
    # The recollection's confidence, rather than the formed one or a constant. A stated memory
    # does not decay (`formation.A_STATED_MEMORY_DOES_NOT_DECAY`), so it is still certain an
    # hour on; the inferred one, formed at 0.9 two hours ago, has decayed a little and not at
    # all to the floor.
    assert body["curated"][0]["confidence"] == 1.0
    assert [one["statement"] for one in body["extracted"]] == [
        "Usually asks about renewals on Mondays"
    ]
    assert 0.89 < body["extracted"][0]["confidence"] < 0.9
    assert sorted(one["memory_id"] for one in body["history"]) == ["m_inferred", "m_stated"]
    assert body["corrections_are_not_recorded"] is True
    assert body["edit_is_not_writable"] is True
    assert body["considered_per_kind"] == MAX_MEMORIES_CONSIDERED


def test_a_memory_the_reader_may_not_recall_answers_what_a_person_nobody_remembers_answers(
    client: TestClient, stored: Stored
) -> None:
    """A reader who holds the screen and not the capability a memory was formed under is shown
    the same bytes for a person with memories as for a person with none.

    Delete this and the viewer tells a reader that the system knows something about a person,
    which is the fact the recall check exists to withhold. The admin's answer about the same
    person proves the memory is there."""
    stored.stated = [stated("m_stated", "Prefers invoices by post")]

    remembered = get(client, "u_narrow", MEMORY, subject="u_subject")
    stored.stated = []
    absent = get(client, "u_narrow", MEMORY, subject="u_subject")

    assert remembered.status_code == absent.status_code == 200
    assert remembered.content == absent.content
    stored.stated = [stated("m_stated", "Prefers invoices by post")]
    assert get(client, "u_admin", MEMORY, subject="u_subject").json()["curated"] != []


def test_the_viewer_shows_only_the_person_asked_about(client: TestClient, stored: Stored) -> None:
    """Two people's memories are stored and the answer about one of them names only theirs.

    Delete this and the load can drop its subject, after which the viewer is the directory of
    what the system knows about everybody that `brain.console.govern_estate.
    A_MEMORY_VIEWER_OVER_EVERY_SUBJECT_IS_A_DIRECTORY_OF_PEOPLE` refuses. The stub applies the
    statement's own subject, so a route that stopped keying the load is answered both."""
    stored.stated = [
        stated("m_one", "Prefers email", subject="u_one"),
        stated("m_two", "Prefers a call", subject="u_two"),
    ]

    body = get(client, "u_admin", MEMORY, subject="u_one").json()

    assert [one["memory_id"] for one in body["curated"]] == ["m_one"]
    assert [one["memory_id"] for one in body["history"]] == ["m_one"]


def test_an_inferred_memory_below_the_recall_floor_is_absent_and_a_fresh_one_is_shown(
    client: TestClient, stored: Stored
) -> None:
    """An inferred memory formed four hundred days ago has decayed below the floor and is not
    shown; one formed an hour ago at the same confidence is.

    Delete this and the adaptive row's own confidence can be dropped on the way to recall, after
    which a guess the system stopped trusting a year ago reads on the viewer as though it were
    fresh."""
    stored.inferred = [
        inferred("m_old", "Asked about hosting once", formed_at=ago(days=400)),
        inferred("m_new", "Asks about hosting weekly", formed_at=ago(hours=1)),
    ]

    extracted = get(client, "u_admin", MEMORY, subject="u_subject").json()["extracted"]

    assert [one["memory_id"] for one in extracted] == ["m_new"]
    assert all(one["confidence"] >= RECALL_FLOOR for one in extracted)


def test_an_inferred_memory_is_recalled_at_the_confidence_it_was_formed_with(
    client: TestClient, stored: Stored
) -> None:
    """An inferred memory formed an hour ago at a confidence under the floor is not shown, and a
    stated one of the same age is.

    Delete this and the adaptive row is handed to recall as certain, which is
    `STATED_CONFIDENCE` applied to the wrong table: every weak inference would read on the
    viewer as something a person said."""
    stored.stated = [stated("m_stated", "Prefers invoices by post", formed_at=ago(hours=1))]
    stored.inferred = [
        inferred("m_weak", "Might prefer invoices by post", confidence=0.2, formed_at=ago(hours=1))
    ]

    body = get(client, "u_admin", MEMORY, subject="u_subject").json()

    assert body["extracted"] == []
    assert [one["memory_id"] for one in body["curated"]] == ["m_stated"]


def test_a_row_that_does_not_describe_a_showable_memory_is_skipped_rather_than_failing_the_screen(
    client: TestClient, stored: Stored
) -> None:
    """A session-kind row, a row of an unknown kind and a row whose capability tag the type
    refuses are each skipped, and the good row beside them is still shown.

    Delete this and one malformed row answers 500 for every reader of that person's memory,
    which takes the viewer away from the person who came to find out what the system believes."""
    stored.stated = [
        stated("m_good", "Prefers invoices by post"),
        stated("m_session", "Said this in passing", kind=MemoryKind.SESSION.value),
        stated("m_unknown", "Written by something else", kind="rumour"),
        stated("m_badtag", "Tagged wrongly", tags=("not a capability",)),
    ]

    response = get(client, "u_admin", MEMORY, subject="u_subject")

    assert response.status_code == 200, response.text
    assert [one["memory_id"] for one in response.json()["curated"]] == ["m_good"]


def test_stored_memory_refuses_each_row_a_viewer_cannot_show_and_keeps_a_good_one() -> None:
    """The loader on its own: `None` for the three malformed shapes and a stored memory with the
    row's statement for a good one.

    Delete this and the skip can widen to every row or narrow to none without the route test
    above being able to say which, because that test sees only what reached the response."""
    good = stored_memory(stated("m_good", "Prefers invoices by post"))

    assert good is not None
    assert good[1] == "Prefers invoices by post"
    assert good[0].formation.kind is MemoryKind.PERSISTENT
    assert good[0].replaced_id is None
    assert stored_memory(stated("m_session", "x", kind=MemoryKind.SESSION.value)) is None
    assert stored_memory(stated("m_unknown", "x", kind="rumour")) is None
    assert stored_memory(stated("m_badtag", "x", tags=("not a capability",))) is None


def test_every_revision_has_no_diff_because_nothing_records_what_a_memory_replaced(
    client: TestClient, stored: Stored
) -> None:
    """Each readable memory is one history entry, oldest first, with no replaced memory, no
    diff, no trigger and no correction.

    Delete this and a diff invented from two statements that happen to sit side by side could
    appear, which is a viewer inferring why something changed by comparing text, the thing
    `brain.console.reach_view.revisions` says it must never do."""
    stored.stated = [
        stated("m_first", "Retainer ends in June", formed_at=ago(hours=3)),
        stated("m_second", "Retainer ends in September", formed_at=ago(hours=1)),
    ]

    history = get(client, "u_admin", MEMORY, subject="u_subject").json()["history"]

    assert [one["memory_id"] for one in history] == ["m_first", "m_second"]
    for one in history:
        assert one["replaced_id"] is None
        assert one["diff"] == []
        assert one["trigger"] is None
        assert one["correction"] is None


def test_a_subject_made_of_white_space_is_refused_as_a_request_and_a_real_one_is_answered(
    client: TestClient,
) -> None:
    """Blank and white-space subjects are 422s naming the parameter, a missing one is too, and
    an ordinary principal id is answered.

    Delete this and a subject of spaces reaches `subject_memory`, which refuses it by raising,
    and the refusal arrives as a 500: a request mistake reported as a broken server."""
    assert get(client, "u_admin", MEMORY, subject="   ").status_code == 422
    assert get(client, "u_admin", MEMORY, subject="").status_code == 422
    assert get(client, "u_admin", MEMORY).status_code == 422
    assert get(client, "u_admin", MEMORY, subject="u_subject").status_code == 200


def test_the_memory_loads_are_keyed_by_the_subject_newest_first_and_bounded() -> None:
    """Both statements, compiled against PostgreSQL.

    Delete this and the order can be dropped, after which the memories that fall outside the
    bound are whichever the database returns first rather than the oldest."""
    for statement, table in (
        (stated_about("u_subject", 5), "mem.persistent"),
        (inferred_about("u_subject", 5), "mem.adaptive"),
    ):
        sql = str(statement.compile(dialect=DIALECT, compile_kwargs={"literal_binds": True}))
        assert f"FROM {table}" in sql
        assert f"WHERE {table}.principal_id = 'u_subject'" in sql
        assert f"ORDER BY {table}.formed_at DESC, {table}.id" in sql
        assert "LIMIT 5" in sql


def test_the_viewer_reads_the_bound_it_states_and_drops_the_oldest_beyond_it(
    client: TestClient, stored: Stored
) -> None:
    """One more stated memory than the bound: the answer holds exactly as many as
    `considered_per_kind` says, and the one left out is the oldest.

    Delete this and the bound the page states and the bound the load applies can drift apart,
    after which the sentence under the history is a claim about a load nobody made."""
    stored.stated = [
        stated(f"m_{index:03d}", f"Statement {index}", formed_at=ago(hours=index + 1))
        for index in range(MAX_MEMORIES_CONSIDERED + 1)
    ]

    body = get(client, "u_admin", MEMORY, subject="u_subject").json()

    assert len(body["curated"]) == body["considered_per_kind"] == MAX_MEMORIES_CONSIDERED
    assert f"m_{MAX_MEMORIES_CONSIDERED:03d}" not in {one["memory_id"] for one in body["curated"]}


def test_a_revision_is_sent_with_its_trigger_and_correction_as_their_words() -> None:
    """A revision carrying a trigger and a correction is projected with both, as the words of
    their vocabularies, and one carrying neither is projected with two nulls.

    Nothing stores a correction yet, so no route test can reach a revision with either. Delete
    this and the projection can drop them, and the day a store exists the history says a
    memory changed and never why."""
    moved = Revision(
        memory_id="m_new",
        replaced_id="m_old",
        at=ago(hours=1),
        diff=("-June", "+September"),
        trigger=Signal.CONTRADICTED,
        correction=Correction.SUPERSEDED,
    )

    view = revision_view(moved)
    still = revision_view(replace(moved, trigger=None, correction=None))

    assert (view.trigger, view.correction) == ("contradicted", "superseded")
    assert view.diff == ("-June", "+September")
    assert view.replaced_id == "m_old"
    assert (still.trigger, still.correction) == (None, None)


# --------------------------------------------------------------- all three screens


@pytest.mark.parametrize(("path", "params"), [(LIBRARY, {}), (MEMORY, {"subject": "u_subject"})])
def test_a_caller_with_no_grant_cannot_tell_whether_this_process_has_a_database(
    client: TestClient, unwired: TestClient, path: str, params: dict[str, str]
) -> None:
    """A caller holding nothing is refused in the same words on an instance with a database and
    on one without, and a caller holding the screen is told the second is broken.

    Delete this and the screen's question and the session can be swapped by somebody tidying,
    after which the refusal on one instance and the fault on the other is the deployment's state
    readable by anybody who can reach the port."""
    wired = get(client, "u_none", path, **params)
    bare = get(unwired, "u_none", path, **params)

    assert wired.status_code == bare.status_code == 404
    # Everything but the trace id, which is per request by design.
    assert {k: v for k, v in wired.json().items() if k != "trace_id"} == {
        k: v for k, v in bare.json().items() if k != "trace_id"
    }
    fault = get(unwired, "u_admin", path, **params)
    assert fault.status_code == 500
    # The application's own error body, which is `Failed` handled, and not the bare text an
    # unhandled exception is answered with: a route that stopped raising `Failed` would reach
    # the same status through an AttributeError.
    assert set(fault.json()) >= {"message", "trace_id"}


@pytest.mark.parametrize(
    ("path", "params"),
    [(LEARNING, {}), (MEMORY, {"subject": "u_subject"})],
)
def test_a_content_screen_is_refused_to_a_reader_holding_its_capability_and_only_existence(
    client: TestClient, path: str, params: dict[str, str]
) -> None:
    """The learning review and the memory viewer are the content plane, so a reader holding each
    screen's capability with only the existence plane is refused, and the library, which is the
    existence plane, answers the same reader.

    Delete this and a route can check the bare capability, which answers the statements people
    made and the learnings the system formed to somebody trusted only to know things exist."""
    assert get(client, "u_prefix", path, **params).status_code == 404
    assert get(client, "u_prefix", LIBRARY).status_code == 200


@pytest.mark.parametrize("path", [LIBRARY, LEARNING])
def test_a_caller_with_no_grant_is_refused_each_screen_and_its_holder_is_answered(
    client: TestClient, path: str
) -> None:
    """Nobody is answered without the screen's grant, and the refusal names nothing but the
    screen's own place in the menu.

    Delete this and one of the three routes can open for anybody who can authenticate."""
    refused = get(client, "u_none", path)

    assert refused.status_code == 404
    assert "u_none" not in refused.text
    assert get(client, "u_admin", path).status_code == 200


def test_none_of_the_three_screens_has_a_write(client: TestClient) -> None:
    """The application's own OpenAPI document declares GET and nothing else on the three paths.

    Delete this and an undo, an edit or an upload can be added with nothing behind it, which is
    the control `docs/admin-console.md` says is worse than none: it renders and reaches no row."""
    paths = client.get("/openapi.json").json()["paths"]

    for path in (LIBRARY, LEARNING, MEMORY):
        assert set(paths[path]) == {"get"}
    assert not [one for one in paths if one.startswith(f"{API_PREFIX}/govern/learning/")]
    assert not [one for one in paths if one.startswith(f"{API_PREFIX}/govern/memory/")]


VIEWS: tuple[type[BaseModel], ...] = (
    LibraryRowView,
    LibraryPage,
    TierOneView,
    TierTwoView,
    TierThreeView,
    TierRuleView,
    LearningReviewView,
    MemoryTextView,
    RevisionView,
    SubjectMemoryView,
)


def test_no_view_carries_a_field_that_would_count_what_was_withheld() -> None:
    """Every response model's own fields are checked against both vocabularies of counting
    names, and the one inherited `total` is proved never to be set.

    Read off `model_fields`, because `brain.ops.jobs.hidden_count_fields` reads dataclass fields
    and finds nothing on a pydantic model. Delete this and a `hidden` or `withheld` field added
    to make a page friendlier is the subtraction the whole system refuses."""
    forbidden = NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT | COUNTING_FIELD_NAMES
    for view in VIEWS:
        own = set(view.model_fields) - ({"total"} if view is LibraryPage else set())
        assert not own & forbidden, view.__name__
    assert LibraryPage(items=[]).total is None


def test_nothing_in_this_module_computes_a_reach() -> None:
    """Delete this and a route here can intersect two entitlement sets of its own, which is a
    second implementation of the invariant, and the copy on a screen is the one nobody audits."""
    assert intersections_in(inspect.getsource(estate_routes)) == ()
