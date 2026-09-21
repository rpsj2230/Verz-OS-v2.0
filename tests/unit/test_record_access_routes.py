"""The record access view: who can see a record, only for somebody who can already see it.

Driven through the real application, the row tool `build_registry` registers and the redactor,
over a row source that honours the asker's id filter and nothing else. The caller's scope is
therefore applied by the redactor, the second enforcement point the records route relies on, so
a person is counted as seeing a record only when both points would show it to them.

Task ids: M1.9.1
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api import API_PREFIX
from brain.api_routes import FILTER_PARAM, GateWiring
from brain.app import Settings, create_app
from brain.console.reads import Plane, plane_capability
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.identity.bearer import TokenAuthority
from brain.knowledge.rows import RowQuery
from brain.tools.startup import build_registry
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    SEEDED_ROWS,
    SOURCE,
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

SECOND_FACTOR: Mapping[str, object] = {"amr": ["otp"]}
WHOLE = Scope.unrestricted()
WEB_ONLY = Scope(clauses=(Clause(field="sku", op=Op.PREFIX, value="WEB-"),))
IN_FINANCE = Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),))

#: The two seeded records, named by the column every reader here reaches.
WEB = "WEB-1001"
MAINTENANCE = "MNT-2002"
#: What a test may ask for by sku: the two records and one that is not there.
ASKABLE = frozenset({WEB, MAINTENANCE, "ZZZ-0000"})

PRICE_READS = (
    "read:price_list",
    "read:price_list.sku",
    "read:price_list.name",
    "read:price_list.sell_price",
)


def _grants(values: Sequence[str], scope: Scope) -> tuple[Grant, ...]:
    return tuple(Grant(capability=Capability(value=one), scope=scope) for one in values)


PEOPLE_READ = ("read:grant", plane_capability(Plane.CONFIGURATION).value)

GRANTS: dict[str, tuple[Grant, ...]] = {
    # Sees both rows and may open the People screen everywhere.
    "u_admin": (*_grants(PRICE_READS, WHOLE), *_grants(PEOPLE_READ, WHOLE)),
    # Sees both rows and may not open the People screen.
    "u_wide": _grants(PRICE_READS, WHOLE),
    "u_narrow": _grants(PRICE_READS, WHOLE),
    # Sees the web row only, and may open the People screen.
    "u_prefix": (*_grants(PRICE_READS, WEB_ONLY), *_grants(PEOPLE_READ, WHOLE)),
    # Sees both rows and may name only the people sitting in finance.
    "u_elsewhere": (*_grants(PRICE_READS, WHOLE), *_grants(PEOPLE_READ, IN_FINANCE)),
    # May open the People screen and sees no price list at all.
    "u_admin_only": _grants(PEOPLE_READ, WHOLE),
    "u_none": (),
}

#: Where each candidate sits. `u_narrow` is the one person in finance.
PEOPLE: tuple[tuple[str, str, str | None], ...] = tuple(
    (pid, f"Person {pid}", "finance" if pid == "u_narrow" else "web") for pid in sorted(GRANTS)
)


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


class IdFilteredRows:
    """Every seeded row whose sku the compiled statement names, or every row if it names none.

    The asker's filter is the only thing honoured, so each person's scope is left to the
    redactor, and `asked` counts the reads so the refusals can be shown to read nothing.
    """

    def __init__(self) -> None:
        self.asked = 0

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        self.asked += 1
        values = set(query.statement.compile().params.values())
        if not values & ASKABLE:
            return SEEDED_ROWS
        return [row for row in SEEDED_ROWS if row["sku"] in values]


class Result:
    def __init__(self, rows: Sequence[Any]) -> None:
        self._rows = tuple(rows)

    def all(self) -> tuple[Any, ...]:
        return self._rows


class Session(AsyncSession):
    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        return Result(PEOPLE)

    async def close(self) -> None:
        return None


@pytest.fixture
def rows() -> IdFilteredRows:
    return IdFilteredRows()


@pytest.fixture
def client(rows: IdFilteredRows) -> Iterator[TestClient]:
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
        app.state.tools = build_registry(source=SOURCE, records=rows)
        app.state.db_sessions = async_sessionmaker(class_=Session)
        yield c


def who_sees(c: TestClient, pid: str, record: str, entity: str = "price_list") -> Response:
    response: Response = c.get(
        f"{API_PREFIX}/records/{entity}/access",
        headers={"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"},
        params=[(FILTER_PARAM, f"sku:{record}")],
    )
    return response


def ids(answer: Response) -> list[str]:
    return [one["principal_id"] for one in answer.json()["people"]]


def test_a_reader_who_sees_the_record_is_told_everybody_who_does(client: TestClient) -> None:
    """The positive case. Delete this and every refusal below is satisfied by a route that
    refuses everybody."""
    web = who_sees(client, "u_admin", WEB)
    maintenance = who_sees(client, "u_admin", MAINTENANCE)
    assert web.status_code == 200, web.text
    assert ids(web) == ["u_admin", "u_elsewhere", "u_narrow", "u_prefix", "u_wide"]
    assert ids(maintenance) == ["u_admin", "u_elsewhere", "u_narrow", "u_wide"]


def test_the_view_does_not_open_for_somebody_who_cannot_see_the_record(
    client: TestClient,
) -> None:
    """M1.9.1's condition. Delete this and "who can see this record" confirms a record exists to
    a person it is withheld from, which is the leak the console had declined the view over."""
    unseen = who_sees(client, "u_prefix", MAINTENANCE)
    no_entity = who_sees(client, "u_admin_only", WEB)
    unknown = who_sees(client, "u_admin", WEB, entity="nothing_here")
    assert unseen.status_code == no_entity.status_code == unknown.status_code == 404
    assert who_sees(client, "u_prefix", WEB).status_code == 200


def test_the_answer_for_an_unseen_record_is_the_answer_for_an_unknown_entity(
    client: TestClient,
) -> None:
    """DENIED and ABSENT alike. Delete this and the refusal's wording tells a record withheld
    from one that is not there."""
    unseen = who_sees(client, "u_prefix", MAINTENANCE).json()["message"]
    missing = who_sees(client, "u_prefix", "ZZZ-0000").json()["message"]
    assert unseen == missing


def test_a_reader_without_the_people_screen_is_refused_before_anything_is_read(
    client: TestClient, rows: IdFilteredRows
) -> None:
    """The list is of people, so it is the People screen's disclosure too. Delete this and any
    reader of a row is handed a directory of who else reaches it."""
    assert who_sees(client, "u_wide", WEB).status_code == 404
    assert who_sees(client, "u_none", WEB).status_code == 404
    assert rows.asked == 0


def test_names_are_narrowed_to_the_people_the_reader_may_see(client: TestClient) -> None:
    """A reader whose People grant covers finance is told only about finance. Delete this and the
    view lists people the People screen would withhold."""
    assert ids(who_sees(client, "u_elsewhere", WEB)) == ["u_narrow"]


def test_the_answer_carries_no_count_of_anybody_withheld(client: TestClient) -> None:
    """Delete this and a total beside a narrowed list is the subtraction CLAUDE.md forbids."""
    body = who_sees(client, "u_elsewhere", WEB).json()
    assert set(body) == {"people", "truncated"}
