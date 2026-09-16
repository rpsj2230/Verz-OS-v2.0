"""The line protocol a runner speaks, read as hostile input, and the tree a page becomes.

Task ids: M19.1.3
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from brain.browsing.enforcer import Refusal, Spend, authorise, compile_policy
from brain.browsing.envelope import Envelope, compile_envelope
from brain.browsing.planning import Goal, PlanRequest, plan
from brain.browsing.targets import Surface, Target, TargetRegistry, Verb
from brain.browsing.wire import (
    FIELDS,
    MAX_LINE_BYTES,
    MAX_NAME,
    MAX_NODES,
    Kind,
    WireError,
    action_of,
    decode,
    encode,
    policy_of,
    snapshot_fields,
    snapshot_from_accessibility,
    snapshot_of,
    start_fields,
    surfaces_of,
)
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier
from brain.ops.halt import NOTHING_HALTED

READ = Capability(value="read:browser_surface")
WRITE = Capability(value="write:browser_surface")
ORIGIN = "https://books.example"


def books() -> Target:
    return Target(
        name="books",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="filing",
                origin=ORIGIN,
                path="/filing",
                verbs=frozenset({Verb.OPEN, Verb.CLICK}),
                capability=WRITE,
            ),
        ),
    )


def envelope() -> Envelope:
    request = PlanRequest(
        goal=Goal(text="File it", asked_by="alex"), target="books", surfaces=("filing",)
    )
    reach = EntitlementSet(
        principal_id="alex",
        grants=(
            Grant(capability=READ, scope=Scope.department("finance")),
            Grant(capability=WRITE, scope=Scope.department("finance")),
        ),
    )
    return compile_envelope(
        plan(request, TargetRegistry(targets=(books(),))),
        books(),
        run_id="run-1",
        reach=reach,
        ceiling=AutonomyTier.AUTONOMOUS,
    )


def tree(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {"nodes": list(nodes)}


def ax(backend: object, role: str = "button", name: str = "Export", **extra: Any) -> dict[str, Any]:
    return {
        "nodeId": str(backend),
        "backendDOMNodeId": backend,
        "role": {"type": "role", "value": role},
        "name": {"type": "computedString", "value": name},
        **extra,
    }


# ------------------------------------------------------------------ the line
def test_a_line_longer_than_the_limit_is_refused_before_it_is_parsed() -> None:
    """The limit is on bytes read, not on a parsed object. Delete this and a runner can send a
    gigabyte of JSON and the control plane allocates it before refusing anything."""
    padding = "x" * MAX_LINE_BYTES
    line = json.dumps({"kind": "ended", "reason": padding}).encode()

    with pytest.raises(WireError, match="refused unread"):
        decode(line)


@pytest.mark.parametrize(
    "line",
    [
        b"not json",
        b"[1, 2]",
        b'{"kind": "exploit", "reason": "x"}',
        b'{"kind": "ended", "reason": "x", "also": "this"}',
        b'{"kind": "ended"}',
    ],
    ids=["not JSON", "not an object", "unknown kind", "extra field", "missing field"],
)
def test_a_line_that_is_not_exactly_a_declared_message_is_refused(line: bytes) -> None:
    """A tolerant reader is a second protocol. Delete this and a runner can attach a field the
    control plane ignores today and a later version reads."""
    with pytest.raises(WireError):
        decode(line)


def test_a_declared_message_round_trips() -> None:
    """The positive case. Delete this and a decoder refusing everything passes the test above."""
    message = decode(encode(Kind.ENDED, reason="stopped"))

    assert message.kind is Kind.ENDED
    assert message.fields == {"reason": "stopped"}


def test_a_message_is_refused_on_the_way_out_when_its_fields_are_not_the_declared_ones() -> None:
    """Delete this and the control plane can send a field its own reader would refuse."""
    with pytest.raises(WireError, match="carries"):
        encode(Kind.ENDED, reason="x", extra="y")


# ------------------------------------------------------------------ the tree
def test_nodes_are_named_by_the_browsers_backend_id_and_ignored_or_detached_nodes_are_dropped() -> (
    None
):
    """The reference is a number the page cannot see or set. Delete this and refs can be minted
    from something the page controls, which lets it move a ref onto a different element."""
    snapshot = snapshot_from_accessibility(
        tree(
            ax(12, "button", "Export"),
            ax(13, "link", "Hidden", ignored=True),
            {"nodeId": "x", "role": {"value": "text"}, "name": {"value": "no DOM node"}},
            ax(True, "button", "a bool is not an id"),
            ax(14, "", "no role"),
        ),
        run_id="run-1",
        sequence=1,
        origin=ORIGIN,
    )

    assert [(node.ref, node.role, node.name) for node in snapshot.nodes] == [
        ("n12", "button", "Export")
    ]


def test_a_replaced_node_leaves_the_old_reference_unknown_to_the_enforcer() -> None:
    """**Why the backend id is the reference.** The page swaps the button between snapshots; the
    browser gives the new one a new id, and an action citing the old ref is refused.

    Delete this and the reference check can pass on a ref that now names a different element."""
    policy = compile_policy(envelope())
    before = snapshot_from_accessibility(tree(ax(12)), run_id="run-1", sequence=2, origin=ORIGIN)
    after = snapshot_from_accessibility(tree(ax(99)), run_id="run-1", sequence=2, origin=ORIGIN)
    cite = action_of(
        decode(
            encode(
                Kind.ACT,
                index=1,
                surface="filing",
                verb="open",
                ref="n12",
                sequence=2,
                placeholder="",
                text="",
            )
        ),
        run_id="run-1",
        origin=ORIGIN,
    )

    assert authorise(policy, cite, before, Spend(), halts=NOTHING_HALTED, sequence=2).allowed
    refused = authorise(policy, cite, after, Spend(), halts=NOTHING_HALTED, sequence=2)
    assert refused.refusal is Refusal.UNKNOWN_REFERENCE


def test_a_second_accessibility_node_over_one_dom_node_keeps_the_first() -> None:
    """Delete this and one DOM node with two AX nodes raises, so a page ends every run by
    rendering a labelled control."""
    snapshot = snapshot_from_accessibility(
        tree(ax(5, "button", "First"), ax(5, "text", "Second")),
        run_id="run-1",
        sequence=1,
        origin=ORIGIN,
    )

    assert [node.name for node in snapshot.nodes] == ["First"]


def test_a_long_name_is_shortened_and_a_huge_tree_is_refused() -> None:
    """Delete this and a page can hand the actor a megabyte in one label, or a tree the actor
    reads the top of as though it were the whole page."""
    long = snapshot_from_accessibility(
        tree(ax(1, name="y" * (MAX_NAME + 50))), run_id="run-1", sequence=1, origin=ORIGIN
    )
    assert len(long.nodes[0].name) == MAX_NAME

    with pytest.raises(WireError, match="refused rather than read in part"):
        snapshot_from_accessibility(
            tree(*(ax(one) for one in range(1, MAX_NODES + 2))),
            run_id="run-1",
            sequence=1,
            origin=ORIGIN,
        )
    exactly = snapshot_from_accessibility(
        tree(*(ax(one) for one in range(1, MAX_NODES + 1))),
        run_id="run-1",
        sequence=1,
        origin=ORIGIN,
    )
    assert len(exactly.nodes) == MAX_NODES


def test_a_tree_with_no_node_list_is_refused() -> None:
    """Delete this and a malformed reply reads as an empty page, which a READ reports as nothing."""
    with pytest.raises(WireError, match="no node list"):
        snapshot_from_accessibility({}, run_id="run-1", sequence=1, origin=ORIGIN)


def test_a_snapshot_round_trips_through_its_message() -> None:
    """Delete this and the control plane's copy of a tree can differ from the runner's."""
    snapshot = snapshot_from_accessibility(
        tree(ax(3), ax(4, "link", "Next")), run_id="run-1", sequence=2, origin=ORIGIN
    )

    assert (
        snapshot_of(decode(encode(Kind.SNAPSHOT, **snapshot_fields(snapshot))), run_id="run-1")
        == snapshot
    )


# ------------------------------------------------------------------ the start
def test_a_start_message_rebuilds_the_policy_the_control_plane_compiled() -> None:
    """The positive case: the runner enforces exactly what the envelope permits.

    Delete this and `policy_of` can drop the unattended set or the budget and still pass the
    refusal below."""
    sealed = envelope()
    started = decode(encode(Kind.START, **start_fields(sealed, books(), approved=False)))

    assert policy_of(started) == compile_policy(sealed)
    assert surfaces_of(started) == {"filing": f"{ORIGIN}/filing"}


def test_a_start_message_whose_parts_were_widened_is_refused() -> None:
    """**The runner re-derives the digest.** A relay or a bug that adds a step, an origin or a
    budget line produces parts the digest does not cover.

    Delete this and whoever sits between the control plane and the container can widen the policy
    the container starts with."""
    fields = start_fields(envelope(), books(), approved=True)
    for change in (
        {"origins": [*fields["origins"], "https://elsewhere.example"]},
        {"steps": [*fields["steps"], ["filing", "upload"]]},
        {"budget": [["click", 99]]},
    ):
        widened = decode(encode(Kind.START, **{**fields, **change}))
        with pytest.raises(WireError, match="does not produce the digest"):
            policy_of(widened)


def test_an_approval_that_is_not_a_boolean_is_refused() -> None:
    """Delete this and `"false"`, which is truthy, approves every write in the run."""
    fields = start_fields(envelope(), books(), approved=True)

    with pytest.raises(WireError, match="neither yes nor no"):
        policy_of(decode(encode(Kind.START, **{**fields, "approved": "false"})))


def test_an_approved_start_carries_the_approval_into_the_policy() -> None:
    """Delete this and an approved envelope starts a runner that refuses every write."""
    sealed = envelope()
    policy = policy_of(decode(encode(Kind.START, **start_fields(sealed, books(), approved=True))))

    assert policy.approved_digest == sealed.digest()
    assert policy.may_write("filing", Verb.CLICK)


def test_an_action_takes_its_origin_from_the_browser_and_never_from_the_instruction() -> None:
    """Delete this and an instruction could say where the page is, which checks nothing."""
    assert "origin" not in FIELDS[Kind.ACT]
    made = action_of(
        decode(
            encode(
                Kind.ACT,
                index=1,
                surface="filing",
                verb="click",
                ref="n1",
                sequence=1,
                placeholder="",
                text="",
            )
        ),
        run_id="run-1",
        origin="https://reported.example",
    )
    assert made.origin == "https://reported.example"
