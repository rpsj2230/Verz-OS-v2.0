"""Which channels an agent may answer on, and that the list, the record and the chat path agree.

Pure apart from the source reads: `brain.agents.model`'s list and validators, the row round trip,
`brain.api_routes.roster_of` asked on a chat channel, and the labels the console offers. The route
proofs are in `tests/unit/test_answer_route_gate.py` and the builder's in the two route test files.

Task ids: M13.7.4, M13.7.2
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import ValidationError

from brain.agents.model import (
    ASKING_CHANNELS,
    MAX_TOOL_CALLS_CAP,
    MAX_TURNS_CAP,
    AgentAudience,
    AgentAuthority,
    AgentRecord,
    answering_on,
)
from brain.core.entitlement import EntitlementSet
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.gate.context import Channel, TrafficClass, traffic_class_for
from brain.gate.roster import StoredAgents
from brain.knowledge.visibility import Visibility

#: Far from any wall clock: nothing here is about the present.
NOW = datetime(2999, 1, 1, tzinfo=UTC)
SRC = Path(__file__).parents[2] / "src" / "brain"


def an_agent(agent_id: str = "helper", **fields: object) -> AgentRecord:
    return AgentRecord.model_validate(
        {
            "agent_id": agent_id,
            "display_name": agent_id.title(),
            "persona": "Answer briefly.",
            "audience": AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
            "authority": AgentAuthority(),
            "created_by": "u_steward",
            **fields,
        }
    )


# ------------------------------------------------------------------ which channels count
def test_every_route_a_question_takes_to_the_roster_is_a_channel_an_agent_may_answer_on() -> None:
    """**The list is every channel a question reaches the roster on.** `/answer` names a browser
    session console and a service key api (`channel_for`), and every chat channel with a receiver
    reaches the same function through the chat answerer. Delete this and a channel can reach the
    roster with no box to switch an agent on for it, so no agent could ever answer there."""
    from brain.api_routes import channel_for
    from brain.channels.adapter import channel_wires

    # Only the session id is read; a cast at the claims type, whose constructor proves nothing here.
    on_answer = {
        channel_for(cast(Any, SimpleNamespace(session_id=session))) for session in ("s", None)
    }
    assert on_answer == {Channel.CONSOLE, Channel.API}
    assert channel_wires(), "no chat channel has a receiver, or this test is reading nothing"
    reached = {*on_answer, *channel_wires()}
    assert {one.value for one in reached} <= set(ASKING_CHANNELS)


def test_the_scheduler_is_left_out_and_never_reaches_a_roster() -> None:
    """The one channel left off is the install's own housekeeping, and no module that names it
    selects an agent: the canary asks the answer lane directly. Delete this and a box for the
    scheduler could be offered that switches nothing on, or a scheduled run could start selecting
    agents with nobody having decided which may answer it."""
    assert Channel.SCHEDULER.value not in ASKING_CHANNELS
    assert traffic_class_for(Channel.SCHEDULER) is TrafficClass.SYSTEM
    naming = [
        path
        for path in SRC.rglob("*.py")
        if "Channel.SCHEDULER" in path.read_text(encoding="utf-8")
        and path.name not in {"context.py", "admission.py"}
    ]
    assert naming, "the scheduler is named somewhere, or this test is reading nothing"
    for path in naming:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        called = {
            node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        assert not called & {"answered_for", "roster_of", "answer_roster"}, path


def test_every_other_channel_is_on_the_list_in_the_enums_order() -> None:
    """The positive sibling: everything but the scheduler, in `Channel`'s order, the website widget
    and the company's own webhook among them. Delete this and the list could quietly shrink to the
    human channels, so an upgraded agent stops answering a service key that named it yesterday."""
    assert tuple(one.value for one in Channel if one is not Channel.SCHEDULER) == ASKING_CHANNELS


# ------------------------------------------------------------------ the record
def test_a_record_holds_its_channels_sorted_once_each_and_refuses_one_nothing_is_asked_on() -> None:
    """A channel nothing is asked on is refused rather than dropped, and the ones it holds are
    sorted with repeats removed. Delete this and a box that switches nothing on can be stored as
    ticked, or a steward's choice can be edited without their being told."""
    assert an_agent(channels=["slack", "console", "slack"]).channels == ("console", "slack")
    assert an_agent().channels == ()
    for wrong in (["scheduler"], ["sms"], "console"):
        with pytest.raises(ValidationError):
            an_agent(channels=wrong)


def test_a_run_bound_is_none_or_between_one_and_its_cap() -> None:
    """Zero and one past each cap are refused; one, the cap and None are kept. Delete this and a
    run can be bounded to nothing, which is an agent that stops before it starts."""
    for field, cap in (("max_turns", MAX_TURNS_CAP), ("max_tool_calls", MAX_TOOL_CALLS_CAP)):
        for kept in (None, 1, cap):
            assert getattr(an_agent("helper", **{field: kept}), field) == kept
        for refused in (0, cap + 1):
            with pytest.raises(ValidationError):
                an_agent("helper", **{field: refused})


def test_the_tool_call_cap_admits_a_tool_on_every_turn_and_a_whole_cached_plan() -> None:
    """The caps are stated against what they must hold, not against themselves: a run allowed every
    turn can call a tool on each, and a plan the cache would replay fits inside the bound. Delete
    this and the cap can be lowered below a plan this install replays, so the replay is cut off."""
    from brain.gate.caches import MAX_PLAN_TOOLS

    assert MAX_TOOL_CALLS_CAP >= MAX_TURNS_CAP
    assert MAX_TOOL_CALLS_CAP >= MAX_PLAN_TOOLS
    assert MAX_TURNS_CAP >= 1


def test_the_column_is_wide_enough_for_every_channel() -> None:
    """Delete this and a channel added with a longer name is refused by the database on the first
    agent switched on for it."""
    from brain.tables.agent import CHANNEL_CHARS

    assert max(len(one.value) for one in Channel) <= CHANNEL_CHARS


def test_a_rebuilt_record_keeps_its_channels_and_bounds_through_the_row() -> None:
    """`agent_values` writes them and `record_of` reads them back; a row built in memory holding
    None for the list reads as no channel. Delete this and a stored agent can lose its channels on
    the way out of the database, which switches it off everywhere without anybody pressing
    anything."""
    from brain.agent_routes import record_of
    from brain.agents.install_store import agent_values
    from brain.tables.agent import AgentRow

    record = an_agent(channels=["lark", "console"], max_turns=3, max_tool_calls=9)
    assert record_of(AgentRow(**agent_values(record))) == record
    bare = agent_values(record)
    for added in ("channels", "max_turns", "max_tool_calls"):
        del bare[added]
    back = record_of(AgentRow(**bare))
    assert back is not None
    assert (back.channels, back.max_turns, back.max_tool_calls) == ((), None, None)
    assert answering_on(back, ["console"]).channels == ("console",)


# ------------------------------------------------------------------ a chat channel
def _person() -> Principal:
    return Principal(
        id="u_reader",
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name="Reader",
    )


def _roster_on(channel: Channel, records: Sequence[AgentRecord]) -> frozenset[str]:
    from brain.api_routes import Answering, roster_of
    from brain.tools.registry import ToolRegistry

    async def read() -> StoredAgents:
        return StoredAgents(records=records)

    asking = Answering(
        principal=_person(),
        reach=EntitlementSet(principal_id="u_reader", grants=()),
        channel=channel,
        now=NOW,
    )
    roster = asyncio.run(roster_of(SimpleNamespace(agent_roster=read), asking, ToolRegistry()))
    return roster.visible


def test_a_chat_question_selects_only_from_agents_enabled_on_its_channel() -> None:
    """The roster `answered_for` reads for a Lark message holds the agent switched on for Lark and
    not the one switched on for the console alone, and the console's the other way round. Delete
    this and the chat channels, which reach the roster by a different route from the web, can be
    left unfiltered while the web test stays green."""
    agents = (an_agent("on_lark", channels=["lark"]), an_agent("on_console", channels=["console"]))
    assert {"on_lark"} <= _roster_on(Channel.LARK, agents)
    assert "on_console" not in _roster_on(Channel.LARK, agents)
    assert "on_lark" not in _roster_on(Channel.CONSOLE, agents)
    assert "on_console" in _roster_on(Channel.CONSOLE, agents)


def test_the_chat_answerer_answers_on_the_channel_the_message_arrived_on() -> None:
    """The chat answerer hands `answered_for` the inbound event's own channel, which is what the
    roster filters on. Read from the source because the answerer needs a live channel to run.
    Delete this and a chat question can be answered as if it came from the console, so every agent
    switched on for the console answers in every chat."""
    from brain.chat_answer import ChatAnswerer

    tree = ast.parse(textwrap.dedent(inspect.getsource(ChatAnswerer._ask)))
    assigned = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and [getattr(t, "id", None) for t in node.targets] == ["channel"]
    ]
    assert [ast.unparse(one.value) for one in assigned] == ["inbound.event.channel"]
    answering = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Answering"
    ]
    assert len(answering) == 1
    keywords = {one.arg: ast.unparse(one.value) for one in answering[0].keywords}
    assert keywords["channel"] == "channel"


# ------------------------------------------------------------------ what the console offers
def test_every_channel_an_agent_may_answer_on_has_a_label_and_the_labels_agree() -> None:
    """The boxes are the list and nothing else, each with the word the Channels screen uses for it.
    Delete this and a channel can be offered with no label, or one channel can be called two
    things on two screens."""
    from brain.agent_lifecycle_routes import AGENT_CHANNEL_LABELS, channel_choices
    from brain.binding_routes import CHANNEL_LABELS

    assert tuple(AGENT_CHANNEL_LABELS) == ASKING_CHANNELS
    for channel, label in CHANNEL_LABELS.items():
        assert AGENT_CHANNEL_LABELS[channel.value] == label
    assert [one.name for one in channel_choices()] == list(ASKING_CHANNELS)
