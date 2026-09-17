"""The knowledge library, the learning review and the memory viewer over HTTP.

Driven through the real application, with the token machinery and the key source borrowed from
`tests/unit/test_api_routes.py`, for the reason `tests/unit/test_skill_routes.py` gives about
borrowing them. What is under test is three screens assembled from decisions
`brain.console.govern_estate` owns, so the rows here are the rows the tables would hold and the
readers are entitlement sets, and nothing in this file restates what those decisions decide.

**Every refusal has a sibling proving the permitted case is answered**, because a route that
refused everybody would satisfy every refusal and none of the positives.

**Two claims are held against something outside the module under test.** That the undo is the
only write on these three screens is read off the application's own OpenAPI document, and that
the review and the viewer read tables a migration creates is read off the migrations directory.

**The undo is driven through the real store over the stub session**, so what a test sees written
is the statement `brain.ops.memory_store` sends, and what the next reading shows is the stub
answering with the row that statement wrote. The ledger entry that insert leaves is a trigger's,
and `tests/unit/test_memory_store.py` follows it through a real database.

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
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Insert, create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BooleanClauseList

from brain import estate_routes
from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.govern_estate import UNDO_AUTHORITY
from brain.console.reach_view import Revision
from brain.console.reads import Plane, plane_capability
from brain.console.screens import screen
from brain.console.workspace import intersections_in
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.estate_routes import (
    MAX_ITEMS_CONSIDERED,
    MAX_LEARNINGS_CONSIDERED,
    MAX_MEMORIES_CONSIDERED,
    UNDO_PATH,
    UNDO_SAYS,
    LearningReviewView,
    LearningUndoneView,
    LibraryPage,
    LibraryRowView,
    MemoryTextView,
    RevisionView,
    SubjectMemoryView,
    TierOneView,
    TierRuleView,
    TierThreeView,
    TierTwoView,
    UndoAsked,
    inferred_about,
    retrievable_items,
    revision_view,
    stated_about,
    stored_memory,
)
from brain.identity.bearer import TokenAuthority
from brain.listing import MAX_PAGE_ROWS
from brain.memory.correction import Correction
from brain.memory.digest import COUNTING_FIELD_NAMES
from brain.memory.formation import RECALL_FLOOR, MemoryKind
from brain.memory.signals import Signal
from brain.memory.tiers import CHANGES_WHAT_ANYBODY_MAY_SEE, Change
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from brain.tables.agent import AgentRow
from brain.tables.knowledge import KnowledgeItemRow
from brain.tables.learning import CorrectionRow, LearningRow
from brain.tables.memory import AdaptiveMemoryRow, PersistentMemoryRow
from tests.fixtures.http_client import Response
from tests.unit.test_agent_routes import agent_row
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
UNDO = f"{API_PREFIX}{UNDO_PATH}"
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
#: grouping is withheld and no memory is recalled. `u_admin` also holds the undo authority
#: everywhere, and `u_elsewhere` holds the two content screens and the memories' capability
#: everywhere with the undo authority in finance only, which is a reader who sees a learning formed
#: in web and may not undo it. `u_prefix` holds all three screens with only
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
        UNDO_AUTHORITY,
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
    "u_elsewhere": (
        *_everywhere(LEARNING_READ, MEMORY_READ, CONTENT, CLIENT_NAME),
        Grant(capability=UNDO_AUTHORITY, scope=Scope.department("finance")),
    ),
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
    scope: Scope | None = None,
) -> PersistentMemoryRow:
    """One `mem.persistent` row: something a person stated."""
    return PersistentMemoryRow(
        id=memory_id,
        principal_id=subject,
        statement=statement,
        capability_tags=list(tags),
        scope=(scope or Scope.unrestricted()).model_dump(mode="json"),
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
    scope: Scope | None = None,
) -> AdaptiveMemoryRow:
    """One `mem.adaptive` row: something the system inferred, with the confidence it had."""
    return AdaptiveMemoryRow(
        id=memory_id,
        principal_id=subject,
        statement=statement,
        capability_tags=[CLIENT_NAME.value],
        scope=(scope or Scope.unrestricted()).model_dump(mode="json"),
        ent_hash="e" * 32,
        kind=MemoryKind.ADAPTIVE.value,
        formed_confidence=confidence,
        formed_at=formed_at or ago(hours=2),
    )


# ------------------------------------------------------------------- the stub session


def learnt(
    memory_id: str,
    *,
    change: Change = Change.PREFERENCE,
    tier: int = 1,
    agent_id: str | None = "desk",
    replaced_id: str | None = None,
    recorded_at: datetime | None = None,
) -> LearningRow:
    """One `mem.learning` row: what a memory proposed, under which agent, and what it replaced."""
    return LearningRow(
        memory_id=memory_id,
        change=change.value,
        tier=tier,
        subject="answer.length",
        agent_id=agent_id,
        replaced_id=replaced_id,
        evidence=["reasked"],
        recorded_at=recorded_at or ago(minutes=30),
    )


def marked(
    memory_id: str,
    *,
    by_id: str | None,
    prompted_by: Signal | None = Signal.CONTRADICTED,
    at: datetime | None = None,
) -> CorrectionRow:
    """One `mem.correction` row: a supersession when `by_id` names a memory, else a demotion."""
    return CorrectionRow(
        memory_id=memory_id,
        correction="superseded" if by_id is not None else "demoted",
        by_id=by_id,
        prompted_by=None if by_id is None or prompted_by is None else prompted_by.value,
        field=None if by_id is not None else "answer.length",
        recorded_by="u_seed",
        at=at or ago(minutes=20),
    )


class Stored:
    """What the stub database holds, and every statement it was asked."""

    def __init__(self) -> None:
        self.items: list[KnowledgeItemRow] = []
        self.stated: list[PersistentMemoryRow] = []
        self.inferred: list[AdaptiveMemoryRow] = []
        self.agents: list[AgentRow] = []
        self.learnings: list[LearningRow] = []
        self.corrections: list[CorrectionRow] = []
        self.statements: list[Any] = []


_STORED = Stored()


class StubResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> StubResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        return self._rows[0]


def _holds(clause: Any, row: Any) -> bool:
    """Whether a row satisfies a WHERE clause, read off the clause: equality, IN, AND and OR.

    Read rather than assumed, so a route that stopped narrowing a load is answered rows it did not
    ask for and a test sees them. A clause of any other shape is a statement nothing here expects.
    """
    if isinstance(clause, BooleanClauseList):
        found = [_holds(one, row) for one in clause.clauses]
        return any(found) if clause.operator is operators.or_ else all(found)
    value = getattr(row, clause.left.name)
    if clause.operator is operators.eq:
        return bool(value == clause.right.value)
    if clause.operator is operators.in_op:
        return value in clause.right.value
    raise AssertionError(f"a clause nothing here expects: {clause}")


def _bound(statement: Any, rows: list[Any]) -> list[Any]:
    """The rows a real database would return for a statement's `LIMIT`, honoured here.

    Honoured rather than ignored, so `truncated` is computed against a load that really came
    back full, and a route that stopped passing its bound would be answered every row.
    """
    limit = statement._limit
    return rows if limit is None else rows[:limit]


#: Each table the stub answers, where its rows are held and the order a load reads them in.
_ORDERS: dict[type, tuple[str, Any]] = {
    KnowledgeItemRow: ("items", lambda one: one.item_id),
    PersistentMemoryRow: ("stated", lambda one: (-one.formed_at.timestamp(), one.id)),
    AdaptiveMemoryRow: ("inferred", lambda one: (-one.formed_at.timestamp(), one.id)),
    AgentRow: ("agents", lambda one: one.id),
    LearningRow: ("learnings", lambda one: (-one.recorded_at.timestamp(), one.memory_id)),
    CorrectionRow: ("corrections", lambda one: one.at),
}


class StubSession(AsyncSession):
    """An `AsyncSession` answering the loads and the one write these routes make, and no other.

    Each load is told apart by the table it selects from and narrowed by its own WHERE clause. An
    insert into `mem.correction` is kept, so the next load reads the row the store wrote; the
    database's clock is the wall clock, for the module docstring's reason.
    """

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        _STORED.statements.append(statement)
        if isinstance(statement, Insert):
            assert getattr(statement.table, "fullname", None) == "mem.correction", statement
            _STORED.corrections.append(CorrectionRow(**statement.compile().params))
            return StubResult([])
        if not hasattr(statement, "column_descriptions"):
            # `SET TRANSACTION READ ONLY`, the revision lock and the trace settings select nothing.
            return StubResult([])
        table = statement.column_descriptions[0].get("entity")
        if table is None:
            # The store's `SELECT now()`.
            return StubResult([datetime.now(UTC)])
        held, order = _ORDERS[table]
        where = statement.whereclause
        rows = sorted(
            (one for one in getattr(_STORED, held) if where is None or _holds(where, one)),
            key=order,
        )
        return StubResult(_bound(statement, rows))

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


#: An `amr` a session carries when a second factor was used. An `admin:` capability is admitted
#: to a request only at that assurance, so the undo is exercised with it and refused without it.
SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}


def get(c: TestClient, pid: str, path: str, **params: Any) -> Response:
    response: Response = c.get(
        path, headers={"authorization": f"Bearer {token_for(pid)}"}, params=params or {}
    )
    return response


def get_strongly(c: TestClient, pid: str, path: str) -> Response:
    """A read by somebody signed in with a second factor, which is when an undo can be offered."""
    response: Response = c.get(
        path, headers={"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"}
    )
    return response


def post(
    c: TestClient,
    pid: str,
    path: str,
    body: Mapping[str, Any],
    claims: Mapping[str, object] = SECOND_FACTOR,
) -> Response:
    response: Response = c.post(
        path, headers={"authorization": f"Bearer {token_for(pid, claims=claims)}"}, json=dict(body)
    )
    return response


def writes(stored: Stored) -> list[Any]:
    """Every insert a test's requests sent, in order."""
    return [one for one in stored.statements if isinstance(one, Insert)]


def ids(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return [one["memory_id"] for one in rows]


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
    client: TestClient, stored: Stored, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a bound of two and two stored items the load is full, whatever the reader sees of
    it and whatever they searched for, and with a bound of three it is not.

    Delete this and `truncated` can be computed over the rows `library_rows` returned, which is
    a count of what the decision withheld spelled as a boolean: the scoped reader here sees one
    row and would be told there is no more exactly when there is. The search that matches
    nothing is `A_FILTER_ON_THE_SERVER_TURNS_A_TRUNCATION_FLAG_INTO_A_COUNT`: a load narrowed by
    it would turn the flag into a statement about what matched."""
    stored.items = [an_item("doc_finance", department="finance"), an_item("doc_web")]

    monkeypatch.setattr(estate_routes, "MAX_ITEMS_CONSIDERED", 2)
    full = get(client, "u_narrow", LIBRARY).json()
    searched = get(client, "u_narrow", LIBRARY, q="finance").json()
    monkeypatch.setattr(estate_routes, "MAX_ITEMS_CONSIDERED", 3)
    room = get(client, "u_narrow", LIBRARY).json()

    assert full["items"] == room["items"] == [{"item_id": "doc_web", "level": "department"}]
    assert full["truncated"] is True
    assert searched["truncated"] is True
    assert searched["items"] == []
    assert room["truncated"] is False


def test_the_library_searches_filters_and_pages_only_the_rows_the_reader_may_know_exist(
    client: TestClient, stored: Stored
) -> None:
    """Delete this and the library's search can reach the loaded items, so a department reader
    typing a finance document's reference is answered whether it exists; or the cursor can be
    computed over the load, so the last web document carries a cursor because finance has more.
    The positive half is the company-wide reader's walk."""
    stored.items = [
        an_item("doc_a"),
        an_item("doc_finance", department="finance"),
        an_item("doc_web"),
    ]

    withheld = get(client, "u_narrow", LIBRARY, q="doc_finance").json()
    narrow = get(client, "u_narrow", LIBRARY, limit=2).json()
    first = get(client, "u_admin", LIBRARY, limit=2).json()
    rest = get(client, "u_admin", LIBRARY, limit=2, cursor=first["next_cursor"]).json()
    by_level = get(client, "u_admin", LIBRARY, filter="level:department").json()

    assert withheld["items"] == [] and withheld["next_cursor"] is None
    assert narrow["next_cursor"] is None
    walked = [one["item_id"] for one in (*first["items"], *rest["items"])]
    assert walked == ["doc_a", "doc_finance", "doc_web"]
    assert rest["next_cursor"] is None
    assert [one["item_id"] for one in by_level["items"]] == ["doc_a", "doc_finance", "doc_web"]


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
    """A page larger than `brain.listing.MAX_PAGE_ROWS` is refused as a request, the largest page
    is answered, and the load a page is cut from never exceeds `MAX_ITEMS_CONSIDERED`.

    Delete this and a caller can ask for the whole table in one answer, or the load can follow the
    page size and stop being a constant."""
    assert get(client, "u_admin", LIBRARY, limit=MAX_PAGE_ROWS + 1).status_code == 422
    assert get(client, "u_admin", LIBRARY, limit=MAX_PAGE_ROWS).status_code == 200
    assert MAX_PAGE_ROWS < MAX_ITEMS_CONSIDERED


# ------------------------------------------------------- the learning review (M27.7.21)


def test_the_learning_review_answers_three_empty_tiers_on_an_install_that_has_learnt_nothing(
    client: TestClient,
) -> None:
    """The positive case over an empty store: a reader who may open the screen is answered the
    three tiers apart, the vocabulary that sorts them, the bound the load reads, and what an undo
    would write in each case.

    Delete this and every refusal below is satisfied by a route that refuses everybody."""
    response = get(client, "u_admin", LEARNING)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tier_one"] == []
    assert body["tier_two"] == []
    assert body["tier_three"] == []
    assert body["basis"] == "everyone"
    assert body["considered"] == MAX_LEARNINGS_CONSIDERED
    assert body["undo_says"] == {one.value: said for one, said in UNDO_SAYS.items()}
    assert set(body["undo_says"]) == {one.value for one in Correction}


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


def test_the_review_and_the_viewer_read_tables_a_migration_creates() -> None:
    """A migration creates `mem.learning` and `mem.correction`, and the memory tables the viewer
    reads.

    Held against the migrations directory rather than against the models, so a route reading a
    table no migration builds goes red here rather than on the first request after a deploy. Delete
    this and the review can be written against a model nothing ever created."""
    created = [
        found.group(1)
        for path in sorted((REPO / "migrations" / "versions").glob("*.py"))
        for found in re.finditer(r'create_table\(\s*"([a-z_]+)"', path.read_text(encoding="utf-8"))
    ]

    assert {"learning", "correction", "adaptive", "persistent"} <= set(created)


def test_a_visible_agents_tier_one_learning_is_listed_with_its_undo_offered_to_its_administrator(
    client: TestClient, stored: Stored
) -> None:
    """The positive case over stored rows: a tier-one learning of an agent every reader may see,
    formed from a memory the reader may recall, is listed in tier one, in effect, with its undo
    offered and saying it would restore the memory it replaced; a tier-two learning of the same
    agent is in tier two.

    Delete this and every refusal below is satisfied by a review that lists nothing, which is the
    screen as it was before a learning could be stored."""
    stored.agents = [agent_row("desk", capabilities=(CLIENT_NAME,))]
    stored.stated = [stated("m_before", "Prefers the long answer", formed_at=ago(hours=3))]
    stored.inferred = [
        inferred("m_learnt", "Prefers the short answer", formed_at=ago(hours=1)),
        inferred("m_rule", "Asks renewals by product", formed_at=ago(hours=2)),
    ]
    stored.learnings = [
        learnt("m_learnt", replaced_id="m_before"),
        learnt("m_rule", change=Change.FAST_PATH_RULE, tier=2),
    ]

    body = get_strongly(client, "u_admin", LEARNING).json()
    weak = get(client, "u_admin", LEARNING).json()

    assert [one["undo_offered"] for one in weak["tier_one"]] == [False]
    assert body["tier_one"] == [
        {
            "memory_id": "m_learnt",
            "change": "preference",
            "control_writes": "superseded",
            "learned_at": body["tier_one"][0]["learned_at"],
            "in_effect": True,
            "undo_offered": True,
        }
    ]
    assert ids(body["tier_two"]) == ["m_rule"]
    assert body["tier_three"] == []


def test_a_learning_the_reader_may_not_recall_is_absent_from_the_review_and_cannot_be_undone(
    client: TestClient, stored: Stored
) -> None:
    """A reader who holds the screen and not the capability the memory was formed under is shown
    the same bytes as for a review with nothing in it, and an undo of that memory is refused in the
    words an undo of a memory that does not exist is refused in.

    Delete this and the review lists a learning formed from a conversation the reader could not
    have read, which is the per-agent tab with its lens taken off."""
    stored.agents = [agent_row("desk", capabilities=(CLIENT_NAME,))]
    stored.inferred = [inferred("m_learnt", "Prefers the short answer")]
    stored.learnings = [learnt("m_learnt")]

    remembered = get(client, "u_narrow", LEARNING)
    refused = post(client, "u_narrow", UNDO, {"memory_id": "m_learnt"})
    stored.learnings = []
    absent = get(client, "u_narrow", LEARNING)
    missing = post(client, "u_narrow", UNDO, {"memory_id": "m_nothing"})

    assert remembered.status_code == absent.status_code == 200
    assert remembered.json()["tier_one"] == absent.json()["tier_one"] == []
    assert {k: v for k, v in remembered.json().items() if k != "as_of"} == {
        k: v for k, v in absent.json().items() if k != "as_of"
    }
    assert refused.status_code == missing.status_code == 404
    assert refused.json()["message"] == missing.json()["message"]
    assert writes(stored) == []


def test_a_learning_the_agents_ceiling_does_not_reach_is_absent_even_to_a_reader_who_may_recall_it(
    client: TestClient, stored: Stored
) -> None:
    """The learning is listed through an agent whose ceiling holds the memory's capability and
    absent through one whose ceiling does not, for the same reader.

    Delete this and the review is read at the caller's own reach rather than at their run of the
    agent, which is the lens this system never lets an agent drop."""
    stored.agents = [agent_row("desk", capabilities=(CLIENT_NAME,)), agent_row("blind")]
    stored.inferred = [
        inferred("m_through_desk", "Prefers the short answer"),
        inferred("m_through_blind", "Prefers email"),
    ]
    stored.learnings = [learnt("m_through_desk"), learnt("m_through_blind", agent_id="blind")]

    body = get(client, "u_admin", LEARNING).json()

    assert ids(body["tier_one"]) == ["m_through_desk"]
    assert post(client, "u_admin", UNDO, {"memory_id": "m_through_blind"}).status_code == 404


def test_an_undo_writes_the_correction_and_the_next_reading_no_longer_recalls_the_learning(
    client: TestClient, stored: Stored
) -> None:
    """**The leaf's sentence, followed through the route.** Before: the learnt memory is what the
    viewer shows as remembered, and the memory it replaced is not. The undo answers what it wrote,
    and the store's insert names the learning, the memory it restores, a person's refusal and who
    pressed it. After: the viewer shows the memory put back and not the learnt one, its history has
    the step with its diff and its trigger, and the review says the change is no longer in effect
    and offers no undo. A second undo writes nothing.

    Delete this and an undo can answer success for a row the viewer never reads, which is the
    control that renders and reaches nothing. The ledger entry the insert leaves is followed through
    a real database by `tests/unit/test_memory_store.py`."""
    stored.agents = [agent_row("desk", capabilities=(CLIENT_NAME,))]
    stored.stated = [stated("m_before", "Prefers the long answer", formed_at=ago(hours=3))]
    stored.inferred = [inferred("m_learnt", "Prefers the short answer", formed_at=ago(hours=1))]
    stored.learnings = [learnt("m_learnt", replaced_id="m_before")]
    stored.corrections = [marked("m_before", by_id="m_learnt", at=ago(hours=1))]
    before = get(client, "u_admin", MEMORY, subject="u_subject").json()

    undone = post(client, "u_admin", UNDO, {"memory_id": "m_learnt"})

    assert undone.status_code == 200, undone.text
    assert undone.json()["took_effect"] is True
    assert undone.json()["correction"] == "superseded"
    [insert] = writes(stored)
    assert {key: value for key, value in insert.compile().params.items() if key != "at"} == {
        "memory_id": "m_learnt",
        "correction": "superseded",
        "by_id": "m_before",
        "prompted_by": "rejected",
        "field": None,
        "recorded_by": "u_admin",
    }
    after = get(client, "u_admin", MEMORY, subject="u_subject").json()
    review = get_strongly(client, "u_admin", LEARNING).json()
    again = post(client, "u_admin", UNDO, {"memory_id": "m_learnt"})

    assert (ids(before["curated"]), ids(before["extracted"])) == ([], ["m_learnt"])
    assert (ids(after["curated"]), ids(after["extracted"])) == (["m_before"], [])
    restored = after["history"][-1]
    assert (restored["memory_id"], restored["replaced_id"]) == ("m_before", "m_learnt")
    assert (restored["trigger"], restored["correction"]) == ("rejected", "superseded")
    assert "-Prefers the short answer" in restored["diff"]
    assert "+Prefers the long answer" in restored["diff"]
    assert [(one["in_effect"], one["undo_offered"]) for one in review["tier_one"]] == [
        (False, False)
    ]
    assert again.status_code == 200
    assert again.json()["took_effect"] is False
    assert len(writes(stored)) == 1


def test_an_undo_of_a_learning_that_replaced_nothing_writes_a_demotion(
    client: TestClient, stored: Stored
) -> None:
    """The other half of `digest.undo`: nothing to restore, so the memory is demoted and the viewer
    stops showing it. Delete this and the route can offer only the restoring half, after which every
    learning formed from nothing is a learning nobody can undo."""
    stored.agents = [agent_row("desk", capabilities=(CLIENT_NAME,))]
    stored.inferred = [inferred("m_alone", "Asks on Mondays")]
    stored.learnings = [learnt("m_alone")]

    undone = post(client, "u_admin", UNDO, {"memory_id": "m_alone"})
    after = get(client, "u_admin", MEMORY, subject="u_subject").json()

    assert undone.json()["correction"] == "demoted"
    assert [one.compile().params["correction"] for one in writes(stored)] == ["demoted"]
    assert after["extracted"] == []
    assert [(one["memory_id"], one["correction"]) for one in after["history"]] == [
        ("m_alone", "demoted")
    ]


def test_the_undo_authority_is_matched_against_where_the_memory_was_formed(
    client: TestClient, stored: Stored
) -> None:
    """A reader holding the undo authority in finance and every read is offered the undo on a
    learning formed in finance and undoes it, and is shown a learning formed in web without the
    control and refused its undo.

    Delete this and `admin:learning` held anywhere undoes everything the reader can see, which puts
    one department's administrator in charge of what the system recalls for every other."""
    finance, web = Scope.department("finance"), Scope.department("web")
    stored.agents = [agent_row("desk", capabilities=(CLIENT_NAME,))]
    stored.inferred = [
        inferred("m_finance", "Prefers invoices by post", scope=finance),
        inferred("m_web", "Prefers the short answer", scope=web),
    ]
    stored.learnings = [learnt("m_finance"), learnt("m_web")]

    rows = {
        one["memory_id"]: one
        for one in get_strongly(client, "u_elsewhere", LEARNING).json()["tier_one"]
    }
    refused = post(client, "u_elsewhere", UNDO, {"memory_id": "m_web"})
    undone = post(client, "u_elsewhere", UNDO, {"memory_id": "m_finance"})

    assert (rows["m_finance"]["undo_offered"], rows["m_web"]["undo_offered"]) == (True, False)
    assert refused.status_code == 404
    assert undone.status_code == 200, undone.text
    assert [one.compile().params["memory_id"] for one in writes(stored)] == ["m_finance"]


def test_an_undo_is_refused_before_anything_is_read_to_a_caller_without_the_screen_or_the_authority(
    client: TestClient, unwired: TestClient, stored: Stored
) -> None:
    """A caller with no grant, a caller with the learning screen and no undo authority, the
    administrator signed in without a second factor, and a caller with no grant on an instance with
    no database are refused alike before a session is reached for; the administrator on that
    instance is told it is broken.

    Delete this and the order of the questions can move, after which a refusal on one instance and
    a fault on another is the deployment's state readable by anybody who can reach the port."""
    stored.agents = [agent_row("desk", capabilities=(CLIENT_NAME,))]
    stored.inferred = [inferred("m_learnt", "Prefers the short answer")]
    stored.learnings = [learnt("m_learnt")]

    nobody = post(client, "u_none", UNDO, {"memory_id": "m_learnt"})
    reader = post(client, "u_narrow", UNDO, {"memory_id": "m_learnt"})
    password_only = post(
        client, "u_admin", UNDO, {"memory_id": "m_learnt"}, claims={"amr": ["pwd"]}
    )
    bare = post(unwired, "u_none", UNDO, {"memory_id": "m_learnt"})
    fault = post(unwired, "u_admin", UNDO, {"memory_id": "m_learnt"})

    assert {
        nobody.status_code,
        reader.status_code,
        password_only.status_code,
        bare.status_code,
    } == {404}
    assert (
        nobody.json()["message"]
        == reader.json()["message"]
        == password_only.json()["message"]
        == bare.json()["message"]
    )
    assert stored.statements == []
    assert fault.status_code == 500
    assert set(fault.json()) >= {"message", "trace_id"}


def test_a_tier_two_learning_is_not_undone_from_the_review(
    client: TestClient, stored: Stored
) -> None:
    """A rule proving itself in shadow is promoted by agreement, not undone by a click. Delete this
    and the undo can mark a tier-two learning, which the review shows with no undo control, so the
    write arrives from a request no screen sends."""
    stored.agents = [agent_row("desk", capabilities=(CLIENT_NAME,))]
    stored.inferred = [inferred("m_rule", "Asks renewals by product")]
    stored.learnings = [learnt("m_rule", change=Change.FAST_PATH_RULE, tier=2)]

    assert post(client, "u_admin", UNDO, {"memory_id": "m_rule"}).status_code == 404
    assert writes(stored) == []


def test_an_undo_names_a_memory_by_its_id_and_nothing_else(client: TestClient) -> None:
    """A body naming no memory, a memory id wider than the column, and a body carrying which
    correction to write are refused as requests. Delete this and a caller can choose to demote a
    memory whose undo should have restored the one before it."""
    assert post(client, "u_admin", UNDO, {}).status_code == 422
    assert post(client, "u_admin", UNDO, {"memory_id": "m" * 27}).status_code == 422
    assert (
        post(client, "u_admin", UNDO, {"memory_id": "m_1", "correction": "demoted"}).status_code
        == 422
    )
    assert set(UndoAsked.model_fields) == {"memory_id"}


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


def test_a_memory_nothing_records_as_replacing_another_has_no_diff(
    client: TestClient, stored: Stored
) -> None:
    """Each readable memory with no learning record naming what it replaced is one history entry,
    oldest first, with no replaced memory, no diff, no trigger and no correction.

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

    Delete this and the projection can drop them, and the history says a memory changed and
    never why."""
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


def test_an_edit_is_shown_as_a_revision_with_its_diff_and_what_triggered_it(
    client: TestClient, stored: Stored
) -> None:
    """**The history leaf's sentence, over stored rows.** A memory whose learning record names the
    memory it replaced, with the supersession that marked the older one, is a revision carrying
    both statements' diff and the supersession's signal; what is remembered now is the newer
    statement alone.

    Delete this and the viewer can go on answering every revision with no diff and no trigger over a
    store that records both, which is the screen saying nothing changed when something did."""
    stored.stated = [
        stated("m_june", "Retainer ends in June", formed_at=ago(hours=3)),
        stated("m_september", "Retainer ends in September", formed_at=ago(hours=1)),
    ]
    stored.learnings = [learnt("m_september", replaced_id="m_june", agent_id=None)]
    stored.corrections = [marked("m_june", by_id="m_september", at=ago(hours=1))]

    body = get(client, "u_admin", MEMORY, subject="u_subject").json()

    assert ids(body["curated"]) == ["m_september"]
    assert [(one["memory_id"], one["replaced_id"]) for one in body["history"]] == [
        ("m_june", None),
        ("m_september", "m_june"),
    ]
    step = body["history"][1]
    assert (step["trigger"], step["correction"]) == ("contradicted", "superseded")
    assert step["diff"] == ["@@ -1 +1 @@", "-Retainer ends in June", "+Retainer ends in September"]


def test_a_revision_whose_older_side_the_reader_may_not_recall_is_shown_without_its_diff(
    client: TestClient, stored: Stored
) -> None:
    """The replaced memory was formed under a capability this reader lacks, so the revision is
    listed with no diff and nothing saying why, and a reader who holds both sees the diff.

    Delete this and the history is the one place a statement formed under wider tags reaches a
    reader who could not recall it, which is `brain.console.reach_view.
    A_DIFF_IS_TWO_DISCLOSURES_AND_THE_OLDER_ONE_IS_THE_ONE_NOBODY_CHECKS` at the route."""
    stored.stated = [
        stated(
            "m_secret",
            "Retainer is worth a lot",
            tags=("read:client.contract_value",),
            formed_at=ago(hours=3),
        ),
        stated("m_open", "Retainer renews yearly", formed_at=ago(hours=1)),
    ]
    stored.learnings = [learnt("m_open", replaced_id="m_secret", agent_id=None)]
    stored.corrections = [marked("m_secret", by_id="m_open", at=ago(hours=1))]

    narrow = get(client, "u_elsewhere", MEMORY, subject="u_subject").json()

    assert [(one["memory_id"], one["diff"]) for one in narrow["history"]] == [("m_open", [])]
    assert "Retainer is worth a lot" not in str(narrow)


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


def test_the_undo_is_the_only_write_on_the_three_screens(client: TestClient) -> None:
    """The application's own OpenAPI document declares GET on the three paths, POST on the undo,
    and nothing else under either screen.

    Delete this and an edit or an upload can be added with nothing behind it, which is the control
    `docs/admin-console.md` says is worse than none: it renders and reaches no row."""
    paths = client.get("/openapi.json").json()["paths"]

    for path in (LIBRARY, LEARNING, MEMORY):
        assert set(paths[path]) == {"get"}
    assert set(paths[UNDO]) == {"post"}
    assert [one for one in paths if one.startswith(f"{API_PREFIX}/govern/learning/")] == [UNDO]
    assert not [one for one in paths if one.startswith(f"{API_PREFIX}/govern/memory/")]


VIEWS: tuple[type[BaseModel], ...] = (
    LibraryRowView,
    LibraryPage,
    TierOneView,
    TierTwoView,
    TierThreeView,
    TierRuleView,
    LearningReviewView,
    UndoAsked,
    LearningUndoneView,
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
