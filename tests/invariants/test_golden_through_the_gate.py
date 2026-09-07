"""The golden corpus, asked of the real answer lane as the real people, and scored.

**M28.1.1's phrase is "driven through our gate, never against a bare model", and that phrase
is the whole design.** An evaluation that talks to a model directly measures whether the model
answers well and can detect no permission regression at all, because every permission decision
in this system happens before and after the model call and none of it runs. So every question
below goes through `brain.gate.answer.answer_lane`, which runs the projection, the row read at
the caller's own reach, the redaction and the abstention classifier. What is measured is the
system, not a provider.

Until 2026-09-07 this file could not exist. `tests/invariants/test_golden_and_adversarial.py`
validates that the corpus is well formed, which is a test of the fixture; nothing asked the
system any of its questions, because nothing in the repository could be asked one. The answer
lane and its route were built the same day.

**Two properties, scored separately, and only one of them may fail a build today.**

The permission half must hold now and forever. A canary token is a value planted in a
restricted field of the synthetic company, so a canary appearing in any answer is a
disclosure, and it does not matter which question was asked or how well. A `REFUSE` case must
produce text byte-identical to what a question about a record that does not exist produces.
Both are asserted for every case regardless of what the case expects, because a permission
failure on a question tagged `ANSWER` is still a permission failure.

The quality half is measured and cannot pass yet, and the honest thing is to say so rather
than to lower the floor until it does. `evaluation.QUALITY_FLOOR` stays at 0.9 and names the
target; `BASELINE_QUALITY_SHARE` records what the system actually scores and may only ever go
up. The gap between the two is the work not done, and it is visible in the report every run
rather than hidden by a floor somebody tuned. See
`evaluation.A_HARNESS_THAT_RECORDS_ITS_OWN_BASELINE_RATCHETS_DOWNWARDS`, which is why the
baseline is a committed literal here rather than a file this file writes.

**promptfoo is not used, and that is a deviation from M28.1.1's wording recorded rather than
glossed.** promptfoo drives a provider, and the provider here is an entitled request pipeline
that needs a different principal per case; wiring it up means writing a custom provider in
JavaScript that shells into Python, which puts a second language and a subprocess between the
corpus and the gate and buys nothing this file does not do. What M28.1.1 is for is the
property, and the property is that evaluation goes through the gate. `docs/needs-rupash.md`
carries the choice as a decision somebody can overrule.

Task ids: M28.1.1, M28.1.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from brain.core.entitlement import Capability, EntitlementSet
from brain.core.field_policy import Classification, FieldPolicy
from brain.core.redaction import ChannelPayload, RedactionTrace
from brain.gate.answer import Answered, answer_lane
from brain.gate.fast_lane import FastPathRule, RowReader
from brain.gate.streaming import Event, frames
from brain.knowledge.columns import ColumnRule, TableClassification
from brain.knowledge.rows import RowQuery, RowTool
from brain.ops.evaluation import (
    PERMISSION_FAILURES_ALLOWED,
    QUALITY_FLOOR,
    Baseline,
    cases_from,
    report_lines,
    score,
)
from tests.fixtures.company import NOW, canary_tokens, everyone, person
from tests.fixtures.golden import GOLDEN, REFUSAL_TEXT, Expect
from tests.unit.test_streaming import decode

pytestmark = pytest.mark.invariant

#: What the lane scores on the quality half today, as measured on 2026-09-07.
#:
#: **This may go up and may not go down.** It is a committed literal rather than a number this
#: file writes, which is the whole of the ratchet argument in `evaluation`: a harness that
#: records its own baseline records whatever it happened to do, and a regression becomes the
#: new normal on the commit that caused it.
#:
#: Zero, and the reason is not a defect in the lane. The corpus asks natural-language
#: questions with more than one fact in them, and the only lane that exists answers a
#: data-driven rule with a single field. Nothing here is expected to lift this until the model
#: lane exists. Lowering it is impossible, because zero is the bottom, and that is the one
#: property a baseline of zero still has.
BASELINE_QUALITY_SHARE = 0.0

#: The lane the corpus is asked of. A source name rather than the registry's, because these
#: questions are about the synthetic company rather than about whatever a process registered.
SOURCE = "golden"


class NoRows:
    """A row source with nothing in it, which is what the golden corpus runs against.

    **Deliberate, and it is what makes the permission half meaningful rather than lucky.** The
    synthetic company's records are held as fixtures rather than in a database, so there is no
    store for a row tool to read. A source that invented rows to make the quality half look
    better would be measuring a fixture against itself.

    What still runs is everything that decides: the rule matcher, the projection compiled at
    the caller's reach, the redactor, and the abstention classifier. So the permission
    assertions below are about the real path, and the quality figure is honestly zero.
    """

    def __init__(self) -> None:
        self.asked = 0

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        self.asked += 1
        return ()


CLIENT = TableClassification(
    entity="client",
    rules=(
        ColumnRule(
            column="name",
            required_capability=Capability(value="read:client.name"),
            classification=Classification.INTERNAL,
        ),
    ),
)


def lane_pieces() -> tuple[
    tuple[FastPathRule, ...], dict[tuple[str, str], RowReader], dict[str, FieldPolicy]
]:
    """The three things `answer_lane` needs, built once for every case.

    One rule, over one entity, so the matcher has something to match and the corpus is not
    being asked of an empty lane. A lane with no rules abstains before it reaches the
    projection, which would make every permission assertion below pass for the wrong reason.
    """
    rule = FastPathRule(
        rule_id="golden_client_name",
        template="what is the registered name of {client}",
        slot="client",
        source=SOURCE,
        entity="client",
        match_field="name",
        answer_field="name",
    )
    tool = RowTool(source=SOURCE, classification=CLIENT, description="Read a client record.")
    return (rule,), {(SOURCE, "client"): tool.reader(NoRows())}, {"client": CLIENT.policy()}


class Sink:
    """A `TraceSink` that keeps nothing, because what a trace holds is not what is scored."""

    def emit(self, reference: str, payload: ChannelPayload, trace: RedactionTrace) -> None:
        return None


def ask(question: str, entitlement: EntitlementSet) -> Answered:
    """One golden question, through the whole lane, as one person.

    `asyncio.run` in a synchronous test, which is the house convention: there is no
    `pytest-asyncio` here.
    """
    rules, readers, policies = lane_pieces()
    return asyncio.run(
        answer_lane(
            question,
            rules=rules,
            readers=readers,
            entitlement=entitlement,
            policies=policies,
            reachable_sources=(SOURCE,),
            sink=Sink(),
            now=NOW,
        )
    )


def said(answered: Answered) -> str:
    """Everything the person receives, as one string, decoded from the frames.

    Every frame and not only the prose. A canary that reached a step label or a citation is a
    canary that reached a person, and a check reading only the text frames would miss the two
    places this system emits something that is not the answer.
    """
    return "\n".join(one.data for one in decode(frames(answered.frames)))


def run_corpus() -> tuple[dict[str, bool], dict[str, str], list[str]]:
    """Ask every golden question as its own asker, and mark each case.

    Returns the marks, the reasons, and which ids are permission cases, in the shape
    `evaluation.cases_from` takes. Severity comes from the corpus rather than from the
    English, which is the mistake `tests.fixtures.golden` warns about in its own docstring.
    """
    canaries = canary_tokens()
    marks: dict[str, bool] = {}
    reasons: dict[str, str] = {}
    permission_ids: list[str] = []

    for one in GOLDEN:
        answered = ask(one.question, person(one.asked_by).entitlement())
        text = said(answered)

        leaked = sorted(token for token in canaries if token in text)
        forbidden = sorted(token for token in one.must_not_contain if token in text)

        if one.expect is Expect.REFUSE:
            permission_ids.append(one.qid)
            passed = not leaked and not forbidden and REFUSAL_TEXT in text
            marks[one.qid] = passed
            if not passed:
                reasons[one.qid] = (
                    f"a refusal disclosed {leaked or forbidden}"
                    if (leaked or forbidden)
                    else "a refusal did not produce the sentence an absence produces"
                )
            continue

        # An ANSWER or PARTIAL case is scored on quality, and separately on the one thing that
        # is never a quality question: a canary in the answer is a disclosure whatever the
        # case expected. It is recorded as its own permission case rather than folded into the
        # quality mark, so a leak cannot be averaged away by a corpus that mostly passes.
        if leaked or forbidden:
            permission_ids.append(f"{one.qid}-leak")
            marks[f"{one.qid}-leak"] = False
            reasons[f"{one.qid}-leak"] = f"the answer carried {leaked or forbidden}"
        else:
            permission_ids.append(f"{one.qid}-leak")
            marks[f"{one.qid}-leak"] = True

        missing = sorted(fact for fact in one.must_contain if fact not in text)
        marks[one.qid] = not missing
        if missing:
            reasons[one.qid] = f"the answer did not carry {missing}"

    return marks, reasons, permission_ids


# --------------------------------------------------------------- the permission half


def test_no_canary_reaches_anybody_through_the_answer_lane() -> None:
    """**The property the whole system exists to guarantee, asked as twenty real questions by
    real people through the real path.**

    A canary is a value planted in a restricted field of the synthetic company, so its
    appearance in any answer is a disclosure regardless of which question produced it. Checked
    over every frame rather than over the prose, because a canary in a citation or a step
    label reached a person just the same.

    Delete this and the only end-to-end check that the permission model holds is gone, and
    what remains are unit tests of the pieces that each pass while the composition leaks."""
    marks, reasons, permission_ids = run_corpus()

    failed = sorted(qid for qid in permission_ids if not marks[qid])

    assert failed == [], [reasons[qid] for qid in failed]


def test_a_refusal_is_the_sentence_an_absence_produces() -> None:
    """A refusal that reads differently from "there is no such thing" has confirmed that the
    thing exists. The corpus records the expected text as the same constant for both, and this
    asserts the system agrees.

    Asked as the person the corpus says should be refused, so what is exercised is the real
    narrowing rather than an entitlement assembled here.

    Delete this and the refusal wording drifts, and the drift is a permission leak in a diff
    that reads as copy editing."""
    refused = [one for one in GOLDEN if one.expect is Expect.REFUSE]
    assert refused, "the corpus has no refusal cases, so this asserts nothing"

    for one in refused:
        text = said(ask(one.question, person(one.asked_by).entitlement()))
        assert REFUSAL_TEXT in text, (one.qid, text)


def test_two_people_asking_one_question_are_answered_at_their_own_reach() -> None:
    """**The corpus's own point, asserted against the system rather than against the
    fixture.** A question recorded three times over with three expected shapes is only worth
    having if the system actually answers it three ways.

    Today it answers them the same way, because the lane abstains for every question the fast
    path cannot match, and that is recorded here as the honest state rather than asserted
    away. What is asserted is the part that must hold: the person who may not see the record
    is refused, and the refusal is the sentence an absence produces.

    Delete this and the day the lane starts answering, nothing checks that the two answers
    differ by exactly the entitlement difference."""
    grouped: dict[str, list[Any]] = {}
    for one in GOLDEN:
        grouped.setdefault(one.question, []).append(one)

    shared = [askers for askers in grouped.values() if len(askers) > 1]
    assert shared, "no question is asked by more than one person"

    for askers in shared:
        for one in askers:
            if one.expect is not Expect.REFUSE:
                continue
            text = said(ask(one.question, person(one.asked_by).entitlement()))
            assert REFUSAL_TEXT in text, one.qid


def test_every_persona_the_corpus_names_can_actually_be_asked_as() -> None:
    """A corpus naming a persona whose entitlement cannot be built tests nothing, and it fails
    as a `KeyError` in the middle of a run rather than as a statement about coverage.

    The positive sibling of the checks above: without it they are all satisfied by a run that
    asked nobody anything.

    Delete this and a renamed persona turns twenty scored cases into twenty errors that read
    as a broken harness."""
    people = set(everyone())

    for one in GOLDEN:
        assert one.asked_by in people, one.qid
        assert person(one.asked_by).entitlement().principal_id == one.asked_by


# --------------------------------------------------------------- the quality half


def test_the_run_scores_something_and_reports_what_it_scored() -> None:
    """`score` refuses a run that scored no cases, because a verdict of "nothing failed" from
    a harness that asked nothing is the most convincing wrong answer available: it is what a
    broken runner, a filter matching nothing and an import error all look like.

    Delete this and an import error inside `run_corpus` presents as a passing evaluation."""
    marks, reasons, permission_ids = run_corpus()
    verdict = score(cases_from(marks, permission_ids=permission_ids, reasons=reasons))

    assert marks, "the run scored no cases"
    assert len(marks) >= len(GOLDEN)
    assert report_lines(verdict)


def test_quality_has_not_fallen_below_what_was_committed() -> None:
    """**A floor alone never notices a decline**, which is `evaluation`'s own argument and the
    reason a baseline exists beside the floor. The floor names where this must get to; the
    baseline catches the day it goes backwards.

    The baseline is a committed literal and not a file this run writes, so moving it is a
    commit somebody makes and a diff somebody reads.

    Delete this and a change that stops the lane answering anything at all passes every other
    test in this file, because every other test here is about what must not be said."""
    marks, reasons, permission_ids = run_corpus()
    verdict = score(
        cases_from(marks, permission_ids=permission_ids, reasons=reasons),
        baseline=Baseline(quality_share=BASELINE_QUALITY_SHARE),
    )

    assert verdict.quality_share >= BASELINE_QUALITY_SHARE, report_lines(verdict)
    assert verdict.previous_quality_share == BASELINE_QUALITY_SHARE


def test_the_gap_between_the_baseline_and_the_floor_is_visible_rather_than_tuned_away() -> None:
    """The dishonest way to make this suite green is to lower `QUALITY_FLOOR` until today's
    score clears it. This asserts that has not happened: the floor is where the architecture
    put it, the baseline is where the system actually is, and the distance between them is the
    work that has not been done.

    Anchored to `evaluation.QUALITY_FLOOR` rather than to a literal, so the two cannot be
    changed independently without this failing.

    Delete this and the floor drifts down to meet the baseline one commit at a time, and the
    suite goes on reporting "passing"."""
    assert QUALITY_FLOOR == 0.9
    assert BASELINE_QUALITY_SHARE < QUALITY_FLOOR
    assert PERMISSION_FAILURES_ALLOWED == 0


def test_a_permission_failure_blocks_the_merge_whatever_the_quality_figures_say() -> None:
    """**M28.1.4 is "CI integration blocking merge on regression", and this is the part of it
    that is a decision rather than a workflow file.** The invariants suite is its own CI step
    and Deploy is gated on CI, so a failure here stops a merge and stops a deployment. What
    this asserts is that a permission failure produces that failure even on a run whose
    quality is perfect, which is the case where somebody would be tempted to let it through.

    Constructed rather than provoked, because provoking a real leak means building one, and a
    test that plants a disclosure to prove the harness sees it is a test that can leave one
    behind.

    Delete this and a permission failure can be averaged into a passing quality share."""
    perfect = cases_from(
        {"Q1": True, "Q2": True, "Q3": False},
        permission_ids=["Q3"],
        reasons={"Q3": "the answer carried a canary"},
    )

    verdict = score(perfect)

    assert verdict.may_merge is False
    assert verdict.permission_failures == ("Q3",)
    assert verdict.quality_share == 1.0
    assert any("does not merge whatever the quality figures say" in one for one in verdict.reasons)


def test_the_corpus_is_asked_of_the_gate_and_not_of_a_model() -> None:
    """**M28.1.1's actual requirement, asserted structurally.** An evaluation that talks to a
    model directly measures a provider and can detect no permission regression, because every
    decision in this system happens outside the model call.

    Asserted over this module's imports, parsed, rather than over its text. The first version
    searched the source for forbidden strings and failed on its own assertion list, which is
    the inverse of the trap CLAUDE.md records about tests satisfied by their own docstrings:
    the same mistake, pointing the other way, and the same fix. What a module imports is the
    fact, and it is a fact a parser can state.

    A behavioural check cannot say this, because a harness that called a model would still
    produce answers and still score them.

    Delete this and somebody adds a faster path that asks a model directly, and the suite goes
    on being called an evaluation."""
    import ast
    import inspect

    from tests.invariants import test_golden_through_the_gate as this

    tree = ast.parse(inspect.getsource(this))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert "brain.gate.answer" in imported

    for forbidden in sorted(imported):
        assert not forbidden.startswith("brain.models"), forbidden
        assert forbidden not in ("openai", "anthropic", "litellm"), forbidden


def test_no_persona_in_the_synthetic_company_can_reach_a_row_at_all() -> None:
    """**A finding, recorded as a test because it is the only form nobody deletes by
    accident.** Asking the corpus of the real lane for the first time turned this up, and it
    is why the quality baseline is zero: not because no rule matches, but because nobody in
    the company can read a record.

    `brain.knowledge.rows.entity_capability` is explicit that `Capability.covers` deliberately
    does not let `read:client.*` confer `read:client`: reaching a row and reading a column are
    two separate grants, and that separation is what lets the scope on the row grant be the
    WHERE clause while the field grants are the SELECT list. It is a good design.

    `tests/fixtures/company.py` grants columns and never records. Every persona holds
    `read:client.*` or `read:client.name` and not one holds `read:client`, for any entity. So
    `row_scope_for` answers None for everybody, `compile_row_query` short-circuits to a
    statement it knows is empty, and no row source is ever consulted. The golden corpus
    expects `u_aaron` to be told a hosting expiry and a number of hours; through the real
    system he is told what somebody with no grants is told.

    **Nothing noticed until now, and the reason is worth naming.**
    `tests/invariants/test_golden_and_adversarial.py` validates that the corpus is well formed,
    which is a property of the fixture. Every row-plane test builds its own entitlement inline
    rather than taking a persona. So the fixture and the row plane have disagreed since the row
    plane was written, and the two were never in the same test.

    This asserts the gap rather than fixing it, deliberately: adding record grants to the
    company widens what every persona reaches, and roughly seven thousand tests take their
    reach from that fixture. That is a change to make on its own, with its own mutation run,
    not as a side effect of building an evaluation harness.

    Delete this and the finding goes back to being invisible, and the quality baseline of zero
    reads as "the lane cannot answer" rather than "the fixture cannot be read"."""
    from brain.knowledge.rows import row_scope_for

    reachable = [
        (pid, entity)
        for pid, who in everyone().items()
        for entity in ("client", "ticket", "invoice", "price_list")
        if row_scope_for(entity, who.entitlement(), NOW) is not None
    ]

    assert reachable == [], (
        "a persona now reaches rows, so the fixture has been given record-level grants and "
        "this test should be replaced by one asserting the golden answers actually arrive"
    )

    # The positive half, so this cannot be satisfied by a `row_scope_for` that always answers
    # None. An entitlement holding the record grant reaches rows, which is what the personas
    # are missing rather than what the function refuses.
    from brain.core.entitlement import EntitlementSet, Grant
    from brain.core.scope import Scope

    holder = EntitlementSet(
        principal_id="p_probe",
        grants=(Grant(capability=Capability(value="read:client"), scope=Scope()),),
    )
    assert row_scope_for("client", holder, NOW) is not None


def test_the_lane_reaches_a_row_source_for_a_caller_who_holds_the_record_grant() -> None:
    """The permission assertions in this file would be worth nothing if the lane abstained
    before reaching the projection: a rule that matched nothing produces the same refusal as a
    projection that refused, and only one of those is the property being tested.

    So this builds the entitlement the company does not contain and shows the source is
    consulted, which puts the whole path under test rather than the matcher alone.

    Delete this and every permission assertion above passes against a lane that never gets
    past the rule matcher."""
    from brain.core.entitlement import EntitlementSet, Grant
    from brain.core.scope import Scope

    rules, _, policies = lane_pieces()
    consulted = NoRows()
    tool = RowTool(source=SOURCE, classification=CLIENT, description="Read a client record.")
    holder = EntitlementSet(
        principal_id="p_probe",
        grants=(
            Grant(capability=Capability(value="read:client"), scope=Scope()),
            Grant(capability=Capability(value="read:client.name"), scope=Scope()),
        ),
    )

    asyncio.run(
        answer_lane(
            "what is the registered name of SNM",
            rules=rules,
            readers={(SOURCE, "client"): tool.reader(consulted)},
            entitlement=holder,
            policies=policies,
            reachable_sources=(SOURCE,),
            sink=Sink(),
            now=NOW,
        )
    )

    assert consulted.asked == 1, "the lane did not reach the row source for a caller who does"


def test_a_step_label_or_a_citation_never_carries_a_canary() -> None:
    """The frames that are not the answer are the ones nobody reviews, and they are emitted
    before the answer is. `said` reads every frame for exactly this reason and this asserts
    the reason rather than leaving it to a docstring.

    Delete this and the canary check narrows to text frames, and the two surfaces this system
    emits alongside an answer stop being checked."""
    canaries = canary_tokens()

    for one in GOLDEN[:6]:
        answered = ask(one.question, person(one.asked_by).entitlement())
        for frame in decode(frames(answered.frames)):
            if frame.event in (Event.STEP.value, Event.CITATION.value):
                for token in canaries:
                    assert token not in frame.data, (one.qid, frame.event, frame.data)
