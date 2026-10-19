"""A publish that costs more per run than its department allows waits for the department's
administrator, and the publish record shows what a run costs (M20.5.2).

Driven through the same real application and in-memory draft store as
`tests/unit/test_agent_builder_routes.py`, with the department's per-run ceiling put where
`brain.agent_builder_routes._department_ceiling` looks first. That the budget row and the switch are
read from PostgreSQL is the install check's.

Task ids: M20.5.2
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from brain.agent_builder_routes import (
    APPROVE_PATH,
    EDIT_PATH,
    PUBLICATIONS_PATH,
    PUBLISH_PATH,
    PUBLISHED_NEW,
    REFUSED,
    WAITS_FOR_A_SECOND_PERSON,
)
from brain.agents.model import AgentAudience, AgentState
from brain.app import Settings, create_app
from brain.builder.agent_drafts import NOT_THE_AUTHOR
from brain.builder.run_cost import HELD_FOR_ITS_COST, rehearsed_run_cost
from brain.knowledge.visibility import Visibility
from tests.fixtures.console_http import gate_wiring
from tests.unit.test_agent_builder_routes import (
    COMPANY,
    GRANTS,
    Console,
    Memory,
    a_document,
    at,
    checked,
    everybody,
    not_changed,
    reaching_nothing,
    ready,
    saved,
)
from tests.unit.test_agent_lifecycle_routes import installed, tools
from tests.unit.test_agent_routes import KEY


@pytest.fixture
def console() -> Iterator[Console]:
    """`tests/unit/test_agent_builder_routes.py`'s console: the real application, an in-memory draft
    store, a signing key and a one-source tool registry."""
    app = create_app(Settings(env="development"))
    memory = Memory(agents=everybody())
    with TestClient(app) as client:
        app.state.gate = gate_wiring(GRANTS)
        app.state.db_sessions = None
        app.state.agent_drafts = memory
        app.state.template_key = KEY
        app.state.tools = tools("ledger")
        yield Console(client=client, app=app, memory=memory)


#: Far above anything a run of these agents costs, and below it.
ROOMY = 10**9
TIGHT = 1


def ceiling(console: Console, minor: int | None) -> None:
    """The department's per-run ceiling the route reads, whatever department it is asked for."""

    async def found(department: str) -> int | None:
        del department
        return minor

    set_on(console, found)


def set_on(console: Console, found: Callable[[str], Awaitable[int | None]]) -> None:
    console.app.state.department_run_ceiling = found


def a_team_agent_ready(console: Console) -> tuple[str, int]:
    """A draft of a team agent that reaches nothing, saved and checked."""
    return ready(console, reaching_nothing())


def publish_for_the_department(console: Console, draft_id: str, revision: int) -> Any:
    return console.post(
        "u_admin",
        at(PUBLISH_PATH, draft_id=draft_id),
        {"revision": revision, "agent_kind": "team"},
    )


def test_a_publish_that_costs_more_than_its_departments_ceiling_waits_for_the_departments_admin(
    console: Console,
) -> None:
    """The author's publish to their own department is held, says so with both figures and the
    unit, and makes nothing; the author cannot approve it; the department's administrator, who
    reaches the department's agents and nothing else, sees it and approves it, which publishes it.

    Delete this and an agent that costs more than its department allows ships on its author's word,
    with the budget the department set standing for nothing."""
    ceiling(console, TIGHT)
    draft_id, revision = a_team_agent_ready(console)
    before = set(console.memory.agents)

    asked = publish_for_the_department(console, draft_id, revision)

    assert asked.status_code == 202, asked.text
    body = asked.json()
    assert body["state"] == "waiting"
    assert body["sentence"] == HELD_FOR_ITS_COST
    assert body["held_for_cost"] is True
    assert body["ceiling_minor"] == TIGHT and body["cost_minor"] > TIGHT
    assert body["currency"]
    assert set(console.memory.agents) == before

    approve = {"revision": revision}
    own = console.post("u_admin", at(APPROVE_PATH, draft_id=draft_id), approve)
    elsewhere = console.post("u_wide", at(APPROVE_PATH, draft_id=draft_id), approve)
    assert not_changed(own) == (409, REFUSED, NOT_THE_AUTHOR)
    assert elsewhere.status_code == 404
    assert [
        one["draft_id"]
        for one in console.get("u_narrow", "/agent-drafts").json()["waiting_for_you"]
    ] == [draft_id]

    approved = console.post("u_narrow", at(APPROVE_PATH, draft_id=draft_id), approve)

    assert approved.status_code == 201, approved.text
    made = console.memory.agents[approved.json()["agent_id"]]
    assert made.record.audience.level is Visibility.DEPARTMENT
    assert made.record.audience.department == "web"


def test_a_publish_within_its_departments_ceiling_or_with_none_set_goes_out_on_its_authors_word(
    console: Console,
) -> None:
    """The positive half: a ceiling above the cost, no ceiling at all and no switch each publish
    at once, and say nothing of a hold.

    Delete this and the hold above is satisfied by a route that holds every publish."""
    for minor in (ROOMY, None):
        ceiling(console, minor)
        draft_id, revision = a_team_agent_ready(console)
        done = publish_for_the_department(console, draft_id, revision)
        assert done.status_code == 201, done.text
        assert done.json()["sentence"] == PUBLISHED_NEW
        assert done.json()["held_for_cost"] is False

    del console.app.state.department_run_ceiling
    draft_id, revision = a_team_agent_ready(console)
    assert publish_for_the_department(console, draft_id, revision).status_code == 201


def test_a_cost_equal_to_the_ceiling_is_within_it() -> None:
    """The ceiling is a limit, so a run costing exactly it is not held.

    Delete this and the comparison can drift to at-or-above, which holds the agent whose cost the
    department chose as its limit."""
    from brain.agents.catalogue import catalogue_by_id
    from brain.builder.run_cost import cost_hold

    manifest = catalogue_by_id()["support_ticket_agent"]
    cost = rehearsed_run_cost(manifest).minor

    assert cost_hold(manifest, department="web", ceiling_minor=cost) is None
    held = cost_hold(manifest, department="web", ceiling_minor=cost - 1)
    assert held is not None and (held.cost_minor, held.ceiling_minor) == (cost, cost - 1)


def test_a_personal_agent_belongs_to_no_department_and_is_never_held(console: Console) -> None:
    """A publish for its author alone is not held, however low a ceiling is.

    Delete this and a person's own agent waits for an administrator over a budget that is not
    theirs."""
    ceiling(console, TIGHT)
    draft_id, revision = a_team_agent_ready(console)

    done = console.post("u_admin", at(PUBLISH_PATH, draft_id=draft_id), {"revision": revision})

    assert done.status_code == 201, done.text
    assert done.json()["held_for_cost"] is False


def test_an_edit_held_only_for_its_cost_is_approved_by_an_administrator_who_need_not_read_it(
    console: Console,
) -> None:
    """A persona change to a department's agent reaches no further than before, so nothing widens
    and only the cost holds it; the department's administrator, who reads none of what the agent
    reads, can approve it, because a cost needs an administrator and not a reader.

    Delete this and a cost hold can be approved only by somebody who holds everything the agent
    reaches, which is the widening rule asked about something that is not a widening."""
    console.memory.agents["web_desk"] = installed(
        "web_desk",
        AgentAudience(level=Visibility.DEPARTMENT, owner_id="u_steward", department="web"),
        state=AgentState.ENABLED,
    )
    ceiling(console, TIGHT)
    started = console.post("u_admin", at(EDIT_PATH, agent_id="web_desk"))
    assert started.status_code == 201, started.text
    draft = started.json()
    document = {**draft["document"], "persona": "Answer in one sentence and name the invoice."}
    revision = saved(console, draft, document)
    assert checked(console, draft["draft_id"], revision).json()["passed"]

    waits = console.post(
        "u_admin", at(PUBLISH_PATH, draft_id=draft["draft_id"]), {"revision": revision}
    )

    assert waits.status_code == 202, waits.text
    assert waits.json()["held_for_cost"] is True and waits.json()["widened"] == []
    approved = console.post(
        "u_narrow", at(APPROVE_PATH, draft_id=draft["draft_id"]), {"revision": revision}
    )
    assert approved.status_code == 201, approved.text
    assert console.memory.agents["web_desk"].record.persona.startswith("Answer in one sentence")


def test_a_company_agent_belongs_to_no_department_and_is_not_held(console: Console) -> None:
    """An edit of an agent the whole company sees has no department whose ceiling it could exceed.

    Delete this and a company agent is held against the author's own department's budget."""
    ceiling(console, TIGHT)
    started = console.post("u_admin", at(EDIT_PATH, agent_id=COMPANY))
    draft = started.json()
    revision = saved(console, draft, {**draft["document"], "persona": "Answer briefly."})
    assert checked(console, draft["draft_id"], revision).json()["passed"]

    done = console.post(
        "u_admin", at(PUBLISH_PATH, draft_id=draft["draft_id"]), {"revision": revision}
    )

    assert done.status_code == 201, done.text


def test_a_widening_that_is_also_held_for_its_cost_says_the_wider_reason(
    console: Console,
) -> None:
    """Both reasons at once: the sentence is the widening's, which names a second person who holds
    everything the agent reaches, and the hold is still reported.

    Delete this and an agent that both reaches further and costs more tells its author only the
    cheaper reason, and the approver they are sent to cannot publish it."""
    ceiling(console, TIGHT)
    draft_id, revision = ready(console, a_document())

    asked = publish_for_the_department(console, draft_id, revision)

    assert asked.status_code == 202, asked.text
    assert asked.json()["sentence"] == WAITS_FOR_A_SECOND_PERSON
    assert asked.json()["held_for_cost"] is True
    assert asked.json()["widened"]


def test_the_publish_record_shows_what_a_run_of_each_version_cost(
    console: Console, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The history of a published agent carries each version's cost in the unit the history names,
    as the store computed it, and a version whose cost is not known carries none rather than
    nought.

    Delete this and the cost a publish was held against cannot be read from anywhere afterwards."""
    from datetime import UTC, datetime

    import brain.agent_builder_routes as routes
    import brain.builder.publication_store as store
    from brain.builder.publish import PublishDecision, record_publish
    from brain.gate.injection import AutonomyTier

    def made(cost: int | None) -> Any:
        return record_publish(
            agent_id=COMPANY,
            actor_id="u_admin",
            at=datetime(2019, 3, 4, 12, tzinfo=UTC),
            before={},
            after={"persona": "Answer."},
            decision=PublishDecision(
                agent_id=COMPANY, rung=AutonomyTier.SHADOW, approvers=1, widenings=(), refusals=()
            ),
            cost_minor=cost,
        )

    class Kept:
        def __init__(self, sessions: object) -> None:
            pass

        async def history(self, agent_id: str) -> tuple[Any, ...]:
            return (made(1234), made(None))

    monkeypatch.setattr(routes, "sessions_of", lambda request: object())
    monkeypatch.setattr(store, "StoredPublications", Kept)

    served = console.get("u_admin", at(PUBLICATIONS_PATH, agent_id=COMPANY))

    assert served.status_code == 200, served.text
    body = served.json()
    assert body["currency"]
    assert [one["cost_minor"] for one in body["publications"]] == [1234, None]
