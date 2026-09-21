"""The matrix gate run on an install: golden questions through the answer lane, then the canaries.

`brain.ops.matrix_gate` decides; this asks. Each golden question is put to
`brain.gate.answer.answer_lane` as the principal it names, at that principal's reach from the one
resolver, with the model step's executor planning from the changed copy of the ladder
(`ModelCalls.trying`). That is "through the gate" in M5.6.2's words: the projection, the row read
at the asker's reach, the redaction and the abstention all run, and only the ladder differs from
what a person's question would meet. Then `brain.ops.canary_run.ask_every_reach` asks the
canaries over every reach the install holds.

**Nothing is recorded in anybody's name.** The lane is handed no recorders, as the canaries'
lane is, so a golden question is on neither the question ledger nor anybody's adoption figure.
The model calls are real and metered on attempt rows under their own trace, recorded as
`golden_question` in the data categories, so the provider register counts what the gate sent. A
trial rung that is not on the ladder yet has no row, so its attempts are not written, and that is
said in the attempt log's warning rather than invented.

**A golden question the lane could not answer for a fault is a question it did not answer.** The
exception's name is the reason; its text is not kept, for `brain.credential_routes`' reason.

Task ids: M5.6.2
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

import structlog
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain.api_routes import field_policies, row_readers
from brain.core.entitlement import EntitlementSet
from brain.core.field_policy import FieldPolicy
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.gate.answer import answer_lane
from brain.gate.context import Channel
from brain.gate.entitlement_store import StoredEntitlements
from brain.gate.fast_lane import FastPathRule, RowReader
from brain.gate.finish import Origin
from brain.gate.model_lane import ModelLane, PassageSearch
from brain.models.calls import ModelCalls
from brain.models.disclosure import DataCategory
from brain.ops.canary_run import (
    CanaryRun,
    ask_every_reach,
    minted_value,
    reaches_on_this_install,
)
from brain.ops.evaluation import Baseline, CaseResult, Severity
from brain.ops.matrix_gate import (
    CANARY_CASE,
    GateVerdict,
    GoldenQuestion,
    MatrixChange,
    canary_results,
    gate_verdict,
    golden_result,
    overlaid,
)
from brain.ops.model_service import ModelService
from brain.ops.trace_sink import CountingTraceSink
from brain.tables.model_registry import (
    ChangeStatus,
    GoldenExpectation,
    GoldenQuestionRow,
    RoutingChangeRow,
)
from brain.tools.registry import ToolRegistry

log = structlog.get_logger(__name__)

#: What a golden question's origin is called. Not a person: the gate asks as a reach.
GOLDEN_ASKER_NAME = "Golden question"


@dataclass(frozen=True)
class LaneInputs:
    """What the answer route hands the lane, as this process holds it."""

    rules: Sequence[FastPathRule]
    readers: Mapping[tuple[str, str], RowReader]
    policies: Mapping[str, FieldPolicy]
    search: PassageSearch | None


async def ask_golden(
    question: GoldenQuestion,
    *,
    reach: EntitlementSet,
    calls: ModelCalls,
    inputs: LaneInputs,
    now: datetime,
) -> tuple[bool, str]:
    """Whether the lane answered this question at this reach, and why not when it did not."""
    origin = Origin(
        # A trace of its own per question, so each question's attempt rows form their own chain.
        trace_id=f"golden-{uuid.uuid4().hex}",
        principal=Principal(
            id=reach.principal_id,
            kind=PrincipalKind.SERVICE,
            employment=Employment.SERVICE,
            display_name=GOLDEN_ASKER_NAME,
        ),
        channel=Channel.SCHEDULER,
    )
    lane = (
        None
        if inputs.search is None
        else ModelLane(
            search=inputs.search, model=calls, question_category=DataCategory.GOLDEN_QUESTION
        )
    )
    try:
        answered = await answer_lane(
            question.question,
            origin=origin,
            recorders=(),
            rules=inputs.rules,
            readers=inputs.readers,
            entitlement=reach,
            policies=inputs.policies,
            reachable_sources=(),
            sink=CountingTraceSink(),
            now=now,
            clock=lambda: now,
            model=lane,
        )
    except Exception as exc:
        return False, f"the lane raised {type(exc).__name__}"
    if answered.composed is not None:
        return True, ""
    reason = "no answer" if answered.abstention is None else answered.abstention.reason.value
    return False, reason


async def run_gate(
    change: MatrixChange,
    *,
    calls: ModelCalls,
    questions: Sequence[GoldenQuestion],
    reach_of: Callable[[str], Awaitable[EntitlementSet]],
    inputs: LaneInputs,
    canaries: Callable[[], Awaitable[CanaryRun]],
    baseline: Baseline | None,
    now: datetime,
    new_rung_id: str,
) -> GateVerdict:
    """Ask every golden question through the changed ladder, run the canaries, and decide."""
    trial = calls.trying(lambda rungs: overlaid(rungs, change, new_rung_id=new_rung_id))
    golden: list[CaseResult] = []
    for question in questions:
        reach = await reach_of(question.asked_as)
        answered, detail = await ask_golden(
            question, reach=reach, calls=trial, inputs=inputs, now=now
        )
        golden.append(golden_result(question, answered=answered, detail=detail))
    try:
        run = await canaries()
        found = canary_results(run.findings)
    except Exception as exc:
        # A canary run that could not finish holds the change: nothing says the install is clean.
        log.warning("matrix_gate.canaries_unfinished", error=type(exc).__name__)
        found = (
            CaseResult(
                question_id=CANARY_CASE,
                severity=Severity.PERMISSION,
                passed=False,
                reason=f"the canaries could not finish: {type(exc).__name__}",
            ),
        )
    verdict = gate_verdict(golden, found, baseline=baseline)
    log.info(
        "matrix_gate.decided",
        may_apply=verdict.may_apply,
        questions=len(questions),
        failing=len(verdict.failing),
    )
    return verdict


# ------------------------------------------------------------------------ the install


#: The most golden questions one change is asked. Each is a model call a person waits on while
#: the Routing screen saves, so the bound is what keeps a save to minutes rather than an hour.
MAX_GOLDEN_QUESTIONS = 25


class MatrixGate(Protocol):
    """What the Routing screen's writes ask before a change takes traffic."""

    async def decide(self, change: MatrixChange, *, now: datetime, new_rung_id: str) -> GateVerdict:
        """Run the gate for `change` and say whether it may be applied."""
        ...


class GateUnavailableError(RuntimeError):
    """The process holds nothing the gate can ask through: no database, model or registry."""


def live_golden_questions() -> Select[tuple[GoldenQuestionRow]]:
    """The live golden questions, oldest first, bounded. `deleted_at` tested here as well."""
    return (
        select(GoldenQuestionRow)
        .where(GoldenQuestionRow.deleted_at.is_(None))
        .order_by(GoldenQuestionRow.created_at, GoldenQuestionRow.id)
        .limit(MAX_GOLDEN_QUESTIONS)
    )


def last_applied_share() -> Select[tuple[Decimal | None]]:
    """The quality share the most recent applied change recorded: the next change's baseline."""
    return (
        select(RoutingChangeRow.quality_share)
        .where(
            RoutingChangeRow.status == ChangeStatus.APPLIED.value,
            RoutingChangeRow.quality_share.is_not(None),
        )
        .order_by(RoutingChangeRow.decided_at.desc())
        .limit(1)
    )


def golden_of(row: GoldenQuestionRow) -> GoldenQuestion:
    """One stored question, as the gate asks it."""
    return GoldenQuestion(
        question_id=str(row.id),
        question=row.question,
        asked_as=row.asked_as,
        expect=GoldenExpectation(row.expect),
    )


class InstallMatrixGate:
    """`MatrixGate` over what this process's lifespan built: the database, the models, the tools.

    Read from the application's state at each change rather than captured at start, because the
    rules and the registry are rebuilt while a process runs and a gate asking yesterday's rules
    would judge a change against a lane nobody meets any more.
    """

    def __init__(self, state: Any) -> None:
        self._state = state

    async def decide(self, change: MatrixChange, *, now: datetime, new_rung_id: str) -> GateVerdict:
        state = self._state
        sessions = getattr(state, "db_sessions", None)
        models = getattr(state, "models", None)
        registry = getattr(state, "tools", None)
        if (
            not isinstance(sessions, async_sessionmaker)
            or not isinstance(models, ModelService)
            or not isinstance(registry, ToolRegistry)
        ):
            raise GateUnavailableError
        rules = tuple(getattr(state, "fast_path_rules", ()))
        inputs = LaneInputs(
            rules=rules,
            readers=row_readers(registry),
            policies=field_policies(registry),
            search=getattr(state, "passage_search", None),
        )
        async with sessions() as session:
            questions = tuple(
                golden_of(row)
                for row in (await session.execute(live_golden_questions())).scalars().all()
            )
            share = (await session.execute(last_applied_share())).scalar_one_or_none()
        store = StoredEntitlements(sessions)

        async def reach_of(principal_id: str) -> EntitlementSet:
            return await store.load(principal_id, now)

        async def canaries() -> CanaryRun:
            reaches = await reaches_on_this_install(sessions, now=now)
            return await ask_every_reach(
                reaches,
                definitions=registry.definitions(),
                rules=rules,
                readers=inputs.readers,
                policies=inputs.policies,
                now=now,
                value=minted_value(),
            )

        return await run_gate(
            change,
            calls=models.calls,
            questions=questions,
            reach_of=reach_of,
            inputs=inputs,
            canaries=canaries,
            baseline=None if share is None else Baseline(quality_share=float(share)),
            now=now,
            new_rung_id=new_rung_id,
        )
