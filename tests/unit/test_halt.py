"""The stop button, held to the five ways a stop button lies.

Nothing in this system could be stopped before `brain.ops.halt`. There is a rate limiter, an
admission controller, a lease and a budget, and every one of them is a policy about normal
operation rather than a switch for the moment operation stops being normal. Every test here
is one of the five failures that make a stop button worse than none, because a button that
reports stopped and is not stopped is what somebody trusts during an incident.

The fifth failure is the one the tests below the wiring heading exist for, and it is the one
this module had: a halt that was declared, validated, ordered, rendered and asked nothing by
anybody. Those tests reach into `brain.ops.admission.decide` on purpose. A test of the value
class alone cannot tell a stop button from a dataclass.

Task ids: none
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.console.screens import screen
from brain.core.lane import Lane
from brain.gate.context import TrafficClass
from brain.ops.admission import (
    OPERATOR_ACTION,
    AdmissionRequest,
    CapacityState,
    RefusalKind,
    Resource,
    Verdict,
    decide,
    seed_budgets,
)
from brain.ops.halt import (
    ENFORCED_AXES,
    HALT_CAPABILITY,
    MINIMUM_REASON,
    NOTHING_HALTED,
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
BUDGETS = seed_budgets()


def everything() -> Halt:
    return stop_everything(declared_by="u_rupash", at=WHEN, reason=BECAUSE)


def _model_request() -> AdmissionRequest:
    """One ordinary interactive question, asking for the resource that saturates first."""
    return AdmissionRequest(
        trace_id="tr_1",
        lane=Lane.ANSWER,
        traffic_class=TrafficClass.HUMAN_INTERACTIVE,
        resource=Resource.MODEL_CALLS,
    )


def _source_request(connector: str) -> AdmissionRequest:
    """One call to a named connector, which is the only halt axis admission can see."""
    return AdmissionRequest(
        trace_id="tr_2",
        lane=Lane.ANSWER,
        traffic_class=TrafficClass.HUMAN_INTERACTIVE,
        resource=Resource.SOURCE_CALLS,
        key=connector,
    )


def _parse_request() -> AdmissionRequest:
    """One document parse. Nobody is waiting for it, so admission queues it rather than
    shedding it, which is what makes it the request that discriminates a halt from a
    shortage."""
    return AdmissionRequest(
        trace_id="tr_3",
        lane=Lane.TASK,
        traffic_class=TrafficClass.SYSTEM,
        resource=Resource.DOCUMENT_JOBS,
    )


# --- the five lies -------------------------------------------------------------------------


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


def test_the_refusal_sentence_is_empty_exactly_when_the_work_is_admitted() -> None:
    """**The bug this file found.** `refusal` took the widest covering halt and spoke for it,
    whether or not that halt refused anything. A halt carrying `SIGNAL_RUNNING` alone stops
    what is running and admits more, so `admits` said yes while `refusal` said "your work has
    been paused", and the obvious way to use a function called `refusal`, which is to refuse
    when it returns something, refused work that nothing had stopped.

    The last three lines are the sibling that stops the fix going too far: the signalling halt
    is still in force and `blocking` still reports it, because a caller that has to tell a
    running job to stop needs to find it. Filtering it out of `blocking` rather than out of
    `refusal` would pass the first half of this test and lose the effect entirely.

    Delete this and the two answers drift apart again, in a direction where a system that is
    not halted tells people it is."""
    signalling = Halt(
        scope=HaltScope.CONNECTOR,
        target="xero",
        declared_by="u_rupash",
        at=WHEN,
        reason=BECAUSE,
        effects=frozenset({Effect.SIGNAL_RUNNING}),
    )
    refusing = Halt(
        scope=HaltScope.CONNECTOR,
        target="xero",
        declared_by="u_rupash",
        at=WHEN,
        reason=BECAUSE,
        effects=frozenset({Effect.REFUSE_NEW}),
    )

    for state, axes in (
        (in_force(()), {}),
        (in_force([signalling]), {"connector": "xero"}),
        (in_force([refusing]), {"connector": "xero"}),
        (in_force([refusing]), {"connector": "freshdesk"}),
        (in_force([everything()]), {}),
        (HaltState.unknown(), {}),
    ):
        assert bool(state.refusal(**axes)) == (not state.admits(**axes)), (state, axes)

    only_signalling = in_force([signalling])
    assert only_signalling.admits(connector="xero") is True
    assert only_signalling.refusal(connector="xero") == ""
    assert only_signalling.blocking(connector="xero") == (signalling,)


def test_a_halt_that_stops_running_work_and_admits_more_of_it_is_reported() -> None:
    """The mirror of the half-halt above, and the worse of the two. A halt that signals what
    is running and refuses nothing new kills a job and lets the next request start the same
    work, so an operator watching sees churn rather than a stop and the connector somebody is
    protecting is hit at the same rate by shorter jobs.

    Reported rather than refused at construction, for the same reason as its mirror: the type
    allows either effect on its own, and what must not happen is that either is silent.

    Delete this and `halt_gaps` guards one of the two ways to build a halt that does nothing
    useful, which is the more forgivable one."""
    signalling = Halt(
        scope=HaltScope.CONNECTOR,
        target="xero",
        declared_by="u_rupash",
        at=WHEN,
        reason=BECAUSE,
        effects=frozenset({Effect.SIGNAL_RUNNING}),
    )

    found = halt_gaps([signalling])

    assert len(found) == 1, found
    assert "churn" in found[0]
    assert not halt_gaps([everything()])


def test_a_halt_on_an_axis_nothing_consults_is_reported_as_refusing_nothing() -> None:
    """**A halt in force that stops nothing is the fifth lie in its purest form.** Admission
    is handed a connector and nothing else, so a halt on a person, an agent or a department
    is stored, listed, and obeyed by no code path at all. An administrator halting a
    compromised account is not in a position to go and read which call sites exist, so the
    arrangement says so itself.

    The last three assertions are what stop this being decoration: the claim `ENFORCED_AXES`
    makes is checked against what `decide` actually does, in both directions. A person halt
    admits, a connector halt does not.

    Delete this and `ENFORCED_AXES` becomes a comment, and a halt declared during an account
    compromise reads as in force on the screen while the account keeps working."""
    person = Halt(
        scope=HaltScope.PERSON,
        target="u_someone",
        declared_by="u_rupash",
        at=WHEN,
        reason=BECAUSE,
    )

    found = halt_gaps([person])

    assert len(found) == 1, found
    assert "nothing consults" in found[0]

    assert HaltScope.PERSON not in ENFORCED_AXES
    assert HaltScope.CONNECTOR in ENFORCED_AXES

    unreached = decide(
        _source_request("xero"), BUDGETS, CapacityState(), now=WHEN, halts=in_force([person])
    )
    assert unreached.admitted is True


def test_the_capability_that_stops_the_system_is_the_one_the_stop_screen_requires() -> None:
    """A capability constant asserted against itself is green for every value it could hold,
    so this asserts it against two things outside the module: the literal grant string, and
    the console screen that offers the button.

    The divergence is what matters. Repointed at any other admin grant, the module would want
    one capability and the screen that presses it would require another, so whoever was given
    the stop button could open the page and not be the person the halt path recognises. That
    is discovered during an incident or not at all.

    Delete this and `HALT_CAPABILITY` is free to drift to any string matching the grammar."""
    assert HALT_CAPABILITY.value == "admin:halt"
    assert screen("halt").read.requires == HALT_CAPABILITY


def test_a_reason_shorter_than_the_words_that_are_not_reasons_is_refused() -> None:
    """The floor is pinned against the words people actually type when they are in a hurry,
    rather than against itself. `len(reason) < MINIMUM_REASON` compared with an imported
    `MINIMUM_REASON` is true for every value the constant could hold.

    Both directions. Dropped to four, "test" becomes a reason to stop the company. Raised to
    something safe-looking, a real sentence somebody wrote at three in the morning is refused
    and the halt does not happen at all, which is the worse of the two failures.

    Delete this and the floor is a number nothing checks in either direction."""
    for not_a_reason in ("x", "ok", "test", "resumed", "see slack"):
        with pytest.raises(HaltError, match="is not a reason"):
            stop_everything(declared_by="u_rupash", at=WHEN, reason=not_a_reason)

    real = "hubspot is leaking rows"
    assert stop_everything(declared_by="u_rupash", at=WHEN, reason=real).reason == real
    assert len("resumed") < MINIMUM_REASON


# --- the fifth lie: whether anything actually asks -------------------------------------------


def test_the_admission_controller_refuses_every_request_while_the_system_is_halted() -> None:
    """**The wiring, and the whole point of the module.** Everything above this line is true
    of a value class that no code path consults, which is what this was: halts could be
    declared, stored, reloaded, ordered and rendered, and every request was admitted anyway.

    `brain.ops.admission.decide` is the call site because it is the one function every piece
    of work passes through before any of it starts, which is exactly what `Effect.REFUSE_NEW`
    means. The unknown state is asserted here too, because failing closed matters at the
    point somebody is admitted, not in the type.

    The admitted case is the sibling: a wiring that refused everything would pass the other
    two assertions and stop the company.

    Delete this and the halt goes back to being a dataclass with opinions."""
    quiet = CapacityState()

    admitted = decide(_model_request(), BUDGETS, quiet, now=WHEN)
    assert admitted.verdict is Verdict.ADMITTED
    assert admitted.halted is False

    stopped = decide(_model_request(), BUDGETS, quiet, now=WHEN, halts=in_force([everything()]))
    assert stopped.verdict is Verdict.SHED
    assert stopped.admitted is False
    assert stopped.halted is True

    unreadable = decide(_model_request(), BUDGETS, quiet, now=WHEN, halts=HaltState.unknown())
    assert unreadable.admitted is False
    assert unreadable.halted is True

    assert decide(_model_request(), BUDGETS, quiet, now=WHEN, halts=NOTHING_HALTED).admitted


def test_a_halt_on_one_connector_refuses_that_connector_and_admits_the_others() -> None:
    """The axis is passed, not assumed. A halt on one connector must reach the requests that
    name it and no others, and the only way to tell a wiring that passes the connector from
    one that asks "is anything halted" is to halt one connector and watch a second one work.

    Delete this and `decide` can drop the axis, which turns every narrow halt into a full
    stop, which is an outage caused by the tool built to prevent one and it looks like the
    tool working."""
    stopped = Halt(
        scope=HaltScope.CONNECTOR,
        target="xero",
        declared_by="u_rupash",
        at=WHEN,
        reason=BECAUSE,
    )
    state = in_force([stopped])

    refused = decide(_source_request("xero"), BUDGETS, CapacityState(), now=WHEN, halts=state)
    served = decide(_source_request("freshdesk"), BUDGETS, CapacityState(), now=WHEN, halts=state)

    assert refused.halted is True
    assert refused.verdict is Verdict.SHED
    assert served.halted is False
    assert served.verdict is Verdict.ADMITTED


def test_a_halted_request_is_never_given_a_queue_position_or_a_time_to_come_back() -> None:
    """A queue position and an expected wait come out of budget arithmetic: how many units
    must depart before there is room. A halt has none. It ends when a person resumes it, so
    any time offered here would be invented here and believed by a client that would come
    straight back into the same refusal having been told it would not be.

    The parse request is the discriminating one. Nobody is waiting for it, so admission over
    the ceiling hands it a position rather than shedding it, and the first half of this test
    proves that still happens. The second half is the same request under a halt.

    Delete this and the halt branch can fall through to the queue, and a stopped system hands
    out wait estimates for a queue that is not moving."""
    full = CapacityState(used={(Resource.DOCUMENT_JOBS, ""): 4})

    queued = decide(_parse_request(), BUDGETS, full, now=WHEN)
    assert queued.verdict is Verdict.QUEUED
    assert queued.queue is not None
    assert queued.retry_after_seconds is not None

    halted = decide(_parse_request(), BUDGETS, full, now=WHEN, halts=in_force([everything()]))
    assert halted.verdict is Verdict.SHED
    assert halted.queue is None
    assert halted.retry_after_seconds is None


def test_a_halt_refuses_before_a_budget_row_is_looked_up_at_all() -> None:
    """Order, and it is the rule rather than an implementation detail. A halted system refuses
    because somebody stopped it, and it must say that whether or not the resource has a budget
    row, whether or not the row is full, and without the arithmetic running first.

    Both refusals are `SHED` with no budget, so the verdict cannot separate them: the reason
    and the flag are what an operator has. Given the unbudgeted resource and no halt, the
    sentence is still the one about the missing row.

    Delete this and the halt check drifts below the budget branch, where a halted system
    refuses an unbudgeted resource with a sentence about a configuration gap, and somebody
    spends an incident adding a row that changes nothing."""
    stopped = decide(
        _model_request(), (), CapacityState(), now=WHEN, halts=in_force([everything()])
    )
    assert stopped.halted is True
    assert "budget row" not in stopped.reason
    assert "paused" in stopped.reason.lower()

    unbudgeted = decide(_model_request(), (), CapacityState(), now=WHEN)
    assert unbudgeted.halted is False
    assert unbudgeted.verdict is Verdict.SHED
    assert "budget row" in unbudgeted.reason


def test_a_halted_refusal_tells_an_operator_something_other_than_add_capacity() -> None:
    """Two refusals that read alike to the person asking and mean opposite things to whoever
    is on call. Full says buy more or raise the row. Halted says a colleague pressed the stop
    button and the machine is fine, so every minute spent on capacity is wasted.

    The kinds are asserted as the literal strings that reach a log line rather than against
    the enum members they came from, and the actions are asserted against each other, because
    a mapping compared with itself is correct for every value it could hold.

    Delete this and a halt is logged as a capacity refusal, and the first thing that happens
    during a deliberate stop is somebody adding a server."""
    halted = decide(
        _model_request(), BUDGETS, CapacityState(), now=WHEN, halts=in_force([everything()])
    ).log_record()
    full = decide(
        _model_request(), BUDGETS, CapacityState(used={(Resource.MODEL_CALLS, ""): 40}), now=WHEN
    ).log_record()

    assert halted["refusal_kind"] == "halted"
    assert full["refusal_kind"] == "capacity"
    assert halted["operator_action"] != full["operator_action"]
    assert "add capacity" not in halted["operator_action"]
    assert set(OPERATOR_ACTION) == set(RefusalKind)


def test_nothing_the_administrator_wrote_reaches_the_person_who_was_refused() -> None:
    """**The leak this wiring could produce.** A halt's reason is written by an administrator
    for an administrator and routinely names a customer, a supplier or a defect. It travels
    into `decide` inside the halt and must come out of nothing: not the decision's sentence,
    not the operator record, not the exception a caller raises.

    Each forbidden word is distinctive and appears nowhere else in the call, which is the trap
    this repository has fallen into twice: asserting a substring absent while something nearby
    supplies it.

    The sibling is the last two lines. Going silent would be the other failure: a halt is not
    a permission decision, so the person is told the system is paused rather than being sent
    to report a bug that does not exist, and they are not told it is busy, which is false and
    brings them straight back.

    Delete this and the halt's reason reaches whoever asked a question the first time somebody
    finds the refusal unhelpful."""
    stopped = Halt(
        scope=HaltScope.CONNECTOR,
        target="xero",
        declared_by="u_rupash",
        at=WHEN,
        reason="acme plc threatened to sue over the leaked margin column",
    )

    decision = decide(
        _source_request("xero"), BUDGETS, CapacityState(), now=WHEN, halts=in_force([stopped])
    )
    said = [decision.reason, decision.as_error().public_message, *decision.log_record().values()]

    for secret in ("acme", "sue", "margin", "u_rupash"):
        for one in said:
            assert secret not in one.lower(), (secret, one)

    assert "xero" not in decision.reason.lower()
    assert "xero" not in decision.as_error().public_message.lower()

    assert "paused" in decision.as_error().public_message.lower()
    assert "busy" not in decision.as_error().public_message.lower()
