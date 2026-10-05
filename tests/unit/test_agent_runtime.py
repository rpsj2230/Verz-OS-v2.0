"""The agent runtime: the one loop that hands a model tools, driven over scripted replies.

Over `brain.gate.runtime` with no database and no provider: the model is a list of replies, the
tools are handlers in a registry, and the reach is a set built here. Each property is asserted on
what the loop was handed and what it handed on, including what the model was shown.

Task ids: M13.7.1, M13.7.2, M13.8.2
"""

from __future__ import annotations

import ast
import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.core.field_policy import Classification, FieldPolicy, FieldRule
from brain.core.scope import Scope
from brain.gate.abstain import Abstention, AbstentionReason, SearchScope
from brain.gate.compose import ComposedAnswer
from brain.gate.leash import Leash
from brain.gate.model_lane import ModelLane
from brain.gate.roster import run_entitlement
from brain.gate.runtime import (
    SEND_ONE_OBJECT,
    TOOL_NOT_AVAILABLE,
    AgentRuntime,
    FinalAnswer,
    RunHaltedError,
    RunRecord,
    ToolProposal,
    ToolRefusedError,
    parse_reply,
)
from brain.gate.screening import NOTHING_MATCHED
from brain.gate.stop import StopReason
from brain.knowledge.visibility import Visibility
from brain.models.driver import DriverMessage, DriverResponse, TokenUsage
from brain.models.metering import Meter
from brain.tools.registry import ToolRegistry
from tests.unit.test_answer_lane import Sink

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "brain"

#: Far from any wall clock: nothing here is about the present.
NOW = datetime(2019, 3, 1, 9, 0, tzinfo=UTC)

PRICE = "read:price_note.amount"
NAME = "read:price_note.title"
WRITE = "write:price_note.amount"


class PriceNote(Entity):
    title: str = ""
    amount: str = ""
    secret: str = ""


NOTE = PriceNote(
    entity="price_note", id="n1", title="Hosting", amount="40 a month", secret="SECRETOCHRE"
)


def read_notes() -> TypedResult[PriceNote]:
    return TypedResult[PriceNote](records=(NOTE,), source="notes", fetched_at=NOW.isoformat())


def definition(name: str, capability: str, effect: SideEffect = SideEffect.NONE) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"does {name}",
        entity="price_note",
        required_capability=capability,
        side_effect=effect,
        identity_mode=IdentityMode.DELEGATED,
    )


def registry() -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(definition("notes.read_note", PRICE), read_notes)
    tools.register(definition("notes.update_note", WRITE, SideEffect.WRITE), read_notes)
    return tools


POLICY = FieldPolicy(
    rules=(
        FieldRule.of("price_note", "title", NAME, Classification.INTERNAL),
        FieldRule.of("price_note", "amount", PRICE, Classification.INTERNAL),
    )
)


def holding(*capabilities: str, principal: str = "u_asker") -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal,
        grants=tuple(
            Grant(capability=Capability(value=one), scope=Scope.unrestricted())
            for one in capabilities
        ),
    )


def agent(
    *capabilities: str, max_turns: int | None = None, max_tool_calls: int | None = None
) -> AgentRecord:
    return AgentRecord(
        agent_id="pricing_desk",
        display_name="Pricing desk",
        persona="Answers about prices.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=AgentAuthority(
            scope=Scope.unrestricted(),
            capabilities=tuple(Capability(value=one) for one in capabilities),
            allowed_tools=frozenset({"notes.read_note", "notes.update_note"}),
            max_side_effect=SideEffect.WRITE,
        ),
        created_by="u_steward",
        max_turns=max_turns,
        max_tool_calls=max_tool_calls,
    )


@dataclass
class Model:
    """An `AnswerModel` replying from a script, keeping every conversation it was shown."""

    replies: list[str]
    tokens: int = 10
    shown: list[tuple[DriverMessage, ...]] = field(default_factory=list)

    async def complete(self, messages: Sequence[DriverMessage], **_: Any) -> DriverResponse:
        self.shown.append(tuple(messages))
        text = self.replies.pop(0) if self.replies else '{"answer": "out of script"}'
        return DriverResponse(
            deployment_id="d",
            model="m",
            text=text,
            usage=TokenUsage(input_tokens=self.tokens, output_tokens=self.tokens),
            finish_reason="stop",
        )


@dataclass
class Tools:
    """A `ToolCaller` calling the registry's handler, keeping each reach it was handed."""

    tools: ToolRegistry
    reaches: list[EntitlementSet] = field(default_factory=list)
    refuse: bool = False

    def call(
        self,
        *,
        tool: ToolDefinition,
        arguments: Mapping[str, Any],
        entitlement: EntitlementSet,
        now: datetime | None,
    ) -> object:
        del arguments, now
        self.reaches.append(entitlement)
        if self.refuse:
            raise ToolRefusedError("arguments refused")
        return self.tools.get(tool.name).handler()


@dataclass
class Runs:
    kept: list[RunRecord] = field(default_factory=list)

    async def record(self, run: RunRecord) -> None:
        self.kept.append(run)


@dataclass
class Setup:
    runtime: AgentRuntime
    model: Model
    tools: Tools
    runs: Runs


def setup(
    replies: list[str],
    *,
    asker: EntitlementSet | None = None,
    now_reach: EntitlementSet | None = None,
    record: AgentRecord | None = None,
    told: str = "",
    tokens: int = 10,
) -> Setup:
    held = asker or holding(PRICE, NAME, WRITE)
    tools = registry()
    caller = Tools(tools)
    runs = Runs()

    async def reach_now(now: datetime) -> EntitlementSet:
        del now
        return now_reach or held

    async def halted() -> str:
        return told

    runtime = AgentRuntime(
        record=record or agent(PRICE, NAME, WRITE),
        asker=held,
        registry=tools,
        leash=Leash(),
        tools=caller,
        policy_for=lambda _: POLICY,
        reach_now=reach_now,
        halted=halted,
        assessment=NOTHING_MATCHED,
        runs=runs,
        clock=lambda: 0.0,
        wall=lambda: NOW,
    )
    return Setup(runtime=runtime, model=Model(replies, tokens=tokens), tools=caller, runs=runs)


def run(made: Setup) -> Any:
    lane = ModelLane(search=cast(Any, None), model=made.model)
    return asyncio.run(
        made.runtime.drafted(
            "what does hosting cost",
            lane=lane,
            scope=SearchScope(),
            sink=Sink(),
            now=NOW,
            meter=Meter(),
            trace_id="t-runtime-1",
            started=lambda: None,
        )
    )


CALL = json.dumps({"tool": "notes.read_note", "arguments": {}})
ANSWER = json.dumps({"answer": "Hosting is 40 a month."})


# ------------------------------------------------------------------ the protocol
def test_a_reply_is_a_tool_request_an_answer_or_nothing() -> None:
    """**The protocol is strict.** One object with exactly the keys of one shape; a fenced
    object is unwrapped; prose, two shapes at once and extra keys are no proposal. Delete this
    and the parser can start reading intent out of prose, which is a model deciding what runs."""
    assert parse_reply(CALL) == ToolProposal(tool="notes.read_note", arguments={})
    assert parse_reply(ANSWER) == FinalAnswer(answer="Hosting is 40 a month.")
    assert parse_reply(f"```json\n{ANSWER}\n```") == FinalAnswer(answer="Hosting is 40 a month.")
    for malformed in (
        "Sure! " + ANSWER,
        json.dumps({"tool": "notes.read_note", "answer": "both"}),
        json.dumps({"answer": "x", "confidence": 1}),
        json.dumps(["notes.read_note"]),
        json.dumps({"tool": "Not A Tool!"}),
    ):
        assert parse_reply(malformed) is None, malformed


# ------------------------------------------------------------------ the loop
def test_a_run_reads_through_a_tool_and_answers_citing_what_it_read() -> None:
    """**The positive case, end to end.** A tool call, its redacted result shown to the model, and
    an answer composed with citations from what the model was shown, recorded as answered with
    its counts. Delete this and every refusal test below passes for a loop that never answers."""
    made = setup([CALL, ANSWER])

    drafted = run(made)

    assert isinstance(drafted.outcome, ComposedAnswer)
    assert drafted.outcome.text == "Hosting is 40 a month."
    assert {(one.entity, one.record_id, one.field) for one in drafted.outcome.citations} == {
        ("price_note", "n1", "amount"),
        ("price_note", "n1", "title"),
    }
    [kept] = made.runs.kept
    assert (kept.stop_reason, kept.turns, kept.tool_calls) == (StopReason.ANSWERED, 2, 1)


def test_the_model_is_shown_only_the_redacted_result_and_no_side_effecting_tool() -> None:
    """**What the model sees.** A field no rule classifies never reaches a prompt, and a tool that
    writes is not offered in this release. Delete this and a run can show a model a field the
    asker may not read, or offer it a write nothing can hold for a person yet."""
    made = setup([CALL, ANSWER])

    run(made)

    everything = "\n".join(one.content for convo in made.model.shown for one in convo)
    assert "SECRETOCHRE" not in everything
    assert "40 a month" in everything
    assert "notes.update_note" not in everything
    assert "notes.read_note" in everything


def test_the_tool_is_called_at_the_callers_reach_narrowed_by_the_agent() -> None:
    """**The one intersection.** The reach the handler is handed is `run_entitlement` of the
    asker and the agent, so a capability the asker holds and the agent does not is not in it.
    Delete this and a run can read at the asker's whole reach through a narrow agent."""
    asker = holding(PRICE, NAME, WRITE, "read:client.name")
    made = setup([CALL, ANSWER], asker=asker)

    run(made)

    [handed] = made.tools.reaches
    expected = run_entitlement(asker, made.runtime.record)
    assert handed.ent_hash() == expected.ent_hash()
    assert not handed.holds(Capability(value="read:client.name"), NOW)


def test_a_grant_revoked_mid_run_refuses_the_next_call_in_the_one_sentence() -> None:
    """**M13.8.2.** The reach is resolved again before the call; a capability no longer held is
    refused with `TOOL_NOT_AVAILABLE`, the handler is never called, and the run goes on. Delete
    this and a run reads for a person after their access was taken away."""
    made = setup([CALL, ANSWER], now_reach=holding(NAME))

    drafted = run(made)

    assert made.tools.reaches == []
    assert TOOL_NOT_AVAILABLE in made.model.shown[1][-1].content
    assert isinstance(drafted.outcome, Abstention)


def test_a_tool_not_offered_and_arguments_refused_are_one_sentence() -> None:
    """A tool the run was not offered, one that does not exist and arguments the tool refuses
    are each told `TOOL_NOT_AVAILABLE` and nothing else, so a model cannot map the catalogue by
    asking. Delete this and the refusals grow reasons."""
    unknown = json.dumps({"tool": "notes.update_note", "arguments": {}})
    made = setup([unknown, CALL, ANSWER])
    made.tools.refuse = True

    run(made)

    told = [convo[-1].content for convo in made.model.shown[1:]]
    assert told == [TOOL_NOT_AVAILABLE, TOOL_NOT_AVAILABLE]


def test_a_malformed_reply_is_a_turn_and_the_turn_bound_stops_the_run() -> None:
    """**M13.7.2.** A reply that is no proposal is answered with `SEND_ONE_OBJECT` and counted, and
    a model that never sends one stops at the agent's turn bound, recorded as the bound reached.
    Delete this and a confused model loops until somebody notices the bill."""
    made = setup(["I think the answer is 40."] * 5, record=agent(PRICE, NAME, max_turns=3))

    drafted = run(made)

    [kept] = made.runs.kept
    assert (kept.stop_reason, kept.turns) == (StopReason.TURN_BOUND, 3)
    assert made.model.shown[1][-1].content == SEND_ONE_OBJECT
    assert isinstance(drafted.outcome, Abstention)
    assert drafted.outcome.reason is AbstentionReason.NOTHING_RETRIEVED


def test_an_agent_can_lower_its_turn_bound_and_never_raise_it() -> None:
    """The product's default is a ceiling: an agent asking for more turns gets the default. Delete
    this and an agent's setting becomes a way to run without a bound."""
    made = setup(["no"] * 20, record=agent(PRICE, NAME, max_turns=50))

    run(made)

    assert made.runs.kept[0].turns == 8


def test_the_tool_call_bound_stops_a_run_that_only_calls_tools() -> None:
    """A model asking for a tool on every turn stops at the tool-call bound before the turn bound
    is reached, named as the bound it reached. Delete this and the tool-call bound is decoration."""
    made = setup([CALL] * 20, record=agent(PRICE, NAME, max_turns=8, max_tool_calls=2))

    run(made)

    [kept] = made.runs.kept
    assert (kept.stop_reason, kept.tool_calls) == (StopReason.TOOL_CALL_BOUND, 2)


def test_the_token_budget_stops_a_run() -> None:
    """A run that has spent its tokens stops before the next turn. Delete this and a run can spend
    without limit on a long conversation of short turns."""
    made = setup([CALL] * 20, tokens=40_000)

    run(made)

    assert made.runs.kept[0].stop_reason is StopReason.SPEND_BOUND


def test_a_halted_run_reads_nothing_and_asks_no_model() -> None:
    """A run somebody stopped is refused before anything: no model, no tool, no row read. Delete
    this and a stop button leaves a run going."""
    made = setup([CALL, ANSWER], told="Stopped by an administrator.")

    with pytest.raises(RunHaltedError) as stopped:
        run(made)

    assert stopped.value.told == "Stopped by an administrator."
    assert made.model.shown == [] and made.tools.reaches == []


def test_an_agent_with_no_tool_to_offer_does_not_ask_a_model() -> None:
    """An agent whose catalogue projects to nothing is refused before any model is asked, and
    recorded as refused. Delete this and a run asks a model with no tools, which answers from its
    training and reads as a researched answer."""
    made = setup([ANSWER], asker=holding("read:client.name"))

    drafted = run(made)

    assert made.model.shown == []
    assert made.runs.kept[0].stop_reason is StopReason.REFUSED
    assert isinstance(drafted.outcome, Abstention)


# ------------------------------------------------------------------ one runtime (M13.7.1)
#: Modules allowed to call a model at all, each for a reason that is not an agent run.
CALLS_A_MODEL_WITHOUT_TOOLS: frozenset[str] = frozenset(
    {
        "brain.gate.model_lane",
        "brain.builder.coauthor",
        "brain.ops.model_probe_run",
        "brain.provider_routes",
        "brain.models.adapter",
    }
)

#: Names that mean a module holds a tool catalogue or the runtime's protocol.
TOOL_BEARING: frozenset[str] = frozenset(
    {"ProjectedCatalogue", "invoke", "project", "ToolProposal", "tools_block", "PROTOCOL"}
)


def _modules() -> dict[str, ast.Module]:
    found: dict[str, ast.Module] = {}
    for path in sorted(SRC.rglob("*.py")):
        module = ".".join(path.relative_to(SRC.parent).with_suffix("").parts)
        found[module] = ast.parse(path.read_text(encoding="utf-8"))
    return found


def _calls_a_model(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "complete"
        for node in ast.walk(tree)
    )


def _imported(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
    return names


def test_only_the_runtime_calls_a_model_while_holding_tools() -> None:
    """**M13.7.1's own sentence: a test fails if a second code path calls a model with tools.**
    Every module that calls `.complete(` is either the runtime or on the short list of callers
    that ask a model with no tools, and none of those imports a projected catalogue, `invoke` or
    the runtime's protocol. Read from the source. Delete this and a second agent loop can be
    written beside the runtime with its own idea of the reach."""
    modules = _modules()
    callers = {name for name, tree in modules.items() if _calls_a_model(tree)}

    assert callers - CALLS_A_MODEL_WITHOUT_TOOLS == {"brain.gate.runtime"}
    for name in callers - {"brain.gate.runtime"}:
        assert not (_imported(modules[name]) & TOOL_BEARING), name


def test_the_answer_lane_hands_a_tool_loop_to_the_runtime_and_nothing_else() -> None:
    """The lane calls the runtime through `ModelLane.runtime` and calls `draft` otherwise; it
    builds no loop of its own. Delete this and the lane can grow a tool step beside the runtime."""
    tree = _modules()["brain.gate.answer"]
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert "drafted" in called
    assert "complete" not in called
