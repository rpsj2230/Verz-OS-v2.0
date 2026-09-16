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

Task ids: M27.7.28
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

from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.console.own_things import own_scope
from brain.console.reads import Plane, plane_capability
from brain.console.screens import SCREENS
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.member.shell import DISCLOSURE_PREFIX
from brain.mine_routes import (
    MAX_OWN_RUNS,
    MORE_SPEND_THAN_THIS_PAGE_READS,
    UNDO_IS_NOT_RECORDED,
    month_start,
)
from brain.ops.budgets import BudgetLevel, BudgetPeriod
from brain.tables.adoption import QuestionAskedRow
from brain.tables.agent import AgentRow
from brain.tables.budget import BudgetVersionRow
from brain.tables.knowledge import KnowledgeItemRow
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
from tests.unit.test_estate_routes import CLIENT_NAME, an_item, inferred, stated

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


class StubSession(AsyncSession):
    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if not hasattr(statement, "column_descriptions"):
            return StubResult([])
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
    assert body["learned_undo"] == UNDO_IS_NOT_RECORDED
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
    the database holds.

    Delete this and the page could be gated on an administrative capability, which is a personal
    screen only administrators can open, or on nothing, which is `permitted` skipped."""
    for pid in ("u_admin", "u_prefix", "u_none"):
        assert get(client, pid).status_code == 404, pid
    empty = get(client, "u_admin").json()["message"]
    two_people(rows)
    assert get(client, "u_admin").json()["message"] == empty
    assert get(client, "u_prefix").json()["message"] == empty
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
