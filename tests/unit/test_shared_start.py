"""The shared start of a model request names only tools everybody holds (needs-rupash 175, A).

Each refusal has the sibling that proves the shared start still carries what it should: the
person who holds everything gets the tools everybody holds in the first message and their own in the
second, and the person who lacks one is told of neither half of it.

Task ids: M3.7.2
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from brain.core.entitlement import Capability
from brain.gate.runtime import PROTOCOL, tools_block
from brain.gate.shared_start import (
    EVERYBODY_HOLDS,
    shared_and_following,
    universal_tools,
)
from brain.identity.lifecycle import STARTER_PACK
from brain.models.driver import Role
from brain.tools.registry import ToolRegistry
from tests.unit.test_agent_runtime import (
    ANSWER,
    NAME,
    PRICE,
    WRITE,
    agent,
    definition,
    holding,
    read_notes,
    run,
    setup,
)

#: A tool everybody holds under the joiner's pack, and two that the pack does not give.
SHARED = "knowledge.read_document"
SHARED_CAPABILITY = "read:knowledge"


def _registry() -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(definition("notes.read_note", PRICE), read_notes)
    tools.register(definition("notes.read_title", NAME), read_notes)
    tools.register(definition(SHARED, SHARED_CAPABILITY), read_notes)
    return tools


def test_the_tools_everybody_holds_are_those_the_joiners_pack_covers() -> None:
    """The knowledge tool is universal and a tool the pack does not give is not; with no pack
    nothing is shared.

    Delete this and the shared start names a tool somebody does not hold, or shares nothing."""
    found = universal_tools(_registry())
    assert found == {SHARED}
    assert universal_tools(_registry(), ()) == frozenset()
    assert STARTER_PACK.capabilities == EVERYBODY_HOLDS
    assert Capability(value=SHARED_CAPABILITY) in EVERYBODY_HOLDS


def test_the_two_halves_are_the_offered_tools_split_and_never_more() -> None:
    """Every tool of either half was offered, in order, once; a universal tool not offered is in
    neither.

    Delete this and the split can add a tool the person was not offered."""
    tools = _registry()
    offered = tuple(tools.get(name).definition for name in ("notes.read_note", SHARED))
    shared, following = shared_and_following(offered, frozenset({SHARED, "notes.read_title"}))
    assert [one.name for one in shared] == [SHARED]
    assert [one.name for one in following] == ["notes.read_note"]
    assert {one.name for one in (*shared, *following)} == {one.name for one in offered}


def _messages(*capabilities: str, universal: frozenset[str]) -> list[tuple[Role, str]]:
    made = setup(
        [ANSWER],
        asker=holding(*capabilities),
        record=agent(PRICE, NAME, WRITE, SHARED_CAPABILITY),
    )
    registry = _registry()
    allowed = frozenset(registry.names())
    record = made.runtime.record
    record = record.model_copy(
        update={"authority": record.authority.model_copy(update={"allowed_tools": allowed})}
    )
    runtime: Any = replace(made.runtime, registry=registry, record=record, universal=universal)
    run(replace_runtime(made, runtime))
    return [(one.role, one.content) for one in made.model.shown[0]]


def replace_runtime(made: Any, runtime: Any) -> Any:
    return replace(made, runtime=runtime)


def test_with_the_switch_off_a_run_sends_the_one_block_it_always_did() -> None:
    """No universal tool: one system message, the protocol then every offered tool.

    Delete this and switching nothing on changes what every run sends."""
    sent = _messages(PRICE, NAME, SHARED_CAPABILITY, universal=frozenset())
    systems = [text for role, text in sent if role is Role.SYSTEM]
    assert len(systems) == 1
    assert systems[0].startswith(PROTOCOL)
    assert all(name in systems[0] for name in ("notes.read_note", "notes.read_title", SHARED))


def test_the_shared_start_holds_what_everybody_holds_and_the_person_s_own_follow() -> None:
    """Switched on, the first system message is the protocol and the universal tool, and the second
    is the person's own tools, which are named nowhere in the first.

    Delete this and the shared start carries tools only some people hold, or none are shared."""
    sent = _messages(PRICE, NAME, SHARED_CAPABILITY, universal=frozenset({SHARED}))
    systems = [text for role, text in sent if role is Role.SYSTEM]
    assert len(systems) == 2
    assert SHARED in systems[0] and "notes.read_note" not in systems[0]
    assert "notes.read_title" not in systems[0]
    assert "notes.read_note" in systems[1] and "notes.read_title" in systems[1]


def test_a_person_without_a_tool_never_sees_it_named_in_either_half() -> None:
    """Somebody who holds the universal tool's grant and neither of the others is sent it in the
    shared start and sent no name of the others anywhere; somebody who lacks the universal tool's
    grant is sent a start without it.

    Delete this and the shared start tells a person a tool exists that they cannot use."""
    only_shared = _messages(SHARED_CAPABILITY, universal=frozenset({SHARED}))
    everything = " ".join(text for _, text in only_shared)
    assert SHARED in everything
    assert "notes.read_note" not in everything and "notes.read_title" not in everything

    without = _messages(PRICE, universal=frozenset({SHARED}))
    named = " ".join(text for _, text in without)
    assert SHARED not in named and "notes.read_title" not in named
    assert "notes.read_note" in named

    # And what two people who both hold the universal tool are sent first is the same bytes.
    a = [
        t
        for r, t in _messages(PRICE, SHARED_CAPABILITY, universal=frozenset({SHARED}))
        if r is Role.SYSTEM
    ]
    b = [
        t
        for r, t in _messages(NAME, SHARED_CAPABILITY, universal=frozenset({SHARED}))
        if r is Role.SYSTEM
    ]
    assert a[0] == b[0] == f"{PROTOCOL}\n\n{tools_block([_registry().get(SHARED).definition])}"
    assert a[1] != b[1]
