"""Effort and output length, held apart from each other and to the lane.

Two claims. M6.4.3 is that neither axis is derivable from the other, which is asserted through
the real API rather than over the lane table, because the lane table maps one lane to one of
each and would prove the opposite. M6.4.4 is that the effort is a lookup on the lane and has
no per-request override, which is asserted over the signature, because a parameter that does
not exist is the only kind that cannot be passed.

Task ids: M6.4.3, M6.4.4
"""

from __future__ import annotations

import inspect
from dataclasses import fields
from typing import get_type_hints

import pytest

from brain.core.lane import Lane
from brain.gate.effort import (
    BRIEF,
    DEFAULT_LENGTH_BY_LANE,
    EFFORT_BY_LANE,
    EFFORT_LADDER,
    EFFORT_PARAMETER,
    FULL,
    NORMAL,
    OUTPUT_LENGTHS,
    OUTPUT_LENGTHS_BY_NAME,
    TRUNCATION_HEADROOM,
    Effort,
    ModelSettings,
    OutputLength,
    default_length_for,
    effort_for,
    effort_rank,
    settings_for,
)
from brain.gate.prefix import CALLER_MATERIAL_NAMES, build_prefix, lay_out

#: Everything a pin may not read. The lane is removed because a lane is a bucket many callers
#: share rather than one caller's material, and it is the one per-request value the pins are
#: allowed to see; every other name on that list would turn the lookup into a computation.
FORBIDDEN_PIN_PARAMETERS = CALLER_MATERIAL_NAMES - {"lane"}

#: The lanes a model actually runs on. `Lane.FAST` takes no model at all, so it has no call
#: settings and appears here only in the tests that assert that refusal.
MODEL_LANES = (Lane.ANSWER, Lane.TASK)


# ------------------------------------------------------------------------------- M6.4.4
def test_the_effort_pin_reads_the_lane_and_nothing_else() -> None:
    """**M6.4.4 asserted over the signature.** The pin exists so that every request on a lane
    presents the same shape to the provider, and anything that varies within a lane defeats
    it. A parameter carrying the question, the principal or the channel would make the effort
    a per-request value, which is a cache partition per value.

    Checked over the signature rather than over what the function does today, because the
    function that reads the question tomorrow will still pass a behavioural test written now:
    it will return the same answer for the fixtures that happen to be here.

    Checked over every pin rather than only over `effort_for`, so the default length cannot
    grow a question parameter either and then be read as licence for the effort to follow.

    Delete this and `effort_for(lane, question=...)` is one line away, and the provider cache
    partitions by phrasing while every answer stays correct."""
    for pin in (effort_for, default_length_for):
        signature = inspect.signature(pin)
        hints = get_type_hints(pin)

        assert list(signature.parameters) == ["lane"], (
            f"{pin.__name__} takes {list(signature.parameters)}, not the lane alone"
        )
        assert hints["lane"] is Lane
        for name in signature.parameters:
            assert name not in FORBIDDEN_PIN_PARAMETERS


def test_effort_has_no_per_request_override_and_output_length_does() -> None:
    """**The asymmetry that makes the two axes different in practice as well as in principle.**

    Effort is part of the request shape a provider caches on, so one caller raising it costs
    everybody else on that lane their cache. The output-length instruction sits after the
    cache breakpoint, so one caller shortening it costs that request and nothing else. The
    parameter that exists is the one whose cost falls on whoever sets it.

    The two names are taken from `ModelSettings` rather than written here, so renaming a field
    moves this test with it rather than leaving it asserting about a name nothing uses.

    Delete this and `settings_for(lane, effort=Effort.HIGH)` is added by whoever is debugging
    one hard question, and the answer lane's cache quietly partitions in two."""
    axes = {f.name for f in fields(ModelSettings)}
    parameters = set(inspect.signature(settings_for).parameters)

    assert axes == {"effort", "length"}, f"ModelSettings now carries {sorted(axes)}"
    assert "effort" not in parameters, "effort has acquired a per-request override"
    assert "length" in parameters, "output length is no longer overridable per request"


def test_the_lane_table_is_derived_from_the_pin_it_displays() -> None:
    """`EFFORT_BY_LANE` is what a console renders and what an operator reasons about, and
    `effort_for` is what the gate applies. Two hand-maintained copies of one decision drift,
    and the copy that drifts is the one nobody executes, so the console shows a setting the
    system is not using.

    Covers every lane rather than the two with a model, because the fast lane's entry is the
    one somebody would leave out of a hand-written table.

    Delete this and the table can be written by hand, and it can be wrong for a release."""
    assert set(EFFORT_BY_LANE) == set(Lane)
    assert set(DEFAULT_LENGTH_BY_LANE) == set(Lane)

    for lane in Lane:
        assert EFFORT_BY_LANE[lane] is effort_for(lane)
        assert DEFAULT_LENGTH_BY_LANE[lane] is default_length_for(lane)


def test_the_task_lane_is_pinned_above_the_answer_lane_which_is_above_the_fast_lane() -> None:
    """The pins are three literal values, and a test asserting `effort_for(TASK) is HIGH` while
    importing `HIGH` from the module under test is green for every value HIGH could hold.

    So the claim is asserted as a relation instead: the lane where nobody is watching and an
    agent acts on the answer gets more work than the lane where a person is reading it, and
    the lane with no model at all sits below both. `EFFORT_LADDER` is what makes that
    comparable, since a `StrEnum` carries no order.

    Delete this and the task lane can be pinned to MEDIUM, which costs nothing visible and
    makes the lane that exists for hard work indistinguishable from the one that does not."""
    fast = effort_rank(effort_for(Lane.FAST))
    answer = effort_rank(effort_for(Lane.ANSWER))
    task = effort_rank(effort_for(Lane.TASK))

    assert fast < answer < task
    assert effort_for(Lane.FAST) is Effort.NONE
    assert set(EFFORT_LADDER) == set(Effort), "an effort is missing from the ladder"
    assert len(EFFORT_LADDER) == len(set(EFFORT_LADDER))


def test_the_fast_lane_has_no_call_settings_and_the_other_lanes_do() -> None:
    """The fast lane answers with no model in the loop, and everything downstream of it (an
    empty tool catalogue, reads restricted to projected tables) was built on that. Handing back
    a plausible-looking settings object for it would let a call happen on a path with none of
    the guards a model path has, which is the argument
    `brain.models.driver.ProviderClient.policy_for` makes for refusing the same case there.

    The positive half is asserted beside the refusal, because a function that refused every
    lane would satisfy the refusal on its own.

    Delete this and the fast lane acquires call settings, and the one lane whose guarantee is
    "no model saw this" gets one."""
    with pytest.raises(ValueError, match="no model"):
        settings_for(Lane.FAST)

    with pytest.raises(ValueError, match="no model"):
        ModelSettings(effort=Effort.NONE, length=BRIEF)

    for lane in MODEL_LANES:
        settings = settings_for(lane)
        assert settings.effort is effort_for(lane)
        assert settings.length is default_length_for(lane)


def test_the_refusal_names_the_lane_the_caller_asked_for() -> None:
    """**Written because a mutation survived.** Deleting the fast-lane refusal from
    `settings_for` left the whole file green, because `ModelSettings` refuses `Effort.NONE`
    on its own and the test above was satisfied by either message.

    The rule has one implementation, on the type, and that is deliberate: a second
    `if effort is Effort.NONE` would be a second copy, and the copy that goes wrong is the one
    in production. What the entry point adds is the lane, which is the thing the caller
    actually passed and the only thing they can act on. `ModelSettings` was handed an effort
    and cannot name a lane it never saw, which is why the two messages differ and why that
    difference is asserted here rather than assumed.

    Delete this and the re-raise can go, and somebody who asked for the fast lane is told that
    an enum member they have never heard of is not allowed.

    Task ids: M6.4.4"""
    with pytest.raises(ValueError) as through_the_entry_point:
        settings_for(Lane.FAST)

    with pytest.raises(ValueError) as constructed_directly:
        ModelSettings(effort=Effort.NONE, length=BRIEF)

    named = str(through_the_entry_point.value)
    unnamed = str(constructed_directly.value)

    assert Lane.FAST.value in named, f"the refusal does not say which lane: {named}"
    assert Lane.FAST.value not in unnamed, (
        "the constructor names a lane it was never given, so the two refusals are one "
        "message in two places and the entry point adds nothing"
    )
    assert Effort.NONE.name in unnamed


# ------------------------------------------------------------------------------- M6.4.3
def test_the_length_varies_while_the_effort_stays_pinned() -> None:
    """**Half of M6.4.3: an output length is not a function of an effort.** Two requests on the
    same lane, with the same pinned effort, can ask for different lengths, so knowing the
    effort tells you nothing about the length.

    This is the case the conflated design cannot express, and the one that matters: a hard
    question asked in a chat window where a long answer is unreadable still gets the full
    effort and a short answer, rather than a cheap answer because it had to be short.

    Delete this and `settings_for` can start ignoring its length argument, which no other test
    here would notice."""
    ordinary = settings_for(Lane.ANSWER)
    shortened = settings_for(Lane.ANSWER, length=BRIEF)
    lengthened = settings_for(Lane.ANSWER, length=FULL)

    assert ordinary.effort is shortened.effort is lengthened.effort
    assert shortened.length is not lengthened.length
    assert shortened.max_output_tokens < lengthened.max_output_tokens
    assert shortened.instruction != lengthened.instruction


def test_the_effort_varies_while_the_length_stays_the_same() -> None:
    """**The other half of M6.4.3: an effort is not a function of a length.** Two requests
    asking for the same length, on different lanes, carry different efforts.

    Together with the test above this is the whole claim: neither value determines the other,
    so neither can be derived from the other and both have to be carried.

    The pair also names the failure in both directions. Deriving effort from length gives an
    expensive lane writing essays about trivia; deriving length from effort gives a cheap lane
    truncating a hard question halfway through a sentence.

    Delete this and effort could become a function of the requested length, which reads as a
    tidy simplification and makes the task lane cheap whenever somebody wants a short
    answer."""
    on_the_answer_lane = settings_for(Lane.ANSWER, length=BRIEF)
    on_the_task_lane = settings_for(Lane.TASK, length=BRIEF)

    assert on_the_answer_lane.length is on_the_task_lane.length
    assert on_the_answer_lane.effort is not on_the_task_lane.effort
    assert effort_rank(on_the_task_lane.effort) > effort_rank(on_the_answer_lane.effort)


def test_neither_axis_holds_a_reference_to_the_other() -> None:
    """The structural half of the same claim. The two tests above prove the values vary
    independently; this proves there is no field or attribute through which one could later be
    computed from the other, which is how "separate" quietly stops being true.

    `OutputLength` carrying a default effort, or `Effort` carrying a length, is a single field
    that would make one derivable and would read in review as a convenience.

    Delete this and `OutputLength(..., effort=Effort.LOW)` is added by whoever wants a short
    answer to also be a cheap one, and the two axes are one axis again with two names."""
    length_fields = {f.name: f.type for f in fields(OutputLength)}
    hints = get_type_hints(OutputLength)

    assert not any(hints[name] is Effort for name in length_fields)
    assert not any(isinstance(getattr(Effort, name, None), OutputLength) for name in dir(Effort))
    assert not any(isinstance(getattr(BRIEF, name, None), Effort) for name in dir(BRIEF))


def test_the_instruction_asks_for_a_length_the_cap_will_not_cut_short() -> None:
    """A token cap that bites cuts a sentence in half, and half a sentence about a client's
    invoice reads as a broken system rather than as a brief answer. The instruction is what
    shapes the answer; the cap is a stop on a runaway.

    Asserted through the constructor as well as over the three shipped lengths, so the relation
    holds for any length added later rather than only for the ones written today.

    The positive case is the shipped set: a guard tested only by its refusal is satisfied by a
    constructor that refuses everything, and these three have to be constructible.

    Delete this and a cap can be lowered to save money without its instruction moving, and
    answers start ending mid-word on the lane that gets the most traffic."""
    assert OUTPUT_LENGTHS, "no lengths ship, so this checks nothing"

    for length in OUTPUT_LENGTHS:
        assert length.max_output_tokens >= length.target_words * TRUNCATION_HEADROOM
        assert str(length.target_words) in length.instruction

    with pytest.raises(ValueError, match="what would end the answer"):
        OutputLength(
            name="cramped",
            target_words=200,
            max_output_tokens=200,
            instruction="Answer in about 200 words.",
        )

    with pytest.raises(ValueError, match="does not say so"):
        OutputLength(
            name="silent",
            target_words=200,
            max_output_tokens=1_000,
            instruction="Answer briefly.",
        )


def test_the_longest_answer_fits_the_headroom_the_router_left_for_it() -> None:
    """**The cap anchored outside itself.** `brain.models.routing` escalates a request to a
    larger tier once the estimated input passes `ESCALATION_HEADROOM` of the window, and its
    comment says why that is not 1.0: the output tokens and every tool-result turn land in the
    same window. So the headroom left over is the budget the longest answer has to fit in, and
    a cap above it is a request that overflows on the turn after the one that was measured.

    Anchored to the routing module's own numbers rather than to a figure repeated here, so
    raising the cap past what the router leaves fails, and narrowing a tier's window fails too.

    Delete this and FULL can be raised to a round number that looks generous, and the requests
    that reach it are the long ones that were already close to the window.

    Task ids: M6.4.3"""
    from brain.models.routing import ESCALATION_HEADROOM, TIER_CONTEXT_WINDOW, Tier

    budget = TIER_CONTEXT_WINDOW[Tier.MAIN] * (1.0 - ESCALATION_HEADROOM)

    assert budget > 0, "the router leaves no headroom, so this anchors nothing"
    assert FULL.max_output_tokens <= budget
    assert BRIEF.max_output_tokens < NORMAL.max_output_tokens < FULL.max_output_tokens
    assert BRIEF.target_words < NORMAL.target_words < FULL.target_words


def test_the_length_index_is_derived_and_the_names_are_distinct() -> None:
    """Two things that drift apart when either is maintained by hand: the names inside the
    lengths and any mapping keyed by them. A duplicate name collapses the mapping and ships two
    lengths where one silently wins.

    Delete this and two lengths can share a name, and which one a console shows depends on
    which was defined second."""
    assert len(OUTPUT_LENGTHS_BY_NAME) == len(OUTPUT_LENGTHS), "two lengths share a name"
    for name, length in OUTPUT_LENGTHS_BY_NAME.items():
        assert length.name == name


# ---------------------------------------------------------- fitting the seams either side
def test_the_effort_is_a_call_parameter_and_the_length_is_prompt_text() -> None:
    """The two axes leave this module by different roads, and that is the mechanical reason
    they can be pinned differently.

    The effort goes into `DriverRequest.extra`, which is `Mapping[str, str]` so a call is
    replayable from a trace, and never into the prompt: text telling a model to try harder is a
    request rather than a setting. The length's instruction goes into
    `PromptLayout.variable`, after the cache breakpoint, which is what makes a per-request
    override cost only the request that made it.

    Built into a real `DriverRequest` and a real `PromptLayout` rather than asserted about, so
    a change to either seam fails here instead of at the first live call.

    Delete this and `as_extra` can start returning something the driver seam will not take, or
    the length instruction can migrate into the shared prefix and take the hit rate with it."""
    from brain.models.driver import DriverMessage, DriverRequest, Role

    settings = settings_for(Lane.ANSWER, length=BRIEF)

    request = DriverRequest(
        deployment_id="d_main_primary",
        model="a-model",
        messages=(DriverMessage(role=Role.USER, content="How many hours are left on Acme?"),),
        timeout_seconds=20.0,
        max_output_tokens=settings.max_output_tokens,
        extra=settings.as_extra(),
    )

    assert request.extra[EFFORT_PARAMETER] == Effort.MEDIUM.value
    assert all(isinstance(value, str) for value in request.extra.values())
    assert request.max_output_tokens == BRIEF.max_output_tokens

    layout = lay_out(build_prefix([]), settings.instruction, "How many hours are left on Acme?")

    assert settings.instruction not in layout.shared.text
    assert settings.instruction in layout.variable
    assert layout.blocks.index(settings.instruction) >= layout.cache_breakpoint


def test_settings_carry_no_reach() -> None:
    """The one thing this module must never become is a second place where what a caller may
    see is decided. A model working harder does not see more: reach is settled by the projected
    catalogue and by the redaction walker long before any of this is consulted.

    Asserted as an absence, because the presence is what a future edit adds, and the edit that
    adds it looks reasonable: an agent that needs a wider tool list on the task lane is exactly
    the request somebody will make of this module.

    Delete this and `ModelSettings` grows a capability, a tool list or a principal, and the
    invariant has a second implementation in the module least likely to be reviewed for it."""
    carried = {f.name for f in fields(ModelSettings)}

    for forbidden in ("capability", "entitlement", "principal", "tool", "scope", "reach"):
        assert not any(forbidden in name for name in carried), (
            f"ModelSettings carries something naming a {forbidden}"
        )
