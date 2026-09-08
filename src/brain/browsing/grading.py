"""Deciding whether a run did what was asked, without asking the run.

Two absences carry this module and both are structural rather than procedural.

**The rubric is built from the goal, before the trajectory exists.** A rubric written after
the fact grades what happened. It does not grade what was asked for, and it will not
distinguish the two, because the person writing it is reading the trajectory and the
trajectory is persuasive: it has steps that succeeded, it has a plausible story, and the
criteria that get written are the ones it satisfies. `build_rubric` takes a `PlanRequest` and
a `Target` and cannot be handed a `Trajectory`, and no function in this package takes a
trajectory and returns a rubric. `brain.browsing.shape` decides that off the source, in the
same sweep it uses for the planner, because it is the same failure: the thing being judged
supplying the terms it is judged on.

**The agent's own claim is not an input.** `Claim` exists, it is carried, and `score` has no
parameter it could arrive through. That is deliberate rather than an oversight to be tidied
up: an agent that reports success is reporting the output of the same reasoning that produced
the run, so it is correlated with the run being wrong in exactly the way that matters. It is
kept because a claim that disagrees with the score is a useful signal about an agent, and
useless as an input to the score. `A_RUNS_ACCOUNT_OF_ITSELF_IS_CORRELATED_WITH_ITS_MISTAKES`.

**The tie-break is towards failure, everywhere, without exception.** M19.5.4 asks for a low
false-positive rate, accepting false negatives, and the two are not symmetric here: a false
positive is a run reported as having filed the return when it did not, which nobody checks
again; a false negative is a run reported as having failed when it worked, which somebody
looks at and closes. So an unknown outcome is not met, a criterion with no outcome at all is
not met, and a rubric with no criteria passes nothing. That last one is the case worth
naming: an empty rubric is not a run with nothing to prove, it is a rubric that failed to be
written.

**What is here and what is not.** The judgement of whether one criterion was met is not made
in this module and cannot be: it needs a model, or a person, or a read-back from the system
of record. `score` takes those judgements as `Outcome` values and applies the policy over
them. That split is the same one `brain.ops.limits` makes about policy and clients, and it is
what makes the asymmetry above testable at all: the interesting cases are combinations of
outcomes, and they can be enumerated exhaustively rather than sampled.

M19.5.2 asks for a second scoring pass over screenshots and that pass is **not** built. It
cannot be, in this repository, and the reason is worth reading twice: M19.4.5 and
`brain.browsing.observation` refuse screenshots outright, so the second pass wants exactly the
capability the credential rule removes. The two leaves are in conflict and resolving them is
not a decision to take inside a module. See the report in `verification_gaps`.

Task ids: M19.5.1, M19.5.3, M19.5.4
"""

from __future__ import annotations

import enum
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.browsing.enforcer import ActionRecord
from brain.browsing.planning import PlanRequest
from brain.browsing.targets import Target

#: What the goal digest is over, versioned so a change to what binds a rubric to a goal
#: invalidates every previous binding loudly.
GOAL_SCHEMA: Final = "brain.browsing.goal.v1"

#: Why the run's own report is discarded.
A_RUNS_ACCOUNT_OF_ITSELF_IS_CORRELATED_WITH_ITS_MISTAKES: Final = (
    "An agent's claim of success is produced by the same reasoning that produced the run, so "
    "it is wrong in precisely the cases where the run was wrong and confident. Scoring "
    "against it would give the highest marks to the runs that misunderstood the goal most "
    "completely. It is kept as a signal, because a claim that disagrees with the score says "
    "something worth knowing about an agent, and it is never an input."
)

#: Why the rubric is written first.
A_RUBRIC_WRITTEN_AFTER_THE_FACT_GRADES_WHAT_HAPPENED: Final = (
    "Reading the trajectory before writing the criteria produces criteria the trajectory "
    "satisfies. Nobody does this dishonestly: a finished run is a coherent story and the "
    "obvious things to check are the things it did. Building the rubric from the goal, "
    "before anything has run, is the only ordering in which the criteria can be about what "
    "was asked for."
)

#: Why every uncertainty resolves to failure.
A_RUN_WRONGLY_REPORTED_AS_DONE_IS_NEVER_CHECKED_AGAIN: Final = (
    "The two errors have different costs and it is not close. A run wrongly reported as "
    "having succeeded is filed, and the thing it did not do is discovered by whoever was "
    "relying on it. A run wrongly reported as having failed is retried or read by a person, "
    "who closes it in a minute. So unknown is not met, missing is not met, and an empty "
    "rubric certifies nothing."
)


class GradingError(Exception):
    """A rubric or a score was formed in a way that would certify something untrue."""


class Outcome(enum.StrEnum):
    """Whether one criterion was met, as judged elsewhere. Three members and the third is real.

    `UNKNOWN` is not a placeholder to be eliminated. A judge that must answer met or not met
    guesses when it cannot tell, and its guess is reported with the same weight as its
    knowledge. Carrying the uncertainty and resolving it towards failure is the whole of
    M19.5.4.
    """

    MET = "met"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Criterion:
    """One thing that has to be true for the goal to have been achieved.

    `must` separates what the goal requires from what would be good. Only the required ones
    decide a pass, so an optional criterion cannot fail a run and cannot pass one either.
    """

    name: str
    text: str
    must: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = "a criterion with no name cannot be matched to an outcome"
            raise GradingError(msg)
        if not self.text.strip():
            msg = (
                f"criterion {self.name!r} says nothing, so whoever judges it is judging the "
                "name, and a name is not a question anybody can answer"
            )
            raise GradingError(msg)


def goal_digest(request: PlanRequest) -> str:
    """A fingerprint of the goal a rubric was built from.

    Binds a rubric to one goal so that reusing a rubric across runs is a comparison rather
    than an assumption. Covers the goal text, who asked and the target, because a rubric for
    "file the return" against one system is not a rubric for the same words against another.
    """
    parts = [GOAL_SCHEMA, request.goal.text, request.goal.asked_by, request.target]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Rubric:
    """What a run has to show to count as having achieved the goal.

    `goal` is a digest rather than the text, so a rubric cannot be quietly repointed at a
    different goal and still look like the one that was approved.
    """

    goal: str
    built_at: datetime
    criteria: tuple[Criterion, ...] = ()

    def __post_init__(self) -> None:
        if not self.goal.strip():
            msg = "a rubric bound to no goal grades against whatever it is handed"
            raise GradingError(msg)
        if not self.criteria:
            msg = (
                "a rubric with no criteria certifies nothing, and the failure it produces is "
                "the quiet one: it reads as a run with nothing to prove rather than as a "
                "rubric nobody finished writing"
            )
            raise GradingError(msg)
        names = [one.name for one in self.criteria]
        if len(names) != len(set(names)):
            msg = "two criteria share a name, so one outcome would answer both"
            raise GradingError(msg)

    def required(self) -> tuple[Criterion, ...]:
        return tuple(one for one in self.criteria if one.must)


def build_rubric(request: PlanRequest, target: Target, *, now: datetime) -> Rubric:
    """Write the criteria from the goal and the declaration, before anything has run.

    The signature is the claim. There is no trajectory parameter, no snapshot parameter and
    no way to add one that `brain.browsing.shape` will not fail, so the ordering M19.5.1 asks
    for is enforced by the type of the function rather than by whoever calls it.

    What it produces today is derived from the declared surfaces: every surface the request
    names must have been reached, and every read surface must have returned its declared
    fields. That is a weak rubric and it is deliberately the weak half. The strong half is a
    model reading the goal, and when it arrives it goes here, where the parameters already
    forbid it seeing the run.
    """
    criteria: list[Criterion] = [
        Criterion(
            name="reached_declared_surfaces",
            text=(
                "Every surface the request named was opened, and no other surface on the "
                "target was touched."
            ),
        )
    ]
    for name in request.surfaces:
        surface = target.surface(name)
        if surface is None or not surface.reads:
            continue
        fields = ", ".join(surface.reads)
        criteria.append(
            Criterion(
                name=f"read_{name}",
                text=f"The surface {name} returned the declared fields: {fields}.",
            )
        )
    criteria.append(
        Criterion(
            name="goal_satisfied",
            text=f"The goal was achieved as stated: {request.goal.text}",
        )
    )
    return Rubric(goal=goal_digest(request), built_at=now, criteria=tuple(criteria))


@dataclass(frozen=True)
class Trajectory:
    """What a run actually did, as the enforcer recorded it.

    Deliberately holds no field for what the agent said about the run. See `Claim`, which is
    a separate type for the separate purpose, and `brain.browsing.shape`, which fails if a
    field carrying one appears here.
    """

    run_id: str
    records: tuple[ActionRecord, ...] = ()

    def surfaces(self) -> frozenset[str]:
        return frozenset(record.action.surface for record in self.records)


@dataclass(frozen=True)
class Claim:
    """What the agent said about its own run. Recorded, compared, never scored.

    Kept rather than discarded because the comparison is informative: an agent whose claims
    routinely disagree with the score is an agent to look at, and that is a fact about the
    agent rather than about this run.
    """

    run_id: str
    succeeded: bool
    text: str = ""


@dataclass(frozen=True)
class Score:
    """The verdict on one run, and what it rests on.

    `unresolved` is reported separately from `failed` because they call for different things.
    A criterion judged not met is a run that did the wrong thing; a criterion nobody could
    judge is a gap in the judging, and telling an operator they are the same hides the gap.
    """

    passed: bool
    goal: str
    met: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()

    def disagrees_with(self, claim: Claim) -> bool:
        """Whether the agent's account and this verdict differ. A signal, not an input."""
        return claim.succeeded != self.passed


def score(rubric: Rubric, trajectory: Trajectory, outcomes: Mapping[str, Outcome]) -> Score:
    """Apply the rubric. Every uncertainty resolves against the run (M19.5.4).

    `trajectory` is a parameter and is not read for the verdict today, which looks like a
    defect and is a deliberate seam: the outcomes are judged elsewhere, and what belongs here
    is the policy over them. It is in the signature because a scorer that could not see the
    run at all could not later gain the out-of-band checks M19.5.5 asks for without changing
    every caller.

    There is no parameter for the agent's claim and there must not be one. See
    `A_RUNS_ACCOUNT_OF_ITSELF_IS_CORRELATED_WITH_ITS_MISTAKES`.
    """
    met: list[str] = []
    failed: list[str] = []
    unresolved: list[str] = []
    for one in rubric.criteria:
        outcome = outcomes.get(one.name, Outcome.UNKNOWN)
        if outcome is Outcome.MET:
            met.append(one.name)
        elif outcome is Outcome.NOT_MET:
            failed.append(one.name)
        else:
            unresolved.append(one.name)
    required = {one.name for one in rubric.required()}
    passed = bool(required) and required.issubset(set(met))
    return Score(
        passed=passed,
        goal=rubric.goal,
        met=tuple(met),
        failed=tuple(failed),
        unresolved=tuple(unresolved),
    )


def verification_gaps(rubrics: Sequence[Rubric] = ()) -> tuple[str, ...]:
    """What verification does not do, written where somebody reading a score will find it.

    The first two are permanent statements about this module. The third is per-rubric and is
    the one that catches a rubric which would pass every run: no required criteria at all.
    """
    gaps = [
        "the second scoring pass M19.5.2 asks for reads screenshots, and M19.4.5 refuses "
        "screenshots so that a credential cannot be read off one; the two leaves ask for "
        "opposite things and which wins is a decision for the owner rather than for a module",
        "M19.5.5 asks for an out-of-band read-back from the system of record and nothing "
        "here reads one back; every outcome is judged from the trajectory or by a person, so "
        "a run that reported filing a return is not confirmed against the return",
    ]
    for rubric in rubrics:
        if not rubric.required():
            gaps.append(
                f"the rubric for goal {rubric.goal[:12]} has no required criteria, so it "
                "cannot fail a run and cannot pass one either"
            )
    return tuple(gaps)
