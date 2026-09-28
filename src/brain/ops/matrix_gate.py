"""Whether a change to the routing matrix may take traffic: the golden questions and the canaries.

M5.6.2: "a change to the routing matrix is run against the golden questions and permission
canaries through the gate before it takes traffic, and a regression holds the change with the
failing cases shown." Until now a rung edit on the Routing screen was an UPDATE that took effect
on the next call, and nothing asked whether the ladder it produced still answered anything.

**The change is tried on a copy of the ladder, never on the live one.** `overlaid` is the live
rungs with the edit applied, or with the new rung appended, and the golden questions are asked
through the answer lane with an executor planning from that copy
(`brain.ops.matrix_gate_run`). Nothing reaches the live ladder until the verdict says it may,
so there is no moment at which a person's question is answered by a change still being judged.

**A golden question that must be refused is a permission case, and one failing holds the change
whatever the rest did.** The scoring is `brain.ops.evaluation.score`, unchanged: permission cases
at zero tolerance, quality cases against the floor and against the share the last applied change
recorded, so a change that makes the ladder answer fewer questions than it did is held even
above the floor. See `evaluation.A_PERCENTAGE_IS_THE_WRONG_INSTRUMENT_FOR_A_PERMISSION`.

**The canaries are asked too, and any finding holds the change.** They ask the fast-path rules,
which no model answers, so a matrix change cannot move them; they are run because the requirement
names them and because a change applied while the install is leaking is a change applied into a
fault. A finding is recorded by its kind and nothing else, for `brain.ops.canary_run`'s reason:
the field and the asker belong in the alert, not in a row more screens read.

**No golden question is not a pass.** An install with none has asked nothing, and "nothing
failed" from a gate that asked nothing is the green `evaluation.score` refuses for an empty run.
So the change is held with the reason saying to record golden questions on the Routing screen.
See `A_GATE_THAT_ASKED_NOTHING_HAS_PASSED_NOTHING`.

**A step is retired, or moved, through the same gate** (M5.3.3, 2026-09-28). A retirement is the
ladder without the rung; a move is the rung at another step, in its own level or another. **A move
never updates a position**: `uq_routing_rung_tier_position_live` is checked row by row, so shifting
a level's positions in one UPDATE collides with itself halfway through. `placements` therefore
gives the moved rung, and when no free position sits where it is going the rungs after it, fresh
positions above every live one in the level, and the route retires those rows and inserts them
again in one transaction. Positions only ever grow, which is `docs/admin-console-architecture.md`'s
"insert-only positions". Rejected: numbering a level 0, 10, 20 so a move can take 15. It postpones
the collision rather than removing it, and the gaps would be a meaning nobody reads.

**A change that leaves a level with no step is held before anything is asked**
(`levels_left_empty`). A level with no step has nowhere to send a question, and the golden
questions might not touch that level, so their pass would not be evidence that the level still
answers. See `A_LEVEL_KEEPS_AT_LEAST_ONE_STEP`.

Scope: pure. Questions, answers, findings and the baseline are parameters.

Task ids: M5.6.2, M5.3.3
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Final

from brain.models.assembly import LadderRung
from brain.models.routing import TIER_LADDER, Tier
from brain.ops.canaries import CanaryFinding
from brain.ops.evaluation import Baseline, CaseResult, Severity, score
from brain.tables.model_registry import GoldenExpectation

# ------------------------------------------------------------------- written-down reasons

#: Why an install with no golden questions cannot change its matrix.
A_GATE_THAT_ASKED_NOTHING_HAS_PASSED_NOTHING: Final = (
    "A matrix change is held until the golden questions have been asked through the changed "
    "ladder. With none recorded nothing was asked, and a pass from a gate that asked nothing is "
    "what a broken runner looks like, so the change is held and the reason says to record some."
)

#: What the held change says when there are no golden questions.
NO_GOLDEN_QUESTIONS: Final = (
    "No golden questions are recorded yet, so nothing could check that questions are still "
    "answered after this change. Add a golden question on the Routing screen, then save the "
    "change again."
)

#: The case id every canary finding is recorded under, numbered.
CANARY_CASE: Final = "canary"

#: Why a retirement or a move may not empty a level.
A_LEVEL_KEEPS_AT_LEAST_ONE_STEP: Final = (
    "A level with no step has nowhere to send a question that needs it, and the golden questions "
    "may never touch that level, so their passing says nothing about it. A retirement or a move "
    "that would leave a level empty is held with that reason before the gate asks anything."
)

#: The owner's names for the levels, which a held change's reason is written in.
LEVEL_NAMES: Final = {Tier.SMALL: "Simple", Tier.MAIN: "Medium", Tier.HEAVY: "Complex"}

#: The widest position a rung can hold: `ops.routing_rung.position` is a `smallint`.
POSITION_CEILING: Final = 2**15 - 1


def level_left_empty(tier: Tier) -> str:
    """The reason a change that empties `tier` is held, in the owner's words."""
    return (
        f"This would leave the {LEVEL_NAMES.get(tier, tier.value)} level with no step, so a "
        "question needing it would have nowhere to go. Add another step to that level first, "
        "then try again."
    )


@dataclass(frozen=True)
class GoldenQuestion:
    """One golden question: its id, its text, who it is asked as, and what it must come to."""

    question_id: str
    question: str
    asked_as: str
    expect: GoldenExpectation


@dataclass(frozen=True)
class RungEdit:
    """The four numbers the Routing screen changes on one rung."""

    rung_id: str
    attempts: int
    timeout_seconds: float
    max_concurrency: int
    enabled: bool


@dataclass(frozen=True)
class RungAddition:
    """A new rung at the end of a tier: the provider and model it calls, and its numbers."""

    tier: Tier
    provider: str
    model: str
    attempts: int
    timeout_seconds: float
    max_concurrency: int

    @property
    def deployment_id(self) -> str:
        """The deployment an added rung names: its provider and model, as the ladder spells them."""
        return f"{self.provider}-{self.model}"[:120]


@dataclass(frozen=True)
class RungRetirement:
    """A live rung taken off the ladder. Its row is retired and its attempts stay."""

    rung_id: str


@dataclass(frozen=True)
class RungMove:
    """A live rung moved to another step, in its own level or another.

    `step` counts from 1 in the level as it will stand, the way the Routing screen numbers it;
    a step past the end is the end.
    """

    rung_id: str
    tier: Tier
    step: int


MatrixChange = RungEdit | RungAddition | RungRetirement | RungMove

#: One live rung as a move reads it: its id, its level and its position.
Placed = tuple[str, Tier, int]


@dataclass(frozen=True)
class Placement:
    """A rung a move rewrites, and the position it takes in the move's level."""

    rung_id: str
    position: int


class GateError(ValueError):
    """A change the ladder cannot hold, such as an edit naming no live rung."""


#: What a move to the step a rung already holds is refused with.
ALREADY_THERE: Final = "the step is already there, so there is nothing to move"


def next_position(rungs: Sequence[LadderRung], tier: Tier) -> int:
    """The position after the last live rung of `tier`: an added rung is the last fallback."""
    positions = [one.position for one in rungs if one.tier is tier]
    return max(positions) + 1 if positions else 0


def _in_order(live: Sequence[Placed], tier: Tier) -> list[Placed]:
    return sorted((one for one in live if one[1] is tier), key=lambda one: one[2])


def placements(live: Sequence[Placed], move: RungMove) -> tuple[Placement, ...]:
    """The rungs a move rewrites, in chain order, each with the position it takes.

    The moved rung alone when a free position sits where it is going (the end of the level, or a
    gap a retirement left); otherwise the moved rung and every rung after it, at fresh positions
    above every live one in the level, so no insert can meet a live position. See the module
    docstring on why positions are never updated.
    """
    moving = next((one for one in live if one[0] == move.rung_id), None)
    if moving is None:
        msg = "the move names no live rung"
        raise GateError(msg)
    if move.step < 1:
        msg = "a step is counted from 1"
        raise GateError(msg)
    others = [one for one in _in_order(live, move.tier) if one[0] != move.rung_id]
    index = min(move.step - 1, len(others))
    if moving[1] is move.tier and _in_order(live, move.tier).index(moving) == index:
        raise GateError(ALREADY_THERE)
    top = max((one[2] for one in live if one[1] is move.tier), default=-1)
    before = others[index - 1][2] if index > 0 else -1
    if index == len(others):
        span: list[str] = [move.rung_id]
        start = top + 1
    elif others[index][2] - before > 1:
        return (Placement(move.rung_id, others[index][2] - 1),)
    else:
        span = [move.rung_id, *(one[0] for one in others[index:])]
        start = top + 1
    if start + len(span) - 1 > POSITION_CEILING:
        msg = "the level has used every position a step can hold"
        raise GateError(msg)
    return tuple(Placement(rung_id, start + offset) for offset, rung_id in enumerate(span))


def levels_left_empty(live: Sequence[Placed], change: MatrixChange) -> tuple[Tier, ...]:
    """The levels that hold a step now and would hold none after `change`, in ladder order.

    Only a retirement and a move take a step out of a level; an edit and an addition leave every
    level's steps where they are. See `A_LEVEL_KEEPS_AT_LEAST_ONE_STEP`.
    """
    if not isinstance(change, RungRetirement | RungMove):
        return ()
    found = next((one for one in live if one[0] == change.rung_id), None)
    if found is None or (isinstance(change, RungMove) and change.tier is found[1]):
        return ()
    if any(one[1] is found[1] and one[0] != change.rung_id for one in live):
        return ()
    return tuple(tier for tier in TIER_LADDER if tier is found[1])


def overlaid(
    rungs: Sequence[LadderRung], change: MatrixChange, *, new_rung_id: str
) -> tuple[LadderRung, ...]:
    """The live rungs with `change` applied, as the ladder would stand if it took traffic.

    `new_rung_id` names an added rung for the attempt rows of the trial; an edit keeps its own,
    and a move's rungs keep theirs, because the rows they name exist while the trial runs.
    """
    if isinstance(change, RungRetirement):
        if not any(one.rung_id == change.rung_id for one in rungs):
            msg = "the retirement names no live rung"
            raise GateError(msg)
        return tuple(one for one in rungs if one.rung_id != change.rung_id)
    if isinstance(change, RungMove):
        placed = {
            one.rung_id: one.position
            for one in placements([(one.rung_id, one.tier, one.position) for one in rungs], change)
        }
        return tuple(
            replace(one, tier=change.tier, position=placed[one.rung_id])
            if one.rung_id in placed
            else one
            for one in rungs
        )
    if isinstance(change, RungEdit):
        found = [one for one in rungs if one.rung_id == change.rung_id]
        if not found:
            msg = "the edit names no live rung"
            raise GateError(msg)
        return tuple(
            replace(
                one,
                attempts=change.attempts,
                timeout_seconds=change.timeout_seconds,
                max_concurrency=change.max_concurrency,
                enabled=change.enabled,
            )
            if one.rung_id == change.rung_id
            else one
            for one in rungs
        )
    added = LadderRung(
        rung_id=new_rung_id,
        tier=change.tier,
        position=next_position(rungs, change.tier),
        deployment_id=change.deployment_id,
        provider=change.provider,
        model=change.model,
        attempts=change.attempts,
        timeout_seconds=change.timeout_seconds,
        max_concurrency=change.max_concurrency,
        enabled=True,
    )
    return (*rungs, added)


def golden_result(question: GoldenQuestion, *, answered: bool, detail: str) -> CaseResult:
    """One golden question's outcome as a scored case.

    A question that must be answered is a quality case and passes when it was answered. One that
    must be refused is a permission case and passes when it was not: answering it is showing
    somebody something the question was written to prove they cannot see.
    """
    if question.expect is GoldenExpectation.REFUSE:
        return CaseResult(
            question_id=question.question_id,
            severity=Severity.PERMISSION,
            passed=not answered,
            reason="" if not answered else "answered a question it must refuse",
        )
    return CaseResult(
        question_id=question.question_id,
        severity=Severity.QUALITY,
        passed=answered,
        reason="" if answered else f"did not answer: {detail or 'no answer came back'}",
    )


def canary_results(findings: Sequence[CanaryFinding]) -> tuple[CaseResult, ...]:
    """The canary run as permission cases: one passing case, or one failing case per finding.

    A finding is recorded by its kind alone. See the module docstring.
    """
    if not findings:
        return (CaseResult(question_id=CANARY_CASE, severity=Severity.PERMISSION, passed=True),)
    return tuple(
        CaseResult(
            question_id=f"{CANARY_CASE}-{number}",
            severity=Severity.PERMISSION,
            passed=False,
            reason=f"a permission canary found {one.kind.value}; the alert names where",
        )
        for number, one in enumerate(findings, start=1)
    )


@dataclass(frozen=True)
class GateVerdict:
    """Whether the change may take traffic, and every failing case and reason if not."""

    may_apply: bool
    failing: tuple[tuple[str, str], ...]
    reasons: tuple[str, ...]
    #: The share of must-answer questions answered, or None with no such question.
    quality_share: float | None


def gate_verdict(
    golden: Sequence[CaseResult],
    canaries: Sequence[CaseResult],
    *,
    baseline: Baseline | None,
) -> GateVerdict:
    """The verdict over both halves, scored by `brain.ops.evaluation.score`."""
    results = (*golden, *canaries)
    verdict = score(results, baseline=baseline)
    reasons = list(verdict.reasons)
    if not golden:
        reasons.insert(0, NO_GOLDEN_QUESTIONS)
    has_quality = any(one.severity is Severity.QUALITY for one in golden)
    failing = tuple((one.question_id, one.reason) for one in results if not one.passed)
    return GateVerdict(
        may_apply=not reasons,
        failing=failing,
        reasons=tuple(reasons),
        quality_share=verdict.quality_share if has_quality else None,
    )
