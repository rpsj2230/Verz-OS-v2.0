"""A person's ask to be deleted, and the retention owner seeing who has asked.

Driven through the real application with the token machinery borrowed from
`tests/unit/test_api_routes.py` and the erasure queue stand-in `tests/unit/test_erasure_routes.py`
uses. The asks are an in-memory store that keeps the real store's one rule (one ask waiting for a
person); the SQL is `tests/unit/test_acceptance_checks_member_deletion.py`'s, against a server.

**The member grant, the erasure authority and the Retention screen's capabilities are spelled out
here**, so a repointed one in the routes is a failure in this file rather than a constant compared
with itself.

Task ids: M40.4.2.3
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from brain.api import API_PREFIX
from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.identity.bearer import TokenAuthority
from brain.member_deletion_routes import (
    ASKING_DELETES_NOTHING,
    YOUR_ASK_IS_WAITING,
    YOUR_ASK_WAS_FILED,
)
from brain.ops.deletion_request_store import Asked
from brain.ops.erasure import deletion_order, erasure_targets
from brain.ops.retention import STORES
from tests.fixtures.http_client import Response
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Directory,
    Keys,
    NoCache,
    Versions,
    token_for,
)
from tests.unit.test_api_routes import verifier as verify_token
from tests.unit.test_erasure_routes import (
    CONFIGURATION,
    ERASE,
    RETENTION_READ,
    SECOND_FACTOR,
    Erasures,
    Exports,
)

MINE = f"{API_PREFIX}/me/deletion-request"
WAITING = f"{API_PREFIX}/govern/erasure-requests"
FILE = f"{API_PREFIX}/govern/erasures"

MEMBER_HOME = Capability(value="read:member.home")
CONTENT = Capability(value="read:member.content")

ME = "u_narrow"
SOMEBODY_ELSE = "u_wide"

#: Far outside any wall clock. See CLAUDE.md on dates in fixtures.
LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


def _everywhere(*capabilities: Capability) -> tuple[Grant, ...]:
    return tuple(Grant(capability=one, scope=Scope.unrestricted()) for one in capabilities)


#: Two members, an administrator with the erasure authority and the screen, one with the authority
#: and not the screen, one with the screen and not the authority, and one holding nothing.
GRANTS: Mapping[str, tuple[Grant, ...]] = {
    "u_narrow": _everywhere(MEMBER_HOME, CONTENT),
    "u_wide": _everywhere(MEMBER_HOME, CONTENT),
    "u_admin": _everywhere(RETENTION_READ, CONFIGURATION, ERASE),
    "u_prefix": _everywhere(ERASE),
    "u_elsewhere": _everywhere(RETENTION_READ, CONFIGURATION),
    "u_none": (),
}


class Store:
    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=GRANTS[principal_id])


@dataclass
class Asks:
    """`DeletionRequests` in memory, keeping the real rule that one ask waits for a person."""

    rows: list[Asked] = field(default_factory=list)
    closed: list[tuple[str, str, str]] = field(default_factory=list)
    refuse_to_close: bool = False

    async def ask(self, subject_id: str, *, at: datetime) -> tuple[Asked, bool]:
        for one in self.rows:
            if one.subject_id == subject_id and one.waiting:
                return one, False
        made = Asked(request_id=f"ask-{len(self.rows) + 1}", subject_id=subject_id, requested_at=at)
        self.rows.append(made)
        return made, True

    async def latest(self, subject_id: str) -> Asked | None:
        mine = [one for one in self.rows if one.subject_id == subject_id]
        return mine[-1] if mine else None

    async def waiting(self, *, limit: int) -> tuple[Asked, ...]:
        return tuple(one for one in self.rows if one.waiting)[:limit]

    async def decide(
        self, subject_id: str, *, by: str, erasure_request_id: str, at: datetime
    ) -> bool:
        if self.refuse_to_close:
            raise SQLAlchemyError("the database would not take it")
        for index, one in enumerate(self.rows):
            if one.subject_id == subject_id and one.waiting:
                self.rows[index] = replace(
                    one, decided_by=by, decided_at=at, filed_as=erasure_request_id
                )
                self.closed.append((subject_id, by, erasure_request_id))
                return True
        return False


@pytest.fixture
def asks() -> Asks:
    return Asks()


@pytest.fixture
def client(asks: Asks) -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = GateWiring(
            authority=TokenAuthority(
                issuer=ISSUER,
                audience=AUDIENCE,
                keys=Keys(),
                verify=verify_token,
                directory=Directory(),
            ),
            versions=Versions(),
            store=Store(),
            cache=NoCache(),
        )
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        # Never used: the stores are stood in. Present so a route asking for a database finds one.
        app.state.db_sessions = async_sessionmaker(class_=AsyncSession)
        app.state.deletion_requests = asks
        app.state.erasure_records = Erasures()
        app.state.export_log = Exports()
        app.state.member_deletion_requests_on = True
        yield c


def headers(pid: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token_for(pid, claims=SECOND_FACTOR)}"}


def read(c: TestClient, pid: str, path: str = MINE) -> Response:
    response: Response = c.get(path, headers=headers(pid))
    return response


def ask(c: TestClient, pid: str) -> Response:
    response: Response = c.post(MINE, headers=headers(pid))
    return response


def switch(c: TestClient, on: bool) -> None:
    c.app.state.member_deletion_requests_on = on  # type: ignore[attr-defined]


# ---------------------------------------------------------------- what a person is shown
def test_a_person_is_shown_what_a_deletion_reaches_before_they_ask(client: TestClient) -> None:
    """**The four lists** are the retention policy's own: what is reached, what only time removes,
    what is kept on purpose, and the order, each store with the sentence the policy gives for it.
    Delete this and the page can offer the ask without saying what it would not reach."""
    shown = read(client, ME).json()

    assert shown["state"] == "none"
    assert shown["may_ask"] is True
    assert shown["told"] == ASKING_DELETES_NOTHING
    route = shown["route"]
    assert [one["store"] for one in route["order"]] == [one.value for one in deletion_order()]
    assert [one["store"] for one in route["reaches"]] == [one.value for one in erasure_targets()]
    shown_stores = {
        one["store"] for part in ("reaches", "rotates_out", "retained") for one in route[part]
    }
    assert shown_stores == {one.store.value for one in STORES}
    sentences = {one.store.value: one.holds for one in STORES}
    assert all(one["holds"] == sentences[one["store"]] for one in route["order"])


def test_the_three_lists_add_up_to_the_order_with_no_store_twice_or_missing(
    client: TestClient,
) -> None:
    """A store described twice, or not at all, on a page about what will happen. Delete this and a
    store added without a disposition leaves the page complete-looking and wrong."""
    route = read(client, ME).json()["route"]

    parts = [one["store"] for name in ("reaches", "rotates_out", "retained") for one in route[name]]
    assert sorted(parts) == sorted(one["store"] for one in route["order"])
    assert route["rotates_out"], "the backups rotate out, and the page must say so"


# ---------------------------------------------------------------------------- asking
def test_asking_records_the_ask_and_deletes_nothing(client: TestClient, asks: Asks) -> None:
    """The ask is a row and nothing else: the answer is `waiting`, the erasure queue was handed
    nothing, and the ask is the asker's own. Delete this and the button can file an erase."""
    erasures = client.app.state.erasure_records  # type: ignore[attr-defined]

    response = ask(client, ME)

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "waiting"
    assert response.json()["told"] == YOUR_ASK_IS_WAITING
    assert response.json()["may_ask"] is False
    assert [(one.subject_id, one.waiting) for one in asks.rows] == [(ME, True)]
    assert erasures.filed == []


def test_asking_twice_is_one_ask_with_the_first_instant(client: TestClient, asks: Asks) -> None:
    """The sibling: a second press is the first row, shown with when it was first made. Delete this
    and pressing twice queues two asks for an administrator to read."""
    first = ask(client, ME).json()["asked_at"]
    second = ask(client, ME)

    assert second.status_code == 200
    assert second.json()["asked_at"] == first
    assert len(asks.rows) == 1


def test_one_person_asking_is_not_another_asking(client: TestClient, asks: Asks) -> None:
    """The asker is the sign-in and there is no parameter that names anyone else. Delete this and
    the route can be used to ask on a colleague's behalf."""
    ask(client, ME)

    assert read(client, SOMEBODY_ELSE).json()["state"] == "none"
    assert [one.subject_id for one in asks.rows] == [ME]


def test_a_switch_that_is_off_takes_no_new_ask_and_says_nothing_about_why(
    client: TestClient, asks: Asks
) -> None:
    """Off is the page's one refusal, and nothing is recorded. Delete this and an install that has
    not turned it on collects asks nobody agreed to read."""
    switch(client, False)

    assert ask(client, ME).status_code == 404
    assert asks.rows == []


def test_a_switch_that_is_off_leaves_an_earlier_ask_readable_and_closeable(
    client: TestClient, asks: Asks
) -> None:
    """A switch gates the door and never traps what it opened: the ask made while it was on still
    reads as waiting, the page offers no new ask, and the administrator can still file the erasure
    and close it. Delete this and turning the switch off strands a person's ask."""
    ask(client, ME)
    switch(client, False)

    shown = read(client, ME).json()
    filed = client.post(
        FILE, headers=headers("u_admin"), json={"subject_id": ME, "reason_reference": "DSAR-1"}
    )

    assert (shown["state"], shown["may_ask"]) == ("waiting", False)
    assert filed.status_code == 200, filed.text
    assert asks.closed == [(ME, "u_admin", "r-new")]


def test_somebody_without_the_member_grant_is_refused_alike_on_every_route(
    client: TestClient, asks: Asks
) -> None:
    """DENIED and ABSENT are one answer: holding nothing, or only administrative grants, opens
    nothing here. Delete this and the member page opens for a grant that opens no member screen."""
    for pid in ("u_none", "u_admin", "u_elsewhere"):
        assert read(client, pid).status_code == 404
        assert ask(client, pid).status_code == 404
    assert asks.rows == []


# ------------------------------------------------------------------ the retention owner
def test_the_retention_owner_sees_who_is_waiting_and_a_member_does_not(
    client: TestClient, asks: Asks
) -> None:
    """The list is the authority over everything and the screen, and carries the reference the
    erasure form takes and no name. Delete this and the asks are read by anybody who can read a
    page, or by nobody who can act on them."""
    ask(client, ME)
    ask(client, SOMEBODY_ELSE)

    seen = read(client, "u_admin", WAITING)

    assert seen.status_code == 200, seen.text
    assert [one["subject_id"] for one in seen.json()["requests"]] == [ME, SOMEBODY_ELSE]
    assert set(seen.json()["requests"][0]) == {"request_id", "subject_id", "requested_at"}
    for pid in (ME, "u_prefix", "u_elsewhere", "u_none"):
        assert read(client, pid, WAITING).status_code == 404


def test_filing_the_erasure_closes_the_ask_and_the_person_reads_that_it_was_filed(
    client: TestClient, asks: Asks
) -> None:
    """Filing through the queue's own route is what closes the ask, in the administrator's name.
    Delete this and an ask stays waiting for ever after the erasure it asked for was queued."""
    ask(client, ME)

    filed = client.post(
        FILE, headers=headers("u_admin"), json={"subject_id": ME, "reason_reference": "DSAR-1"}
    )

    assert filed.status_code == 200, filed.text
    assert asks.closed == [(ME, "u_admin", "r-new")]
    assert read(client, "u_admin", WAITING).json()["requests"] == []
    assert read(client, ME).json()["state"] == "filed"
    assert read(client, ME).json()["told"] == YOUR_ASK_WAS_FILED


def test_filing_for_somebody_who_never_asked_closes_nothing_and_still_files(
    client: TestClient, asks: Asks
) -> None:
    """The sibling: an erasure an administrator files on their own account is filed as before and
    marks no ask. Delete this and the closing step is the filing's precondition."""
    filed = client.post(
        FILE, headers=headers("u_admin"), json={"subject_id": "p_other", "reason_reference": "X-1"}
    )

    assert filed.status_code == 200, filed.text
    assert asks.closed == []


def test_a_failure_to_close_the_ask_does_not_fail_the_erasure_that_was_filed(
    client: TestClient, asks: Asks
) -> None:
    """The erasure is queued whatever the ask does: a database that will not close it leaves the ask
    waiting, which is a repeated prompt and not a lost erasure. Delete this and a failure after the
    queue took the erasure reports the filing as failed, and the administrator files it again."""
    ask(client, ME)
    asks.refuse_to_close = True

    filed = client.post(
        FILE, headers=headers("u_admin"), json={"subject_id": ME, "reason_reference": "DSAR-1"}
    )

    assert filed.status_code == 200, filed.text
    assert [one.waiting for one in asks.rows] == [True]


def test_the_route_builds_for_the_signed_in_person_alone(client: TestClient) -> None:
    """There is no query or body parameter that names a person. Delete this and a parameter is
    added for an administrator's convenience and the page becomes a directory."""
    schema: Any = client.get("/openapi.json").json()
    for path, method in (
        ("/api/v1/me/deletion-request", "post"),
        ("/api/v1/me/deletion-request", "get"),
    ):
        operation = schema["paths"][path][method]
        assert operation.get("parameters", []) == []
        assert "requestBody" not in operation
