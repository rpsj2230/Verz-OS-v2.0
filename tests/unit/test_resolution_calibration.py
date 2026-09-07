"""The offline fit, the document it exports, and the three ways it could lie quietly.

`tests/unit/test_cascade.py` holds the online half: the weights are declared, nothing measured
them, and a table claims calibration only by naming an export. These are about the other end.
Two of them are the ones worth reading twice.

**The recovery test is the only thing that says the arithmetic is right.** Expectation-
maximisation converges to something for any input, and something is not a fit. So the extract
is generated from parameters this file chose, at population scale, and the test is that the fit
finds them again. A test that asserted the fit converged, or that its weights were positive,
would pass over an implementation with the maximisation step written backwards.

**The inversion test is about a failure that has no symptoms.** The swapped solution has the
same likelihood, so nothing downstream fails: the stages run, the thresholds hold, the queue
renders, and the wrong pairs merge. It is caught here or it is caught by somebody noticing that
two unrelated companies were joined.

`tests/invariants/test_no_ml_on_the_request_path.py` holds the boundary this module sits behind
and is where M14.4.5 is asserted; nothing here duplicates it.

Task ids: M14.3.5, M14.4.2, M14.4.3, M14.4.4
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from itertools import combinations
from math import log2
from pathlib import Path

import pytest

from brain.resolution.calibration import (
    CALIBRATION_PERIOD,
    INITIAL_M,
    INITIAL_MATCH_RATE,
    INITIAL_U,
    MIN_REF_CHARS,
    OFFLINE_TOOLING,
    PROBABILITY_FLOOR,
    FellegiSunter,
    PatternCount,
    ToolingStep,
    WeightExport,
    drift,
    due,
    export,
    from_document,
    promote,
    tooling_gaps,
    train,
    unbuilt_steps,
    weight_of,
)
from brain.resolution.canonical import ResolutionError
from brain.resolution.cascade import DECLARED_WEIGHTS, Feature
from brain.resolution.guardrails import DECISIVE_WEIGHT, STRONG_WEIGHT, SUPPORTING_WEIGHT, Strength

SRC = Path(__file__).resolve().parents[2] / "src" / "brain"

#: Four features and the parameters the extract below is generated from. Chosen so the four
#: weights land in four different bands, which is what makes the drift tests further down
#: about band crossings rather than about decimals.
FITTED: tuple[Feature, ...] = (
    Feature.UEN,
    Feature.DOMAIN,
    Feature.NAME_EXACT,
    Feature.COUNTRY,
)
TRUE_MATCH_RATE = 0.2
TRUE_M: dict[Feature, float] = {
    Feature.UEN: 0.95,
    Feature.DOMAIN: 0.85,
    Feature.NAME_EXACT: 0.75,
    Feature.COUNTRY: 0.60,
}
TRUE_U: dict[Feature, float] = {
    Feature.UEN: 0.02,
    Feature.DOMAIN: 0.10,
    Feature.NAME_EXACT: 0.05,
    Feature.COUNTRY: 0.30,
}

#: Large enough that rounding each pattern's expected count to a whole number of pairs moves
#: the maximum by far less than the tolerance the recovery test asserts.
POPULATION = 10_000_000


def _population(
    *,
    match_rate: float = TRUE_MATCH_RATE,
    m: dict[Feature, float] | None = None,
    u: dict[Feature, float] | None = None,
    pairs: int = POPULATION,
) -> list[PatternCount]:
    """The extract a perfectly representative sample of this model would produce.

    Every one of the sixteen patterns, with the count the model implies. Generated rather than
    sampled, because a sampled extract makes the recovery test a statement about a random seed
    and the property being checked is about the estimator.
    """
    m_values = TRUE_M if m is None else m
    u_values = TRUE_U if u is None else u
    counts: list[PatternCount] = []
    for size in range(len(FITTED) + 1):
        for combo in combinations(FITTED, size):
            pattern = frozenset(combo)
            as_match = match_rate
            as_other = 1.0 - match_rate
            for feature in FITTED:
                agreed = feature in pattern
                as_match *= m_values[feature] if agreed else 1.0 - m_values[feature]
                as_other *= u_values[feature] if agreed else 1.0 - u_values[feature]
            counts.append(PatternCount(pattern=pattern, pairs=round(pairs * (as_match + as_other))))
    return counts


def _fitted() -> FellegiSunter:
    return train(_population(), features=FITTED)


# ------------------------------------------------------ the estimator itself (M14.4.2)
def test_the_fit_recovers_the_probabilities_the_extract_was_generated_from() -> None:
    """**The only test here that says the arithmetic is right rather than that it ran.**

    Expectation-maximisation converges to something for every input. Asserting that it
    converged, or that the weights came out positive, or that the strongest feature got the
    largest one, all pass over an implementation whose maximisation step divides by the wrong
    total. The extract is therefore generated from parameters chosen in this file, at
    population scale, and the claim is that the fit finds those parameters again.

    Both classes are checked, not just the match class. A maximisation step that computed the
    unmatch probabilities from the same posterior weights as the match ones would recover m
    correctly and put u equal to it, which sends every weight to nought while looking like a
    working fit.

    Delete this and the estimator can be wrong in any way that still converges, which is most
    of the ways it can be wrong."""
    model = _fitted()

    assert model.converged, f"the fit stopped after {model.iterations} iterations"
    assert model.match_rate == pytest.approx(TRUE_MATCH_RATE, abs=1e-3)
    for feature in FITTED:
        assert model.m[feature] == pytest.approx(TRUE_M[feature], abs=1e-3), feature.value
        assert model.u[feature] == pytest.approx(TRUE_U[feature], abs=1e-3), feature.value
        expected = log2(TRUE_M[feature] / TRUE_U[feature])
        assert model.weights()[feature] == pytest.approx(expected, abs=1e-2), feature.value


def test_a_feature_that_agrees_equally_in_both_classes_is_worth_nothing() -> None:
    """The property that makes a weight a weight: it is evidence, and a feature that agrees as
    often among non-matches as among matches is evidence for nothing.

    Asserted against the arithmetic rather than against a fitted figure, so it holds whatever
    the estimator does: log2 of one is nought, and the two probabilities being equal is the
    only input that produces it.

    Delete this and a weight can be defined as m alone, which makes a field that everybody
    shares into the strongest evidence in the table."""
    assert weight_of(0.5, 0.5) == 0.0
    assert weight_of(0.9, 0.9) == 0.0
    assert weight_of(0.9, 0.1) > 0.0
    assert weight_of(0.1, 0.9) < 0.0


def test_the_probability_floor_still_leaves_room_for_a_decisive_feature() -> None:
    """The floor is chosen against `guardrails.DECISIVE_WEIGHT` and not by taste.

    Its job is to keep a weight finite: a feature that agreed on every match and no non-match
    in the extract has u of nought and an infinite weight, and one infinite term makes every
    threshold meaningless. Its cost is that it caps how strong a feature can be, so the figure
    has to leave a genuinely decisive feature able to reach the top band. Stated as that
    relation rather than as the number, so the number cannot be changed without the relation
    being re-checked.

    Delete this and the floor can be raised to something comfortable like a tenth, which caps
    every weight at about three and a third and makes it impossible for any feature to render
    as decisive."""
    assert PROBABILITY_FLOOR > 0.0
    assert log2((1.0 - PROBABILITY_FLOOR) / PROBABILITY_FLOOR) >= DECISIVE_WEIGHT

    capped = weight_of(1.0, 0.0)
    assert capped == pytest.approx(log2((1.0 - PROBABILITY_FLOOR) / PROBABILITY_FLOOR))
    assert capped >= DECISIVE_WEIGHT


def test_the_search_starts_where_matches_are_rare_and_agree_more() -> None:
    """The starting point is the identifiability constraint, expressed before the search runs.

    Both classes fit the same likelihood with their labels swapped, so where the search starts
    decides which of the two it finds. Matches are the rare class in any candidate set worth
    scoring, and the class called match must be the one that agrees more. Asserted as two
    relations between the constants rather than as three figures, because the figures may be
    tuned and the relations may not.

    Delete this and the seed can be set anywhere, including inside the basin of the inverted
    solution, and the refusal that catches inversion becomes the thing that fires on every
    run."""
    assert INITIAL_MATCH_RATE < 0.5
    assert INITIAL_M > INITIAL_U


def test_an_extract_that_cannot_identify_the_model_is_refused_rather_than_fitted() -> None:
    """Two parameters per feature plus a match rate, and fewer patterns than that is a ridge.

    A fit over three patterns and four features returns its starting point with an iteration
    count on it, and that starting point exports as a weight table nobody can tell from a
    measured one. Refusing is the only honest answer, because there is no reading of the data
    that produces the parameters.

    The empty extract is here too, and it is the case a caller reaches first: a blocking pass
    that matched nothing hands this function an empty list, and a fit over no pairs would
    otherwise return the seed.

    Delete this and a calibration run over a tiny extract produces a confident-looking table."""
    tiny = [
        PatternCount(pattern=frozenset({Feature.UEN}), pairs=10),
        PatternCount(pattern=frozenset(), pairs=90),
    ]
    with pytest.raises(ResolutionError, match="identify"):
        train(tiny, features=FITTED)

    with pytest.raises(ResolutionError, match="no pairs"):
        train([], features=FITTED)

    with pytest.raises(ResolutionError, match="no features"):
        train(_population(), features=[])


def test_a_pattern_naming_a_feature_the_fit_was_not_asked_for_is_refused() -> None:
    """A feature in the data and not in the parameter list is silently treated as never
    agreeing, which reports a weight of nought as a measurement.

    That is the quiet version of the mistake: the fit runs, the export loads, and one feature's
    weight is a fact about the parameter list rather than about the data. Refusing at the input
    is the only place it is visible.

    Delete this and an extract built against a newer cascade fits against an older one, and the
    feature that was added is measured as worthless."""
    extract = [*_population(), PatternCount(pattern=frozenset({Feature.PHONE}), pairs=5)]

    with pytest.raises(ResolutionError, match="phone"):
        train(extract, features=FITTED)


# ------------------------------------------------------------- the export (M14.3.5, M14.4.3)
def test_a_fit_with_its_labels_swapped_is_refused_rather_than_exported() -> None:
    """**The failure with no symptoms.** The swapped solution is the same likelihood, so
    expectation-maximisation cannot prefer the right one and nothing downstream notices: the
    stages run, the thresholds hold, the review queue renders, and every weight has the wrong
    sign, so a UEN agreement becomes evidence that two records are different companies.

    Built directly rather than fitted, because reaching an inverted fit through `train` needs a
    seed inside the other basin and the test would then be about the seed. The check being
    tested is the one on the way out, which is where it has to be: a caller holding a
    `FellegiSunter` must not be able to skip it.

    Delete this and an inverted fit exports, and the merges it produces are the wrong ones with
    confident-looking weights attached.

    The sibling is the export that works, one test below."""
    inverted = FellegiSunter(
        match_rate=0.2,
        m={one: TRUE_U[one] for one in FITTED},
        u={one: TRUE_M[one] for one in FITTED},
        iterations=12,
        converged=True,
        pairs=1000,
    )
    assert inverted.labels_are_inverted() is True

    with pytest.raises(ResolutionError, match="labels swapped"):
        export(inverted, ref="em-2026-09-07", version="v1")

    assert _fitted().labels_are_inverted() is False


def test_a_fit_that_ran_out_of_iterations_cannot_become_an_export() -> None:
    """A fit that did not converge has parameters that are wherever the search was when it
    stopped, and exporting them puts an arbitrary table behind a calibration reference.

    `converged` is reported rather than raised inside `train`, because a run that ran out is
    something an operator should be able to look at; the refusal belongs at the export, which
    is the artefact that travels.

    Delete this and a job that timed out ships its intermediate state as a measurement."""
    stopped = train(_population(), features=FITTED, max_iterations=1)
    assert stopped.converged is False

    with pytest.raises(ResolutionError, match="without converging"):
        export(stopped, ref="em-2026-09-07", version="v1")


def test_an_export_is_the_only_thing_in_this_repository_that_calls_a_table_calibrated() -> None:
    """**`WeightTable.calibrated` is only as good as the strings that reach `calibration_ref`.**

    The property `test_cascade` asserts is that there is no boolean to set. This is the other
    half: the field is set in exactly one place in `src/brain`, and that place sets it from a
    reference this module validated. Found by parsing rather than by searching, so a mention in
    a docstring is not a call.

    Delete this and a second caller sets the field from a hand-typed string, and every table in
    the system can call itself calibrated."""
    setters: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and any(
                keyword.arg == "calibration_ref" for keyword in node.keywords
            ):
                setters.append(path.relative_to(SRC).as_posix())

    assert setters == ["resolution/calibration.py"], setters


def test_a_reference_that_names_nothing_is_refused_and_a_real_one_is_accepted() -> None:
    """The grammar is what stops the honesty guard being satisfied by a word meaning yes.

    `calibrated` is true of any table whose reference is a non-empty string, so "yes", "done"
    and "calibrated" all satisfy it. A reference names a job and a run, which is at least two
    parts and a separator, and that is the shape a reviewer can see is missing.

    Both halves: the refusals, and a real reference producing a table that reports itself
    calibrated and names what calibrated it. "a-b" is in the refusals because it satisfies the
    grammar and is too short to name a job and a run, which is the only case `MIN_REF_CHARS`
    decides on its own.

    Delete this and the reference can be any string at all, which makes the property derived
    from it a property of nothing."""
    for bad in ("yes", "done", "calibrated", "em2026", "", "EM-2026-09-07", "em 2026", "a-b"):
        with pytest.raises(ResolutionError, match="export reference"):
            WeightExport(
                ref=bad,
                version="v1",
                weights=dict(DECLARED_WEIGHTS.weights),
                pairs=1,
                iterations=1,
            )

    good = WeightExport(
        ref="em-2026-09-07",
        version="fitted-v1",
        weights=dict(DECLARED_WEIGHTS.weights),
        pairs=99,
        iterations=7,
    )
    table = good.to_weight_table()
    assert len("em-2026-09-07") >= MIN_REF_CHARS
    assert table.calibrated is True
    assert table.calibration_ref == "em-2026-09-07"
    assert DECLARED_WEIGHTS.calibrated is False


def test_an_export_that_fitted_some_of_the_features_cannot_become_an_online_table() -> None:
    """An unweighted feature contributes nothing to the sum and is indistinguishable from one
    that never agreed, which is `WeightTable`'s own argument for refusing a partial table.

    It matters here because a real fit covers whatever the extract had, and the extract will
    not have every feature. The refusal is what stops a partial fit from silently zeroing the
    features it did not measure. `drift` compares only what the candidate fitted for the same
    reason, and the two rules meet at exactly this point.

    Delete this and a fit over four features promotes a table in which the other seven weigh
    nothing, and the cascade goes on scoring with them."""
    model = _fitted()
    partial = export(model, ref="em-2026-09-07", version="partial-v1")
    assert set(partial.weights) == set(FITTED)

    with pytest.raises(ResolutionError, match="no weight for"):
        partial.to_weight_table()


def test_an_export_survives_the_document_it_travels_in() -> None:
    """The artefact is a document rather than a serialised object, so the online side never
    deserialises anything a training job produced.

    A round trip is the whole claim, and it is asserted on every field rather than on the
    weights alone: an export that lost its reviewer on the way through would promote without
    anybody having read it, which is the one field whose loss has a consequence.

    Delete this and the document format drifts from the type, and an export written last week
    loads with its reviewer missing."""
    model = _fitted()
    original = export(model, ref="em-2026-09-07", version="fitted-v1", reviewed_by="rupash")

    restored = from_document(original.to_document())

    assert restored == original
    assert restored.reviewed_by == "rupash"
    assert original.to_document()["weights"][Feature.UEN.value] == pytest.approx(
        original.weights[Feature.UEN]
    )


def test_a_document_naming_a_feature_this_cascade_does_not_compare_is_refused() -> None:
    """Skipping the unknown name is the tempting behaviour and it produces the wrong error.

    An export fitted against a different vocabulary would load with the renamed feature missing,
    `WeightTable` would refuse it for having no weight for that feature, and the message would
    name the new feature rather than the old export. Refusing at the load names the actual
    problem.

    Delete this and an export from a different cascade version loads far enough to fail
    somewhere else."""
    document = {
        "ref": "em-2026-09-07",
        "version": "v1",
        "pairs": 10,
        "iterations": 3,
        "weights": {"uen": 5.0, "handwriting": 1.0},
    }

    with pytest.raises(ResolutionError, match="handwriting"):
        from_document(document)

    with pytest.raises(ResolutionError, match="weights mapping"):
        from_document({"ref": "em-2026-09-07", "version": "v1"})


# ---------------------------------------------------- the schedule and the drift (M14.4.4)
def test_the_calibration_runs_weekly() -> None:
    """The leaf's word, and a cadence a test can hold to something outside the constant.

    Compared against a week built a different way, so changing the declared figure changes one
    side only. `due` is asserted either side of the boundary rather than at it alone, because a
    comparison written with the wrong operator is right at exactly one instant.

    Delete this and the period can drift to a month with the docstring still saying weekly."""
    assert timedelta(days=7) == CALIBRATION_PERIOD

    last = datetime(2026, 9, 1, tzinfo=UTC)
    assert due(last, last + timedelta(days=6, hours=23)) is False
    assert due(last, last + timedelta(days=7)) is True
    assert due(last, last + timedelta(days=9)) is True


def test_a_weight_that_crosses_a_band_is_refused_until_somebody_has_read_it() -> None:
    """**The review is what makes the weekly job a schedule rather than a cron line.**

    `guardrails.Evidence.render` shows a band and never a number, so the reviewable event is a
    weight crossing a band boundary: that is the point at which a reviewer starts being told
    something different about a pair. A job that promoted its own fit would change that sentence
    with nobody reading it.

    The sibling is the promotion that works: a candidate whose weights move without crossing a
    band needs no reviewer, because there is no sentence to read, and it promotes unsigned.

    Delete this and the weekly job silently re-words every review item in the queue."""
    weights = dict(DECLARED_WEIGHTS.weights)
    crossing = {**weights, Feature.COUNTRY: DECISIVE_WEIGHT + 1.0}
    unsigned = WeightExport(
        ref="em-2026-09-14", version="fitted-v2", weights=crossing, pairs=500, iterations=9
    )

    report = drift(DECLARED_WEIGHTS, unsigned)
    assert report.needs_review is True
    assert [one.feature for one in report.crossings] == [Feature.COUNTRY]
    assert report.crossings[0].before_band is Strength.SUPPORTING
    assert report.crossings[0].after_band is Strength.DECISIVE

    with pytest.raises(ResolutionError, match="names no reviewer"):
        promote(DECLARED_WEIGHTS, unsigned)

    signed = WeightExport(
        ref="em-2026-09-14",
        version="fitted-v2",
        weights=crossing,
        pairs=500,
        iterations=9,
        reviewed_by="rupash",
    )
    assert promote(DECLARED_WEIGHTS, signed).calibrated is True


def test_a_move_inside_one_band_needs_no_reviewer_and_is_reported_as_no_change() -> None:
    """The guard tested only by its refusals is satisfied by a function that refuses
    everything, so this is the sibling that says the weekly job can actually promote.

    It also fixes what drift means. A weight moving from just above supporting to just below
    strong is a large move in figures and no move at all in what a reviewer reads, so it is
    reported as unchanged. Reporting it as a change would put every week's noise in front of a
    person and teach them to approve.

    Delete this and drift can be defined on the figures, and the review queue for the weekly
    job fills up with moves nobody can see the effect of."""
    weights = dict(DECLARED_WEIGHTS.weights)
    midband = SUPPORTING_WEIGHT + (STRONG_WEIGHT - SUPPORTING_WEIGHT) / 2
    nudged = {**weights, Feature.COUNTRY: midband}
    candidate = WeightExport(
        ref="em-2026-09-14", version="fitted-v3", weights=nudged, pairs=500, iterations=9
    )

    report = drift(DECLARED_WEIGHTS, candidate)
    assert report.needs_review is False
    assert report.crossings == ()
    assert any("stayed supporting" in line for line in report.explain())

    promoted = promote(DECLARED_WEIGHTS, candidate)
    assert promoted.weight_for(Feature.COUNTRY) == pytest.approx(nudged[Feature.COUNTRY])


def test_a_drift_report_is_written_in_the_bands_a_reviewer_reads_and_carries_no_figures() -> None:
    """The rendering rule `guardrails.Evidence.render` follows, applied to the other surface a
    person reads: bands in words, and no number for anybody to threshold on.

    A reviewer shown 4.1 next to 3.9 does arithmetic, and the arithmetic is a cutoff they
    invented on a scale that has just changed underneath them, which is the worst possible
    moment for it.

    Delete this and the drift report grows a column of decimals, which is the most natural
    thing in the world to add to it."""
    weights = dict(DECLARED_WEIGHTS.weights)
    moved = {**weights, Feature.COUNTRY: DECISIVE_WEIGHT + 1.0}
    candidate = WeightExport(
        ref="em-2026-09-14", version="fitted-v4", weights=moved, pairs=500, iterations=9
    )

    lines = drift(DECLARED_WEIGHTS, candidate).explain()

    assert "country moved from supporting to decisive" in lines
    for line in lines:
        assert not any(character.isdigit() for character in line), line


# --------------------------------------------- the job that is not built (M14.4.1, not claimed)
def test_no_step_of_the_offline_job_claims_to_have_been_verified_against_its_package() -> None:
    """M14.4.1 asks for a Splink job against a DuckDB export and neither package is installed.

    The register is what makes that absence checkable rather than remembered, and the check is
    the one `brain.ops.jobs.driver_mapping_gaps` makes about its own driver: a row claiming
    verification while the package cannot be imported is the sentence a reader trusts, so it is
    the finding. The declared rows are all False, and the control below proves the check can
    fire, because a check that has never been seen to fail is a check nobody has tested.

    Delete this and a row can be marked verified to make the register look finished, which is
    exactly the pressure a register like this is under."""
    assert tooling_gaps() == ()
    assert all(step.verified is False for step in OFFLINE_TOOLING)
    assert {step.package for step in OFFLINE_TOOLING} == {"splink", "duckdb"}

    lying = (
        ToolingStep(
            ours="train",
            theirs="the estimator",
            package="splink",
            note="claims a verification nobody performed",
            verified=True,
        ),
    )
    findings = tooling_gaps(lying)
    assert len(findings) == 1
    assert "splink" in findings[0]


def test_the_register_names_the_parts_of_the_job_this_repository_does_not_have() -> None:
    """The rows marked unbuilt are what say M14.4 is not finished, and they are the reason the
    register exists rather than a paragraph.

    A register reads as a completed mapping, and a reader skimming it takes the presence of a
    row for the presence of the thing. Two steps have no counterpart here: nothing decides
    which pairs are compared, and nothing produces an extract of real pairs to fit. Those two
    are why M14.4.1 is not claimed by any module in this repository.

    A step that does not exist cannot have been verified against anything, which is asserted as
    a refusal at construction rather than left to `tooling_gaps`: the register would otherwise
    admit a row that is absent and checked at the same time.

    Delete this and the register can lose the two rows that say what is missing, leaving a
    mapping that looks complete."""
    assert set(unbuilt_steps()) == {"the blocking pass", "the labelled sample"}

    with pytest.raises(ResolutionError, match="does not exist"):
        ToolingStep(
            ours="the blocking pass",
            theirs="blocking rules",
            package="splink",
            note="absent and checked at once",
            verified=True,
            built=False,
        )
