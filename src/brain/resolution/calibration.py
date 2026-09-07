"""Fitting the weights the cascade adds up, in a job the request path is structurally unable
to reach.

`brain.resolution.cascade` declares a weight for every feature and says, in
`THE_WEIGHTS_ARE_DECLARED_AND_NOTHING_HAS_CALIBRATED_THEM`, that an author chose all of them.
This is the other half of that sentence: the arithmetic that would measure them, the document
they travel in, and the load that turns such a document into the table the online scorer sums.

**The arrow points one way and that is the whole of M14.4.5.** This module imports `cascade`;
`cascade` must never import this one. A fitted model is a training-time artefact and the moment
one is reachable from the gate it is loaded at import time and consulted per comparison, which
is the opposite of the millisecond online cost M14.3.6 asks for. The claim is not a comment
here: `tests/invariants/test_no_ml_on_the_request_path.py` walks the import graph from the gate
and refuses to find this module in it, and refuses to find a numerical library anywhere in that
closure. See `THE_CALIBRATION_IS_OFFLINE_AND_THE_ARROW_POINTS_ONE_WAY`.

**The expectation-maximisation is written out in plain Python and that is a deliberate cost
(M14.4.2).** Fellegi-Sunter over agreement patterns is four lines of arithmetic per iteration
and a library would be faster to write, would be a dependency, and would then have to be kept
off the request path by a rule about packaging rather than by a rule about imports. Writing it
out means the only thing this file needs is `math.log2`, so the assertion above stays a
statement about the repository rather than about a virtualenv. What it costs is that nobody has
checked this implementation against Splink's: see `THE_SPLINK_JOB_IS_NOT_BUILT_AND_THIS_SAYS_SO`
and `OFFLINE_TOOLING`.

**Two probabilities near nought are the failure mode, not the arithmetic (M14.4.2).** The
weight of a feature is `log2(m / u)`, so a feature that never agrees among non-matches has an
infinite weight, and one infinite term makes every threshold meaningless and every review item
read as decisive. `PROBABILITY_FLOOR` bounds both probabilities away from the ends, and the
floor is chosen against `guardrails.DECISIVE_WEIGHT` rather than by taste: it has to be small
enough that a genuinely decisive feature can still reach the top band. See
`A_ZERO_UNMATCH_PROBABILITY_IS_AN_INFINITE_WEIGHT`.

**A converged model can be the right likelihood with the labels swapped**, which exports a
weight table with every sign inverted: a UEN agreement would become evidence that two records
are different companies, and every stage of the cascade would go on working while merging the
wrong pairs. Expectation-maximisation cannot tell the two apart, because they are the same
likelihood. So the fit is refused rather than exported when the matching class is not the class
that agrees more. See `AN_INVERTED_SOLUTION_IS_THE_SAME_LIKELIHOOD_WITH_THE_LABELS_SWAPPED`.

**A calibration reference is a name and not a boolean (M14.3.5, M14.4.3).**
`cascade.WeightTable.calibrated` is derived from `calibration_ref`, so the only way a table can
claim it was measured is to name the export that measured it. `WeightExport.to_weight_table` is
the one route in this repository that sets that field, and it sets it from a reference this
module validated, so "calibrated" cannot become a string somebody typed. See
`A_CALIBRATION_REF_IS_A_NAME_AND_NOT_A_BOOLEAN`.

**The weights reach the online scorer as a value and not as a row (M14.4.3).** There is no
`er.match_weight` table and this module does not want one. `brain.resolution.query` binds every
weight as a query parameter, so the scoring SQL is the same text under every weight table and
the weights are data the caller hands over; a table would add a read to the request path for a
figure that changes weekly, and the read would be the thing that fails during an incident. What
that costs is said rather than implied: nothing here persists an export, so which export a
running deployment loaded is a fact about its deploy and not about its database. See
`THE_ONLINE_WEIGHTS_ARE_A_VALUE_AND_NOT_A_ROW`.

**Weekly, and the review of drift is what makes it a schedule rather than a cron line
(M14.4.4).** A job that re-fits and promotes on its own is a job that can quietly move a
feature from "supports these being one thing" to "very nearly the whole answer" without anybody
reading the sentence that changed. `promote` refuses a candidate that crosses a band unless the
export names a reviewer, so the review is a value the export carries rather than a step in a
runbook. `due` is the cadence and it takes both instants as parameters, for the reason every
other policy module here takes its clock as one.

Rejected: exporting the m and u probabilities and letting the online side compute log2 per
comparison. That is one logarithm per feature per pair, it puts a fitted quantity on the
request path in all but name, and it makes the SQL expression impossible: a CASE WHEN can hold
a bound number and cannot hold a transformation of one.

Rejected: refusing to export at all until Splink has been run against the same data. It reads
as the careful choice and it means the honest half never ships. The register below says which
half is exercised, and `OFFLINE_TOOLING` is the shape that makes the absence checkable rather
than remembered.

Scope: offline. Nothing here opens a connection, reads a clock or touches a table, and nothing
on the request path may import it.

Task ids: M14.3.5, M14.4.2, M14.4.3, M14.4.4, M14.4.5
"""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import log2
from types import MappingProxyType
from typing import Any, Final

from brain.resolution.canonical import ResolutionError
from brain.resolution.cascade import Feature, WeightTable
from brain.resolution.guardrails import Strength, strength_of

# ------------------------------------------------------------------ written-down reasons
#: Why this module may import the cascade and the cascade may never import this one.
THE_CALIBRATION_IS_OFFLINE_AND_THE_ARROW_POINTS_ONE_WAY: Final = (
    "A fitted model is a training-time artefact. Reachable from the gate it becomes an object "
    "loaded at import time and consulted per comparison, which is what M14.4.5 forbids and "
    "the opposite of the one-SQL-expression cost M14.3.6 asks for. The dependency therefore "
    "runs offline to online and never back: this module imports cascade so that an export can "
    "be turned into the table the online scorer sums, and cascade imports nothing from here. "
    "A comment saying so would be believed and would not be true for long, so the property is "
    "an import-graph walk from the gate's own modules that refuses to find this one, with the "
    "walker's ability to find anything at all proved by asking it for a module that is there."
)

#: Why both probabilities are held away from the ends.
A_ZERO_UNMATCH_PROBABILITY_IS_AN_INFINITE_WEIGHT: Final = (
    "The weight of a feature is log2(m / u). A feature that agreed on every match and on no "
    "non-match in the training extract has u = 0, an infinite weight, and one infinite term "
    "in an additive score makes every threshold meaningless and renders every review item as "
    "decisive. That is not a rare accident: it is what a small extract produces for a strong "
    "identifier, which is exactly the feature whose weight matters most. So both probabilities "
    "are clamped, and the floor is chosen against guardrails.DECISIVE_WEIGHT rather than by "
    "taste: it has to leave room for a genuinely decisive feature to reach the top band, and a "
    "floor that did not would quietly cap the strongest evidence the cascade has."
)

#: Why a converged fit can still be the wrong fit.
AN_INVERTED_SOLUTION_IS_THE_SAME_LIKELIHOOD_WITH_THE_LABELS_SWAPPED: Final = (
    "Expectation-maximisation fits two classes and does not know which is which. Swapping the "
    "match class for the non-match class and swapping every m with its u is the same "
    "likelihood, so the algorithm cannot prefer one, and the swapped solution exports a weight "
    "table with every sign inverted. A UEN agreement would then be evidence that two records "
    "are different companies. Nothing downstream would fail: the stages would run, the "
    "thresholds would hold, the review queue would render, and the pairs merged would be the "
    "wrong ones. So the fit is refused when the class called match is not the class that "
    "agrees more, which is the identifiability constraint stated as a check rather than as an "
    "assumption about the starting point."
)

#: Why the reference is a validated name.
A_CALIBRATION_REF_IS_A_NAME_AND_NOT_A_BOOLEAN: Final = (
    "cascade.WeightTable.calibrated is a property derived from calibration_ref, so there is no "
    "boolean to set to True and claiming calibration means naming the export. That guard is "
    "worth only as much as the strings that reach the field, and the string 'yes' would "
    "satisfy it. to_weight_table is the one route here that sets it, it sets it from a "
    "reference this module has validated against a grammar, and the grammar is the thing that "
    "makes the name a name. What is still not checked, and is said rather than implied: "
    "nothing verifies that the named export exists anywhere, because nothing here persists one."
)

#: Why a band crossing is the thing a person reviews.
A_DRIFT_THAT_CROSSES_A_BAND_IS_A_DIFFERENT_SENTENCE_TO_A_REVIEWER: Final = (
    "guardrails.Evidence.render shows a band and never a number, so a weight moving from 3.9 "
    "to 4.1 changes what a reviewer reads from 'supports these being one thing' to 'counts "
    "heavily towards these being one thing', and a weight moving from 1.0 to 3.9 changes "
    "nothing they see. The reviewable event is therefore the crossing and not the size of the "
    "move, which is why drift is reported in bands. A weekly job that promoted its own fit "
    "would change that sentence without anybody reading it, so promote refuses a crossing that "
    "no reviewer signed."
)

#: What the online side reads, and what it does not.
THE_ONLINE_WEIGHTS_ARE_A_VALUE_AND_NOT_A_ROW: Final = (
    "There is no er.match_weight table and no migration creates one. brain.resolution.query "
    "binds every weight as a query parameter, so the scoring SQL is one text under every "
    "weight table and the weights are data handed to the builder; a table would put a read on "
    "the request path for a figure that changes weekly, and that read is what fails during an "
    "incident. The cost is real and is not hidden: which export a deployment loaded is a fact "
    "about its deploy rather than about its database, so an operator asking which weights "
    "produced a link has the weight table's version on the link and nothing to join it to."
)

#: The half of M14.4 that is not built, kept as a constant so it has to be deleted.
THE_SPLINK_JOB_IS_NOT_BUILT_AND_THIS_SAYS_SO: Final = (
    "M14.4.1 asks for a Splink job against a DuckDB export. Neither package is a dependency of "
    "this repository, neither is installed, and nothing here has been run against either. What "
    "exists is the extract shape a DuckDB export would be built from, the arithmetic Splink "
    "would perform, and the document the two would agree on, so the day somebody adds the "
    "dependency there is something to compare against. Until then no row of OFFLINE_TOOLING "
    "may claim verification, tooling_gaps refuses one that does, and M14.4.1 is not claimed by "
    "any Task ids line in this repository."
)


# ------------------------------------------------------------------------ the arithmetic
#: How far a probability is held from nought and from one.
#:
#: Chosen against `guardrails.DECISIVE_WEIGHT` rather than picked: a feature that agrees on
#: nearly every match and nearly no non-match must still be able to reach the top band, so the
#: floor has to satisfy `log2((1 - floor) / floor) >= DECISIVE_WEIGHT`. A test states that
#: relation rather than repeating the figure. See
#: `A_ZERO_UNMATCH_PROBABILITY_IS_AN_INFINITE_WEIGHT`.
PROBABILITY_FLOOR: Final = 1e-4

#: When to stop. The largest change in any parameter between two iterations.
CONVERGENCE_TOLERANCE: Final = 1e-9

#: How many iterations before the fit is reported as not converged.
#:
#: Not an error. A fit that ran out of iterations is a fact about the extract, and refusing to
#: return it would leave nothing to look at; `FellegiSunter.converged` carries it and `export`
#: refuses to build a document from a fit that did not converge.
MAX_ITERATIONS: Final = 500

#: The share of candidate pairs the fit starts by assuming are matches.
#:
#: Below a half deliberately. In any candidate set worth blocking, matches are the rare class,
#: and starting above a half starts the search in the basin of the inverted solution that
#: `AN_INVERTED_SOLUTION_IS_THE_SAME_LIKELIHOOD_WITH_THE_LABELS_SWAPPED` describes.
INITIAL_MATCH_RATE: Final = 0.1

#: Where the two per-feature probabilities start, m high and u low, for the same reason.
INITIAL_M: Final = 0.9
INITIAL_U: Final = 0.1

#: What an export reference may look like: at least two parts joined by a separator.
#:
#: The two parts are the point rather than the character class. A reference names a job and a
#: run, because `WeightTable.calibrated` is true of any table whose reference is non-empty and
#: a one-word reference is how that guard is satisfied without naming anything: "calibrated",
#: "yes" and "done" are all non-empty strings. Requiring a separator does not make a reference
#: true, and it does make the shape of a claim visible in review.
_REF_RE: Final = re.compile(r"^[a-z0-9]+(?:[.:_-][a-z0-9]+)+$")

#: The shortest reference that could name a job and a run rather than an opinion.
MIN_REF_CHARS: Final = 8


def _clamp(value: float) -> float:
    """Hold a probability inside the open interval the weight is finite on."""
    return min(max(value, PROBABILITY_FLOOR), 1.0 - PROBABILITY_FLOOR)


def weight_of(m: float, u: float) -> float:
    """The match weight of one feature agreeing, in log2 Bayes factors.

    The unit `guardrails.Strength`'s bands are cut in, which is what lets an export be rendered
    to a reviewer without a second scale to convert. Both probabilities are clamped first, so
    there is no input to this function that produces an infinity.
    """
    return log2(_clamp(m) / _clamp(u))


@dataclass(frozen=True)
class PatternCount:
    """How many candidate pairs showed exactly this set of agreements.

    The extract a DuckDB export would produce, reduced to the only thing the fit reads. A pair
    contributes its pattern and nothing else: no identifier, no name, no record reference, so
    an extract cannot carry a contact record into a training set and a fitted weight cannot be
    traced back to the pair that moved it. That is `guardrails.Evidence`'s rule applied to the
    offline half, and it is why this type has no source reference on it.
    """

    pattern: frozenset[Feature]
    pairs: int

    def __post_init__(self) -> None:
        if self.pairs < 0:
            msg = f"a pattern seen {self.pairs} times is not an observation"
            raise ResolutionError(msg)


@dataclass(frozen=True)
class FellegiSunter:
    """A fitted model: how often each feature agrees among matches and among non-matches.

    Not exportable on its own. `export` is the only route to a document and it refuses a fit
    that did not converge or whose labels are inverted, so the artefact that leaves this module
    has passed both checks and a caller holding a `FellegiSunter` cannot skip them.
    """

    #: The share of the extract the fit believes are matches.
    match_rate: float
    #: P(feature agrees | the pair is a match).
    m: Mapping[Feature, float]
    #: P(feature agrees | the pair is not a match).
    u: Mapping[Feature, float]
    iterations: int
    converged: bool
    #: How many pairs were fitted. Carried so an export says what it was measured on.
    pairs: int

    def weights(self) -> Mapping[Feature, float]:
        """The weight of every fitted feature, strongest evidence highest."""
        return MappingProxyType({one: weight_of(self.m[one], self.u[one]) for one in self.m})

    def labels_are_inverted(self) -> bool:
        """Whether the class this fit calls a match is the class that agrees less.

        Compared on the mean rather than on one feature, because the swap is global: every m
        and u trade places together, so any single feature could legitimately be the exception
        while the fit as a whole is inverted. See
        `AN_INVERTED_SOLUTION_IS_THE_SAME_LIKELIHOOD_WITH_THE_LABELS_SWAPPED`.
        """
        if not self.m:
            return False
        mean_m = sum(self.m.values()) / len(self.m)
        mean_u = sum(self.u.values()) / len(self.u)
        return mean_m <= mean_u


def train(
    counts: Sequence[PatternCount],
    *,
    features: Sequence[Feature],
    max_iterations: int = MAX_ITERATIONS,
    tolerance: float = CONVERGENCE_TOLERANCE,
) -> FellegiSunter:
    """Expectation-maximisation over agreement patterns (M14.4.2).

    Two classes, conditional independence between features within each, and the standard two
    steps. The expectation step gives every pattern its posterior probability of being a match
    under the current parameters; the maximisation step re-estimates the parameters as the
    posterior-weighted proportions. Both are written out because the alternative is a
    dependency, and a dependency here is the thing M14.4.5 has to keep off the request path.

    Independence between features is an assumption and it is wrong in the direction that
    overstates: `name_exact` and `name_phonetic` agree together far more often than
    independently, so their weights double-count a single fact about spelling.
    `cascade.compare` reports at most one name feature per pair, which removes the worst of it
    for the name family and does nothing for a correlation between, say, a domain and an email.
    That is a limit of Fellegi-Sunter rather than of this implementation, and Splink models it
    with term-frequency adjustments this does not have.

    Refuses an extract that cannot identify a two-class model rather than returning a fit
    nobody can read: fewer distinct patterns than parameters, or an extract with no pairs in
    it, produce a fit whose numbers are arbitrary and confident-looking.
    """
    ordered = tuple(sorted(set(features), key=lambda one: one.value))
    if not ordered:
        msg = "a fit over no features has no parameters and no meaning"
        raise ResolutionError(msg)
    rows = tuple(one for one in counts if one.pairs > 0)
    total = sum(one.pairs for one in rows)
    if total <= 0:
        msg = "an extract with no pairs in it cannot be fitted; there is nothing to maximise"
        raise ResolutionError(msg)
    asked = {one.value for one in ordered}
    unknown = sorted({one.value for row in rows for one in row.pattern} - asked)
    if unknown:
        msg = (
            f"pattern(s) name feature(s) {', '.join(unknown)} that the fit was not asked for; "
            "a feature in the data and not in the parameter list is silently treated as never "
            "agreeing, which is a weight of nought reported as a measurement"
        )
        raise ResolutionError(msg)
    #: Two parameters per feature plus the match rate. Fewer distinct patterns than that and
    #: the likelihood has a ridge rather than a maximum, so the answer is the starting point
    #: wearing an iteration count.
    if len(rows) < 2 * len(ordered) + 1:
        msg = (
            f"{len(rows)} distinct agreement pattern(s) cannot identify {2 * len(ordered) + 1} "
            "parameters; the fit would return its starting point with an iteration count on it"
        )
        raise ResolutionError(msg)

    match_rate = INITIAL_MATCH_RATE
    m = dict.fromkeys(ordered, INITIAL_M)
    u = dict.fromkeys(ordered, INITIAL_U)

    iterations = 0
    converged = False
    for iterations in range(1, max_iterations + 1):  # noqa: B007 - the count is the result
        posteriors: list[float] = []
        for row in rows:
            as_match = match_rate
            as_other = 1.0 - match_rate
            for feature in ordered:
                agreed = feature in row.pattern
                as_match *= m[feature] if agreed else 1.0 - m[feature]
                as_other *= u[feature] if agreed else 1.0 - u[feature]
            denominator = as_match + as_other
            posteriors.append(0.0 if denominator <= 0.0 else as_match / denominator)

        expected_matches = sum(row.pairs * g for row, g in zip(rows, posteriors, strict=True))
        expected_others = total - expected_matches
        if expected_matches <= 0.0 or expected_others <= 0.0:
            msg = (
                "the fit collapsed onto one class, so every pair is a match or none is; that "
                "is an extract with no contrast in it rather than a model"
            )
            raise ResolutionError(msg)

        new_rate = expected_matches / total
        new_m: dict[Feature, float] = {}
        new_u: dict[Feature, float] = {}
        for feature in ordered:
            agree_match = sum(
                row.pairs * g
                for row, g in zip(rows, posteriors, strict=True)
                if feature in row.pattern
            )
            agree_other = sum(
                row.pairs * (1.0 - g)
                for row, g in zip(rows, posteriors, strict=True)
                if feature in row.pattern
            )
            new_m[feature] = _clamp(agree_match / expected_matches)
            new_u[feature] = _clamp(agree_other / expected_others)

        moved = max(
            [abs(new_rate - match_rate)]
            + [abs(new_m[one] - m[one]) for one in ordered]
            + [abs(new_u[one] - u[one]) for one in ordered]
        )
        match_rate, m, u = new_rate, new_m, new_u
        if moved < tolerance:
            converged = True
            break

    return FellegiSunter(
        match_rate=match_rate,
        m=MappingProxyType(dict(m)),
        u=MappingProxyType(dict(u)),
        iterations=iterations,
        converged=converged,
        pairs=total,
    )


# --------------------------------------------------------------- the export (M14.4.3)
@dataclass(frozen=True)
class WeightExport:
    """One calibration run's result, in the shape it travels in.

    A document rather than a pickled model, for the reason `brain.ops.vault` gives about
    secrets in transit: an artefact a person can read is an artefact a person can review, and a
    review is what `promote` requires. It also means the online side never deserialises
    anything a training job produced, which is the other half of M14.4.5.

    `reviewed_by` is a name and empty means nobody. It is on the export rather than in a
    separate approval record because the thing being approved is this set of figures, and an
    approval that can be separated from what it approved is an approval that outlives it.
    """

    ref: str
    version: str
    weights: Mapping[Feature, float]
    #: How many candidate pairs the fit was measured on.
    pairs: int
    iterations: int
    reviewed_by: str = ""

    def __post_init__(self) -> None:
        if not _REF_RE.match(self.ref) or len(self.ref) < MIN_REF_CHARS:
            msg = (
                f"{self.ref!r} is not an export reference. This string is the only evidence a "
                "weight table has that anything measured it, so it is held to a grammar: at "
                "least two parts joined by a separator, naming a job and a run rather than a "
                f"word meaning yes. {A_CALIBRATION_REF_IS_A_NAME_AND_NOT_A_BOOLEAN}"
            )
            raise ResolutionError(msg)
        if not self.version.strip():
            msg = "an export with no version cannot be told from another one"
            raise ResolutionError(msg)
        if self.pairs <= 0:
            msg = "an export measured on no pairs is a declaration wearing a reference"
            raise ResolutionError(msg)

    def to_weight_table(self) -> WeightTable:
        """This export as the table the online scorer sums (M14.3.5, M14.4.3).

        The one route in this repository that sets `calibration_ref`, and the only reason
        `WeightTable.calibrated` can ever be True. `WeightTable` refuses a partial table, so an
        export that fitted some of the features cannot become an online table with the rest
        silently at nought: an unweighted feature contributes nothing to the sum and looks
        exactly like one that never agreed.
        """
        return WeightTable(
            version=self.version,
            weights=MappingProxyType(dict(self.weights)),
            calibration_ref=self.ref,
        )

    def to_document(self) -> dict[str, Any]:
        """The export as plain data, keyed by the feature's machine name."""
        return {
            "ref": self.ref,
            "version": self.version,
            "pairs": self.pairs,
            "iterations": self.iterations,
            "reviewed_by": self.reviewed_by,
            "weights": {one.value: self.weights[one] for one in sorted(self.weights, key=str)},
        }


def from_document(document: Mapping[str, Any]) -> WeightExport:
    """Read an export back, refusing anything the fit could not have produced.

    A feature name the vocabulary does not hold is refused rather than skipped. Skipping is the
    tempting behaviour, because it makes an old export load against a newer cascade, and what
    it produces is a table missing the feature that was renamed, which `WeightTable` would then
    refuse for a reason naming the wrong thing.
    """
    weights: dict[Feature, float] = {}
    raw = document.get("weights")
    if not isinstance(raw, Mapping):
        msg = "an export document with no weights mapping is not an export"
        raise ResolutionError(msg)
    for name, value in raw.items():
        try:
            feature = Feature(str(name))
        except ValueError as exc:
            msg = (
                f"{name!r} is not a feature this cascade compares. An export naming one it "
                "does not hold was fitted against a different vocabulary, and loading it "
                "would produce a table whose missing feature is reported as unweighted"
            )
            raise ResolutionError(msg) from exc
        weights[feature] = float(value)
    return WeightExport(
        ref=str(document.get("ref", "")),
        version=str(document.get("version", "")),
        weights=MappingProxyType(weights),
        pairs=int(document.get("pairs", 0)),
        iterations=int(document.get("iterations", 0)),
        reviewed_by=str(document.get("reviewed_by", "")),
    )


def export(model: FellegiSunter, *, ref: str, version: str, reviewed_by: str = "") -> WeightExport:
    """A converged, non-inverted fit as a document (M14.4.3).

    Both refusals are here rather than at the load, because an export is the artefact that
    travels and the thing that travels should already have been checked. A fit that ran out of
    iterations is a fit whose parameters are wherever the search happened to be, and an
    inverted one is the right likelihood with every sign the wrong way round.
    """
    if not model.converged:
        msg = (
            f"the fit stopped after {model.iterations} iteration(s) without converging, so its "
            "parameters are wherever the search was when it ran out; exporting them would put "
            "an arbitrary weight table behind a calibration reference"
        )
        raise ResolutionError(msg)
    if model.labels_are_inverted():
        msg = (
            "the class this fit calls a match agrees less than the other one, which is the "
            "same likelihood with the labels swapped and exports every weight with its sign "
            f"inverted. {AN_INVERTED_SOLUTION_IS_THE_SAME_LIKELIHOOD_WITH_THE_LABELS_SWAPPED}"
        )
        raise ResolutionError(msg)
    return WeightExport(
        ref=ref,
        version=version,
        weights=model.weights(),
        pairs=model.pairs,
        iterations=model.iterations,
        reviewed_by=reviewed_by,
    )


# ------------------------------------------------------- the schedule and drift (M14.4.4)
#: How often the fit is re-run. The leaf's word, and one week exactly.
CALIBRATION_PERIOD: Final = timedelta(weeks=1)


def due(last_run_at: datetime, now: datetime) -> bool:
    """Whether the weekly fit is due. Both instants are parameters and neither is read here."""
    return now - last_run_at >= CALIBRATION_PERIOD


@dataclass(frozen=True)
class FeatureDrift:
    """One feature's weight before and after a re-fit, in bands as well as in figures."""

    feature: Feature
    before: float
    after: float

    @property
    def before_band(self) -> Strength:
        return strength_of(self.before)

    @property
    def after_band(self) -> Strength:
        return strength_of(self.after)

    @property
    def crosses_a_band(self) -> bool:
        """Whether this move changes the sentence a reviewer reads.

        See `A_DRIFT_THAT_CROSSES_A_BAND_IS_A_DIFFERENT_SENTENCE_TO_A_REVIEWER`.
        """
        return self.before_band is not self.after_band

    def render(self) -> str:
        """The line a person reviewing the week's drift reads. Bands, and no figures.

        `guardrails.PLAIN_LANGUAGE` is not reused here and the difference is deliberate: that
        mapping says what one field agreeing means about one pair, and this says what changed
        about a weight. Rendering a drift with the evidence sentence would tell a reviewer that
        two records agreed, which is not what they are being shown.
        """
        if not self.crosses_a_band:
            return f"{self.feature.value} stayed {self.before_band.name.lower()}"
        return (
            f"{self.feature.value} moved from {self.before_band.name.lower()} "
            f"to {self.after_band.name.lower()}"
        )


@dataclass(frozen=True)
class DriftReport:
    """What a week changed, as a person would read it.

    Every fitted feature is here, including the ones that did not move, for the reason
    `brain.ops.jobs.DeadLetterSummary` names every reason including the ones at nought: a
    report listing only what changed reads as though the rest were not measured.
    """

    previous_version: str
    candidate_ref: str
    moves: tuple[FeatureDrift, ...]

    @property
    def crossings(self) -> tuple[FeatureDrift, ...]:
        """The moves that change a sentence, strongest destination first."""
        crossed = [one for one in self.moves if one.crosses_a_band]
        return tuple(sorted(crossed, key=lambda one: (-int(one.after_band), one.feature.value)))

    @property
    def needs_review(self) -> bool:
        return bool(self.crossings)

    def explain(self) -> tuple[str, ...]:
        """Every move in words, in the feature order a reader can predict."""
        return tuple(one.render() for one in sorted(self.moves, key=lambda one: one.feature.value))


def drift(previous: WeightTable, candidate: WeightExport) -> DriftReport:
    """What a candidate export would change about the weights in force.

    Only the features the candidate fitted are compared. A feature the candidate did not fit is
    not a move to nought, and reporting it as one would put a crossing in front of a reviewer
    that describes an absence rather than a measurement; `to_weight_table` is where a partial
    export is refused, which is the right place for it.
    """
    moves = tuple(
        FeatureDrift(
            feature=feature,
            before=previous.weight_for(feature),
            after=candidate.weights[feature],
        )
        for feature in sorted(candidate.weights, key=lambda one: one.value)
    )
    return DriftReport(previous_version=previous.version, candidate_ref=candidate.ref, moves=moves)


def promote(previous: WeightTable, candidate: WeightExport) -> WeightTable:
    """The candidate as the table in force, or a refusal naming what nobody read (M14.4.4).

    The weekly job's last step, and the one that makes the schedule a schedule rather than a
    cron line. A crossing changes what a reviewer is told about a pair, so a crossing that no
    reviewer signed is refused here rather than reported and promoted anyway. A run that moved
    nothing across a band needs no reviewer, because there is no sentence to read.
    """
    report = drift(previous, candidate)
    if report.needs_review and not candidate.reviewed_by.strip():
        moved = ", ".join(one.render() for one in report.crossings)
        msg = (
            f"export {candidate.ref!r} moves a weight across a band and names no reviewer: "
            f"{moved}. {A_DRIFT_THAT_CROSSES_A_BAND_IS_A_DIFFERENT_SENTENCE_TO_A_REVIEWER}"
        )
        raise ResolutionError(msg)
    return candidate.to_weight_table()


# ------------------------------------------------- what would run this, and does not (M14.4.1)
@dataclass(frozen=True)
class ToolingStep:
    """One part of the offline job, against the package that would perform it.

    `brain.ops.jobs.DriverConcept`'s register applied to a different absent dependency, and a
    second instance of that shape rather than a second implementation of a rule: a queue
    driver's vocabulary and a record-linkage library's are two different correspondences, and
    importing that type here would make the resolution package depend on the operations one for
    a dataclass.

    `verified` exists to be False. `tooling_gaps` refuses a row claiming otherwise while the
    package cannot be imported, so the day somebody adds the dependency the check stops firing
    on its own rather than waiting for a reader to remember it was there.

    `built` is the other direction and it is the one that matters more here. Every row names
    something the tool would do; `built=False` says this repository has no counterpart for it,
    which is what turns a register that reads as a completed mapping into one that says where
    M14.4 stops. A step that is not built cannot be verified, and `tooling_gaps` says so.
    """

    ours: str
    theirs: str
    package: str
    note: str
    verified: bool = False
    #: Whether this repository has the part at all. False is the register's whole value.
    built: bool = True

    def __post_init__(self) -> None:
        for name in ("ours", "note"):
            if not str(getattr(self, name)).strip():
                msg = f"a tooling step with no {name} says nothing anybody can check"
                raise ResolutionError(msg)
        if self.verified and not self.built:
            msg = (
                f"{self.ours!r} claims to have been verified against {self.package!r} and does "
                "not exist in this repository; a verification of an absent part is a sentence "
                "with nothing behind it"
            )
            raise ResolutionError(msg)


#: Every part of this module against the tool M14.4.1 names for it. Nothing has been run.
OFFLINE_TOOLING: Final[tuple[ToolingStep, ...]] = (
    ToolingStep(
        ours="PatternCount",
        theirs="the comparison vector table a blocking pass materialises",
        package="duckdb",
        note=(
            "the extract, reduced to a pattern and a count. DuckDB is where the leaf puts it "
            "because the extract is a columnar scan over every candidate pair and Postgres "
            "would be doing it on the same server that answers requests. Nothing here reads "
            "or writes a DuckDB file: this is the shape such a file would be reduced to"
        ),
    ),
    ToolingStep(
        ours="train",
        theirs="the expectation-maximisation estimator over comparison vectors",
        package="splink",
        note=(
            "the same two steps over the same model. What Splink has and this does not is "
            "term-frequency adjustment, which weakens the agreement of a common value, and "
            "the blocking-rule machinery that decides which pairs are compared at all"
        ),
    ),
    ToolingStep(
        ours="weight_of",
        theirs="the match weight, log2 of the Bayes factor",
        package="splink",
        note=(
            "the same transformation and the same unit, which is what makes a comparison "
            "between the two possible on the day one can be run"
        ),
    ),
    ToolingStep(
        ours="WeightExport",
        theirs="the settings document a trained model is saved to",
        package="splink",
        note=(
            "both are a document rather than a serialised object, and neither is loaded by "
            "anything on the request path. The formats are not the same and no converter "
            "exists"
        ),
    ),
    ToolingStep(
        ours="the blocking pass",
        theirs="blocking rules",
        package="splink",
        built=False,
        note=(
            "not built here at all. Which pairs are compared is candidate generation, cascade "
            "answers about a pair it was handed, and nothing in this repository generates "
            "candidates. This is the largest gap in M14.4 and it is not a detail: an unblocked "
            "extract is every pair of records against every other"
        ),
    ),
    ToolingStep(
        ours="the labelled sample",
        theirs="the training set the estimator is fitted on",
        package="splink",
        built=False,
        note=(
            "not built. Nothing in this repository produces an extract of real candidate "
            "pairs, so every fit this module has performed was over figures a test wrote"
        ),
    ),
)


def unbuilt_steps(steps: Sequence[ToolingStep] | None = None) -> tuple[str, ...]:
    """The parts of the offline job this repository does not have, in declared order.

    Not a list of problems: it is what M14.4.1 would still need after everything here works.
    `brain.ops.jobs.ours_alone` is the same shape pointed the other way, at the parts a driver
    could not hold rather than at the parts we never wrote.
    """
    rows = OFFLINE_TOOLING if steps is None else tuple(steps)
    return tuple(step.ours for step in rows if not step.built)


def package_is_installed(package: str) -> bool:
    """Whether a named package can be imported in this environment.

    `find_spec` rather than an import, for the reason `brain.ops.queue.driver_is_installed`
    gives: asking costs nothing and importing a data library pulls in its dependency tree,
    which is precisely the tree this module exists to keep out of the request path.
    """
    return importlib.util.find_spec(package) is not None


def tooling_gaps(steps: Sequence[ToolingStep] | None = None) -> tuple[str, ...]:
    """Every way this register could be read as more settled than it is.

    A row claiming verification while its package cannot be imported is the finding that
    matters, because it is the sentence a reader trusts. The steps are a parameter defaulting
    to the declared ones, for the reason `brain.ops.jobs.driver_mapping_gaps` takes one: a
    check that can only ever be run against the constant beside it cannot be shown to fail.
    """
    rows = OFFLINE_TOOLING if steps is None else tuple(steps)
    return tuple(
        f"{step.ours!r} claims to be verified against {step.package!r}, which is not installed "
        f"in this environment. {THE_SPLINK_JOB_IS_NOT_BUILT_AND_THIS_SAYS_SO}"
        for step in rows
        if step.verified and not package_is_installed(step.package)
    )
