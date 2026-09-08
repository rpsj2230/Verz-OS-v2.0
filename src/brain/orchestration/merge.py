"""Putting the children's answers back together, and saying honestly what is missing.

Three things happen here and the third is the one with a rule on it.

**The final answer is written from validated inputs and there is nowhere to pass anything
else.** `merge` takes `brain.orchestration.contract.ValidatedResult`, whose constructor
re-runs the contract check, so a result that did not satisfy its contract cannot reach this
module at all. That is what makes M18.1.3's "failure rather than merge input" a shape
rather than a habit: there is no parameter here a raw mapping could arrive through, and no
branch that copes with one. The values are typed because prose was refused upstream, which
is what lets `brain.core.redaction.compute_mask` run over them field by field on the way
out.

**Cost and duration are surfaced per subtask, and that is not a disclosure.** Every figure
here is about the asker's own run: what their question cost and how long each part of it
took. `brain.console.agent_automations.OwnerNotice` carries a count of the owner's own
failures on the same reasoning. What would be a disclosure is a total that differs from the
sum of what is shown, and there is no field for one; `hidden_count_fields` is imported from
`brain.ops.jobs` rather than restated, because a count of what a reader was not shown is one
rule and it already has an implementation.

**A gap reads the same whether the subtask failed or was refused, and this is the rule the
whole module is built around.** A run whose finance subtask was refused for entitlement and
whose helpdesk subtask timed out must produce two gaps a reader cannot tell apart.
Otherwise the answer discloses by its own shape: "I could not reach the helpdesk" beside "I
am not allowed to tell you about finance" is `brain.core.errors`' DENIED and ABSENT
separated in the one place nobody was watching, and the reader learns that a finance record
exists for this client. So `Gap` has two fields, neither of which is a cause, and the cause
lives in `GapTrace`, which is read by an auditor. `brain.connectors.federation.PartialAnswer`
makes exactly this split for an unreachable source and the shape is taken from it rather
than invented; the fallback sentence is `brain.core.errors.Degraded.public_message`
verbatim, so a gap the asker may not be told the shape of produces the message an
unreachable source has always produced. See `A_REFUSED_SUBTASK_AND_A_FAILED_ONE_READ_ALIKE`.

**Naming an objective is itself a disclosure, so it is gated on the same set the catalogue
already decided.** A planner proposes subtasks from the asker's question, and most of them
name things the asker already named. Not all: a broad question produces a plan that reaches
into places the asker may not know exist, and reporting "I could not do: check the group
ledger" tells them there is a group ledger. `notice` therefore names an objective only when
its subtask is in `disclosable`, which is the caller's own projection of what this asker may
be told exists, and says the fixed sentence otherwise.

**Every gap has a trace and every trace has a gap.** Both directions, and the second is the
one that fires: a cause recorded for a subtask that is not reported as missing is a run
whose answer went out looking complete while the trace knew otherwise.
`brain.console.agent_automations.registry_gaps` checks its own two halves the same way and
for the same reason.

Rejected: a `reason` field on `Gap` with a rule that callers must not fill it in for a
refusal. The rule is the thing that gets forgotten, and the field would be filled in by
somebody making an error message more helpful, which is the most sympathetic possible route
to the disclosure this module exists to prevent.

Rejected: omitting a refused subtask from the answer entirely, so there is no gap to read.
It is the tidiest version and it is worse: an answer that silently covers less than the
question asked is an answer the reader believes is complete, and the whole value of a stated
gap is that they know to ask somebody. Absence and denial are indistinguishable; absence and
completeness must not be.

Rejected: a merged answer that composes the values into one flat mapping. Two subtasks
returning a field of the same name would silently overwrite one another, and which one won
would depend on the order the children happened to finish in.

Scope: domain logic. Nothing here reads a clock, opens a connection or renders anything for
a channel; `brain.core.redaction` masks what this produces and `brain.channels` renders it.

Task ids: M18.4.1, M18.4.2, M18.4.3
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from brain.core.errors import Degraded
from brain.ops.jobs import hidden_count_fields
from brain.orchestration.contract import ValidatedResult

# ------------------------------------------------------------------ written-down reasons
#: Why a gap carries no cause, and where the cause goes instead.
A_REFUSED_SUBTASK_AND_A_FAILED_ONE_READ_ALIKE: Final = (
    "A run whose finance subtask was refused for entitlement and whose helpdesk subtask "
    "timed out has to produce two gaps a reader cannot tell apart. Anything else separates "
    "DENIED from ABSENT in the one place nobody is watching: I could not reach the helpdesk "
    "beside I am not allowed to tell you about finance discloses that a finance record "
    "exists for this client, and it does so in the answer rather than in an error. So Gap "
    "has no field a cause could go in, the cause goes to GapTrace, and GapTrace is read by "
    "an auditor. brain.connectors.federation.PartialAnswer splits the same two audiences "
    "the same way for an unreachable source."
)

#: Why naming a missing subtask is gated on what the asker may already know exists.
NAMING_AN_OBJECTIVE_IS_A_DISCLOSURE: Final = (
    "A planner proposes subtasks from the question, and a broad question produces a plan "
    "that reaches into places the asker may not know exist. Reporting that the group ledger "
    "check could not be completed tells them there is a group ledger, which is a fact they "
    "did not have and did not ask for. An objective is therefore named only when its "
    "subtask is one this asker may be told exists, and the fallback is the sentence an "
    "unreachable source has always produced, so the two are indistinguishable."
)

#: Why an answer says it is incomplete rather than quietly covering less.
A_SILENT_GAP_IS_AN_ANSWER_THE_READER_BELIEVES: Final = (
    "Dropping a refused subtask from the answer with no gap is the tidiest version and the "
    "most dangerous: the reader gets something that reads as a complete answer to the "
    "question they asked and has no reason to ask anybody else. Absence and denial are "
    "indistinguishable to a person by design; absence and completeness must not be, because "
    "the whole cost of the first rule is paid back by the reader knowing when to go and ask."
)


class MergeError(Exception):
    """A merged answer that would say something untrue about what it contains.

    Outside the `brain.core.errors` taxonomy, like the rest of this package: nobody asking a
    question ever sees one. What a person is told is `MergedAnswer.notice`.
    """


# --------------------------------------------------------------- cost and duration (M18.4.2)
@dataclass(frozen=True)
class SubtaskReport:
    """What one subtask cost and how long it took, as the asker is shown it.

    Their own run, so a figure here is their own spend and not a fact about anybody else.
    What would be a disclosure is a total that does not equal the sum of the rows, and there
    is no field for one: `merge_gaps` asks `brain.ops.jobs.hidden_count_fields` of this type
    rather than restating the rule.
    """

    subtask_id: str
    #: Minor currency units, as `brain.ops.spend.Estimate.minor` counts them.
    minor: int
    seconds: float

    def __post_init__(self) -> None:
        if not self.subtask_id.strip():
            msg = "a cost line naming no subtask cannot be read against the plan it came from"
            raise MergeError(msg)
        if self.minor < 0 or self.seconds < 0:
            msg = (
                f"subtask {self.subtask_id!r} reports {self.minor} minor units in "
                f"{self.seconds} seconds; a negative figure subtracts from the run's total "
                "and makes the sum smaller than the parts"
            )
            raise MergeError(msg)


# --------------------------------------------------------------- the gap (M18.4.3)
class GapCause(enum.StrEnum):
    """Why a subtask produced nothing. Recorded, and never shown to the asker.

    A closed vocabulary rather than prose, for the reason
    `brain.gate.leash.CheckReason` is closed: this is written down, and a free-text cause is
    where somebody eventually writes the value that was refused.
    """

    #: The child's reach did not cover what its objective needed.
    REFUSED = "refused"
    #: It ran and did not finish in time.
    TIMED_OUT = "timed_out"
    #: It returned something its contract does not admit.
    INVALID_RESULT = "invalid_result"
    #: It could not start: no room, or a halt.
    NOT_ADMITTED = "not_admitted"
    #: Something under it was unreachable.
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class Gap:
    """One subtask whose result is not in the answer, as the asker may be told about it.

    Two fields and neither is a cause. See `A_REFUSED_SUBTASK_AND_A_FAILED_ONE_READ_ALIKE`:
    a refused subtask and a failed one produce the same value here, and the only thing that
    varies between them is what an auditor reads in `GapTrace`.

    The objective is carried because it is what a reader needs in order to know what to go
    and ask for, and whether it is *shown* is `MergedAnswer.notice`'s decision against the
    disclosable set rather than this type's.
    """

    subtask_id: str
    objective: str

    def __post_init__(self) -> None:
        if not self.subtask_id.strip():
            msg = "a gap naming no subtask cannot be matched to the plan or to its trace"
            raise MergeError(msg)
        if not self.objective.strip():
            msg = (
                f"the gap for {self.subtask_id!r} states no objective, so a reader told "
                "about it learns only that something is missing"
            )
            raise MergeError(msg)


@dataclass(frozen=True)
class GapTrace:
    """Why one subtask produced nothing. For an auditor, never for the asker.

    Safe to hold a cause for the reason `brain.connectors.federation.PartialAnswer.trace_lines`
    is safe: nothing in this module can put a `GapTrace` into what a person is shown.
    `MergedAnswer.notice` reads `gaps` and `MergedAnswer.trace_lines` reads these, and the
    two are separate methods rather than one with a flag, because a flag defaults to
    whatever the first caller needed.
    """

    subtask_id: str
    cause: GapCause
    #: Free text for an auditor. Never rendered to an asker by anything here.
    detail: str = ""


# --------------------------------------------------------------- the merge (M18.4.1)
@dataclass(frozen=True)
class MergedAnswer:
    """The final answer's inputs, what each part cost, and what is missing from it.

    `values` is keyed by subtask rather than flattened, so two subtasks returning a field of
    the same name do not overwrite one another and which one won does not depend on the
    order the children finished in.

    There is no field here holding rendered text. What a person reads is composed downstream,
    after `brain.core.redaction.compute_mask` has run over these typed values, which is the
    whole reason `brain.orchestration.contract` refuses prose.
    """

    run_id: str
    #: Subtask id to the validated values it returned.
    values: Mapping[str, Mapping[str, object]]
    #: What each part cost and how long it took, in plan order.
    reports: tuple[SubtaskReport, ...]
    #: What is missing, in the shape the asker may be told about.
    gaps: tuple[Gap, ...] = ()
    #: Why, for an auditor.
    traces: tuple[GapTrace, ...] = ()

    @property
    def is_complete(self) -> bool:
        return not self.gaps

    @property
    def total_minor(self) -> int:
        """What the whole run cost, as the sum of the rows the asker is shown.

        A sum of what is displayed and not a figure carried alongside it, which is the
        difference between a total and a hidden count: this cannot disagree with the rows
        above it, because it is computed from them. `brain.ops.jobs.dead_letter_summary`
        counts after filtering for the same reason.
        """
        return sum(one.minor for one in self.reports)

    def notice(self, *, disclosable: frozenset[str]) -> str:
        """What the asker is told about what is missing (M18.4.3).

        Names an objective only when its subtask is one this asker may be told exists, and
        says `brain.core.errors.Degraded.public_message` verbatim otherwise, so a gap whose
        shape is itself a disclosure produces the sentence an unreachable source has always
        produced. See `NAMING_AN_OBJECTIVE_IS_A_DISCLOSURE`.

        Says nothing at all when the answer is complete. A reassurance that every part
        succeeded is the list of parts by another route, offered on every request, which is
        the argument `PartialAnswer.notice` makes about naming sources that worked.
        """
        if not self.gaps:
            return ""
        nameable = tuple(
            sorted(one.objective for one in self.gaps if one.subtask_id in disclosable)
        )
        if not nameable:
            return Degraded.public_message
        listed = "; ".join(nameable)
        return f"This answer is missing what these would have added: {listed}."

    def trace_lines(self) -> tuple[str, ...]:
        """The full list, for an auditor. Names every gap and every cause.

        Sorted, so two readings of one run produce the same list and a trace can be compared
        with the same run replayed.
        """
        return tuple(
            f"{one.subtask_id}: {one.cause}" + (f" ({one.detail})" if one.detail else "")
            for one in sorted(self.traces, key=lambda one: (one.subtask_id, one.cause))
        )


def merge(
    run_id: str,
    results: Sequence[ValidatedResult],
    reports: Sequence[SubtaskReport],
    *,
    gaps: Sequence[Gap] = (),
    traces: Sequence[GapTrace] = (),
) -> MergedAnswer:
    """Write the final answer's inputs from validated results (M18.4.1).

    Takes `ValidatedResult` and has no parameter a raw mapping could arrive through, which
    is where M18.1.3's "failure rather than merge input" is enforced: a result that did not
    satisfy its contract cannot be constructed, so it cannot be passed here.

    Refuses every shape in which the answer would say something untrue about itself, and
    refuses them all at once rather than the first, matching
    `brain.ops.queue.queue_url_refusals`. The checks are in `merge_refusals` so that a
    caller assembling a partial run can ask before it commits to an answer.
    """
    refusals = merge_refusals(results, reports, gaps=gaps, traces=traces)
    if refusals:
        msg = f"run {run_id!r} cannot be merged: {'; '.join(refusals)}"
        raise MergeError(msg)
    return MergedAnswer(
        run_id=run_id,
        values={one.contract.subtask_id: dict(one.values) for one in results},
        reports=tuple(reports),
        gaps=tuple(gaps),
        traces=tuple(traces),
    )


def merge_refusals(
    results: Sequence[ValidatedResult],
    reports: Sequence[SubtaskReport],
    *,
    gaps: Sequence[Gap] = (),
    traces: Sequence[GapTrace] = (),
) -> tuple[str, ...]:
    """Every way this merge would produce an answer that misdescribes itself.

    Five checks. A subtask both answered and missing is the one that produces a wrong answer
    rather than a confusing one: the values are in the merge and the notice says they are
    not, so the reader is told to go and ask about something they were already given.

    A gap with no trace and a trace with no gap are the two halves of one rule, and the
    second is the one that fires. A cause recorded for a subtask nothing reports as missing
    is a run whose answer went out looking complete while the trace knew otherwise, which is
    exactly `A_SILENT_GAP_IS_AN_ANSWER_THE_READER_BELIEVES`.

    A missing cost line is a refusal rather than a blank, because M18.4.2 asks for the cost
    of each subtask and a run that quietly shows five of six lines has a total that does not
    equal the work.
    """
    findings: list[str] = []
    answered = {one.contract.subtask_id for one in results}
    missing = {one.subtask_id for one in gaps}
    traced = {one.subtask_id for one in traces}
    reported = {one.subtask_id for one in reports}

    findings.extend(
        f"{one!r} is both merged and reported as missing, so the answer contains it and "
        "tells the reader to go and ask somebody for it"
        for one in sorted(answered & missing)
    )
    findings.extend(
        f"{one!r} is reported as missing and nothing records why, so an auditor asking "
        "whether it was refused or merely failed has nowhere to look"
        for one in sorted(missing - traced)
    )
    findings.extend(
        f"{one!r} has a recorded cause and is not reported as missing, so the answer goes "
        f"out looking complete. {A_SILENT_GAP_IS_AN_ANSWER_THE_READER_BELIEVES}"
        for one in sorted(traced - missing)
    )
    findings.extend(
        f"{one!r} produced a result and no cost line, so what the run cost is smaller than "
        "what the run did"
        for one in sorted(answered - reported)
    )
    findings.extend(
        f"{one!r} has a cost line and neither a result nor a gap, so the run is charged for "
        "work that is in no part of the answer"
        for one in sorted(reported - (answered | missing))
    )
    return tuple(findings)


# ------------------------------------------------------------------------- the diagnostic
#: Field names on `Gap` that would tell an asker why something is missing. See
#: `A_REFUSED_SUBTASK_AND_A_FAILED_ONE_READ_ALIKE`.
NAMES_THAT_WOULD_BE_A_CAUSE: Final[frozenset[str]] = frozenset(
    {"cause", "reason", "denied", "refused", "error", "detail", "outcome", "why"}
)

#: The types the asker is handed. Listed rather than discovered, following
#: `brain.ops.jobs.OPERATOR_SURFACE`.
ASKER_SURFACE: Final[tuple[type, ...]] = (Gap, SubtaskReport, MergedAnswer)


def merge_gaps(
    *,
    surface: Sequence[type] = ASKER_SURFACE,
    gap_type: type = Gap,
) -> tuple[str, ...]:
    """Everything about this surface that would disclose more than the answer does.

    Takes its inputs rather than reading the module's own constants, for the reason
    `brain.ops.starter.starter_gaps` records: a diagnostic that can only be run against the
    healthy tree has nothing to report on today's data, so switching off any of its
    refusals changes nothing observable and every one of them survives a mutation.

    Asks `brain.ops.jobs.hidden_count_fields` rather than carrying a second list of names
    that would be a count. One rule, one implementation, and the module that owns it already
    has the list.
    """
    findings: list[str] = []
    findings.extend(
        f"{found} would tell a reader how much they were not shown"
        for found in hidden_count_fields(surface)
    )
    declared: Mapping[str, Any] = getattr(gap_type, "__dataclass_fields__", {})
    findings.extend(
        f"{gap_type.__name__}.{name} would tell an asker why something is missing. "
        f"{A_REFUSED_SUBTASK_AND_A_FAILED_ONE_READ_ALIKE}"
        for name in declared
        if name in NAMES_THAT_WOULD_BE_A_CAUSE
    )
    return tuple(findings)
