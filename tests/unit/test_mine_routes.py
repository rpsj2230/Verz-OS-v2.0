"""My workspace over HTTP: what the person asking has asked, kept and been given.

Driven through the real application with the token machinery borrowed from
`tests/unit/test_api_routes.py`, and the rows shaped by the helpers the agent and estate route tests
already use, for the reason `tests/unit/test_estate_routes.py` gives about borrowing them.

**The stub database honours every WHERE clause it is handed, read off the statement.** Each load is
answered from rows belonging to two people, so a route that stopped narrowing a load to the person
asking would be answered the other person's rows and a test below would see them.

**The member grant is spelled out here**, so a member screen repointed at another capability is a
failure in this file rather than a constant compared with itself. So is its plane, which is the
member surface's own since 2026-09-17: `read:member.content`, never the console's
`read:console.content`, whose holder is refused below.

The present is the wall clock, because the route reads it through `brain.api_routes.asking` and a
month, a day and recall are all measured from it. Rows here are an hour old, never dated.

Task ids: M27.7.28, M16.4.2
"""

from __future__ import annotations

import operator
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import operators
from sqlalchemy.sql.functions import FunctionElement

from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.own_things import own_scope
from brain.console.reads import Plane, plane_capability
from brain.console.screens import SCREENS
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.knowledge.item import RETRIEVABLE_STATES
from brain.knowledge.search import PRINCIPAL_SETTING
from brain.member.shell import DISCLOSURE_PREFIX
from brain.memory.digest import Learning, Undo, undo
from brain.memory.review import Edit, edit
from brain.memory.signals import Signal
from brain.mine_routes import (
    A_PERSON_UNDOES_WHAT_WAS_LEARNT_FROM_THEM_ON_THEIR_SIGN_IN_ALONE,
    FORGET_AND_EDIT_SAY,
    LEARNING_UNDO_PATH,
    MAX_OWN_RUNS,
    MORE_SPEND_THAN_THIS_PAGE_READS,
    month_start,
)
from brain.ops.budgets import BudgetLevel, BudgetPeriod
from brain.tables.adoption import QuestionAskedRow
from brain.tables.agent import AgentRow
from brain.tables.budget import BudgetVersionRow
from brain.tables.knowledge import KnowledgeItemRow
from brain.tables.learning import LearningRow
from brain.tables.memory import AdaptiveMemoryRow, PersistentMemoryRow
from brain.tables.spend import SpendActualRow
from tests.fixtures.http_client import Response
from tests.unit.test_agent_routes import agent_row, spend_row
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
from tests.unit.test_estate_routes import CLIENT_NAME, an_item, inferred, learnt, stated

WORKSPACE = f"{API_PREFIX}/me/workspace"

#: The member screen's capability and the plane it is registered on, written out.
MEMBER_HOME = Capability(value="read:member.home")
CONTENT = Capability(value="read:member.content")

#: The console's content plane, which opened this page until 2026-09-17 and opens it no longer.
CONSOLE_CONTENT = plane_capability(Plane.CONTENT)

#: The one grant a sign-in binding writes, spelled out: the member surface over one's own things.
MEMBER_SURFACE = Capability(value="read:member.*")

ME = "u_narrow"
SOMEBODY_ELSE = "u_wide"


def _everywhere(*capabilities: Capability) -> tuple[Grant, ...]:
    return tuple(Grant(capability=one, scope=Scope.unrestricted()) for one in capabilities)


#: `u_narrow` is a member who administers nothing: the member grant, its plane, and the capability
#: their memories were formed under. `u_wide` is the same without the recall capability.
#: `u_admin` holds every console screen's capability and the console's content plane and not the
#: member grant. `u_prefix` holds the member grant with no member plane, and the console's content
#: plane over everything in its place. `u_elsewhere` holds exactly what a sign-in binding writes
#: and nothing else.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_narrow": _everywhere(MEMBER_HOME, CONTENT, CLIENT_NAME),
    "u_wide": _everywhere(MEMBER_HOME, CONTENT),
    "u_admin": _everywhere(*{one.read.requires for one in SCREENS}, CONSOLE_CONTENT),
    "u_prefix": _everywhere(MEMBER_HOME, CONSOLE_CONTENT),
    "u_none": (),
    "u_elsewhere": (Grant(capability=MEMBER_SURFACE, scope=own_scope("u_elsewhere")),),
}


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


def ago(**delta: float) -> datetime:
    return datetime.now(UTC) - timedelta(**delta)


def question(principal_id: str, trace: str, at: datetime | None = None) -> QuestionAskedRow:
    return QuestionAskedRow(
        trace_id=trace,
        principal_id=principal_id,
        principal_kind="human",
        channel="web",
        department="web",
        at=at or ago(minutes=5),
    )


def ceiling(subject: str, period: BudgetPeriod, minor: int) -> BudgetVersionRow:
    return BudgetVersionRow(
        level=BudgetLevel.USER.value,
        subject=subject,
        period=period.value,
        ceiling_minor=minor,
        version=1,
        author="u_admin",
        effective_from=datetime(2019, 1, 1, tzinfo=UTC),
        reason="",
        alert_fractions=[0.5],
    )


#: The states `know.items_stewarded_by_the_session` returns. Held to the migration's list.
RETRIEVABLE: frozenset[str] = frozenset(one.value for one in RETRIEVABLE_STATES)

#: Every row the stub database holds, keyed by table class. Replaced per test.
ROWS: dict[type, list[Any]] = {}

_OPERATORS: Mapping[Any, Callable[[Any, Any], bool]] = {
    operators.eq: operator.eq,
    operators.ge: operator.ge,
    operators.le: operator.le,
    operators.in_op: lambda value, allowed: value in allowed,
}


def _admitted(statement: Any, row: Any) -> bool:
    """Whether a row satisfies every clause of a statement's WHERE, read off the statement."""
    where = statement.whereclause
    if where is None:
        return True
    clauses = getattr(where, "clauses", None) or [where]
    return all(
        _OPERATORS[one.operator](getattr(row, one.left.name), one.right.value) for one in clauses
    )


class StubResult:
    def __init__(self, rows: Sequence[Any]) -> None:
        self._rows = list(rows)

    def scalars(self) -> StubResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalar_one(self) -> int:
        return len(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None


def _function_called(statement: Any) -> tuple[str, list[Any]] | None:
    """The function a statement selects, or selects from, with its arguments, or None."""
    expression = statement.column_descriptions[0].get("expr")
    for one in (expression, *statement.get_final_froms()):
        called = getattr(one, "element", one)
        if isinstance(called, FunctionElement):
            return str(getattr(called, "name", "")), [
                getattr(arg, "value", None) for arg in called.clauses
            ]
    return None


class StubSession(AsyncSession):
    """Answers each load by its table, and the stewardship read as `0069`'s function answers it.

    The function is answered from its contract, the rows whose owner is the principal this
    transaction set and whose state is retrievable, in reference order and bounded; that the
    function keeps the contract is `tests/unit/test_application_reads_db.py`'s, against a server.
    """

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if not hasattr(statement, "column_descriptions"):
            return StubResult([])
        called = _function_called(statement)
        if called is not None and called[0] == "set_config":
            name, value, _local = called[1]
            self.info[name] = value
            return StubResult([value])
        if called is not None and called[0] == "items_stewarded_by_the_session":
            (limit,) = called[1]
            owner = self.info.get(PRINCIPAL_SETTING)
            found = sorted(
                (
                    row
                    for row in ROWS.get(KnowledgeItemRow, [])
                    if row.owner_id == owner and row.state in RETRIEVABLE
                ),
                key=lambda row: row.item_id,
            )
            return StubResult(found[:limit])
        entity = statement.column_descriptions[0]["entity"]
        if entity is None:
            # The count of questions selects a function, so its table is read off its FROM.
            entity = QuestionAskedRow
            assert QuestionAskedRow.__table__ in statement.get_final_froms()
        found = [row for row in ROWS.get(entity, []) if _admitted(statement, row)]
        limit = statement._limit
        return StubResult(found if limit is None else found[:limit])

    async def close(self) -> None:
        return None


@pytest.fixture
def rows() -> Iterator[dict[type, list[Any]]]:
    ROWS.clear()
    yield ROWS


@pytest.fixture
def client(rows: dict[type, list[Any]]) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer=ISSUER,
                audience=AUDIENCE,
                keys=Keys(),
                verify=verifier,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(),
            cache=NoCache(),
        )
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        app.state.console_reads = None
        yield c


def get(c: TestClient, pid: str) -> Response:
    response: Response = c.get(WORKSPACE, headers={"authorization": f"Bearer {token_for(pid)}"})
    return response


def two_people(rows: dict[type, list[Any]]) -> None:
    """The same things held by the person asking and by somebody else."""
    rows[QuestionAskedRow] = [
        question(ME, "t1"),
        question(ME, "t2"),
        question(SOMEBODY_ELSE, "t3"),
    ]
    rows[AgentRow] = [agent_row("quoting")]
    rows[SpendActualRow] = [
        spend_row("quoting", ME, minor=300, at=ago(minutes=30)),
        spend_row("quoting", SOMEBODY_ELSE, minor=9000, at=ago(minutes=30)),
    ]
    mine = an_item("doc_mine")
    mine.owner_id = ME
    rows[KnowledgeItemRow] = [mine, an_item("doc_theirs")]
    rows[PersistentMemoryRow] = [
        stated("mem_mine", "Hours before dates", subject=ME),
        stated("mem_theirs", "Something about somebody else", subject=SOMEBODY_ELSE),
    ]
    rows[AdaptiveMemoryRow] = [inferred("mem_guess", "Short answers", subject=ME)]
    rows[BudgetVersionRow] = [
        ceiling(ME, BudgetPeriod.MONTH, 1000),
        ceiling(SOMEBODY_ELSE, BudgetPeriod.MONTH, 50),
    ]


# ------------------------------------------------------------------------ the answers
def test_a_member_sees_what_they_asked_kept_and_were_given_and_nothing_of_anybody_elses(
    client: TestClient, rows: dict[type, list[Any]]
) -> None:
    """**The page.** Two questions, one agent used once, a monthly ceiling with their own spend
    against it, the item they steward, the two memories formed from their own conversations, and
    the line read off their grants. Every row the other person holds is absent.

    Delete this and a route that stopped narrowing any one load passes every refusal below."""
    two_people(rows)

    response = get(client, ME)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["principal_id"] == ME
    assert body["asked"]["questions"] == 2
    assert datetime.fromisoformat(body["asked"]["since"]) == month_start(
        datetime.fromisoformat(body["asked"]["since"])
    )
    assert [(one["agent_id"], one["uses"], one["provision"]) for one in body["agents"]] == [
        ("quoting", 1, "provided")
    ]
    assert body["budget"] == [
        {
            "period": "month",
            "ceiling_minor": 1000,
            "spent_minor": 300,
            "headroom_minor": 700,
            "alerts_crossed": [],
        }
    ]
    assert body["budget_unread"] == ""
    assert body["knowledge"] == [
        {"item_id": "doc_mine", "level": "department", "department": "web"}
    ]
    assert sorted((one["memory_id"], one["stated"]) for one in body["learned"]) == [
        ("mem_guess", False),
        ("mem_mine", True),
    ]
    assert body["learned_undo"] == FORGET_AND_EDIT_SAY
    assert body["can_ask_about"].startswith(DISCLOSURE_PREFIX)


def test_a_memory_formed_from_their_own_conversation_is_absent_once_they_no_longer_reach_it(
    client: TestClient, rows: dict[type, list[Any]]
) -> None:
    """Ownership admits the row and recall admits the words. `u_wide` formed a memory under a
    capability they do not hold now, and it is absent from their own page.

    Delete this and the page could read ownership as permission, showing somebody the text of a
    memory formed while they held a grant since revoked."""
    rows[PersistentMemoryRow] = [stated("mem_lost", "A client's name", subject=SOMEBODY_ELSE)]

    body = get(client, SOMEBODY_ELSE).json()

    assert body["learned"] == []


def test_a_spend_load_that_came_back_full_shows_no_budget_rather_than_a_short_one(
    client: TestClient, rows: dict[type, list[Any]]
) -> None:
    """Delete this and a busy month shows a ceiling beside an undercounted spend, which is
    headroom the person does not have on the page they check before spending."""
    rows[SpendActualRow] = [
        spend_row("quoting", ME, minor=1, at=ago(minutes=1)) for _ in range(MAX_OWN_RUNS)
    ]
    rows[BudgetVersionRow] = [ceiling(ME, BudgetPeriod.MONTH, 1000)]

    body = get(client, ME).json()

    assert body["budget"] is None
    assert body["budget_unread"] == MORE_SPEND_THAN_THIS_PAGE_READS


# ------------------------------------------------------------------------ the refusals
def test_the_page_opens_on_the_member_grant_and_on_no_administrative_grant(
    client: TestClient, rows: dict[type, list[Any]]
) -> None:
    """**Administers nothing, as a property.** Every console screen's capability and the console's
    content plane opens nothing here; the member grant without the member surface's own plane opens
    nothing either, even beside the console's content plane over everything, which opened it until
    2026-09-17; the member grant with its own plane opens the page. A refusal is the same whatever
    the database holds, for each caller: the administrator's sign-in has no second factor and is
    told so, before and after, and the other caller is told it could not be found, before and after.

    Delete this and the page could be gated on an administrative capability, which is a personal
    screen only administrators can open, or on nothing, which is `permitted` skipped."""
    for pid in ("u_admin", "u_prefix", "u_none"):
        assert get(client, pid).status_code == 404, pid
    empty = {pid: {**get(client, pid).json(), "trace_id": ""} for pid in ("u_admin", "u_prefix")}
    two_people(rows)
    for pid, refused in empty.items():
        assert {**get(client, pid).json(), "trace_id": ""} == refused, pid
    assert get(client, ME).status_code == 200


def test_the_grant_a_sign_in_binding_writes_opens_the_page_on_its_own(
    client: TestClient, rows: dict[type, list[Any]]
) -> None:
    """**The owner's goal, over HTTP.** A person holding nothing but the member surface over their
    own things, which is what `brain.identity.sign_in_binding` writes, opens their workspace and it
    is theirs. Delete this and binding a sign-in can go back to opening a page that refuses the
    person it was bound for, and the way round it is a console content grant again."""
    two_people(rows)

    response = get(client, "u_elsewhere")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["principal_id"] == "u_elsewhere"
    assert body["asked"]["questions"] == 0
    assert body["knowledge"] == []


def test_there_is_no_way_to_ask_about_somebody_else() -> None:
    """The route takes no parameter naming a person. Delete this and a `subject` query parameter
    added for an administrator's convenience turns a personal page into a directory."""
    app = create_app(Settings(env="development"))
    operation = app.openapi()["paths"][WORKSPACE]["get"]

    assert operation.get("parameters", []) == []
    assert set(app.openapi()["paths"][WORKSPACE]) == {"get"}


# ------------------------------------------------------------ forgetting and editing
FORGET = f"{API_PREFIX}/me/memory/forget"
EDIT = f"{API_PREFIX}/me/memory/edit"


class KeptRecords:
    """`brain.ops.memory_store.MemoryRecords` deciding with the domain and writing nothing."""

    def __init__(self) -> None:
        self.undone: list[tuple[Learning, str]] = []
        self.edited: list[tuple[Learning, Learning, str, str]] = []

    async def undo(self, learning: Learning, *, actor: str, trace_id: str, ent_hash: str) -> Undo:
        self.undone.append((learning, actor))
        return undo(learning, at=datetime.now(UTC))

    async def edit(
        self,
        learning: Learning,
        replacement: Learning,
        statement: str,
        *,
        prompted_by: Signal,
        actor: str,
        trace_id: str,
        ent_hash: str,
    ) -> Edit:
        self.edited.append((learning, replacement, statement, actor))
        return edit(learning, replacement, at=datetime.now(UTC), prompted_by=prompted_by)


@pytest.fixture
def records(client: TestClient) -> KeptRecords:
    kept = KeptRecords()
    client.app.state.memory_records = kept  # type: ignore[attr-defined]
    return kept


def post(c: TestClient, pid: str, path: str, body: dict[str, str]) -> Response:
    response: Response = c.post(
        path, json=body, headers={"authorization": f"Bearer {token_for(pid)}"}
    )
    return response


def memories_with_records(rows: dict[type, list[Any]]) -> None:
    """Two people's memories, each with the learning record a conversation leaves."""
    two_people(rows)
    rows[LearningRow] = [
        learnt("mem_mine", agent_id=None),
        learnt("mem_guess", agent_id=None),
        learnt("mem_theirs", agent_id=None),
    ]


def test_a_member_forgets_a_memory_formed_from_their_own_words(
    client: TestClient, rows: dict[type, list[Any]], records: KeptRecords
) -> None:
    """**A person reads, edits and forgets what is remembered about them** (M16.4.2, M16.7.7's
    person's half). Forget reaches the store the Learning screen's undo writes through, with their
    own memory and their own name, and answers what it wrote.

    Delete this and the forget control can answer success with nothing handed to the store."""
    memories_with_records(rows)

    response = post(client, ME, FORGET, {"memory_id": "mem_mine"})

    assert response.status_code == 200, response.text
    assert response.json()["took_effect"] is True
    assert [(one.memory_id, actor) for one, actor in records.undone] == [("mem_mine", ME)]


def test_a_member_edits_a_memory_and_the_replacement_changes_the_words_and_nothing_else(
    client: TestClient, rows: dict[type, list[Any]], records: KeptRecords
) -> None:
    """The replacement names the memory it replaces, keeps its person, place, capabilities, kind
    and change, and carries what they wrote. Delete this and an edit could hand a memory to
    somebody else or move it somewhere more readers reach."""
    memories_with_records(rows)

    response = post(client, ME, EDIT, {"memory_id": "mem_mine", "statement": "Dates before hours"})

    assert response.status_code == 200, response.text
    body = response.json()
    [(original, replacement, statement, actor)] = records.edited
    assert (body["took_effect"], body["replacement_id"]) == (True, replacement.memory_id)
    assert (statement, actor, replacement.replaced_id) == ("Dates before hours", ME, "mem_mine")
    assert replacement.formation.principal_id == original.formation.principal_id == ME
    assert replacement.formation.scope == original.formation.scope
    assert replacement.formation.capabilities == original.formation.capabilities
    assert replacement.formation.kind is original.formation.kind
    assert replacement.memory_id != original.memory_id


def test_somebody_elses_memory_is_refused_as_a_missing_one_and_reaches_no_store(
    client: TestClient, rows: dict[type, list[Any]], records: KeptRecords
) -> None:
    """Forget and edit on another person's memory, on one that does not exist, on a statement of
    white space, and by somebody without the member grant are the one 404, and nothing reaches the
    store. Delete this and a person could forget or rewrite what is remembered about somebody else
    by its id."""
    memories_with_records(rows)

    refused = [
        post(client, ME, FORGET, {"memory_id": "mem_theirs"}),
        post(client, ME, FORGET, {"memory_id": "mem_nothing"}),
        post(client, ME, EDIT, {"memory_id": "mem_theirs", "statement": "Mine now"}),
        post(client, ME, EDIT, {"memory_id": "mem_mine", "statement": "   "}),
        post(client, "u_admin", FORGET, {"memory_id": "mem_mine"}),
    ]

    assert [one.status_code for one in refused] == [404] * 5
    assert len({one.json()["message"] for one in refused[:4]}) == 1
    assert (records.undone, records.edited) == ([], [])


# ------------------------------------------------------------ the digest's undo (M16.5.1)
UNDO = f"{API_PREFIX}{LEARNING_UNDO_PATH}"


def test_a_person_holding_no_grant_at_all_undoes_what_was_learnt_from_them(
    client: TestClient, rows: dict[type, list[Any]], records: KeptRecords
) -> None:
    """**The digest's undo works for everybody it is sent to.** A person holding no grant at all,
    and one holding every console screen and not the member grant, each undo a learning formed from
    their own words, where Forget on the workspace refuses them both. Delete this and the weekly
    digest can link an undo its recipient is refused, which reads as an undo that does nothing."""
    assert "by nothing an administrator grants" in (
        A_PERSON_UNDOES_WHAT_WAS_LEARNT_FROM_THEM_ON_THEIR_SIGN_IN_ALONE
    )
    rows[PersistentMemoryRow] = [
        stated("mem_none", "Mondays first", subject="u_none"),
        stated("mem_admin", "Tables over prose", subject="u_admin"),
    ]
    rows[LearningRow] = [learnt("mem_none", agent_id=None), learnt("mem_admin", agent_id=None)]

    assert post(client, "u_none", FORGET, {"memory_id": "mem_none"}).status_code == 404
    done = [
        post(client, "u_none", UNDO, {"memory_id": "mem_none"}),
        post(client, "u_admin", UNDO, {"memory_id": "mem_admin"}),
    ]

    assert [one.status_code for one in done] == [200, 200], [one.text for one in done]
    assert all(one.json()["took_effect"] is True for one in done)
    assert [(one.memory_id, actor) for one, actor in records.undone] == [
        ("mem_none", "u_none"),
        ("mem_admin", "u_admin"),
    ]


def test_the_digests_undo_refuses_somebody_elses_learning_as_a_missing_one(
    client: TestClient, rows: dict[type, list[Any]], records: KeptRecords
) -> None:
    """Authorship is the whole of the gate, so it has to hold: another person's memory and one that
    does not exist are the one 404, in one sentence, and nothing reaches the store. Delete this and
    a grant-free route undoes anybody's memory by its id."""
    memories_with_records(rows)

    refused = [
        post(client, ME, UNDO, {"memory_id": "mem_theirs"}),
        post(client, ME, UNDO, {"memory_id": "mem_nothing"}),
        post(client, "u_none", UNDO, {"memory_id": "mem_mine"}),
    ]

    assert [one.status_code for one in refused] == [404] * 3
    assert len({one.json()["message"] for one in refused}) == 1
    assert records.undone == []
    assert post(client, ME, UNDO, {"memory_id": "mem_mine"}).status_code == 200
