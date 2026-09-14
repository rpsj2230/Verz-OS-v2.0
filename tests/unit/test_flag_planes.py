"""Wrong sources is not a wrong answer, and a report keeps the two halves apart.

Every test here is about one figure that used to be two bugs. An answer built from the wrong
documents and an answer that misread the right ones were both `WRONG_FACT`, so whoever read
the count tuned the half they owned. The tests hold the two reasons apart, hold each reason in
one half, and hold the report to returning every half whether or not anything was filed in it.

Task ids: M34.2.2.2
"""

from __future__ import annotations

from datetime import UTC, datetime

from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Scope
from brain.gate.compose import new_trace_ref
from brain.ops.evaluation import Severity
from brain.ops.feedback import (
    FLAG_CAPABILITY,
    FaultPlane,
    Flag,
    FlagReason,
    by_plane,
    flag_answer,
    plane_of,
    severity_of,
)

#: Far from any wall clock, because nothing here is about the present and a flag's retention
#: is not what is being tested.
AT = datetime(2099, 1, 1, tzinfo=UTC)
REF = new_trace_ref()


def _flag(reason: FlagReason, question_id: str = "G01a") -> Flag:
    return Flag(
        trace_ref=REF,
        question_id=question_id,
        department="web",
        flagged_by="u_lead",
        reason=reason,
        at=AT,
    )


def test_wrong_sources_is_its_own_reason_and_lands_in_a_different_half_from_wrong_fact() -> None:
    """**The leaf.** Two reasons with two spellings, one a retrieval bug and one a reasoning
    bug.

    Delete this and `WRONG_SOURCES` can be folded back into `WRONG_FACT`, or mapped to the
    same half, and the one figure that was two bugs comes back with every other test green."""
    assert len({reason.value for reason in FlagReason}) == len(FlagReason)
    assert "wrong_sources" in {reason.value for reason in FlagReason}
    assert plane_of(FlagReason.WRONG_SOURCES) is not plane_of(FlagReason.WRONG_FACT)
    assert plane_of(FlagReason.WRONG_SOURCES) is FaultPlane.RETRIEVAL
    assert plane_of(FlagReason.WRONG_FACT) is FaultPlane.REASONING


def test_every_reason_is_assigned_to_the_half_it_is_a_bug_in() -> None:
    """The whole mapping, stated as a literal table outside the module, so a member moved
    between halves fails here rather than being compared against itself.

    Delete this and `STALE` can drift into reasoning, which sends somebody to rewrite prompts
    over a figure that was simply read too long ago."""
    assert {reason: plane_of(reason) for reason in FlagReason} == {
        FlagReason.WRONG_SOURCES: FaultPlane.RETRIEVAL,
        FlagReason.STALE: FaultPlane.RETRIEVAL,
        FlagReason.WRONG_FACT: FaultPlane.REASONING,
        FlagReason.INCOMPLETE: FaultPlane.REASONING,
        FlagReason.SHOULD_HAVE_REFUSED: FaultPlane.PERMISSION,
        FlagReason.REFUSED_WRONGLY: FaultPlane.PERMISSION,
    }


def test_a_report_tells_retrieval_flags_from_reasoning_flags() -> None:
    """One flag of every reason goes in, and each comes out in its own half, once.

    Delete this and `by_plane` can put every flag in one half, or drop the ones it cannot
    place, and the report reads as a separation while measuring nothing."""
    flags = [_flag(reason, question_id=f"q_{reason.value}") for reason in FlagReason]

    report = by_plane(flags)

    assert {one.reason for one in report[FaultPlane.RETRIEVAL]} == {
        FlagReason.WRONG_SOURCES,
        FlagReason.STALE,
    }
    assert {one.reason for one in report[FaultPlane.REASONING]} == {
        FlagReason.WRONG_FACT,
        FlagReason.INCOMPLETE,
    }
    assert {one.reason for one in report[FaultPlane.PERMISSION]} == {
        FlagReason.SHOULD_HAVE_REFUSED,
        FlagReason.REFUSED_WRONGLY,
    }
    assert sorted(one.question_id for half in report.values() for one in half) == sorted(
        one.question_id for one in flags
    ), "every flag handed in comes out exactly once"


def test_every_half_is_in_the_report_when_nothing_was_filed_in_it() -> None:
    """A report with keys that come and go has a shape that depends on the data, and a
    missing half reads as "not measured" to whatever consumes it.

    Delete this and a quiet week for reasoning bugs looks like a report that forgot to ask."""
    report = by_plane([_flag(FlagReason.WRONG_SOURCES)])

    assert set(report) == set(FaultPlane)
    assert report[FaultPlane.REASONING] == ()
    assert report[FaultPlane.PERMISSION] == ()


def test_a_lead_files_wrong_sources_and_it_is_scored_as_a_quality_failure() -> None:
    """The positive path through the existing flag, carrying the new reason unchanged, and
    the severity it is scored at.

    Delete this and `WRONG_SOURCES` can exist in the vocabulary while `severity_of` refuses
    it or scores it as a permission failure, which puts a zero threshold on a ranking bug."""
    lead = EntitlementSet(
        principal_id="u_lead",
        grants=(Grant(capability=FLAG_CAPABILITY, scope=Scope.department("web")),),
    )

    filed = flag_answer(
        trace_ref=REF,
        question_id="G01a",
        department="web",
        flagger=lead,
        reason=FlagReason.WRONG_SOURCES,
        now=AT,
    )

    assert filed.reason is FlagReason.WRONG_SOURCES
    assert severity_of(FlagReason.WRONG_SOURCES) is Severity.QUALITY
    assert filed.severity() is Severity.QUALITY
