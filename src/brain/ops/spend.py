"""What a request will cost, decided before it costs anything.

`brain.ops.budgets` holds the ceilings. This holds the three things that happen around them:
an estimate taken before any tokens are spent, a ladder of things to give up when the
estimate does not fit, and the accounting that closes the loop afterwards.

Six things are load-bearing.

**The estimate is a pure function and there is nowhere to put a client.** A cost estimate
that needed a model call would cost money to find out whether there was money, which is the
one shape this module cannot have. So `estimate` is an ordinary `def` over five scalars, and
the guarantee is structural rather than a convention: there is no `async def` anywhere in
this file, nothing here imports a transport, and `CostInputs` has no field that could hold
something with a method on it. A test parses this module and refuses all three. See
`THE_ESTIMATE_IS_A_PURE_FUNCTION_AND_HAS_NOWHERE_TO_PUT_A_CLIENT`.

**The ladder is ordered by what the caller gives up, and each rung gives up strictly more
than the one above it.** Cheaper tier, then no fan-out, then queue, then refuse. The rungs
are cumulative, which is both how degradation actually works and what makes the ordering hold
by construction: dropping fan-out keeps the cheaper tier rather than restoring the expensive
one. `ladder_disorder` measures the order rather than trusting the declaration, because a
ladder a later editor can reorder without a test failing is not a ladder.

**Refusing saves more than queueing, and that is the difference between the last two rungs.**
A queued request is still going to be paid for; it lands in a later window, so it relieves
this period entirely and the budget's whole horizon not at all. Refusing relieves both. That
is why `Relief` carries two numbers rather than one, and why the two rungs do not compare
equal. See `REFUSE_SAVES_MORE_THAN_QUEUE`.

**A refusal names which budget was hit and who can raise it, and carries no figure at all.**
Naming the budget is deliberate: it is the caller's own budget, not somebody else's data, and
a refusal that says only "no" sends a person to a help desk that cannot help them. Naming a
*role* rather than a person is equally deliberate, and so is the absence of any number. Two
refusals a week apart, each carrying a remaining figure, subtract into how much everybody
else spent in between, and neither refusal on its own looks like a disclosure. See
`A_REFUSAL_CARRIES_NO_FIGURE` and `A_REFUSAL_NAMES_A_ROLE_NOT_A_PERSON`.

**The correction from actuals is bounded in both directions, and the floor is the one that
matters.** An estimator that learns freely learns down: a quiet fortnight of cheap questions
teaches it that everything is cheap, and it then waves through the expensive week with the
budget check passing on every one of them. So the factor is clamped, the clamp is symmetric
in log space, and a single window moves it by a quarter of the distance rather than all of
it. See `CORRECTION_IS_BOUNDED_IN_BOTH_DIRECTIONS`.

**Machine traffic is labelled, never guessed and never dropped.** `Actual.machine` is derived
from `limits.is_automated`, which reads the principal's kind and the channel's declared
traffic class. There is no boolean for a caller to set, so there is no second answer to
disagree with the first, and excluding machine traffic from a report is a filter at the point
of reporting rather than a row that was never written. M21.3.2 is the leaf that decides what
the reports do with it; this is the half that makes the decision possible. See
`MACHINE_TRAFFIC_IS_LABELLED_NOT_DROPPED`.

Nothing here opens a connection, records anything or reads a clock. `now` and the spend so
far arrive as arguments, exactly as they do in `brain.ops.limits`, so the case that is always
wrong is testable: the decision taken at the boundary of a budget with the counters as they
were.

**What has no caller yet.** Nothing in `src` calls `preflight`: the gate is not assembled end
to end, `brain.gate.invoke` does not consult a budget, and no worker writes an `Actual`. What
is here is the shape the decision has to have before anything starts making it, which is the
half worth writing first, because an estimator is easy to start trusting and very hard to
stop once a wrong number is in the ledger.

Task ids: M21.2.1, M21.2.2, M21.2.3, M21.2.4, M21.2.5, M21.2.6
"""

from __future__ import annotations

import enum
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from itertools import pairwise
from types import MappingProxyType
from typing import assert_never

from brain.core.lane import Lane
from brain.core.principal import PrincipalKind
from brain.gate.context import TrafficClass
from brain.models.routing import TIER_LADDER, Tier
from brain.ops.admission import (
    A_PERSON_WAITING_IS_NEVER_QUEUED,
    RefusalKind,
    refusal_record,
)
from brain.ops.budgets import (
    Allowance,
    BudgetError,
    BudgetLevel,
    BudgetPeriod,
    admits,
    tightest,
)
from brain.ops.limits import is_automated

# ------------------------------------------------------------------ written-down reasons
#: Why the estimator cannot become async and cannot be handed a client.
THE_ESTIMATE_IS_A_PURE_FUNCTION_AND_HAS_NOWHERE_TO_PUT_A_CLIENT = (
    "A cost estimate that needed a model call would spend money to find out whether there "
    "was money, and the refusal it exists to produce would arrive after the tokens it exists "
    "to save. So the guarantee is structural rather than a convention somebody keeps: there "
    "is no `async def` in this module, nothing here imports a transport, and `CostInputs` "
    "carries only enums and integers, so there is no field a session could arrive through. "
    "A test parses the module and refuses all three, because a convention lasts until the "
    "first afternoon somebody needs one live figure."
)

#: Why refusing is a rung below queueing rather than the same rung.
REFUSE_SAVES_MORE_THAN_QUEUE = (
    "A queued request is still going to be paid for. It relieves the window under pressure "
    "entirely and the budget's whole horizon not at all, so over a month a queue moves cost "
    "rather than removing it. Refusing removes it. That is why `Relief` carries what is "
    "saved now and what is saved for good, and why the two rungs do not compare equal: a "
    "single number would make them identical and the ladder would end one rung early."
)

#: Why the refusal message carries no number.
A_REFUSAL_CARRIES_NO_FIGURE = (
    "Two refusals a week apart, each naming what was left, subtract into how much everybody "
    "else spent in between, and neither refusal on its own looks like a disclosure. A "
    "remaining figure is also the number a person is most likely to forward, so it travels "
    "furthest. `Refusal` therefore holds a level and a period and nothing else, and the "
    "template has two placeholders and no slot a figure could be added to without editing "
    "the sentence, which is the change a reviewer sees."
)

#: Why the person who can raise a budget is named as a role.
A_REFUSAL_NAMES_A_ROLE_NOT_A_PERSON = (
    "Naming which budget was hit is deliberate and is M21.2.6: it is the caller's own "
    "budget, not somebody else's data, and a refusal that says only 'no' sends a person to a "
    "help desk that cannot help them. Naming a role rather than a person is equally "
    "deliberate. A name is a directory lookup this module cannot make and a fact about the "
    "organisation it has no business stating, and it goes stale the week somebody changes "
    "job while the sentence stays in a log."
)

#: Why the estimator's correction is clamped, and why the clamp is symmetric.
CORRECTION_IS_BOUNDED_IN_BOTH_DIRECTIONS = (
    "An estimator that learns freely learns downwards. A quiet fortnight of cheap questions "
    "teaches it that everything is cheap, and the expensive week that follows then passes "
    "every pre-flight check on the way to spending a month's budget. The floor is what stops "
    "that. The ceiling stops the opposite and rarer failure, where one runaway run teaches "
    "the estimator to refuse ordinary work, which is an outage we caused ourselves. The two "
    "are reciprocal so that a mis-estimate is bounded by the same factor whichever way it "
    "errs and neither direction is reachable faster than the other."
)

#: Why the queue rung is withheld from somebody watching a cursor, in the words the capacity
#: controller already used. Imported and quoted rather than restated: the argument is the same
#: for money as it is for machine capacity, and two copies of it would drift on the afternoon
#: somebody decides a queue would be kinder than a refusal.
A_PERSON_WAITING_IS_NEVER_QUEUED_FOR_MONEY_EITHER = (
    "The money ladder offers a queue for the reason the capacity controller does and "
    "withholds it from the same class, so the argument is quoted rather than written again: "
    + A_PERSON_WAITING_IS_NEVER_QUEUED
)

#: Why a machine's spend is labelled at the point it is recorded.
MACHINE_TRAFFIC_IS_LABELLED_NOT_DROPPED = (
    "`Actual.machine` is derived from `limits.is_automated`, which reads the principal's "
    "kind and the traffic class the channel declared at ingress. There is no boolean for a "
    "caller to set, so there is no second answer that can disagree with the first, and no "
    "user-agent string is consulted. The rows are written either way and excluded at the "
    "point of reporting, because a row that was never written cannot be added back when "
    "somebody asks what the automations actually cost."
)


# ------------------------------------------------------------------------ the cost model
#: Minor units per thousand tokens, by tier. Seeds for the cost column on `model_pool`, which
#: the console owns at runtime, in the same way `routing.TIER_CONTEXT_WINDOW` seeds the
#: window column.
#:
#: **These are ratios first and prices second.** No figure here has been measured against an
#: invoice, and the absolute numbers will be wrong the week a provider changes a price. What
#: the ladder actually depends on is the relation: `Tier.NONE` costs nothing because the fast
#: lane runs no model at all, and each step up the ladder costs enough more than the step
#: below that dropping a tier is worth the worse answer it buys. Both of those are asserted
#: as properties rather than as values.
TIER_RATE_PER_KTOKEN: Mapping[Tier, int] = MappingProxyType(
    {
        Tier.NONE: 0,
        Tier.SMALL: 10,
        Tier.MAIN: 60,
        Tier.HEAVY: 300,
    }
)

#: The least a step down the tier ladder must save, as a fraction of the tier above it.
#: Below this the first rung of the degradation ladder buys a worse answer for very little
#: money, which is the worst trade available: the person notices the quality and nobody
#: notices the saving.
CHEAPER_TIER_MUST_SAVE_AT_LEAST = 0.5

#: The prompt, the instructions and the answer for one request, before retrieval and tools.
#: Ordered by what the lane is allowed to do rather than by observation: `Lane.FAST` runs no
#: model, so it is zero by definition; `Lane.TASK` is autonomous multi-step work and carries
#: several turns of its own scaffolding. A test pins the ordering, not the figures.
BASE_TOKENS: Mapping[Lane, int] = MappingProxyType(
    {
        Lane.FAST: 0,
        Lane.ANSWER: 1_200,
        Lane.TASK: 4_000,
    }
)

#: Tokens one tool round trip adds: the call, the result, and the model reading the result
#: back. A single figure rather than one per tool, because the variation between tools is
#: smaller than the variation between questions, and a per-tool table is a table that goes
#: stale silently.
TOKENS_PER_TOOL_CALL = 800

#: Tokens per thousand. Named because dividing by a bare 1000 in the cost expression reads
#: like a unit conversion somebody can safely move.
TOKENS_PER_KTOKEN = 1_000


class SpendError(Exception):
    """A request, an observation or an accounting row that cannot mean what it says.

    An authoring-time failure like `budgets.BudgetError`, and not part of the
    `brain.core.errors` taxonomy. What a person is told when a budget binds is `Refusal`.
    """


@dataclass(frozen=True)
class CostInputs:
    """Everything the estimate is allowed to read: the four things M21.2.1 names, and fan-out.

    Five fields, every one an enum or an integer. That is the enforceable half of
    `THE_ESTIMATE_IS_A_PURE_FUNCTION_AND_HAS_NOWHERE_TO_PUT_A_CLIENT`: there is no field here
    a session, a client or a callable could arrive through, so an estimator that wanted to go
    and look something up would have to grow a parameter in the signature, which a reviewer
    sees.

    Fan-out is here rather than folded into the tool count because the degradation ladder has
    a rung for it. A question that touches four clients is four branches of the same shape,
    and dropping to one is a different sacrifice from dropping the model tier: it narrows what
    the answer covers rather than how well it is written.
    """

    lane: Lane
    tier: Tier
    tool_calls: int = 0
    retrieval_tokens: int = 0
    fan_out: int = 1

    def __post_init__(self) -> None:
        if self.tool_calls < 0 or self.retrieval_tokens < 0:
            msg = "tool calls and retrieval size are counts and cannot be negative"
            raise SpendError(msg)
        if self.fan_out < 1:
            msg = "a fan-out of less than one branch is not a request"
            raise SpendError(msg)
        if self.lane is Lane.FAST and self.tier is not Tier.NONE:
            msg = (
                f"a fast-lane request cannot be priced at tier {self.tier}; the fast lane "
                "runs no model, and `routing.Tier.NONE` is the absence of the ladder rather "
                "than a cheap rung on it"
            )
            raise SpendError(msg)
        if self.lane is not Lane.FAST and self.tier is Tier.NONE:
            msg = (
                f"a {self.lane} request cannot be priced at tier none; only the fast lane "
                "answers without a model"
            )
            raise SpendError(msg)
        if self.lane is Lane.FAST and (self.tool_calls or self.fan_out > 1):
            msg = (
                "a fast-lane request has no tools and no branches; see "
                "`gate.fast_lane.THE_FAST_LANE_HAS_NOWHERE_TO_PUT_A_TOOL`"
            )
            raise SpendError(msg)


@dataclass(frozen=True)
class Correction:
    """How far the estimator's raw arithmetic is currently believed to be off.

    Carries the sample count it was learnt from, because a factor of 1.4 over twenty-two runs
    and a factor of 1.4 over nine thousand are the same number and different degrees of
    evidence, and the console is where somebody decides whether to trust it.
    """

    factor: float
    samples: int
    reason: str

    def __post_init__(self) -> None:
        if not CORRECTION_FLOOR <= self.factor <= CORRECTION_CEILING:
            msg = (
                f"a correction of {self.factor} is outside [{CORRECTION_FLOOR}, "
                f"{CORRECTION_CEILING}]; see CORRECTION_IS_BOUNDED_IN_BOTH_DIRECTIONS"
            )
            raise SpendError(msg)
        if self.samples < 0:
            msg = "a sample count cannot be negative"
            raise SpendError(msg)
        if not self.reason:
            msg = "a correction with no stated reason cannot be argued with in the console"
            raise SpendError(msg)


#: The least the correction may ever fall to. A half: the estimator may believe a request
#: costs half what its arithmetic says, and no less. This is the bound that matters, because
#: under-estimating is the direction that waves expensive work through a budget check.
CORRECTION_FLOOR = 0.5

#: The most it may ever rise to. The reciprocal of the floor, so that a mis-estimate is
#: bounded by the same factor whichever way it errs and neither direction is reachable faster
#: than the other. Its own job is the rarer failure: one runaway run teaching the estimator to
#: refuse ordinary work, which is an outage we caused ourselves.
CORRECTION_CEILING = 2.0

#: How much of the distance to the newly observed factor one window moves. A quarter, so it
#: takes several consistent windows to move the estimate a long way and one unusual window
#: moves it a little. A blend of 1.0 is "trust the last window entirely", which is exactly the
#: one-cheap-fortnight failure the floor exists to bound.
CORRECTION_BLEND = 0.25

#: Runs below which a ratio means nothing. The same argument as
#: `limits.VOLUME_MIN_OBSERVATIONS`, and never fewer than it: a cost ratio is noisier than a
#: volume ratio, because one long task outweighs fifty questions.
MIN_CORRECTION_SAMPLES = 20

NO_CORRECTION = Correction(
    factor=1.0,
    samples=0,
    reason="no actuals have been folded in; the raw arithmetic stands",
)


@dataclass(frozen=True)
class Estimate:
    """What a request is expected to cost, and what that expectation was built from.

    Carries its inputs so that a refusal can be replayed from a trace without the estimator
    being run again against a different rate table.
    """

    inputs: CostInputs
    tokens: int
    minor: int
    factor: float


def estimate(inputs: CostInputs, *, correction: Correction = NO_CORRECTION) -> Estimate:
    """What this request will cost, from lane, tier, tool count and retrieval size (M21.2.1).

    Pure, synchronous, and takes nothing that could look anything up. See
    `THE_ESTIMATE_IS_A_PURE_FUNCTION_AND_HAS_NOWHERE_TO_PUT_A_CLIENT`.

    Rounds up. An estimate that rounds down under-states, and under-stating is the direction
    that admits work which should have been degraded; a whole minor unit per request is a
    rounding error and a budget waved through is not.

    A fast-lane request costs nothing, and it costs nothing because `Tier.NONE` is priced at
    nothing rather than because of a branch here. The fast lane runs no model at all, which is
    what `core.lane.Lane.FAST` means.
    """
    rate = TIER_RATE_PER_KTOKEN.get(inputs.tier)
    if rate is None:
        msg = (
            f"tier {inputs.tier} has no rate, so nothing can say what a request costs; an "
            "unpriced tier waits for somebody to price it rather than defaulting"
        )
        raise SpendError(msg)
    per_branch = (
        BASE_TOKENS[inputs.lane]
        + inputs.tool_calls * TOKENS_PER_TOOL_CALL
        + inputs.retrieval_tokens
    )
    tokens = per_branch * inputs.fan_out
    minor = math.ceil(tokens * rate * correction.factor / TOKENS_PER_KTOKEN)
    return Estimate(inputs=inputs, tokens=tokens, minor=minor, factor=correction.factor)


# ------------------------------------------------------------- correction from actuals
@dataclass(frozen=True)
class Observation:
    """One completed run: what it was estimated at, and what it actually cost.

    Both figures are required to be at least one unit. A zero estimate cannot be corrected
    against, because the ratio is undefined, and a zero actual is a fast-lane answer, which
    teaches the model-cost estimator nothing at all.
    """

    estimated_minor: int
    actual_minor: int

    def __post_init__(self) -> None:
        if self.estimated_minor < 1:
            msg = "an estimate of nothing has no ratio to an actual"
            raise SpendError(msg)
        if self.actual_minor < 1:
            msg = "a run that cost nothing teaches a model-cost estimator nothing"
            raise SpendError(msg)


def correct(prior: Correction, observations: Sequence[Observation]) -> Correction:
    """Fold a window of actuals into the correction factor (M21.2.4).

    **The ratio is over the totals, not the mean of the per-run ratios.** A mean of ratios
    lets a hundred trivial cheap runs outvote one expensive one, which is the failure this
    whole function has to survive: the runs that matter to a budget are the few large ones,
    and a mean weights them equally with a question that cost a penny.

    Moves a quarter of the way and no further, then clamps. See
    `CORRECTION_IS_BOUNDED_IN_BOTH_DIRECTIONS`. Below `MIN_CORRECTION_SAMPLES` the prior is
    returned unchanged rather than moved a little, because a ratio over four runs is noise
    and moving on noise is how the factor drifts with nothing reporting that it has.
    """
    if len(observations) < MIN_CORRECTION_SAMPLES:
        return Correction(
            factor=prior.factor,
            samples=prior.samples,
            reason=(
                f"{len(observations)} run(s) is below the {MIN_CORRECTION_SAMPLES} a cost "
                "ratio needs to mean anything; the prior stands"
            ),
        )
    estimated = sum(one.estimated_minor for one in observations)
    actual = sum(one.actual_minor for one in observations)
    residual = actual / estimated
    target = prior.factor * residual
    blended = prior.factor + CORRECTION_BLEND * (target - prior.factor)
    factor = min(CORRECTION_CEILING, max(CORRECTION_FLOOR, blended))
    return Correction(
        factor=factor,
        samples=len(observations),
        reason=(
            f"{len(observations)} runs came in at {residual:.2f}x their estimate; the factor "
            f"moved {CORRECTION_BLEND:.0%} of the way and is clamped to "
            f"[{CORRECTION_FLOOR}, {CORRECTION_CEILING}]"
        ),
    )


# ------------------------------------------------------------------ the degradation ladder
class Rung(enum.IntEnum):
    """What to give up, in order, when a request does not fit (M21.2.5).

    An `IntEnum` and ordered, because the useful operation is "everything up to here" and a
    comparison is the honest way to write it. The values are the ladder; `LADDER` is sorted by
    them rather than by declaration order, so moving a line does not move a rung and changing
    a value does.

    **The rungs are cumulative.** `NO_FAN_OUT` keeps the cheaper tier rather than restoring
    the expensive one, which is both how anybody actually degrades a request and what makes
    each rung give up strictly more than the one above it without that having to be arranged
    by hand.
    """

    #: Same question, same breadth, a smaller model.
    CHEAPER_TIER = 0
    #: The cheaper model, and one branch instead of several. Narrower, not worse.
    NO_FAN_OUT = 1
    #: The same degraded work, in a later window. Nobody may be waiting for it.
    QUEUE = 2
    #: Nothing runs. The only rung that removes the cost rather than moving it.
    REFUSE = 3


#: The ladder, cheapest sacrifice first. Sorted by value rather than taken from the
#: declaration order, so that the integers are the single statement of the order.
LADDER: tuple[Rung, ...] = tuple(sorted(Rung))


@dataclass(frozen=True)
class Relief:
    """What a rung takes off the budget: out of this window, and out of every window.

    Two numbers rather than one, and that is the whole of `REFUSE_SAVES_MORE_THAN_QUEUE`. A
    queued request relieves the window under pressure completely and the budget's horizon not
    at all, because it is still going to be paid for. With one number a queue and a refusal
    are the same rung and the ladder ends early.
    """

    now_minor: int
    for_good_minor: int

    @property
    def key(self) -> tuple[int, int]:
        """The comparable form. Lexicographic: relief now first, then relief for good."""
        return (self.now_minor, self.for_good_minor)


def cheaper_tier(tier: Tier) -> Tier:
    """One step down `routing.TIER_LADDER`, or the same tier when there is no step left.

    Reads the ladder from `brain.models.routing` rather than restating it. A second ordering
    of the tiers here would be a second thing to keep in step with the model pools, and the
    copy that drifts is the one deciding what a degraded answer runs on.
    """
    if tier not in TIER_LADDER:
        return tier
    position = TIER_LADDER.index(tier)
    return TIER_LADDER[position - 1] if position > 0 else tier


def degraded(inputs: CostInputs, rung: Rung) -> CostInputs | None:
    """The request as it would run at this rung. None means it does not run at all.

    Cumulative: every rung applies the sacrifices of the rungs above it as well as its own.
    `assert_never` is the point of the shape. A new rung is a type error here until somebody
    decides what it gives up, and a mapping with a default would quietly give up nothing.
    """
    match rung:
        case Rung.CHEAPER_TIER:
            return replace(inputs, tier=cheaper_tier(inputs.tier))
        case Rung.NO_FAN_OUT:
            return replace(inputs, tier=cheaper_tier(inputs.tier), fan_out=1)
        case Rung.QUEUE:
            # The same work as the rung above, later. A queue changes when the cost lands,
            # never what it is, which is exactly why it relieves one window and no more.
            return replace(inputs, tier=cheaper_tier(inputs.tier), fan_out=1)
        case Rung.REFUSE:
            return None
        case _:
            assert_never(rung)


def relief_of(rung: Rung, inputs: CostInputs, *, correction: Correction = NO_CORRECTION) -> Relief:
    """What this rung would take off the budget for this request."""
    full = estimate(inputs, correction=correction).minor
    lowered = degraded(inputs, rung)
    if lowered is None:
        return Relief(now_minor=full, for_good_minor=full)
    cost = estimate(lowered, correction=correction).minor
    if rung is Rung.QUEUE:
        return Relief(now_minor=full, for_good_minor=full - cost)
    return Relief(now_minor=full - cost, for_good_minor=full - cost)


def ladder_disorder(
    inputs: CostInputs, *, correction: Correction = NO_CORRECTION
) -> tuple[str, ...]:
    """Every way the declared ladder disagrees with what the rungs actually give up.

    The same construction `memory.tiers.tier_gaps` uses: the declaration is checked against a
    measurement rather than believed. An inversion is reported; equality is not, because a
    rung can legitimately give up nothing for a particular request, such as a cheaper tier for
    a request already at the cheapest.

    Refusing must be the last rung and must give up strictly the most. Without both of those a
    reordered enum leaves `preflight` refusing before it has tried a queue, and every test
    written about degradation still passes because degradation still happens.
    """
    gaps: list[str] = []
    reliefs = {rung: relief_of(rung, inputs, correction=correction) for rung in LADDER}

    for earlier, later in pairwise(LADDER):
        if reliefs[later].key < reliefs[earlier].key:
            gaps.append(
                f"{later.name} is below {earlier.name} on the ladder and gives up less, so "
                "descending it makes a request more expensive rather than less"
            )
    if LADDER[-1] is not Rung.REFUSE:
        gaps.append(
            f"the last rung is {LADDER[-1].name}; refusing must be last, or a request is "
            "refused while a cheaper sacrifice is still untried"
        )
    if estimate(inputs, correction=correction).minor > 0:
        for rung in LADDER:
            if rung is not Rung.REFUSE and reliefs[rung].key >= reliefs[Rung.REFUSE].key:
                gaps.append(
                    f"{rung.name} gives up as much as refusing, so the ladder has two last "
                    "rungs and which one runs is decided by declaration order"
                )
    return tuple(gaps)


# ---------------------------------------------------------------------------- the refusal
#: How each budget is named to the person who hit it. Exhaustive over `BudgetLevel` by test.
#: Second person for the three a caller owns some part of, third for the company's, because
#: "your company budget" invites a reply about their own spending and the company's ceiling is
#: not theirs to have spent.
BUDGET_PHRASE: Mapping[BudgetLevel, str] = MappingProxyType(
    {
        BudgetLevel.COMPANY: "The company's {period} budget",
        BudgetLevel.DEPARTMENT: "Your department's {period} budget",
        BudgetLevel.USER: "Your own {period} allowance",
        BudgetLevel.AGENT: "This agent's {period} ceiling",
    }
)

#: How each period reads in that sentence. Exhaustive over `BudgetPeriod` by test.
PERIOD_PHRASE: Mapping[BudgetPeriod, str] = MappingProxyType(
    {
        BudgetPeriod.RUN: "per-run",
        BudgetPeriod.DAY: "daily",
        BudgetPeriod.MONTH: "monthly",
    }
)

#: Who can raise each budget, as a role. Exhaustive over `BudgetLevel` by test. See
#: `A_REFUSAL_NAMES_A_ROLE_NOT_A_PERSON`.
RAISED_BY: Mapping[BudgetLevel, str] = MappingProxyType(
    {
        BudgetLevel.COMPANY: "whoever owns the company's budget",
        BudgetLevel.DEPARTMENT: "your department head",
        # A person's allowance is a share of their department's, so the person who can widen
        # it is the person who owns the department's, not the person themselves.
        BudgetLevel.USER: "your department head",
        BudgetLevel.AGENT: "the agent's owner",
    }
)

#: One sentence, two placeholders, no count. A module constant rather than an f-string at the
#: call site, for the reason `department.GAP_TEMPLATE` is one: so that it cannot quietly
#: acquire "you have 4 left" the week somebody decides the message is unhelpful.
REFUSAL_TEMPLATE = "{budget} is used up; {who} can raise it."


@dataclass(frozen=True)
class Refusal:
    """Which budget was hit and who can raise it (M21.2.6). Two fields, and no figure.

    There is no subject here, no amount and no headroom. That is not a rule about what the
    renderer may print, it is the absence of anything to print: see `A_REFUSAL_CARRIES_NO_FIGURE`.
    The operator log gets the same two facts, and the audit layer owns who asked, exactly as
    `admission.refusal_record` says it does.
    """

    level: BudgetLevel
    period: BudgetPeriod

    @property
    def budget(self) -> str:
        return BUDGET_PHRASE[self.level].format(period=PERIOD_PHRASE[self.period])

    @property
    def raised_by(self) -> str:
        return RAISED_BY[self.level]

    @property
    def message(self) -> str:
        return REFUSAL_TEMPLATE.format(budget=self.budget, who=self.raised_by)

    def log_record(self) -> Mapping[str, str]:
        """The operator-facing line. `QUOTA`, because a budget is the caller's own allowance.

        Not `CAPACITY`: the machine has room and buying a bigger one would not help. Not
        `DEPENDENCY`: nothing was unreachable. `OPERATOR_ACTION` for QUOTA already says the
        right thing, which is to raise this allowance or leave it alone deliberately.
        """
        return refusal_record(
            RefusalKind.QUOTA,
            subject=f"budget:{self.level}:{self.period}",
            detail=f"{self.budget} is exhausted for the period",
        )


# ------------------------------------------------------------------------- the pre-flight
@dataclass(frozen=True)
class AlertCrossing:
    """An alert fraction this request would take a budget past for the first time."""

    level: BudgetLevel
    period: BudgetPeriod
    fraction: float


@dataclass(frozen=True)
class Preflight:
    """What to do with a request, decided before a token is spent (M21.2.2).

    `rung` is None when the request runs exactly as asked, which is the ordinary case and the
    one a guard tested only by its refusals would quietly break.
    """

    allowed: bool
    #: The rung applied, or None when nothing was given up.
    rung: Rung | None
    #: The request to actually run. None when it is refused.
    inputs: CostInputs | None
    estimate_minor: int
    refusal: Refusal | None = None
    alerts: tuple[AlertCrossing, ...] = ()

    @property
    def queued(self) -> bool:
        return self.rung is Rung.QUEUE

    @property
    def degraded(self) -> bool:
        return self.allowed and self.rung is not None


def alerts_for(allowances: Sequence[Allowance], cost_minor: int) -> tuple[AlertCrossing, ...]:
    """Alert fractions this spend would cross that the spend so far had not (M21.1.1).

    Newly crossed rather than currently over, so that a budget sitting at 80% does not raise
    the 75% alert on every request for the rest of the month. An alert that repeats is an
    alert people filter, and then the 90% one arrives in a folder nobody reads.
    """
    crossings: list[AlertCrossing] = []
    for allowance in allowances:
        before = set(allowance.row.alerts_crossed(allowance.spent_minor))
        after = allowance.row.alerts_crossed(allowance.spent_minor + cost_minor)
        crossings.extend(
            AlertCrossing(level=allowance.row.level, period=allowance.row.period, fraction=fraction)
            for fraction in after
            if fraction not in before
        )
    return tuple(crossings)


def may_queue(traffic: TrafficClass, allowances: Sequence[Allowance], cost_minor: int) -> bool:
    """Whether the queue rung is available for this request.

    Two reasons it is not, and they are different failures.

    A person watching a cursor is never queued. That is not this module's rule to make:
    `admission.A_PERSON_WAITING_IS_NEVER_QUEUED` already decided it for capacity, and the
    argument is the same for money, so the constant is imported rather than restated.

    A per-run ceiling cannot be waited past. Waiting refills a day and a month and does
    nothing at all to the most one run may cost, so offering a queue against one hands back a
    position that will be refused again on arrival. `BudgetPeriod.RUN` exists to make that
    difference expressible.
    """
    if traffic is TrafficClass.HUMAN_INTERACTIVE:
        return False
    return all(
        allowance.headroom_minor >= cost_minor
        for allowance in allowances
        if allowance.row.period is BudgetPeriod.RUN
    )


def preflight(
    inputs: CostInputs,
    *,
    allowances: Sequence[Allowance],
    traffic: TrafficClass,
    correction: Correction = NO_CORRECTION,
) -> Preflight:
    """Run it, degrade it, queue it or refuse it, before any of it is spent (M21.2.2).

    The request as asked is tried first, and it is the ordinary answer. Only when it does not
    fit does the ladder run, cheapest sacrifice first, stopping at the first rung that fits.

    Nothing is recorded here and no spend is registered: `Allowance.spent_minor` arrives from
    outside and the accounting happens afterwards against the actual, not against this
    estimate. That is the same split `limits.check` makes, and for the same reason: a refusal
    that consumed budget would push a caller further from being served every time they were
    turned away.
    """
    asked = estimate(inputs, correction=correction)
    if admits(allowances, asked.minor):
        return Preflight(
            allowed=True,
            rung=None,
            inputs=inputs,
            estimate_minor=asked.minor,
            alerts=alerts_for(allowances, asked.minor),
        )

    cheapest = asked.minor
    for rung in LADDER:
        lowered = degraded(inputs, rung)
        if lowered is None:
            break
        cost = estimate(lowered, correction=correction).minor
        cheapest = min(cheapest, cost)
        if relief_of(rung, inputs, correction=correction).now_minor <= 0:
            # This rung gives up nothing for this request: a cheaper tier for a request
            # already at the cheapest, or no fan-out for a request with one branch.
            # Offering it would report a degradation that did not happen, which is worse
            # than refusing, because it looks like it worked.
            #
            # It cannot currently change the outcome, and mutation testing proved that
            # rather than argument: a rung with no relief costs exactly what was asked,
            # `admits` was already False for that figure at the top of this function, and
            # the only rung whose relief is the whole cost is the queue, whose relief is
            # zero only for a request that costs nothing and was therefore admitted above.
            # It stays as the statement of intent, in the same way the unreachable branch
            # below does, so that a later edit which decouples a rung's availability from
            # its cost cannot start reporting sacrifices nobody made.
            continue
        if rung is Rung.QUEUE:
            if not may_queue(traffic, allowances, cost):
                continue
            return Preflight(
                allowed=True,
                rung=rung,
                inputs=lowered,
                estimate_minor=cost,
                alerts=alerts_for(allowances, cost),
            )
        if admits(allowances, cost):
            return Preflight(
                allowed=True,
                rung=rung,
                inputs=lowered,
                estimate_minor=cost,
                alerts=alerts_for(allowances, cost),
            )

    binding = tightest(allowances, cheapest)
    if binding is None:
        # Not reachable: the loop returns for any rung whose cost every allowance admits, and
        # an empty allowance list admits everything and returns at the top. Present so that a
        # future edit to the loop cannot fall through to a refusal naming nothing.
        msg = "the ladder refused while every budget admitted the cheapest variant"
        raise AssertionError(msg)
    return Preflight(
        allowed=False,
        rung=Rung.REFUSE,
        inputs=None,
        estimate_minor=cheapest,
        refusal=Refusal(level=binding.row.level, period=binding.row.period),
    )


# ------------------------------------------------------------------- post-hoc accounting
class Dimension(enum.StrEnum):
    """The five things spend is counted against. Exactly M21.2.3's list.

    A closed vocabulary, because `spend_by` matches on it with `assert_never`: a sixth
    dimension is a type error until somebody says what key it groups by, rather than a
    silently empty report.
    """

    PRINCIPAL = "principal"
    DEPARTMENT = "department"
    AGENT = "agent"
    MODEL = "model"
    LANE = "lane"


#: The key rows with no agent are grouped under. A bucket rather than a filter, so that the
#: agent breakdown still totals to the same figure as every other breakdown. Dropping the rows
#: instead makes the agent report quietly smaller than the department report, and the first
#: person to notice is the one reconciling an invoice.
NO_AGENT = "(no agent)"


@dataclass(frozen=True)
class Actual:
    """One completed run and what it actually cost (M21.2.3).

    Carries the principal, the department, the agent, the model and the lane, which is the
    five dimensions M21.2.3 asks to account against and nothing beyond them. In particular it
    carries no question, no answer and no record identifier: a cost ledger is a copy of
    business activity with its own retention, and the rule `ops.queue` states about jobs
    applies here unchanged.

    Whether this was a machine is derived rather than stored. See
    `MACHINE_TRAFFIC_IS_LABELLED_NOT_DROPPED`.
    """

    principal_id: str
    principal_kind: PrincipalKind
    traffic: TrafficClass
    department: str
    agent_id: str | None
    model: str
    lane: Lane
    cost_minor: int
    at: datetime

    def __post_init__(self) -> None:
        if not self.principal_id or not self.department or not self.model:
            msg = "an accounting row needs a principal, a department and a model to group by"
            raise SpendError(msg)
        if self.cost_minor < 0:
            msg = "a run cannot have cost less than nothing"
            raise SpendError(msg)
        if self.at.tzinfo is None:
            msg = "a naive instant lands in the wrong budget period at either end of a day"
            raise SpendError(msg)

    @property
    def machine(self) -> bool:
        """Whether nobody was asking. A lookup through `limits.is_automated`, never a guess."""
        return is_automated(self.principal_kind, self.traffic)

    def key_for(self, dimension: Dimension) -> str:
        """This row's bucket in one dimension.

        `assert_never` rather than a mapping, for the reason `lane_share.is_machine` uses one:
        a new dimension is a type error until somebody decides what it groups by, and a
        mapping with a default would produce an empty report that looks like no spend.
        """
        match dimension:
            case Dimension.PRINCIPAL:
                return self.principal_id
            case Dimension.DEPARTMENT:
                return self.department
            case Dimension.AGENT:
                return self.agent_id or NO_AGENT
            case Dimension.MODEL:
                return self.model
            case Dimension.LANE:
                return str(self.lane)
            case _:
                assert_never(dimension)


def spend_by(
    actuals: Sequence[Actual], dimension: Dimension, *, include_machine: bool = True
) -> Mapping[str, int]:
    """Total spend in one dimension (M21.2.3).

    Every row lands in exactly one bucket, including rows with no agent, so any two
    dimensions total to the same figure. That reconciliation is the property worth having:
    a breakdown that quietly drops rows is a breakdown somebody balances an invoice against
    and cannot.

    `include_machine` is a filter at the point of reporting rather than at the point of
    recording, and the labelled rows are always written. What the reports do with it is
    M21.3.2's decision, not this function's.
    """
    totals: dict[str, int] = {}
    for actual in actuals:
        if actual.machine and not include_machine:
            continue
        key = actual.key_for(dimension)
        totals[key] = totals.get(key, 0) + actual.cost_minor
    return MappingProxyType(totals)


def total_minor(actuals: Sequence[Actual], *, include_machine: bool = True) -> int:
    """Everything these rows cost. The figure every dimension's breakdown must add up to."""
    return sum(one.cost_minor for one in actuals if include_machine or not one.machine)


def observed(prediction: Estimate, actual: Actual) -> Observation:
    """Pair one estimate with what the run actually cost, ready for `correct` (M21.2.4).

    The bridge between the accounting and the estimator, written here rather than left to the
    caller so that the estimated figure fed back is the one the estimator produced. Building
    an `Observation` from a re-run of `estimate` would compare the estimator against itself
    and the correction would be 1.0 for every rate table it could possibly hold.
    """
    return Observation(estimated_minor=prediction.minor, actual_minor=actual.cost_minor)


def budget_gaps() -> tuple[str, ...]:
    """Every budget level or period the refusal wording cannot name.

    The same construction `memory.tiers.tier_gaps` uses. The message is assembled from three
    mappings and a template, and a missing entry raises at the moment somebody is being
    refused, which is the worst moment for a lookup to fail and the one least likely to be
    reached by a test that never produced that level.
    """
    gaps: list[str] = []
    for level in BudgetLevel:
        if level not in BUDGET_PHRASE:
            gaps.append(f"{level.value} has no wording, so a refusal cannot name it")
        if level not in RAISED_BY:
            gaps.append(f"{level.value} has nobody who can raise it, which M21.2.6 requires")
    for period in BudgetPeriod:
        if period not in PERIOD_PHRASE:
            gaps.append(f"{period.value} has no wording, so a refusal cannot name the window")
    return tuple(gaps)


def assert_priced(tiers: Sequence[Tier] = TIER_LADDER) -> None:
    """Refuse a tier ladder with an unpriced or non-increasing rung.

    Checked against `routing.TIER_LADDER` rather than against this module's own mapping, so
    that a tier added to the model pools without a price fails here instead of being estimated
    at whatever a missing key defaults to. That is the constant-anchoring rule applied to a
    table: the rates are held to another module's list.
    """
    previous = -1
    for tier in tiers:
        rate = TIER_RATE_PER_KTOKEN.get(tier)
        if rate is None:
            msg = f"{tier} is on the routing ladder and has no rate here"
            raise BudgetError(msg)
        if rate <= previous:
            msg = (
                f"{tier} costs {rate} and the tier below it costs {previous}; a ladder that "
                "does not rise makes the cheaper-tier rung a worse answer for no money"
            )
            raise BudgetError(msg)
        previous = rate
