"""A partial answer that says what is missing without saying which half of the rule hid it.

The property this file is mostly about is that a subtask refused for entitlement and a
subtask that timed out produce the same gap. It is asserted by building both and comparing
the values, rather than by checking that some particular word is absent, because a `reason`
field added later would pass a word check and fail an equality one.

The merge itself is driven from real `ValidatedResult`s, which cannot be constructed around
a value nothing checked, so "failure rather than merge input" is exercised as a type here
and as a constructor in the contract tests.

Task ids: M18.4.1, M18.4.2, M18.4.3
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from brain.core.entitlement import Capability
from brain.core.errors import Degraded
from brain.orchestration.contract import (
    FieldKind,
    FieldSpec,
    SubtaskContract,
    ValidatedResult,
    validated,
)
from brain.orchestration.merge import (
    Gap,
    GapCause,
    GapTrace,
    MergeError,
    SubtaskReport,
    merge,
    merge_gaps,
    merge_refusals,
)

NOW = datetime(2026, 9, 8, 4, 0, tzinfo=UTC)
NAME = Capability(value="read:client.name")

LEDGER = "Total the group ledger for this client"
HELPDESK = "Count the open helpdesk tickets"


def _contract(subtask_id: str) -> SubtaskContract:
    return SubtaskContract(
        subtask_id=subtask_id,
        objective="Report the open invoice position for this client",
        output=(FieldSpec(name="balance", kind=FieldKind.DECIMAL),),
        capabilities=(NAME,),
    )


def _result(subtask_id: str, balance: float = 12.5) -> ValidatedResult:
    return validated(_contract(subtask_id), {"balance": balance})


def _report(subtask_id: str, minor: int = 40) -> SubtaskReport:
    return SubtaskReport(subtask_id=subtask_id, minor=minor, seconds=3.0)


# ------------------------------------------------------------------ the gap (M18.4.3)
def test_a_refused_subtask_and_a_failed_one_produce_the_same_gap():
    """**The rule the whole module is built around.**

    Compared as values rather than by looking for a word, because a `reason` field added
    later would pass a word check and fail this one.

    Delete this and a run whose finance subtask was refused and whose helpdesk subtask timed
    out would tell the reader which was which, and the answer itself would separate DENIED
    from ABSENT in the one place nobody is watching."""
    refused = Gap(subtask_id="s-1", objective=LEDGER)
    failed = Gap(subtask_id="s-1", objective=LEDGER)

    assert refused == failed
    assert set(Gap.__dataclass_fields__) == {"subtask_id", "objective"}


def test_the_gap_type_has_no_field_a_cause_could_go_in():
    """The structural half, asked of the class rather than promised: a rule that lives in
    prose is defeated by somebody adding one field to make an error message more helpful,
    which is the most sympathetic possible route to this disclosure.

    Delete this and the constant above becomes a paragraph nobody enforces."""
    assert merge_gaps() == ()

    @dataclass(frozen=True)
    class Helpful:
        subtask_id: str
        objective: str
        reason: str

    findings = merge_gaps(surface=(Helpful,), gap_type=Helpful)
    assert any("Helpful.reason" in one for one in findings)


def test_the_notice_names_only_objectives_the_asker_may_be_told_exist():
    """A planner proposes subtasks from the question, and a broad question produces a plan
    that reaches into places the asker may not know exist.

    Delete this and a gap would disclose the group ledger to somebody who never knew there
    was one, in the answer rather than in an error."""
    answer = merge(
        "r-1",
        (_result("s-1"),),
        (_report("s-1"),),
        gaps=(
            Gap(subtask_id="s-2", objective=LEDGER),
            Gap(subtask_id="s-3", objective=HELPDESK),
        ),
        traces=(
            GapTrace(subtask_id="s-2", cause=GapCause.REFUSED),
            GapTrace(subtask_id="s-3", cause=GapCause.TIMED_OUT),
        ),
    )

    notice = answer.notice(disclosable=frozenset({"s-3"}))

    assert HELPDESK in notice
    assert LEDGER not in notice


def test_the_notice_falls_back_to_the_sentence_an_unreachable_source_has_always_produced():
    """`brain.core.errors.Degraded.public_message` verbatim rather than a sentence of this
    module's own, so a gap whose shape is itself a disclosure is indistinguishable from a
    source being down.

    Delete this and the fallback could become "I could not complete part of this", which is
    a sentence only a refused subtask ever produces."""
    answer = merge(
        "r-1",
        (_result("s-1"),),
        (_report("s-1"),),
        gaps=(Gap(subtask_id="s-2", objective=LEDGER),),
        traces=(GapTrace(subtask_id="s-2", cause=GapCause.REFUSED),),
    )

    assert answer.notice(disclosable=frozenset()) == Degraded.public_message


def test_a_complete_answer_says_nothing_about_what_succeeded():
    """A reassurance that every part worked is the list of parts by another route, offered
    on every request.

    Delete this and a complete answer would enumerate its own subtasks, which is the
    catalogue the disclosable set exists to gate."""
    answer = merge("r-1", (_result("s-1"),), (_report("s-1"),))

    assert answer.is_complete
    assert answer.notice(disclosable=frozenset({"s-1"})) == ""


def test_the_trace_names_every_cause_and_is_a_separate_method():
    """Two audiences kept apart in the type, which is
    `brain.connectors.federation.PartialAnswer`'s split and is taken from it rather than
    invented. Two methods rather than one with a flag, because a flag defaults to whatever
    the first caller needed.

    Delete this and the cause could migrate into the notice, which is exactly the
    disclosure."""
    answer = merge(
        "r-1",
        (_result("s-1"),),
        (_report("s-1"),),
        gaps=(
            Gap(subtask_id="s-3", objective=HELPDESK),
            Gap(subtask_id="s-2", objective=LEDGER),
        ),
        traces=(
            GapTrace(subtask_id="s-3", cause=GapCause.TIMED_OUT, detail="connector"),
            GapTrace(subtask_id="s-2", cause=GapCause.REFUSED),
        ),
    )

    assert answer.trace_lines() == ("s-2: refused", "s-3: timed_out (connector)")


# ------------------------------------------------------------------ the merge (M18.4.1)
def test_merge_takes_validated_results_and_has_no_parameter_a_raw_mapping_arrives_through():
    """**Where "failure rather than merge input" is enforced.** The type cannot be built
    around a value nothing checked, so a result that did not satisfy its contract cannot be
    passed here at all.

    Asserted on the annotation as well as by use, because a signature widened to accept a
    mapping would still pass every behavioural test in this file.

    Delete this and the guarantee reduces to whoever calls the validator first."""
    parameters = inspect.signature(merge).parameters

    assert "ValidatedResult" in str(parameters["results"].annotation)
    assert not any("Mapping" in str(one.annotation) for one in parameters.values()), parameters


def test_a_merge_composes_the_values_keyed_by_subtask():
    """The positive half, and the reason the values are not flattened: two subtasks
    returning a field of the same name would overwrite one another, and which one won would
    depend on the order the children finished in.

    Delete this and every other test here is about refusals, so a merge that produced
    nothing would be green."""
    answer = merge(
        "r-1",
        (_result("s-1", 10.0), _result("s-2", 20.0)),
        (_report("s-1", 30), _report("s-2", 40)),
    )

    assert answer.values == {"s-1": {"balance": 10.0}, "s-2": {"balance": 20.0}}
    assert answer.is_complete


def test_a_subtask_both_merged_and_reported_missing_is_refused():
    """The refusal that produces a wrong answer rather than a confusing one: the values are
    in the merge and the notice says they are not, so the reader is told to go and ask about
    something they were already given.

    Delete this and an answer could contradict itself and still be sent."""
    refusals = merge_refusals(
        (_result("s-1"),),
        (_report("s-1"),),
        gaps=(Gap(subtask_id="s-1", objective=LEDGER),),
        traces=(GapTrace(subtask_id="s-1", cause=GapCause.REFUSED),),
    )

    assert any("both merged and reported as missing" in one for one in refusals)


def test_a_gap_with_no_recorded_cause_is_refused():
    """An auditor asking whether a subtask was refused or merely failed has nowhere to look.

    Delete this and the trace could be dropped for exactly the gaps somebody wanted no
    record of, which is the shape a deliberate omission takes."""
    refusals = merge_refusals(
        (_result("s-1"),),
        (_report("s-1"),),
        gaps=(Gap(subtask_id="s-2", objective=LEDGER),),
    )

    assert len(refusals) == 1
    assert "nothing records why" in refusals[0]


def test_a_recorded_cause_with_no_gap_is_refused():
    """**The half that fires.** An answer goes out looking complete while the trace knows
    otherwise, which is the silent version of a partial answer and the one a reader has no
    reason to question.

    Delete this and dropping a refused subtask from the answer entirely would be the tidiest
    way to handle it, which is what makes it dangerous."""
    refusals = merge_refusals(
        (_result("s-1"),),
        (_report("s-1"),),
        traces=(GapTrace(subtask_id="s-2", cause=GapCause.REFUSED),),
    )

    assert len(refusals) == 1
    assert "looking complete" in refusals[0]


def test_a_result_with_no_cost_line_and_a_cost_line_with_no_work_are_both_refused():
    """M18.4.2 asks for the cost of each subtask, so a run that quietly shows five of six
    lines has a total that does not equal the work; and a line for a subtask that neither
    answered nor is missing charges the run for work in no part of the answer.

    Delete this and the per-subtask figures could disagree with the plan in either
    direction, and the total would still look internally consistent."""
    missing_line = merge_refusals((_result("s-1"),), ())
    assert len(missing_line) == 1
    assert "no cost line" in missing_line[0]

    spare_line = merge_refusals((_result("s-1"),), (_report("s-1"), _report("s-9")))
    assert len(spare_line) == 1
    assert "neither a result nor a gap" in spare_line[0]


def test_merge_raises_rather_than_returning_a_misdescribed_answer():
    """`merge_refusals` exists so a caller assembling a partial run can ask before it
    commits, and `merge` refuses so a caller that did not ask cannot ship one.

    Delete this and the refusals become advisory, and the only caller that consults them is
    the one that already thought to."""
    with pytest.raises(MergeError, match="cannot be merged"):
        merge("r-1", (_result("s-1"),), ())


# ------------------------------------------------------------- cost and duration (M18.4.2)
def test_the_total_is_the_sum_of_the_rows_the_reader_is_shown():
    """A total computed from the rows cannot disagree with them, which is the difference
    between a total and a hidden count.

    Delete this and the total could become a field carried beside the rows, and the gap
    between the two would be the number of subtasks the reader was not shown."""
    answer = merge(
        "r-1",
        (_result("s-1"), _result("s-2")),
        (_report("s-1", 30), _report("s-2", 40)),
    )

    assert answer.total_minor == 70
    assert answer.total_minor == sum(one.minor for one in answer.reports)


def test_a_negative_cost_line_is_refused():
    """A negative figure subtracts from the run's total and makes the sum smaller than the
    parts, which is the one arithmetic a reader will not check.

    Delete this and a correction posted as a negative line would hide the cost of a
    subtask."""
    with pytest.raises(MergeError, match="negative figure"):
        SubtaskReport(subtask_id="s-1", minor=-1, seconds=1.0)


def test_a_gap_or_a_cost_line_naming_nothing_is_refused():
    """Two constructor refusals with one message each: a gap nobody can match to the plan
    and a cost line nobody can match to a subtask are both rows that exist and cannot be
    read.

    Delete this and an answer could carry an unattributable figure, and reconciling the
    total against the plan would be impossible."""
    with pytest.raises(MergeError, match="naming no subtask"):
        Gap(subtask_id=" ", objective=LEDGER)
    with pytest.raises(MergeError, match="states no objective"):
        Gap(subtask_id="s-1", objective="   ")
    with pytest.raises(MergeError, match="naming no subtask"):
        SubtaskReport(subtask_id="", minor=1, seconds=1.0)


def test_every_gap_cause_is_a_closed_vocabulary_member():
    """A free-text cause is where somebody eventually writes the value that was refused,
    which is `brain.gate.leash.CheckReason`'s argument for being closed.

    Delete this and the trace could carry prose, and the trace is the half that is
    retained."""
    assert {one.value for one in GapCause} == {
        "refused",
        "timed_out",
        "invalid_result",
        "not_admitted",
        "unreachable",
    }
