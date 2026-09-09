"""Both systems answering the same questions, and what a comparison period is allowed to decide.

A migration cuts over on somebody's judgement, and the point of running both systems side by
side is to replace that judgement with a measurement. It only replaces it if the measurement
was defined first.

**The criteria are agreed before the period starts, and this module refuses one that was
not.** A criterion written after the first week is a criterion fitted to the week: whoever
writes it has seen the disagreements, and the threshold that gets written is the one the
result already clears. That is not dishonesty, it is what anybody does when the number is in
front of them, which is why the rule is a refusal here rather than a note in a runbook. See
`A_THRESHOLD_WRITTEN_AFTER_THE_RESULT_IS_A_DESCRIPTION_OF_THE_RESULT`.

**A question only one system answered is not agreement, and it is not a disagreement
either.** It is the third outcome, and folding it into either of the others is how a
comparison period reports a result it did not measure. Folded into agreement, an old system
that has quietly stopped answering produces a perfect score; folded into disagreement, the
same outage reads as the new system being wrong about everything. `Comparison` therefore has
three verdicts and `agreement` counts only the pairs where both answered, while
`unanswered` is reported separately and on its own. See
`A_QUESTION_ONE_SYSTEM_DID_NOT_ANSWER_IS_NOT_A_QUESTION_THEY_AGREED_ON`.

**A disagreement is surfaced rather than counted.** `disagreements` returns the entries, not
a number, because the whole value of the log is which questions the two systems answered
differently: a count sends somebody to argue about a percentage and the entries send them to
read three answers. A count is available, and it is available as the thing a criterion is
measured against rather than as the thing a person reads.

**Every measure needs a criterion, and there are three of them.** A cutover agreed on the
question count alone is agreed without reference to whether anybody read the disagreements,
which is the one measure that says whether the comparison was done rather than merely run.
`cutover_gaps` reports a measure nobody set a threshold for as a gap in the agreement, not as
a criterion that passes by absence.

What was rejected. An expression language for criteria, so a client could write "agreement
above 95 percent excluding pricing questions". It is one afternoon to write and it moves the
argument from what the criteria should be to what the language can express, and the criteria
that matter here are three counts. Three measures with a direction and a threshold can be
read aloud in a meeting, which is where they have to be agreed.

Rejected too: storing the answers. The log records that two answers differed and the question
they were given, and nothing here holds either answer, because an answer from the old system
was produced under that system's permission model and this repository has one rule about
content like that, in `brain.migration.carry`. The reviewer reads both in the two systems.

Task ids: M37.1.3.1, M37.1.3.2, M37.1.3.3
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.migration.inventory import MigrationError


class ParallelError(MigrationError):
    """Raised when a comparison period would decide something it did not measure."""


# ------------------------------------------------------------------ written-down reasons
#: Why a criterion agreed after the period started is refused.
A_THRESHOLD_WRITTEN_AFTER_THE_RESULT_IS_A_DESCRIPTION_OF_THE_RESULT: Final = (
    "Whoever writes a cutover criterion in week two has seen week one, and the threshold "
    "that gets written is the one the result already clears. That is not dishonesty, it is "
    "what anybody does with the number in front of them, and it is why this is a refusal "
    "rather than a line in a runbook. The criteria are agreed in writing before the period "
    "starts, which is what M37.1.3.3 asks for, and the timestamps are what make that "
    "checkable afterwards by somebody who was not in the room."
)

#: Why a question only one system answered is its own outcome.
A_QUESTION_ONE_SYSTEM_DID_NOT_ANSWER_IS_NOT_A_QUESTION_THEY_AGREED_ON: Final = (
    "Folded into agreement, an old system that has quietly stopped answering produces a "
    "perfect score and the cutover is decided by an outage. Folded into disagreement, the "
    "same outage reads as the new system being wrong about everything and the cutover is "
    "postponed by one. Neither is a measurement, so it is a third verdict, counted "
    "separately and reported on its own."
)

#: Why an agreed period has an agreed end.
A_PARALLEL_RUN_NOBODY_ENDED_IS_NOT_A_PERIOD: Final = (
    "Two systems answering the same questions costs twice and confuses everybody who asks "
    "one of them, so it is a period with an end rather than an arrangement. A period running "
    "past its end with no decision is the finding: not that the criteria failed, which is a "
    "real answer, but that nobody looked."
)


class Verdict(enum.StrEnum):
    """What one question produced.

    Three, and the third is the one a two-valued log loses. See
    `A_QUESTION_ONE_SYSTEM_DID_NOT_ANSWER_IS_NOT_A_QUESTION_THEY_AGREED_ON`.
    """

    AGREED = "agreed"
    DIFFERED = "differed"
    ONLY_ONE_ANSWERED = "only one answered"


class Measure(enum.StrEnum):
    """The three things a comparison period produces a number for.

    Read against the M37.1.3.1 and M37.1.3.3 leaf sentences: the period is questions asked
    over an agreed span, and the criteria decide the cutover. Volume, duration, and whether
    anybody read the disagreements.
    """

    QUESTIONS_ASKED = "questions asked"
    DAYS_RUNNING = "days running"
    UNREVIEWED_DISAGREEMENTS = "unreviewed disagreements"


class Direction(enum.StrEnum):
    """Which side of the threshold passes."""

    AT_LEAST = "at least"
    AT_MOST = "at most"


@dataclass(frozen=True)
class Comparison:
    """One question put to both systems, and what came back.

    Neither answer is stored. See the module docstring: an answer from the old system was
    produced under that system's permission model, and `brain.migration.carry` is where this
    repository decided what happens to content like that.

    `reviewed_by` is empty until somebody has read both answers. It is a name rather than a
    flag because "reviewed" with nobody attached is the state a bulk update produces.
    """

    question: str
    asked_at: datetime
    verdict: Verdict
    reviewed_by: str = ""

    def __post_init__(self) -> None:
        if not self.question.strip():
            msg = "a comparison records no question, so nobody can go and look at it"
            raise ParallelError(msg)
        if self.reviewed_by and self.verdict is not Verdict.DIFFERED:
            msg = (
                f"{self.question!r} is marked reviewed and the two systems {self.verdict.value}; "
                "review is what happens to a disagreement"
            )
            raise ParallelError(msg)


@dataclass(frozen=True)
class Criterion:
    """One threshold, when it was agreed, and the argument for it."""

    measure: Measure
    direction: Direction
    threshold: int
    agreed_at: datetime
    because: str

    def __post_init__(self) -> None:
        if self.threshold < 0:
            msg = f"{self.measure.value} cannot be counted to {self.threshold}"
            raise ParallelError(msg)
        if not self.because.strip():
            msg = f"the {self.measure.value} threshold is {self.threshold} for no stated reason"
            raise ParallelError(msg)


@dataclass(frozen=True)
class Period:
    """An agreed span with both systems answering, and the criteria that end it."""

    started_at: datetime
    ends_at: datetime
    criteria: tuple[Criterion, ...]

    def __post_init__(self) -> None:
        if self.ends_at <= self.started_at:
            msg = (
                f"the period ends at {self.ends_at} and starts at {self.started_at}. "
                f"{A_PARALLEL_RUN_NOBODY_ENDED_IS_NOT_A_PERIOD}"
            )
            raise ParallelError(msg)
        for one in self.criteria:
            if one.agreed_at >= self.started_at:
                msg = (
                    f"the {one.measure.value} threshold was agreed at {one.agreed_at}, after "
                    f"the period started at {self.started_at}. "
                    f"{A_THRESHOLD_WRITTEN_AFTER_THE_RESULT_IS_A_DESCRIPTION_OF_THE_RESULT}"
                )
                raise ParallelError(msg)


# ------------------------------------------------------------------- reading the log
def disagreements(log: Sequence[Comparison]) -> tuple[Comparison, ...]:
    """The questions the two systems answered differently, in the order they were asked.

    The entries rather than a count. A count sends somebody to argue about a percentage; the
    entries send them to read three answers, which is what the period is for.
    """
    return tuple(one for one in log if one.verdict is Verdict.DIFFERED)


def unanswered(log: Sequence[Comparison]) -> tuple[Comparison, ...]:
    """The questions only one system answered, which are neither agreement nor disagreement."""
    return tuple(one for one in log if one.verdict is Verdict.ONLY_ONE_ANSWERED)


def unreviewed(log: Sequence[Comparison]) -> tuple[Comparison, ...]:
    """Disagreements nobody has read yet. The measure that says whether anybody looked."""
    return tuple(one for one in disagreements(log) if not one.reviewed_by.strip())


def measured(measure: Measure, log: Sequence[Comparison], *, period: Period, now: datetime) -> int:
    """What one measure stands at.

    `QUESTIONS_ASKED` counts the questions both systems answered, so a period padded with
    questions the old system did not answer does not clear a volume threshold. `DAYS_RUNNING`
    is measured to `now` and not to the agreed end, because the question a criterion asks is
    how long it has actually run.
    """
    if measure is Measure.QUESTIONS_ASKED:
        return sum(1 for one in log if one.verdict is not Verdict.ONLY_ONE_ANSWERED)
    if measure is Measure.DAYS_RUNNING:
        return max(0, (now - period.started_at).days)
    return len(unreviewed(log))


def unmet(period: Period, log: Sequence[Comparison], *, now: datetime) -> tuple[str, ...]:
    """Every criterion the period does not currently clear, in the order they were agreed."""
    findings: list[str] = []
    for one in period.criteria:
        stands = measured(one.measure, log, period=period, now=now)
        passes = (
            stands >= one.threshold
            if one.direction is Direction.AT_LEAST
            else stands <= one.threshold
        )
        if not passes:
            findings.append(
                f"{one.measure.value}: {stands}, and the agreed criterion is "
                f"{one.direction.value} {one.threshold}"
            )
    return tuple(findings)


def cutover_gaps(period: Period, log: Sequence[Comparison], *, now: datetime) -> tuple[str, ...]:
    """Everything between here and a cutover somebody can defend afterwards.

    A measure nobody set a threshold for is reported first, because it is a gap in the
    agreement rather than a result: a cutover agreed on the question count alone is agreed
    without reference to whether anybody read the disagreements.

    Running past the agreed end is a finding on its own, and it is not the same finding as a
    criterion that is unmet. An unmet criterion is a real answer, and this one says nobody
    looked.
    """
    covered = {one.measure for one in period.criteria}
    findings = [
        f"{one.value}: nothing was agreed about it before the period started"
        for one in Measure
        if one not in covered
    ]
    if now > period.ends_at:
        findings.append(
            f"the agreed period ended at {period.ends_at} and both systems are still "
            f"answering. {A_PARALLEL_RUN_NOBODY_ENDED_IS_NOT_A_PERIOD}"
        )
    findings.extend(unmet(period, log, now=now))
    return tuple(findings)


def may_cut_over(period: Period, log: Sequence[Comparison], *, now: datetime) -> bool:
    """Whether every agreed criterion is met and every measure was agreed on.

    Deliberately not "no disagreements". A period that ends with disagreements everybody has
    read and decided about is a period that did its job, and refusing to cut over until two
    systems agree on everything is refusing to cut over.
    """
    return not cutover_gaps(period, log, now=now)
