"""A workflow definition is read whole or refused with every reason, and a step reads only what an
earlier step declared.

Over `brain.orchestration.workflow.read_definition`. Each refusal has a sibling that shows the same
shape accepted, so a reader that refuses everything does not pass.

Task ids: M17.6.1, M17.6.3, M17.6.4, M17.6.5, M17.6.6
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from brain.orchestration.contract import FieldKind
from brain.orchestration.workflow import (
    MOST_RETRIES,
    MOST_STEPS,
    OnFailure,
    Op,
    Ref,
    StepKind,
    WorkflowError,
    read_definition,
)


def _good() -> dict[str, Any]:
    return {
        "name": "Monthly report",
        "steps": [
            {
                "id": "fetch",
                "kind": "connector_read",
                "target": "analytics.read_traffic",
                "arguments": {"month": "2026-09"},
                "outputs": [
                    {"name": "visits", "kind": "integer", "path": "visits"},
                    {"name": "rate", "kind": "decimal", "path": "0.rate"},
                ],
            },
            {
                "id": "rank",
                "kind": "tool",
                "target": "search.read_rank",
                "arguments": {"visits": {"$ref": "fetch.visits"}},
                "after": ["fetch"],
                "when": {"ref": "fetch.visits", "op": "gt", "value": 100},
                "parallel": True,
                "retry": {"limit": 2, "backoff_seconds": 1.5},
                "on_failure": "handler",
                "outputs": [{"name": "position", "kind": "integer", "path": "position"}],
            },
            {
                "id": "fallback",
                "kind": "tool",
                "target": "search.read_cached_rank",
                "after": ["rank"],
                "handles": "rank",
            },
        ],
    }


def _refused(raw: object) -> tuple[str, ...]:
    with pytest.raises(WorkflowError) as raised:
        read_definition(raw)
    return raised.value.reasons


def _with(step: int, **over: Any) -> dict[str, Any]:
    raw = copy.deepcopy(_good())
    raw["steps"][step].update(over)
    return raw


def test_a_good_definition_is_read_with_everything_it_says() -> None:
    """Delete this and every refusal below would pass for a reader that refuses everything."""
    definition = read_definition(_good())
    assert definition.name == "Monthly report"
    fetch, rank, fallback = definition.steps
    assert fetch.kind is StepKind.CONNECTOR_READ
    assert [(o.name, o.kind, o.path) for o in fetch.outputs] == [
        ("visits", FieldKind.INTEGER, "visits"),
        ("rate", FieldKind.DECIMAL, "0.rate"),
    ]
    assert rank.arguments == {"visits": Ref("fetch", "visits")}
    assert rank.when is not None and rank.when.op is Op.GT and rank.when.value == 100
    assert rank.parallel and rank.retry.limit == 2 and rank.retry.backoff_seconds == 1.5
    assert rank.on_failure is OnFailure.HANDLER and fallback.handles == "rank"
    assert definition.waves() == (("fetch",), ("rank",), ("fallback",))


def test_a_step_can_read_only_an_output_an_earlier_step_declared() -> None:
    """Delete this and a step can read an output nobody declared, or one from a step it does not
    follow, which makes every result an input to every later step."""
    undeclared = _with(1, arguments={"visits": {"$ref": "fetch.clicks"}})
    assert any("never declared" in one for one in _refused(undeclared))
    not_followed = _with(1, after=[], handles=None, on_failure="stop")
    assert any("does not follow" in one for one in _refused(not_followed))
    later = _with(0, arguments={"x": {"$ref": "rank.position"}})
    assert _refused(later)


def test_a_condition_reads_declared_outputs_of_steps_it_follows_and_nothing_else() -> None:
    """Delete this and a condition can compare something nobody declared."""
    assert _refused(_with(1, when={"ref": "fetch.clicks", "op": "gt", "value": 1}))
    assert _refused(_with(1, when={"ref": "fetch.visits", "op": "matches", "value": 1}))
    assert _refused(_with(1, when={"ref": "fetch.visits", "op": "gt", "value": [1]}))
    assert read_definition(_with(1, when={"ref": "fetch.visits", "op": "is_true"}))


@pytest.mark.parametrize("kind", ["text", "summary", "string", "hologram"])
def test_an_output_cannot_be_prose_or_a_kind_that_does_not_exist(kind: str) -> None:
    """Delete this and prose enters a workflow by way of an output."""
    raw = _with(0, outputs=[{"name": "note", "kind": kind, "path": "note"}])
    assert any("prose is not a kind" in one for one in _refused(raw))


def test_steps_are_listed_in_the_order_they_follow_each_other() -> None:
    """Delete this and a cycle is possible, and the check for one is a second answer to whether a
    run can start."""
    assert any("not listed before" in one for one in _refused(_with(0, after=["rank"])))
    assert any("not a step here" in one for one in _refused(_with(1, after=["ghost"])))
    raw = _good()
    raw["steps"].append(copy.deepcopy(raw["steps"][0]))
    assert any("more than once" in one for one in _refused(raw))


def test_a_step_with_a_handler_names_exactly_one_and_the_handler_follows_it() -> None:
    """Delete this and a failure path hands over to nothing, or to two steps."""
    assert _refused(_with(1, on_failure="stop"))
    assert _refused(_with(2, after=[]))
    assert _refused(_with(2, handles="fallback"))
    assert read_definition(_good())
    alone = _good()
    del alone["steps"][2]
    assert any("exactly one step must handle it" in one for one in _refused(alone))
    twice = _good()
    twice["steps"].append({**copy.deepcopy(twice["steps"][2]), "id": "second_fallback"})
    assert any("exactly one step must handle it" in one for one in _refused(twice))


def test_retries_are_bounded_and_a_step_has_no_key_it_was_not_given() -> None:
    """Delete this and a step retries for ever, or carries a key nothing reads."""
    # Stated as numbers and not as the module's own constant, which a changed constant would move
    # with: three retries are read, four are not.
    assert read_definition(_with(1, retry={"limit": 3}))
    assert _refused(_with(1, retry={"limit": 4}))
    assert MOST_RETRIES == 3
    assert _refused(_with(1, retry={"limit": 1, "backoff_seconds": 600}))
    assert _refused(_with(1, retry={"limit": True}))
    assert _refused(_with(1, mystery=1))
    assert _refused(_with(1, parallel="yes"))


def test_an_argument_is_plain_data_or_a_reference_and_never_wiring() -> None:
    """Delete this and a step can set the entitlement a tool runs with, or pass a record."""
    assert _refused(_with(0, arguments={"entitlement": "all"}))
    assert _refused(_with(0, arguments={"x": {"$ref": "fetch.n", "extra": 1}}))
    assert _refused(_with(0, arguments={"x": {"a": {"$ref": "fetch.n"}}}))
    assert _refused(_with(0, arguments={"x": {"a": {"b": {"c": {"d": {"e": 1}}}}}}))
    assert read_definition(_with(0, arguments={"filters": {"clauses": [{"field": "name"}]}}))
    assert _refused(_with(0, arguments={"x": float("nan")}))
    assert _refused(_with(0, arguments={"Bad Name": 1}))
    assert read_definition(_with(0, arguments={"x": [1, "a", None, True]}))


def test_a_skill_step_names_a_skill_tool_and_every_target_is_a_tool_name() -> None:
    """Delete this and a skill step can name any tool, and a target can be an address."""
    assert _refused(_with(0, kind="skill", target="analytics.read_traffic"))
    assert read_definition(_with(0, kind="skill", target="skill.run_script"))
    assert _refused(_with(0, target="https://example.invalid/x"))


def test_a_definition_has_a_name_and_between_one_and_the_most_steps() -> None:
    """Delete this and an empty workflow, or one past the bound, is stored."""
    assert _refused({"steps": _good()["steps"]})
    assert _refused({"name": "x", "steps": []})
    assert _refused({"name": "x", "steps": "no"})
    assert _refused({"name": " ", "steps": _good()["steps"]})
    assert _refused(["not", "an", "object"])
    many = [
        {
            "id": f"s{i}",
            "kind": "tool",
            "target": "alpha.read_beta",
            "after": [f"s{i - 1}"] if i else [],
        }
        for i in range(MOST_STEPS + 1)
    ]
    assert _refused({"name": "x", "steps": many})
    assert read_definition({"name": "x", "steps": many[:MOST_STEPS]})


def test_every_reason_is_reported_together() -> None:
    """Delete this and an author fixes one problem at a time."""
    raw = _good()
    raw["steps"][0]["outputs"][0]["kind"] = "text"
    raw["steps"][1]["retry"] = {"limit": 99}
    assert len(_refused(raw)) >= 2
