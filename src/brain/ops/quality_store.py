"""The quality stores: flags, captured cases, readings, annotations, golden scores, candidates,
examples and the decisions about them. The one writer for `0219`'s eight tables.

`brain.ops.feedback`, `brain.ops.sampling`, `brain.ops.evaluation` and `brain.memory.tiers` each
decide something about answer quality and hold nothing, on the split `brain.ops.limits` makes:
this holds the statements and decides nothing they did not. Every function takes a session already
in the caller's transaction and sets `app.principal_id` to the person it writes as, which `0219`'s
insert policies hold the writer column to.

**A candidate is opened and never applied.** `open_candidates` writes rows about an agent and
touches no table that configures one: the return value is the rows opened, and there is no
function here that takes a candidate to a change. What a candidate becomes is a person's decision,
written by `decide` as a `TierDecision` row. See
`A_FAILED_CASE_OPENS_A_CANDIDATE_AND_NEVER_CHANGES_THE_AGENT`.

**Standing is read, not stored.** A candidate is pending until a decision row names it, and an
example is in effect only from a `promoted` decision at tier two, once its `effective_from` has
passed. So nothing here is updated, and the decision's author, who agreed and when it takes effect
are one row. See `AN_EXAMPLE_INFLUENCES_RUNS_ONLY_THROUGH_THE_TIER_ITS_CHANGE_WOULD_REACH`.

**A regression is read between two releases and says nothing about one.**
`regression_since_previous` compares the newest release's golden scores with the one before it,
by when each last ran, and the comparison is two figures side by side with the permission
failures counted and never turned into a percentage, for
`brain.ops.evaluation.A_PERCENTAGE_IS_THE_WRONG_INSTRUMENT_FOR_A_PERMISSION`.

**Two tiers, two functions.** The automated tier's rows are read by `automated_day` and the
human's by `annotated_day`, and nothing here takes both, which is `brain.ops.sampling`'s rule held
at the store.

Task ids: M28.3.1, M28.3.2, M28.3.3, M28.4.1, M28.5.3, M16.6.7, M16.7.14
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Final

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from brain.ops.canaries import Finding
from brain.ops.evaluation import CaseResult, Severity
from brain.ops.feedback import CapturedCase, Flag, FlagReason
from brain.ops.sampling import (
    AutomatedReading,
    DailySample,
    HumanAnnotation,
    annotation_report,
    automated_report,
    draw,
)
from brain.tables.quality import (
    AnswerFlagRow,
    CandidateSource,
    EvaluationCandidateRow,
    GoldenScoreRow,
    ItemKind,
    PositiveExampleRow,
    QualityAnnotationRow,
    QualityReadingRow,
    RegressionCaseRow,
    TierDecisionRow,
    TierDecisionWord,
)

# ------------------------------------------------------------------ written-down reasons
#: Why opening a candidate writes nothing to an agent.
A_FAILED_CASE_OPENS_A_CANDIDATE_AND_NEVER_CHANGES_THE_AGENT: Final = (
    "A case that failed is evidence about an agent, and what to do about it is a person's "
    "decision. So a failure writes one candidate row naming the agent and the case, there is no "
    "column on it that holds a change, and no function here takes one to an agent's configuration: "
    "the review queue is where it waits."
)

#: Why an example is in effect only through the tier its change would reach.
AN_EXAMPLE_INFLUENCES_RUNS_ONLY_THROUGH_THE_TIER_ITS_CHANGE_WOULD_REACH: Final = (
    "An output somebody approved unchanged is a positive example, and teaching an agent from it "
    "changes what it says without changing what anybody may see, which is tier two's reach "
    "(brain.memory.tiers): proposed, then promoted by a person. So the example is recorded at once "
    "and is in effect only from the instant a promotion row names, which is never the instant it "
    "was recorded."
)

#: How many rows a read of one list takes.
MOST_ROWS_READ: Final = 500

#: The seed the daily sample is drawn with. Published, because the draw is only checkable if it is.
DAILY_SEED: Final = "quality-daily"

#: The tiers a decision is made at, in `brain.memory.tiers.Tier`'s numbers.
PROMOTED_TIER: Final = 2
GATED_TIER: Final = 3


async def _as(session: AsyncSession, principal: str) -> None:
    await session.execute(
        text("SELECT set_config('app.principal_id', :who, true)"), {"who": principal}
    )


# --------------------------------------------------------------------------------- flags
@dataclass(frozen=True)
class StoredFlag:
    """A flag as read back, with the id a capture is made against."""

    id: uuid.UUID
    flag: Flag
    captured: bool


async def file_flag(session: AsyncSession, flag: Flag) -> uuid.UUID:
    """Keep one flag, in the flagger's own name. A second flag by one lead on one answer is the
    first, because the table refuses it, and this returns the first's id."""
    await _as(session, flag.flagged_by)
    existing = (
        await session.execute(
            select(AnswerFlagRow.id).where(
                AnswerFlagRow.trace_ref == flag.trace_ref,
                AnswerFlagRow.flagged_by == flag.flagged_by,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    made = AnswerFlagRow(
        trace_ref=flag.trace_ref,
        question_id=flag.question_id,
        department=flag.department,
        flagged_by=flag.flagged_by,
        reason=flag.reason.value,
        flagged_at=flag.at,
    )
    session.add(made)
    await session.flush()
    return made.id


async def flags(session: AsyncSession) -> list[StoredFlag]:
    """Every flag, newest first, with whether a case was captured from it."""
    rows = (
        await session.execute(
            select(AnswerFlagRow, RegressionCaseRow.id)
            .join(RegressionCaseRow, RegressionCaseRow.flag_id == AnswerFlagRow.id, isouter=True)
            .order_by(AnswerFlagRow.flagged_at.desc(), AnswerFlagRow.id)
            .limit(MOST_ROWS_READ)
        )
    ).all()
    return [
        StoredFlag(
            id=row.id,
            flag=Flag(
                trace_ref=row.trace_ref,
                question_id=row.question_id,
                department=row.department,
                flagged_by=row.flagged_by,
                reason=FlagReason(row.reason),
                at=row.flagged_at,
            ),
            captured=case_id is not None,
        )
        for row, case_id in ((one[0], one[1]) for one in rows)
    ]


def case_document(case: CapturedCase) -> dict[str, object]:
    """A captured case as the document `ops.regression_case` holds: names and words, no value."""
    return {
        "question": case.question,
        "held": [one.value for one in case.held],
        "answering_fields": list(case.answering_fields),
        "locked_fields": list(case.locked_fields),
        "mocked_from": case.mocked_from,
        "fault": case.fault.value,
        "origin_trace_ref": case.origin_trace_ref,
        "origin_question_id": case.origin_question_id,
    }


async def keep_case(
    session: AsyncSession, flag_id: uuid.UUID, case: CapturedCase, *, by: str
) -> uuid.UUID:
    """Keep the case a flag became, once. A second capture of one flag is the first."""
    await _as(session, by)
    existing = (
        await session.execute(
            select(RegressionCaseRow.id).where(RegressionCaseRow.flag_id == flag_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    made = RegressionCaseRow(flag_id=flag_id, document=case_document(case), captured_by=by)
    session.add(made)
    await session.flush()
    return made.id


async def kept_cases(session: AsyncSession) -> list[dict[str, Any]]:
    """Every case kept, as its document, oldest first, which is the order a run asks them in."""
    rows = (
        await session.execute(
            select(RegressionCaseRow.document)
            .order_by(RegressionCaseRow.captured_at, RegressionCaseRow.id)
            .limit(MOST_ROWS_READ)
        )
    ).scalars()
    return [dict(one) for one in rows]


# --------------------------------------------------------------- the two tiers, apart
async def record_reading(session: AsyncSession, reading: AutomatedReading, *, by: str) -> None:
    """Keep what the mechanical checks saw on one request. A request is read once."""
    await _as(session, by)
    if (
        await session.execute(
            select(QualityReadingRow.id).where(QualityReadingRow.request_id == reading.request_id)
        )
    ).scalar_one_or_none() is not None:
        return
    session.add(
        QualityReadingRow(
            request_id=reading.request_id,
            passed=reading.passed,
            fault=None if reading.fault is None else reading.fault.value,
            recorded_by=by,
        )
    )
    await session.flush()


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


async def automated_day(session: AsyncSession, day: date) -> list[AutomatedReading]:
    """The automated tier's readings taken on one day. Never read beside the human tier's."""
    start, end = _day_bounds(day)
    rows = (
        await session.execute(
            select(QualityReadingRow)
            .where(QualityReadingRow.read_at >= start, QualityReadingRow.read_at < end)
            .order_by(QualityReadingRow.request_id)
            .limit(MOST_ROWS_READ * 20)
        )
    ).scalars()
    return [
        AutomatedReading(
            request_id=one.request_id,
            passed=one.passed,
            fault=None if one.fault is None else Finding(one.fault),
        )
        for one in rows
    ]


async def sample_for(session: AsyncSession, day: date) -> DailySample:
    """One day's annotation queue, drawn from the requests read that day, reproducibly."""
    ids = [one.request_id for one in await automated_day(session, day)]
    return draw(seed=DAILY_SEED, day=day, request_ids=ids)


async def annotate(session: AsyncSession, annotation: HumanAnnotation, *, day: date) -> bool:
    """Keep one judgement of one sampled answer, in the annotator's own name.

    Refused (False) for a request not in that day's sample, so the human tier is only ever about
    what was drawn for it, and for one already annotated.
    """
    await _as(session, annotation.annotator)
    sample = await sample_for(session, day)
    if annotation.request_id not in sample.request_ids:
        return False
    if (
        await session.execute(
            select(QualityAnnotationRow.id).where(
                QualityAnnotationRow.request_id == annotation.request_id
            )
        )
    ).scalar_one_or_none() is not None:
        return False
    session.add(
        QualityAnnotationRow(
            day=day,
            request_id=annotation.request_id,
            annotator=annotation.annotator,
            sound=annotation.sound,
            fault=None if annotation.fault is None else annotation.fault.value,
        )
    )
    await session.flush()
    return True


async def annotated_day(session: AsyncSession, day: date) -> list[HumanAnnotation]:
    """The human tier's annotations of one day's sample."""
    rows = (
        await session.execute(
            select(QualityAnnotationRow)
            .where(QualityAnnotationRow.day == day)
            .order_by(QualityAnnotationRow.request_id)
        )
    ).scalars()
    return [
        HumanAnnotation(
            request_id=one.request_id,
            annotator=one.annotator,
            sound=one.sound,
            fault=None if one.fault is None else FlagReason(one.fault),
        )
        for one in rows
    ]


@dataclass(frozen=True)
class DayReport:
    """One day's two reports, kept as two. There is no field that holds both as one figure."""

    automated: tuple[str, ...]
    annotated: tuple[str, ...]


async def day_report(session: AsyncSession, day: date) -> DayReport:
    """The two tiers' reports for one day, each from its own rows with its own coverage line."""
    return DayReport(
        automated=automated_report(await automated_day(session, day)),
        annotated=annotation_report(await annotated_day(session, day)),
    )


# ------------------------------------------------------------------------------ golden
async def record_golden(
    session: AsyncSession,
    *,
    release: str,
    persona: str,
    results: Sequence[CaseResult],
    by: str,
) -> int:
    """Keep each result of one golden run, with the release it ran on. A result is kept once per
    release, question and persona, and the number newly kept is returned."""
    await _as(session, by)
    kept = 0
    for one in results:
        if (
            await session.execute(
                select(GoldenScoreRow.id).where(
                    GoldenScoreRow.release == release,
                    GoldenScoreRow.question_id == one.question_id,
                    GoldenScoreRow.persona == persona,
                )
            )
        ).scalar_one_or_none() is not None:
            continue
        session.add(
            GoldenScoreRow(
                release=release,
                question_id=one.question_id,
                persona=persona,
                severity=one.severity.value,
                passed=one.passed,
                reason=one.reason[:64],
                ran_by=by,
            )
        )
        kept += 1
    await session.flush()
    return kept


@dataclass(frozen=True)
class ReleaseScore:
    """One release's golden figures. Permission failures are a count and quality is a share."""

    release: str
    ran_at: datetime
    permission_failures: int
    quality_passed: int
    quality_total: int

    @property
    def quality_share(self) -> float | None:
        """None for a release that asked no quality question: nought of nothing is not a share."""
        return None if self.quality_total == 0 else self.quality_passed / self.quality_total


@dataclass(frozen=True)
class Regression:
    """The newest release against the one before it, and whether it did worse."""

    latest: ReleaseScore
    previous: ReleaseScore
    regressed: bool


async def release_scores(session: AsyncSession) -> list[ReleaseScore]:
    """Each release's figures, newest first by when it last ran."""
    rows = (
        await session.execute(
            select(
                GoldenScoreRow.release,
                func.max(GoldenScoreRow.ran_at),
                func.count().filter(
                    GoldenScoreRow.severity == Severity.PERMISSION.value,
                    GoldenScoreRow.passed.is_(False),
                ),
                func.count().filter(
                    GoldenScoreRow.severity == Severity.QUALITY.value,
                    GoldenScoreRow.passed.is_(True),
                ),
                func.count().filter(GoldenScoreRow.severity == Severity.QUALITY.value),
            )
            .group_by(GoldenScoreRow.release)
            .order_by(func.max(GoldenScoreRow.ran_at).desc(), GoldenScoreRow.release)
        )
    ).all()
    return [
        ReleaseScore(
            release=row[0],
            ran_at=row[1],
            permission_failures=row[2],
            quality_passed=row[3],
            quality_total=row[4],
        )
        for row in rows
    ]


def regressed(latest: ReleaseScore, previous: ReleaseScore) -> bool:
    """Whether the later release did worse: more permission failures, or a lower quality share.

    Permission failures first and as a count, because one is a regression whatever the share did.
    A release with no quality question compares on permission alone.
    """
    if latest.permission_failures > previous.permission_failures:
        return True
    now, before = latest.quality_share, previous.quality_share
    return now is not None and before is not None and now < before


async def regression_since_previous(session: AsyncSession) -> Regression | None:
    """The newest release against the previous one, or None when fewer than two have been scored."""
    scored = await release_scores(session)
    if len(scored) < 2:
        return None
    latest, previous = scored[0], scored[1]
    return Regression(latest=latest, previous=previous, regressed=regressed(latest, previous))


# ------------------------------------------------------------- candidates and examples
async def open_candidates(
    session: AsyncSession,
    *,
    agent_id: str,
    source: CandidateSource,
    failed_case_refs: Sequence[str],
    by: str,
) -> list[uuid.UUID]:
    """Open one candidate per failed case against an agent. See
    `A_FAILED_CASE_OPENS_A_CANDIDATE_AND_NEVER_CHANGES_THE_AGENT`.

    A case that already has a candidate against this agent is not opened again.
    """
    await _as(session, by)
    opened: list[uuid.UUID] = []
    for ref in dict.fromkeys(failed_case_refs):
        if (
            await session.execute(
                select(EvaluationCandidateRow.id).where(
                    EvaluationCandidateRow.agent_id == agent_id,
                    EvaluationCandidateRow.source == source.value,
                    EvaluationCandidateRow.case_ref == ref,
                )
            )
        ).scalar_one_or_none() is not None:
            continue
        made = EvaluationCandidateRow(
            agent_id=agent_id, source=source.value, case_ref=ref, opened_by=by
        )
        session.add(made)
        await session.flush()
        opened.append(made.id)
    return opened


@dataclass(frozen=True)
class Candidate:
    """A failed case waiting for a person, or decided."""

    id: uuid.UUID
    agent_id: str
    source: CandidateSource
    case_ref: str
    #: `pending`, or the word of the newest decision about it.
    standing: str


async def _newest_decisions(
    session: AsyncSession, kind: ItemKind, refs: Sequence[str]
) -> dict[str, TierDecisionRow]:
    if not refs:
        return {}
    rows = (
        (
            await session.execute(
                select(TierDecisionRow)
                .where(TierDecisionRow.item_kind == kind.value, TierDecisionRow.item_ref.in_(refs))
                .order_by(TierDecisionRow.item_ref, TierDecisionRow.decided_at.desc())
                .distinct(TierDecisionRow.item_ref)
            )
        )
        .scalars()
        .all()
    )
    return {one.item_ref: one for one in rows}


async def candidates(session: AsyncSession, *, agent_id: str | None = None) -> list[Candidate]:
    """Candidates, newest first, each with its standing read off its newest decision."""
    query = select(EvaluationCandidateRow).order_by(
        EvaluationCandidateRow.opened_at.desc(), EvaluationCandidateRow.id
    )
    if agent_id is not None:
        query = query.where(EvaluationCandidateRow.agent_id == agent_id)
    rows = (await session.execute(query.limit(MOST_ROWS_READ))).scalars().all()
    decided = await _newest_decisions(session, ItemKind.CANDIDATE, [str(one.id) for one in rows])
    return [
        Candidate(
            id=one.id,
            agent_id=one.agent_id,
            source=CandidateSource(one.source),
            case_ref=one.case_ref,
            standing=decided[str(one.id)].decision if str(one.id) in decided else "pending",
        )
        for one in rows
    ]


async def record_example(
    session: AsyncSession, *, agent_id: str, skill: str | None, artefact_ref: str, by: str
) -> uuid.UUID:
    """Keep an output approved unchanged as a positive example for its agent and skill.

    Recorded at once and in effect only once promoted. An output is an example once.
    """
    await _as(session, by)
    existing = (
        await session.execute(
            select(PositiveExampleRow.id).where(
                PositiveExampleRow.agent_id == agent_id,
                PositiveExampleRow.artefact_ref == artefact_ref,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    made = PositiveExampleRow(
        agent_id=agent_id, skill=skill, artefact_ref=artefact_ref, approved_by=by
    )
    session.add(made)
    await session.flush()
    return made.id


async def examples_in_effect(
    session: AsyncSession, agent_id: str, *, now: datetime
) -> list[PositiveExampleRow]:
    """The examples a run of this agent may use at `now`: promoted, and past the instant the
    promotion takes effect. See
    `AN_EXAMPLE_INFLUENCES_RUNS_ONLY_THROUGH_THE_TIER_ITS_CHANGE_WOULD_REACH`."""
    rows = (
        (
            await session.execute(
                select(PositiveExampleRow)
                .where(PositiveExampleRow.agent_id == agent_id)
                .order_by(PositiveExampleRow.approved_at, PositiveExampleRow.id)
                .limit(MOST_ROWS_READ)
            )
        )
        .scalars()
        .all()
    )
    decided = await _newest_decisions(session, ItemKind.EXAMPLE, [str(one.id) for one in rows])
    return [
        one
        for one in rows
        if str(one.id) in decided
        and decided[str(one.id)].decision == TierDecisionWord.PROMOTED.value
        and decided[str(one.id)].effective_from <= now
    ]


class DecisionError(Exception):
    """A decision that the tier it names does not allow."""


async def decide(
    session: AsyncSession,
    *,
    kind: ItemKind,
    ref: str,
    tier: int,
    decision: TierDecisionWord,
    decided_by: str,
    agreed_by: Sequence[str] = (),
    at: datetime,
    effective_from: datetime | None = None,
) -> uuid.UUID:
    """Record who agreed to a change that needed a person, and when it takes effect.

    The decider is among those who agreed whether or not they are listed. Takes effect at `at`
    unless a later instant is given, and never before it. Tier two promotes and tier three
    approves or declines, which the table holds as well.
    """
    if tier not in (PROMOTED_TIER, GATED_TIER):
        msg = f"tier {tier} is not decided by a person"
        raise DecisionError(msg)
    if (tier == PROMOTED_TIER) != (decision is TierDecisionWord.PROMOTED) and (
        tier == PROMOTED_TIER or decision is TierDecisionWord.PROMOTED
    ):
        msg = f"{decision.value} is not a decision at tier {tier}"
        raise DecisionError(msg)
    await _as(session, decided_by)
    everyone = sorted({decided_by, *agreed_by})
    made = TierDecisionRow(
        item_kind=kind.value,
        item_ref=ref,
        tier=tier,
        decision=decision.value,
        decided_by=decided_by,
        agreed_by=everyone,
        decided_at=at,
        effective_from=at if effective_from is None else max(effective_from, at),
    )
    session.add(made)
    await session.flush()
    return made.id
