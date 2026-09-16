"""Reading the code for every door to the outside, and every call through one that issues.

`brain.ops.effects` is the check that makes "every side-effecting operation has a key" a claim
about the tree rather than about a list, and a check nobody has watched produce a finding is a
check nobody knows works. So almost every test here builds a small tree of its own, with a
protocol and a call in the shape under test, and asks the scan what it found there. The
repository's own tree is `tests/invariants/test_every_side_effect_is_keyed.py`'s.

Each refusal has its admitted sibling beside it, for the reason CLAUDE.md gives: a scan that
flagged every call would pass every refusal test on its own.

Task ids: M17.3.1
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from brain.ops.effects import (
    PORTS,
    WHY,
    Admitted,
    Repeat,
    classification_gaps,
    effect_callables,
    effect_calls,
    protocol_methods,
    unkeyed_effects,
)

PROTOCOLS = """
from typing import Protocol


class Messenger(Protocol):
    def send(self, body: str, *, to: str) -> None: ...

    def healthy(self) -> bool: ...

    @property
    def name(self) -> str: ...

    def _private(self) -> None: ...


class Webhook(Protocol):
    def send(self, request: object) -> object: ...
"""

#: The classification the small tree is read against.
SMALL: dict[str, Repeat] = {
    "brain.ports:Messenger.send": Repeat.ISSUES,
    "brain.ports:Messenger.healthy": Repeat.READS,
    "brain.ports:Webhook.send": Repeat.KEYED_BY_THE_RECEIVER,
}


def _tree(tmp_path: Path, **modules: str) -> Path:
    """A package called `brain` holding the protocols above and the modules given."""
    root = tmp_path / "brain"
    root.mkdir()
    (root / "ports.py").write_text(PROTOCOLS, encoding="utf-8")
    for name, source in modules.items():
        (root / f"{name}.py").write_text(textwrap.dedent(source), encoding="utf-8")
    return root


def _admitted(tmp_path: Path, source: str) -> list[Admitted]:
    return [one.admitted for one in effect_calls(SMALL, _tree(tmp_path, caller=source))]


# ------------------------------------------------------------------ the population
def test_every_public_method_of_every_protocol_is_found_and_properties_are_not(
    tmp_path: Path,
) -> None:
    """Two protocols, three public methods, one property and one private method.

    Delete this and the scan could miss a protocol written with a subscripted base, or count a
    property, and every classification check downstream would be asked about the wrong set."""
    root = _tree(tmp_path)
    (root / "more.py").write_text(
        "import typing\n\nclass Keyed(typing.Protocol[str]):\n    def put(self) -> None: ...\n",
        encoding="utf-8",
    )

    assert set(protocol_methods(root)) == {
        "brain.ports:Messenger.send",
        "brain.ports:Messenger.healthy",
        "brain.ports:Webhook.send",
        "brain.more:Keyed.put",
    }


def test_a_protocol_method_nobody_classified_is_a_finding_and_so_is_a_stale_one(
    tmp_path: Path,
) -> None:
    """A new door with no classification, and a classification of a door that is gone, are both
    named; the complete classification of the same tree is clean.

    Delete this and a protocol method added next month would never be asked whether calling it
    twice sends twice, which is the whole of what makes "every" true."""
    root = _tree(tmp_path)

    assert classification_gaps(SMALL, root, {}) == ()
    missing = classification_gaps({k: v for k, v in SMALL.items() if "healthy" not in k}, root, {})
    stale = classification_gaps({**SMALL, "brain.ports:Gone.send": Repeat.READS}, root, {})

    assert len(missing) == 1
    assert missing[0].startswith("brain.ports:Messenger.healthy: a protocol method with no")
    assert len(stale) == 1
    assert stale[0].startswith("brain.ports:Gone.send: classified here and declared nowhere")


def test_every_classification_has_a_written_reason_and_the_shipped_table_uses_only_them() -> None:
    """Delete this and a member of `Repeat` could be added with no sentence saying why a repeat
    of it is safe, which is the one sentence a reviewer reads."""
    assert set(WHY) == set(Repeat)
    assert all(WHY[one].strip() for one in Repeat)
    assert set(PORTS.values()) <= set(Repeat)


# ------------------------------------------------------------------ the calls
def test_a_call_to_a_door_that_issues_outside_the_door_is_unkeyed(tmp_path: Path) -> None:
    """Delete this and the scan could admit every call, which passes every test below."""
    source = """
    from brain.ports import Messenger

    def deliver(adapter: Messenger) -> None:
        adapter.send("hello", to="room")
    """
    root = _tree(tmp_path, caller=source)

    (found,) = unkeyed_effects(SMALL, root)
    assert (found.module, found.function, found.method) == ("brain.caller", "deliver", "send")
    assert "outside issue_once" in found.sentence()


def test_a_call_inside_a_function_handed_to_the_door_is_admitted(tmp_path: Path) -> None:
    """By name and by keyword, and a lambda positionally.

    Delete this and the one shape every issuing call in the repository takes would be a
    finding, and the invariant would be switched off within the day."""
    source = """
    from brain.ops.idempotency import issue_once
    from brain.ports import Messenger

    def by_name(adapter: Messenger, ledger, operation) -> None:
        def send(_):
            adapter.send("hello", to="room")
        issue_once(ledger, operation, send)

    def by_keyword(adapter: Messenger, ledger, operation) -> None:
        def post(_):
            adapter.send("hello", to="room")
        issue_once(ledger, operation, effect=post)

    def by_lambda(adapter: Messenger, ledger, operation) -> None:
        issue_once(ledger, operation, lambda _: adapter.send("hello", to="room"))
    """

    assert _admitted(tmp_path, source) == [Admitted.THROUGH_THE_DOOR] * 3


def test_a_function_of_the_same_name_that_is_not_the_one_handed_to_the_door_is_not_admitted(
    tmp_path: Path,
) -> None:
    """A `send` defined in another function is not the effect this `issue_once` was handed.

    Delete this and any nested function sharing a name with an effect anywhere in the module
    would be treated as keyed."""
    source = """
    from brain.ops.idempotency import issue_once
    from brain.ports import Messenger

    def elsewhere(adapter: Messenger) -> None:
        def send(_):
            adapter.send("hello", to="room")
        send(None)

    def keyed(adapter: Messenger, ledger, operation) -> None:
        def send(_):
            return None
        def beside(_):
            adapter.send("hello", to="room")
        issue_once(ledger, operation, send)
        beside(None)

    def handed_to_something_else(adapter: Messenger, ledger, operation) -> None:
        def send(_):
            adapter.send("hello", to="room")
        defer(ledger, operation, send)
    """

    assert _admitted(tmp_path, source) == [Admitted.UNKEYED] * 3


def test_a_call_after_the_no_side_effect_guard_is_admitted_and_one_before_it_is_not(
    tmp_path: Path,
) -> None:
    """Delete this and the guard could come after the call it is meant to protect, or anywhere in
    the module, and still admit it."""
    source = """
    from brain.ops.idempotency import assert_no_side_effect
    from brain.ports import Messenger

    def guarded(adapter: Messenger, tool) -> None:
        assert_no_side_effect(tool)
        adapter.send("hello", to="room")

    def too_late(adapter: Messenger, tool) -> None:
        adapter.send("hello", to="room")
        assert_no_side_effect(tool)
    """

    assert _admitted(tmp_path, source) == [Admitted.NOTHING_TO_KEY, Admitted.UNKEYED]


def test_a_method_of_the_same_name_delegating_to_its_port_is_admitted_and_a_function_is_not(
    tmp_path: Path,
) -> None:
    """A wrapper implementing `send` by calling `send` is the port, and its callers are the calls
    that matter; a module-level function called `send` is not an implementation of anything.

    Delete this and a counting or retrying wrapper would be a finding, or every function named
    `send` would be admitted."""
    source = """
    from brain.ports import Messenger

    class Counting:
        def __init__(self, inner: Messenger) -> None:
            self.inner = inner

        def send(self, body: str, *, to: str) -> None:
            self.inner.send(body, to=to)

    def send(adapter: Messenger) -> None:
        adapter.send("hello", to="room")
    """

    assert _admitted(tmp_path, source) == [Admitted.DELEGATES, Admitted.UNKEYED]


def test_a_receiver_typed_as_a_port_that_does_not_issue_is_not_a_door_that_issues(
    tmp_path: Path,
) -> None:
    """`Webhook.send` carries its own key and `Messenger.send` does not, and the two share a
    name. A receiver annotated with the first is not listed; one annotated with the second, one
    annotated with a concrete class, and one with no annotation are all treated as issuing.

    Delete this and either the outbox sender would be a finding it should not be, or a concrete
    channel adapter's send would be resolved away as not issuing."""
    source = """
    from brain.ports import Messenger, Webhook

    def outbox(sender: Webhook) -> None:
        sender.send(object())

    def channel(adapter: Messenger) -> None:
        adapter.send("hello", to="room")

    def concrete(adapter: "SlackAdapter") -> None:
        adapter.send("hello", to="room")

    def unannotated(adapter) -> None:
        adapter.send("hello", to="room")
    """
    found = effect_calls(SMALL, _tree(tmp_path, caller=source))

    assert [one.function for one in found] == ["channel", "concrete", "unannotated"]
    assert all(one.admitted is Admitted.UNKEYED for one in found)


def test_a_method_no_door_that_issues_declares_is_not_a_call_to_one(tmp_path: Path) -> None:
    """`healthy` reads and `publish` is declared nowhere. Delete this and every attribute call in
    the tree would be listed, and the invariant would be unreadable."""
    source = """
    from brain.ports import Messenger

    def check(adapter: Messenger, other) -> None:
        adapter.healthy()
        other.publish("x")
    """

    assert _admitted(tmp_path, source) == []


# ------------------------------------------------------------------ callables over an action
UNITS = frozenset({"brain.leash:Action"})

LEASH = """
from collections.abc import Callable


class Action:
    pass


def run_shadow(action: Action, *, simulate: Callable[[Action], object]) -> object:
    return simulate(action)


def run_real(action: Action, *, execute: Callable[[Action], object]) -> object:
    return execute(action)


def governs(action: Action, *, execute: Callable[[Action], object]) -> object:
    return run_real(action, execute=execute)
"""

CALLED: dict[str, Repeat] = {
    "brain.leash:run_shadow.simulate": Repeat.NO_EFFECT_AT_THE_FAR_END,
    "brain.leash:run_real.execute": Repeat.ISSUES,
}


def test_a_called_parameter_typed_as_a_callable_over_an_action_is_a_door(tmp_path: Path) -> None:
    """Declared in the unit's own module, and imported under another name elsewhere; a parameter
    passed along rather than called is not a door, and a callable over something else is not.

    Delete this and the scan could miss the leash's `execute`, which is the one door the task lane
    exists to govern, or list every function that forwards it."""
    root = _tree(
        tmp_path,
        leash=LEASH,
        other="""
        from collections.abc import Callable
        from brain.leash import Action as Step

        def run(step: Step, *, go: Callable[[Step], object], clock: Callable[[], object]) -> None:
            go(step)
            clock()

        def unrelated(value: int, *, go: Callable[[int], object]) -> None:
            go(value)
        """,
    )

    assert set(effect_callables(root, UNITS)) == {
        "brain.leash:run_shadow.simulate",
        "brain.leash:run_real.execute",
        "brain.other:run.go",
    }


def test_a_callable_over_an_action_nobody_classified_is_a_finding(tmp_path: Path) -> None:
    """Delete this and a new way of running an action could be added with no classification, and
    no call to it would ever be asked for a key."""
    root = _tree(tmp_path, leash=LEASH)

    assert classification_gaps(SMALL, root, CALLED, UNITS) == ()
    gaps = classification_gaps(SMALL, root, {"brain.leash:run_real.execute": Repeat.ISSUES}, UNITS)

    assert len(gaps) == 1
    assert gaps[0].startswith("brain.leash:run_shadow.simulate: a callable over a side effect")


def test_a_call_to_an_issuing_callable_is_held_to_the_door_and_one_that_does_not_issue_is_not(
    tmp_path: Path,
) -> None:
    """`run_real` calls `execute` outside the door and is listed; `run_shadow` calls `simulate`,
    which does nothing, and is not; a function that hands `execute` to the door is admitted.

    Delete this and the leash's own call would be invisible to the invariant, or a shadow run would
    be asked for a key it has no effect to use it for."""
    root = _tree(
        tmp_path,
        leash=LEASH,
        keyed="""
        from collections.abc import Callable
        from brain.leash import Action
        from brain.ops.idempotency import issue_once

        def run_keyed(action: Action, *, execute: Callable[[Action], object], ledger, op) -> None:
            issue_once(ledger, op, lambda _: execute(action))
        """,
    )
    called = {**CALLED, "brain.keyed:run_keyed.execute": Repeat.ISSUES}

    found = effect_calls(SMALL, root, called, UNITS)

    assert [(one.module, one.function, one.admitted) for one in found] == [
        ("brain.keyed", "run_keyed", Admitted.THROUGH_THE_DOOR),
        ("brain.leash", "run_real", Admitted.UNKEYED),
    ]
    assert [one.function for one in unkeyed_effects(SMALL, root, called, UNITS)] == ["run_real"]
