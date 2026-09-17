"""One agent's About tab over HTTP: the audience and the one 404, and each input at its own gate.

Driven through the real application with the stub session `tests/unit/test_agent_routes.py`
answers statements from, so the rows under test are the rows the workspace's tests write, and the
same people hold the same grants. The automations are a stub store installed where
`brain.automation_schedule_routes.schedules_of` looks first, which records whether it was asked,
because the order of reads is half of what is under test: nothing about an agent a caller may not
see, and nothing about its automations for a reader of no Automations tab.

Every refusal is compared with the case it must be indistinguishable from, and has a sibling
proving the permitted case is answered.

Task ids: none
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain import agent_about_routes
from brain.agent_about_routes import AboutView, FlowLineView, FlowStepView, NeverView
from brain.app import Settings, create_app
from brain.console.agent_about import AN_AGENT_NEVER_SEES_MORE_THAN_ITS_CALLER
from brain.console.agent_automations import Automation, SchedulerChange
from brain.console.automation_gallery import BUILT_IN
from brain.console.workspace import intersections_in
from brain.core.errors import Absent
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.knowledge.visibility import Visibility
from brain.ops.automation_run_store import Listed
from brain.ops.jobs import NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT
from tests.fixtures.http_client import Response
from tests.unit import test_agent_routes as workspace_tests
from tests.unit.test_agent_routes import (
    AGENTS,
    DRAFTS,
    INSTALLED_AT,
    SENDS,
    Stored,
    StubSession,
    _wiring,
    agent_row,
    an_acting_agent,
    app_of,
    get,
    install_rows,
    tools_acting,
)

#: The automation template the stub store's automations are installed from.
TEMPLATE = BUILT_IN[0]


class Schedules:
    """An `AutomationSchedules` over a fixed list, recording every agent it was asked about."""

    def __init__(self, listed: tuple[Listed, ...] = ()) -> None:
        self.listed_rows = listed
        self.asked: list[str] = []

    async def listed(self, agent_id: str) -> tuple[Listed, ...]:
        self.asked.append(agent_id)
        return tuple(one for one in self.listed_rows if one.automation.agent_id == agent_id)

    async def change(
        self,
        change: SchedulerChange,
        *,
        reason: str,
        actor: str,
        ent_hash: str,
        trace_id: str,
        at: datetime,
    ) -> bool:
        raise AssertionError("the About tab changes no automation")


def automation(automation_id: str, *, running: bool, agent_id: str = "quote_helper") -> Listed:
    return Listed(
        automation=Automation(
            automation_id=automation_id,
            agent_id=agent_id,
            name=TEMPLATE.name,
            runs_as=Principal(
                id="u_somebody",
                kind=PrincipalKind.HUMAN,
                employment=Employment.STAFF,
                display_name="Somebody",
                primary_department="web",
            ),
            task="work_summary",
            next_run_at=INSTALLED_AT if running else None,
        ),
        template_id=TEMPLATE.template_id,
        guards="nothing leaves the building",
        stopped_because=None,
        runs=(),
    )


@pytest.fixture
def stored() -> Iterator[Stored]:
    """A fresh store, installed where the workspace tests' stub session reads it."""
    workspace_tests._STORED = Stored()
    yield workspace_tests._STORED


@pytest.fixture
def schedules() -> Schedules:
    return Schedules(
        (automation("auto_running", running=True), automation("auto_stopped", running=False))
    )


@pytest.fixture
def client(stored: Stored, schedules: Schedules) -> Iterator[TestClient]:
    """The real application with the stub where the pool is and the stub store where the
    Automations tab's store is looked for first."""
    app: FastAPI = create_app(Settings(env="development"))
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.gate = _wiring()
        app.state.db_sessions = async_sessionmaker(class_=StubSession)
        app.state.automation_schedules = schedules
        yield c


def about_of(c: TestClient, pid: str, agent_id: str) -> Response:
    return get(c, pid, f"{AGENTS}/{agent_id}/about")


def kinds(body: dict[str, object]) -> list[tuple[str, list[str]]]:
    steps = body["steps"]
    assert isinstance(steps, list)
    return [(one["step"], [line["kind"] for line in one["lines"]]) for one in steps]


# ---------------------------------------------------------------------------- the audience
def test_a_missing_agent_and_an_agent_outside_the_audience_are_one_404_on_the_about_tab(
    client: TestClient, stored: Stored
) -> None:
    """Somebody else's personal agent, a row that does not construct and a slug nothing holds
    answer identically, and the owner of the personal agent is answered.

    Delete this and the About tab's address enumerates the company's agents one slug at a time."""
    stored.agents["their_notes"] = agent_row(
        "their_notes", level=Visibility.PERSONAL, owner_id="u_wide"
    )
    broken = agent_row("broken_desk")
    broken.required_tools = ["a_tool_nothing_allows"]
    stored.agents["broken_desk"] = broken

    missing = about_of(client, "u_narrow", "nothing_here")
    assert missing.status_code == 404
    assert missing.json()["message"] == Absent.public_message
    for refused in (
        about_of(client, "u_narrow", "their_notes"),
        about_of(client, "u_narrow", "broken_desk"),
    ):
        assert refused.status_code == 404
        assert {k: v for k, v in refused.json().items() if k != "trace_id"} == {
            k: v for k, v in missing.json().items() if k != "trace_id"
        }
    assert about_of(client, "u_wide", "their_notes").status_code == 200


def test_nothing_about_an_agent_the_caller_may_not_see_is_read_on_their_behalf(
    client: TestClient, stored: Stored, schedules: Schedules
) -> None:
    """A refused caller holding every tab's read causes one statement, for the agent row, and the
    automation store is never asked; the owner, holding nothing but the audience, causes the install
    read and still no automation read.

    Delete this and a refusal comes after reading another person's install or automations, which is
    a read made for somebody never entitled to it and a timing that says the agent exists."""
    stored.agents["their_notes"] = agent_row(
        "their_notes", level=Visibility.PERSONAL, owner_id="u_wide"
    )
    instance_row, version_row, _, _ = install_rows("their_notes")
    stored.installs["their_notes"] = (instance_row, version_row)

    def tables() -> list[str]:
        return [str(one.column_descriptions[-1]["entity"].__name__) for one in stored.statements]

    assert about_of(client, "u_elsewhere", "their_notes").status_code == 404
    assert tables() == ["AgentRow"]
    assert schedules.asked == []

    stored.statements.clear()
    assert about_of(client, "u_wide", "their_notes").status_code == 200
    assert tables() == ["AgentRow", "TemplateVersionRow"]
    assert schedules.asked == []


# --------------------------------------------------------------------------- what is said
def test_a_member_of_the_audience_is_told_the_surfaces_and_the_rule_and_nothing_of_the_setup(
    client: TestClient, stored: Stored
) -> None:
    """A reader holding nothing but a place in the audience gets the summary, a first step naming
    the surfaces, a last step saying where an answer goes, and the one sentence true of every agent.

    Delete this and the About tab either tells a member nothing at all, or tells them the ceiling,
    the tools and the leash the Settings tab is granted for."""
    an_acting_agent(stored)
    app_of(client).state.tools = tools_acting()

    body = about_of(client, "u_narrow", "quote_helper").json()

    assert body["agent_id"] == "quote_helper"
    assert body["summary"] == "Drafts a first answer to a pricing question."
    assert kinds(body) == [("starts", ["asked"]), ("result", ["answer"])]
    assert [step["number"] for step in body["steps"]] == [1, 2]
    assert body["never"] == [
        {"text": AN_AGENT_NEVER_SEES_MORE_THAN_ITS_CALLER, "every_agent": True}
    ]
    assert DRAFTS not in str(body)


def test_a_reader_of_the_settings_tab_is_told_what_the_agent_does_and_where_a_person_steps_in(
    client: TestClient, stored: Stored
) -> None:
    """The same agent for a reader of its configuration: the drafting action waits for a person and
    links to its leash row, the sending action is only practised and links to the leash card, and
    what it will never do includes what its ceiling rules out.

    Delete this and the About tab's middle three steps are never drawn for the administrator they
    were written for, or a practised action is drawn as one somebody approves."""
    an_acting_agent(stored)
    app_of(client).state.tools = tools_acting()

    body = about_of(client, "u_admin", "quote_helper").json()

    assert kinds(body) == [
        ("starts", ["asked"]),
        ("reads", ["read_tool", "rows"]),
        ("does", ["action", "action"]),
        ("person", ["awaits_approval", "approver", "practised"]),
        ("result", ["answer", "carried_out"]),
    ]
    actions = list(body["steps"][2]["lines"])
    assert [(one["tool"], one["effect"], one["rungs"], one["leash_entry"]) for one in actions] == [
        (DRAFTS, "draft", ["assisted"], True),
        (SENDS, "send", ["shadow"], False),
    ]
    assert body["steps"][3]["lines"][0]["tool"] == DRAFTS
    assert body["steps"][4]["lines"][1]["effect"] == "draft"
    assert [one["text"] for one in body["never"]] == [
        "It never moves money.",
        AN_AGENT_NEVER_SEES_MORE_THAN_ITS_CALLER,
    ]


def test_the_schedule_is_told_to_a_reader_of_the_automations_tab_and_names_only_what_is_running(
    client: TestClient, stored: Stored, schedules: Schedules
) -> None:
    """A reader holding the Automations tab's read is told the running automation starts the agent
    and where its result goes, and nothing about the stopped one; a reader without that read is told
    neither and the store is not asked on their behalf.

    Delete this and a stopped automation is said to start the agent, or a reader who may not see
    the Automations tab learns from the About tab that the agent runs on a schedule."""
    an_acting_agent(stored)
    app_of(client).state.tools = tools_acting()

    wide = about_of(client, "u_elsewhere", "quote_helper").json()
    scheduled = [
        line for step in wide["steps"] for line in step["lines"] if line["kind"] == "scheduled"
    ]
    assert [line["automation_id"] for line in scheduled] == ["auto_running"]
    assert scheduled[0]["text"] == f"{TEMPLATE.name}, on a schedule: {TEMPLATE.cadence.words()}."
    assert "run_result" in [
        kind for step, lines in kinds(wide) if step == "result" for kind in lines
    ]
    assert schedules.asked == ["quote_helper"]

    schedules.asked.clear()
    narrower = about_of(client, "u_admin", "quote_helper").json()
    assert "scheduled" not in str(kinds(narrower))
    assert "run_result" not in str(kinds(narrower))
    assert schedules.asked == []


def test_the_about_tab_offers_one_reader_the_surfaces_and_sources_the_workspace_does(
    client: TestClient, stored: Stored
) -> None:
    """The first step's surfaces are the workspace's channel rows for the same reader, and the
    sources it reads are the workspace's attached connector rows, for a wide and a narrow reader.

    Delete this and the two routes compute a reader's reach twice and drift, so the About tab names
    a surface or a source the Profile does not."""
    an_acting_agent(stored)
    instance_row, version_row, _, _ = install_rows(
        "quote_helper", connectors=(workspace_tests.SOURCE, "atlas")
    )
    stored.installs["quote_helper"] = (instance_row, version_row)
    app_of(client).state.tools = tools_acting()

    for pid in ("u_elsewhere", "u_narrow"):
        workspace = get(client, pid, f"{AGENTS}/quote_helper/workspace").json()
        about = about_of(client, pid, "quote_helper").json()
        lines = [line for step in about["steps"] for line in step["lines"]]
        asked = next(line for line in lines if line["kind"] == "asked")
        assert asked["channels"] == [one["channel"] for one in workspace["channels"]], pid
        assert [line["source"] for line in lines if line["kind"] == "source"] == [
            one["source"]
            for one in workspace["connectors"]["rows"]
            if one["presence"] == "attached"
        ], pid


# ------------------------------------------------------------------------------ the shapes
def test_the_about_router_intersects_no_entitlement_sets_and_asks_for_no_capability() -> None:
    """Parsed, not searched: no `intersect` call and no `holds` call in the module's source, and the
    parser finds both when handed them.

    Delete this and the About route grows a second copy of the platform's intersection, or a
    capability check the workspace does not make, and the two tabs disagree about who sees what."""
    source = inspect.getsource(agent_about_routes)
    assert intersections_in(source) == ()
    holds = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "holds"
    ]
    assert holds == []
    assert intersections_in("reach.intersect(ceiling)\n") == (1,)


def test_no_shape_on_the_about_tab_counts_what_a_step_left_out() -> None:
    """Asked of the models' own fields, because `hidden_count_fields` reads dataclass fields and
    every view here is a model; the model built beside them is the sibling proving the check finds
    a count.

    What breaks if this is deleted: a field counting the lines or steps a reader was not shown is
    added to the About view and nothing reports it."""
    for view in (AboutView, FlowStepView, FlowLineView, NeverView):
        assert not set(view.model_fields) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT, view.__name__

    class Counted(BaseModel):
        steps: list[FlowStepView]
        omitted: int

    assert set(Counted.model_fields) & NAMES_THAT_WOULD_BE_A_HIDDEN_COUNT == {"omitted"}
