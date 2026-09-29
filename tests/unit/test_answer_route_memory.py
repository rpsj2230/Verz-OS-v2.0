"""The answer route forms what a person asks to be remembered and shows a model what they said.

`tests/unit/test_memory_turn.py` holds the rules and the stores against PostgreSQL. This is the
wiring: the real application from `create_app`, the real token path, a real executor behind
`app.state.models`, and a formation store and a recall store on `app.state` that keep what they
were handed instead of writing it. What is proved is that `brain.api_routes.answered_for`, the one
function the web and every chat channel answer through, hands formation the turn a person's words
were, at the run's reach and in their department, and hands the model the hints recall admitted.

Task ids: M16.6.3, M16.7.12
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from brain.api import API_PREFIX
from brain.api_routes import formations_of, recall_of
from brain.app import Settings, create_app
from brain.core.entitlement import EntitlementSet
from brain.memory.turn import Turn
from brain.ops.memory_store import Formed, StoredFormations, StoredRecall
from brain.ops.model_service import ModelService
from brain.tools.startup import build_registry
from tests.fixtures.console_http import gate_wiring, headers
from tests.unit.test_answer_route import HOURS, OneRow
from tests.unit.test_answer_route_model import READER, READER_GRANTS
from tests.unit.test_api_routes import SOURCE
from tests.unit.test_model_calls import Ladder, Scripted, executor, rung
from tests.unit.test_model_lane import VISIBLE, Passages, completion
from tests.unit.test_streaming import decode

#: A hint nothing else in the application holds, so finding it anywhere is finding the hint.
HINT = "I prefer the figure first HINTCERULEAN"


class KeptFormations(StoredFormations):
    """A formation store that keeps each turn it was handed and writes nothing."""

    def __init__(self) -> None:
        self.turns: list[Turn] = []

    async def after_turn(self, turn: Turn) -> Formed | None:
        self.turns.append(turn)
        return Formed(memory_ids=(), skipped=())


class KeptRecall(StoredRecall):
    """A recall store answering with fixed hints, and keeping who it was asked about and where."""

    def __init__(self, *hints: str) -> None:
        self.given = hints
        self.asked: list[tuple[EntitlementSet, Mapping[str, object], datetime]] = []

    async def hints(
        self,
        reader: EntitlementSet,
        *,
        where: Mapping[str, object],
        now: datetime,
        trace_id: str,
    ) -> tuple[str, ...]:
        self.asked.append((reader, where, now))
        return self.given


@pytest.fixture
def transport() -> Scripted:
    return Scripted(completion())


@pytest.fixture
def wired(transport: Scripted) -> Iterator[tuple[TestClient, KeptFormations, KeptRecall]]:
    """The application with a model step, a formation store and a recall store in place."""
    app: FastAPI = create_app(Settings(env="development", database_url=""))
    calls, _ = executor(Ladder((rung("anthropic"),)), {"anthropic": transport})
    owned = httpx.Client()
    formations, recall = KeptFormations(), KeptRecall(HINT)
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = gate_wiring(READER_GRANTS)
        app.state.tools = build_registry(source=SOURCE, records=OneRow())
        app.state.fast_path_rules = (HOURS,)
        app.state.models = ModelService(calls=calls, client=owned)
        app.state.passage_search = Passages(VISIBLE)
        app.state.memory_formations = formations
        app.state.memory_recall = recall
        yield c, formations, recall
    owned.close()


def asked(client: TestClient, question: str) -> Any:
    return client.post(f"{API_PREFIX}/answer", headers=headers(READER), json={"question": question})


def test_a_person_asking_to_be_remembered_is_handed_to_formation_by_the_answer_route(
    wired: tuple[TestClient, KeptFormations, KeptRecall],
) -> None:
    """**Nothing on an install formed a memory until 2026-09-29, because nothing called
    `StoredFormations.after_turn`.** The route now hands it the turn: the person's own words, the
    run's reach, which is theirs, answered as the lane answered it, and the trace the request ran
    under.

    Delete this and the call can fall out of `answered_for` with every store test green, and the
    Memory and Learning screens go back to being empty on every install."""
    client, formations, _ = wired

    answered = asked(client, "Remember that I prefer email. How much annual leave do we get?")

    assert answered.status_code == 200
    [turn] = formations.turns
    assert turn.said == "Remember that I prefer email. How much annual leave do we get?"
    assert turn.principal_id == READER == turn.reach.principal_id
    assert (turn.answered, turn.refused, turn.agent_id) == (True, False, None)
    assert turn.trace_id


def test_a_question_asking_nothing_to_be_remembered_is_not_handed_to_formation(
    wired: tuple[TestClient, KeptFormations, KeptRecall],
) -> None:
    """The positive case's sibling: almost every question asks nothing to be remembered, and the
    route decides that before any store is reached.

    Delete this and every question could take a lock on its asker and read their memories."""
    client, formations, _ = wired

    assert asked(client, "how much annual leave do we get").status_code == 200
    assert asked(client, "what is the price of WEB-1001").status_code == 200
    assert formations.turns == []


def test_the_model_is_shown_what_recall_admitted_about_the_asker_and_cites_none_of_it(
    wired: tuple[TestClient, KeptFormations, KeptRecall], transport: Scripted
) -> None:
    """**The route asks recall about the person asking, at the run's reach and at their own place,
    and the model is sent what it admitted as a hint (M16.6.3).** The frames the person reads cite
    the passage and never the hint.

    Delete this and the route can stop reading memories for the model, which every lane test with
    its own `ModelLane` passes, and no answer on an install ever uses what a person told it."""
    client, _, recall = wired

    answered = asked(client, "how much annual leave do we get")

    assert answered.status_code == 200
    [(reader, where, _)] = recall.asked
    assert reader.principal_id == READER
    assert where["principal_id"] == READER
    [request] = transport.sent
    assert HINT in request.messages[1].content
    assert HINT not in request.messages[0].content
    cited = [one.data for one in decode(answered.text) if one.event == "citation"]
    assert cited and all("HINTCERULEAN" not in data for data in cited)


def test_a_question_the_fast_lane_answers_reads_no_memory(
    wired: tuple[TestClient, KeptFormations, KeptRecall], transport: Scripted
) -> None:
    """A question a rule answers reaches no model, so nothing is recalled for one.

    Delete this and every fast-lane answer, which is meant to cost one row read, pays for a read of
    the asker's memories nobody is shown."""
    client, _, recall = wired

    assert asked(client, "what is the price of WEB-1001").status_code == 200
    assert recall.asked == []
    assert transport.sent == []


def test_a_process_with_no_database_forms_nothing_and_recalls_nothing() -> None:
    """With no sessions there is nowhere to keep a memory or read one; with sessions both stores
    are the database's own, unless the state carries its own.

    Delete this and a process with no database could be handed a store over a session factory that
    does not exist, which fails on the first person asking to be remembered."""
    from types import SimpleNamespace

    from sqlalchemy.ext.asyncio import async_sessionmaker

    bare: Any = SimpleNamespace()
    assert formations_of(bare) is None
    assert recall_of(bare) is None
    with_database: Any = SimpleNamespace(db_sessions=async_sessionmaker())
    assert type(formations_of(with_database)) is StoredFormations
    assert type(recall_of(with_database)) is StoredRecall
    own = KeptFormations()
    assert formations_of(SimpleNamespace(memory_formations=own, db_sessions=None)) is own
