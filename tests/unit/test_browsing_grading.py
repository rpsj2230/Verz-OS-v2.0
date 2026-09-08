"""Scoring a run without asking it, and resolving every uncertainty against it.

The structural half, that `build_rubric` cannot be handed a trajectory and that `score` has no
parameter the agent's claim could arrive through, is in `test_browsing_shape.py`. This is the
behavioural half, and the exhaustive enumeration of M19.5.4 is the part worth reading.

Task ids: M19.5.1, M19.5.3, M19.5.4
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

import pytest

from brain.browsing.enforcer import Action, ActionRecord
from brain.browsing.grading import (
    Claim,
    Criterion,
    GradingError,
    Outcome,
    Rubric,
    Trajectory,
    build_rubric,
    goal_digest,
    score,
    verification_gaps,
)
from brain.browsing.planning import Goal, PlanRequest
from brain.browsing.targets import Surface, Target, Verb
from brain.core.entitlement import Capability

READ = Capability(value="read:browser_surface")
ORIGIN = "https://books.example"
NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def books() -> Target:
    return Target(
        name="books",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="invoices",
                origin=ORIGIN,
                path="/invoices",
                verbs=frozenset({Verb.OPEN, Verb.READ}),
                capability=READ,
                reads=("number", "total"),
            ),
        ),
    )


def request(text: str = "Read this month's invoice totals") -> PlanRequest:
    return PlanRequest(
        goal=Goal(text=text, asked_by="alex"),
        target="books",
        surfaces=("invoices",),
    )


def trajectory() -> Trajectory:
    return Trajectory(
        run_id="run-1",
        records=(
            ActionRecord(
                action=Action(
                    run_id="run-1",
                    surface="invoices",
                    verb=Verb.READ,
                    origin=ORIGIN,
                    ref="n1",
                    sequence=1,
                ),
                claimed_allowed=True,
            ),
        ),
    )


# --------------------------------------------------------------------- the rubric


def test_a_rubric_is_built_from_the_goal_and_the_declaration() -> None:
    """M19.5.1, the positive case. A rubric with nothing in it would satisfy every refusal
    below and certify nothing.

    Delete this and `build_rubric` can start returning a single vacuous criterion, which is
    what a rubric looks like when nobody is checking that it says anything.
    """
    rubric = build_rubric(request(), books(), now=NOW)

    names = {one.name for one in rubric.criteria}

    assert "reached_declared_surfaces" in names
    assert "read_invoices" in names
    assert "goal_satisfied" in names
    assert any("number, total" in one.text for one in rubric.criteria)


def test_a_rubric_is_bound_to_the_goal_it_was_written_for() -> None:
    """Reusing a rubric across runs must be a comparison rather than an assumption.

    Delete this and a rubric can be quietly repointed at a different goal, and it still looks
    like the one that was approved.
    """
    first = build_rubric(request(), books(), now=NOW)
    second = build_rubric(request("File the return"), books(), now=NOW)

    assert first.goal == goal_digest(request())
    assert first.goal != second.goal


def test_the_goal_digest_covers_who_asked_and_which_system() -> None:
    """A rubric for the same words against another system is not the same rubric.

    Delete this and the digest can be narrowed to the goal text, which lets an approved rubric
    for one target certify a run against a different one.
    """
    base = goal_digest(request())
    elsewhere = PlanRequest(
        goal=Goal(text="Read this month's invoice totals", asked_by="alex"),
        target="ledger",
        surfaces=("invoices",),
    )
    somebody_else = PlanRequest(
        goal=Goal(text="Read this month's invoice totals", asked_by="sam"),
        target="books",
        surfaces=("invoices",),
    )

    assert base != goal_digest(elsewhere)
    assert base != goal_digest(somebody_else)


def test_a_rubric_with_no_criteria_is_refused() -> None:
    """An empty rubric is not a run with nothing to prove; it is a rubric nobody finished.

    Delete this and a rubric that failed to be written reads as a run that passed.
    """
    with pytest.raises(GradingError, match="no criteria"):
        Rubric(goal="abc", built_at=NOW, criteria=())


def test_two_criteria_with_one_name_are_refused() -> None:
    """One outcome would answer both, and which one it answered would be list order.

    Delete this and a rubric can carry a duplicate whose outcome silently decides a criterion
    nobody judged.
    """
    with pytest.raises(GradingError, match="share a name"):
        Rubric(
            goal="abc",
            built_at=NOW,
            criteria=(
                Criterion(name="same", text="one thing"),
                Criterion(name="same", text="another thing"),
            ),
        )


def test_a_criterion_with_no_text_is_refused() -> None:
    """Whoever judges it would be judging the name, and a name is not a question.

    Delete this and a rubric can be generated with empty criteria that are then judged
    UNKNOWN for ever, which fails every run for a reason nobody can act on.
    """
    with pytest.raises(GradingError, match="says nothing"):
        Criterion(name="empty", text="   ")


# --------------------------------------------------------------------- the score


def test_a_run_meeting_every_required_criterion_passes() -> None:
    """The positive case. Everything below is a refusal, and a scorer that never passed
    anything would satisfy all of them.

    Delete this and `score` can start returning False unconditionally, which is the safest
    possible answer and useless.
    """
    rubric = build_rubric(request(), books(), now=NOW)
    outcomes = {one.name: Outcome.MET for one in rubric.criteria}

    verdict = score(rubric, trajectory(), outcomes)

    assert verdict.passed
    assert verdict.failed == ()
    assert verdict.unresolved == ()


def test_every_combination_of_outcomes_passes_only_when_all_required_ones_are_met() -> None:
    """M19.5.4, enumerated rather than sampled.

    Three criteria, two of them required, and all twenty-seven combinations of outcomes. The
    property asserted is not a threshold constant compared with itself: it is that `passed` is
    true exactly when every required criterion is MET, for every state the judgements could
    be in. UNKNOWN never passes, and neither does a criterion nobody judged.

    Delete this and the tie-break can be changed to treat UNKNOWN as met, which is the change
    somebody makes when too many runs are failing, and it converts every case the judge could
    not resolve into a false pass that nobody looks at again.
    """
    rubric = Rubric(
        goal="abc",
        built_at=NOW,
        criteria=(
            Criterion(name="a", text="first required thing", must=True),
            Criterion(name="b", text="second required thing", must=True),
            Criterion(name="c", text="a nice to have", must=False),
        ),
    )

    for combination in itertools.product(Outcome, repeat=3):
        outcomes = dict(zip(("a", "b", "c"), combination, strict=True))
        verdict = score(rubric, trajectory(), outcomes)
        expected = outcomes["a"] is Outcome.MET and outcomes["b"] is Outcome.MET

        assert verdict.passed is expected, f"{combination} scored {verdict.passed}"


def test_a_criterion_with_no_outcome_at_all_is_not_met() -> None:
    """A judgement that was never made must not default to the favourable reading.

    Delete this and a judge that silently skipped a criterion produces a pass, which is the
    quietest possible false positive.
    """
    rubric = Rubric(
        goal="abc",
        built_at=NOW,
        criteria=(Criterion(name="a", text="the required thing"),),
    )

    verdict = score(rubric, trajectory(), {})

    assert not verdict.passed
    assert verdict.unresolved == ("a",)


def test_a_rubric_of_only_optional_criteria_passes_nothing() -> None:
    """A rubric that cannot fail a run cannot pass one either.

    Delete this and an all-optional rubric certifies every run, including one that did
    nothing, because the set of required criteria is empty and every empty set is a subset.
    """
    rubric = Rubric(
        goal="abc",
        built_at=NOW,
        criteria=(Criterion(name="a", text="a nice to have", must=False),),
    )

    verdict = score(rubric, trajectory(), {"a": Outcome.MET})

    assert not verdict.passed
    assert any("no required criteria" in one for one in verification_gaps((rubric,)))


def test_what_could_not_be_judged_is_reported_apart_from_what_failed() -> None:
    """A run that did the wrong thing and a run nobody could judge call for different things.

    Delete this and a gap in the judging is filed as a fault in the run, and the judge is
    never fixed because nothing says it is failing.
    """
    rubric = Rubric(
        goal="abc",
        built_at=NOW,
        criteria=(
            Criterion(name="a", text="the required thing"),
            Criterion(name="b", text="the other required thing"),
        ),
    )

    verdict = score(rubric, trajectory(), {"a": Outcome.NOT_MET, "b": Outcome.UNKNOWN})

    assert verdict.failed == ("a",)
    assert verdict.unresolved == ("b",)


# --------------------------------------------------------------------- the agent's claim


def test_the_score_is_the_same_whatever_the_agent_said_about_itself() -> None:
    """M19.5.3. Asserted as invariance rather than by reading the signature, because "does not
    read a field" is the kind of claim that stops being true in a change about something else.

    Delete this and a claim can be threaded into scoring as a tiebreak for the unresolved
    cases, which sounds reasonable and gives the highest marks to the runs that misunderstood
    the goal most completely.
    """
    rubric = Rubric(goal="abc", built_at=NOW, criteria=(Criterion(name="a", text="the thing"),))
    confident = Trajectory(run_id="run-1", records=trajectory().records)

    verdict = score(rubric, confident, {"a": Outcome.UNKNOWN})

    assert not verdict.passed
    assert verdict.disagrees_with(Claim(run_id="run-1", succeeded=True))
    assert not verdict.disagrees_with(Claim(run_id="run-1", succeeded=False))


def test_a_trajectory_has_nowhere_to_put_the_agents_claim() -> None:
    """The claim is a separate type on purpose, so scoring cannot reach it by accident.

    Delete this and a `succeeded` field can be added to `Trajectory`, at which point it is in
    every signature that takes a trajectory, including the scorer's.
    """
    fields = set(Trajectory.__dataclass_fields__)

    assert fields == {"run_id", "records"}
    assert "succeeded" not in fields
    assert "claim" not in fields


# --------------------------------------------------------------------- what is not built


def test_the_module_reports_the_two_verification_leaves_it_does_not_close() -> None:
    """M19.5.2 wants screenshots and M19.4.5 refuses them, which is a conflict between two
    leaves rather than a gap in one.

    Delete this and the conflict survives only in a commit message, and the next person to
    read M19.5.2 builds the second pass and quietly undoes the credential rule.
    """
    gaps = verification_gaps()

    assert any("M19.5.2" in one and "M19.4.5" in one for one in gaps)
    assert any("M19.5.5" in one and "out-of-band" in one for one in gaps)


def test_a_criterion_with_no_name_is_refused() -> None:
    """The name is what an outcome is matched to, so a criterion with none can never be
    judged and is therefore always unresolved, which fails every run for a reason nobody can
    act on.

    Whitespace as well as empty, which is the survivor CLAUDE.md records for validators.

    Delete this and a rubric can carry a nameless criterion that quietly fails every run.
    """
    for bad in ("", "   "):
        with pytest.raises(GradingError, match="no name"):
            Criterion(name=bad, text="the required thing")


def test_a_rubric_bound_to_no_goal_is_refused() -> None:
    """A rubric with no goal grades against whatever it is handed, and the binding is the only
    thing stopping an approved rubric being reused for a different question.

    Delete this and `goal` can be defaulted to the empty string, which makes every rubric
    interchangeable and the digest comparison meaningless.
    """
    for bad in ("", "   "):
        with pytest.raises(GradingError, match="bound to no goal"):
            Rubric(
                goal=bad,
                built_at=NOW,
                criteria=(Criterion(name="a", text="the required thing"),),
            )


def test_a_rubric_writes_no_read_criterion_for_a_surface_that_returns_nothing() -> None:
    """Two cases, and both are ordinary. A login page is navigation only and declares no
    fields; and a request may name a surface the target does not declare at all, because the
    two are validated separately.

    Writing a read criterion for either would give the judge a question with no answer, which
    resolves to UNKNOWN, which fails the run.

    Delete this and every rubric built for a target with a login page fails every run, and the
    reason is a criterion nobody could ever have met.
    """
    login = Surface(
        name="login",
        origin=ORIGIN,
        path="/login",
        verbs=frozenset({Verb.OPEN, Verb.TYPE}),
        capability=READ,
    )
    target = Target(name="books", origins=frozenset({ORIGIN}), surfaces=(*books().surfaces, login))
    asked = PlanRequest(
        goal=Goal(text="Read this month's invoice totals", asked_by="alex"),
        target="books",
        surfaces=("invoices", "login", "ledger"),
    )

    rubric = build_rubric(asked, target, now=NOW)
    names = {one.name for one in rubric.criteria}

    assert "read_invoices" in names
    assert "read_login" not in names
    assert "read_ledger" not in names
