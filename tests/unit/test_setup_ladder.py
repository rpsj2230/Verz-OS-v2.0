"""The setup wizard writes the routing ladder for the provider it chose, after it appoints.

Driven through `POST /setup/appointment` with `tests/unit/test_setup_routes.py`'s own harness: the
real application, an in-memory first administrator store, and a vault held in memory. The ladder
writer is a recording stand-in; `tests/unit/test_default_ladder_store.py` is what writes one into
PostgreSQL.

Task ids: none
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field

from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from brain.app import create_app
from brain.firstrun import GRANTED_BY
from brain.models.default_ladder import LadderWritten
from brain.models.wire import LOCAL_PROVIDER
from brain.ops.credentials import Credentials
from tests.unit.test_credentials import KEY, Vault
from tests.unit.test_setup_routes import (
    HOSTED,
    Store,
    appointing,
    body,
    minted_settings,
)
from tests.unit.test_setup_routes import carried as carried  # the fixture, by its name


@dataclass
class Writer:
    """A `LadderWriter` recording each request and how many were appointed when it was made."""

    store: Store
    fails: bool = False
    asked: list[tuple[str, str, str, int]] = field(default_factory=list)

    async def write(self, provider: str, *, actor: str, trace_id: str) -> LadderWritten:
        self.asked.append((provider, actor, trace_id, len(self.store.appointed)))
        if self.fails:
            msg = "the routing table refused"
            raise RuntimeError(msg)
        return LadderWritten.WRITTEN


@contextmanager
def serving(
    store: Store, writer: Writer | None, *, credentials: Credentials | None = None
) -> Iterator[TestClient]:
    app = create_app(minted_settings())
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.first_administrators = store
        app.state.default_ladder = writer
        if credentials is not None:
            app.state.credentials = credentials
        yield c


def test_a_local_install_is_written_the_local_server_s_ladder_after_its_administrator(
    carried: Mapping[str, str],
) -> None:
    """**The positive case.** A wizard answered with the local profile appoints its administrator
    and then asks for the install's own server's ladder, as first run, under the request's trace.

    Delete this and a fresh install finishes its wizard with an empty ladder, and its first
    question finds no rung whatever it chose."""
    del carried
    store = Store()
    writer = Writer(store)
    with serving(store, writer) as c:
        answer = appointing(c, body())

    assert answer.status_code == 200
    assert writer.asked == [(LOCAL_PROVIDER, GRANTED_BY, answer.headers["x-trace-id"], 1)]


def test_a_hosted_install_is_written_the_ladder_of_the_provider_whose_key_it_kept(
    carried: Mapping[str, str],
) -> None:
    """A wizard answered with a hosted provider keeps its key, appoints, and then asks for that
    provider's ladder.

    Delete this and a hosted install is written the local server's ladder, which its hosted
    profile leaves in rotation in front of nothing that answers."""
    del carried
    store = Store()
    writer = Writer(store)
    with serving(store, writer, credentials=Credentials(Vault(), environ={})) as c:
        answer = appointing(c, body(answers=HOSTED))

    assert answer.status_code == 200
    assert [(provider, count) for provider, _, _, count in writer.asked] == [("anthropic", 1)]


def test_an_appointment_that_is_refused_writes_no_ladder(carried: Mapping[str, str]) -> None:
    """A finished install, and a hosted key that could not be kept, appoint nobody and ask for no
    ladder.

    Delete this and a refused attempt can write a ladder for a provider nobody was appointed over,
    which is then never refilled and sits in front of whatever the next attempt chooses."""
    del carried
    finished = Store(held=1)
    unkept = Store()
    first = Writer(finished)
    second = Writer(unkept)
    with serving(finished, first) as c:
        closed = appointing(c, body())
    with serving(unkept, second) as c:
        refused = appointing(c, body(answers=HOSTED))

    assert (closed.status_code, refused.status_code) == (404, 409)
    assert first.asked == second.asked == []
    assert KEY not in refused.text


def test_a_ladder_that_cannot_be_written_does_not_take_the_appointment_with_it(
    carried: Mapping[str, str],
) -> None:
    """The administrator is appointed and the finishing screen is sent for whatever the routing
    table says; the refusal is logged by its class, and the next start writes the ladder.

    Delete this and a routing table that refuses turns a finished wizard into a 500 after the door
    has closed, which is an install nobody can finish and nobody can start again."""
    del carried
    store = Store()
    writer = Writer(store, fails=True)
    with capture_logs() as logged, serving(store, writer) as c:
        answer = appointing(c, body())

    assert answer.status_code == 200
    assert len(store.appointed) == 1
    assert len(writer.asked) == 1
    unwritten = [one for one in logged if one["event"] == "setup.ladder_unwritten"]
    assert unwritten == [
        {
            "event": "setup.ladder_unwritten",
            "log_level": "warning",
            "provider": LOCAL_PROVIDER,
            "error": "RuntimeError",
        }
    ]


def test_a_process_with_no_ladder_writer_still_appoints(carried: Mapping[str, str]) -> None:
    """A process with no database has no writer and writes no ladder, and appointing is otherwise
    unchanged.

    Delete this and the ladder becomes a condition of appointing, on the one kind of process that
    has nowhere to write one."""
    del carried
    store = Store()
    with serving(store, None) as c:
        answer = appointing(c, body())

    assert answer.status_code == 200
    assert len(store.appointed) == 1
