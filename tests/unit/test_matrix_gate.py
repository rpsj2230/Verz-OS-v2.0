"""The matrix gate: a change tried on a copy of the ladder, scored, and applied or held.

The decisions are driven directly; the run is driven through the real answer lane with a real
executor over recording transports, so "through the gate" is the lane a person's question meets.

Task ids: M5.6.2
"""

from __future__ import annotations

import asyncio

import pytest

from brain.core.entitlement import EntitlementSet
from brain.models.routing import Tier
from brain.ops.canaries import CanaryFinding, Finding
from brain.ops.canary_run import CanaryRun
from brain.ops.evaluation import Baseline, Severity
from brain.ops.matrix_gate import (
    A_GATE_THAT_ASKED_NOTHING_HAS_PASSED_NOTHING,
    NO_GOLDEN_QUESTIONS,
    GateError,
    GateVerdict,
    GoldenQuestion,
    RungAddition,
    RungEdit,
    canary_results,
    gate_verdict,
    golden_result,
    overlaid,
)
from brain.ops.matrix_gate_run import LaneInputs, run_gate
from brain.tables.model_registry import GoldenExpectation
from tests.unit.test_answer_lane import ACME, CLIENTS, Rows, readers_for
from tests.unit.test_model_calls import Ladder, Log, Scripted, executor, ok, rung
from tests.unit.test_model_lane import CALLER, NOW, VISIBLE, Passages, completion

ANSWER = GoldenQuestion(
    question_id="q-answer",
    question="how much annual leave do we get",
    asked_as="p_priya",
    expect=GoldenExpectation.ANSWER,
)
REFUSE = GoldenQuestion(
    question_id="q-refuse",
    question="how much annual leave do we get",
    asked_as="p_nobody",
    expect=GoldenExpectation.REFUSE,
)


# ------------------------------------------------------------------------ the decisions
def test_an_edit_changes_only_its_own_rung_and_an_addition_goes_last_in_its_tier() -> None:
    """The copy the gate tries. Delete this and a trial can change a rung nobody edited, or put
    a new rung ahead of the primary."""
    rungs = (rung("anthropic"), rung("moonshot", position=1), rung("openai", tier=Tier.HEAVY))

    edited = overlaid(
        rungs,
        RungEdit(
            rung_id="main-1", attempts=3, timeout_seconds=9.0, max_concurrency=4, enabled=False
        ),
        new_rung_id="new",
    )
    added = overlaid(
        rungs,
        RungAddition(
            tier=Tier.MAIN,
            provider="deepseek",
            model="deepseek-chat",
            attempts=1,
            timeout_seconds=20.0,
            max_concurrency=2,
        ),
        new_rung_id="new",
    )

    assert edited[0] == rungs[0] and edited[2] == rungs[2]
    assert (edited[1].attempts, edited[1].enabled) == (3, False)
    assert added[-1].rung_id == "new"
    assert (added[-1].tier, added[-1].position) == (Tier.MAIN, 2)
    assert added[-1].deployment_id == "deepseek-deepseek-chat"
    with pytest.raises(GateError):
        overlaid(
            rungs,
            RungEdit(
                rung_id="gone", attempts=1, timeout_seconds=1.0, max_concurrency=1, enabled=True
            ),
            new_rung_id="new",
        )


def test_a_must_refuse_question_is_a_permission_case_and_a_must_answer_one_is_quality() -> None:
    """Delete this and a question written to prove somebody cannot see a thing is averaged in
    with answer quality, where one failure is a rounding error."""
    assert golden_result(REFUSE, answered=True, detail="").severity is Severity.PERMISSION
    assert golden_result(REFUSE, answered=True, detail="").passed is False
    assert golden_result(REFUSE, answered=False, detail="absent").passed is True
    assert golden_result(ANSWER, answered=False, detail="absent").severity is Severity.QUALITY
    missed = golden_result(ANSWER, answered=False, detail="absent")
    assert missed.reason == "did not answer: absent"


def test_a_canary_finding_holds_the_change_and_is_recorded_by_its_kind_alone() -> None:
    """Delete this and the field and the asker a canary names can land in a row every matrix
    reader sees, or a finding can pass."""
    finding = CanaryFinding(
        kind=next(iter(Finding)), asker="p_priya", question_id="rule-1", subject="client.salary"
    )

    (case,) = canary_results((finding,))
    verdict = gate_verdict(
        (golden_result(ANSWER, answered=True, detail=""),), (case,), baseline=None
    )

    assert verdict.may_apply is False
    assert "client.salary" not in case.reason and "p_priya" not in case.reason
    assert canary_results(())[0].passed is True


def test_a_permission_failure_holds_the_change_whatever_quality_scored() -> None:
    """Delete this and a change that answers a must-refuse question is applied because every
    other question was answered."""
    verdict = gate_verdict(
        (
            golden_result(ANSWER, answered=True, detail=""),
            golden_result(REFUSE, answered=True, detail=""),
        ),
        canary_results(()),
        baseline=None,
    )

    assert verdict.may_apply is False
    assert ("q-refuse", "answered a question it must refuse") in verdict.failing


def test_a_fall_against_the_last_applied_share_holds_the_change_even_above_the_floor() -> None:
    """A regression is measured against what the last applied change scored. Delete this and a
    change that answers fewer questions than the ladder did is applied while above the floor."""
    nine_of_ten = tuple(
        golden_result(
            GoldenQuestion(
                question_id=f"q{n}", question="q", asked_as="p", expect=GoldenExpectation.ANSWER
            ),
            answered=n != 0,
            detail="absent",
        )
        for n in range(10)
    )

    held = gate_verdict(nine_of_ten, canary_results(()), baseline=Baseline(quality_share=1.0))
    fresh = gate_verdict(nine_of_ten, canary_results(()), baseline=None)

    assert held.may_apply is False
    assert fresh.may_apply is True
    assert held.quality_share == pytest.approx(0.9)


def test_a_gate_with_no_golden_questions_holds_the_change_and_says_to_record_some() -> None:
    """`A_GATE_THAT_ASKED_NOTHING_HAS_PASSED_NOTHING`. Delete this and an install with no golden
    questions changes its matrix unchecked while the screen says the gate passed."""
    verdict = gate_verdict((), canary_results(()), baseline=None)

    assert verdict.may_apply is False
    assert verdict.reasons[0] == NO_GOLDEN_QUESTIONS
    assert "golden questions" in A_GATE_THAT_ASKED_NOTHING_HAS_PASSED_NOTHING


# ----------------------------------------------------------------------- through the lane
def reach_of(principal_id: str) -> EntitlementSet:
    return (
        CALLER
        if principal_id == CALLER.principal_id
        else EntitlementSet(principal_id=principal_id, grants=())
    )


def run(change: RungEdit, transport: Scripted) -> tuple[GateVerdict, Log]:
    calls, log = executor(Ladder((rung("anthropic"),)), {"anthropic": transport})

    async def reach(principal_id: str) -> EntitlementSet:
        return reach_of(principal_id)

    async def canaries() -> CanaryRun:
        return CanaryRun(findings=(), rules_asked=())

    verdict = asyncio.run(
        run_gate(
            change,
            calls=calls,
            questions=(
                GoldenQuestion(
                    question_id="q-answer",
                    question=ANSWER.question,
                    asked_as=CALLER.principal_id,
                    expect=GoldenExpectation.ANSWER,
                ),
                REFUSE,
            ),
            reach_of=reach,
            inputs=LaneInputs(
                rules=(),
                readers=readers_for(Rows(ACME)),
                policies={"client": CLIENTS.policy()},
                search=Passages(VISIBLE),
            ),
            canaries=canaries,
            baseline=None,
            now=NOW,
            new_rung_id="11111111-1111-1111-1111-111111111111",
        )
    )
    return verdict, log


def test_a_change_that_keeps_the_ladder_answering_passes_through_the_real_lane() -> None:
    """M5.6.2 end to end: the must-answer question is answered by a model through the changed
    ladder, the must-refuse one is refused at a reach that reads nothing, the canaries are clean,
    and the change may be applied.

    Delete this and a gate that holds everything passes every test below."""
    transport = Scripted(completion())
    verdict, log = run(
        RungEdit(
            rung_id="main-0", attempts=1, timeout_seconds=20.0, max_concurrency=2, enabled=True
        ),
        transport,
    )

    assert verdict.may_apply is True
    assert [one.timeout_seconds for one in transport.sent] == [20.0]
    assert [row["categories"] for row in log.rows.values()] == [
        ("document_passages", "golden_question")
    ]


def test_a_change_that_stops_the_ladder_answering_is_held_with_the_failing_question_shown() -> None:
    """M5.6.2's regression: taking the only rung out of rotation leaves the must-answer question
    unanswered, so the change is held with that question's id and reason.

    Delete this and a change that silences the ladder is applied and found by the next person to
    ask."""
    transport = Scripted(ok())
    verdict, _ = run(
        RungEdit(
            rung_id="main-0", attempts=1, timeout_seconds=12.0, max_concurrency=2, enabled=False
        ),
        transport,
    )

    assert verdict.may_apply is False
    cases = dict(verdict.failing)
    assert set(cases) == {"q-answer"}
    assert cases["q-answer"].startswith("did not answer")
    assert transport.sent == []
