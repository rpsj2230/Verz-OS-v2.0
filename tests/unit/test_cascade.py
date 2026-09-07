"""The cascade, held to the order of its stages rather than to the answers it happens to give.

Four groups, one per stage, and then the three tables the stages read. The order is the whole
of the safety argument: a hard identifier is an identity and cannot be outvoted, a name cannot
promote itself, two thresholds make three outcomes, and the third outcome is a person. Each of
those is a property somebody could delete with a one-line edit that no test about matching
would notice, so each has a test named after the property rather than after the function.

Every refusal here has a sibling proving the ordinary case still works. A cascade tested only
by what it declines to merge is satisfied by one that merges nothing, and that cascade passes
every disclosure test in this file.

Two of these tests are here because the module was wrong when it was read. The rendered SQL
scored a pair of identical names three times where the Python scorer scored it once, which is
the double count the module's own docstring warns about; and the confidence check inside
`cascade_gaps` read a module constant, so nothing could make it fire.

Task ids: M14.3.1, M14.3.2, M14.3.3, M14.3.4, M14.3.5, M14.3.6, M14.3.7, M14.3.8
"""

from __future__ import annotations

import ast
import inspect
import sqlite3
from collections.abc import Mapping
from dataclasses import fields as dataclass_fields
from pathlib import Path

import pytest

from brain.resolution import cascade as cascade_module
from brain.resolution.canonical import IdentifierKind, ResolutionError, SourceRef
from brain.resolution.cascade import (
    DECLARED_CONFIDENCE,
    DECLARED_THRESHOLDS,
    DECLARED_WEIGHTS,
    DM_CODE_LENGTH,
    FREE_MAIL_DOMAINS,
    HARD_IDENTIFIERS,
    MAX_PHONETIC_CODES,
    MIN_REVIEW_BAND,
    NAME_EQUALITY_FEATURES,
    NAME_FEATURES,
    PHONETIC_WEIGHT,
    SQL_PREDICATES,
    CascadeResult,
    Comparison,
    CorroboratedName,
    Decision,
    Feature,
    Observation,
    Stage,
    Thresholds,
    WeightTable,
    cascade,
    cascade_gaps,
    compare,
    corroboration_for,
    domain_key,
    evidence_for,
    phonetic_agrees,
    phonetic_codes,
    score,
    sql_score_expression,
    trigram_similarity,
    trigrams,
    usable_identifiers,
)
from brain.resolution.guardrails import (
    BLOCK_REASONS,
    SUPPORTING_WEIGHT,
    BlockRule,
    ReviewItem,
    Strength,
    priority_of,
    review_queue,
    strength_of,
)
from brain.resolution.normalise import MIN_KEY_CHARS, normalise_name
from brain.resolution.query import weight_parameters

PEPPER = "a-deployment-secret"

#: Two digests that are the shape `canonical.identifier_hash` produces and nothing else.
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64

#: A client name that appears in no module and in no blocklist, so a test asserting that a
#: refusal does not quote its input has something specific to look for.
SECRET = "kandangkerbauholdings"


def observation(
    name: str,
    *,
    record: str = "1",
    source_name: str = "freshdesk",
    identifiers: Mapping[IdentifierKind, str] | None = None,
    fields: Mapping[Feature, str] | None = None,
    verified: frozenset[IdentifierKind] = frozenset(),
) -> Observation:
    """One source record as the cascade may compare it."""
    return Observation(
        record=SourceRef(source=source_name, entity="company", source_id=record),
        name=normalise_name(name),
        identifiers=dict(identifiers or {}),
        fields=dict(fields or {}),
        verified=verified,
    )


# ------------------------------------------------------- stage one: identity (M14.3.1)
def test_a_hard_identifier_that_agrees_settles_the_pair_before_anything_is_scored() -> None:
    """**Two records carrying one UEN are one registered company.**

    Stage one returns an identity rather than a score, so the answer is MATCHED at
    `Stage.HARD_IDENTIFIER` with the confidence the stage declares, and it arrives for a pair
    whose names disagree completely. That last part is the test: if the sum decided, two names
    with a similarity of nought would have pulled the answer down.

    Delete this and the whole positive half of stage one goes untested, and a cascade that
    refused every pair would satisfy every other stage-one test in this file."""
    left = observation("Acme Trading Pte Ltd", identifiers={IdentifierKind.UEN: DIGEST_A})
    right = observation(
        "Something Else Entirely", record="2", identifiers={IdentifierKind.UEN: DIGEST_A}
    )

    result = cascade(left, right)

    assert result.decision is Decision.MATCHED
    assert result.stage is Stage.HARD_IDENTIFIER
    assert result.confidence == DECLARED_CONFIDENCE[Stage.HARD_IDENTIFIER]
    assert trigram_similarity("acme trading", "something else entirely") < DECLARED_THRESHOLDS.lower


def test_a_hard_identifier_that_disagrees_is_not_overturned_by_an_identical_name() -> None:
    """The half of stage one that a scoring implementation gets wrong.

    Under an additive model a UEN that disagrees plus a name that agrees exactly is a match,
    and the merge carries a confident-sounding total nobody goes back and checks. Here the
    strongest hard identifier both records carry decides, and when it disagrees the answer is
    NOT_MATCHED however strong everything underneath it is.

    The two records below agree on their name, their country and their postcode, which is
    every corroboration stage two could ask for, and it changes nothing.

    Delete this and the cascade can fall through to the name on a UEN mismatch, which is the
    single merge in this module that would be both wrong and confident."""
    left = observation(
        "Acme Trading Pte Ltd",
        identifiers={IdentifierKind.UEN: DIGEST_A},
        fields={Feature.COUNTRY: "sg", Feature.POSTCODE: "049315"},
    )
    right = observation(
        "Acme Trading Pte Ltd",
        record="2",
        identifiers={IdentifierKind.UEN: DIGEST_B},
        fields={Feature.COUNTRY: "sg", Feature.POSTCODE: "049315"},
    )

    result = cascade(left, right)

    assert result.decision is Decision.NOT_MATCHED
    assert result.stage is Stage.HARD_IDENTIFIER
    assert result.confidence is None
    # The corroboration that would have carried stage two is present and was not consulted.
    assert corroboration_for(compare(left, right)) is not None


def test_an_unverified_domain_is_scored_rather_than_deciding_stage_one_alone() -> None:
    """ "Verified domain" is the leaf's wording and the word is load-bearing.

    A domain scraped off a signature and a domain a source confirmed the customer controls are
    different facts. The unverified one is demoted rather than discarded: it still compares and
    still appears in the evidence, it simply does not decide by itself.

    Both halves are here. Without the positive half a cascade that ignored `verified` entirely
    would pass, and stage one would have lost two of its four identifiers.

    Delete this and `VERIFICATION_REQUIRED` can be emptied, and a domain read off an email
    signature merges two companies at confidence one."""
    scraped_left = observation("Acme Trading", identifiers={IdentifierKind.DOMAIN: DIGEST_A})
    scraped_right = observation(
        "Beta Holdings", record="2", identifiers={IdentifierKind.DOMAIN: DIGEST_A}
    )

    unverified = cascade(scraped_left, scraped_right)

    assert unverified.decision is not Decision.MATCHED
    assert unverified.stage is not Stage.HARD_IDENTIFIER
    assert Feature.DOMAIN in compare(scraped_left, scraped_right).agreed

    confirmed_left = observation(
        "Acme Trading",
        identifiers={IdentifierKind.DOMAIN: DIGEST_A},
        verified=frozenset({IdentifierKind.DOMAIN}),
    )
    confirmed_right = observation(
        "Beta Holdings",
        record="2",
        identifiers={IdentifierKind.DOMAIN: DIGEST_A},
        verified=frozenset({IdentifierKind.DOMAIN}),
    )

    confirmed = cascade(confirmed_left, confirmed_right)

    assert confirmed.decision is Decision.MATCHED
    assert confirmed.stage is Stage.HARD_IDENTIFIER


def test_every_identifier_that_decides_stage_one_outranks_the_weakest_one_there_is() -> None:
    """The four hard identifiers are held against `guardrails`' order, not against themselves.

    M14.3.1 names UEN, tax id, verified domain and verified phone, and the honest check that
    EMAIL is absent is not "email is not in the tuple", which restates the tuple. It is that
    every kind stage one may merge on outranks EMAIL in the priority order another module
    wrote, where an address identifies a person at best and a shared mailbox identifies nobody.

    Delete this and EMAIL can be added to `HARD_IDENTIFIERS`, and twenty companies listing one
    role address become one entity at confidence one, in a module whose blocklist exists to
    stop exactly that."""
    weakest = priority_of(IdentifierKind.EMAIL)

    assert HARD_IDENTIFIERS
    for kind in HARD_IDENTIFIERS:
        assert priority_of(kind) < weakest, f"{kind.value} does not outrank email"
    assert IdentifierKind.EMAIL not in HARD_IDENTIFIERS


def test_the_strongest_shared_hard_identifier_decides_and_not_the_first_one_found() -> None:
    """A UEN that agrees beats a verified domain that disagrees, and the reverse is refused.

    Two records can share more than one hard identifier and the two can say different things.
    The strongest present decides, which is `guardrails`' tie rule applied to a pair, and
    walking the list in declaration order or taking whichever was seen first would let a domain
    overrule a register.

    Delete this and `min(..., key=priority_of)` can become `next(iter(...))`, which passes every
    single-identifier test in this file."""
    agreeing_uen = {IdentifierKind.UEN: DIGEST_A, IdentifierKind.DOMAIN: DIGEST_A}
    disagreeing_domain = {IdentifierKind.UEN: DIGEST_A, IdentifierKind.DOMAIN: DIGEST_B}
    both_verified = frozenset({IdentifierKind.DOMAIN})

    left = observation("Acme Trading", identifiers=agreeing_uen, verified=both_verified)
    right = observation(
        "Beta Holdings", record="2", identifiers=disagreeing_domain, verified=both_verified
    )

    result = cascade(left, right)

    assert result.decision is Decision.MATCHED
    assert compare(left, right).hard_kind is IdentifierKind.UEN


# ------------------------------------------------------- stage two: corroboration (M14.3.2)
def test_a_name_cannot_corroborate_itself_because_the_value_does_not_exist() -> None:
    """**The guard is a type rather than a condition, and this is what that buys.**

    "The names agree, and the trigrams also agree" is one fact reported twice, and a condition
    saying so is an `if` somebody loosens when the review queue gets long. `CorroboratedName`
    refuses construction, so the promotion is not a value this module can hold, and widening it
    means deleting a check in a frozen dataclass rather than editing a boolean.

    Both slots are checked, because refusing only the corroborant leaves the two fillable the
    other way round.

    Delete this and the check in `__post_init__` can go, and stage two becomes "the names
    agree", which is exactly the promotion M14.3.2 exists to prevent."""
    for name_feature in NAME_FEATURES:
        with pytest.raises(ResolutionError):
            CorroboratedName(name=Feature.NAME_EXACT, corroborant=name_feature)

    with pytest.raises(ResolutionError):
        CorroboratedName(name=Feature.COUNTRY, corroborant=Feature.POSTCODE)

    admitted = CorroboratedName(name=Feature.NAME_EXACT, corroborant=Feature.COUNTRY)
    assert admitted.corroborant not in NAME_FEATURES


def test_names_that_are_equal_with_nothing_beside_them_go_to_a_person_and_are_not_merged() -> None:
    """**The stage-two guard was decorative, because stage three merged what it refused.**

    Two equal keys have a trigram similarity of one, which is above every upper threshold the
    band guard admits, so a pair whose names agreed and which stage two refused for want of a
    second field was merged one branch later at a lower confidence. Stage two chose which
    confidence a name agreement was recorded with and refused nothing at all.

    Both shapes of equality are here, and the second is the one `normalise` warns about: the
    collapsed forms differ and the keys agree only because the legal forms came off, which is
    "Ace Co" and "Ace" being one key. The similarity is asserted to be above the upper
    threshold in both, because that is the value that used to merge them.

    Delete this and the branch goes with it, M14.3.2 stops refusing anything, and every pair of
    identical names in the estate merges automatically on the name alone."""
    for left_name, right_name, agreement in (
        ("Acme Trading Pte Ltd", "Acme Trading Pte Ltd", Feature.NAME_EXACT),
        ("Acme Trading Pte Ltd", "Acme Trading Limited", Feature.NAME_STRIPPED),
    ):
        left = observation(left_name)
        right = observation(right_name, record="2")
        comparison = compare(left, right)
        result = cascade(left, right)

        assert agreement in comparison.agreed
        assert corroboration_for(comparison) is None
        assert comparison.similarity is not None
        assert comparison.similarity >= DECLARED_THRESHOLDS.upper
        assert result.decision is Decision.TO_REVIEW, left_name
        assert result.stage is Stage.HUMAN_REVIEW


def test_the_two_name_equalities_are_written_out_and_the_measured_one_is_not_among_them() -> None:
    """The set that decides which name agreements need a second field, held apart from the sum.

    `NAME_EQUALITY_FEATURES` is the two agreements that are one string being another, and
    `NAME_TRIGRAM` is deliberately not one of them: it is an overlap measured between two keys
    that differ, which is what stage three thresholds. Derived as "the name features that are
    not the trigram", the set and the rule would agree by construction and a new name feature
    spelled some other way would land on whichever side the derivation happened to put it.

    Delete this and `NAME_TRIGRAM` can be added to the equality set, which sends every
    near-match to a reviewer, or the set can be emptied, which merges every identical name."""
    assert NAME_EQUALITY_FEATURES.issubset(NAME_FEATURES)
    assert NAME_EQUALITY_FEATURES != NAME_FEATURES
    assert Feature.NAME_TRIGRAM not in NAME_EQUALITY_FEATURES
    assert Feature.NAME_PHONETIC not in NAME_EQUALITY_FEATURES
    assert Feature.NAME_EXACT in NAME_EQUALITY_FEATURES
    assert Feature.NAME_STRIPPED in NAME_EQUALITY_FEATURES
    assert len(NAME_EQUALITY_FEATURES) == 2


def test_a_name_with_a_second_non_name_field_beside_it_merges_at_stage_two() -> None:
    """The positive half, without which a cascade that never promotes anything passes.

    One name feature plus one field that is not a name is what M14.3.2 asks for, and the answer
    is MATCHED at `Stage.CORROBORATED_NAME` with that stage's confidence.

    Delete this and stage two can be removed entirely and the suite stays green, because every
    other stage-two test here is a refusal."""
    left = observation("Acme Trading Pte Ltd", fields={Feature.POSTCODE: "049315"})
    right = observation("Acme Trading Pte Ltd", record="2", fields={Feature.POSTCODE: "049315"})

    result = cascade(left, right)

    assert result.decision is Decision.MATCHED
    assert result.stage is Stage.CORROBORATED_NAME
    assert result.confidence == DECLARED_CONFIDENCE[Stage.CORROBORATED_NAME]

    corroborated = corroboration_for(compare(left, right))
    assert corroborated is not None
    assert corroborated.corroborant is Feature.POSTCODE


def test_an_observation_cannot_carry_a_name_feature_as_a_corroborating_field() -> None:
    """The other door into stage two, closed at the type that carries the fields.

    `CorroboratedName` refuses a name feature in the corroborant slot, and a caller could still
    have reached the same place by putting a name feature on `Observation.fields`, where
    `compare` would have found it and offered it as a corroborator.

    The positive half is that the two real field features are admitted, and without it a type
    that refused every field would pass.

    Delete this and the corroboration guard has a second entrance nobody is watching."""
    for feature in NAME_FEATURES:
        with pytest.raises(ResolutionError):
            observation("Acme Trading", fields={feature: "anything"})

    admitted = observation(
        "Acme Trading", fields={Feature.COUNTRY: "sg", Feature.POSTCODE: "049315"}
    )
    assert set(admitted.fields) == {Feature.COUNTRY, Feature.POSTCODE}


# ------------------------------------------------- stage three: two thresholds (M14.3.3)
def test_a_similarity_at_the_upper_threshold_merges_and_one_below_the_lower_does_not() -> None:
    """The two ends of stage three, tested on the boundary rather than near it.

    "tan ah kow trading" against "tan ah kow tradings" is seventeen shared trigrams out of
    twenty, which is exactly the declared upper threshold, so the pair sits on the comparison
    rather than either side of it: an admission written `>` instead of `>=` refuses it, and a
    threshold moved by a hundredth in either direction changes the answer. Test data far from
    the boundary would survive both of those.

    Delete this and the upper threshold can be moved anywhere between the lower one and one,
    and the comparison can be loosened or tightened by a character, with nothing failing."""
    at_the_threshold = trigram_similarity("tan ah kow trading", "tan ah kow tradings")
    assert at_the_threshold == DECLARED_THRESHOLDS.upper

    merged = cascade(
        observation("Tan Ah Kow Trading"), observation("Tan Ah Kow Tradings", record="2")
    )
    assert merged.decision is Decision.MATCHED
    assert merged.stage is Stage.SIMILARITY
    assert merged.confidence == DECLARED_CONFIDENCE[Stage.SIMILARITY]

    refused = cascade(observation("Acme Trading"), observation("Acme Holdings", record="2"))
    assert trigram_similarity("acme trading", "acme holdings") < DECLARED_THRESHOLDS.lower
    assert refused.decision is Decision.NOT_MATCHED
    assert refused.stage is Stage.SIMILARITY
    assert refused.confidence is None


def test_two_thresholds_that_meet_cannot_be_constructed() -> None:
    """**Setting upper equal to lower deletes human review and fails no test about matching.**

    One threshold gives two outcomes. The cascade would go on merging what it merged and
    refusing what it refused, and the band M14.3.4 asks for would simply have nothing in it,
    which no test about a match and no test about a refusal would notice. So the type refuses
    it, and refuses the inverted case as well.

    Delete this and `upper <= lower` becomes a one-character edit with no consequence in the
    suite, and the fourth stage of a four-stage cascade quietly stops existing."""
    with pytest.raises(ResolutionError):
        Thresholds(upper=0.6, lower=0.6)
    with pytest.raises(ResolutionError):
        Thresholds(upper=0.4, lower=0.6)
    with pytest.raises(ResolutionError):
        Thresholds(upper=0.9, lower=0.0)
    with pytest.raises(ResolutionError):
        Thresholds(upper=1.5, lower=0.6)

    admitted = Thresholds(upper=0.9, lower=0.5)
    assert admitted.upper - admitted.lower >= MIN_REVIEW_BAND


def test_a_review_band_narrower_than_one_trigram_is_refused_as_empty_in_practice() -> None:
    """A band of a thousandth is non-empty in arithmetic and holds nothing a key can produce.

    The floor is anchored to `normalise.MIN_KEY_CHARS` rather than chosen: the shortest key the
    cascade will look at has `MIN_KEY_CHARS + 1` trigrams, so one trigram is a fifth of it, and
    a band narrower than one trigram cannot contain any similarity two keys of that length can
    take. The derivation is checked here against the figure it comes from, which is the only
    way a literal can be tested without comparing it with itself.

    Delete this and `MIN_REVIEW_BAND` can be set to anything, up to and including a value so
    small that the band admits nothing, which is `upper == lower` with extra steps."""
    assert MIN_REVIEW_BAND == 1 / (MIN_KEY_CHARS + 1)

    # Distinct letters, because trigrams are a set: "aaaa" yields four of them rather than
    # five, and a key of repeated characters is refused as a held-down key anyway.
    shortest_key = "".join(chr(ord("a") + step) for step in range(MIN_KEY_CHARS))
    assert len(trigrams(shortest_key)) == MIN_KEY_CHARS + 1

    with pytest.raises(ResolutionError):
        Thresholds(upper=0.85, lower=0.85 - MIN_REVIEW_BAND / 2)

    assert DECLARED_THRESHOLDS.upper - DECLARED_THRESHOLDS.lower >= MIN_REVIEW_BAND


def test_a_pair_of_names_neither_of_which_may_be_matched_on_produces_no_similarity() -> None:
    """`normalise`'s verdict is a guard for this call site and the cascade has to honour it.

    A key shorter than the minimum carries fewer trigrams than a similarity is a measurement
    over. `match_key` is None for those, and a caller that read `key` instead would join every
    short name to every other. With nothing else agreeing there is nothing for a person to
    weigh either, so the answer is a refusal rather than a queue item.

    Delete this and `compare` can read `name.key`, and every two-letter initialism in the
    estate becomes a candidate for every other."""
    left = observation("IBM")
    right = observation("IBN", record="2")

    assert left.name.match_key is None
    comparison = compare(left, right)

    assert comparison.similarity is None
    assert not comparison.agreed
    assert cascade(left, right).decision is Decision.NOT_MATCHED


# --------------------------------------------------- stage four: the band is a person (M14.3.4)
def test_a_similarity_between_the_thresholds_goes_to_a_person_rather_than_to_the_cascade() -> None:
    """**Two thresholds make three outcomes and the third one is not a refusal.**

    "peters" against "peterson" is six shared trigrams out of ten, which is exactly the
    declared lower threshold, so the pair sits on the lower comparison the way the stage-three
    test sits on the upper one: `lower <= similarity` admits it to the band and
    `lower < similarity` does not.

    Delete this and stage four can be deleted with it, and every pair in the band is answered
    by the cascade instead of being handed to somebody who can look at the records."""
    on_the_lower_edge = trigram_similarity("peters", "peterson")
    assert on_the_lower_edge == DECLARED_THRESHOLDS.lower
    assert DECLARED_THRESHOLDS.band_holds(on_the_lower_edge)

    result = cascade(observation("Peters"), observation("Peterson", record="2"))

    assert result.decision is Decision.TO_REVIEW
    assert result.stage is Stage.HUMAN_REVIEW
    assert result.confidence is None


def test_a_pair_the_cascade_decided_cannot_be_put_in_front_of_a_reviewer() -> None:
    """A queue holding decided pairs teaches its reviewers to approve everything.

    A reviewer shown a pair the cascade already settled assumes their opinion was wanted, and
    the queue stops being a list of open questions. So only `TO_REVIEW` becomes a `ReviewItem`,
    and everything else refuses.

    Delete this and a caller can queue every pair it looked at, which is a review queue nobody
    finishes and a reviewer who stops reading."""
    in_the_band = cascade(observation("Peters"), observation("Peterson", record="2"))
    item = in_the_band.review_item("rev-1")

    assert isinstance(item, ReviewItem)
    assert item.left == in_the_band.left
    assert item.right == in_the_band.right

    decided = cascade(
        observation("Acme Trading", identifiers={IdentifierKind.UEN: DIGEST_A}),
        observation("Acme Trading", record="2", identifiers={IdentifierKind.UEN: DIGEST_A}),
    )
    with pytest.raises(ResolutionError):
        decided.review_item("rev-2")


def test_a_review_item_reaches_a_person_only_through_the_filter_that_knows_their_reach() -> None:
    """**Nothing in this module filters by reach, and that is the point rather than a gap.**

    A reviewer who reaches one of two records cannot decide whether they are one thing and must
    not be told the other exists. That filter is a conjunction and it lives in
    `guardrails.review_queue`; a second copy here would be a second place for it to be subtly
    wrong, and the wrong copy is the one in production.

    The positive half is the reviewer who reaches both and gets the item, without which a queue
    that showed nobody anything would pass.

    Delete this and a reach filter grows here, disagrees with the one in `guardrails`, and the
    disagreement is invisible until somebody is shown a record they may not read."""
    in_the_band = cascade(observation("Peters"), observation("Peterson", record="2"))
    item = in_the_band.review_item("rev-1")

    reaches_one = review_queue(
        [item], reviewer_id="alice", reaches=lambda member: member.source_id == "1"
    )
    assert reaches_one.items == ()

    reaches_both = review_queue([item], reviewer_id="bob", reaches=lambda member: True)
    assert reaches_both.items == (item,)

    assert "reach" not in inspect.signature(CascadeResult.review_item).parameters


def test_a_pair_whose_names_cannot_be_measured_reaches_a_person_when_something_else_agreed() -> (
    None
):
    """Queueing every unmeasurable pair makes the queue the estate, and queueing none loses them.

    A name too short to threshold is not a bad name: a real company is called IBM. So a pair
    with no similarity to measure goes to a person when something else agreed, and is refused
    when nothing did, and the two cases are tested together because the difference between them
    is the whole rule.

    Delete this and either every short name in the estate is queued or none of them ever is,
    and both look correct from the outside."""
    left = observation("IBM", fields={Feature.POSTCODE: "049315"})
    right = observation("IBN", record="2", fields={Feature.POSTCODE: "049315"})

    queued = cascade(left, right)
    assert queued.decision is Decision.TO_REVIEW
    assert queued.stage is Stage.HUMAN_REVIEW

    nothing_agreed = cascade(
        observation("IBM", fields={Feature.POSTCODE: "049315"}),
        observation("IBN", record="2", fields={Feature.POSTCODE: "018956"}),
    )
    assert nothing_agreed.decision is Decision.NOT_MATCHED


# ------------------------------------------------------------- the weight table (M14.3.5)
def test_a_weight_table_cannot_claim_calibration_without_naming_the_export() -> None:
    """**M14.3.5 says "exported from offline calibration" and this table is not one.**

    `brain.resolution.calibration` can now produce an export and nothing has run it against
    real data, so every figure in the declared table was still chosen by an author.
    `calibrated` is a property derived from `calibration_ref` rather than a field, so there is
    no boolean to set to True and claiming calibration means naming the export that produced
    it. `tests/unit/test_resolution_calibration.py` holds the other end of that: an export is
    the only route in this repository that sets the reference.

    Both halves matter: the structural one says there is no field, and the positive one says a
    table that does name an export reports itself as calibrated, so the property is not simply
    hard-wired to False.

    Delete this and `calibrated` becomes a settable field, and the day somebody wants the
    console to stop showing a caveat they set it to True and the caveat was the only thing
    saying the numbers are guesses."""
    assert DECLARED_WEIGHTS.calibrated is False
    assert DECLARED_WEIGHTS.calibration_ref == ""
    assert "calibrated" not in {one.name for one in dataclass_fields(WeightTable)}

    named = WeightTable(
        version="from-a-job",
        weights=dict(DECLARED_WEIGHTS.weights),
        calibration_ref="splink-2026-09-07",
    )
    assert named.calibrated is True


def test_every_declared_weight_renders_as_the_strength_its_comment_claims() -> None:
    """The weights are held against the bands a reviewer reads, not against themselves.

    A test asserting `weight_for(UEN) == DECISIVE_WEIGHT` while importing both from the modules
    under test compares a constant with itself and is green for every value it could hold. The
    property that actually matters is the sentence a reviewer sees, so each weight is checked
    through `guardrails.strength_of`, which is the function that turns a figure into that
    sentence.

    Delete this and a weight can drift to a value that renders to a reviewer as a different
    strength than the author intended, with the arithmetic still adding up."""
    expected = {
        Feature.UEN: Strength.DECISIVE,
        Feature.TAX_ID: Strength.DECISIVE,
        Feature.DOMAIN: Strength.STRONG,
        Feature.NAME_EXACT: Strength.STRONG,
        Feature.PHONE: Strength.SUPPORTING,
        Feature.EMAIL: Strength.SUPPORTING,
        Feature.NAME_STRIPPED: Strength.SUPPORTING,
        Feature.NAME_TRIGRAM: Strength.SUPPORTING,
        Feature.COUNTRY: Strength.SUPPORTING,
        Feature.POSTCODE: Strength.SUPPORTING,
        Feature.NAME_PHONETIC: Strength.WEAK,
    }
    assert set(expected) == set(Feature)

    for feature, band in expected.items():
        assert strength_of(DECLARED_WEIGHTS.weight_for(feature)) is band, feature.value


def test_a_feature_with_no_weight_is_refused_rather_than_scored_at_nothing() -> None:
    """An unweighted feature is indistinguishable from one that never agreed.

    A default of zero would make a forgotten feature look like a feature that agreed and told
    us nothing, which is a silent miss in the direction that produces fewer merges and no
    report. The table refuses at construction, and `weight_for` refuses again for a table built
    some other way.

    Delete this and adding a `Feature` member without a weight is a change nothing catches,
    and the new comparison contributes nothing to any score for as long as nobody looks."""
    incomplete: dict[Feature, float] = {
        feature: 1.0 for feature in Feature if feature is not Feature.POSTCODE
    }

    with pytest.raises(ResolutionError):
        WeightTable(version="incomplete", weights=incomplete)

    with pytest.raises(ResolutionError):
        WeightTable(version="   ", weights=dict(DECLARED_WEIGHTS.weights))

    complete = WeightTable(version="complete", weights=dict(DECLARED_WEIGHTS.weights))
    assert complete.weight_for(Feature.POSTCODE) == DECLARED_WEIGHTS.weight_for(Feature.POSTCODE)


# --------------------------------------------------- additive scoring in SQL (M14.3.6)
#: The columns a rendered predicate may name, which is every column `SQL_PREDICATES` uses.
_SQL_COLUMNS = (
    "uen_hash",
    "tax_id_hash",
    "domain_hash",
    "phone_hash",
    "email_hash",
    "name_collapsed",
    "name_key",
    "name_dm",
    "country_key",
    "postcode_key",
)

#: PostgreSQL's array overlap, which SQLite has no parser for. Rewritten into a function
#: registered on the connection, and the rewrite is asserted to have changed something so a
#: predicate that stops using the operator fails loudly rather than evaluating as absent.
_ARRAY_OVERLAP = "l.name_dm && r.name_dm"
_OVERLAP_CALL = "overlaps(l.name_dm, r.name_dm)"


def _row(record: Observation, *, dm_from_key: bool = True) -> list[str | None]:
    """One record as the columns the rendered expression names.

    `name_dm` is the phonetic codes materialised at write time, which is what
    `WHAT_WOULD_BREAK_THE_SQL_SHAPE` says the phonetic term assumes. Two plausible
    materialisations exist and this module owns neither: coding the match key, in which case
    the column is NULL wherever the name may not be matched on, and coding the collapsed form,
    in which case it is not. `dm_from_key` is which one, and the rendered expression has to
    give the same total under both, because no migration in this repository decides it.
    """
    key = record.name.match_key
    coded = key if dm_from_key else record.name.collapsed
    return [
        record.identifiers.get(IdentifierKind.UEN),
        record.identifiers.get(IdentifierKind.TAX_ID),
        record.identifiers.get(IdentifierKind.DOMAIN),
        record.identifiers.get(IdentifierKind.PHONE),
        record.identifiers.get(IdentifierKind.EMAIL),
        record.name.collapsed,
        key,
        " ".join(sorted(phonetic_codes(coded))) if coded is not None else None,
        record.fields.get(Feature.COUNTRY),
        record.fields.get(Feature.POSTCODE),
    ]


def _similarity(left: str | None, right: str | None) -> float | None:
    if left is None or right is None:
        return None
    return trigram_similarity(left, right)


def _overlaps(left: str | None, right: str | None) -> bool | None:
    if left is None or right is None:
        return None
    return bool(set(left.split()) & set(right.split()))


def _evaluate_rendered_sql(
    left: Observation, right: Observation, *, dm_from_key: bool = True
) -> float:
    """Run the rendered expression over two records and return the total it produces."""
    rendered = sql_score_expression()
    runnable = rendered.replace(_ARRAY_OVERLAP, _OVERLAP_CALL)
    assert runnable != rendered, "the phonetic predicate no longer uses the array operator"
    body = "\n".join(line for line in runnable.splitlines() if not line.startswith("--"))

    connection = sqlite3.connect(":memory:")
    try:
        connection.create_function("similarity", 2, _similarity)
        connection.create_function("overlaps", 2, _overlaps)
        connection.execute(
            "CREATE TABLE rec (side TEXT, uen_hash TEXT, tax_id_hash TEXT, domain_hash TEXT, "
            "phone_hash TEXT, email_hash TEXT, name_collapsed TEXT, name_key TEXT, "
            "name_dm TEXT, country_key TEXT, postcode_key TEXT)"
        )
        placeholders = ", ".join("?" * (len(_SQL_COLUMNS) + 1))
        connection.execute(
            f"INSERT INTO rec VALUES ({placeholders})",  # noqa: S608
            ["l", *_row(left, dm_from_key=dm_from_key)],
        )
        connection.execute(
            f"INSERT INTO rec VALUES ({placeholders})",  # noqa: S608
            ["r", *_row(right, dm_from_key=dm_from_key)],
        )
        query = f"SELECT {body} FROM rec l, rec r WHERE l.side = 'l' AND r.side = 'r'"  # noqa: S608
        bound = {**weight_parameters(), "upper": DECLARED_THRESHOLDS.upper}
        rows = connection.execute(query, bound).fetchall()
    finally:
        connection.close()
    return float(rows[0][0])


def test_the_rendered_sql_expression_scores_a_pair_exactly_as_the_python_scorer_does() -> None:
    """**The two halves were not the same scoring rule and this is the test that says so.**

    M14.3.6 asks for an additive score evaluated in plain SQL, which means the query and the
    Python reasoning have to be one rule rather than two that agree today. They were two. The
    name predicates were four bare equalities, so a pair of identical names satisfied
    `name_collapsed`, `name_key` and the similarity threshold at once and scored six and a half
    where `score` scored four and a half: the double count the module's own docstring warns
    about, in the rendered half, on the pairs that match most often.

    Evaluated rather than read, in SQLite, so the parser is not this test's opinion about what
    the expression means. The one rewrite is PostgreSQL's array overlap, which SQLite cannot
    parse, and it is asserted to have found something.

    Run twice, under both plausible materialisations of the phonetic column, because no
    migration in this repository decides which one a deployment would use and the expression
    has to be right either way. Coding the match key makes the column NULL wherever the name
    may not be matched on; coding the collapsed form does not, and the guard on the phonetic
    term is the only thing that keeps the two totals equal in the second case.

    Delete this and the two halves drift again, silently, because nothing else compares them."""
    pairs = (
        (observation("Acme Trading Pte Ltd"), observation("Acme Trading Pte Ltd", record="2")),
        (observation("Acme Trading Pte Ltd"), observation("Acme Trading Limited", record="2")),
        (observation("Tan Ah Kow Trading"), observation("Tan Ah Kow Tradings", record="2")),
        (observation("Acme Trading"), observation("Acme Holdings", record="2")),
        (observation("Schwartz Group"), observation("Shvarts Group", record="2")),
        # Two names that collapse to the same string and may not be matched on. `compare`
        # evaluates no name feature at all for this pair, and it is the pair that says whether
        # the guards on the two name terms that read a collapsed form are doing anything.
        (observation("IBM"), observation("IBM", record="2")),
        (
            observation(
                "Acme Trading",
                identifiers={IdentifierKind.UEN: DIGEST_A, IdentifierKind.EMAIL: DIGEST_B},
                fields={Feature.COUNTRY: "sg"},
            ),
            observation(
                "Acme Trading",
                record="2",
                identifiers={IdentifierKind.UEN: DIGEST_A, IdentifierKind.EMAIL: DIGEST_B},
                fields={Feature.COUNTRY: "sg"},
            ),
        ),
    )

    for dm_from_key in (True, False):
        for left, right in pairs:
            agreed = compare(left, right).agreed
            total = _evaluate_rendered_sql(left, right, dm_from_key=dm_from_key)
            assert total == pytest.approx(score(agreed)), (
                f"{left.name.observed!r} against {right.name.observed!r}, "
                f"phonetic column from {'the match key' if dm_from_key else 'the collapsed form'}"
            )

    identical = pairs[0]
    assert score(compare(*identical).agreed) > 0.0, "the strongest case must not score nothing"


def test_the_score_is_a_sum_of_independent_terms_and_nothing_more() -> None:
    """No interaction between terms, which is the one shape a CASE WHEN cannot express.

    An additive score is the sum over the features that agreed, so the score of two disjoint
    sets of agreements is the sum of their scores. A term whose weight depended on which other
    terms fired would break that, and it is the shape `WHAT_WOULD_BREAK_THE_SQL_SHAPE` says a
    calibration job must not produce.

    Delete this and `score` can grow a bonus for two strong features agreeing together, which
    reads as an improvement and cannot be rendered as a sum of independent CASE WHENs."""
    left = frozenset({Feature.UEN, Feature.COUNTRY})
    right = frozenset({Feature.NAME_EXACT, Feature.POSTCODE})

    assert score(left | right) == pytest.approx(score(left) + score(right))
    assert score(frozenset()) == 0.0
    assert score(left) > 0.0


def test_nothing_on_the_request_path_imports_a_model_or_a_numerical_library() -> None:
    """M14.4.5 read as a constraint on this file rather than as a promise about another one.

    The cascade runs per candidate pair on the request path. A numerical or machine-learning
    import here would be a fitted object loaded at import time and consulted per comparison,
    which is the opposite of the millisecond online cost M14.3.6 asks for, and it is the thing
    M14.4.5 says must not exist.

    Parsed rather than searched for as text, so a comment mentioning one of these names does
    not fail the test and an import written any of the several ways cannot hide from it.

    Delete this and the first convenient `import numpy` arrives with a calibration branch, and
    the request path grows a model nobody meant to deploy."""
    source = Path(inspect.getfile(cascade_module)).read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])

    allowed = {
        "__future__",
        "brain",
        "collections",
        "dataclasses",
        "enum",
        "itertools",
        "re",
        "types",
        "typing",
    }
    assert imported <= allowed, sorted(imported - allowed)
    assert "brain" in imported, "the module stopped importing its own package"


# ------------------------------------------------- free-mail domains, removed (M14.3.7)
def test_a_free_mail_domain_is_dropped_rather_than_given_a_small_weight() -> None:
    """**A low weight still sums, and removal is the only version that cannot be re-weighted.**

    Give a webmail domain a tenth of a real one's weight and eleven records sharing it reach any
    threshold you like, and what has been matched is a mail provider. Dropped before hashing,
    the domain never becomes an identifier, never becomes a comparison, and has no term in the
    additive sum for a calibration job to raise later.

    The check is that the feature is in neither half of the comparison. Absent from `agreed` is
    what a weight of zero would also look like; absent from `disagreed` as well is what says
    there is no term at all.

    Delete this and the list can be turned into a weight, which is the specific mistake M14.3.7
    was written to forbid, and it will look like a tuning change."""
    values = {IdentifierKind.DOMAIN: "gmail.com"}
    kept, dropped = usable_identifiers(values, pepper=PEPPER)

    assert kept == {}
    assert len(dropped) == 1
    assert dropped[0].is_free_mail is True
    assert dropped[0].rule is None

    webmail = observation("Acme Trading", identifiers=dict(kept))
    other = observation("Beta Holdings", record="2", identifiers=dict(kept))
    comparison = compare(webmail, other)

    assert Feature.DOMAIN not in comparison.agreed
    assert Feature.DOMAIN not in comparison.disagreed
    assert score(comparison.agreed) == pytest.approx(score(comparison.agreed - {Feature.DOMAIN}))


def test_a_company_domain_is_still_a_join_key_and_so_is_an_address_at_a_webmail_one() -> None:
    """The positive half, twice, because the blocklist has two ways to be too keen.

    A domain a company controls is exactly the identifier stage one merges on, and a list that
    dropped it would leave the estate with no domain identifiers at all. And an email address at
    a free-mail domain is kept on purpose: the whole address identifies one person, which is a
    legitimate join key for a person entity, where the domain part of it identifies a provider.

    Delete this and the free-mail list can be applied to the email kind or grown until it
    catches real company domains, and the failure is a merge that silently never happens."""
    kept, dropped = usable_identifiers(
        {IdentifierKind.DOMAIN: "www.Acme.Example.", IdentifierKind.EMAIL: "wei.ling@gmail.com"},
        pepper=PEPPER,
    )

    assert dropped == ()
    assert set(kept) == {IdentifierKind.DOMAIN, IdentifierKind.EMAIL}
    assert all(len(digest) == 64 for digest in kept.values())
    assert domain_key("www.Acme.Example.") == "acme.example"


def test_the_shared_mailbox_rule_is_the_one_guardrails_holds_and_not_a_second_copy() -> None:
    """One shared-mailbox rule in the repository, and this is the check that there is one.

    `guardrails.blocked` runs first and covers shared mailboxes, placeholders, punctuation and
    held-down keys. The free-mail domain list is a different list that `guardrails` does not
    hold. The identity comparison on the reason string is what says the refusal came from
    `guardrails.BLOCK_REASONS` rather than from a sentence written here that agrees today.

    The refusal also carries no value, which is the same rule one module along.

    Delete this and a second blocklist grows here, the two disagree, and the disagreement is
    invisible until a role address gets through one of them."""
    kept, dropped = usable_identifiers(
        {IdentifierKind.EMAIL: f"info@{SECRET}.example"}, pepper=PEPPER
    )

    assert kept == {}
    assert len(dropped) == 1
    assert dropped[0].rule is BlockRule.SHARED_MAILBOX
    assert dropped[0].reason is BLOCK_REASONS[BlockRule.SHARED_MAILBOX]
    assert dropped[0].is_free_mail is False
    assert SECRET not in dropped[0].reason
    assert SECRET not in repr(dropped[0])
    assert {one.name for one in dataclass_fields(dropped[0].__class__)} == {"kind", "rule"}


def test_the_free_mail_list_is_generic_providers_and_never_a_client_domain() -> None:
    """`guardrails.THE_BLOCKLIST_IS_WRITTEN_AND_NEVER_LEARNT`, applied to the domain half.

    A list that learnt from what it saw would be an enumeration of which of this installation's
    clients use which provider, sitting in a file everybody with repository access can read. So
    every entry is a provider anybody could name from memory, and the check that has teeth is
    that the list is a module constant with no loader: `usable_identifiers` takes a pepper and
    a mapping of values and has no parameter a list could arrive through.

    Delete this and the list grows a loader, and the configuration file becomes a customer
    list."""
    assert "gmail.com" in FREE_MAIL_DOMAINS
    assert f"{SECRET}.example" not in FREE_MAIL_DOMAINS
    assert all(domain == domain_key(domain) for domain in FREE_MAIL_DOMAINS)

    parameters = set(inspect.signature(usable_identifiers).parameters)
    assert parameters == {"values", "pepper"}


def test_an_observation_cannot_carry_a_raw_identifier_value() -> None:
    """The digest bound applied one step before the column that also applies it.

    Everything downstream of `Observation` compares digests, which is what makes the cascade,
    the evidence and the review item structurally incapable of reading an address: there is no
    value in scope at any of those call sites to be interpolated into a reason string. A caller
    that handed over a raw email fails here rather than joining on plaintext.

    Delete this and a raw value reaches a `ReviewItem` through the identifier map, and the
    review queue becomes a surface that shows contact details."""
    with pytest.raises(ResolutionError):
        observation(
            "Acme Trading", identifiers={IdentifierKind.EMAIL: f"wei.ling@{SECRET}.example"}
        )

    with pytest.raises(ResolutionError):
        observation("Acme Trading", identifiers={IdentifierKind.UEN: DIGEST_A.upper()})

    # A digest with something after it, which is the case that fails only because the pattern
    # is anchored. Without it the other two values here would still be refused, on their
    # content rather than on their shape, and dropping the anchors would go unnoticed.
    with pytest.raises(ResolutionError):
        observation("Acme Trading", identifiers={IdentifierKind.UEN: DIGEST_A + "z"})
    with pytest.raises(ResolutionError):
        observation("Acme Trading", identifiers={IdentifierKind.UEN: "z" + DIGEST_A})

    admitted = observation("Acme Trading", identifiers={IdentifierKind.UEN: DIGEST_A})
    assert admitted.identifiers[IdentifierKind.UEN] == DIGEST_A


# ------------------------------------------ Daitch-Mokotoff as a stated subset (M14.3.8)
def test_a_branching_letter_yields_more_than_one_code_which_is_what_soundex_cannot_do() -> None:
    """**Branching is the whole difference between this and Soundex.**

    A C that could be read as K or as TS gets both readings, and two names match when their
    code sets intersect. A coder that returned one code per name would be Soundex with a longer
    table, and the names it would get wrong are exactly the non-English ones M14.3.8 was
    written for.

    The cap is checked against the floor that matters rather than against its own value: what
    has to be true is that more than one code is possible at all.

    Delete this and `MAX_PHONETIC_CODES` can be set to one, and the coder silently stops being
    Daitch-Mokotoff while every test about matching stays green."""
    assert MAX_PHONETIC_CODES > 1

    branched = phonetic_codes("Cohen")
    assert len(branched) > 1

    single = phonetic_codes("Kohen")
    assert len(single) == 1
    assert branched & single
    assert phonetic_agrees("Cohen", "Kohen")


def test_two_transliterations_a_trigram_similarity_misses_share_a_phonetic_code() -> None:
    """The case the leaf names, and the reason the coder is in the module at all.

    Two transliterations of one name share few substrings, so a trigram similarity puts them
    below the lower threshold and the cascade refuses. Their phonetic codes agree. That
    agreement is what a blocking key built on these codes would use to put the pair in front of
    a person at all, which is where the coder earns its keep.

    Delete this and the coder can be replaced by anything that returns a set, including one
    that never agrees, and no test about matching would notice."""
    left, right = "schwartz", "shvarts"

    assert trigram_similarity(left, right) < DECLARED_THRESHOLDS.lower
    assert phonetic_agrees(left, right)
    assert phonetic_codes(left) == phonetic_codes(right)


def test_a_phonetic_agreement_decides_nothing_the_cascade_decides() -> None:
    """It is evidence about spelling, and the module says so rather than implying it.

    Three constructions keep it there and this test names the outcome of all three: a phonetic
    code is a name feature, so it cannot corroborate a name and cannot reach stage two; stage
    three thresholds a similarity and never a code; and the additive score it contributes to
    decides nothing. So a pair whose only agreement is phonetic is refused, exactly like a pair
    with no agreement at all, and the refused pair that agrees phonetically is the one with the
    lower similarity of the two.

    Delete this and a phonetic agreement can be promoted into a corroborator, and every pair of
    names that sound alike in transliteration merges on a weight of a half."""
    assert Feature.NAME_PHONETIC in NAME_FEATURES

    sounds_alike = cascade(observation("Schwartz Group"), observation("Shvarts Group", record="2"))
    unrelated = cascade(observation("Acme Trading"), observation("Acme Holdings", record="2"))

    assert sounds_alike.decision is Decision.NOT_MATCHED
    assert unrelated.decision is Decision.NOT_MATCHED
    assert (
        Feature.NAME_PHONETIC
        in compare(observation("Schwartz Group"), observation("Shvarts Group", record="2")).agreed
    )


def test_a_phonetic_agreement_reaches_a_reviewer_as_the_weakest_thing_on_the_page() -> None:
    """The weight is a stated fraction of an outside constant rather than a decimal of its own.

    A phonetic agreement is a question about transliteration, and the set of companies whose
    names sound alike is very much larger than the set that are the same company. Below
    `guardrails.SUPPORTING_WEIGHT` is where that sits, and `strength_of` is what turns it into
    the sentence a reviewer reads.

    Delete this and the weight can be raised past the band boundary by editing a digit, and a
    reviewer starts being told that two names sounding alike supports their being one thing."""
    assert PHONETIC_WEIGHT < SUPPORTING_WEIGHT
    assert strength_of(PHONETIC_WEIGHT) is Strength.WEAK
    assert DECLARED_WEIGHTS.weight_for(Feature.NAME_PHONETIC) == PHONETIC_WEIGHT


def test_two_sounds_inside_one_table_entry_are_not_collapsed_into_one() -> None:
    """MN is two sixes, and a coder that collapses them has lost a published rule.

    Adjacent identical codes collapse, except across a vowel and except inside one table entry.
    The MN entry exists precisely to say that these two sounds are not one sound, and a
    collapse rule applied to the digits inside an entry would flatten it to a single six, which
    is the sort of difference that changes which names agree and nothing reports.

    Delete this and the collapse rule can be applied one character too widely, and the coder
    quietly becomes a different coder."""
    assert phonetic_codes("MN") == frozenset({"660000"})
    assert phonetic_codes("M") == frozenset({"600000"})
    assert not phonetic_agrees("MN", "M")


def test_two_identical_codes_either_side_of_a_vowel_are_both_kept() -> None:
    """The other half of the collapse rule, and the half a coder is likeliest to lose.

    Adjacent identical codes collapse because they are one sound written twice. A vowel between
    them means they are two sounds, so the collapse does not apply across one, and a coder that
    dropped the vowel exception would give "Mamet" a six where it has two. The vowel is not
    coded itself away from the start of the name and still has to be seen, which is the bit
    that gets optimised away.

    Delete this and the vowel exception can go, every name with a doubled consonant around a
    vowel is coded differently, and the pairs that stop agreeing are exactly the transliterated
    ones the coder is here for."""
    assert phonetic_codes("Mamet") == frozenset({"663000"})
    assert phonetic_codes("Mmet") == frozenset({"630000"})
    assert not phonetic_agrees("Mamet", "Mmet")


def test_a_code_is_six_digits_because_that_is_the_published_length() -> None:
    """A code of another length compares against no other implementation of the scheme.

    Six is the published figure, and it is asserted as a literal here on purpose: the point of
    a published length is agreeing with somebody outside this repository, so the anchor has to
    be outside it too. Padded on the right and truncated on the right, so a short name and a
    long one are both six digits.

    Delete this and the length can change, and every code already materialised in a column
    stops joining to the codes the running system computes."""
    assert DM_CODE_LENGTH == 6

    for name in ("M", "Schwartz", "Kandang Kerbau Holdings Pte Ltd"):
        codes = phonetic_codes(name)
        assert codes
        for code in codes:
            assert len(code) == DM_CODE_LENGTH
            assert code.isdigit()


def test_a_name_with_no_letters_in_it_has_no_code_rather_than_an_empty_agreement() -> None:
    """The only honest answer, and the one that stops every digits-only field joining.

    An empty set turns into "no agreement" rather than "agreement on nothing". A coder that
    returned a padded run of zeroes for a name with no letters would make every such record
    agree with every other, which is the failure `normalise` refuses at the other end.

    Delete this and two records whose name fields hold a phone number agree phonetically."""
    assert phonetic_codes("123 456") == frozenset()
    assert not phonetic_agrees("123 456", "789 012")
    assert not phonetic_agrees("123 456", "Acme Trading")


# -------------------------------------------------------------- the tables, and the gaps
def test_the_gap_detector_reports_a_confidence_that_inverts_the_order_of_the_stages() -> None:
    """**The check the detector's own docstring calls the one worth having, made to fire.**

    It read a module constant until this test was written, so nothing could hand it a table
    that disagrees, and a detector that returns nothing on a healthy tree returns nothing
    whether or not it is still doing anything. That is the defect `guardrails.guardrail_gaps`
    records finding in itself, one package along.

    Two ways round: a stage-two link believed less than a stage-three one inverts the stages,
    and a similarity link believed no more than the threshold below which the cascade refuses
    to make one says less than the refusal does.

    Delete this and the fourth check can be deleted, and the confidence table can say the
    opposite of the truth to every reviewer who reads it."""
    assert cascade_gaps() == ()

    inverted = {
        Stage.HARD_IDENTIFIER: 1.0,
        Stage.CORROBORATED_NAME: 0.50,
        Stage.SIMILARITY: 0.75,
    }
    assert any("inverts" in gap for gap in cascade_gaps(confidence=inverted))

    below_the_refusal = {
        Stage.HARD_IDENTIFIER: 1.0,
        Stage.CORROBORATED_NAME: 0.90,
        Stage.SIMILARITY: DECLARED_THRESHOLDS.lower,
    }
    assert cascade_gaps(confidence=below_the_refusal) != ()


def test_the_gap_detector_reports_a_feature_with_no_sql_predicate() -> None:
    """A feature the query cannot compare is scored at nothing online and at its weight offline.

    That is the two halves disagreeing again, one feature at a time and without the arithmetic
    looking wrong on either side. The predicate table is a parameter, which is the only way a
    test can hand the detector one that disagrees.

    The weight half of the same check is unreachable and that is said here rather than faked:
    `WeightTable` refuses an incomplete table at construction, so no table missing a weight can
    be handed to the detector at all. The constructor refusal is tested above, and the branch
    inside the detector is a second wall behind it.

    Delete this and the predicate map can lose a member on a healthy tree with nothing
    reporting it."""
    fewer_predicates: dict[Feature, str] = {
        feature: SQL_PREDICATES[feature] for feature in Feature if feature is not Feature.COUNTRY
    }
    gaps = cascade_gaps(predicates=fewer_predicates)

    assert any("no SQL predicate" in gap for gap in gaps)
    assert cascade_gaps(predicates=SQL_PREDICATES) == ()

    with pytest.raises(ResolutionError):
        WeightTable(
            version="missing-one",
            weights={one: 1.0 for one in Feature if one is not Feature.COUNTRY},
        )


def test_the_phonetic_table_covers_every_letter_and_the_detector_says_so_when_it_stops() -> None:
    """A missing letter is skipped silently, which changes every code containing it.

    The coder walks the string matching the longest table entry it can, and a letter with no
    entry at all is stepped over rather than coded. That is a coder producing different codes
    for the same names with nothing reporting it, so the detector checks the alphabet.

    The table is a module constant rather than a parameter, so the failing case is reached by
    replacing it for the duration of the test.

    Delete this and a table edit can drop a letter, and every code containing it changes."""
    assert cascade_gaps() == ()

    with pytest.MonkeyPatch.context() as patch:
        without_z = {
            sequence: row for sequence, row in cascade_module._DM_LOOKUP.items() if sequence != "Z"
        }
        patch.setattr(cascade_module, "_DM_LOOKUP", without_z)
        gaps = cascade_gaps()

    assert any("phonetic table has no entry for Z" in gap for gap in gaps)


def test_nothing_the_cascade_produces_can_report_how_many_candidates_there_were() -> None:
    """**DENIED and ABSENT stay indistinguishable, and a count is how that is lost.**

    "Showing three of forty-seven" tells the reader there are forty-four things they may not
    see. This module answers about one pair, so there is nothing here to count, and the check
    is that no type it produces has a field a count could be put on and no function it exposes
    has a parameter a candidate set could arrive through. A caller that needs that shape hands
    its own count to `guardrails.unresolved_for`, whose signature is the disclosure guard.

    Delete this and a `candidates` field appears on `CascadeResult` because it was convenient
    for a log line, and the log line becomes a disclosure."""
    forbidden = ("count", "total", "candidates", "others", "truncated")

    for kind in (CascadeResult, Comparison, Observation):
        for field in dataclass_fields(kind):
            assert not any(word in field.name for word in forbidden), field.name

    for function in (cascade, compare, corroboration_for, evidence_for, score, usable_identifiers):
        for parameter in inspect.signature(function).parameters:
            assert not any(word in parameter for word in forbidden), parameter


def test_a_reviewer_is_shown_the_disagreements_as_well_as_the_agreements() -> None:
    """A reviewer shown only what agreed will merge more than they should.

    Every comparison becomes a line, and a disagreement is carried at weight nought, which
    `guardrails.strength_of` renders as AGAINST. The lines carry a field name and a sentence and
    no value and no number, which is `Evidence`'s rule and not this module's.

    Delete this and `evidence_for` can return the agreements only, and the review queue starts
    presenting one-sided cases that all look like merges."""
    left = observation("Acme Trading", fields={Feature.COUNTRY: "sg", Feature.POSTCODE: "049315"})
    right = observation(
        "Acme Trading", record="2", fields={Feature.COUNTRY: "my", Feature.POSTCODE: "049315"}
    )

    comparison = compare(left, right)
    lines = evidence_for(comparison)
    by_field = {one.field: one for one in lines}

    assert Feature.COUNTRY.value in by_field
    assert by_field[Feature.COUNTRY.value].strength is Strength.AGAINST
    assert by_field[Feature.POSTCODE.value].strength is Strength.SUPPORTING
    assert all(not any(char.isdigit() for char in one.render()) for one in lines)
    assert {one.name for one in dataclass_fields(lines[0].__class__)} == {"field", "weight"}


def test_a_match_carries_a_confidence_and_a_refusal_cannot() -> None:
    """The two have to agree or a caller writes a link out of something that was not a match.

    `canonical.Link` requires a confidence, so a match with none is a link with nothing to put
    in the column, and a refusal carrying one is a number a caller will write into a link
    because it was there.

    Delete this and a review item can carry a confidence, and the first caller to read the
    field without reading the decision merges everything in the band."""
    with pytest.raises(ResolutionError):
        CascadeResult(
            decision=Decision.TO_REVIEW,
            stage=Stage.HUMAN_REVIEW,
            left=SourceRef(source="freshdesk", entity="company", source_id="1"),
            right=SourceRef(source="xero", entity="company", source_id="2"),
            evidence=(),
            reason="a review with a number on it",
            confidence=0.9,
        )

    with pytest.raises(ResolutionError):
        CascadeResult(
            decision=Decision.MATCHED,
            stage=Stage.SIMILARITY,
            left=SourceRef(source="freshdesk", entity="company", source_id="1"),
            right=SourceRef(source="xero", entity="company", source_id="2"),
            evidence=(),
            reason="a match with nothing to write",
        )

    queued = cascade(observation("Peters"), observation("Peterson", record="2"))
    assert queued.decision is Decision.TO_REVIEW
    assert queued.confidence is None

    merged = cascade(
        observation("Acme Trading", identifiers={IdentifierKind.UEN: DIGEST_A}),
        observation("Acme Trading", record="2", identifiers={IdentifierKind.UEN: DIGEST_A}),
    )
    assert merged.decision is Decision.MATCHED
    assert merged.confidence is not None


def test_the_cascade_is_not_called_by_anything_in_the_running_system() -> None:
    """Said in a constant so that claiming otherwise means deleting it.

    Nothing outside `brain.resolution` imports this module: no route reaches it, no worker runs
    it, and the columns the rendered SQL names exist in no migration. Everything here is
    callable and nothing calls it.

    Imports are parsed rather than searched for, because half the package is quoted by name in
    other modules' prose. The one module outside the package that does import from
    `brain.resolution` is `brain.tables.resolution`, which reads widths and grammars off
    `canonical` to build columns with, and that is a declaration rather than a call.

    Delete this and the gap stops being written down, and the next reader assumes a module this
    carefully argued is in the request path."""
    assert cascade_module.NOTHING_HERE_IS_CALLED_BY_THE_RUNNING_SYSTEM

    package = Path(inspect.getfile(cascade_module)).parent
    root = package.parent
    importers: list[str] = []
    for path in root.rglob("*.py"):
        if path.parent == package:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            named: set[str] = set()
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                named.add(node.module)
            elif isinstance(node, ast.Import):
                named.update(alias.name for alias in node.names)
            if "brain.resolution.cascade" in named:
                importers.append(str(path.relative_to(root)))

    assert importers == []
