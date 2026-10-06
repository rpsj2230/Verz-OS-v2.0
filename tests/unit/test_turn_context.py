"""One assembler for what a model is shown on a turn, and a trace that names its parts (M16.6.1).

Run against the real `brain.gate.answer.answer_lane`, the real model lane and a real executor over a
recording transport, through `tests.unit.test_model_lane.ask`, so what is asserted is what a
request carries rather than what a fake was handed.

Task ids: M16.6.1
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from brain.core.redaction import ChannelPayload
from brain.gate import model_lane, turn_context
from brain.gate.model_lane import FixedHints, prompt_for, prompt_of
from brain.gate.turn_context import (
    INCLUDED_ATTRIBUTE,
    LEFT_OUT_ATTRIBUTE,
    WITHOUT_A_SOURCE,
    ContextNote,
    ContextParts,
    LeftOut,
    Part,
    assemble,
)
from brain.ops.trace_store import rows_of, steps_of
from brain.ops.tracing import SAFE_ATTRIBUTES
from tests.unit.test_model_lane import QUESTION, Passages, ask

SRC = Path(__file__).resolve().parents[2] / "src" / "brain"


def test_a_turn_with_nothing_but_its_question_names_every_part_as_left_out_with_its_reason() -> (
    None
):
    """Each part absent is named with one reason from the closed vocabulary: the two nothing holds
    say so, knowledge a run's tools read says so, and every other says nothing came back.

    Delete this and a part can drop out of the trace silently, or be named with a reason that
    says more than the prompt did."""
    note = ContextParts(question="q").note()

    assert note.included == ()
    assert dict(note.left_out) == {
        Part.CONVERSATION: LeftOut.NOTHING,
        Part.SESSION: LeftOut.NOTHING,
        Part.TASK: LeftOut.NOTHING,
        Part.PROJECT: LeftOut.NO_SOURCE,
        Part.ASKER_MEMORY: LeftOut.NOTHING,
        Part.AGENT_MEMORY: LeftOut.NO_SOURCE,
        Part.KNOWLEDGE: LeftOut.BY_TOOLS,
    }
    with_payload = ContextParts(question="q", knowledge=ChannelPayload(records=())).note()
    assert dict(with_payload.left_out)[Part.KNOWLEDGE] is LeftOut.NOTHING


def test_the_parts_a_turn_holds_are_named_as_included_in_the_order_the_prompt_reads_them() -> None:
    """The positive half: a part holding anything is included, in `Part`'s order.

    Delete this and a note that left everything out would satisfy the test above."""
    note = ContextParts(
        question="q",
        conversation=("earlier",),
        asker_memory=("I prefer the figure first",),
        knowledge=ChannelPayload(records=({"entity": "knowledge", "id": "c1"},)),
    ).note()

    assert note.included == (Part.CONVERSATION, Part.ASKER_MEMORY, Part.KNOWLEDGE)
    assert note.attributes() == {
        INCLUDED_ATTRIBUTE: "conversation/asker_memory/knowledge",
        LEFT_OUT_ATTRIBUTE: ("session:none/task:none/project:no_source/agent_memory:no_source"),
    }


def test_assemble_reads_each_recollection_once_and_takes_no_project_or_agent_memory() -> None:
    """`assemble` reads the session and the asker's memories once each, and has no parameter for
    the two parts nothing holds, which is what `WITHOUT_A_SOURCE` says, read off the signature
    rather than restated.

    Delete this and the day a project source is added, nothing makes the trace stop saying it has
    none."""

    class Counted:
        def __init__(self, said: tuple[str, ...]) -> None:
            self.said = said
            self.calls = 0

        async def hints(self) -> tuple[str, ...]:
            self.calls += 1
            return self.said

    session, asker = Counted(("for now, in euros",)), Counted(("I prefer the figure first",))
    parts = asyncio.run(assemble("q", conversation=("before",), session=session, asker=asker))

    assert (parts.session, parts.asker_memory, parts.conversation) == (
        ("for now, in euros",),
        ("I prefer the figure first",),
        ("before",),
    )
    assert session.calls == asker.calls == 1
    taken = set(inspect.signature(assemble).parameters)
    fields = {"conversation", "session", "task", "project", "asker_memory", "agent_memory"}
    fed = {"conversation", "session", "task", "asker", "knowledge"}
    assert {Part(one) for one in fields if one not in taken and one != "asker_memory"} == (
        WITHOUT_A_SOURCE
    )
    assert fed <= taken


def test_a_hint_source_that_returns_nothing_and_no_hint_source_are_one_reason() -> None:
    """An asker with no memories and an asker whose memories the run may not recall are told
    apart nowhere: both are `nothing`, so a trace reader learns nothing about the asker.

    Delete this and a reason for "you may not see it" could be added beside "there is none"."""
    none = asyncio.run(assemble("q", asker=None, knowledge=ChannelPayload()))
    empty = asyncio.run(assemble("q", asker=FixedHints(()), knowledge=ChannelPayload()))

    assert none.note() == empty.note()


def test_the_model_lane_prompt_is_built_from_the_assembled_parts() -> None:
    """`prompt_of` is `prompt_for` over the parts, with knowledge read by tools shown as no
    passages, so the two answer paths render one value the same way.

    Delete this and `prompt_of` can drop a part that `prompt_for` would have shown."""
    parts = ContextParts(
        question="q",
        conversation=("earlier",),
        asker_memory=("hint",),
        knowledge=ChannelPayload(records=({"entity": "knowledge", "id": "c1", "title": "t"},)),
    )
    assert prompt_of(parts) == prompt_for(
        "q", parts.knowledge or ChannelPayload(), (), ("hint",), earlier=("earlier",)
    )
    tools = ContextParts(question="q")
    assert prompt_of(tools) == prompt_for("q", ChannelPayload())


def test_a_model_answer_carries_its_context_note_to_the_answer_and_the_trace() -> None:
    """**The leaf's sentence on a real request.** A question a model answers with a hint shown
    carries a note naming the asker's memory and the knowledge as included and the rest as left
    out; the request's trace keeps exactly those words through `mask`; and no hint text reaches
    either.

    Delete this and the note can be built and reach no trace, which is the shape the product's
    unwired modules have taken before."""
    run = ask(hints=("I prefer the figure first HINTVERMILION",))

    assert run.answered is not None
    note = run.answered.context
    assert note is not None
    assert note.included == (Part.ASKER_MEMORY, Part.KNOWLEDGE)
    (root, *_) = rows_of("t", steps_of(run.finished, (), environment="development"))
    attributes = dict(cast(Mapping[str, str], root["attributes"]))
    assert attributes[INCLUDED_ATTRIBUTE] == "asker_memory/knowledge"
    assert attributes[LEFT_OUT_ATTRIBUTE] == (
        "conversation:none/session:none/task:none/project:no_source/agent_memory:no_source"
    )
    assert "HINTVERMILION" not in repr(root)
    assert {INCLUDED_ATTRIBUTE, LEFT_OUT_ATTRIBUTE} <= SAFE_ATTRIBUTES


def test_a_question_no_model_was_asked_about_carries_no_context_note() -> None:
    """A question answered from a rule, or one nothing was retrieved for, showed a model nothing,
    so it carries no note and its trace names no part.

    Delete this and a fast-lane answer could be traced as though a model had been shown context."""
    fast = ask("hours left on Acme")
    nothing = ask(QUESTION, search=_empty())

    for run in (fast, nothing):
        assert run.answered is not None and run.answered.context is None
        (root, *_) = rows_of("t", steps_of(run.finished, (), environment="development"))
        assert INCLUDED_ATTRIBUTE not in cast(Mapping[str, str], root["attributes"])


def _empty() -> Passages:
    return Passages()


def test_only_the_assembler_reads_a_turns_recollections_and_only_prompt_of_builds_a_prompt() -> (
    None
):
    """`ONE_PLACE_ASSEMBLES_WHAT_A_MODEL_IS_SHOWN`, held to the source: nothing under `src/brain`
    calls `prompt_for` but `prompt_of`, nothing calls `assemble` but the two answer paths (the
    model lane's `draft` and the agent runtime's loop), and `draft` reads no recollection itself.

    Delete this and a second assembler can be written beside the first, with the trace naming
    the parts of one and the model shown the parts of the other."""
    callers: dict[str, set[str]] = {"prompt_for": set(), "assemble": set()}
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # Which of the two names this module means: `assemble` is also a function of
        # `brain.models.assembly`, so only a module importing this one's is counted for it.
        imported = {
            alias.asname or alias.name: node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        wanted = {
            "prompt_for": "brain.gate.model_lane",
            "assemble": "brain.gate.turn_context",
        }
        module = f"brain.{path.relative_to(SRC).with_suffix('')}".replace("/", ".")
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(function):
                name = (
                    node.func.id
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    else ""
                )
                if name in wanted and (
                    imported.get(name) == wanted[name] or module == wanted[name]
                ):
                    callers[name].add(f"{module.removeprefix('brain.')}.{function.name}")

    assert callers["prompt_for"] == {"gate.model_lane.prompt_of"}
    assert callers["assemble"] == {"gate.model_lane.draft", "gate.runtime._loop"}
    drafted = ast.unparse(ast.parse(inspect.getsource(model_lane.draft)))
    assert ".hints()" not in drafted
    assert turn_context.ONE_PLACE_ASSEMBLES_WHAT_A_MODEL_IS_SHOWN


def test_a_note_s_attributes_survive_the_trace_mask_and_an_empty_one_adds_none() -> None:
    """The two attribute values are system vocabulary that `mask` keeps, even at their longest
    (every part left out, or every part included), and a note with nothing on one side adds no
    attribute rather than an empty string `mask` would turn into a shape.

    Delete this and a part name with a character outside the token grammar would reach the trace
    as a masked shape and say nothing."""
    from brain.ops.tracing import Span, mask

    every_left_out = ContextParts(question="q").note()
    every_included = ContextNote(included=tuple(Part), left_out=())
    for note in (every_left_out, every_included):
        kept = mask(
            Span(name="request", environment="development", attributes=dict(note.attributes()))
        )
        assert dict(kept.attributes) == dict(note.attributes())
    assert ContextNote(included=(), left_out=()).attributes() == {}


def test_the_agent_runtime_is_shown_the_same_assembled_parts_and_names_them() -> None:
    """**The second answer path takes the same value.** An agent run with an earlier question, a
    hint and a session note shows the model all three in its user turn, built by `tool_loop_turn`
    from the assembled parts, declares the hint as carried, and its answer names the parts with
    knowledge left out because its tools read it.

    Delete this and the runtime can go back to sending the bare question, so an agent's answer
    forgets what the person said for this conversation while the model lane's remembers."""
    from typing import Any

    from brain.gate.abstain import SearchScope
    from brain.models.disclosure import DataCategory
    from brain.models.metering import Meter
    from tests.unit.test_agent_runtime import ANSWER, CALL, NOW, setup
    from tests.unit.test_answer_lane import Sink

    class Said:
        async def hints(self) -> tuple[str, ...]:
            return ("Call me Sam SESSIONTEAL",)

    made = setup([CALL, ANSWER])
    lane = model_lane.ModelLane(
        search=cast(Any, None),
        model=made.model,
        hints=FixedHints(("I prefer the figure first HINTAMBER",)),
        session=Said(),
        follow_up=model_lane.FollowUp(earlier=("what about EARLIERCOBALT",)),
    )
    drafted = asyncio.run(
        made.runtime.drafted(
            "what does hosting cost",
            lane=lane,
            scope=SearchScope(),
            sink=Sink(),
            now=NOW,
            meter=Meter(),
            trace_id="t-runtime-context",
            started=lambda: None,
        )
    )

    first_user = made.model.shown[0][1].content
    assert "HINTAMBER" in first_user and "SESSIONTEAL" in first_user
    assert first_user.index("EARLIERCOBALT") < first_user.index("Question:")
    assert first_user.index("Question:") < first_user.index("HINTAMBER")
    assert DataCategory.MEMORY_HINTS in made.model.categories[0]
    assert drafted.context is not None
    assert drafted.context.included == (Part.CONVERSATION, Part.SESSION, Part.ASKER_MEMORY)
    assert (Part.KNOWLEDGE, LeftOut.BY_TOOLS) in drafted.context.left_out
