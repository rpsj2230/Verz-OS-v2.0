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

Scope: pure. Questions, answers, findings and the baseline are parameters.

Task ids: M5.6.2
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Final

from brain.models.assembly import LadderRung
from brain.models.routing import Tier
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
    "no golden questions are recorded, so nothing checked that the changed ladder still answers. "
    "Add golden questions on the Routing screen and save the change again."
)

#: The case id every canary finding is recorded under, numbered.
CANARY_CASE: Final = "canary"


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


MatrixChange = RungEdit | RungAddition


class GateError(ValueError):
    """A change the ladder cannot hold, such as an edit naming no live rung."""


def next_position(rungs: Sequence[LadderRung], tier: Tier) -> int:
    """The position after the last live rung of `tier`: an added rung is the last fallback."""
    positions = [one.position for one in rungs if one.tier is tier]
    return max(positions) + 1 if positions else 0


def overlaid(
    rungs: Sequence[LadderRung], change: MatrixChange, *, new_rung_id: str
) -> tuple[LadderRung, ...]:
    """The live rungs with `change` applied, as the ladder would stand if it took traffic.

    `new_rung_id` names an added rung for the attempt rows of the trial; an edit keeps its own.
    """
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
