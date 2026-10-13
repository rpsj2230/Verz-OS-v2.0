"""Which kinds of memory an agent may read and write, over HTTP (M39.7.1).

Driven through the real application and the in-memory lifecycle store
`tests/unit/test_agent_lifecycle_routes.py` uses, with a stored-kinds object that records the write
it was asked for, so what is proved is the route's decisions: who is told, who may change it, what a
stale page is told and what is written. That the row and the ledger entry reach PostgreSQL is
`brain.ops.acceptance_checks_agent_memory_kinds`'s.

Task ids: M39.7.1
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from brain.agent_memory_kinds_routes import (
    A_KIND_LEFT_OUT_IS_NOT_READ_AND_NOT_DELETED,
    MEMORY_KINDS_PATH,
    REASON_CODE,
    StoredMemoryKinds,
    view_of,
)
from brain.agents.memory_kinds import ALL_KINDS, MemoryKind
from brain.agents.model import AgentRecord
from tests.unit import test_agent_lifecycle_routes as lifecycle
from tests.unit.test_agent_lifecycle_routes import (
    COMPANY,
    MISSING,
    SALES,
    Console,
    not_changed,
    path,
    refusal,
)

console = lifecycle.console


class Writes(StoredMemoryKinds):
    """The one write, recorded, into the lifecycle store's own rows."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self.told: list[tuple[AgentRecord, AgentRecord, str]] = []

    async def change(
        self,
        before: AgentRecord,
        after: AgentRecord,
        *,
        actor_id: str,
        ent_hash: str,
        trace_id: str,
    ) -> bool:
        held = self.console.memory.agents[before.agent_id]
        self.console.memory.agents[before.agent_id] = replace(held, record=after)
        self.told.append((before, after, actor_id))
        return True


@pytest.fixture
def writes(console: Console) -> Writes:
    made = Writes(console)
    console.app.state.memory_kinds = made
    return made


def kinds_of(console: Console, agent_id: str) -> tuple[str, ...]:
    return console.memory.agents[agent_id].record.memory_kinds


def test_a_new_agent_has_every_kind_of_memory_and_the_view_says_each_is_on(
    console: Console,
) -> None:
    """The default is all five and the page is drawn from the record: every kind, in order, on.

    Delete this and a default of none can silence every agent's memory the day this ships."""
    seen = console.get("u_wide", path(MEMORY_KINDS_PATH, agent_id=SALES))

    assert seen.status_code == 200, seen.text
    body = seen.json()
    assert [one["name"] for one in body["kinds"]] == list(ALL_KINDS)
    assert all(one["on"] for one in body["kinds"])
    assert body["note"] == A_KIND_LEFT_OUT_IS_NOT_READ_AND_NOT_DELETED


def test_an_agents_steward_leaves_a_kind_out_and_the_store_is_told_who_did_it(
    console: Console, writes: Writes
) -> None:
    """The steward holds no lifecycle authority and still sets what the agent remembers; the page's
    answer shows the kind off and the store is told who.

    Delete this and only an administrator can change what an agent remembers."""
    switched = console.post(
        "u_wide",
        path(MEMORY_KINDS_PATH, agent_id=SALES),
        {"kinds": ["conversation", "own", "project", "task"], "expected": list(ALL_KINDS)},
    )

    assert switched.status_code == 200, switched.text
    offs = [one["name"] for one in switched.json()["kinds"] if not one["on"]]
    assert offs == [MemoryKind.PERSON.value]
    [(before, after, actor)] = writes.told
    assert (before.memory_kinds, after.memory_kinds) == (
        ALL_KINDS,
        ("conversation", "own", "project", "task"),
    )
    assert actor == "u_wide"
    assert REASON_CODE == "memory_kinds_set"


def test_an_administrator_over_the_row_sets_an_agents_memory(
    console: Console, writes: Writes
) -> None:
    """The administrator's half: a holder of the lifecycle authority over the row who is not its
    steward. Delete this and the rule can narrow to the steward alone."""
    switched = console.post(
        "u_admin",
        path(MEMORY_KINDS_PATH, agent_id=COMPANY),
        {"kinds": [], "expected": list(ALL_KINDS)},
    )

    assert switched.status_code == 200, switched.text
    assert kinds_of(console, COMPANY) == ()
    assert writes.told


def test_anybody_else_is_answered_as_if_the_agent_did_not_exist(
    console: Console, writes: Writes
) -> None:
    """A reader who sees the agent and is neither steward nor administrator gets the one 404 a
    missing agent gets, and nothing is written.

    Delete this and the route tells a reader which agents exist by answering them differently."""
    body: dict[str, Any] = {"kinds": [], "expected": list(ALL_KINDS)}
    refused = console.post("u_wide", path(MEMORY_KINDS_PATH, agent_id=COMPANY), body)
    missing = console.post("u_wide", path(MEMORY_KINDS_PATH, agent_id=MISSING), body)

    assert refusal(refused) == refusal(missing)
    assert refused.status_code == 404
    assert writes.told == []


def test_a_name_that_is_no_kind_is_refused_and_a_stale_page_writes_nothing(
    console: Console, writes: Writes
) -> None:
    """A name that is not one of the five is a 422 and a page that drew kinds the agent no longer
    has is a 409; neither writes.

    Delete this and the route can store a kind nothing reads or overwrite a change somebody else
    just made."""
    unknown = console.post(
        "u_admin",
        path(MEMORY_KINDS_PATH, agent_id=COMPANY),
        {"kinds": ["everything"], "expected": list(ALL_KINDS)},
    )
    stale = console.post(
        "u_admin",
        path(MEMORY_KINDS_PATH, agent_id=COMPANY),
        {"kinds": ["own"], "expected": ["own"]},
    )

    assert unknown.status_code == 422
    assert stale.status_code == 409
    assert not_changed(stale)[1] == "moved"
    assert writes.told == []


def test_the_view_says_what_it_is_made_from_and_never_a_count() -> None:
    """The view is five boxes and a note, with nothing that counts what was left out.

    Delete this and a field that totals the kinds, or what was remembered, can be added unseen."""
    assert set(view_of.__annotations__) >= {"record"}
    names = set(type(view_of(_record(), may_change=True)).model_fields)
    assert names == {"agent_id", "kinds", "may_change", "note"}


def _record() -> AgentRecord:
    from tests.unit.test_agent_lifecycle_routes import everybody

    return everybody()[SALES].record
