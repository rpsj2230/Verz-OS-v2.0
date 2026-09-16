"""Every side effect this repository can issue goes through the one door, under a key.

M17.3.1 asks for an idempotency key on every side-effecting operation, and "every" is the word a
list cannot keep true: the operation that matters is the one added after the list was written.
So this reads the tree. `brain.ops.effects` finds every protocol method, which is where this
repository puts a door to the outside, and every call to one classified as issuing a side effect,
and this file asserts two things about the tree as it stands.

**Nothing is unclassified, and nothing is unkeyed but the one door named.** A protocol method, or
a called parameter typed as a callable over an agent's action, with no classification fails, so a
new door cannot arrive without somebody saying whether calling it twice does a thing twice; a call
to an issuing door outside `issue_once`, with no `assert_no_side_effect` before it, fails with its
file and line. **One is named and not yet through the door**: the leash's `run_real`, which runs an
agent's action, and `NOT_YET_THROUGH_THE_DOOR` says why. That entry is why M17.3.1 is not claimed.

**And the scan is not passing because it found nothing.** An invariant that holds over an empty
set holds for every tree, including one where the scan's own parsing broke. So the doors known to
issue are named, the calls through them are counted, and each is required to be admitted by the
door itself or by the guard, never by default.

What a red run here means for somebody else's change: a new protocol needs a row in
`brain.ops.effects.PORTS`, and a new call to a channel's `send` or a tool's `call` needs to be
made inside `issue_once`. Neither is a reason to add to an exemption; there is no exemption list.

Task ids: M17.3.1
"""

from __future__ import annotations

from brain.ops.effects import (
    CALLABLES,
    PORTS,
    Admitted,
    Repeat,
    classification_gaps,
    effect_callables,
    effect_calls,
    protocol_methods,
    unkeyed_effects,
)

#: The doors that issue, spelled out rather than read off `PORTS`, so this file states which
#: sends and calls are side effects instead of agreeing with whatever the table says today.
ISSUING: frozenset[str] = frozenset(
    {
        "brain.channels.adapter:ChannelAdapter.send",
        "brain.ops.automation_piece:ToolCaller.call",
        "brain.ops.digest_delivery:DigestSender.send",
    }
)

#: The modules whose deliveries are made through the door. A module leaving this set has either
#: stopped sending or started sending some other way, and both are worth a failing test.
DELIVERS_THROUGH_THE_DOOR: frozenset[str] = frozenset(
    {
        "brain.channels.correction",
        "brain.channels.email",
        "brain.channels.lark",
        "brain.channels.slack",
        "brain.channels.teams",
        "brain.channels.telegram",
        "brain.channels.whatsapp",
        "brain.ops.digest_delivery",
    }
)


def test_every_protocol_method_in_the_tree_says_what_calling_it_twice_does() -> None:
    """Delete this and a new protocol for a payment provider could be added with its `charge`
    classified nowhere, and every call to it would be invisible to the check below."""
    assert classification_gaps() == ()


#: The calls to a door that issues which are not yet through the door, by `module:function`, and
#: why each is not. Named rather than counted, for the reason `KNOWN_ORPHANS` in
#: `test_no_safety_mechanism_lacks_a_caller.py` is: a new unkeyed call is a failure naming it, and
#: a call keyed later fails here until its line is removed.
NOT_YET_THROUGH_THE_DOOR: dict[str, str] = {
    "brain.gate.leash:run_real": (
        "the leash runs an approved or autonomous action by calling the `execute` its caller "
        "hands in, and returns that call's typed result. Keying it needs two things this change "
        "does not decide: what an agent is handed when its action already ran under the same key, "
        "which the typed result has no place to say, and a ledger for `govern` and `resume` to "
        "carry, which `brain.builder.rehearse` would then need for a replay that has no effect. "
        "Nothing outside tests constructs an `execute` today: `govern` is called only by the "
        "rehearsal and `resume` only by `brain.gate.suspension_store.resume_stored`, which has "
        "no caller"
    ),
}


def test_no_call_to_a_door_that_issues_is_made_outside_the_door_but_the_ones_named() -> None:
    """**The leaf's invariant.** Delete this and a send added to a channel next month posts twice
    on a retry, and every other test of that channel passes because none of them retries."""
    unkeyed = {f"{one.module}:{one.function}" for one in unkeyed_effects()}

    assert unkeyed == set(NOT_YET_THROUGH_THE_DOOR), [one.sentence() for one in unkeyed_effects()]


def test_the_doors_that_issue_are_the_ones_this_file_names() -> None:
    """Asserted against a set written here, so a door reclassified as not issuing is a decision
    made in two places rather than a line edited in one.

    Delete this and `ChannelAdapter.send` could be reclassified as a read, which would empty the
    check above and leave it green."""
    assert {name for name, repeat in PORTS.items() if repeat is Repeat.ISSUES} == ISSUING
    assert set(protocol_methods()) >= ISSUING
    assert {name for name, repeat in CALLABLES.items() if repeat is Repeat.ISSUES} == {
        "brain.gate.leash:run_real.execute"
    }
    assert set(effect_callables()) >= {"brain.gate.leash:run_real.execute"}


def test_the_scan_finds_the_deliveries_and_admits_each_by_the_door_or_the_guard() -> None:
    """The non-vacuous half. Every delivering module has at least one call through the door, the
    automation path's tool call is admitted by the guard, and nothing is admitted by being
    missed.

    Delete this and a scan that parsed nothing, or resolved every receiver away, would pass the
    check above over an empty set."""
    calls = effect_calls()
    through = {one.module for one in calls if one.admitted is Admitted.THROUGH_THE_DOOR}
    guarded = {
        (one.module, one.function) for one in calls if one.admitted is Admitted.NOTHING_TO_KEY
    }

    assert through == DELIVERS_THROUGH_THE_DOOR
    assert guarded == {("brain.ops.automation_piece", "run_step")}
    assert len([one for one in calls if one.admitted is Admitted.THROUGH_THE_DOOR]) >= len(
        DELIVERS_THROUGH_THE_DOOR
    )
