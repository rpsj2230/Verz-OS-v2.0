"""The stop button, held to the four ways a stop button lies.

Nothing in this system could be stopped before `brain.ops.halt`. There is a rate limiter, an
admission controller, a lease and a budget, and every one of them is a policy about normal
operation rather than a switch for the moment operation stops being normal. Every test here
is one of the four failures that make a stop button worse than none, because a button that
reports stopped and is not stopped is what somebody trusts during an incident.

Task ids: none
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.ops.halt import (
    Effect,
    Halt,
    HaltError,
    HaltScope,
    HaltState,
    Resume,
    halt_gaps,
    in_force,
    stop_everything,
)

WHEN = datetime(2026, 9, 7, 11, 0, tzinfo=UTC)
#: A reason long enough to pass the floor, naming something a reader could act on.
BECAUSE = "hubspot connector returning other tenants rows"


def everything() -> Halt:
    return stop_everything(declared_by="u_rupash", at=WHEN, reason=BECAUSE)


# --- the four lies -------------------------------------------------------------------------


def test_a_system_that_cannot_tell_whether_it_is_halted_refuses_work() -> None:
    """**The inversion, and it is the opposite of every other cache here.** Everything else
    treats an unreachable store as permission to carry on, because failing closed would turn a
    Valkey blip into an outage. Not this one: the moment the halt store cannot be read is
    disproportionately likely to be the moment something is wrong, and carrying on then means
    ignoring a halt during the incident that caused it.

    The pair matters. An empty known state admits, an unknown state refuses, and the two are
    otherwise identical: both carry no halts. A test asserting only the refusal would pass
    against a `HaltState` that refused everything.

    Delete this and `known` becomes a field nothing reads, and an unreachable store silently
    means no halts."""
    assert in_force(()).admits() is True
    assert HaltState.unknown().admits() is False

    assert HaltState.unknown().refusal()
    assert not in_force(()).refusal()


def test_no_argument_can_make_an_unknown_state_admit_work() -> None:
    """The unknown check is unconditional and first. A scope, a target or a combination of
    them must not be able to reach a code path that returns True from a state that was never
    read, because the caller supplying those arguments is the one in the incident.

    Delete this and somebody reorders `admits` so the blocking lookup runs first, which
    returns an empty tuple for a state with no halts, and unknown starts admitting."""
    unknown = HaltState.unknown()

    for kwargs in (
        {},
        {"department": "maintenance"},
        {"person": "u_someone"},
        {"agent": "a_reporter", "connector": "hubspot"},
        {"department": "", "person": "", "agent": "", "connector": ""},
    ):
        assert unknown.admits(**kwargs) is False, kwargs


def test_the_stop_button_both_refuses_new_work_and_signals_what_is_running() -> None:
    """**The cheap implementation refuses admission and calls it stopped**, which leaves every
    job already in flight writing to the connector somebody is trying to protect. The screen
    says stopped and the writes continue.

    `stop_everything` exists precisely so this cannot be got wrong at a call site: constructing
    a `Halt` by hand with `effects={REFUSE_NEW}` is a plausible thing to type in a hurry.

    Delete this and the named constructor can quietly lose an effect, and the loss is
    invisible until an incident where it is the only thing that mattered."""
    one = everything()

    assert one.refuses_new() is True
    assert one.signals_running() is True
    assert one.effects == frozenset({Effect.REFUSE_NEW, Effect.SIGNAL_RUNNING})


def test_a_halt_that_does_not_signal_running_work_is_reported() -> None:
    """The diagnostic side of the same property, for halts built by hand rather than by the
    named constructor. Reported rather than refused at construction, because a halt that only
    refuses new work is a legitimate thing to want: closing the door on a connector while
    letting the current job finish cleanly is sometimes right. What it must not be is silent.

    Delete this and the distinction between the two effects stops being visible anywhere, and
    a half-halt reads on the screen exactly like a whole one."""
    half = Halt(
        scope=HaltScope.CONNECTOR,
        target="hubspot",
        declared_by="u_rupash",
        at=WHEN,
        reason=BECAUSE,
        effects=frozenset({Effect.REFUSE_NEW}),
    )

    found = halt_gaps([half])

    assert any("keep writing" in one for one in found), found
    assert not halt_gaps([everything()])


def test_a_halt_cannot_carry_an_expiry_or_a_disabled_flag() -> None:
    """**The absence that is load-bearing.** An automatic expiry looks like hygiene and is the
    worst property this type could have: the halt ends at a time chosen by whoever wrote the
    default rather than by anybody watching, silently, while every person who was told the
    system is stopped still believes that.

    Asserted against the field names rather than the docstring, because the field would arrive
    with a plausible default and a review comment does not outlive the reviewer. The disabled
    flag is the same failure in the other direction: a halt in the store doing nothing, which
    an administrator reading the list cannot tell from one that is working.

    Delete this and `expires_at: datetime | None = None` lands in the next sprint."""
    names = {one.name for one in fields(Halt)}

    for forbidden in ("expires_at", "expires", "ttl", "until", "duration", "clears_at"):
        assert forbidden not in names, forbidden
    for forbidden in ("enabled", "active", "suppressed", "muted"):
        assert forbidden not in names, forbidden

    assert "reason" in names
    assert not halt_gaps()


# --- what a halt covers, in both directions ------------------------------------------------


def test_a_narrow_halt_stops_what_it_names_and_nothing_else() -> None:
    """The positive case beside the refusal, without which a `covers` that returned True for
    everything would pass every other test in this file.

    Delete this and a halt on one connector can quietly become a halt on the company, which is
    an outage caused by the tool built to prevent one."""
    one = Halt(
        scope=HaltScope.CONNECTOR,
        target="hubspot",
        declared_by="u_rupash",
        at=WHEN,
        reason=BECAUSE,
    )

    assert one.covers(connector="hubspot") is True
    assert one.covers(connector="freshdesk") is False
    assert one.covers(department="hubspot") is False
    assert one.covers() is False


def test_a_halt_on_everything_covers_work_that_names_no_axis_at_all() -> None:
    """The case the narrow halts deliberately miss. Work arriving with no department, no agent
    and no connector is still work, and the button labelled stop everything has to stop it.

    Delete this and `covers` can be rewritten to match on a named axis in every branch, which
    passes the test above and makes the stop button miss exactly the requests that carry the
    least context."""
    assert everything().covers() is True
    assert in_force([everything()]).admits() is False


def test_a_targeted_halt_with_no_target_and_a_global_one_with_a_target_are_both_refused() -> None:
    """Two mistakes, opposite in shape and identical in consequence: a halt whose reach is not
    what the person pressing the button thought.

    The second is the one worth the constructor check. `Halt(scope=EVERYTHING, target="hubspot")`
    reads as a halt on Hubspot and stops the company, and nothing about the call site says so.

    Delete this and both are constructible, and a halt's reach becomes a thing you work out by
    reading the covers implementation."""
    with pytest.raises(HaltError, match="names nothing"):
        Halt(
            scope=HaltScope.DEPARTMENT,
            target="  ",
            declared_by="u_rupash",
            at=WHEN,
            reason=BECAUSE,
        )

    with pytest.raises(HaltError, match="narrower than it is"):
        Halt(
            scope=HaltScope.EVERYTHING,
            target="hubspot",
            declared_by="u_rupash",
            at=WHEN,
            reason=BECAUSE,
        )


def test_a_halt_with_no_effects_cannot_be_constructed() -> None:
    """A row in a table that refuses nothing, stops nothing, and reports itself as in force.

    Delete this and `effects=frozenset()` is the shape a halt takes when somebody is midway
    through making one configurable."""
    with pytest.raises(HaltError, match="row in a table"):
        Halt(
            scope=HaltScope.AGENT,
            target="a_reporter",
            declared_by="u_rupash",
            at=WHEN,
            reason=BECAUSE,
            effects=frozenset(),
        )


# --- what the refused person is told -------------------------------------------------------


def test_the_refusal_names_the_scope_and_never_the_reason() -> None:
    """**The leak this type could produce.** A halt's reason is written by an administrator for
    an administrator and routinely names a customer, a defect or a supplier. It must not reach
    the person whose question was refused.

    The reason here is a distinctive string with no overlap with the sentence, which is the
    trap this repository has fallen into twice: asserting a substring absent when a timestamp
    or a docstring nearby supplies it.

    Delete this and `refusal` grows "because: {reason}" the first time somebody finds the
    message unhelpful, and a customer's name reaches whoever asked a question."""
    one = Halt(
        scope=HaltScope.CONNECTOR,
        target="hubspot",
        declared_by="u_rupash",
        at=WHEN,
        reason="acme plc threatened to sue over the leaked margin column",
    )

    said = one.refusal()

    assert "acme" not in said.lower()
    assert "sue" not in said.lower()
    assert "margin" not in said.lower()
    assert "hubspot" not in said.lower()
    assert "connector" in said.lower()
    assert "paused" in said.lower()


def test_a_halt_says_it_is_a_halt_rather_than_going_quiet() -> None:
    """A halt is not a permission decision, so the rule that DENIED and ABSENT must be
    indistinguishable does not reach it: telling somebody the system is paused reveals nothing
    about what they could otherwise have read. Refusing them in silence would send them to
    report a bug that does not exist.

    Delete this and somebody applies the denial rule here by analogy, and a halted system
    becomes a system that appears to have no answers."""
    for said in (everything().refusal(), HaltState.unknown().refusal()):
        assert said
        assert "paused" in said.lower()
        assert "nothing is being lost" in said.lower()


def test_the_unknown_sentence_does_not_claim_somebody_pressed_a_button() -> None:
    """The two states get different sentences deliberately. Claiming an administrator paused
    the system when nobody did sends whoever is on call looking for a halt that does not exist,
    which is the worst possible use of the first ten minutes of an incident.

    Delete this and the unknown case borrows a halt's sentence, because it is shorter."""
    said = HaltState.unknown().refusal()

    assert "cannot confirm" in said.lower()
    assert "by an administrator" not in said.lower()


# --- resuming, which is the guarded act ----------------------------------------------------


def test_resuming_takes_a_reason_and_stopping_takes_no_approval() -> None:
    """**The asymmetry that is the whole design.** A stop button with a confirmation step is a
    stop button that can fail when it is needed; one needing a second signature does not work
    at three in the morning. Restarting a system somebody deliberately halted is the act that
    carries the risk, so that is the one that takes paperwork.

    Both halves asserted. `stop_everything` takes no approver, no quorum and no second
    principal; `Resume` refuses a reason too short to mean anything.

    Delete this and the paperwork migrates to the stop, which is the intuitive place for it and
    the wrong one."""
    taken = stop_everything.__annotations__
    for forbidden in ("approved_by", "approver", "quorum", "second", "confirm"):
        assert forbidden not in taken, forbidden

    with pytest.raises(HaltError, match="not a reason to restart"):
        Resume(halt=everything(), by="u_someone", at=WHEN, reason="ok")

    lifted = Resume(
        halt=everything(),
        by="u_someone",
        at=WHEN + timedelta(minutes=5),
        reason="connector rolled back to the previous release",
    )
    assert lifted.overrides_somebody_else() is True


def test_one_person_may_restart_what_another_stopped_and_it_is_said_out_loud() -> None:
    """Reported rather than refused. A halt whose declarer is asleep must still be liftable,
    and a rule requiring the same person turns an incident into a phone call. What it must not
    be is invisible.

    The negative case is the discriminating one: a person resuming their own halt is not an
    override, and a `render` that always said "overrode" would pass a test that only checked
    the first.

    Delete this and either the rule tightens into a lockout or the override stops being
    recorded, and both are found during the next incident."""
    mine = Resume(
        halt=everything(),
        by="u_rupash",
        at=WHEN + timedelta(minutes=1),
        reason="false alarm, the rows were from the sandbox tenant",
    )
    theirs = Resume(
        halt=everything(),
        by="u_someone",
        at=WHEN + timedelta(minutes=1),
        reason="false alarm, the rows were from the sandbox tenant",
    )

    assert mine.overrides_somebody_else() is False
    assert "they had stopped" in mine.render()

    assert theirs.overrides_somebody_else() is True
    assert "u_rupash had stopped" in theirs.render()


def test_a_resume_that_predates_its_halt_is_refused() -> None:
    """A resume stamped before the halt it lifts is reinstated by any correct replay of the
    ledger, so the system comes back halted after a restore and nobody can find the halt that
    is in force.

    Delete this and clock skew between two containers produces a halt that will not stay
    lifted, diagnosed at whatever hour it is discovered."""
    with pytest.raises(HaltError, match="predates the halt"):
        Resume(
            halt=everything(),
            by="u_someone",
            at=WHEN - timedelta(seconds=1),
            reason="lifting before it was declared, which cannot have happened",
        )


def test_the_widest_halt_is_the_one_reported_first() -> None:
    """A caller reporting one halt should report the one an administrator will recognise. Two
    halts cover a request, one on everything and one on a connector; the sentence should be
    about the company being stopped rather than about Hubspot.

    Delete this and the ordering follows insertion, and the person refused during a full stop
    is told a connector is unavailable."""
    narrow = Halt(
        scope=HaltScope.CONNECTOR,
        target="hubspot",
        declared_by="u_rupash",
        at=WHEN - timedelta(hours=1),
        reason=BECAUSE,
    )
    state = in_force([narrow, everything()])

    blocking = state.blocking(connector="hubspot")

    assert len(blocking) == 2
    assert blocking[0].scope is HaltScope.EVERYTHING
    assert "connector" not in state.refusal(connector="hubspot").lower()


def test_a_state_built_from_a_store_is_known_and_the_constructor_default_is_not_relied_on() -> None:
    """`in_force` exists so a caller has something to call that is not the constructor, whose
    default for `known` is True: wrapping an unreachable store's empty list in `HaltState(())`
    produces a state claiming to know there are no halts.

    Delete this and `in_force` looks like an unnecessary wrapper and is inlined, and the
    mistake it was named for has nowhere to be caught."""
    assert in_force([everything()]).known is True
    assert in_force(()).known is True
    assert HaltState.unknown().known is False
