"""The member's thread list with a state beside each thread, over the real application.

The store of the records behind a run is a stand-in that notes whom it was asked about; the same
records over PostgreSQL are the install check in
`tests/unit/test_acceptance_checks_thread_states.py`. Every refusal has a sibling that succeeds.

Task ids: M40.7.6
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.app import Settings, create_app
from brain.chat.threads import Thread, ThreadMessage
from brain.gate.context import Channel
from brain.gate.leash import ApprovalState
from brain.member_task_state import HeldAction, RunFacts
from brain.tables.chat import MessageRole, RunState
from tests.fixtures.console_http import gate_wiring, headers

LONG_AGO = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
ADA = "u_narrow"


def _thread(name: str, trace: str, run_state: RunState | None, minutes: int) -> Thread:
    at = LONG_AGO + timedelta(minutes=minutes)
    answer = ThreadMessage(
        role=MessageRole.ASSISTANT,
        at=at + timedelta(seconds=1),
        channel=Channel.CONSOLE,
        body="an answer",
        run_state=run_state,
        trace_id=trace,
    )
    question = ThreadMessage(role=MessageRole.USER, at=at, channel=Channel.CONSOLE, body=name)
    return Thread(
        thread_id=f"00000000-0000-4000-8000-{minutes:012d}",
        owner_id=ADA,
        title=name,
        messages=(question, answer) if trace else (question,),
    )


THREADS = (
    _thread("settled", "trace_done", RunState.ANSWERED, 1),
    _thread("broken", "trace_failed", RunState.FAILED, 2),
    _thread("held", "trace_held", RunState.ANSWERED, 3),
    _thread("old", "", None, 4),
)


@dataclass
class Records:
    """What the stand-ins were asked, and what the switch says."""

    on: bool = True
    asked: list[tuple[str, dict[str, RunState | None]]] = field(default_factory=list)


@pytest.fixture
def records(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Records]]:
    seen = Records()

    class Threads:
        async def threads(self, principal_id: str) -> tuple[Thread, ...]:
            return THREADS

    class Facts:
        def __init__(self, _sessions: object) -> None:
            pass

        async def facts(
            self, principal_id: str, answers: dict[str, RunState | None], now: datetime
        ) -> dict[str, RunFacts]:
            seen.asked.append((principal_id, dict(answers)))
            return {
                "trace_done": RunFacts(run_state=RunState.ANSWERED),
                "trace_failed": RunFacts(run_state=RunState.FAILED, steps=("identify", "invoke")),
                "trace_held": RunFacts(
                    run_state=RunState.ANSWERED, held=(HeldAction(ApprovalState.PENDING, False),)
                ),
            }

    async def switch(_sessions: object) -> bool:
        return seen.on

    monkeypatch.setattr("brain.thread_routes.thread_states_are_on", switch)
    monkeypatch.setattr("brain.thread_routes.threads_of", lambda _state: Threads())
    monkeypatch.setattr("brain.thread_routes.StoredTaskStates", Facts)
    monkeypatch.setattr("brain.thread_routes.sessions_of", lambda _request: object())
    app = create_app(Settings(env="development"))
    with TestClient(app) as client:
        app.state.gate = gate_wiring({ADA: ()})
        app.state.db_sessions = None
        yield client, seen


def _listed(client: TestClient) -> dict[str, Any]:
    answered = client.get(f"{API_PREFIX}/threads", headers=headers(ADA))
    assert answered.status_code == 200, answered.text
    return {one["title"]: one for one in answered.json()["items"]}


def test_each_thread_says_where_its_last_run_has_got_to(
    records: tuple[TestClient, Records],
) -> None:
    """With the switch on, a settled thread is done, a broken one failed with the step it stopped
    at, one holding an action waiting for approval, and an old one with no recorded answer says
    nothing. Delete this and the list carries no state, or the wrong one, or a state for a thread
    that has nothing to say."""
    client, seen = records
    items = _listed(client)

    assert items["settled"]["state"] == "done" and items["settled"]["state_words"] == "Done"
    assert items["broken"]["state"] == "failed"
    assert items["broken"]["failed_step"].startswith("It stopped while")
    assert items["held"]["state"] == "waiting_for_approval"
    assert items["held"]["state_words"] == "Waiting for approval"
    assert (items["old"]["state"], items["old"]["failed_step"]) == ("", "")
    assert items["settled"]["failed_step"] == ""
    # One read for the whole list, for the caller alone, and for answers that name a request.
    assert seen.asked == [
        (
            ADA,
            {
                "trace_done": RunState.ANSWERED,
                "trace_failed": RunState.FAILED,
                "trace_held": RunState.ANSWERED,
            },
        )
    ]


def test_with_the_switch_off_the_threads_are_listed_without_a_state_and_nothing_is_read(
    records: tuple[TestClient, Records],
) -> None:
    """Off, the same four threads are listed and none carries a state, and the records behind a run
    are not asked for. Delete this and a switched-off install reads three more tables for every
    list, or hides a person's threads."""
    client, seen = records
    seen.on = False
    items = _listed(client)

    assert set(items) == {"settled", "broken", "held", "old"}
    assert all(one["state"] == "" and one["failed_step"] == "" for one in items.values())
    assert seen.asked == []


def test_a_search_lists_the_same_states(
    records: tuple[TestClient, Records], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The search over a person's threads is a list too and says the same. Delete this and a
    thread found by searching shows no state while the same thread in the list does."""
    client, _ = records

    class Found:
        async def search(self, principal_id: str, words: str) -> tuple[Thread, ...]:
            return THREADS[:2]

    monkeypatch.setattr("brain.thread_routes.threads_of", lambda _state: Found())
    answered = client.get(f"{API_PREFIX}/threads/search?q=word", headers=headers(ADA))
    assert answered.status_code == 200, answered.text
    states = {one["title"]: one["state"] for one in answered.json()["items"]}
    assert states == {"settled": "done", "broken": "failed"}
