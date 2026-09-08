"""The failure matrix, the retry classification and the service levels, held to their sources.

Every number in `brain.ops.reliability` is a default, and a default in a template is the
thing that is right for one company and silently wrong for the next. So the tests here are
mostly about where a figure came from rather than what it is: the lane targets are parsed
out of the sentence `brain.ops.admission` already states them in, the stage count is read out
of the work breakdown, and the baseline component names are read out of the compose file.
A test asserting `FAST_P95_MS == 500` beside a module declaring `FAST_P95_MS = 500` compares
the constant against itself and passes for every value it could hold.

Task ids: M30.4.1, M30.4.2, M30.5.1
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from brain.core.lane import Lane
from brain.ops.admission import LOAD_TEST_TARGET
from brain.ops.idempotency import Disposition
from brain.ops.reliability import (
    ANSWER_P95_MS,
    BASELINE_COMPONENTS,
    FAILURE_STATUSES,
    FAST_P95_MS,
    LANE_OBJECTIVES,
    MATRIX,
    OPERATION_CLASSES,
    RECOVERY_OBJECTIVES,
    STAGE_OBJECTIVES,
    SUCCESS_STATUSES,
    SUCCESSFUL_REQUEST_RATE,
    FailureMode,
    LaneObjective,
    OperationClass,
    RecoveryObjective,
    ReliabilityError,
    RetryClass,
    Stage,
    StageObjective,
    all_components,
    attainment,
    classification_gaps,
    lane_objective,
    matrix_gaps,
    measurement_gaps,
    profiles_without_objectives,
    recovery_objective,
    retry_class_for,
    stage_budget_gaps,
    status_gaps,
    success_rate,
)
from brain.ops.telemetry import RequestStatus
from brain.ops.wiring import COMPONENTS, PROFILES

REPO = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------ where the figures come from
def test_the_lane_targets_are_the_service_levels_the_architecture_already_states() -> None:
    """**The one test that stops these figures being invented here.**

    `brain.ops.admission.LOAD_TEST_TARGET` states the service levels as prose, inside a load
    test's pass conditions, and has done since M22. The integers in `brain.ops.reliability`
    are a second copy of the same three numbers, which is safe only because this parses them
    out of that sentence and holds the two equal.

    Delete this and `FAST_P95_MS` becomes a number somebody chose, and the load test and the
    objective can promise different things about the same lane with both files reading
    correctly on their own."""
    fast = re.search(r"FAST p95 under (\d+)ms", LOAD_TEST_TARGET)
    answer = re.search(r"ANSWER p95 under (\d+)s", LOAD_TEST_TARGET)
    rate = re.search(r"successful request rate above ([\d.]+)%", LOAD_TEST_TARGET)

    assert fast is not None and answer is not None and rate is not None, LOAD_TEST_TARGET
    assert int(fast.group(1)) == FAST_P95_MS
    assert int(answer.group(1)) * 1000 == ANSWER_P95_MS
    assert float(rate.group(1)) / 100 == SUCCESSFUL_REQUEST_RATE


def test_there_is_one_stage_for_each_task_group_the_gate_was_planned_as() -> None:
    """The stage vocabulary is nine members and nothing in the module says why nine.

    It is the nine task groups of M3, which is the decomposition the gate was actually built
    against, and reading the count out of `docs/wbs.json` is what stops a stage list being a
    set of names whoever wrote this file found plausible.

    Delete this and a tenth group can be added to M3 with no stage for it, which is the
    positional-id trap CLAUDE.md records: the ids still resolve, the budget still sums, and
    a whole phase of the request is charged to whichever neighbour is measured next."""
    wbs = json.loads((REPO / "docs" / "wbs.json").read_text(encoding="utf-8"))
    gate = next(one for one in wbs["modules"] if one["id"] == "M3")
    groups = {leaf.rsplit(".", 1)[0] for leaf in gate["leaf_ids"]}

    assert len(Stage) == len(groups), f"M3 has {len(groups)} groups and Stage has {len(Stage)}"


def test_the_baseline_components_are_the_services_the_deployed_compose_file_declares() -> None:
    """`wiring.COMPONENTS` starts at wave two, so the four containers every install runs are
    in no register anywhere: `PRODUCTION_BASELINE_MIB` costs them as one number and names
    none of them. `BASELINE_COMPONENTS` is therefore a list typed by hand, and this is what
    stops it being a list typed by hand once.

    Read with `yaml.safe_load` rather than grepped, for the reason `test_compose.py` gives:
    a substring search passes happily on a commented-out service.

    Delete this and a fifth base service can be added to `docker-compose.yml` with no
    failure mode written for it, and `matrix_gaps` will report full coverage."""
    parsed = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    declared = set(parsed["services"])

    assert set(BASELINE_COMPONENTS) == declared
    assert declared.isdisjoint({one.name for one in COMPONENTS}), (
        "a base service is also in the wave-two register, so it is budgeted twice"
    )


# ------------------------------------------------------------------- the stage budgets
def test_the_stage_budgets_are_an_allocation_of_the_lane_target_and_not_a_ceiling() -> None:
    """The declared budgets total exactly the fast lane's target, and a set that merely fits
    inside it is reported.

    That is the whole difference between a budget and a limit. Under a ceiling, every stage
    can be raised a little, each change is locally defensible, and the lane misses its
    objective with every component inside its own allocation and nobody at fault.

    Delete this and the equality becomes a comparison the first time somebody needs twenty
    more milliseconds."""
    assert stage_budget_gaps() == ()
    assert sum(one.p95_ms for one in STAGE_OBJECTIVES) == FAST_P95_MS

    slack = tuple(
        StageObjective(stage=one.stage, p95_ms=one.p95_ms - 1, because=one.because)
        for one in STAGE_OBJECTIVES
    )
    found = stage_budget_gaps(slack)

    assert len(found) == 1
    assert "total" in found[0] and str(FAST_P95_MS) in found[0]


def test_a_stage_with_no_budget_and_a_stage_with_two_are_both_reported() -> None:
    """Two ways a set of nine numbers stops being an allocation of one.

    A missing stage is charged to whichever neighbour is measured next, and a duplicated one
    makes the total depend on which line the reader stops at. Both are asserted here because
    the sum check above passes for a set that drops one stage and doubles another.

    Delete this and the budget can be a partition of the right total over the wrong stages."""
    without = tuple(one for one in STAGE_OBJECTIVES if one.stage is not Stage.CACHE)
    missing = stage_budget_gaps(without)

    assert any(Stage.CACHE.value in one and "no latency budget" in one for one in missing)

    twice = (*STAGE_OBJECTIVES, STAGE_OBJECTIVES[0])
    duplicated = stage_budget_gaps(twice)

    assert any("budgeted 2 times" in one for one in duplicated)


def test_a_stage_budgeted_nothing_is_refused_at_construction() -> None:
    """A zero is how "no budget" gets written by somebody who does not want to think about
    a stage yet, and it passes the sum check by contributing nothing.

    Delete this and a stage can be declared with no cost, which reads as a stage that is
    free rather than as a stage nobody has measured."""
    with pytest.raises(ReliabilityError, match="no budget"):
        StageObjective(stage=Stage.CACHE, p95_ms=0, because="not measured yet")


# ------------------------------------------------------------------- the lane objectives
def test_a_refused_request_counts_as_a_successful_one() -> None:
    """**This is a permission decision, not an availability one, and it is the reason the
    success rate is safe to show anybody.**

    DENIED and ABSENT are one status in the ledger so that nobody can count the difference.
    A success rate that treated `NOTHING_RETURNED` as a failure would put the count straight
    back: a person with narrow reach would show a lower availability figure than their
    manager for the same traffic, and the gap between the two numbers is how many things
    they were refused.

    Delete this and the obvious edit, moving a refusal into the failure set because it looks
    like one, publishes a hidden item count on a dashboard."""
    assert RequestStatus.NOTHING_RETURNED in SUCCESS_STATUSES
    assert RequestStatus.NOTHING_RETURNED not in FAILURE_STATUSES

    refusals = [RequestStatus.NOTHING_RETURNED] * 10

    assert success_rate(refusals) == 1.0


def test_the_two_status_sets_partition_the_ledger_vocabulary() -> None:
    """Neither set is derived from the other, so a sixth status can land in both or neither.

    In both, the rate depends on which set the counter reads first. In neither, requests
    ending that way leave the numerator and the denominator together and the figure stays
    flattering while a whole failure mode goes uncounted.

    Both directions are shown failing, because a partition check run only against the
    declarations is silent for every value they could hold.

    Delete this and adding a status to `RequestStatus` changes an availability figure with
    nothing saying so."""
    assert status_gaps() == ()

    overlap = status_gaps(SUCCESS_STATUSES | {RequestStatus.FAILED}, FAILURE_STATUSES)

    assert any("both a success and a failure" in one for one in overlap)

    orphan = status_gaps(SUCCESS_STATUSES - {RequestStatus.UNRESOLVED}, FAILURE_STATUSES)

    assert any("neither a success nor a failure" in one for one in orphan)


def test_a_success_rate_over_no_requests_is_refused_rather_than_perfect() -> None:
    """The version of this function that returns 1.0 for an empty window shows a green light
    for a system that stopped receiving traffic an hour ago, which is the one outage a
    dashboard exists to catch.

    Delete this and the guard becomes a `ZeroDivisionError` somebody fixes with a default."""
    with pytest.raises(ReliabilityError, match="unknown"):
        success_rate([])


def test_the_task_lane_promises_a_success_rate_and_deliberately_no_percentile() -> None:
    """Nobody is watching a task, so a latency percentile there measures the wrong thing
    precisely: a task taking nine minutes instead of four has cost nothing and one that ends
    without saying so has cost everything.

    Asserted with the reason attached, because a `None` in that slot is indistinguishable
    from a figure somebody forgot to fill in, and the next reader fills it in.

    Delete this and the task lane gets an eight-second target on the grounds that the other
    two have one."""
    task = lane_objective(Lane.TASK)

    assert task.p95_ms is None
    assert task.success_rate == SUCCESSFUL_REQUEST_RATE
    assert "nobody is watching" in task.because

    assert lane_objective(Lane.FAST).p95_ms == FAST_P95_MS
    assert lane_objective(Lane.ANSWER).p95_ms == ANSWER_P95_MS


def test_a_lane_nothing_declares_an_objective_for_is_refused() -> None:
    """Returning `None` here puts a dash on a screen and a lane's traffic against nothing.

    Delete this and a fourth lane is measured by not being measured."""
    with pytest.raises(ReliabilityError, match="no objective declares"):
        lane_objective(Lane.FAST, [one for one in LANE_OBJECTIVES if one.lane is not Lane.FAST])


def test_an_objective_with_no_measurement_is_reported_as_unmet_rather_than_passed_over() -> None:
    """Today's state for every lane, and the reading that matters: an unmeasured target is
    not a met one. The alternative implementation skips the row when the observation is
    `None`, and a dashboard built on it shows every latency objective green because nothing
    times anything.

    Delete this and the absence of a metric renders as compliance."""
    fast = lane_objective(Lane.FAST)

    unmeasured = attainment(fast, observed_p95_ms=None, observed_success_rate=1.0)

    assert len(unmeasured) == 1
    assert "nothing measures one" in unmeasured[0]

    met = attainment(fast, observed_p95_ms=float(FAST_P95_MS), observed_success_rate=1.0)

    assert met == ()

    missed = attainment(fast, observed_p95_ms=float(FAST_P95_MS + 1), observed_success_rate=0.5)

    assert len(missed) == 2


def test_an_objective_with_no_percentile_is_not_reported_for_want_of_a_measurement() -> None:
    """The sibling of the test above and the reason the branch is on the objective rather
    than on the observation: the task lane has no percentile to miss, so a missing latency
    measurement is not a shortfall there.

    Delete this and every task-lane row on a dashboard is permanently red for a number the
    lane deliberately does not have."""
    task = lane_objective(Lane.TASK)

    assert attainment(task, observed_p95_ms=None, observed_success_rate=1.0) == ()


def test_an_objective_promising_more_than_all_requests_is_refused() -> None:
    """A success rate above one is a target nothing can meet, and it arrives as a percentage
    typed into a fraction.

    Delete this and a client is promised 99.5 requests out of every one."""
    with pytest.raises(ReliabilityError, match="not a share"):
        LaneObjective(lane=Lane.FAST, p95_ms=500, success_rate=99.5, because="typo")


# ---------------------------------------------------- what the ledger can actually measure
def test_the_ledger_can_measure_the_success_rate_and_cannot_measure_any_latency() -> None:
    """**M30.5.2 is not claimed and this is the finding rather than an omission.**

    `brain.ops.telemetry.TELEMETRY_FIELDS` carries `received_at` and no completion time, so
    there is no duration in a ledger row to take a percentile of, and it carries no field
    naming a stage, so the nine stage budgets are an allocation nothing observes. What it
    does carry, required and on every row, is `status`, so the success-rate half of every
    objective is measurable today.

    Derived from telemetry's own declarations rather than restated here, so the day somebody
    adds a completion timestamp the first finding disappears on its own.

    Delete this and the objectives read as measured, which is the exact failure
    `brain.console.installation` exists to prevent one screen over."""
    findings = measurement_gaps()

    assert any("no duration in it to take a percentile of" in one for one in findings)
    assert any("no field naming a stage" in one for one in findings)
    assert not any("no status" in one for one in findings)

    # A ledger holding only when the request arrived still cannot measure how long it took.
    # Written after a mutation adding `received_at` to `WHOLE_REQUEST_DURATION_FIELDS`
    # survived: `RequestTelemetry.ledger_row` does carry that key, so a caller passing the
    # row's own keys rather than `TELEMETRY_FIELDS` would have been told the lane latency
    # was measurable from a single timestamp.
    arrival_only = measurement_gaps(("received_at", "status"), ())

    assert any("no duration in it to take a percentile of" in one for one in arrival_only)


def test_a_ledger_with_a_completion_time_and_a_stage_measures_all_of_it() -> None:
    """The positive half, and it is not decoration: the test above passes for a function
    that reports every finding unconditionally, which would be a check that can never go
    green and would be switched off the week it did.

    Delete this and `measurement_gaps` can become a constant."""
    complete = ("received_at", "completed_at", "stage", "status")

    assert measurement_gaps(complete, ()) == ()


def test_a_ledger_that_lost_its_status_field_loses_the_one_half_that_works() -> None:
    """The fourth finding, which is silent against the declarations and is the one that
    matters most if it ever fires: without `status` nothing about these objectives is
    observed at all.

    Delete this and a branch nothing can reach sits in the module looking like coverage."""
    found = measurement_gaps(("received_at",), ())

    assert any("no status" in one for one in found)


# ----------------------------------------------------------- the operation classification
def test_an_operation_with_a_side_effect_cannot_be_classified_safe_to_retry() -> None:
    """**The rule the whole classification exists for, refused in a constructor rather than
    reviewed.**

    Safe to retry means the second attempt is indistinguishable from the first not having
    happened, and anything that changed something outside this process fails that by
    definition, whatever the transport reported, because the transport is exactly what could
    not be relied on. `brain.ops.idempotency` is the machinery for the honest answer.

    Delete this and the classification is edited during an incident, which is when somebody
    wants a write to be safe to retry."""
    with pytest.raises(ReliabilityError, match="safe to retry"):
        OperationClass(
            name="raise an invoice",
            has_side_effect=True,
            retry=RetryClass.SAFE,
            because="it worked the last few times",
        )

    allowed = OperationClass(
        name="raise an invoice",
        has_side_effect=True,
        retry=RetryClass.AFTER_VERIFICATION,
        because="the way out of not knowing is asking the source",
    )

    assert allowed.retry is RetryClass.AFTER_VERIFICATION


def test_every_retry_class_is_something_this_system_actually_does() -> None:
    """A class declared and never applied looks like coverage in a review and is a word in
    an enum. All four of the leaf's classes are used by a real operation here, and
    `classification_gaps` is what says so when one stops being.

    Delete this and the four-way classification can shrink to two with the enum unchanged."""
    assert classification_gaps() == ()
    assert {one.retry for one in OPERATION_CLASSES} == set(RetryClass)

    without_human = tuple(
        one for one in OPERATION_CLASSES if one.retry is not RetryClass.NEEDS_A_HUMAN
    )
    found = classification_gaps(without_human)

    assert any(RetryClass.NEEDS_A_HUMAN.value in one for one in found)


def test_an_operation_classified_twice_is_reported() -> None:
    """Two entries for one name means the answer depends on which is read first, and the two
    would not have been written unless somebody disagreed.

    Delete this and a write can be classified safe in one line and unsafe in another with
    both present."""
    doubled = (*OPERATION_CLASSES, OPERATION_CLASSES[0])

    assert any("classified 2 times" in one for one in classification_gaps(doubled))


def test_an_unclassified_operation_is_refused_rather_than_retried() -> None:
    """The default a lookup would have here is the dangerous one. An operation nothing
    classifies is by definition one nobody has thought about, and a `.get` with a `SAFE`
    default retries it.

    Delete this and the safe answer becomes the answer for everything unnamed."""
    with pytest.raises(ReliabilityError, match="nothing classifies"):
        retry_class_for("wire the money again")

    assert retry_class_for("read a projected row") is RetryClass.SAFE
    assert retry_class_for("send a message on a channel") is RetryClass.UNSAFE


def test_this_retry_vocabulary_stays_distinguishable_from_the_crash_recovery_one() -> None:
    """`brain.ops.idempotency.Disposition` is four members about a record found after a
    crash; `RetryClass` is four members about work that has not started. They answer
    different questions and conflating them is how somebody issues a second side effect
    against a record nobody knows the fate of.

    Asserted as disjoint value sets rather than as a comment, because the failure is a
    rename that makes two vocabularies look like one.

    Delete this and a future `RetryClass.VERIFY` reads as the same thing `Disposition.VERIFY`
    means, which it is not: one says ask the source now, the other says this kind of work may
    be repeated once somebody has."""
    assert len(RetryClass) == len(Disposition) == 4
    assert {one.value for one in RetryClass}.isdisjoint({one.value for one in Disposition})


# ------------------------------------------------------------------- the failure matrix
def test_the_matrix_covers_every_component_the_deployment_runs() -> None:
    """**Covering "every component" means more than the component register holds.**

    `wiring.COMPONENTS` is wave two and does not contain the database, the pooler, the cache
    or the application, so a matrix checked against it alone would report full coverage while
    having no row for PostgreSQL.

    Delete this and the matrix passes its own check while missing the four things that are
    actually running."""
    assert matrix_gaps() == ()
    assert set(all_components()) == set(BASELINE_COMPONENTS) | {one.name for one in COMPONENTS}
    assert "db" in all_components()

    covered = {one.component for one in MATRIX}

    assert covered == set(all_components())


def test_a_component_with_no_failure_mode_and_a_row_for_no_component_are_both_reported() -> None:
    """The two directions, and they are different faults. A component with no row means the
    first person to see it fail writes the matrix during the incident. A row for something
    nothing deploys means the matrix is describing a system that no longer exists, which is
    how the rest of it stops being trusted.

    Delete this and either can happen with `matrix_gaps` silent."""
    without = tuple(one for one in MATRIX if one.component != "db")

    assert any("db: no failure mode" in one for one in matrix_gaps(without))

    stale = (
        *MATRIX,
        FailureMode(
            component="mongo",
            fails="it is not here",
            presents_as="nothing, because it was never deployed",
            blocks=("nothing",),
            retry=RetryClass.SAFE,
            response="delete the row",
        ),
    )

    assert any("nothing deploys" in one for one in matrix_gaps(stale))


def test_a_row_blocking_a_component_that_does_not_exist_is_reported() -> None:
    """`blocks` is prose because the component register carries no dependency edges, so
    nothing can derive it and nothing can fully check it. What is checkable is the half that
    looks like a component name: an entry with a hyphen and no space is a container name, and
    a container name that names nothing is a rename nobody followed through.

    Delete this and `blocks` can name `langfuse-clickhouse` after it has been removed, which
    sends an operator to look at a container that is not there."""
    renamed = (
        FailureMode(
            component="db",
            fails="down",
            presents_as="readiness fails",
            blocks=("brain-nonesuch",),
            retry=RetryClass.SAFE,
            response="look at it",
        ),
    )
    found = matrix_gaps(renamed, ("db",))

    assert any("named like a component and is not one" in one for one in found)


def test_a_plain_english_consequence_is_not_reported_as_a_missing_component() -> None:
    """The positive half of the check above, and the reason it is lenient. What an outage
    costs is often not another container: "every answer and every write" is the most useful
    entry in the matrix and a check demanding component names would force it to be deleted.

    Delete this and the useful half of `blocks` is rewritten into container names."""
    prose = (
        FailureMode(
            component="db",
            fails="down",
            presents_as="readiness fails",
            blocks=("every answer and every write", "nothing outright"),
            retry=RetryClass.SAFE,
            response="look at it",
        ),
    )

    assert matrix_gaps(prose, ("db",)) == ()


def test_a_failure_mode_may_not_say_a_component_blocks_itself() -> None:
    """A row saying the database blocks the database tells an operator nothing they did not
    have, and it is what gets written when somebody fills the field to satisfy a check.

    Delete this and `blocks` can be populated with the component's own name everywhere and
    every coverage test still passes."""
    with pytest.raises(ReliabilityError, match="blocking itself"):
        FailureMode(
            component="db",
            fails="down",
            presents_as="readiness fails",
            blocks=("db",),
            retry=RetryClass.SAFE,
            response="look at it",
        )


def test_every_failure_mode_says_how_it_presents() -> None:
    """The field the matrix is worth the most for and the one usually omitted. The expensive
    outages here present as nothing: a queue behind a transaction pooler stops receiving
    notifications and looks like a queue with nothing in it.

    Asserted over every row rather than spot-checked, because a matrix with one blank row is
    a matrix somebody stops reading.

    Delete this and the field becomes optional by convention."""
    for one in MATRIX:
        assert one.presents_as.strip(), one.component
        assert one.response.strip(), one.component

    with pytest.raises(ReliabilityError, match="no presents_as"):
        FailureMode(
            component="db",
            fails="down",
            presents_as="   ",
            blocks=("app",),
            retry=RetryClass.SAFE,
            response="look at it",
        )


# ------------------------------------------------------------- the recovery objectives
def test_every_deployment_profile_is_promised_a_recovery_objective() -> None:
    """Read off `wiring.PROFILES` rather than from a list here, so a fourth profile arrives
    as a finding rather than as a set of clients promised nothing.

    Delete this and a profile can be added whose install has no stated recovery point and no
    stated recovery time, which is discovered when somebody asks after an outage."""
    assert profiles_without_objectives() == ()
    assert {one.profile for one in RECOVERY_OBJECTIVES} == set(PROFILES)

    thin = tuple(one for one in RECOVERY_OBJECTIVES if one.profile != "full")

    assert profiles_without_objectives(thin) == ("full",)


def test_a_profile_nothing_declares_an_objective_for_is_refused() -> None:
    """Two failures, and the second is the interesting one. A mistyped profile is refused by
    `assert_known_profile`; a correctly spelled profile with no objective is refused here,
    and would otherwise reach a caller as a `None` rendered as a dash.

    Delete this and an install can be on a profile that promises nothing, silently."""
    with pytest.raises(Exception, match="profile"):
        recovery_objective("enormous")

    thin = tuple(one for one in RECOVERY_OBJECTIVES if one.profile != "full")

    with pytest.raises(ReliabilityError, match="no recovery objective"):
        recovery_objective("full", thin)


def test_a_recovery_objective_names_a_profile_that_exists() -> None:
    """`assert_known_profile` is called in the constructor rather than at the call site, so
    an objective declaring a profile nobody deploys cannot be written down at all.

    Delete this and `RECOVERY_OBJECTIVES` can promise figures for `medium`, which no install
    is ever on, and `profiles_without_objectives` will still report full coverage of the
    real ones."""
    with pytest.raises(Exception, match="profile"):
        RecoveryObjective(
            profile="medium", rpo_seconds=60, rto_seconds=60, because="sounds reasonable"
        )


def test_the_recovery_times_are_stated_and_not_zero() -> None:
    """A zero recovery point is a promise to lose nothing ever, which no backup schedule can
    keep, and it is what a field gets initialised to.

    Delete this and a profile can promise instant recovery of everything."""
    with pytest.raises(ReliabilityError, match="recovery point"):
        RecoveryObjective(profile="lite", rpo_seconds=0, rto_seconds=60, because="ambitious")

    with pytest.raises(ReliabilityError, match="be back in"):
        RecoveryObjective(profile="lite", rpo_seconds=60, rto_seconds=0, because="ambitious")


def test_a_tighter_profile_does_not_promise_a_looser_recovery() -> None:
    """The ordering is the only thing making three profiles mean anything: `full` runs more
    and is expected to recover faster, so a `full` objective looser than `lite` would be
    somebody editing one line without reading the other two.

    Delete this and the three figures can drift into any order, and a client upgrading to a
    larger profile is quietly promised less."""
    by_name = {one.profile: one for one in RECOVERY_OBJECTIVES}

    assert by_name["lite"].rpo_seconds >= by_name["standard"].rpo_seconds
    assert by_name["standard"].rpo_seconds >= by_name["full"].rpo_seconds
    assert by_name["lite"].rto_seconds >= by_name["standard"].rto_seconds
    assert by_name["standard"].rto_seconds >= by_name["full"].rto_seconds


def test_the_declared_objective_for_a_profile_is_the_one_that_comes_back() -> None:
    """**A positive lookup, written because a mutation of the match survived.**

    The refusal test above passes for an implementation that matches nothing and raises for
    every profile, which is a function that refuses correctly and answers nothing. `alerts`
    reads its threshold through here, so a lookup that never matches turns every recovery
    alert into an exception.

    Delete this and the lookup can be broken while every refusal test stays green."""
    lite = recovery_objective("lite")

    assert lite.profile == "lite"
    assert lite.rpo_seconds == max(one.rpo_seconds for one in RECOVERY_OBJECTIVES)


def test_the_unfillable_timing_field_is_named_among_the_measurement_gaps() -> None:
    """The third finding, asserted on its own because the test above checks the other two and
    a mutation of this branch survived it.

    It is the finding that says even the partial timing the ledger declares is empty on every
    row, which is what stops somebody concluding that `time_to_first_token_ms` is a workable
    proxy for a lane percentile.

    Delete this and the branch can be removed and `measurement_gaps` under-reports."""
    assert any("time_to_first_token_ms" in one for one in measurement_gaps())
    assert not any(
        "time_to_first_token_ms" in one
        for one in measurement_gaps(("received_at", "completed_at", "stage", "status"), ())
    )


# ------------------------------------------- the refusals a first mutation run found unwatched
#
# Every test below was written after `.scratch/m30_guard_audit.py` mutated each `if` in
# `brain.ops.reliability` and reported it surviving. Blank strings are tested as `" "` as
# well as `""`, because a reason arriving from a form or a settings file is whitespace far
# more often than it is empty and a bare falsiness check lets whitespace through.
def test_an_objective_that_states_no_reason_for_its_figures_is_refused() -> None:
    """Three classes carry a required `because` and none of them had a test for it.

    The reason is the whole difference between an objective and a number. An eight-second
    target with no argument behind it is one somebody relaxes to twelve during a bad week,
    because there is nothing on the page saying what twelve costs.

    Delete this and the field is optional in practice, and the next company inherits three
    figures with no case for any of them."""
    for reason in ("", "   "):
        with pytest.raises(ReliabilityError, match="states no reason"):
            LaneObjective(lane=Lane.FAST, p95_ms=500, success_rate=0.99, because=reason)
        with pytest.raises(ReliabilityError, match="states no reason"):
            StageObjective(stage=Stage.CACHE, p95_ms=20, because=reason)
        with pytest.raises(ReliabilityError, match="state no reason"):
            RecoveryObjective(profile="lite", rpo_seconds=60, rto_seconds=60, because=reason)


def test_a_lane_promising_a_percentile_of_nothing_is_refused() -> None:
    """Zero is not "no target", it is a promise to answer instantly, and it is what the field
    holds when somebody means `None`.

    The distinction matters here more than in most places: `None` is a deliberate statement
    that a percentile is the wrong instrument for this lane, and a zero would be read by
    `attainment` as a target every request misses.

    Delete this and the task lane's argued absence and a mistyped zero become the same
    thing."""
    with pytest.raises(ReliabilityError, match="promises a p95 of 0ms"):
        LaneObjective(lane=Lane.TASK, p95_ms=0, success_rate=0.99, because="no target")

    assert LaneObjective(lane=Lane.TASK, p95_ms=None, success_rate=0.99, because="none").p95_ms is (
        None
    )


def test_an_operation_class_with_no_name_or_no_reason_is_refused() -> None:
    """An operation class with no name classifies nothing, and `retry_class_for` matches on
    that name, so a blank one is a row nothing can ever look up sitting in a table that looks
    complete.

    The reason is required for the same argument as an objective's: this is the table
    somebody edits during an incident, and a row with no case behind it is the one they
    change.

    Delete this and the classification can grow rows nobody can reach or account for."""
    for name in ("", "   "):
        with pytest.raises(ReliabilityError, match="no name"):
            OperationClass(
                name=name, has_side_effect=False, retry=RetryClass.SAFE, because="a read"
            )
    for reason in ("", "   "):
        with pytest.raises(ReliabilityError, match="no reason attached"):
            OperationClass(
                name="read a row", has_side_effect=False, retry=RetryClass.SAFE, because=reason
            )
