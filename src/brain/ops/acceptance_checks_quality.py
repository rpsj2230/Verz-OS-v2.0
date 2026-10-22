"""The install acceptance checks for quality: flags and the cases they become, the two tiers of
reading, a failed case's candidate, the golden scores by release, and the examples and decisions
that need a person.

Every check writes only inside the check's rolled-back transaction, as reserved people of the two
reserved departments, and every route it presses is the function the console would reach.

**What these prove and what they do not.** They prove the stores and the doors: a lead flags and
captures, the capture carries no value, a day's sample is drawn reproducibly from what was read and
annotated apart from it, a failed case opens a candidate and no agent changes, a release's scores
are kept and a regression is shown, and an example is in effect only once promoted. **They do not
prove that anything on the request path records a reading or that a worker asks the golden
questions**: no caller writes `ops.quality_reading` from an answer, and the product holds no golden
corpus outside `tests/fixtures`. Each check's sentence says so where it matters, and the leaves it
names are the ones its sentence is true of.

Task ids: M28.3.1, M28.3.2, M28.3.3, M28.4.1, M28.5.3, M16.6.7, M16.7.14, M34.2.2.2
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from brain.core.scope import Clause, Op, Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_operations_console import asking_as, console_for, refused, screen_grants
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`. **Before the memory roll-ups
#: (880), not after every module**, because the promotion roll-up reads this module's check of a
#: tier-three decision as the proof of its second clause (M16.7.14), and a roll-up sees only the
#: checks that ran earlier in the run: at 1740 it waited for this check for ever and could never
#: pass.
CHECK_ORDER: Final = 876

A, B = RESERVED_DEPARTMENTS

#: Said when golden scores are on the install already, because the check compares only the
#: releases it makes and an earlier one would be the "previous" of its first.
GOLDEN_SCORES_ALREADY_HERE: Final = (
    "this install holds golden scores of its own, and the check compares only releases it makes "
    "itself, so it would be reading a real regression as its own"
)

#: Said when today's real requests fill the annotation queue, so none of the check's own is in it.
THE_DAY_S_QUEUE_IS_FULL_OF_OTHER_REQUESTS: Final = (
    "today's annotation queue was filled by other requests, so none of the readings this check "
    "recorded was drawn and there is nothing of its own to annotate"
)

FLAGGER: Final = "write:answer_flag"
DECIDER: Final = "approve:evaluation_candidate"


def _in(department: str) -> Scope:
    return Scope(clauses=(Clause(field="department", op=Op.EQ, value=department),))


async def _refused_by_the_database(
    h: Harness, acting_as: str, statement: str, **values: object
) -> bool:
    """Whether the database refused this statement as the application role in `acting_as`'s name,
    in a savepoint that is then undone."""
    async with h.sessions() as session:
        await session.execute(
            text("SELECT set_config('app.principal_id', :who, true)"), {"who": acting_as}
        )
        nested = await session.begin_nested()
        try:
            await session.execute(text(statement), values)
        except DBAPIError:
            return True
        finally:
            await nested.rollback()
    return False


# ----------------------------------------------------- 1. a flag and the case it becomes
@check(
    leaves=("M28.3.1", "M28.3.2"),
    sentence=(
        "A department lead flags an answer in their own department by reference and a closed "
        "reason, one press turns the flag into a case holding field names and no value, a lead of "
        "another department is refused both, and the database refuses a case document with any "
        "key beyond the captured ones."
    ),
)
async def a_flag_becomes_a_case_that_holds_no_value(
    h: Harness,
) -> None:
    from brain.ops.feedback import CapturedCase, FlagReason
    from brain.quality_routes import (
        CaseAsked,
        FlagAsked,
        flag_an_answer,
        listed_flags,
        turn_a_flag_into_a_case,
    )
    from brain.tables.quality import CASE_KEYS

    await h.found_departments()
    lead, other = h.principal(A, "lead"), h.principal(B, "lead")
    reads = screen_grants("quality")
    await h.person(lead, department=A, grants=(*reads, (FLAGGER, _in(A))))
    await h.person(other, department=B, grants=(*reads, (FLAGGER, _in(B))))
    console = console_for(h)
    trace = f"trace{h.run[:8]}"

    asked = FlagAsked(trace_ref=trace, question_id="q1", department=A, reason=FlagReason.WRONG_FACT)
    if not await refused(flag_an_answer(console.request("POST"), await asking_as(h, other), asked)):
        raise CheckFailedError("a lead flagged an answer in a department they do not reach")
    made = await flag_an_answer(console.request("POST"), await asking_as(h, lead), asked)
    again = await flag_an_answer(console.request("POST"), await asking_as(h, lead), asked)
    if again.id != made.id:
        raise CheckFailedError("one lead flagging one answer twice made two flags")
    listed = await listed_flags(console.request(), await asking_as(h, lead))
    if [one.id for one in listed.items] != [made.id]:
        raise CheckFailedError("a lead was not shown the flag they filed, alone")
    if (await listed_flags(console.request(), await asking_as(h, other))).items:
        raise CheckFailedError("a lead of another department was shown a flag they may not file")

    import uuid

    flag_id = uuid.UUID(made.id)
    held = ["read:client.name", "read:client.contract_value"]
    body = CaseAsked(
        question="What is the contract worth?",
        held=held,
        answering_fields=["client.name"],
        locked_fields=["client.contract_value"],
        mocked_from="synthetic_company",
    )
    if not await refused(
        turn_a_flag_into_a_case(console.request("POST"), flag_id, await asking_as(h, other), body)
    ):
        raise CheckFailedError("a lead of another department turned a flag into a case")
    case = await turn_a_flag_into_a_case(
        console.request("POST"), flag_id, await asking_as(h, lead), body
    )
    twice = await turn_a_flag_into_a_case(
        console.request("POST"), flag_id, await asking_as(h, lead), body
    )
    if twice.id != case.id or case.expectation != "partial":
        raise CheckFailedError("a flag did not become one case with the shape it was given")
    if not (await listed_flags(console.request(), await asking_as(h, lead))).items[0].captured:
        raise CheckFailedError("a flag did not say a case had been captured from it")

    from brain.ops.quality_store import kept_cases

    async with h.sessions() as session:
        [document] = await kept_cases(session)
    if set(document) != set(CASE_KEYS) or {f.name for f in fields(CapturedCase)} != set(CASE_KEYS):
        raise CheckFailedError("a kept case held a key a captured case does not have")
    if sorted(map(str, document["held"] or ())) != sorted(held):
        raise CheckFailedError("a kept case did not hold exactly the capabilities its asker did")
    extra = (
        "INSERT INTO ops.regression_case (flag_id, document, captured_by) "
        "VALUES (:flag, CAST(:doc AS jsonb), :who)"
    )
    import json

    smuggled = json.dumps({**document, "answer": "14 Nov 2026"})
    if not await _refused_by_the_database(h, lead, extra, flag=made.id, doc=smuggled, who=lead):
        raise CheckFailedError("the database accepted a case carrying an answer")


# ------------------------------------------- 1b. a wrong-sources flag is its own half (M34.2.2.2)
@check(
    leaves=("M34.2.2.2",),
    sentence=(
        "A department lead flags one answer as having the wrong sources and another as having a "
        "wrong fact: the list tells them apart as retrieval and reasoning, each flag in its own "
        "half, and a lead of another department is shown neither."
    ),
)
async def a_wrong_sources_flag_is_told_apart_from_a_wrong_fact(h: Harness) -> None:
    from brain.ops.feedback import FlagReason
    from brain.quality_routes import FlagAsked, flag_an_answer, listed_flags

    await h.found_departments()
    lead, other = h.principal(A, "planes"), h.principal(B, "planes")
    reads = screen_grants("quality")
    await h.person(lead, department=A, grants=(*reads, (FLAGGER, _in(A))))
    await h.person(other, department=B, grants=(*reads, (FLAGGER, _in(B))))
    console = console_for(h)
    sources, fact = f"sources{h.run[:8]}", f"fact{h.run[:8]}"

    filed = {}
    for trace, reason in ((sources, FlagReason.WRONG_SOURCES), (fact, FlagReason.WRONG_FACT)):
        asked = FlagAsked(trace_ref=trace, question_id="q1", department=A, reason=reason)
        filed[trace] = await flag_an_answer(
            console.request("POST"), await asking_as(h, lead), asked
        )
    listed = await listed_flags(console.request(), await asking_as(h, lead))
    planes = {one.trace_ref: (one.reason, one.plane) for one in listed.items}
    if planes.get(sources) != ("wrong_sources", "retrieval"):
        raise CheckFailedError("a wrong-sources flag was not listed as a retrieval fault")
    if planes.get(fact) != ("wrong_fact", "reasoning"):
        raise CheckFailedError("a wrong-fact flag was not listed as a reasoning fault")
    if (filed[sources].plane, filed[fact].plane) != ("retrieval", "reasoning"):
        raise CheckFailedError("a flag was not told which half of the system it blames when filed")
    if (await listed_flags(console.request(), await asking_as(h, other))).items:
        raise CheckFailedError("a lead of another department was shown a flag they may not file")


# --------------------------------------------------------- 2. two tiers, apart
@check(
    leaves=("M28.3.3",),
    sentence=(
        "Readings recorded for a day's requests give a daily annotation queue drawn the same way "
        "twice and no larger than its quota, an answer in the queue can be annotated and one "
        "outside it cannot, a reader without the company-wide grant gets no queue, and the two "
        "tiers are reported as two reports with their own coverage lines."
    ),
)
async def readings_are_sampled_annotated_and_reported_as_two_tiers(h: Harness) -> None:
    from brain.ops.canaries import Finding
    from brain.ops.quality_store import day_report, record_reading, sample_for
    from brain.ops.sampling import (
        COVERAGE,
        DAILY_ANNOTATION_QUOTA,
        AutomatedReading,
        Tier,
    )
    from brain.quality_routes import (
        AnnotationAsked,
        annotate_an_answer,
        annotation_queue,
    )

    await h.found_departments()
    steward, narrow = h.principal(A, "steward"), h.principal(A, "narrow")
    await h.person(steward, department=A, grants=((FLAGGER, Scope.unrestricted()),))
    await h.person(narrow, department=A, grants=((FLAGGER, _in(A)),))
    console = console_for(h)
    today = datetime.now(UTC).date()

    async with h.sessions() as session:
        for number in range(DAILY_ANNOTATION_QUOTA + 5):
            failed = number == 0
            await record_reading(
                session,
                AutomatedReading(
                    request_id=f"req{h.run[:8]}x{number}",
                    passed=not failed,
                    fault=Finding.LEAKED if failed else None,
                ),
                by=steward,
            )
        await session.commit()
        first = await sample_for(session, today)
        second = await sample_for(session, today)
    ours = [one for one in first.request_ids if one.startswith(f"req{h.run[:8]}x")]
    if not ours and len(first.request_ids) == DAILY_ANNOTATION_QUOTA:
        raise CheckNotRunError(THE_DAY_S_QUEUE_IS_FULL_OF_OTHER_REQUESTS)
    if first != second or len(first.request_ids) > DAILY_ANNOTATION_QUOTA or not ours:
        raise CheckFailedError("a day's queue was not drawn the same way twice within its quota")

    if not await refused(annotation_queue(console.request(), await asking_as(h, narrow), today)):
        raise CheckFailedError("a reader without the company-wide grant was given the queue")
    shown = await annotation_queue(console.request(), await asking_as(h, steward), today)
    if shown.request_ids != list(first.request_ids) or shown.seed != first.seed:
        raise CheckFailedError("the queue a route gave was not the queue that was drawn")

    inside, outside = ours[0], f"req{h.run[:8]}x{DAILY_ANNOTATION_QUOTA + 99}"
    kept = await annotate_an_answer(
        console.request("POST"),
        await asking_as(h, steward),
        AnnotationAsked(day=today, request_id=inside, sound=True),
    )
    if kept.request_id != inside:
        raise CheckFailedError("a sampled answer was not annotated")
    for request_id in (inside, outside):
        if not await refused(
            annotate_an_answer(
                console.request("POST"),
                await asking_as(h, steward),
                AnnotationAsked(day=today, request_id=request_id, sound=True),
            )
        ):
            raise CheckFailedError("an answer already annotated or outside the queue was annotated")

    async with h.sessions() as session:
        report = await day_report(session, today)
    if (
        report.automated[0] != COVERAGE[Tier.AUTOMATED]
        or report.annotated[0] != COVERAGE[Tier.HUMAN]
    ):
        raise CheckFailedError("a tier's report did not open with its own coverage line")
    if set(report.automated) & set(report.annotated) - {""}:
        raise CheckFailedError("the two tiers were reported as one")


# ----------------------------------------------------- 3. a failed case, a candidate
@check(
    leaves=("M28.4.1",),
    sentence=(
        "A failed golden, canary or sampled case opens one candidate against its agent and no more "
        "for the same case, the agent's own rows are unchanged, a reader of the whole "
        "installation approves it once and is recorded, and a department reader can neither list "
        "nor decide one."
    ),
)
async def a_failed_case_opens_a_candidate_and_never_changes_the_agent(h: Harness) -> None:
    import uuid

    from brain.ops.quality_store import candidates, open_candidates
    from brain.quality_routes import (
        CandidateDecisionAsked,
        decide_a_candidate,
        listed_candidates,
    )
    from brain.tables.quality import CandidateSource, TierDecisionWord

    await h.found_departments()
    steward, narrow = h.principal(A, "steward"), h.principal(A, "narrow")
    reads = screen_grants("quality")
    await h.person(steward, department=A, grants=(*reads, (DECIDER, Scope.unrestricted())))
    await h.person(narrow, department=A, grants=(*reads, (DECIDER, _in(A))))
    console = console_for(h)
    agent = f"acceptance_{h.run}_agent"

    async def agent_rows() -> tuple[object, ...]:
        found = await h.execute(
            text(
                "SELECT (SELECT count(*) FROM agent.agent), "
                "(SELECT count(*) FROM agent.template_instance)"
            )
        )
        return tuple(found.one())

    before = await agent_rows()
    async with h.sessions() as session:
        first = await open_candidates(
            session,
            agent_id=agent,
            source=CandidateSource.GOLDEN,
            failed_case_refs=["G04a", "G04a", "G07"],
            by=steward,
        )
        again = await open_candidates(
            session,
            agent_id=agent,
            source=CandidateSource.GOLDEN,
            failed_case_refs=["G04a"],
            by=steward,
        )
        for source in (CandidateSource.CANARY, CandidateSource.SAMPLED):
            await open_candidates(
                session, agent_id=agent, source=source, failed_case_refs=["C1"], by=steward
            )
        await session.commit()
        listed = await candidates(session, agent_id=agent)
    if len(first) != 2 or again or len(listed) != 4:
        raise CheckFailedError("a failed case did not open exactly one candidate")
    if await agent_rows() != before:
        raise CheckFailedError("opening a candidate changed an agent")

    if not await refused(
        listed_candidates(console.request(), await asking_as(h, narrow, strong=True))
    ):
        raise CheckFailedError("a department reader was shown the candidates")
    page = await listed_candidates(console.request(), await asking_as(h, steward, strong=True))
    mine = [one for one in page.items if one.agent_id == agent]
    if {one.standing for one in mine} != {"pending"}:
        raise CheckFailedError("a candidate nobody had decided was not pending")
    target = uuid.UUID(mine[0].id)
    approve = CandidateDecisionAsked(decision=TierDecisionWord.APPROVED)
    if not await refused(
        decide_a_candidate(
            console.request("POST"), target, await asking_as(h, narrow, strong=True), approve
        )
    ):
        raise CheckFailedError("a department reader decided a candidate")
    decided = await decide_a_candidate(
        console.request("POST"), target, await asking_as(h, steward, strong=True), approve
    )
    if decided.changes_the_agent or decided.decision != "approved":
        raise CheckFailedError("a decision said it changed an agent, or was not the one given")
    if not await refused(
        decide_a_candidate(
            console.request("POST"), target, await asking_as(h, steward, strong=True), approve
        )
    ):
        raise CheckFailedError("a candidate was decided twice")
    after = {
        one.id: one.standing
        for one in (
            await listed_candidates(console.request(), await asking_as(h, steward, strong=True))
        ).items
    }
    if after[str(target)] != "approved" or await agent_rows() != before:
        raise CheckFailedError("an approved candidate did not stand as approved, or moved an agent")
    row = (
        await h.execute(
            text(
                "SELECT decided_by, tier, decision FROM ops.tier_decision WHERE item_ref = :ref"
            ).bindparams(ref=str(target))
        )
    ).one()
    if tuple(row) != (steward, 3, "approved"):
        raise CheckFailedError("the decision did not record who decided it at tier three")


# ----------------------------------------------------------- 4. golden scores by release
@check(
    leaves=("M28.5.3",),
    sentence=(
        "Golden results recorded for two releases are kept with the release they ran on once "
        "each, the newer is shown against the one before it, a release with more permission "
        "failures or a lower quality share is a regression and one that did no worse is not, and "
        "one release alone has nothing to be compared with."
    ),
)
async def golden_scores_are_kept_by_release_and_a_regression_is_shown(h: Harness) -> None:
    from brain.ops.evaluation import CaseResult, Severity
    from brain.ops.quality_store import record_golden, regression_since_previous, release_scores

    await h.found_departments()
    runner = h.principal(A, "runner")
    await h.person(runner, department=A)
    persona = "junior"
    release_one, release_two, release_three, release_four = (
        f"v{h.run[:6]}.{n}" for n in (1, 2, 3, 4)
    )

    def result(question: str, severity: Severity, passed: bool) -> CaseResult:
        return CaseResult(
            question_id=question,
            severity=severity,
            passed=passed,
            reason="" if passed else "the shape was not answer",
        )

    clean = [
        result("g1", Severity.QUALITY, True),
        result("g2", Severity.QUALITY, True),
        result("g3", Severity.PERMISSION, True),
    ]
    async with h.sessions() as session:
        if await release_scores(session):
            raise CheckNotRunError(GOLDEN_SCORES_ALREADY_HERE)
        kept = await record_golden(
            session, release=release_one, persona=persona, results=clean, by=runner
        )
        repeat = await record_golden(
            session, release=release_one, persona=persona, results=clean, by=runner
        )
        alone = await regression_since_previous(session)
        worse = [clean[0], clean[1], result("g3", Severity.PERMISSION, False)]
        await record_golden(session, release=release_two, persona=persona, results=worse, by=runner)
        regressed_to = await regression_since_previous(session)
        await record_golden(
            session, release=release_three, persona=persona, results=clean, by=runner
        )
        recovered = await regression_since_previous(session)
        dropped = [result("g1", Severity.QUALITY, False), clean[1], clean[2]]
        await record_golden(
            session, release=release_four, persona=persona, results=dropped, by=runner
        )
        lower = await regression_since_previous(session)
        await session.commit()
    if (kept, repeat) != (3, 0):
        raise CheckFailedError("a golden result was not kept once for its release and persona")
    if alone is not None and alone.regressed:
        raise CheckFailedError(
            "a release that did no worse than the one before it was a regression"
        )
    if regressed_to is None or not regressed_to.regressed:
        raise CheckFailedError("a release with more permission failures was not a regression")
    if regressed_to.latest.release != release_two or regressed_to.latest.permission_failures != 1:
        raise CheckFailedError("the regression did not name the release and its failures")
    if recovered is None or recovered.regressed or recovered.latest.release != release_three:
        raise CheckFailedError("a release that did no worse than the one before was a regression")
    if lower is None or not lower.regressed or lower.latest.permission_failures != 0:
        raise CheckFailedError("a release with a lower quality share was not a regression")


# ------------------------------------------- 5. examples, promotion, and who agreed
@check(
    leaves=("M16.6.7", "M16.7.14"),
    sentence=(
        "An output approved unchanged is kept as a positive example for its agent and is in effect "
        "only from a promotion by a person at tier two and past the instant it takes effect, a "
        "tier-three decision and a promotion each record who agreed, a promotion is refused at "
        "tier three and an approval at tier two, and the database refuses a decision in another "
        "person's name."
    ),
)
async def an_approved_output_is_an_example_in_effect_only_once_promoted(h: Harness) -> None:
    from brain.ops.quality_store import DecisionError, decide, examples_in_effect, record_example
    from brain.tables.quality import ItemKind, TierDecisionWord

    await h.found_departments()
    approver, promoter, second = (
        h.principal(A, role) for role in ("approver", "promoter", "second")
    )
    for one in (approver, promoter, second):
        await h.person(one, department=A)
    agent = f"acceptance_{h.run}_agent"
    now = datetime.now(UTC)
    later = now + timedelta(hours=1)

    async with h.sessions() as session:
        example = await record_example(
            session, agent_id=agent, skill="summarise", artefact_ref=f"art{h.run[:8]}", by=approver
        )
        same = await record_example(
            session, agent_id=agent, skill="summarise", artefact_ref=f"art{h.run[:8]}", by=approver
        )
        if same != example:
            raise CheckFailedError("one output was recorded as two examples")
        if await examples_in_effect(session, agent, now=now):
            raise CheckFailedError("an example was in effect before anybody promoted it")

        async def declined(tier: int, word: TierDecisionWord) -> bool:
            try:
                await decide(
                    session,
                    kind=ItemKind.EXAMPLE,
                    ref=str(example),
                    tier=tier,
                    decision=word,
                    decided_by=promoter,
                    at=now,
                )
            except DecisionError:
                return True
            return False

        if not await declined(3, TierDecisionWord.PROMOTED):
            raise CheckFailedError("a promotion at tier three was accepted")
        if not await declined(2, TierDecisionWord.APPROVED):
            raise CheckFailedError("an approval at tier two was accepted")
        if not await declined(1, TierDecisionWord.PROMOTED):
            raise CheckFailedError("a decision at tier one was accepted")
        await decide(
            session,
            kind=ItemKind.EXAMPLE,
            ref=str(example),
            tier=2,
            decision=TierDecisionWord.PROMOTED,
            decided_by=promoter,
            agreed_by=[second],
            at=now,
            effective_from=later,
        )
        if await examples_in_effect(session, agent, now=now):
            raise CheckFailedError("a promotion took effect before the instant it named")
        if len(await examples_in_effect(session, agent, now=later)) != 1:
            raise CheckFailedError("a promoted example was not in effect once its instant came")
        await session.commit()

    row = (
        await h.execute(
            text(
                "SELECT decided_by, agreed_by, tier FROM ops.tier_decision WHERE item_ref = :ref"
            ).bindparams(ref=str(example))
        )
    ).one()
    if row.decided_by != promoter or set(row.agreed_by) != {promoter, second} or row.tier != 2:
        raise CheckFailedError("a promotion did not record who agreed")

    insert = (
        "INSERT INTO ops.tier_decision "
        "(item_kind, item_ref, tier, decision, decided_by, agreed_by) "
        "VALUES ('example', :ref, 2, 'promoted', CAST(:by AS varchar), ARRAY[CAST(:by AS varchar)])"
    )
    if not await _refused_by_the_database(h, promoter, insert, ref="x1", by=second):
        raise CheckFailedError("the database accepted a decision in another person's name")
    if await _refused_by_the_database(h, promoter, insert, ref="x2", by=promoter):
        raise CheckFailedError("the database refused a decision in the session's own name")
    wrong_tier = insert.replace("2, 'promoted'", "3, 'promoted'")
    if not await _refused_by_the_database(h, promoter, wrong_tier, ref="x3", by=promoter):
        raise CheckFailedError("the database accepted a promotion at tier three")
