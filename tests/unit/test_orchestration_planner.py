"""A model's plan is untrusted text, and what passes is only what the existing checks admit.

Over `brain.orchestration.planner`: the reply is read into steps, or refused whole with its reasons.
The checks it passes are the ones that already existed (`read_proposal`, `FieldKind`, the callee
allow-list, the graph), so these tests assert that each of them is reached from a reply, which is
the thing nobody had called before.

Task ids: M18.1.1, M18.1.4, M18.5.3
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from brain.agents.model import CEILING_PRINCIPAL_PREFIX
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.models.driver import Role
from brain.models.routing import Tier
from brain.orchestration.contract import PROSE_IS_NOT_A_CONTRACT, FieldKind
from brain.orchestration.coordinator import Callee, not_allowed_sentence
from brain.orchestration.planner import (
    MOST_TOOL_HINTS,
    PlanRefusedError,
    checked_request,
    planner_messages,
    read_plan,
    system_prompt,
)


def _callee(agent_id: str, *capabilities: str) -> Callee:
    return Callee(
        agent_id=agent_id,
        tier=Tier.MAIN,
        ceiling=EntitlementSet(
            principal_id=f"{CEILING_PRINCIPAL_PREFIX}{agent_id}",
            grants=tuple(
                Grant(capability=Capability(value=one), scope=Scope()) for one in capabilities
            ),
        ),
    )


CALLEES = {"web": _callee("web", "read:site.score"), "seo": _callee("seo", "read:search.rank")}


def _subtask(subtask_id: str = "a", /, **over: Any) -> dict[str, Any]:
    return {
        "subtask_id": subtask_id,
        "callee": "web",
        "objective": "Find the site's score for this client",
        "output": [{"name": "score", "kind": "integer"}],
        "depends_on": [],
        **over,
    }


def _reply(*subtasks: dict[str, Any]) -> str:
    return json.dumps({"subtasks": list(subtasks)})


def _refusal(text: str) -> tuple[str, ...]:
    with pytest.raises(PlanRefusedError) as raised:
        read_plan(text, CALLEES)
    return raised.value.reasons


def test_a_good_plan_is_read_into_steps_whose_capabilities_come_from_the_specialist() -> None:
    """Delete this and the planner reads nothing: every refusal below would pass for a reader that
    refuses everything. The capabilities are the specialist's own, never the reply's."""
    steps = read_plan(
        _reply(
            _subtask("a"),
            _subtask("b", callee="seo", depends_on=["a"], tool_hints=["rank_lookup"]),
        ),
        CALLEES,
    )
    assert [one.subtask_id for one in steps] == ["a", "b"]
    assert [one.callee_id for one in steps] == ["web", "seo"]
    assert steps[1].depends_on == ("a",)
    assert [c.value for c in steps[0].contract.capabilities] == ["read:site.score"]
    assert [c.value for c in steps[1].contract.capabilities] == ["read:search.rank"]
    assert steps[1].contract.tool_hints == ("rank_lookup",)
    assert [(f.name, f.kind) for f in steps[0].contract.output] == [("score", FieldKind.INTEGER)]


def test_a_fenced_reply_is_read_as_the_json_it_wraps() -> None:
    """Delete this and a model that wraps its JSON in a code fence, as models do, is refused."""
    fenced = "```json\n" + _reply(_subtask()) + "\n```"
    assert len(read_plan(fenced, CALLEES)) == 1


@pytest.mark.parametrize("key", ["cost", "seconds", "weight", "tokens", "priority", "coupling"])
def test_a_plan_that_prices_itself_is_refused_by_the_proposal_check(key: str) -> None:
    """Delete this and a planner can set its own weights and talk its way past the gate.

    The refusal is `read_proposal`'s, which names the planner trying to price its own plan.
    """
    reasons = _refusal(_reply(_subtask(**{key: 1})))
    assert len(reasons) == 1 and key in reasons[0]


@pytest.mark.parametrize("key", ["capabilities", "scope", "ceiling", "grants", "reach"])
def test_a_plan_cannot_say_what_a_specialist_may_reach(key: str) -> None:
    """Delete this and a model can write a capability or a scope into a subtask.

    The key is not one a subtask has, so the strict reader refuses it as an unknown key.
    """
    reasons = _refusal(_reply(_subtask(**{key: ["read:everything"]})))
    assert len(reasons) == 1 and key in reasons[0]


@pytest.mark.parametrize("kind", ["text", "summary", "paragraph", "string", "markdown", "Prose"])
def test_a_plan_that_asks_a_subtask_for_prose_is_refused_with_the_contracts_reason(
    kind: str,
) -> None:
    """Delete this and prose enters the merge by way of a field the model named (M18.1.4)."""
    reasons = _refusal(_reply(_subtask(output=[{"name": "note", "kind": kind}])))
    assert any(PROSE_IS_NOT_A_CONTRACT in one for one in reasons)


def test_a_kind_that_does_not_exist_is_refused_and_the_real_ones_are_named() -> None:
    """Delete this and an invented kind is passed on to be validated against nothing."""
    reasons = _refusal(_reply(_subtask(output=[{"name": "x", "kind": "hologram"}])))
    assert len(reasons) == 1
    assert all(one.value in reasons[0] for one in FieldKind)


def test_a_specialist_that_was_not_offered_is_refused_as_an_unknown_one_is() -> None:
    """Delete this and a planner can name any agent and be told whether it exists."""
    unknown = _refusal(_reply(_subtask("a", callee="ghost")))
    with pytest.raises(PlanRefusedError) as raised:
        read_plan(_reply(_subtask("a", callee="seo")), {"web": CALLEES["web"]})
    assert unknown == (not_allowed_sentence("a"),)
    assert raised.value.reasons == (not_allowed_sentence("a"),)


def test_a_plan_with_no_output_for_a_subtask_is_refused() -> None:
    """Delete this and a subtask whose promise is empty is satisfied by anything it returns."""
    assert _refusal(_reply(_subtask(output=[])))
    assert _refusal(_reply(_subtask(output=[{"name": "score"}])))
    assert _refusal(_reply(_subtask(output=[{"name": "Score", "kind": "integer"}])))


def test_a_dependency_written_as_a_bare_string_is_refused() -> None:
    """Delete this and a dependency read one character at a time names nothing and passes."""
    assert _refusal(_reply(_subtask(depends_on="a")))


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        "{}",
        json.dumps({"subtasks": []}),
        json.dumps({"subtasks": [1]}),
        json.dumps({"subtasks": [_subtask()], "weights": {}}),
        '{"subtasks": [NaN]}',
    ],
)
def test_a_reply_that_is_not_an_object_holding_only_a_list_of_subtasks_is_refused_whole(
    text: str,
) -> None:
    """Delete this and a model's malformed reply is repaired or half-used."""
    assert _refusal(text)


def test_a_plan_of_more_than_twelve_subtasks_is_refused() -> None:
    """Delete this and a project is accepted as a plan."""
    many = [_subtask(f"s{index}") for index in range(13)]
    assert _refusal(_reply(*many))
    assert len(read_plan(_reply(*many[:12]), CALLEES)) == 12


def test_a_subtask_id_that_is_not_a_short_lowercase_word_is_refused() -> None:
    """Delete this and an id that is a sentence, or a path, becomes a key in the trace."""
    assert _refusal(_reply(_subtask("Has Spaces")))
    assert _refusal(_reply(_subtask("x" * 40)))


def test_tool_hints_are_a_short_list_of_short_names_and_nothing_else() -> None:
    """Delete this and a hint is a place to put a paragraph."""
    assert _refusal(_reply(_subtask(tool_hints="rank")))
    assert _refusal(_reply(_subtask(tool_hints=["x"] * (MOST_TOOL_HINTS + 1))))
    assert _refusal(_reply(_subtask(tool_hints=["y" * 200])))
    assert read_plan(_reply(_subtask(tool_hints=["rank"])), CALLEES)


def test_every_reason_is_reported_and_none_of_the_bad_steps_is_dropped_quietly() -> None:
    """Delete this and the plan is repaired by losing the step the model got wrong."""
    reasons = _refusal(
        _reply(
            _subtask("a", callee="ghost"),
            _subtask("b", output=[{"name": "n", "kind": "text"}]),
            _subtask("c"),
        )
    )
    assert len(reasons) == 2


def test_the_prompt_carries_the_request_and_the_names_of_the_specialists_and_nothing_else() -> None:
    """Delete this and a persona, a tool list or a record can ride along to the provider."""
    from brain.orchestration.planner import Offered

    messages = planner_messages(
        "Review the client's site", [Offered("web", "Website checker"), Offered("seo", "Search")]
    )
    assert [one.role for one in messages] == [Role.SYSTEM, Role.USER]
    assert messages[0].content == system_prompt()
    sent = json.loads(messages[1].content)
    assert set(sent) == {"request", "specialists"}
    assert sent["request"] == "Review the client's site"
    assert sent["specialists"] == [
        {"id": "web", "name": "Website checker"},
        {"id": "seo", "name": "Search"},
    ]


def test_the_instruction_names_every_kind_and_forbids_any_weight() -> None:
    """Delete this and the model is not told the kinds it may use, so every plan is refused."""
    text = system_prompt()
    assert all(one.value in text for one in FieldKind)
    assert "Do not give any cost" in text


def test_a_blank_or_too_long_request_is_refused_before_any_model_is_asked() -> None:
    """Delete this and an empty request costs a model call."""
    with pytest.raises(PlanRefusedError):
        checked_request("   ")
    with pytest.raises(PlanRefusedError):
        checked_request("x" * 2_001)
    assert checked_request("Review the site") == "Review the site"
