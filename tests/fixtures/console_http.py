"""The real application, signed-in people with chosen grants, and a stub where the pool is.

`tests/unit/test_operate_routes.py` builds this by hand, borrowing the token machinery from
`tests/unit/test_api_routes.py` and the directory from `tests/unit/test_agent_routes.py`. The
Features, Scheduled jobs, Prompts and Errors tests need the same three things with different
grants, so they are built once here: `Stub.answerers` is the list of functions a statement is
offered to in order, and a statement nobody answers fails the test rather than returning nothing.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import TextClause
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api_routes import GateWiring
from brain.app import Settings, create_app
from brain.core.entitlement import EntitlementSet, Grant
from brain.error_routes import router as error_router
from brain.feature_routes import router as feature_router
from brain.identity.bearer import TokenAuthority
from brain.jobs_routes import router as jobs_router
from brain.log_routes import router as log_router
from brain.prompt_routes import router as prompt_router
from tests.fixtures.http_client import Response
from tests.fixtures.setting_rows import Result
from tests.unit.test_agent_routes import Directory
from tests.unit.test_api_routes import (
    AUDIENCE,
    ISSUER,
    Keys,
    NoCache,
    Versions,
    token_for,
    verifier,
)

#: The routers these tests are about.
ROUTERS = (error_router, feature_router, jobs_router, log_router, prompt_router)

#: A function offered a statement, answering a result or None to pass it on.
Answerer = Callable[[Any], Any]


class Stub:
    """What every stub session in one test answers with, and what it was asked."""

    def __init__(self) -> None:
        self.answerers: list[Answerer] = []
        self.statements: list[Any] = []
        #: Each transaction setting a route set for the trigger that records its write, as the
        #: setting's name and value, in the order set. See `brain.tables.audit.attributed_to`.
        self.attributions: list[tuple[str, str]] = []
        self.commits = 0
        self.rollbacks = 0


def attribution_of(statement: Any) -> tuple[str, str] | None:
    """The setting and value a `set_config` statement sets, or None for any other statement.

    Answered by the stub itself rather than left to each test's answerers, because every route
    that writes a recorded row sets these first and the result is never read.
    """
    if not isinstance(statement, TextClause) or not str(statement).startswith("SELECT set_config"):
        return None
    params = statement.compile().params
    return str(params["name"]), str(params["value"])


_STUB = Stub()


class StubSession(AsyncSession):
    """An `AsyncSession` that offers each statement to the answerers and refuses the rest."""

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        _STUB.statements.append(statement)
        attribution = attribution_of(statement)
        if attribution is not None:
            _STUB.attributions.append(attribution)
            return Result([])
        for answerer in _STUB.answerers:
            found = answerer(statement)
            if found is not None:
                return found
        msg = f"no stub answers {statement}"
        raise AssertionError(msg)

    async def commit(self) -> None:
        _STUB.commits += 1

    async def rollback(self) -> None:
        _STUB.rollbacks += 1

    async def close(self) -> None:
        return None


class Store:
    """A `brain.gate.resolve.EntitlementStore` over a grants mapping the test chose."""

    def __init__(self, grants: Mapping[str, tuple[Grant, ...]]) -> None:
        self.grants = grants

    async def load(self, principal_id: str, now: datetime) -> EntitlementSet:
        return EntitlementSet(principal_id=principal_id, grants=self.grants.get(principal_id, ()))


@contextmanager
def console_client(
    grants: Mapping[str, tuple[Grant, ...]], *, database: bool = True
) -> Iterator[tuple[TestClient, Stub]]:
    """The application with these grants, and the stub its sessions answer from."""
    global _STUB
    _STUB = Stub()
    app: FastAPI = create_app(Settings(env="development"))
    # Included here as well as by `brain.app`, which is `tests/unit/test_session_routes.py`'s
    # arrangement: a route registered twice answers from the first registration, which is the same
    # function, so these tests exercise the routers whether or not the lines in `brain.app` are in
    # the tree they run in, as in a mutation worktree at a commit that predates them.
    for router in ROUTERS:
        app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.gate = gate_wiring(grants)
        app.state.db_sessions = async_sessionmaker(class_=StubSession) if database else None
        yield client, _STUB


def gate_wiring(grants: Mapping[str, tuple[Grant, ...]]) -> GateWiring:
    """The token machinery these tests sign in with, over a grants mapping the test chose.

    Separate from `console_client` so a test driving the same routes against a real database
    signs its people in the same way rather than through a second copy of this.
    """
    return GateWiring(
        authority=TokenAuthority(
            issuer=ISSUER,
            audience=AUDIENCE,
            keys=Keys(),
            verify=verifier,
            directory=Directory(),
        ),
        versions=Versions(),
        store=Store(grants),
        cache=NoCache(),
    )


#: What a sign-in with a second factor carries. `brain.gate.admission` withholds every `admin:`
#: capability from a session without one and from a token naming no session, so a test of an
#: administrative control signs in this way unless it is testing exactly that refusal.
SECOND_FACTOR: Mapping[str, object] = {"sid": "sess-1", "amr": ["otp"]}


def headers(pid: str, *, strong: bool = True) -> dict[str, str]:
    """A bearer token for one person, with a second factor unless `strong` is False."""
    claims = dict(SECOND_FACTOR) if strong else {"sid": "sess-1"}
    return {"authorization": f"Bearer {token_for(pid, claims=claims)}"}


def get(client: TestClient, pid: str, path: str, *, strong: bool = True) -> Response:
    response: Response = client.get(path, headers=headers(pid, strong=strong))
    return response


def post(
    client: TestClient,
    pid: str,
    path: str,
    body: Mapping[str, Any] | None = None,
    *,
    strong: bool = True,
) -> Response:
    response: Response = client.post(
        path, json=dict(body or {}), headers=headers(pid, strong=strong)
    )
    return response
