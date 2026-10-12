"""The route that notes a copied answer: one trace and nothing else, one sentence whatever came of
it, and the person's own thread the only place an answer is found.

`tests/unit/test_acceptance_copied.py` runs the same route against PostgreSQL. This is the
wiring: the real application and the real token path, with a signal store on `app.state` that
keeps what it was handed instead of writing it.

Task ids: M16.2.2
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.api_routes import COPY_NOTED, signals_of
from brain.app import Settings, create_app
from brain.ops.signal_store import StoredSignals
from tests.fixtures.console_http import gate_wiring, headers
from tests.unit.test_answer_route_model import READER, READER_GRANTS


class KeptSignals(StoredSignals):
    """A signal store answering for the traces it was told are the asker's, keeping each copy."""

    def __init__(self, *theirs: tuple[str, str]) -> None:
        self.theirs = set(theirs)
        self.kept: list[tuple[str, str]] = []

    async def copied(self, *, principal_id: str, trace_id: str, now: datetime) -> bool:
        if (principal_id, trace_id) not in self.theirs:
            return False
        self.kept.append((principal_id, trace_id))
        return True


@pytest.fixture
def client() -> Iterator[TestClient]:
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = gate_wiring(READER_GRANTS)
        yield c


def copy(client: TestClient, body: dict[str, object]) -> Any:
    return client.post(f"{API_PREFIX}/answer/copied", headers=headers(READER), json=body)


def test_a_copy_of_the_callers_own_answer_is_kept_and_answered_in_one_sentence(
    client: TestClient,
) -> None:
    """**One trace, nothing else, and the same sentence whatever came of it** (M16.2.2). A copy of
    the caller's own answer is kept; a copy of somebody else's, or of a trace that never ran, is
    answered exactly the same and keeps nothing; a body carrying a note or the answer is refused
    before any store is reached.

    Delete this and the route can tell a person whether a trace is theirs, which is a way to find
    out which traces exist, or can grow a text box where the answer gets pasted."""
    signals = KeptSignals((READER, "trace-mine"))
    client.app.state.learning_signals = signals  # type: ignore[attr-defined]

    mine = copy(client, {"trace_id": "trace-mine"})
    theirs = copy(client, {"trace_id": "trace-theirs"})
    noted = copy(client, {"trace_id": "trace-mine", "note": "it said 12"})

    assert mine.status_code == 200
    assert mine.json() == {"told": COPY_NOTED}
    assert (theirs.status_code, theirs.json()) == (200, {"told": COPY_NOTED})
    assert noted.status_code == 422
    assert signals.kept == [(READER, "trace-mine")]


def test_a_copy_on_a_process_that_keeps_no_signals_is_answered_as_one_that_does(
    client: TestClient,
) -> None:
    """The positive case's sibling: a process with no database has nowhere to keep a signal, and
    the person who copied some text is told what everybody is told. Delete this and a process
    with no store turns a copy into a 500 on a button that has nothing to do with storage."""
    shown = copy(client, {"trace_id": "trace-mine"})

    assert (shown.status_code, shown.json()) == (200, {"told": COPY_NOTED})


def test_the_signal_store_is_the_states_own_or_the_databases_and_otherwise_none() -> None:
    """Which store a process writes copies to. Delete this and a process with no database could be
    handed a store over a session factory that does not exist."""
    from types import SimpleNamespace

    from sqlalchemy.ext.asyncio import async_sessionmaker

    bare: Any = SimpleNamespace()
    assert signals_of(bare) is None
    assert type(signals_of(SimpleNamespace(db_sessions=async_sessionmaker()))) is StoredSignals
    own = KeptSignals()
    assert signals_of(SimpleNamespace(learning_signals=own, db_sessions=None)) is own
