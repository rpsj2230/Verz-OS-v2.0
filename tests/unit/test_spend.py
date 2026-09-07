"""Spend enforcement, held to the two things that decide whether a budget is real.

The first is that the refusal arrives before the money is spent, which means the estimate
cannot be allowed to need a model, a client or an await. That is asserted structurally, by
parsing the module, rather than behaviourally: behaviour today says nothing about whether a
session parameter can be added tomorrow, and the day it is added it will be added with a
sensible default.

The second is that the degradation ladder is an order rather than four names. Most of the
tests below measure what each rung gives up instead of trusting the enum, because a ladder a
later editor can reorder with the suite green is not a ladder.

Task ids: M21.2.1, M21.2.2, M21.2.3, M21.2.4, M21.2.5, M21.2.6
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import pytest

from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.gate.context import TrafficClass
from brain.models.routing import TIER_LADDER, Tier
from brain.ops import spend as spend_module
from brain.ops.admission import OPERATOR_ACTION, RefusalKind
from brain.ops.budgets import (
    Allowance,
    BudgetError,
    BudgetLevel,
    BudgetPeriod,
    BudgetRow,
    agent_ceilings,
)
from brain.ops.limits import VOLUME_MIN_OBSERVATIONS, is_automated
from brain.ops.spend import (
    BUDGET_PHRASE,
    CHEAPER_TIER_MUST_SAVE_AT_LEAST,
    CORRECTION_BLEND,
    CORRECTION_CEILING,
    CORRECTION_FLOOR,
    LADDER,
    MIN_CORRECTION_SAMPLES,
    NO_AGENT,
    NO_CORRECTION,
    PERIOD_PHRASE,
    RAISED_BY,
    TIER_RATE_PER_KTOKEN,
    Actual,
    Correction,
    CostInputs,
    Dimension,
    Observation,
    Refusal,
    Rung,
    SpendError,
    assert_priced,
    budget_gaps,
    correct,
    estimate,
    ladder_disorder,
    observed,
    preflight,
    relief_of,
    spend_by,
    total_minor,
)

NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)

#: A request with something to give up at every rung: an expensive tier, several branches,
#: tools and retrieval. Used wherever the ladder's ordering is under test, because a request
#: with one branch has nothing to give up at the fan-out rung and would make the ordering
#: vacuously true.
RICH = CostInputs(
    lane=Lane.ANSWER, tier=Tier.HEAVY, tool_calls=2, retrieval_tokens=5_000, fan_out=3
)


def allowance(
    *,
    level: BudgetLevel = BudgetLevel.USER,
    period: BudgetPeriod = BudgetPeriod.DAY,
    ceiling: int,
    spent: int = 0,
    subject: str = "p_alice",
) -> Allowance:
    return Allowance(
        row=BudgetRow(
            level=level,
            subject=subject,
            period=period,
            ceiling_minor=ceiling,
            version=1,
            author="rupash",
            effective_from=NOW,
        ),
        spent_minor=spent,
    )


def run(cost_minor: int, *, agent: str | None = None, service: bool = False) -> Actual:
    return Actual(
        principal_id="p_bot" if service else "p_alice",
        principal_kind=PrincipalKind.SERVICE if service else PrincipalKind.HUMAN,
        traffic=TrafficClass.AUTOMATION if service else TrafficClass.HUMAN_INTERACTIVE,
        department="web",
        agent_id=agent,
        model="main-1",
        lane=Lane.ANSWER,
        cost_minor=cost_minor,
        at=NOW,
    )


# ----------------------------------------------------- the estimate, before anything runs
def test_the_estimator_cannot_become_async_and_cannot_be_handed_a_client() -> None:
    """**M21.2.2 read structurally.** A refusal must arrive before the tokens are spent, so
    the estimate must not be able to need a model call, a database round trip or an await.

    Asserted by parsing the module rather than by calling it, for the reason
    `test_memory_tiers` parses signatures: behaviour today says nothing about whether a
    `session` parameter can be added tomorrow, and the day somebody adds one it will arrive
    with a sensible-looking default and every behavioural test will still pass.

    Four things are checked and each closes a different door. No coroutine and no await, so
    the estimate cannot start waiting on anything. An exact import list, so it cannot reach a
    transport or a session. Annotations on `estimate` limited to this module's own value
    types. And `CostInputs` carrying only enums and integers, so a client cannot be smuggled
    in through the one argument the estimator does take.

    Delete this and the first person who wants one live price makes the estimator async, and
    the budget check then costs a round trip on every request in the system."""
    source = inspect.getsourcefile(spend_module)
    assert source is not None
    tree = ast.parse(Path(source).read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        assert not isinstance(node, ast.AsyncFunctionDef), "an async function reached this module"
        assert not isinstance(node, ast.Await), "an await reached this module"

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert imported == {
        "__future__",
        "enum",
        "math",
        "collections.abc",
        "dataclasses",
        "datetime",
        "itertools",
        "types",
        "typing",
        "brain.core.lane",
        "brain.core.principal",
        "brain.gate.context",
        "brain.models.routing",
        "brain.ops.admission",
        "brain.ops.budgets",
        "brain.ops.limits",
    }, "an import was added; a cost estimator that can reach a transport is not pre-flight"

    assert not inspect.iscoroutinefunction(estimate)
    annotations = {
        parameter.annotation for parameter in inspect.signature(estimate).parameters.values()
    }
    assert annotations == {"CostInputs", "Correction"}
    assert {field.type for field in dataclass_fields(CostInputs)} == {"Lane", "Tier", "int"}


def test_a_fast_lane_request_costs_nothing_because_no_model_runs() -> None:
    """`Lane.FAST` means no model at all, so its estimate is zero however much was retrieved.

    Asserted from the lane rather than from the rate table, which is the anchor that matters:
    the rate for `Tier.NONE` could be set to anything and this is the property that says what
    it has to be.

    The two refusals beside it keep the pairing honest in both directions. A fast-lane request
    priced at a model tier would be charged for a model it never ran, and a model-lane request
    priced at tier none would be free.

    Delete this and the fast lane starts consuming a budget, which is the exact opposite of
    the reason it exists."""
    assert estimate(CostInputs(lane=Lane.FAST, tier=Tier.NONE, retrieval_tokens=9_000)).minor == 0

    with pytest.raises(SpendError, match="the absence of the ladder"):
        CostInputs(lane=Lane.FAST, tier=Tier.MAIN)
    with pytest.raises(SpendError, match="only the fast lane"):
        CostInputs(lane=Lane.ANSWER, tier=Tier.NONE)
    with pytest.raises(SpendError, match="no tools and no branches"):
        CostInputs(lane=Lane.FAST, tier=Tier.NONE, tool_calls=1)


def test_the_estimate_rises_with_every_input_m21_2_1_names() -> None:
    """Lane, tier, tool count and retrieval size, plus fan-out. Each one is asserted to move
    the figure on its own, because an input that is read and then multiplied by zero is an
    input the estimate does not actually use, and the console would still show it.

    Delete this and the retrieval size can quietly stop contributing, which is the term that
    dominates a document-heavy question and the one nobody notices missing, because the
    estimate still looks plausible."""
    base = CostInputs(lane=Lane.ANSWER, tier=Tier.MAIN)
    figure = estimate(base).minor

    assert estimate(CostInputs(lane=Lane.TASK, tier=Tier.MAIN)).minor > figure
    assert estimate(CostInputs(lane=Lane.ANSWER, tier=Tier.HEAVY)).minor > figure
    assert estimate(CostInputs(lane=Lane.ANSWER, tier=Tier.MAIN, tool_calls=1)).minor > figure
    assert (
        estimate(CostInputs(lane=Lane.ANSWER, tier=Tier.MAIN, retrieval_tokens=100)).minor > figure
    )
    assert estimate(CostInputs(lane=Lane.ANSWER, tier=Tier.MAIN, fan_out=2)).minor > figure


def test_a_fan_out_costs_every_branch_it_opens() -> None:
    """Three branches of one question cost three times one branch. That is what makes the
    no-fan-out rung worth a place on the ladder: without it, dropping from four sources to one
    would save nothing and the rung would report a degradation that saved no money.

    Asserted on the token count as well as the price, so that a rate change cannot make it
    pass for the wrong reason.

    Delete this and fan-out becomes a field the estimate accepts and ignores, and a question
    touching twelve clients is priced as one."""
    single = CostInputs(lane=Lane.ANSWER, tier=Tier.MAIN, retrieval_tokens=5_000)
    triple = CostInputs(lane=Lane.ANSWER, tier=Tier.MAIN, retrieval_tokens=5_000, fan_out=3)

    assert estimate(triple).tokens == 3 * estimate(single).tokens
    assert estimate(triple).minor == 3 * estimate(single).minor


def test_every_tier_on_the_routing_ladder_is_priced_and_each_step_down_halves_the_cost() -> None:
    """The rates are held to `routing.TIER_LADDER` rather than to their own keys, so a tier
    added to the model pools without a price fails here instead of being estimated at whatever
    a missing key would default to.

    The second half is the property that makes the first rung of the degradation ladder worth
    taking. A step down that saves a few percent buys a worse answer for very little money,
    which is the worst trade available: the person notices the quality and nobody notices the
    saving.

    Delete this and `TIER_RATE_PER_KTOKEN` can hold any figures at all, including two tiers
    priced the same, and the cheaper-tier rung becomes a pure loss."""
    assert_priced()
    assert set(TIER_LADDER) <= set(TIER_RATE_PER_KTOKEN)

    for cheaper, dearer in pairwise(TIER_LADDER):
        assert TIER_RATE_PER_KTOKEN[cheaper] <= TIER_RATE_PER_KTOKEN[dearer] * (
            1.0 - CHEAPER_TIER_MUST_SAVE_AT_LEAST
        ), f"dropping from {dearer} to {cheaper} does not save enough to be worth the answer"

    with pytest.raises(BudgetError, match="does not rise"):
        assert_priced((Tier.MAIN, Tier.MAIN))


# ------------------------------------------------------------------ the degradation ladder
def test_each_rung_of_the_ladder_gives_up_strictly_more_than_the_one_above_it() -> None:
    """**M21.2.5 as an order rather than four names.** Cheaper tier, then no fan-out, then
    queue, then refuse, and each one measured rather than assumed.

    The measurement is the point. A test asserting the enum reads `CHEAPER_TIER, NO_FAN_OUT,
    QUEUE, REFUSE` would pass for any values those names could hold, including values that
    make `preflight` refuse before it has tried a queue. So the reliefs are computed from the
    rate table and compared pairwise, and `ladder_disorder` is asked the same question a
    second way.

    Delete this and swapping two rung values is a silent change: degradation still happens,
    every other test still passes, and requests that a queue would have carried are refused."""
    assert len(LADDER) == len(Rung)
    assert LADDER[-1] is Rung.REFUSE, "refusing is not the last thing tried"
    assert ladder_disorder(RICH) == ()

    for above, below in pairwise(LADDER):
        assert relief_of(below, RICH).key > relief_of(above, RICH).key, (
            f"{below.name} gives up no more than {above.name}, so the ladder has a flat step"
        )


def test_refusing_gives_up_more_than_queueing_because_a_queued_request_is_still_paid_for() -> None:
    """The distinction that stops the ladder ending one rung early. Both rungs clear the
    window under pressure completely, so a single-number measure of saving would make them
    equal and the order between them arbitrary.

    What separates them is the horizon: a queued request lands in a later window and is paid
    for there, so over the budget's whole life a queue moves cost rather than removing it.
    That is asserted as the equality it implies, which is that queueing eventually costs
    exactly what the rung above it costs.

    Delete this and `Relief` collapses to one integer, which reads as a simplification, and
    the ladder then refuses whenever it would have queued."""
    queue = relief_of(Rung.QUEUE, RICH)
    refuse = relief_of(Rung.REFUSE, RICH)
    no_fan_out = relief_of(Rung.NO_FAN_OUT, RICH)

    assert queue.now_minor == refuse.now_minor
    assert queue.for_good_minor < refuse.for_good_minor
    assert queue.for_good_minor == no_fan_out.for_good_minor, (
        "a queued request stopped costing what it will actually cost"
    )


# --------------------------------------------------------------------------- the decision
def test_a_request_that_fits_runs_exactly_as_it_was_asked() -> None:
    """**The positive case, without which every guard below is satisfied by a function that
    refuses everything.**

    The request comes back unchanged, at no rung, which is the ordinary answer for almost all
    traffic. `rung is None` is the assertion that matters: a degraded request that happened to
    fit would report a sacrifice nobody made.

    Delete this and a defensive edit can make the ladder run on every request, and the whole
    estate quietly answers from the small model."""
    result = preflight(
        RICH,
        allowances=(allowance(ceiling=1_000_000),),
        traffic=TrafficClass.HUMAN_INTERACTIVE,
    )

    assert result.allowed
    assert result.rung is None
    assert not result.degraded
    assert result.inputs == RICH
    assert result.refusal is None
    assert result.estimate_minor == estimate(RICH).minor


def test_a_request_that_fits_after_a_cheaper_tier_is_degraded_rather_than_refused() -> None:
    """The first rung, and the one that runs most often. The answer still happens, now, over
    the same breadth, from a smaller model.

    The returned inputs are asserted rather than just the rung, because the caller runs what
    comes back: a `Preflight` that reported `CHEAPER_TIER` and handed back the original
    request would be a degradation nobody applied and a budget nobody protected.

    Delete this and the ladder can start at the fan-out rung, which narrows what an answer
    covers when it did not have to."""
    result = preflight(
        RICH,
        allowances=(allowance(ceiling=1_500),),
        traffic=TrafficClass.HUMAN_INTERACTIVE,
    )

    assert result.allowed
    assert result.rung is Rung.CHEAPER_TIER
    assert result.inputs is not None
    assert result.inputs.tier is Tier.MAIN
    assert result.inputs.fan_out == RICH.fan_out, "the breadth was narrowed at the first rung"
    assert result.estimate_minor <= 1_500


def test_a_request_that_only_a_queue_can_carry_is_queued_rather_than_refused() -> None:
    """The rung that a reordered enum removes silently. Nothing else on the ladder fits, and
    nobody is waiting, so the work is deferred rather than abandoned.

    This is the test that fails if `QUEUE` and `REFUSE` swap values: degradation still
    happens, the cheaper-tier and fan-out tests still pass, and the only visible symptom is
    that background work which used to run is now refused.

    Delete this and the last two rungs collapse into one, and every automation that outruns
    its daily allowance loses its work instead of its place in the day."""
    result = preflight(
        RICH,
        allowances=(allowance(ceiling=400),),
        traffic=TrafficClass.AUTOMATION,
    )

    assert result.allowed
    assert result.queued
    assert result.rung is Rung.QUEUE
    assert result.inputs is not None
    assert result.inputs.fan_out == 1, "a queued request kept the fan-out it could not afford"
    assert result.refusal is None


def test_a_person_watching_a_cursor_is_refused_rather_than_queued() -> None:
    """The same request as the test above, from a channel where somebody is waiting.

    `admission.A_PERSON_WAITING_IS_NEVER_QUEUED` decided this for machine capacity and the
    argument is unchanged for money: what a queue position buys is a retry that costs nothing,
    which is worth having only when nobody is watching for the answer.

    Asserted as the pair, so that a mistake in either direction fails: queueing an interactive
    request, or refusing a background one that could have waited.

    Delete this and a person asking a question at the end of the month is handed a position in
    a queue they will never look at, and the honest refusal they could have acted on is
    gone."""
    interactive = preflight(
        RICH, allowances=(allowance(ceiling=400),), traffic=TrafficClass.HUMAN_INTERACTIVE
    )
    background = preflight(
        RICH, allowances=(allowance(ceiling=400),), traffic=TrafficClass.HUMAN_ASYNC
    )

    assert not interactive.allowed
    assert interactive.rung is Rung.REFUSE
    assert interactive.refusal is not None
    assert background.queued


def test_an_agent_run_ceiling_cannot_be_waited_past() -> None:
    """Waiting refills a day and a month and does nothing at all to the most one run may cost,
    so a queue against a per-run ceiling hands back a position that will be refused on arrival.

    `BudgetPeriod.RUN` exists to make that difference expressible, and this is the test that
    says what it is for. The refusal names the agent's ceiling, which is the honest answer:
    the work is too big for this agent however long anybody waits.

    Delete this and a background job is queued forever against a ceiling that never moves,
    and the queue depth is the only symptom."""
    per_run, _per_day = agent_ceilings(
        agent_id="a_reporter",
        per_run_minor=5,
        per_day_minor=5_000,
        author="rupash",
        effective_from=NOW,
    )
    result = preflight(RICH, allowances=(Allowance(row=per_run),), traffic=TrafficClass.AUTOMATION)

    assert not result.allowed
    assert result.refusal == Refusal(level=BudgetLevel.AGENT, period=BudgetPeriod.RUN)


def test_a_request_already_at_the_cheapest_shape_is_queued_rather_than_marked_degraded() -> None:
    """A request at the smallest tier with one branch has nothing to give up at the first two
    rungs, so the ladder must reach the queue rather than report a sacrifice nobody made.

    What this asserts is the outcome, not the skip inside the loop. The skip was mutated and
    survived, and the survival is correct: a rung with no relief costs exactly what was asked,
    and that figure was already refused at the top of `preflight`, so the rung is turned away
    by `admits` whether the skip is there or not. That is recorded in the module rather than
    covered by a test written to fit it.

    The returned request is asserted to be the original, which is the property with teeth
    here: a `Preflight` marked at a rung must never hand back the request it started with.

    Delete this and a request at the bottom of the tier ladder can be refused outright when a
    queue would have carried it, which is the same failure as reordering the rungs and is
    reached by a different route."""
    plain = CostInputs(lane=Lane.ANSWER, tier=Tier.SMALL)
    result = preflight(plain, allowances=(allowance(ceiling=5),), traffic=TrafficClass.AUTOMATION)

    assert result.rung is Rung.QUEUE
    assert result.inputs == plain

    refused = preflight(
        plain, allowances=(allowance(ceiling=5),), traffic=TrafficClass.HUMAN_INTERACTIVE
    )
    assert not refused.allowed


def test_an_alert_is_reported_once_when_a_request_first_crosses_it() -> None:
    """Newly crossed rather than currently over. A budget sitting at 80% would otherwise raise
    the 75% alert on every request for the rest of the month, people would filter it, and the
    90% one would arrive in a folder nobody reads.

    Delete this and the alerting becomes a level rather than an edge, which is the change that
    makes an alert worthless without ever making it wrong."""
    row = BudgetRow(
        level=BudgetLevel.DEPARTMENT,
        subject="web",
        period=BudgetPeriod.MONTH,
        ceiling_minor=1_000,
        version=1,
        author="rupash",
        effective_from=NOW,
        alert_fractions=(0.75, 0.9),
    )
    crossing = preflight(
        CostInputs(lane=Lane.ANSWER, tier=Tier.SMALL),
        allowances=(Allowance(row=row, spent_minor=745),),
        traffic=TrafficClass.HUMAN_INTERACTIVE,
    )
    already = preflight(
        CostInputs(lane=Lane.ANSWER, tier=Tier.SMALL),
        allowances=(Allowance(row=row, spent_minor=800),),
        traffic=TrafficClass.HUMAN_INTERACTIVE,
    )

    assert [one.fraction for one in crossing.alerts] == [0.75]
    assert already.alerts == ()


# ------------------------------------------------------------------------- the refusal
def test_a_refusal_names_the_budget_and_who_can_raise_it_and_carries_no_figure() -> None:
    """**M21.2.6.** Naming the budget is deliberate: it is the caller's own, not somebody
    else's data, and a refusal that says only "no" sends a person to a help desk that cannot
    help them.

    Carrying no figure is equally deliberate. Two refusals a week apart, each naming what was
    left, subtract into how much everybody else spent in between, and neither on its own looks
    like a disclosure. So every one of the twelve level and period pairings is checked for a
    digit, not just the one in the example.

    Delete this and the sentence acquires "you have 4 left" the week somebody decides it is
    unhelpful, and the estate's spending becomes readable one refusal at a time."""
    assert Refusal(level=BudgetLevel.DEPARTMENT, period=BudgetPeriod.MONTH).message == (
        "Your department's monthly budget is used up; your department head can raise it."
    )

    for level in BudgetLevel:
        for period in BudgetPeriod:
            message = Refusal(level=level, period=period).message
            assert not any(character.isdigit() for character in message), message
            assert Refusal(level=level, period=period).raised_by in message
            assert message.endswith("can raise it.")


def test_a_refusal_has_nowhere_to_put_a_count_or_another_principals_spend() -> None:
    """The DENIED and ABSENT rule applied to money. A refusal must not leak a count of things
    the caller cannot see, and must not name anybody else's spending.

    Enforced as a shape rather than as a rule about wording. `Refusal` has two fields and
    neither can hold a number or a name, so the message is a function of the level and the
    period alone. That is asserted twice: on the fields, and on two estates that differ in
    every other respect producing byte-identical sentences.

    Delete this and a helpful `remaining_minor` field appears, the renderer starts using it,
    and every refused person learns how much of the department's month is left."""
    assert {field.name for field in dataclass_fields(Refusal)} == {"level", "period"}

    quiet = preflight(
        RICH,
        allowances=(allowance(level=BudgetLevel.DEPARTMENT, ceiling=10, subject="web"),),
        traffic=TrafficClass.HUMAN_INTERACTIVE,
    )
    busy = preflight(
        RICH,
        allowances=(
            allowance(level=BudgetLevel.DEPARTMENT, ceiling=900, spent=899, subject="web"),
            allowance(level=BudgetLevel.COMPANY, ceiling=10**9, subject="verz"),
            allowance(subject="p_zoe", ceiling=10**9),
        ),
        traffic=TrafficClass.HUMAN_INTERACTIVE,
    )

    assert quiet.refusal is not None
    assert busy.refusal is not None
    assert quiet.refusal.message == busy.refusal.message


def test_every_budget_level_and_period_can_be_named_in_a_refusal() -> None:
    """The message is assembled from three mappings, and a missing entry raises at the moment
    somebody is being refused, which is the worst moment for a lookup to fail and the one a
    test that never produced that level would never reach.

    Checked against `set(BudgetLevel)` and `set(BudgetPeriod)` in both directions, so a level
    added without wording and wording left behind by a deleted level both fail.

    Delete this and a fifth budget level ships with a `KeyError` in the refusal path."""
    assert budget_gaps() == ()
    assert set(BUDGET_PHRASE) == set(BudgetLevel)
    assert set(RAISED_BY) == set(BudgetLevel)
    assert set(PERIOD_PHRASE) == set(BudgetPeriod)


def test_a_budget_refusal_is_a_quota_refusal_and_not_a_capacity_one() -> None:
    """Three refusals that read alike to the person asking and mean three different things to
    whoever is on call. A budget is the caller's own allowance, so it is QUOTA: the machine
    has room and buying a bigger one would not help.

    The operator action is asserted against `admission.OPERATOR_ACTION` rather than against a
    string written here, which is the anchor that matters: this module must say the same thing
    the capacity controller says about the same kind of refusal.

    The subject is asserted to carry no principal, because the audit layer owns who asked and
    a second copy of an identity in the operator log is a second retention policy.

    Delete this and a month-end budget refusal pages somebody to add capacity to a machine
    that is idle."""
    record = Refusal(level=BudgetLevel.USER, period=BudgetPeriod.MONTH).log_record()

    assert record["refusal_kind"] == RefusalKind.QUOTA
    assert record["operator_action"] == OPERATOR_ACTION[RefusalKind.QUOTA]
    assert "p_alice" not in str(record)
    assert record["subject"] == "budget:user:month"


# ------------------------------------------------------------- correction from actuals
def test_the_correction_is_bounded_in_both_directions_and_the_bounds_are_reciprocal() -> None:
    """**M21.2.4's floor and ceiling, anchored against each other rather than against
    themselves.**

    The floor is the one that matters: under-estimating is the direction that waves expensive
    work through a budget check. The ceiling stops the rarer opposite, which is one runaway
    run teaching the estimator to refuse ordinary work.

    They are reciprocal so that a mis-estimate is bounded by the same factor whichever way it
    errs. That relation is the assertion, because a test reading `CORRECTION_FLOOR == 0.5`
    from the module it imported it from is green for every value it could hold.

    The sample floor is anchored on `limits.VOLUME_MIN_OBSERVATIONS`, which is the same
    argument about the same kind of ratio and must not be undercut here.

    Delete this and the floor can be set to 0.01, and one cheap fortnight teaches the
    estimator to wave through anything at all."""
    assert abs(CORRECTION_FLOOR * CORRECTION_CEILING - 1.0) < 1e-9, (
        "the bounds are not reciprocal, so a mis-estimate is bounded further one way than the "
        "other and the estimator drifts faster in whichever direction is looser"
    )
    assert CORRECTION_FLOOR < 1.0 < CORRECTION_CEILING
    assert 0.0 < CORRECTION_BLEND < 1.0
    assert MIN_CORRECTION_SAMPLES >= VOLUME_MIN_OBSERVATIONS

    with pytest.raises(SpendError, match="outside"):
        Correction(factor=CORRECTION_FLOOR / 2, samples=100, reason="learnt too far down")
    with pytest.raises(SpendError, match="outside"):
        Correction(factor=CORRECTION_CEILING * 2, samples=100, reason="learnt too far up")


def test_a_run_of_cheap_windows_cannot_teach_the_estimator_below_its_floor() -> None:
    """**The failure M21.2.4 has to survive.** A quiet fortnight of cheap questions teaches an
    unbounded estimator that everything is cheap, and the expensive week that follows then
    passes every pre-flight check on the way to spending a month's budget.

    Fifty windows of evidence a hundred times cheaper than the estimate, applied one after
    another. The factor stops moving and stops well above what the evidence alone would say,
    and that second assertion is the one anchored on something outside the constant: the
    observed ratio is a hundredth, and the estimator refused to go there.

    Delete this and the clamp can be removed as redundant, because nothing else in the suite
    ever pushes the factor far enough to need it."""
    cheap = [Observation(estimated_minor=100, actual_minor=1)] * (MIN_CORRECTION_SAMPLES + 10)
    learnt = NO_CORRECTION
    for _round in range(50):
        learnt = correct(learnt, cheap)

    assert learnt.factor >= CORRECTION_FLOOR
    assert learnt.factor > 0.01, "the estimator learnt its way down to the raw observed ratio"
    assert correct(learnt, cheap).factor == learnt.factor, "the floor is not a fixed point"


def test_a_run_of_expensive_windows_cannot_teach_the_estimator_above_its_ceiling() -> None:
    """The other direction, which is a self-inflicted outage rather than an overspend: an
    estimator that has learnt everything is five times its estimate refuses ordinary work.

    Asserted as the mirror of the floor test, because a clamp written with one bound is a
    clamp that will be written with one bound.

    Delete this and one runaway task can push the estimator far enough that a working
    department is refused for the rest of the month."""
    dear = [Observation(estimated_minor=1, actual_minor=100)] * (MIN_CORRECTION_SAMPLES + 10)
    learnt = NO_CORRECTION
    for _round in range(50):
        learnt = correct(learnt, dear)

    assert learnt.factor <= CORRECTION_CEILING
    assert learnt.factor < 100.0
    assert correct(learnt, dear).factor == learnt.factor


def test_the_correction_weighs_a_window_by_its_money_and_not_by_its_run_count() -> None:
    """A mean of per-run ratios lets a hundred trivial cheap runs outvote one expensive one,
    and the runs that matter to a budget are the few large ones.

    The window here is twenty-nine runs that were estimated perfectly and one large run that
    cost four times its estimate. By run count the window is 1.1x and the factor would barely
    move; by money it is over three times and the factor moves properly. The assertion is
    placed between those two answers so that only the money-weighted one passes.

    Delete this and the correction is written as `mean(actual / estimated)`, which is the
    obvious spelling, and the estimator never learns about the expensive tail."""
    window = [Observation(estimated_minor=1, actual_minor=1)] * 29
    window.append(Observation(estimated_minor=100, actual_minor=400))

    moved = correct(NO_CORRECTION, window)
    assert moved.factor > 1.5, "the window was weighted by run count rather than by money"


def test_a_window_below_the_sample_floor_leaves_the_correction_where_it_was() -> None:
    """A ratio over four runs is noise, and moving on noise is how the factor drifts with
    nothing reporting that it has.

    The positive sibling is asserted beside it: one run above the floor does move the factor,
    so this is a threshold rather than a function that never learns anything.

    Delete this and the estimator starts tracking whichever handful of runs happened to
    finish before the report ran."""
    thin = [Observation(estimated_minor=100, actual_minor=400)] * (MIN_CORRECTION_SAMPLES - 1)
    enough = [Observation(estimated_minor=100, actual_minor=400)] * MIN_CORRECTION_SAMPLES

    assert correct(NO_CORRECTION, thin).factor == NO_CORRECTION.factor
    assert correct(NO_CORRECTION, enough).factor > NO_CORRECTION.factor


def test_an_observation_carries_the_estimate_that_was_actually_made() -> None:
    """The correction is a comparison between what the estimator said and what happened, and
    it is worth nothing if the first half is recomputed rather than recorded: the estimator
    would then be compared with itself and the factor would be 1.0 for every rate table it
    could hold.

    Asserted by building two observations from the same run, one against an uncorrected
    estimate and one against a corrected one, and requiring them to differ.

    Delete this and `observed` is rewritten to take a `CostInputs` and call `estimate` itself,
    which looks tidier and makes the correction a fixed point at whatever it already was."""
    actual = run(900)
    raw = observed(estimate(RICH), actual)
    corrected = observed(
        estimate(RICH, correction=Correction(factor=1.5, samples=99, reason="learnt")), actual
    )

    assert corrected.estimated_minor > raw.estimated_minor
    assert raw.actual_minor == corrected.actual_minor == 900

    with pytest.raises(SpendError, match="no ratio to an actual"):
        Observation(estimated_minor=0, actual_minor=10)


# ------------------------------------------------------------------- post-hoc accounting
def test_every_dimension_totals_to_the_same_figure() -> None:
    """**M21.2.3's five dimensions, held to the property that makes a breakdown usable.**
    Principal, department, agent, model and lane must each add up to the same number, or one
    of them is quietly dropping rows.

    The rows with no agent are the ones that go missing, because skipping them is the obvious
    way to avoid a null key. They are bucketed instead, so the agent breakdown reconciles with
    every other one and the first person to notice is not somebody balancing an invoice.

    Delete this and the agent report is silently smaller than the department report for as
    long as anybody cares to look."""
    actuals = [run(100, agent="a_reporter"), run(250), run(75, agent="a_reporter"), run(5)]
    expected = total_minor(actuals)

    assert expected == 430
    for dimension in Dimension:
        assert sum(spend_by(actuals, dimension).values()) == expected, dimension
    assert spend_by(actuals, Dimension.AGENT)[NO_AGENT] == 255


def test_machine_traffic_is_read_from_the_declared_class_and_never_from_a_field() -> None:
    """M21.3.2 is not this module's leaf to close, but the label it needs has to exist and has
    to be trustworthy. `Actual` therefore has no `machine` field for anybody to set: the
    answer is derived from `limits.is_automated`, which reads the principal's kind and the
    traffic class the channel declared at ingress.

    Anchored on that function rather than restated, so there is no second answer that can
    disagree with the first, and the grid includes the case a sniffer gets wrong: a service
    principal arriving on an interactive channel.

    Delete this and a `machine=True` field appears with a `False` default, and every
    automation written before somebody remembered to set it counts as a person."""
    assert "machine" not in {field.name for field in dataclass_fields(Actual)}

    for kind in PrincipalKind:
        for traffic in TrafficClass:
            row = Actual(
                principal_id="p",
                principal_kind=kind,
                traffic=traffic,
                department="web",
                agent_id=None,
                model="main-1",
                lane=Lane.ANSWER,
                cost_minor=1,
                at=NOW,
            )
            assert row.machine == is_automated(kind, traffic), f"{kind} on {traffic}"


def test_machine_traffic_can_be_excluded_without_the_rows_being_lost() -> None:
    """Excluding is a filter at the point of reporting, never a row that was never written. A
    row that does not exist cannot be added back when somebody asks what the automations
    actually cost, and that is the question the finance conversation always reaches.

    Both directions are asserted: the exclusion changes the total, and the excluded rows are
    still there to be counted the other way.

    Delete this and `include_machine` becomes the default at the write path, and the ledger
    stops being able to answer the question M21.3.2 exists for."""
    actuals = [run(100), run(400, service=True)]

    assert total_minor(actuals) == 500
    assert total_minor(actuals, include_machine=False) == 100
    assert spend_by(actuals, Dimension.PRINCIPAL, include_machine=False) == {"p_alice": 100}
    assert spend_by(actuals, Dimension.PRINCIPAL) == {"p_alice": 100, "p_bot": 400}


def test_an_accounting_row_refuses_to_be_written_without_what_it_is_grouped_by() -> None:
    """A row with no department cannot be counted against a department budget, and a row with
    a naive instant lands in the wrong period at either end of a day, which is the failure
    that shows up as a department being over budget on the first of the month.

    Delete this and a partially populated row is written by whatever assembles it, and the
    breakdown that reconciles today stops reconciling the day one field is dropped."""
    sound = {
        "principal_id": "p_alice",
        "principal_kind": PrincipalKind.HUMAN,
        "traffic": TrafficClass.HUMAN_INTERACTIVE,
        "department": "web",
        "agent_id": None,
        "model": "main-1",
        "lane": Lane.ANSWER,
        "cost_minor": 1,
        "at": NOW,
    }
    assert Actual(**sound).cost_minor == 1  # type: ignore[arg-type]

    for broken, expected in (
        ({"department": ""}, "needs a principal"),
        ({"model": ""}, "needs a principal"),
        ({"cost_minor": -1}, "less than nothing"),
        ({"at": datetime(2026, 9, 1, 9, 0)}, "naive instant"),
    ):
        with pytest.raises(SpendError, match=expected):
            Actual(**{**sound, **broken})  # type: ignore[arg-type]
