"""Two instruments that must not be averaged, and a draw a reviewer can repeat by hand.

The tests here are about two different ways a quality process stops being one. The first is
arithmetic: two shares printed together are read as two readings of the same thing, and a
single figure mixing a mechanical check of everything with a person's judgement of twenty
answers is a number nobody can act on. The second is disclosure: an annotation queue leaks
through its own shape, because a sample stratified by department states how the day's
questions were spread and a sample carrying its own fraction states the day's volume exactly.

The sampler's fixtures are two hundred request ids drawn down to eight, deliberately. A
sampling test run over a handful of items cannot tell a sample from the population, and a
draw asserted at a quota larger than its input is satisfied by a function that returns
everything it was given.

Task ids: M28.3.3
"""

from __future__ import annotations

import ast
import hashlib
import inspect
from dataclasses import fields as dataclass_fields
from datetime import date, timedelta

import pytest

from brain.gate.compose import new_trace_ref
from brain.ops import sampling
from brain.ops.canaries import Finding
from brain.ops.evaluation import PERMISSION_FAILURES_ALLOWED, QUALITY_FLOOR, score
from brain.ops.feedback import FlagReason
from brain.ops.sampling import (
    DAILY_ANNOTATION_QUOTA,
    DISAGREEMENTS_TOLERATED,
    SEED_MAX_LENGTH,
    AutomatedReading,
    DailySample,
    HumanAnnotation,
    SamplingError,
    annotated_cases,
    annotation_report,
    automated_cases,
    automated_report,
    check_seed,
    draw,
    draw_key,
    sampler_gaps,
    severity_of_finding,
)
from tests.fixtures.company import person

#: A published short name, of the shape a reviewer reads off the top of a queue.
SEED = "autumn-2026"

#: The day a sample is drawn for. Fixed, because a draw that depends on today is a draw
#: nobody can check tomorrow.
DAY = date(2026, 9, 4)

#: Two hundred requests and a quota of eight, so the sampler has to choose. A population
#: smaller than the quota tests the identity function.
POPULATION: tuple[str, ...] = tuple(f"req_{n:04d}" for n in range(200))
QUOTA = 8


def reviewers_own_draw(
    *, seed: str, day: date, request_ids: tuple[str, ...], quota: int
) -> list[str]:
    """The published recipe, carried out here rather than borrowed from the module.

    The claim being checked is that a reviewer with the seed, the date and the day's request
    ids can reproduce the sample with a hash function and a sort. So this computes the digest
    itself: borrowing `draw_key` would test that `draw` calls it and would say nothing about
    whether the recipe in the docstring is the recipe in the code.
    """
    keyed = sorted(
        (hashlib.sha256("\n".join((seed, day.isoformat(), rid)).encode()).hexdigest(), rid)
        for rid in set(request_ids)
    )
    return [rid for _, rid in keyed[:quota]]


def sound(request_id: str, *, annotator: str = "u_hr") -> HumanAnnotation:
    return HumanAnnotation(request_id=request_id, annotator=annotator, sound=True)


def unsound(
    request_id: str, *, fault: FlagReason = FlagReason.WRONG_FACT, annotator: str = "u_hr"
) -> HumanAnnotation:
    return HumanAnnotation(request_id=request_id, annotator=annotator, sound=False, fault=fault)


# ------------------------------------------------------------------------ the draw


def test_a_day_is_sampled_the_same_way_by_anybody_holding_the_seed_and_the_day() -> None:
    """**"We annotated a random two per cent" is not a claim anybody can check.** The draw is
    a digest and not a generator, so a reviewer with the seed, the date and the day's request
    ids repeats it with a hash and a sort: no state, no cursor, no stored random stream.

    Reproduced here from the recipe rather than from `draw_key`, so that changing how the
    material is assembled fails this rather than moving the expectation with it.

    Delete this and the draw becomes a seeded generator whose sequence is not promised across
    Python releases, and reproducing last March's sample becomes an archaeology exercise."""
    sample = draw(seed=SEED, day=DAY, request_ids=POPULATION, quota=QUOTA)

    assert list(sample.request_ids) == reviewers_own_draw(
        seed=SEED, day=DAY, request_ids=POPULATION, quota=QUOTA
    )
    assert sample.seed == SEED
    assert sample.day == DAY
    assert len(sample.request_ids) == QUOTA < len(POPULATION)
    assert set(sample.request_ids) < set(POPULATION), "the sample is the population"
    assert draw(seed=SEED, day=DAY, request_ids=POPULATION, quota=QUOTA) == sample


def test_the_same_population_on_the_next_day_is_a_different_sample() -> None:
    """A sample keyed only on the seed would annotate the same requests every day for as long
    as they existed, which is a queue that looks random and covers a fixed slice.

    Delete this and the day can be dropped from the key, and the human tier reads the same
    corner of the system for ever."""
    today = draw(seed=SEED, day=DAY, request_ids=POPULATION, quota=QUOTA)
    tomorrow = draw(seed=SEED, day=DAY + timedelta(days=1), request_ids=POPULATION, quota=QUOTA)

    assert today.request_ids != tomorrow.request_ids


def test_a_different_seed_draws_a_different_sample_from_the_same_day() -> None:
    """The other half of the key. A draw ignoring the seed is reproducible and unauditable in
    the way that matters: nobody could ever have drawn it differently, so publishing the seed
    proves nothing.

    Delete this and the seed becomes decoration printed above a queue it did not choose."""
    first = draw(seed=SEED, day=DAY, request_ids=POPULATION, quota=QUOTA)
    second = draw(seed="spring-2027", day=DAY, request_ids=POPULATION, quota=QUOTA)

    assert first.request_ids != second.request_ids


def test_the_draw_does_not_depend_on_the_order_the_ids_arrived_in() -> None:
    """**A caller must not be able to move a request into or out of the sample by sorting its
    input**, which a "first n after shuffling" draw would allow and which nothing downstream
    would ever notice.

    Three orderings of one population, including one where every id is reversed, and the
    same eight come back.

    Delete this and the sampler acquires an order dependence, and whichever job feeds it
    decides what gets annotated."""
    rotated = POPULATION[137:] + POPULATION[:137]
    expected = draw(seed=SEED, day=DAY, request_ids=POPULATION, quota=QUOTA).request_ids

    assert draw(seed=SEED, day=DAY, request_ids=reversed(POPULATION), quota=QUOTA).request_ids == (
        expected
    )
    assert draw(seed=SEED, day=DAY, request_ids=rotated, quota=QUOTA).request_ids == expected


def test_the_same_request_twice_spends_one_annotation_and_not_two() -> None:
    """A sample containing one request twice spends two of the day's annotations on one
    answer, which is the scarcest thing in the tier being wasted silently.

    Delete this and a population assembled from two sources annotates its overlap twice."""
    doubled = POPULATION + POPULATION[:50]

    sample = draw(seed=SEED, day=DAY, request_ids=doubled, quota=QUOTA)

    assert len(set(sample.request_ids)) == len(sample.request_ids)
    assert (
        sample.request_ids
        == draw(seed=SEED, day=DAY, request_ids=POPULATION, quota=QUOTA).request_ids
    )


def test_a_sample_discloses_no_count_larger_than_the_quota_whatever_the_day_held() -> None:
    """**The bound the design can actually guarantee, asserted rather than assumed.** A busy
    day and a much busier day produce samples of identical size, so the annotator cannot read
    the day's volume off the length of their queue.

    The quiet day is the honest exception and is asserted too: when there are fewer requests
    than the quota the sample is the population, which is true of every sampler that returns
    items and is why the guarantee is a bound rather than a promise of nothing.

    Delete this and a proportional quota looks reasonable, and the size of the queue starts
    stating the size of the day."""
    busy = draw(seed=SEED, day=DAY, request_ids=POPULATION, quota=QUOTA)
    busier = draw(seed=SEED, day=DAY, request_ids=tuple(f"r{n}" for n in range(9000)), quota=QUOTA)

    assert len(busy.request_ids) == len(busier.request_ids) == QUOTA

    quiet = draw(seed=SEED, day=DAY, request_ids=("req_0001", "req_0002"), quota=QUOTA)
    assert len(quiet.request_ids) == 2


def test_the_sample_has_nowhere_to_record_what_it_left_behind() -> None:
    """**Twenty items and "a two per cent sample" is a thousand requests, stated exactly, by
    a field somebody added to be transparent.** The prose says the sample must disclose no
    population; this says there is no attribute one could arrive in.

    Delete this and `population: int` appears on the model for a progress bar, and every
    other test here passes because none of them read it."""
    names = {f.name for f in dataclass_fields(DailySample)}

    assert names == {"day", "seed", "request_ids"}
    for forbidden in (
        "population",
        "sampled_fraction",
        "fraction",
        "total",
        "remaining",
        "truncated",
        "count",
        "of",
    ):
        assert forbidden not in names, f"a sample can carry a {forbidden}"


def test_nothing_on_the_drawing_surface_can_stratify_or_weight_the_draw() -> None:
    """**A sample stratified by department tells the annotator how the day's questions were
    spread across departments**, which is a fact about volumes in places they may hold nothing
    in, and one weighted by cost tells them which departments spend.

    The scan is checked in both directions. Against the real surface it finds nothing, and
    against a function that takes the argument it exists to find, it names it: without that
    second half, deleting the body of `sampler_gaps` passes this test.

    Delete this and `department=` is added during a review meeting for even coverage, and
    nothing between it and production reads the signature."""
    assert sampler_gaps() == ()

    def stratified(*, seed: str, day: date, request_ids: tuple[str, ...], department: str) -> None:
        return None

    def by_cost(*, seed: str, cost: float) -> None:
        return None

    found = sampler_gaps((stratified, by_cost))

    assert len(found) == 2
    assert any("stratified" in one and "department" in one for one in found)
    assert any("by_cost" in one and "cost" in one for one in found)


def test_a_seed_that_looks_like_a_secret_is_refused_rather_than_published_by_accident() -> None:
    """The seed is carried on the sample and printed with the queue, so a seed somebody
    pasted from a vault is a secret published in an annotation header. The guard refuses the
    shapes a real token takes, and it is a guard and not a proof: a short lowercase name is
    indistinguishable from a short lowercase secret by any rule short of measuring entropy.

    Anchored on what `brain.gate.compose.new_trace_ref` mints, which is the shortest
    deliberately unguessable string this system produces, so raising the cap to admit one
    fails here.

    Delete this and an API key ends up printed above a queue of answers."""
    assert len(new_trace_ref()) > SEED_MAX_LENGTH
    assert check_seed(SEED) == SEED

    for bad in (new_trace_ref(), "Autumn-2026", "autumn_2026", "a3f2b91c4d5e6f708192a3b4", "ab"):
        with pytest.raises(SamplingError, match="not a published name"):
            check_seed(bad)

    with pytest.raises(SamplingError, match="not a published name"):
        draw(seed="Autumn-2026", day=DAY, request_ids=POPULATION, quota=QUOTA)


def test_a_request_id_that_names_nothing_is_refused_before_it_reaches_a_queue() -> None:
    """An empty id in the population puts a row in somebody's annotation queue that points at
    no request, and the annotator's only honest response is to skip it, which spends one of
    the day's annotations on nothing.

    Delete this and a gap in whatever assembles the day's ids becomes a gap in the queue."""
    with pytest.raises(SamplingError, match="empty"):
        draw(seed=SEED, day=DAY, request_ids=(*POPULATION, ""), quota=QUOTA)


def test_a_quota_nobody_could_work_is_refused() -> None:
    """A quota of zero draws nothing, and a queue nobody works is not a tier: it is a tier
    that reports "no faults found" every day for ever.

    Delete this and switching the human tier off looks exactly like running it."""
    for quota in (0, -1):
        with pytest.raises(SamplingError, match="draws nothing"):
            draw(seed=SEED, day=DAY, request_ids=POPULATION, quota=quota)


def test_the_key_cannot_be_collided_by_a_seed_that_ends_where_a_date_begins() -> None:
    """**Two genuinely different draws that concatenation would key identically.** A seed and
    a request id are both variable length and the date sits between them, so
    `"abc" + "2026-09-04" + "2026-09-04z"` and `"abc2026-09-04" + "2026-09-04" + "z"` are the
    same string. Joined with a separator they are not.

    Both seeds pass `check_seed`, so this is a pair somebody could actually publish rather
    than a shape invented to fail. Collisions of this kind are the classic defect in a keyed
    hash and they are silent: two different days, or two different seeds, quietly drawing one
    sample, with nothing saying which draw the queue belonged to.

    Delete this and the separator reads as tidiness, and the first person to shorten the key
    takes it out."""
    assert check_seed("abc") and check_seed("abc2026-09-04")

    left = draw_key(seed="abc", day=DAY, request_id="2026-09-04z")
    right = draw_key(seed="abc2026-09-04", day=DAY, request_id="z")

    assert "abc" + DAY.isoformat() + "2026-09-04z" == "abc2026-09-04" + DAY.isoformat() + "z"
    assert left != right


# ----------------------------------------------------------------- two instruments


def test_the_two_tiers_share_no_vocabulary_of_faults() -> None:
    """**The argument made structurally rather than in prose.** A machine's fault is a
    `brain.ops.canaries.Finding`: a token was present, two strings differed. A person's fault
    is a `brain.ops.feedback.FlagReason`: the answer was wrong, incomplete, out of date. The
    two have no member in common and there is no mapping between them, because there is no
    true one, and two instruments with no shared unit do not average.

    Delete this and the two enums acquire a member in common, which is the first step towards
    a mapping and the second towards one number."""
    machine = {f.value for f in Finding}
    people = {r.value for r in FlagReason}

    assert machine and people
    assert machine & people == set()
    assert {f.name for f in Finding} & {r.name for r in FlagReason} == set()


def test_no_function_here_takes_a_reading_and_an_annotation_at_once() -> None:
    """**There is no function anywhere in this module that takes both**, which is what stops
    the two tiers being combined: a caller who wants one number has to spell out a union by
    hand and will notice they are doing it.

    Asserted over the parsed annotations rather than over the module's text, because this
    module's own docstring names both types repeatedly and a substring search would be
    satisfied by the argument against the thing.

    Delete this and `combined_quality(readings, annotations)` is added for a console
    headline, and the number everybody wants is the one nobody can act on."""
    tree = ast.parse(inspect.getsource(sampling))
    signatures = {
        node.name: " ".join(
            ast.unparse(one.annotation)
            for one in (*node.args.args, *node.args.kwonlyargs, *node.args.posonlyargs)
            if one.annotation is not None
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }

    assert len(signatures) >= 8, "the walk found no functions and asserts nothing"
    assert "automated_cases" in signatures and "annotated_cases" in signatures
    for name, written in signatures.items():
        assert not ("AutomatedReading" in written and "HumanAnnotation" in written), name


def test_two_tiers_reading_the_same_figure_are_still_reported_as_two_things() -> None:
    """**Two shares printed on one screen with no labels are read as two measurements of the
    same thing.** This is that case exactly: a day where both tiers score 1.000, so the
    reported numbers are byte-identical and the only thing separating them is the coverage
    line each report carries.

    Delete this and the coverage lines look like decoration, somebody drops them to tidy the
    console, and the automated tier's silence about correctness starts reading as a
    statement about it."""
    ids = tuple(f"req_{n}" for n in range(10))
    readings = [AutomatedReading(request_id=one, passed=True) for one in ids]
    annotations = [sound(one) for one in ids]

    machine = automated_report(readings)
    people = annotation_report(annotations)

    assert machine[1:] == people[1:], "the two tiers scored differently and this proves nothing"
    assert machine[0] != people[0]
    assert machine[0] and people[0]

    for forbidden in ("combined", "overall", "quality_score", "together", "merged", "blended"):
        assert not any(forbidden in name for name in dir(sampling)), forbidden


def test_a_report_never_names_the_annotator_who_produced_it() -> None:
    """ "Meera marked nine of twenty wrong" is a performance statistic about a person,
    produced by a quality process nobody enrolled them in, and it makes the cheapest way to
    look good marking everything sound.

    The positive half is that the annotation does carry who judged it, so the work can be
    shared out. What must not happen is that reaching the report.

    Delete this and a per-annotator column appears on the console, which is the report
    everybody asks for and the one that changes how annotators annotate."""
    meera = person("u_hr").principal.id
    annotations = [unsound(f"req_{n}", annotator=meera) for n in range(3)]

    assert annotations[0].annotator == meera

    for line in annotation_report(annotations):
        assert meera not in line, line


def test_an_annotator_saying_the_answer_showed_too_much_lands_where_no_percentage_reaches() -> None:
    """One vocabulary for a flag and an annotation, because they are the same judgement made
    by different people at different times. So an annotator saying an answer showed somebody
    something they may not see lands in the class with a threshold of zero, and one saying an
    answer was out of date lands in the class with a floor.

    Anchored against `brain.ops.evaluation.score` rather than against the enum, so what is
    asserted is what the mapping does to a run.

    Delete this and every annotation becomes a quality case, and a disclosure a person spotted
    is averaged into a share that clears the floor."""
    ids = tuple(f"req_{n}" for n in range(20))
    leaked = [sound(one) for one in ids[1:]] + [
        unsound(ids[0], fault=FlagReason.SHOULD_HAVE_REFUSED)
    ]

    verdict = score(annotated_cases(leaked))

    assert verdict.may_merge is False
    assert verdict.permission_failures == (ids[0],)
    assert verdict.quality_share == 1.0

    stale = [sound(one) for one in ids[1:]] + [unsound(ids[0], fault=FlagReason.STALE)]
    ordinary = score(annotated_cases(stale))

    assert ordinary.may_merge is True
    assert ordinary.permission_failures == ()


def test_a_mechanical_finding_that_is_not_a_disclosure_is_not_scored_as_one() -> None:
    """Four of the five findings are permission outcomes and `PROJECTION_TOO_NARROW` is not:
    a catalogue withholding a tool the caller is entitled to is a broken product rather than
    a disclosure. Scoring it at a threshold of zero is how a suite acquires a class of failure
    people learn to override.

    Both directions, so the mapping cannot be satisfied by returning one class.

    Delete this and either every mechanical finding blocks a merge, or none of them do."""
    ids = tuple(f"req_{n}" for n in range(20))

    def run(fault: Finding) -> list[AutomatedReading]:
        return [AutomatedReading(request_id=one, passed=True) for one in ids[1:]] + [
            AutomatedReading(request_id=ids[0], passed=False, fault=fault)
        ]

    assert severity_of_finding(Finding.PROJECTION_TOO_NARROW) is not severity_of_finding(
        Finding.LEAKED
    )

    narrow = score(automated_cases(run(Finding.PROJECTION_TOO_NARROW)))
    assert narrow.may_merge is True
    assert narrow.quality_share == 0.95

    for disclosure in (
        Finding.LEAKED,
        Finding.REFUSAL_DISTINGUISHABLE,
        Finding.UNLOCKED,
        Finding.PROJECTION_TOO_WIDE,
    ):
        leaked = score(automated_cases(run(disclosure)))
        assert leaked.may_merge is False, disclosure
        assert leaked.permission_failures == (ids[0],)


def test_the_automated_tier_keys_on_a_request_and_carries_nobody() -> None:
    """The mechanical tier sees every request, so anything it carries is carried about
    everybody. A request id is a pointer; a principal, a department or an annotator is a
    person, and a reading is the wrong place for one.

    Delete this and `principal` appears on the reading for debugging, and the tier that
    covers everything starts recording who asked what."""
    names = {f.name for f in dataclass_fields(AutomatedReading)}

    assert names == {"request_id", "passed", "fault"}
    for forbidden in ("principal", "asker", "department", "annotator", "question", "answer"):
        assert forbidden not in names, f"a reading can carry a {forbidden}"

    cases = automated_cases([AutomatedReading(request_id="req_0007", passed=True)])
    assert [one.question_id for one in cases] == ["req_0007"]


def test_a_reading_that_passed_and_says_what_went_wrong_is_two_different_claims() -> None:
    """A reading that passed and carries a fault, or failed and says why nowhere, is one
    somebody has to guess about, and the guess is made by whoever reads the console next.

    The positive sibling is that both honest shapes construct, or the guard is satisfied by
    a model that refuses everything.

    Delete this and half the readings in a store say two things at once."""
    assert AutomatedReading(request_id="req_1", passed=True).fault is None
    assert AutomatedReading(request_id="req_1", passed=False, fault=Finding.LEAKED).passed is False

    with pytest.raises(SamplingError, match="one of the two is wrong"):
        AutomatedReading(request_id="req_1", passed=True, fault=Finding.LEAKED)
    with pytest.raises(SamplingError, match="says why nowhere"):
        AutomatedReading(request_id="req_1", passed=False)
    with pytest.raises(SamplingError, match="names nothing"):
        AutomatedReading(request_id="", passed=True)


def test_an_annotation_that_judges_without_saying_what_was_wrong_is_refused() -> None:
    """The same guard on the human side, and the same positive sibling. An annotation that
    says an answer was unsound and names no fault is a judgement nobody can act on, and an
    annotation with no annotator cannot be traced back to anything.

    Delete this and the human tier fills up with verdicts nobody can follow up."""
    assert sound("req_1").fault is None
    assert unsound("req_1").fault is FlagReason.WRONG_FACT

    with pytest.raises(SamplingError, match="carries a fault"):
        HumanAnnotation(
            request_id="req_1", annotator="u_hr", sound=True, fault=FlagReason.WRONG_FACT
        )
    with pytest.raises(SamplingError, match="says why nowhere"):
        HumanAnnotation(request_id="req_1", annotator="u_hr", sound=False)
    for blank in ("request_id", "annotator"):
        with pytest.raises(SamplingError, match="cannot be traced"):
            HumanAnnotation(
                request_id="" if blank == "request_id" else "req_1",
                annotator="" if blank == "annotator" else "u_hr",
                sound=True,
            )


# -------------------------------------------------------------------- the constants


def test_the_daily_quota_is_the_smallest_sample_that_can_express_the_floor() -> None:
    """**A sample too small cannot express the floor it is compared against at all.** At five
    annotations every possible reading is 1.0, 0.8, 0.6 and so on, and none of them is 0.9, so
    the figure is arithmetic wearing the clothes of a quality measurement.

    Asserted by running `brain.ops.evaluation.score` over a day at the quota and a day one
    short of it, with the tolerated number of disagreements in each: the first merges, the
    second does not. That anchors the quota against the scorer rather than against itself, so
    a quota moved in either direction fails here.

    Delete this and the quota can be set to any number somebody finds affordable, and the
    reading it produces is compared against a floor it cannot reach."""
    assert DISAGREEMENTS_TOLERATED > PERMISSION_FAILURES_ALLOWED

    def a_day(size: int) -> list[HumanAnnotation]:
        ids = [f"req_{n:03d}" for n in range(size)]
        return [unsound(one, fault=FlagReason.STALE) for one in ids[:DISAGREEMENTS_TOLERATED]] + [
            sound(one) for one in ids[DISAGREEMENTS_TOLERATED:]
        ]

    at_quota = score(annotated_cases(a_day(DAILY_ANNOTATION_QUOTA)))
    one_short = score(annotated_cases(a_day(DAILY_ANNOTATION_QUOTA - 1)))

    assert at_quota.quality_share >= QUALITY_FLOOR
    assert at_quota.may_merge is True
    assert one_short.quality_share < QUALITY_FLOOR
    assert one_short.may_merge is False


def test_no_baseline_is_recorded_over_a_days_annotations() -> None:
    """**A reading over twenty annotations moves by five percentage points when one annotator
    disagrees.** A baseline ratcheted against that fails builds on sampling noise, and a bar
    that fails on noise is a bar somebody raises until it stops failing, which is the ratchet
    running the wrong way.

    Asserted on the parsed imports rather than on behaviour, because behaviour today says
    nothing about what an import can acquire tomorrow.

    Delete this and the human tier grows a baseline, and the first strict Tuesday moves it."""
    tree = ast.parse(inspect.getsource(sampling))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert "score" in imported, "the import walk read nothing and asserts nothing"
    assert "accept_baseline" not in imported
    assert not hasattr(sampling, "accept_baseline")


def test_a_days_sample_defaults_to_the_quota_rather_than_to_whatever_was_asked_for() -> None:
    """The positive case for the constant: `draw` called the way a scheduled job would call
    it, with no quota, produces the day's quota.

    Delete this and the default can drift away from the constant that was derived to reach
    the floor, and every test above still passes because they all pass a quota."""
    sample = draw(seed=SEED, day=DAY, request_ids=POPULATION)

    assert len(sample.request_ids) == DAILY_ANNOTATION_QUOTA
