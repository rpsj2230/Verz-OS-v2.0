"""Two ways of measuring answer quality that must never be added together.

Automated evaluation runs on every request. It is cheap, mechanical and complete: it can
say a canary token appeared in an answer, that a refusal was not byte-identical to an
absence, that a catalogue offered a tool the caller cannot invoke. Human annotation runs on
a daily sample. It is expensive, judgemental and partial: it can say an answer was
confidently wrong, that a correct-looking number answered a different question from the one
asked, that a refusal was right and useless.

**Neither can substitute for the other and a single number mixing them is a number nobody
can act on.** The automated tier's coverage is total and its judgement is nil: it cannot
tell a right answer from a wrong one, only a permitted answer from a leaking one. The human
tier's judgement is real and its coverage is a sample: an absence in twenty annotations is
not an absence in the day. Average them and the result inherits the shallowness of the first
and the partiality of the second, and the number moves when the sample moves, which reads as
quality moving. So there are two types, two report functions, and no function anywhere in
this module that takes both. See
`AUTOMATED_COVERAGE_IS_COMPLETE_AND_SHALLOW_ANNOTATION_IS_DEEP_AND_PARTIAL`.

**The two tiers do not even share a vocabulary of faults, and that is the argument made
structurally rather than in prose.** An automated reading's fault is a
`brain.ops.canaries.Finding`, which names things a machine can see: a token was present,
two strings differed, a set was not the set it should have been. An annotation's fault is a
`brain.ops.feedback.FlagReason`, which names things only a person can judge: the answer was
wrong, incomplete, out of date. The two enums have no member in common and there is no
mapping between them, because there is no true one. Two instruments with no shared unit do
not average, and here they cannot even be lined up.

**A sample must not disclose the shape of what was not sampled.** This is where an
annotation queue leaks, and it leaks through arithmetic rather than through content. A
sample stratified by department tells the annotator how the day's questions were spread
across departments, which is a fact about volumes in departments they may hold nothing in.
A sample weighted by cost tells them which departments spend. And a sample that carries its
own fraction is the worst of the three, because the reader divides: twenty items at two per
cent is a thousand requests, stated exactly, by a field somebody added to be transparent.
So the draw is uniform over request ids and nothing else, `DailySample` has no field a count
or a fraction could go in, and `sampler_gaps` refuses a stratifying argument on the drawing
surface rather than trusting that nobody adds one. See
`A_SAMPLE_SIZE_BESIDE_A_FRACTION_RECOVERS_THE_POPULATION`.

**What a sample does disclose is bounded by the quota and stated rather than denied.** On a
day with fewer requests than `DAILY_ANNOTATION_QUOTA`, the sample is the population and the
annotator can see its size. That is true of any sampler that returns items and cannot be
designed away. What can be guaranteed is the bound: **a sample discloses no count larger
than the quota**, whatever the day's volume was, because it never returns more than the
quota and never says whether it was short.

**The draw is a hash and not a generator, so a reviewer can reproduce it by hand.** Each
candidate is keyed on `sha256(seed, day, request_id)` and the lowest keys win. That is
deterministic across platforms and Python versions, which a seeded Mersenne Twister is not
promised to be, and it is independent of the order the ids arrive in, so a caller cannot
influence the draw by sorting its input. To check a day's sample a reviewer needs the seed,
the date and the day's request ids, and then runs `draw` and compares: no state, no cursor,
no stored random stream.

**The seed is carried on the sample, which is what stops it being secret-shaped.** A secret
seed makes the draw unauditable, and "we annotated a random two per cent" is then a claim
nobody can check. Putting the seed on the returned object makes hiding it impossible:
publishing the sample publishes the seed. `check_seed` refuses the shapes a real secret
takes as a second guard, and it is a guard and not a proof, which is said where it is
defined. Predictability is the price and it is the right way round: anybody holding the seed
can work out which requests will be annotated, and gaming that means choosing your own
request id, which ingress does not let a caller do.

**Nothing here records a baseline and `accept_baseline` is deliberately not imported.** A
daily sample of twenty has a standard error around seven percentage points, so a baseline
ratcheted on it would fail builds on sampling noise, and a bar that fails on noise is a bar
somebody raises until it stops. The baseline belongs to the automated tier, which measures
the same population every time. See `A_BASELINE_OVER_A_DAILY_SAMPLE_RATCHETS_ON_NOISE`.

Rejected: stratifying the sample by department so every department gets annotated. It is
the first thing anybody asks for and it is the disclosure above, and it buys less than it
looks: what stratification protects against is a department being invisible to annotation,
and a uniform draw over a month covers a department in proportion to how many questions it
asks, which is the right proportion for finding faults.

Rejected: weighting the sample towards expensive or long-running requests. Same disclosure,
worse: cost tracks model choice and tool count, so a cost-weighted queue is a readable
statement about which departments run the expensive work.

Rejected: a `sampled_fraction` or `population` field on `DailySample`, for auditability.
The audit is the seed and the day, which reproduce the draw exactly, and they disclose
nothing. A population count discloses a population count.

Rejected: one `quality_score` combining both tiers for the console's headline. It is the
number everybody wants and it is the one that cannot be acted on: a fall in it does not say
whether something leaked or whether an annotator was strict on a Tuesday.

**"Automated evaluation on every request" describes the tier and not this repository, and
the difference is worth stating plainly.** Nothing calls anything here.
`brain.api_routes.answer` builds no `AutomatedReading`, so the tier that is supposed to see
every request currently sees none, and no scheduled job calls `draw`, so no day has a
queue. What has to exist is one line in that route turning each answered question into an
`AutomatedReading` and a store to put it in, and a daily task that hands `draw` the day's
request ids and publishes the seed with the queue. Neither is built here, because both need
a store and a scheduler and this module is deliberately the half that needs neither. What
is claimed is the instrument: two vocabularies that do not merge, a draw a reviewer can
reproduce by hand, and two reports that cannot be averaged.

Scope: this module opens no connection and reads no clock. The day is a parameter, the
readings and annotations are handed in, and the draw is a pure function of its arguments,
which is the split `brain.ops.limits`, `brain.ops.canaries` and `brain.ops.evaluation`
make.

Task ids: M28.3.3
"""

from __future__ import annotations

import enum
import hashlib
import inspect
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final, assert_never

from brain.gate.compose import TRACE_REF_BYTES
from brain.ops.canaries import Finding
from brain.ops.evaluation import (
    PERMISSION_FAILURES_ALLOWED,
    QUALITY_FLOOR,
    CaseResult,
    Severity,
    report_lines,
    score,
)
from brain.ops.feedback import FlagReason, severity_of


class SamplingError(Exception):
    """Raised when a sample cannot be drawn in a way anybody could reproduce or audit."""


# ------------------------------------------------------------------ written-down reasons
#: Why the two tiers are never combined into one figure.
AUTOMATED_COVERAGE_IS_COMPLETE_AND_SHALLOW_ANNOTATION_IS_DEEP_AND_PARTIAL = (
    "Automated evaluation sees every request and judges none of them: it can say a token "
    "leaked and cannot say an answer was wrong. Human annotation judges properly and sees "
    "a sample: it can say an answer was confidently wrong and cannot say nothing leaked "
    "today. A combined figure inherits the blindness of the first and the coverage of the "
    "second, and it moves when the sample moves, which every reader will read as quality "
    "moving. Two numbers, reported separately, are two things somebody can act on."
)

#: Why the shape of a sample must not admit a count.
A_SAMPLE_SIZE_BESIDE_A_FRACTION_RECOVERS_THE_POPULATION = (
    "Twenty items and 'a two per cent sample' is a thousand requests, stated to the "
    "reader exactly, by a field added to be transparent. So there is no fraction, no "
    "population, no 'showing 20 of' and no field one could be put in. The quota is fixed "
    "rather than proportional for the same reason: a fixed quota discloses no count above "
    "itself on any day, and a proportional one discloses the day."
)

#: Why the seed travels on the sample rather than being held anywhere.
A_SEED_HELD_BACK_IS_A_SAMPLE_NOBODY_CAN_REPRODUCE = (
    "'We annotated a random two per cent' is not a claim anybody can check without the "
    "seed. A seed kept somewhere else is a seed that is rotated, redacted from logs and "
    "eventually lost, and the samples drawn with it become unreproducible one by one with "
    "nothing marking the day it happened. So it is carried on the sample, which makes "
    "treating it as a secret impossible: publishing the sample publishes the seed."
)

#: Why no baseline is recorded over the human tier.
A_BASELINE_OVER_A_DAILY_SAMPLE_RATCHETS_ON_NOISE = (
    "A reading over twenty annotations moves by five percentage points when one annotator "
    "disagrees. A baseline ratcheted against that fails builds on sampling noise, and a "
    "bar that fails on noise is a bar somebody raises until it stops failing, which is the "
    "ratchet running the wrong way. The automated tier measures the same population every "
    "run and is where a baseline belongs. `accept_baseline` is not imported here."
)

#: Why a report never names an annotator.
A_PER_ANNOTATOR_FIGURE_IS_A_STATEMENT_ABOUT_A_PERSON = (
    "`brain.ops.evaluation.report_lines` refuses to produce a per-persona figure because a "
    "suite report is the kind of document that gets forwarded. The same holds on the other "
    "side of the desk: 'Meera marked nine of twenty wrong' is a performance statistic about "
    "an annotator, produced by a quality process nobody enrolled them in, and it makes the "
    "cheapest way to look good marking everything sound."
)

#: How many annotator disagreements a day's reading must survive without failing.
#:
#: Anchored against `brain.ops.evaluation.PERMISSION_FAILURES_ALLOWED`, which is zero and is
#: not configurable, and the relation is the point rather than the number: a permission
#: threshold has no tolerance by design and a human quality reading must have one, or a
#: single strict annotator fails the day and the tier is switched off within the month.
#: Two rather than one, because one disagreement is the ordinary case and a threshold the
#: ordinary case trips is not a threshold.
DISAGREEMENTS_TOLERATED: Final[int] = PERMISSION_FAILURES_ALLOWED + 2

#: How many answers a day's human sample contains. Derived from the floor, not chosen.
#:
#: The reading over a sample of n has a resolution of 1/n, so a sample too small cannot
#: express `brain.ops.evaluation.QUALITY_FLOOR` at all: at n = 5 every possible reading is
#: 1.0, 0.8, 0.6 and so on, and none of them is 0.9. This is the smallest sample at which
#: `DISAGREEMENTS_TOLERATED` failures still land exactly on the floor rather than below it,
#: which makes the quota a property of the instrument rather than a number somebody liked.
#:
#: **It is a lower bound on the sample and not a claim about what a person can read.** If
#: twenty answers a day is more annotation than the company will pay for, the honest
#: conclusion is that the human tier is not affordable, which is a finding somebody should
#: see. Sampling fewer would produce a reading whose resolution cannot reach the floor it
#: is compared against, which is a number that looks like quality and is arithmetic.
DAILY_ANNOTATION_QUOTA: Final[int] = round(DISAGREEMENTS_TOLERATED / (1.0 - QUALITY_FLOOR))

#: The longest a seed may be, in characters.
#:
#: One character shorter than the shortest deliberately unguessable string this system
#: mints: `secrets.token_urlsafe(brain.gate.compose.TRACE_REF_BYTES)` is sixteen characters
#: of URL-safe alphabet. A seed that will not fit in that many characters cannot be one of
#: this system's references pasted in by mistake, and it is short enough to print in the
#: header of an annotation queue, which is where a reviewer reads it from.
SEED_MAX_LENGTH: Final[int] = TRACE_REF_BYTES * 4 // 3 - 1

#: What a seed may look like: a published short name, lowercase, hyphenated.
#:
#: Built from `SEED_MAX_LENGTH` rather than repeating it, so the two cannot drift. It
#: refuses uppercase, underscores, dots and the base64 padding characters, which is most of
#: what a real token looks like, and it refuses anything long enough to be one.
SEED_PATTERN: Final[str] = rf"^[a-z0-9][a-z0-9-]{{2,{SEED_MAX_LENGTH - 1}}}$"
SEED_RE: Final[re.Pattern[str]] = re.compile(SEED_PATTERN)

#: Argument names that would turn a uniform draw into a stratified or weighted one.
#:
#: Scanned for rather than trusted, following `brain.ops.retention`'s scan for arguments
#: that could postpone a window: the way this rule dies is one helpful keyword argument
#: added during a review meeting and never taken out again.
_STRATIFYING_NAMES: Final[frozenset[str]] = frozenset(
    {
        "department",
        "departments",
        "cost",
        "costs",
        "spend",
        "weight",
        "weights",
        "weighted",
        "priority",
        "asker",
        "askers",
        "principal",
        "principals",
        "team",
        "teams",
    }
)


class Tier(enum.StrEnum):
    """The two instruments. Two members and no third, and no way to hold both at once.

    There is deliberately no common base class for `AutomatedReading` and
    `HumanAnnotation`, and neither of them carries a `tier` attribute. A base class is what
    makes one list of both a natural thing to write; without it, anybody who wants to mix
    them has to spell a union out by hand and will notice they are doing it.
    """

    #: Every request, mechanically.
    AUTOMATED = "automated"
    #: A daily sample, by a person.
    HUMAN = "human"


#: What each tier can honestly claim about its own coverage. Printed above its own report so
#: two figures on one screen cannot be read as one.
COVERAGE: Final[dict[Tier, str]] = {
    Tier.AUTOMATED: (
        "automated: every request, mechanical checks only. Says nothing about whether an "
        "answer was right."
    ),
    Tier.HUMAN: (
        "human: one day's sample, judged by a person. Says nothing about the requests that "
        "were not sampled."
    ),
}


@dataclass(frozen=True)
class AutomatedReading:
    """What the mechanical checks saw on one request.

    `fault` is a `brain.ops.canaries.Finding` and nothing else, which is the tier's whole
    reach: the things a machine can decide by comparing two strings or two sets. There is
    no free-text field, for the reason `brain.ops.feedback` gives about flags, and no
    answer text, for the same one.
    """

    request_id: str
    passed: bool
    #: What went wrong, from the machine's vocabulary. None when the request passed.
    fault: Finding | None = None

    def __post_init__(self) -> None:
        if not self.request_id:
            msg = "an automated reading with no request id names nothing anybody can look up"
            raise SamplingError(msg)
        if self.passed and self.fault is not None:
            msg = f"{self.request_id} passed and carries a fault, so one of the two is wrong"
            raise SamplingError(msg)
        if not self.passed and self.fault is None:
            msg = f"{self.request_id} failed and says why nowhere, so nobody can act on it"
            raise SamplingError(msg)


@dataclass(frozen=True)
class HumanAnnotation:
    """One person's judgement of one answer they were shown.

    `fault` is a `brain.ops.feedback.FlagReason`, which is the same vocabulary a department
    lead flags with, deliberately. An annotation that finds a bad answer *is* a flag, and
    two vocabularies for one judgement would be two lists that drift and a console with two
    ways to say the same thing.

    No free text, again, and here the argument is sharper than it is for a flag: an
    annotator is being paid to write down what was wrong with an answer they are looking
    at, so a comment box is not a risk, it is the intended use, and what it collects is
    restricted values transcribed by hand into a store that keeps them.
    """

    request_id: str
    #: Who judged it. Recorded so the work can be shared out, never reported. See
    #: `A_PER_ANNOTATOR_FIGURE_IS_A_STATEMENT_ABOUT_A_PERSON`.
    annotator: str
    sound: bool
    #: What was wrong, from the human vocabulary. None when the answer was sound.
    fault: FlagReason | None = None

    def __post_init__(self) -> None:
        for name in ("request_id", "annotator"):
            if not getattr(self, name):
                msg = f"an annotation with no {name} cannot be traced back to anything"
                raise SamplingError(msg)
        if self.sound and self.fault is not None:
            msg = f"{self.request_id} was judged sound and carries a fault"
            raise SamplingError(msg)
        if not self.sound and self.fault is None:
            msg = f"{self.request_id} was judged unsound and says why nowhere"
            raise SamplingError(msg)


@dataclass(frozen=True)
class DailySample:
    """One day's annotation queue. Three fields, and the missing ones are the design.

    There is no `population`, no `sampled_fraction`, no `total`, no `remaining` and no
    `truncated`. Every one of those is a count of what was not sampled, directly or by one
    division, and there is nowhere to put one: adding a field is an edit to a frozen
    dataclass in a module whose docstring argues against it, which is the structural move
    `brain.ops.canaries.CanaryFinding` makes about carrying a token.

    `seed` is here rather than held somewhere, which is
    `A_SEED_HELD_BACK_IS_A_SAMPLE_NOBODY_CAN_REPRODUCE`, and it is what makes the sample
    reproducible: a reviewer with this object and the day's request ids calls `draw` and
    compares.
    """

    day: date
    #: The published seed the draw used. Printed with the queue.
    seed: str
    #: The drawn ids, in draw order, which is the order the keys sorted in.
    request_ids: tuple[str, ...]


def check_seed(seed: str) -> str:
    """Refuse a seed nobody could print beside the sample it drew.

    A guard and not a proof, and the difference matters enough to say. A thirty-character
    lowercase hex string satisfies this pattern and is indistinguishable from a name by any
    rule short of measuring entropy, which would refuse legitimate seeds too. What actually
    protects against a secret being used here is that the seed is carried on `DailySample`
    and printed with the queue, so anybody who pasted one sees it in the annotation header.
    This stops the accident that has an obvious shape: an API key, a token, a base64 blob.
    """
    if not SEED_RE.match(seed):
        msg = (
            f"seed {seed[:8]!r} is not a published name. A seed is printed beside the "
            f"sample it drew, so it must be a short lowercase name of at most "
            f"{SEED_MAX_LENGTH} characters, and anything longer or token-shaped is "
            "refused rather than published by accident."
        )
        raise SamplingError(msg)
    return seed


def draw_key(*, seed: str, day: date, request_id: str) -> str:
    """The sort key one request gets in one day's draw.

    A digest and not a random number, so the draw is reproducible by anybody with the three
    inputs, on any platform, under any Python version. `random.Random` seeded with the same
    string would do the job today and its sequence is not promised across releases, which
    turns "reproduce last March's sample" into an archaeology exercise.

    The three parts are joined with a newline rather than concatenated, so that a seed
    ending in a digit and a date beginning with one cannot produce the same material as a
    different pair. Concatenation collisions of that shape are the classic defect in a
    keyed hash and they are silent.
    """
    material = "\n".join((seed, day.isoformat(), request_id))
    return hashlib.sha256(material.encode()).hexdigest()


def draw(
    *,
    seed: str,
    day: date,
    request_ids: Iterable[str],
    quota: int = DAILY_ANNOTATION_QUOTA,
) -> DailySample:
    """Draw one day's annotation queue, uniformly, deterministically, and disclosing nothing.

    Uniform over request ids and over nothing else: there is no department argument, no
    cost argument and no weight argument, and `sampler_gaps` checks that none has appeared
    rather than leaving it to whoever reads the signature next.

    Order-independent, because the ids are keyed and then sorted by key. A caller cannot
    move a request into or out of the sample by sorting its input, which a "first n after
    shuffling" draw would let them do, and which nothing downstream would ever notice.

    Duplicates collapse. The same request id twice is one request, and a sample that
    contained it twice would spend two of the day's annotations on one answer.

    **The quota is a count and never a fraction.** A proportional sample discloses the
    day's volume through its own size; a fixed quota discloses no count larger than itself.
    On a quiet day the sample is the whole population and the annotator can see how small
    it is, which is true of every sampler that returns items and is bounded by the quota.
    """
    check_seed(seed)
    if quota < 1:
        msg = f"a quota of {quota} draws nothing, and a queue nobody works is not a tier"
        raise SamplingError(msg)

    unique: set[str] = set()
    for one in request_ids:
        if not one:
            msg = "a request id in the population is empty, so the sample would contain a row"
            raise SamplingError(msg)
        unique.add(one)

    ordered = sorted(unique, key=lambda rid: (draw_key(seed=seed, day=day, request_id=rid), rid))
    return DailySample(day=day, seed=seed, request_ids=tuple(ordered[:quota]))


#: The functions a stratifying argument would have to arrive through. Named as a constant so
#: `sampler_gaps` has something to run against other than itself.
DRAWING_SURFACE: Final[tuple[Callable[..., object], ...]] = (draw, draw_key, check_seed)


def sampler_gaps(surface: Sequence[Callable[..., object]] | None = None) -> tuple[str, ...]:
    """Every way the drawing surface has acquired a way to stratify or weight the draw.

    The surface is a parameter defaulting to this module's own, for the reason
    `brain.ops.tracing.retention_gaps` takes one: a check that can only ever run against
    the constant beside it cannot be shown to fail, and a check nobody has seen fail is a
    check nobody has evidence about.

    Names rather than behaviour, which is a real limitation and is the right trade here. A
    parameter called `bias` would pass this, and the failure mode being guarded against is
    not somebody smuggling stratification past a scan: it is somebody adding
    `department=` because a stakeholder asked for even coverage, and that person writes it
    with the obvious name.
    """
    checked = DRAWING_SURFACE if surface is None else surface
    findings: list[str] = []
    for fn in checked:
        for name in inspect.signature(fn).parameters:
            if name.lower() in _STRATIFYING_NAMES:
                findings.append(
                    f"{fn.__name__} takes {name!r}, which draws a sample whose shape is a "
                    "statement about the population it was drawn from"
                )
    return tuple(findings)


# ---------------------------------------------------------------------- scoring, apart
def severity_of_finding(fault: Finding) -> Severity:
    """Which of `brain.ops.evaluation`'s classes a mechanical finding falls in.

    Four of the five are permission outcomes and one is not, and the odd one out is
    `PROJECTION_TOO_NARROW`, on `brain.ops.canaries`'s own reasoning: a catalogue that
    withholds a tool the caller is entitled to is a broken product rather than a
    disclosure. Scoring it as a permission failure would give it a threshold of zero, and a
    zero threshold on something that is not a disclosure is how a suite acquires a class of
    failure people learn to override.

    `assert_never` so a sixth `Finding` is a type error here rather than a member that
    silently takes whichever class a dictionary default carried.
    """
    match fault:
        case (
            Finding.LEAKED
            | Finding.REFUSAL_DISTINGUISHABLE
            | Finding.UNLOCKED
            | Finding.PROJECTION_TOO_WIDE
        ):
            return Severity.PERMISSION
        case Finding.PROJECTION_TOO_NARROW:
            return Severity.QUALITY
        case _:
            assert_never(fault)


def automated_cases(readings: Sequence[AutomatedReading]) -> tuple[CaseResult, ...]:
    """The automated tier's readings, as cases `brain.ops.evaluation.score` can read.

    Keyed on the request id, which is a pointer and not a person, and carrying no
    annotator, no principal and no department. A passing reading has no severity of its own
    to declare, so it is scored as quality: a request that produced no finding is a request
    the mechanical checks had nothing to say about, and putting it in the permission
    denominator would make the permission share a number, which
    `A_PERCENTAGE_IS_THE_WRONG_INSTRUMENT_FOR_A_PERMISSION` says it must never be.
    """
    return tuple(
        CaseResult(
            question_id=one.request_id,
            severity=Severity.QUALITY if one.fault is None else severity_of_finding(one.fault),
            passed=one.passed,
            reason="" if one.passed else f"the mechanical check reported {one.fault}",
        )
        for one in sorted(readings, key=lambda r: r.request_id)
    )


def annotated_cases(annotations: Sequence[HumanAnnotation]) -> tuple[CaseResult, ...]:
    """The human tier's annotations, as cases, scored entirely separately from the above.

    Severity comes from `brain.ops.feedback.severity_of`, so an annotator saying an answer
    showed somebody something they may not see lands in the class with a threshold of zero,
    and an annotator saying an answer was out of date lands in the class with a floor. One
    mapping for a flag and an annotation, because they are the same judgement made by
    different people at different times.
    """
    return tuple(
        CaseResult(
            question_id=one.request_id,
            severity=Severity.QUALITY if one.fault is None else severity_of(one.fault),
            passed=one.sound,
            reason="" if one.sound else f"an annotator judged this {one.fault}",
        )
        for one in sorted(annotations, key=lambda a: a.request_id)
    )


def automated_report(readings: Sequence[AutomatedReading]) -> tuple[str, ...]:
    """What the automated tier says about itself, with its coverage claim on the first line.

    The coverage line is not decoration. Two shares printed on one screen with no labels
    are read as two measurements of the same thing, and the whole of
    `AUTOMATED_COVERAGE_IS_COMPLETE_AND_SHALLOW_ANNOTATION_IS_DEEP_AND_PARTIAL` is that
    they are not.
    """
    return (COVERAGE[Tier.AUTOMATED], *report_lines(score(automated_cases(readings))))


def annotation_report(annotations: Sequence[HumanAnnotation]) -> tuple[str, ...]:
    """What the human tier says about itself. A separate function returning a separate tuple.

    Never names an annotator, and the report is built from `report_lines`, which already
    refuses to produce a per-person figure. See
    `A_PER_ANNOTATOR_FIGURE_IS_A_STATEMENT_ABOUT_A_PERSON`.

    No baseline and no verdict about merging. A day's reading is a day's reading: see
    `A_BASELINE_OVER_A_DAILY_SAMPLE_RATCHETS_ON_NOISE`.
    """
    return (COVERAGE[Tier.HUMAN], *report_lines(score(annotated_cases(annotations))))
