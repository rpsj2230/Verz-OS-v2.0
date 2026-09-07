"""Four stages in a fixed order, and why the order is the whole of the safety argument.

`brain.resolution.normalise` decides what two names have to look like before they count as
equal. `brain.resolution.guardrails` decides which values may be join keys at all and what a
reviewer may be shown. This is the thing between them: given two source records, does the
system say they are one entity, does it say they are not, or does it hand the question to a
person.

**A hard identifier is an identity and not a score, and stage one either matches or it does
not.** Two records carrying the same UEN are the same registered company; that is not a
probability and nothing weaker may overturn it. So stage one returns before any weight is
summed, and the additive scorer below is never reached on that path. See
`A_HARD_IDENTIFIER_IS_AN_IDENTITY_AND_NOT_A_SCORE`. The same construction settles the harder
half: when the strongest hard identifier both records carry *disagrees*, the cascade refuses
rather than falling through to the name. That is `guardrails.A_TIE_AT_THE_TOP_IS_NOT_BROKEN_BY_
A_WEAKER_IDENTIFIER` applied to a pair instead of to a set of claims, and it is the reason
`priority_of` is imported rather than a second ordering being written here.

**Stage two cannot be reached by a name alone, and the guard is a type rather than a check.**
M14.3.2 asks for corroboration from a second field, and the version of that which decays is an
`if` somebody loosens on a Friday. `CorroboratedName` refuses construction when the
corroborating feature is itself a name feature, so "the names agree, and the names agree" is
not a value that exists. See `STAGE_TWO_CANNOT_BE_REACHED_BY_A_NAME_ALONE`.

**A stage may not re-admit what the stage above it refused, and stage three did.** Two equal
keys have a trigram similarity of one, which is above any upper threshold, so a pair whose
names agreed and which stage two refused for want of a second field was merged one line later
by stage three, at a lower confidence and with no corroboration at all. Stage two's guard was
therefore decorative for as long as it existed: it never refused anything, it only decided
which confidence a name agreement was recorded with. The repair is to say what a similarity is:
a measurement between two keys that differ. Where the keys are equal there is nothing to
threshold, stage three has no opinion, and the pair falls to the person the band exists for.
See `A_SIMILARITY_IS_A_MEASUREMENT_AND_EQUALITY_IS_NOT_ONE`.

**Two thresholds make three outcomes, and the third one is a person.** `upper` admits,
`lower` refuses, and everything between them is M14.3.4. `Thresholds` refuses `upper <= lower`
and refuses a band narrower than `MIN_REVIEW_BAND`, because collapsing the two figures onto
each other deletes human review from the cascade and is a one-character edit that no test
about matching would notice. See `THE_BAND_BETWEEN_THE_THRESHOLDS_IS_THE_FOURTH_STAGE`.

**A free-mail domain contributes nothing, rather than a little (M14.3.7).** A low weight still
sums: enough small contributions reach any threshold, and the specific failure is that two
unrelated people who both use one webmail provider become one company. So a free-mail domain
is removed before hashing and never becomes a comparison at all, which means there is no term
in the sum for anybody to re-weight. See `A_FREE_MAIL_DOMAIN_CONTRIBUTES_NOTHING_RATHER_THAN_A_
LITTLE`. `guardrails.blocked` runs first and covers shared mailboxes, placeholders,
punctuation and held-down keys; the free-mail *domain* list is a different list that
`guardrails` does not hold, and where it should eventually live is said in
`THE_FREE_MAIL_LIST_BELONGS_BESIDE_THE_OTHER_BLOCKLISTS`.

**The score is additive over comparisons so that it can be one SQL expression (M14.3.6).**
Every term is a weight times a boolean, the boolean is a comparison between two columns or a
conjunction of them, and the total is a sum. `sql_score_expression` renders exactly that over
the same feature vocabulary the Python scorer sums, with every weight bound as a parameter
rather than written into the text, so the two cannot drift into two different scoring rules and
the statement does not change when a calibration does. `brain.resolution.query` is what binds
them and wraps the expression into something executable, because a statement needs a table name
and nothing here knows one. The conjunctions are what make that true rather than nearly true:
the name
features are mutually exclusive in `compare`, and three unguarded equalities in SQL would score
a pair of identical names three times over, which is the double-count this module refuses one
paragraph below and would have shipped in the rendered half. Nothing in this module imports
a numerical or a machine-learning library, and there is no model object, no fitted state and
no training-time artefact anywhere on the request path, which is M14.4.5 read as a constraint
on this file rather than as a promise about another one. What would break the shape is written
down rather than implied: see `WHAT_WOULD_BREAK_THE_SQL_SHAPE`.

**The weights are declared and nothing has calibrated them (M14.3.5).** The leaf says
"exported from offline calibration", the calibration is M14.4 and it does not exist, so the
honest thing is a table that says so in its own type. `WeightTable.calibrated` is a property
derived from `calibration_ref`, not a boolean anybody can set, so claiming calibration means
naming the export that produced it. See `THE_WEIGHTS_ARE_DECLARED_AND_NOTHING_HAS_CALIBRATED_
THEM`. Each figure is written as one of `guardrails`' band constants rather than as a number
of its own, so a weight cannot quietly drift to a value that renders as a different strength.

**Daitch-Mokotoff is implemented as a stated subset, not as Soundex wearing its name
(M14.3.8).** Which coding rules are here and which are not is enumerated in
`DAITCH_MOKOTOFF_RULES_IMPLEMENTED` and `DAITCH_MOKOTOFF_RULES_NOT_IMPLEMENTED`, because a
phonetic coder that claims to be D-M and is not is worse than one that says what it is: the
false claim is believed, and the names it gets wrong are exactly the non-English ones the leaf
was written for. It is weighted below `guardrails.SUPPORTING_WEIGHT`, so
`guardrails.strength_of` renders it as WEAK, because a phonetic agreement is evidence about
how two strings are spelled and not about whether two companies are one company. Inside this
module it decides nothing whatever, which is said in
`A_PHONETIC_MATCH_IS_EVIDENCE_ABOUT_SPELLING_AND_NOT_ABOUT_IDENTITY` rather than left for a
reader to infer from three separate constructions.

**No count of candidates leaves this module.** `cascade` answers about one pair, and there is
no function here that takes a set of candidates and reports how many survived. A caller that
needs that shape hands its own count to `guardrails.unresolved_for`, whose signature is the
disclosure guard for it. A stage-four result becomes a `guardrails.ReviewItem` and reaches a
person only through `guardrails.review_queue`, which is where the reach filter lives; nothing
here filters by reach, and nothing here should, for the reason `canonical` gives about having
one implementation of a rule.

Rejected: scoring first and using the stages to explain the score afterwards. That is the
natural shape, it is one query instead of four branches, and it loses the only property that
matters here, which is that a hard identifier cannot be outvoted by a pile of weak agreements.
Under an additive model, a UEN mismatch plus six agreeing weak fields is a match.

Rejected: a single threshold with review above it. One threshold gives two outcomes, and the
band M14.3.4 asks for is the difference between "we merged it" and "somebody looked at it".

Scope: domain logic. Nothing here opens a connection, reads a clock, touches a table or
imports a numerical library. The pepper, the thresholds and the weight table are parameters
for the reason `canonical` takes its timestamps as parameters.

Task ids: M14.3.1, M14.3.2, M14.3.3, M14.3.4, M14.3.5, M14.3.6, M14.3.7, M14.3.8
"""

from __future__ import annotations

import enum
import itertools
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from brain.resolution.canonical import (
    IdentifierKind,
    ResolutionError,
    SourceRef,
    identifier_hash,
)
from brain.resolution.guardrails import (
    BLOCK_REASONS,
    DECISIVE_WEIGHT,
    STRONG_WEIGHT,
    SUPPORTING_WEIGHT,
    BlockRule,
    Evidence,
    ReviewItem,
    blocked,
    priority_of,
)
from brain.resolution.normalise import NormalisedName, accent_fold

# ------------------------------------------------------------------ written-down reasons
#: Why stage one returns before anything is scored.
A_HARD_IDENTIFIER_IS_AN_IDENTITY_AND_NOT_A_SCORE = (
    "Two records carrying one UEN are one registered company, and that is a fact about a "
    "register rather than a probability about a string. So stage one returns its answer "
    "before the additive scorer is reached, and there is no path on which a sum of weak "
    "agreements is compared against it. The rejected design scores everything and lets the "
    "hard identifier be the heaviest term, which reads as equivalent and is not: under a sum, "
    "a UEN that disagrees plus six weak fields that agree is a match, and the merge that "
    "results carries a confident-sounding total nobody goes back and checks. The same "
    "argument is why a hard identifier that disagrees refuses rather than falling through to "
    "the name, which is guardrails.A_TIE_AT_THE_TOP_IS_NOT_BROKEN_BY_A_WEAKER_IDENTIFIER "
    "applied to a pair rather than to a set of claims."
)

#: Why corroboration is a type rather than a condition.
STAGE_TWO_CANNOT_BE_REACHED_BY_A_NAME_ALONE = (
    "M14.3.2 asks for a second field, and the version of that rule which decays is an if "
    "somebody loosens when the review queue gets long. CorroboratedName carries the name "
    "feature and the corroborating feature in two separate slots and refuses to be built when "
    "the corroborating one is itself a name feature, so 'the names agree, and the names also "
    "agree' is not a value this module can hold. A caller wanting to promote on a name alone "
    "would have to delete a check in a frozen dataclass rather than widen a condition, which "
    "is a visible change in review. The reason the rule exists at all is normalise's: suffix "
    "stripping makes 'Ace Co' and 'Ace' one key, and whether that is right depends on facts "
    "no normaliser has."
)

#: Why stage three has nothing to say about two names that are simply equal.
A_SIMILARITY_IS_A_MEASUREMENT_AND_EQUALITY_IS_NOT_ONE = (
    "Two equal keys have a trigram similarity of one, and one is above every upper threshold "
    "the band guard admits. So the first version of this cascade refused a name agreement at "
    "stage two for want of a second field and then merged the same pair at stage three, one "
    "branch later, on the same name and at a lower confidence. Stage two never refused "
    "anything: it chose which confidence a name agreement was recorded with, and M14.3.2's "
    "guard was decorative while reading as the strictest thing in the module. The repair is "
    "not a further threshold. It is that a similarity is a measurement of how two different "
    "strings overlap, equality is not a measurement, and the case normalise warns about is "
    "exactly this one, where suffix stripping made 'Ace Co' and 'Ace' one key. So a pair whose "
    "keys are equal and which nothing corroborates goes to the person the band exists for, and "
    "stage three thresholds only pairs whose keys differ. A pair of long keys overlapping by "
    "more than the upper threshold is a different fact from a normaliser having collapsed two "
    "names together, and it is the one M14.3.3 admits."
)

#: Why the two thresholds may never be one threshold.
THE_BAND_BETWEEN_THE_THRESHOLDS_IS_THE_FOURTH_STAGE = (
    "Two thresholds define three outcomes: admit, refuse, and ask a person. Setting upper "
    "equal to lower deletes the third one, leaves a cascade that never asks anybody anything, "
    "and passes every test about matching and every test about refusing, because both of "
    "those still work. It is a one-character edit. So Thresholds refuses upper <= lower, and "
    "refuses a band narrower than MIN_REVIEW_BAND as well, because a band of one part in a "
    "thousand is arithmetically non-empty and contains no similarity any real pair of keys "
    "can produce."
)

#: Why a free-mail domain is removed rather than weighted low.
A_FREE_MAIL_DOMAIN_CONTRIBUTES_NOTHING_RATHER_THAN_A_LITTLE = (
    "A low weight still sums. Give a shared webmail domain a tenth of the weight of a real "
    "one and eleven records that share it reach any threshold you like, and what has been "
    "matched is a mail provider rather than a company. The failure is not hypothetical in "
    "shape: it is guardrails' shared-mailbox argument with the domain half instead of the "
    "local half. So a free-mail domain is dropped before the value is hashed, never becomes "
    "an Observation identifier, and therefore has no term in the additive score for anybody "
    "to re-weight later. Removal is expressible in SQL as an absent row; a weight of zero "
    "would be a term that a calibration job could raise."
)

#: Where the free-mail list ought to live, and why it is here instead.
THE_FREE_MAIL_LIST_BELONGS_BESIDE_THE_OTHER_BLOCKLISTS = (
    "guardrails holds the blocklists: shared mailbox local parts, placeholder values, and the "
    "two shapes a list cannot enumerate. It holds no domain list, so the free-mail domains "
    "M14.3.7 asks for are declared here, and guardrails.blocked is called first rather than "
    "reimplemented, so there is one shared-mailbox rule and not two. The list obeys "
    "guardrails.THE_BLOCKLIST_IS_WRITTEN_AND_NEVER_LEARNT: generic providers anybody could "
    "name from memory, never a domain observed in an installation's data, because a learnt "
    "list is a readable enumeration of which of our clients use which provider. When somebody "
    "owns guardrails again this belongs next to SHARED_MAILBOX_LOCAL_PARTS."
)

#: Why the weights are honest about not being measured.
THE_WEIGHTS_ARE_DECLARED_AND_NOTHING_HAS_CALIBRATED_THEM = (
    "M14.3.5 says the weight table is exported from offline calibration. The calibration is "
    "M14.4, it is not built, and there is no export to read, so every figure here was chosen "
    "by an author rather than fitted to data. Saying that in a comment does not travel; "
    "WeightTable.calibrated is therefore a property derived from calibration_ref, so there is "
    "no boolean to set and claiming calibration means naming the export that produced it. The "
    "figures themselves are guardrails' band constants rather than numbers of their own, so a "
    "weight cannot drift to a value that renders to a reviewer as a different strength than "
    "the author intended. Nothing in this repository has measured any of them."
)

#: Why the score is a sum of independent terms and nothing more.
THE_SCORE_IS_ADDITIVE_SO_IT_CAN_BE_ONE_SQL_EXPRESSION = (
    "Every term is one weight times one boolean, the boolean is a comparison between two "
    "columns or a conjunction of such comparisons, and the total is a sum. That is a CASE WHEN "
    "per feature inside one SELECT, which is what M14.3.6 means by millisecond online cost: no "
    "round trip per candidate, no per-pair Python, and no object that had to be trained. "
    "sql_score_expression renders that expression over the same feature vocabulary score() "
    "sums, and binds each weight as a parameter rather than rendering it, so the online query "
    "and the offline reasoning cannot become two different scoring rules and a re-calibration "
    "is a different argument list rather than a different statement. A conjunction rather than "
    "a bare equality on three of the name terms, "
    "because compare() reports at most one name feature for a pair and three unguarded "
    "equalities report three: two identical names satisfy name_collapsed, name_key and the "
    "similarity threshold at once, so the rendered expression would have scored one fact three "
    "times while the Python scorer scored it once. That divergence was in this file and it is "
    "the exact failure the paragraph about double counting warns about, which is why the "
    "agreement between the two halves is now asserted by evaluating the rendered expression "
    "rather than by reading it."
)

#: What would have to change if the score could not be evaluated in SQL.
WHAT_WOULD_BREAK_THE_SQL_SHAPE = (
    "Three things, and each has an answer that keeps the shape. A term whose value depends on "
    "both rows in a way no operator expresses would need a function, and the trigram term "
    "avoids that because pg_trgm's similarity is an operator with an index behind it. A term "
    "computed by Python at query time would break it outright, which is what the phonetic "
    "term would do if the code were computed per comparison: it is instead materialised at "
    "write time into a column, so the query does a set overlap. And a term whose weight "
    "depends on the other terms, an interaction rather than a sum, cannot be a CASE WHEN at "
    "all and is the one shape a calibration job must not produce. Note what is not verified "
    "here: no migration in this repository creates any of the columns the rendered SQL names, "
    "no extension is installed, and nothing has checked which PostgreSQL version a deployment "
    "runs, so the rendered expression is a shape and not a query anybody has executed."
)

#: Why a phonetic agreement is worth little.
A_PHONETIC_MATCH_IS_EVIDENCE_ABOUT_SPELLING_AND_NOT_ABOUT_IDENTITY = (
    "A phonetic coder answers 'could these two strings be two spellings of one sound'. That "
    "is a question about transliteration, and the set of companies whose names sound alike is "
    "very much larger than the set that are the same company. So the weight sits below "
    "guardrails.SUPPORTING_WEIGHT, which makes guardrails.strength_of render it as WEAK. "
    "Inside the cascade it decides nothing at all, and that is worth stating rather than "
    "implying: NAME_PHONETIC is a name feature, so it cannot corroborate a name and cannot "
    "reach stage two; stage three thresholds a trigram similarity and never a code; and the "
    "additive score it contributes to decides nothing here by construction. The place a "
    "phonetic code earns its keep is candidate generation, where a shared code puts a pair in "
    "front of the cascade that a trigram index would never have offered, which is the "
    "non-English case M14.3.8 names. This module answers about a pair it was handed and "
    "generates no candidates, so that half is not here and the claim is not made for it."
)

#: The gap this module does not close, kept as a constant so it has to be deleted.
NOTHING_HERE_IS_CALLED_BY_THE_RUNNING_SYSTEM = (
    "brain.resolution has no functional caller. Nothing in brain.gate, brain.tools or "
    "brain.channels imports this package, no route reaches it, no worker runs it, and there "
    "is no resolver service that would call cascade() over a candidate set. The columns "
    "sql_score_expression names do not exist in any migration here, the weight table is not "
    "read from anywhere, and no link row has ever been written by this code. Everything here "
    "is callable and nothing calls it, which is the same sentence normalise's "
    "NOTHING_HERE_IS_INSTALLED_IN_POSTGRES says about its own half, and it is said in a "
    "constant so that a later claim to the contrary requires deleting it."
)


# ------------------------------------------------------------------------ the vocabulary
class Feature(enum.StrEnum):
    """One comparison the cascade can make between two records.

    A closed vocabulary, for the reason `canonical.IdentifierKind` is one: every member has a
    weight and a SQL predicate, and `cascade_gaps` reports the set when either map stops being
    exhaustive. A feature nobody weighted would contribute nothing to the sum and would look
    exactly like a feature that never agreed.

    Every value is a machine name in `guardrails.Evidence`'s grammar, because a feature name
    is the string a reviewer is shown and that grammar is what stops a company name being
    pasted into the slot.
    """

    #: The five identifier kinds, compared as digests.
    UEN = "uen"
    TAX_ID = "tax_id"
    DOMAIN = "domain"
    PHONE = "phone"
    EMAIL = "email"
    #: The collapsed names agree: the same name including its legal form.
    NAME_EXACT = "name_exact"
    #: Only the stripped keys agree: the same name once the legal forms came off.
    NAME_STRIPPED = "name_stripped"
    #: The trigram similarity of the two keys is at or above the upper threshold.
    NAME_TRIGRAM = "name_trigram"
    #: The Daitch-Mokotoff code sets intersect.
    NAME_PHONETIC = "name_phonetic"
    #: Fields that are neither a name nor an identifier, compared as opaque tokens.
    COUNTRY = "country"
    POSTCODE = "postcode"


#: The features that are statements about the name, and therefore cannot corroborate it.
#:
#: Written out rather than derived from the "name_" prefix, for the reason
#: `guardrails.ROUTES_TO_REVIEW` is written out: derived, the set and the rule would agree by
#: construction, and adding a name feature spelled some other way would silently become a
#: legitimate corroborator for the name.
NAME_FEATURES: frozenset[Feature] = frozenset(
    {Feature.NAME_EXACT, Feature.NAME_STRIPPED, Feature.NAME_TRIGRAM, Feature.NAME_PHONETIC}
)

#: Features carried on `Observation.fields` rather than derived from a name or an identifier.
FIELD_FEATURES: frozenset[Feature] = frozenset({Feature.COUNTRY, Feature.POSTCODE})

#: The name features that are an equality rather than a measurement.
#:
#: `NAME_EXACT` is the collapsed forms being the same string and `NAME_STRIPPED` is the match
#: keys being the same string. Both are stage two's evidence, and stage two asks for a second
#: field beside them. `NAME_TRIGRAM` is not here: it is a measured overlap between two keys that
#: differ, which is stage three's evidence and is thresholded rather than corroborated.
#:
#: Written out rather than derived as "the name features that are not the trigram", for the
#: reason `NAME_FEATURES` itself is written out.
NAME_EQUALITY_FEATURES: frozenset[Feature] = frozenset({Feature.NAME_EXACT, Feature.NAME_STRIPPED})

#: The identifier kinds stage one may decide on, strongest first (M14.3.1).
#:
#: The leaf's four: UEN, tax id, verified domain, verified phone. EMAIL is deliberately absent,
#: and the absence is checkable rather than a matter of taste: every kind here outranks EMAIL
#: in `guardrails.IDENTIFIER_PRIORITY`, which says an address identifies a person at best and a
#: shared mailbox identifies nobody. A test holds this tuple against that order rather than
#: against itself.
HARD_IDENTIFIERS: tuple[IdentifierKind, ...] = (
    IdentifierKind.UEN,
    IdentifierKind.TAX_ID,
    IdentifierKind.DOMAIN,
    IdentifierKind.PHONE,
)

#: The hard identifiers that count only when the source says it verified them.
#:
#: The leaf says "verified domain, verified phone" and the word is load-bearing. A domain
#: scraped off an email signature and a domain a source confirmed the customer controls are
#: different facts, and stage one merges on the second only. A UEN or a tax id needs no such
#: flag because it came from a register in the first place. An unverified domain or phone is
#: not discarded: it falls through and is scored, which is a demotion rather than a refusal.
VERIFICATION_REQUIRED: frozenset[IdentifierKind] = frozenset(
    {IdentifierKind.DOMAIN, IdentifierKind.PHONE}
)


class Stage(enum.IntEnum):
    """Which stage of the cascade produced an answer.

    An `IntEnum` and ordered, because "at least as strong as stage two" is a comparison and
    the ordering is the meaning of the cascade: a lower number is a stronger kind of evidence,
    and nothing at a higher number may overturn something decided at a lower one. That is the
    same reason `guardrails.Strength` is ordered, applied to the evidence's kind rather than to
    its size.
    """

    #: A hard identifier agreed. An identity, not a score.
    HARD_IDENTIFIER = 1
    #: The normalised name agreed and a second, non-name field agreed with it.
    CORROBORATED_NAME = 2
    #: Trigram similarity, against two thresholds.
    SIMILARITY = 3
    #: The band between the thresholds. A person decides.
    HUMAN_REVIEW = 4


class Decision(enum.StrEnum):
    """What the cascade concluded about one pair.

    Three members because the thresholds make three outcomes. `TO_REVIEW` is not a kind of
    refusal and is deliberately not spelled as one: a refusal is an answer and a review is a
    question, and a caller that treated them alike would either merge nothing or queue
    everything.
    """

    MATCHED = "matched"
    NOT_MATCHED = "not matched"
    TO_REVIEW = "to review"


# ------------------------------------------------------- the weight table (M14.3.5)
@dataclass(frozen=True)
class WeightTable:
    """A set of match weights, its version, and where it came from if it came from anywhere.

    **`calibrated` is a property and not a field.** There is no boolean to set to True: the
    only way this table can say it was calibrated is for somebody to name the export that
    produced it, and M14.4 is the leaf that would produce one. That is the construction
    `normalise.UenCheck.check_character_verified` uses for the same purpose, adapted so that
    the honest claim becomes possible the day the job exists rather than staying impossible
    forever. See `THE_WEIGHTS_ARE_DECLARED_AND_NOTHING_HAS_CALIBRATED_THEM`.

    Weights are log2 Bayes factors, the unit `guardrails.Strength`'s bands are cut in: a
    weight of w multiplies the odds of a match by 2 ** w. Carrying the same unit is what lets
    `Evidence.render` describe a term without a number and without a second scale to convert.
    """

    version: str
    weights: Mapping[Feature, float]
    #: The offline export this table was read from. Empty means nobody measured any of it.
    calibration_ref: str = ""

    def __post_init__(self) -> None:
        if not self.version.strip():
            msg = (
                "a weight table with no version cannot be told apart from another one, and a "
                "link scored under one set of weights is not comparable with a link scored "
                "under another"
            )
            raise ResolutionError(msg)
        missing = sorted(one.value for one in Feature if one not in self.weights)
        if missing:
            msg = (
                f"no weight for {', '.join(missing)}; an unweighted feature contributes "
                "nothing to the sum and is indistinguishable from one that never agreed"
            )
            raise ResolutionError(msg)

    @property
    def calibrated(self) -> bool:
        """Whether a calibration job produced these figures. False for everything here."""
        return bool(self.calibration_ref)

    def weight_for(self, feature: Feature) -> float:
        """The weight of one feature. Refuses an unweighted one rather than defaulting.

        A default of zero would make a forgotten feature look like a feature that agreed and
        told us nothing, which is the failure `guardrails.priority_of` refuses a default for.
        """
        if feature not in self.weights:
            msg = f"{feature.value!r} has no weight in table {self.version!r}"
            raise ResolutionError(msg)
        return self.weights[feature]


#: How much a phonetic agreement is worth (M14.3.8).
#:
#: Half of `guardrails.SUPPORTING_WEIGHT`, which is what makes `guardrails.strength_of` render
#: it as WEAK rather than as support. Written as the fraction of an outside constant rather
#: than as a number of its own, so raising it past the band boundary means editing the
#: relationship and not a digit. See
#: `A_PHONETIC_MATCH_IS_EVIDENCE_ABOUT_SPELLING_AND_NOT_ABOUT_IDENTITY`.
PHONETIC_WEIGHT: Final = SUPPORTING_WEIGHT / 2.0

#: The weights, declared and uncalibrated.
#:
#: Every figure is one of `guardrails`' band constants or a stated fraction of one, so each is
#: anchored to the sentence a reviewer will read rather than to an author's taste in decimals:
#:
#: - UEN and TAX_ID are DECISIVE, which is what a register-issued number agreeing means. UEN
#:   never actually reaches the sum, because stage one returns first; the weight is here so a
#:   review item carrying a UEN agreement renders it correctly.
#: - DOMAIN and NAME_EXACT are STRONG. A domain a company controls and a full name including
#:   its legal form are each close to identifying, and neither is a register.
#: - PHONE, EMAIL, NAME_STRIPPED, NAME_TRIGRAM, COUNTRY and POSTCODE are SUPPORTING. They are
#:   not equally strong in truth, and saying so with different invented decimals would be a
#:   claim to a precision nobody here has; one band is the honest resolution until M14.4.
#: - NAME_PHONETIC is below SUPPORTING, on purpose. See `PHONETIC_WEIGHT`.
DECLARED_WEIGHTS: Final = WeightTable(
    version="declared-2026-09-07",
    weights=MappingProxyType(
        {
            Feature.UEN: DECISIVE_WEIGHT,
            Feature.TAX_ID: DECISIVE_WEIGHT,
            Feature.DOMAIN: STRONG_WEIGHT,
            Feature.NAME_EXACT: STRONG_WEIGHT,
            Feature.PHONE: SUPPORTING_WEIGHT,
            Feature.EMAIL: SUPPORTING_WEIGHT,
            Feature.NAME_STRIPPED: SUPPORTING_WEIGHT,
            Feature.NAME_TRIGRAM: SUPPORTING_WEIGHT,
            Feature.COUNTRY: SUPPORTING_WEIGHT,
            Feature.POSTCODE: SUPPORTING_WEIGHT,
            Feature.NAME_PHONETIC: PHONETIC_WEIGHT,
        }
    ),
)


# ------------------------------------------------------- the thresholds (M14.3.3, M14.3.4)
#: The narrowest review band the cascade will accept.
#:
#: One fifth, which is one trigram's share of the smallest trigram set the cascade can ever be
#: given. `normalise.MIN_KEY_CHARS` is the shortest key that reaches stage three, and pg_trgm
#: builds `MIN_KEY_CHARS + 1` trigrams from a word of that length, so one trigram is
#: 1 / (MIN_KEY_CHARS + 1) of it and a band narrower than that cannot contain any similarity
#: two keys of the shortest admissible length can produce. Written as a literal rather than as
#: the quotient, so a test can check the derivation against the figure it comes from instead of
#: recomputing it and comparing the answer with itself, which is how `MIN_KEY_CHARS` itself is
#: written.
MIN_REVIEW_BAND: Final = 0.2


@dataclass(frozen=True)
class Thresholds:
    """The two similarity figures that cut stage three into three outcomes.

    `upper` and `lower` are compared against a trigram similarity, which is a share, so both
    live in nought to one. The band between them is stage four and it is refused when empty:
    see `THE_BAND_BETWEEN_THE_THRESHOLDS_IS_THE_FOURTH_STAGE`.

    Uncalibrated, like the weights. M14.3.5's export would set both, and until it exists these
    two figures are an author's judgement about how similar two names have to look.
    """

    upper: float
    lower: float

    def __post_init__(self) -> None:
        if not 0.0 < self.lower < 1.0:
            msg = (
                f"a lower threshold of {self.lower} is not a similarity; at nought every pair "
                "of records in the estate is in the review band, and at one nothing is"
            )
            raise ResolutionError(msg)
        if not 0.0 < self.upper <= 1.0:
            msg = f"an upper threshold of {self.upper} is not a similarity"
            raise ResolutionError(msg)
        if self.upper <= self.lower:
            msg = (
                f"upper {self.upper} is not above lower {self.lower}; two thresholds that meet "
                "leave two outcomes rather than three, which deletes human review from the "
                "cascade without failing any test about matching or about refusing"
            )
            raise ResolutionError(msg)
        if self.upper - self.lower < MIN_REVIEW_BAND:
            msg = (
                f"a review band of {self.upper - self.lower:.3f} is narrower than "
                f"{MIN_REVIEW_BAND}, which is one trigram's share of the smallest trigram set "
                "the cascade can see; no pair of keys of the shortest admissible length can "
                "produce a similarity inside it, so the band is non-empty in arithmetic and "
                "empty in practice"
            )
            raise ResolutionError(msg)

    def band_holds(self, similarity: float) -> bool:
        """Whether this similarity falls to a person rather than to the cascade."""
        return self.lower <= similarity < self.upper


#: The thresholds in force, declared rather than calibrated.
#:
#: Eighty-five hundredths to admit and sixty hundredths to refuse, leaving a band of a quarter,
#: which is above `MIN_REVIEW_BAND` with room. Neither figure was measured; both are here so
#: the cascade has something to run against, and M14.4 is what would replace them.
DECLARED_THRESHOLDS: Final = Thresholds(upper=0.85, lower=0.60)


#: What goes in `canonical.Link.confidence` for a match at each stage.
#:
#: Declared, not measured, and the figures are held in place by their relations rather than by
#: themselves. Stage one is exactly one because a hard identifier is an identity. Stage two is
#: below one and above stage three, because a corroborated exact name is weaker than a register
#: number and stronger than a similarity. Stage three is above `DECLARED_THRESHOLDS.lower`,
#: because a link the cascade makes automatically has to be believed more than the figure below
#: which it refuses to make one at all. A test asserts those three relations rather than the
#: three numbers.
#:
#: The observed similarity is deliberately *not* used as the confidence at stage three. A
#: trigram similarity measures how two strings overlap; `Link.confidence` is documented as what
#: the cascade believed, which is a probability. Passing one off as the other would put a
#: measured-looking number on a scale nothing has calibrated.
DECLARED_CONFIDENCE: Mapping[Stage, float] = MappingProxyType(
    {
        Stage.HARD_IDENTIFIER: 1.0,
        Stage.CORROBORATED_NAME: 0.90,
        Stage.SIMILARITY: 0.75,
    }
)


# ----------------------------------------------- free-mail domains and usable values (M14.3.7)
#: Webmail providers whose domain identifies a mail provider and never a company.
#:
#: Generic, internationally known providers written from memory, and not one entry came from
#: looking at an installation's data. See `THE_FREE_MAIL_LIST_BELONGS_BESIDE_THE_OTHER_
#: BLOCKLISTS` and, for why a learnt list is the wrong shape,
#: `guardrails.THE_BLOCKLIST_IS_WRITTEN_AND_NEVER_LEARNT`.
#:
#: Deliberately short, and incomplete by design rather than by neglect: a domain that is not
#: here is compared as an ordinary domain, which is a false join waiting to happen, and a
#: domain that is here can never join anything, which is a missed match. The second is the safe
#: direction only for providers that really are shared, so the list holds the ones nobody has
#: to check.
FREE_MAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "aol.com",
        "gmail.com",
        "googlemail.com",
        "hotmail.co.uk",
        "hotmail.com",
        "icloud.com",
        "live.com",
        "mail.com",
        "me.com",
        "msn.com",
        "outlook.com",
        "proton.me",
        "protonmail.com",
        "qq.com",
        "yahoo.com",
        "yahoo.com.sg",
        "yandex.ru",
        "163.com",
        "126.com",
    }
)

#: The sentence a free-mail refusal reaches an operator with.
#:
#: Named after the rule and carrying no value, the way `guardrails.BLOCK_REASONS` entries are,
#: so a refusal that travels into a log carries no domain with it.
FREE_MAIL_REASON: Final = (
    "this domain belongs to a mail provider rather than to a company, so joining on it would "
    "make every customer of that provider one entity; it is dropped rather than weighted "
    "down, because a small weight repeated enough times reaches any threshold"
)


@dataclass(frozen=True)
class Dropped:
    """One identifier value that may not be compared, and the rule that refused it.

    No field for the value and no field for the part of it that matched, which is
    `guardrails.A_BLOCK_REPORT_NAMES_THE_RULE_AND_NEVER_THE_VALUE` applied to a second refusal
    path. `rule` is None for exactly one case, the free-mail domain list, which is the rule
    this module holds and `guardrails.BlockRule` does not have a member for. Two-valued rather
    than a local enumeration duplicating `BlockRule`'s four members, because a second
    enumeration of the same idea is a second place for the two to disagree.
    """

    kind: IdentifierKind
    #: The guardrail that refused it, or None when the free-mail domain list did.
    rule: BlockRule | None

    @property
    def is_free_mail(self) -> bool:
        return self.rule is None

    @property
    def reason(self) -> str:
        return FREE_MAIL_REASON if self.rule is None else BLOCK_REASONS[self.rule]


def domain_key(value: str) -> str:
    """One spelling for one domain: lower case, no leading www, no trailing dot.

    `normalise.collapse` is deliberately not used, and the reason is specific rather than
    stylistic: collapse turns every punctuation mark into a token boundary, so "gmail.com"
    would become "gmail com" and would no longer compare against a list of domains. Domains are
    the one field in this module where a dot is part of the value rather than a separator.
    """
    text = value.strip().casefold().rstrip(".")
    prefix = "www."
    return text[len(prefix) :] if text.startswith(prefix) else text


def usable_identifiers(
    values: Mapping[IdentifierKind, str], *, pepper: str
) -> tuple[Mapping[IdentifierKind, str], tuple[Dropped, ...]]:
    """Hash the identifier values that may be joined on, and say what was dropped (M14.3.7).

    **This is the only function in the module that sees an identifier value**, and what it
    returns is digests. Everything downstream compares `canonical.identifier_hash` output, so
    the cascade, the scorer, the evidence and the review item are structurally incapable of
    reading an address or a registration number: there is no value in scope at any of those
    call sites to be interpolated into a reason string.

    Two gates, in this order and not the other. `guardrails.blocked` runs first, because it is
    the shared rule and running it second would mean a free-mail refusal shadowing a
    shared-mailbox one and the operator seeing the weaker explanation. The free-mail domain
    list runs second and applies to `DOMAIN` only.

    **An email at a free-mail domain is kept, and that is deliberate.** The whole address
    identifies one person, which is a legitimate join key for a person entity; the domain part
    of it identifies a mail provider, which is not a join key for anything. Dropping the
    address because of its domain would lose the identifier M14.7 needs most.
    """
    kept: dict[IdentifierKind, str] = {}
    dropped: list[Dropped] = []
    for kind in sorted(values, key=lambda one: one.value):
        value = values[kind]
        refusal = blocked(kind, value)
        if refusal is not None:
            dropped.append(Dropped(kind=kind, rule=refusal.rule))
            continue
        if kind is IdentifierKind.DOMAIN and domain_key(value) in FREE_MAIL_DOMAINS:
            dropped.append(Dropped(kind=kind, rule=None))
            continue
        kept[kind] = identifier_hash(kind, value, pepper=pepper)
    return MappingProxyType(kept), tuple(dropped)


# ---------------------------------------------------------------- trigram similarity (M14.3.3)
def trigrams(text: str) -> frozenset[str]:
    """The padded trigrams of one key, the way pg_trgm builds them.

    One leading pair of spaces and one trailing space per word, so a word of n characters
    yields n + 1 trigrams and the first and last letters are represented. Non-alphanumeric
    characters are word boundaries, matching pg_trgm rather than matching
    `normalise.collapse`'s slightly different rule about symbols.

    **The Python and PostgreSQL implementations are not proven to agree**, and that is said
    here for the reason `normalise.THE_TWO_FOLDINGS_ARE_NOT_PROVEN_TO_AGREE` says it: no unit
    test can compare them because there is no server in one. If they differ, the index holds
    one set of trigrams and the query computes another, the similarity comes out lower than it
    should, and pairs that are one company stay two with nothing reporting it.
    """
    words = "".join(ch if ch.isalnum() else " " for ch in text.casefold()).split()
    grams: set[str] = set()
    for word in words:
        padded = f"  {word} "
        grams.update(padded[i : i + 3] for i in range(len(padded) - 2))
    return frozenset(grams)


def trigram_similarity(left: str, right: str) -> float:
    """How much two keys' trigram sets overlap, as a share. pg_trgm's `similarity`.

    Intersection over union. Two empty keys score nought rather than one: they are not similar,
    they are both nothing, and scoring them one would join every degenerate row in the estate,
    which is the failure `normalise.A_NAME_THAT_IS_ENTIRELY_A_SUFFIX_IS_NOT_A_NAME` refuses at
    the other end.
    """
    left_grams = trigrams(left)
    right_grams = trigrams(right)
    union = left_grams | right_grams
    if not union:
        return 0.0
    return len(left_grams & right_grams) / len(union)


# ------------------------------------------------------ Daitch-Mokotoff, as a subset (M14.3.8)
#: What of the published Daitch-Mokotoff scheme is implemented here.
DAITCH_MOKOTOFF_RULES_IMPLEMENTED = (
    "Six-digit codes, zero padded on the right and truncated on the right. Three-column "
    "position-dependent coding: at the start of the string, immediately before a vowel, and "
    "everywhere else. Multi-letter sequences matched longest first from the table below, "
    "including the sibilant clusters that are the reason the scheme exists. Branching on "
    "letters with more than one pronunciation, so a name returns a set of codes and two names "
    "match when their sets intersect, which is the property that separates this from Soundex. "
    "Vowels coded nought at the start and uncoded elsewhere while still acting as vowels for "
    "the column choice and for the collapse rule. Adjacent identical codes collapsed, except "
    "across a vowel, and except inside one table entry, which is what keeps MN at two sixes."
)

#: What of it is not, so that nobody reads the name as a claim to the whole scheme.
DAITCH_MOKOTOFF_RULES_NOT_IMPLEMENTED = (
    "The complete published sequence table. This one holds roughly a hundred entries against "
    "the published set's greater number, chosen to cover every letter of the Latin alphabet "
    "and the clusters that carry the Slavic, Germanic and Yiddish transliterations; a "
    "sequence that is not here is coded by its longest prefix that is, which is a coarser "
    "answer rather than a wrong one. Removable name prefixes are not handled: the scheme codes "
    "a name beginning with one both with and without it, and this coder codes it once. "
    "Non-Latin scripts are not transliterated; the input is whatever "
    "`normalise.accent_fold` produced. Y and J are not treated as vowels for the column "
    "choice, which the published rules do in some positions. And the coder is applied to a "
    "whole company name rather than to a person's surname, which is what the scheme was built "
    "for, so a two-word name is coded as one string and the second word is usually beyond the "
    "sixth digit. That last one is a real limit and it is part of why the weight is low."
)

#: How many digits a Daitch-Mokotoff code has. Six, which is the published length.
DM_CODE_LENGTH: Final = 6

#: The most alternate codes one name may produce.
#:
#: Sixteen. The floor that matters is not this number but that it is above one: a cap of one
#: would silently turn the coder back into Soundex, because branching is the only thing that
#: makes it more, and a test that a branching letter yields two codes is what pins that. The
#: ceiling exists because a name made entirely of ambiguous letters branches exponentially, and
#: a coder that returned two thousand codes for one name would match almost anything.
MAX_PHONETIC_CODES: Final = 16

#: Letters that count as vowels for the column choice and for the collapse rule.
_VOWELS: Final = frozenset("AEIOU")

#: A code in one column: a digit string, or None for "not coded in this position".
_Codes = tuple[str | None, ...]

#: One table row: the sequence, then its codes at the start, before a vowel, and elsewhere.
_DM_TABLE: tuple[tuple[str, _Codes, _Codes, _Codes], ...] = (
    # Vowels and vowel digraphs. Coded only at the start, except the diphthongs before a vowel.
    ("AI", ("0",), ("1",), (None,)),
    ("AJ", ("0",), ("1",), (None,)),
    ("AY", ("0",), ("1",), (None,)),
    ("AU", ("0",), ("7",), (None,)),
    ("EI", ("0",), ("1",), (None,)),
    ("EJ", ("0",), ("1",), (None,)),
    ("EY", ("0",), ("1",), (None,)),
    ("EU", ("1",), ("1",), (None,)),
    ("IA", ("1",), (None,), (None,)),
    ("IE", ("1",), (None,), (None,)),
    ("IO", ("1",), (None,), (None,)),
    ("IU", ("1",), (None,), (None,)),
    ("OI", ("0",), ("1",), (None,)),
    ("OJ", ("0",), ("1",), (None,)),
    ("OY", ("0",), ("1",), (None,)),
    ("UI", ("0",), ("1",), (None,)),
    ("UJ", ("0",), ("1",), (None,)),
    ("UY", ("0",), ("1",), (None,)),
    ("UE", ("0",), (None,), (None,)),
    ("A", ("0",), (None,), (None,)),
    ("E", ("0",), (None,), (None,)),
    ("I", ("0",), (None,), (None,)),
    ("O", ("0",), (None,), (None,)),
    ("U", ("0",), (None,), (None,)),
    ("Y", ("1",), (None,), (None,)),
    # The long sibilant clusters, which are the reason a whole-sequence table exists at all.
    ("SCHTSCH", ("2",), ("4",), ("4",)),
    ("SCHTSH", ("2",), ("4",), ("4",)),
    ("SCHTCH", ("2",), ("4",), ("4",)),
    ("SHTCH", ("2",), ("4",), ("4",)),
    ("SHTSH", ("2",), ("4",), ("4",)),
    ("STSCH", ("2",), ("4",), ("4",)),
    ("TTSCH", ("4",), ("4",), ("4",)),
    ("ZHDZH", ("2",), ("4",), ("4",)),
    ("SHCH", ("2",), ("4",), ("4",)),
    ("STCH", ("2",), ("4",), ("4",)),
    ("STRZ", ("2",), ("4",), ("4",)),
    ("STRS", ("2",), ("4",), ("4",)),
    ("STSH", ("2",), ("4",), ("4",)),
    ("SZCZ", ("2",), ("4",), ("4",)),
    ("SZCS", ("2",), ("4",), ("4",)),
    ("TSCH", ("4",), ("4",), ("4",)),
    ("TTCH", ("4",), ("4",), ("4",)),
    ("ZSCH", ("4",), ("4",), ("4",)),
    ("ZDZH", ("2",), ("4",), ("4",)),
    ("SCHD", ("2",), ("43",), ("43",)),
    ("SCHT", ("2",), ("43",), ("43",)),
    ("SCH", ("4",), ("4",), ("4",)),
    ("SHT", ("2",), ("43",), ("43",)),
    ("SZT", ("2",), ("43",), ("43",)),
    ("SZD", ("2",), ("43",), ("43",)),
    ("SHD", ("2",), ("43",), ("43",)),
    ("ZHD", ("2",), ("43",), ("43",)),
    ("ZDZ", ("2",), ("4",), ("4",)),
    ("TCH", ("4",), ("4",), ("4",)),
    ("TRZ", ("4",), ("4",), ("4",)),
    ("TRS", ("4",), ("4",), ("4",)),
    ("TSH", ("4",), ("4",), ("4",)),
    ("TTS", ("4",), ("4",), ("4",)),
    ("TTZ", ("4",), ("4",), ("4",)),
    ("TSZ", ("4",), ("4",), ("4",)),
    ("TZS", ("4",), ("4",), ("4",)),
    ("CSZ", ("4",), ("4",), ("4",)),
    ("CZS", ("4",), ("4",), ("4",)),
    ("DRZ", ("4",), ("4",), ("4",)),
    ("DRS", ("4",), ("4",), ("4",)),
    ("DSH", ("4",), ("4",), ("4",)),
    ("DSZ", ("4",), ("4",), ("4",)),
    ("DZH", ("4",), ("4",), ("4",)),
    ("DZS", ("4",), ("4",), ("4",)),
    ("CHS", ("5",), ("54",), ("54",)),
    ("SH", ("4",), ("4",), ("4",)),
    ("SZ", ("4",), ("4",), ("4",)),
    ("ST", ("2",), ("43",), ("43",)),
    ("SD", ("2",), ("43",), ("43",)),
    ("SC", ("2",), ("4",), ("4",)),
    ("ZH", ("4",), ("4",), ("4",)),
    ("ZS", ("4",), ("4",), ("4",)),
    ("ZD", ("2",), ("43",), ("43",)),
    ("CS", ("4",), ("4",), ("4",)),
    ("CZ", ("4",), ("4",), ("4",)),
    ("DS", ("4",), ("4",), ("4",)),
    ("DZ", ("4",), ("4",), ("4",)),
    ("TS", ("4",), ("4",), ("4",)),
    ("TZ", ("4",), ("4",), ("4",)),
    ("TC", ("4",), ("4",), ("4",)),
    ("KS", ("5",), ("54",), ("54",)),
    ("KH", ("5",), ("5",), ("5",)),
    ("TH", ("3",), ("3",), ("3",)),
    ("DT", ("3",), ("3",), ("3",)),
    ("DD", ("3",), ("3",), ("3",)),
    ("TT", ("3",), ("3",), ("3",)),
    ("PF", ("7",), ("7",), ("7",)),
    ("PH", ("7",), ("7",), ("7",)),
    ("FB", ("7",), ("7",), ("7",)),
    ("MN", ("66",), ("66",), ("66",)),
    ("NM", ("66",), ("66",), ("66",)),
    # The branching entries. Each is a letter with two pronunciations in the languages the
    # scheme covers, and each is the reason a name has a set of codes rather than one.
    ("CH", ("5", "4"), ("5", "4"), ("5", "4")),
    ("CK", ("5", "45"), ("5", "45"), ("5", "45")),
    ("RZ", ("94", "4"), ("94", "4"), ("94", "4")),
    ("RS", ("94", "4"), ("94", "4"), ("94", "4")),
    ("C", ("5", "4"), ("5", "4"), ("5", "4")),
    ("J", ("1", "4"), ("1", "4"), ("1", "4")),
    # Single consonants.
    ("B", ("7",), ("7",), ("7",)),
    ("D", ("3",), ("3",), ("3",)),
    ("F", ("7",), ("7",), ("7",)),
    ("G", ("5",), ("5",), ("5",)),
    ("H", ("5",), ("5",), (None,)),
    ("K", ("5",), ("5",), ("5",)),
    ("L", ("8",), ("8",), ("8",)),
    ("M", ("6",), ("6",), ("6",)),
    ("N", ("6",), ("6",), ("6",)),
    ("P", ("7",), ("7",), ("7",)),
    ("Q", ("5",), ("5",), ("5",)),
    ("R", ("9",), ("9",), ("9",)),
    ("S", ("4",), ("4",), ("4",)),
    ("T", ("3",), ("3",), ("3",)),
    ("V", ("7",), ("7",), ("7",)),
    ("W", ("7",), ("7",), ("7",)),
    ("X", ("5",), ("54",), ("54",)),
    ("Z", ("4",), ("4",), ("4",)),
)

_DM_LOOKUP: Final = MappingProxyType({row[0]: row for row in _DM_TABLE})
_DM_LONGEST: Final = max(len(row[0]) for row in _DM_TABLE)

#: One partial code under construction: the digits so far, the last digit appended, and whether
#: a vowel has been passed since it was.
_Branch = tuple[str, str | None, bool]


def _letters(name: str) -> str:
    """The name as the coder sees it: accent folded, upper case, letters only.

    `normalise.accent_fold` rather than a second fold, for the reason that module gives about
    two implementations of normalisation producing two sets of keys. Digits and punctuation are
    dropped rather than made into boundaries, because the coder has no concept of a word.
    """
    folded = accent_fold(name.casefold()).upper()
    return "".join(ch for ch in folded if "A" <= ch <= "Z")


def _extend(branches: Sequence[_Branch], codes: _Codes, *, is_vowel: bool) -> list[_Branch]:
    """Append one sequence's codes to every branch, collapsing where the rule says to.

    Only the *first* digit of a table entry is collapse-checked against what came before.
    Digits inside one entry are appended as written, which is what keeps MN at two sixes: the
    entry exists precisely to say that these two sounds are not one sound.
    """
    out: list[_Branch] = []
    seen: set[_Branch] = set()
    for digits, last, gap in branches:
        for code in codes:
            if code is None:
                nxt = (digits, last, gap or is_vowel)
            elif code[0] == last and not gap:
                rest = code[1:]
                nxt = (digits + rest, rest[-1] if rest else last, False)
            else:
                nxt = (digits + code, code[-1], False)
            if nxt not in seen:
                seen.add(nxt)
                out.append(nxt)
    return out[:MAX_PHONETIC_CODES]


def phonetic_codes(name: str) -> frozenset[str]:
    """Every Daitch-Mokotoff code this name can have, as a subset of the scheme (M14.3.8).

    A set rather than a single code, because branching is the whole difference between this and
    Soundex: a name spelled with a C that could be read as K or as TS gets both readings, and
    two names match when their sets intersect. See `DAITCH_MOKOTOFF_RULES_IMPLEMENTED` for what
    is here and `DAITCH_MOKOTOFF_RULES_NOT_IMPLEMENTED` for what is not.

    An empty set for a name with no letters in it, which is the only honest answer and which
    `phonetic_agrees` turns into "no agreement" rather than into "agreement on nothing".
    """
    letters = _letters(name)
    if not letters:
        return frozenset()
    branches: list[_Branch] = [("", None, False)]
    position = 0
    while position < len(letters):
        row = None
        longest = min(_DM_LONGEST, len(letters) - position)
        for length in range(longest, 0, -1):
            row = _DM_LOOKUP.get(letters[position : position + length])
            if row is not None:
                break
        if row is None:
            # Unreachable while the table covers every letter A to Z, which `cascade_gaps`
            # checks. Kept so that a table edit which drops a letter degrades to skipping it
            # rather than looping forever on the same position.
            position += 1
            continue
        sequence, at_start, before_vowel, otherwise = row
        following = letters[position + len(sequence) : position + len(sequence) + 1]
        if position == 0:
            codes = at_start
        elif following in _VOWELS:
            codes = before_vowel
        else:
            codes = otherwise
        branches = _extend(branches, codes, is_vowel=sequence[0] in _VOWELS)
        position += len(sequence)
    padded = sorted((digits + "0" * DM_CODE_LENGTH)[:DM_CODE_LENGTH] for digits, _, _ in branches)
    return frozenset(padded[:MAX_PHONETIC_CODES])


def phonetic_agrees(left: str, right: str) -> bool:
    """Whether two names share any Daitch-Mokotoff code.

    Set intersection rather than equality of a single code, which is what the scheme asks for:
    a name with two readings agrees with a name that has one of them.
    """
    return bool(phonetic_codes(left) & phonetic_codes(right))


# ------------------------------------------------------------------ what a record looks like
#: What `canonical.Identifier.key_hash` accepts, restated as an early refusal.
#:
#: `canonical` is the authority and `er.identifier` constrains the column; this is the same
#: bound applied one step earlier, so a caller that handed the cascade a raw email address
#: fails here rather than joining on plaintext and producing a link nobody can explain. The
#: precedent is `normalise`'s alias length, refused "here as well as in the column".
_DIGEST_RE: Final = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Observation:
    """One source record as the cascade may compare it: keys and digests, never values.

    `identifiers` holds `canonical.identifier_hash` output, which is why nothing downstream of
    this type can read an address or a registration number. `fields` holds opaque comparison
    tokens for the fields that are neither a name nor an identifier: this module compares them
    for equality and has no idea what they say, which is the point.

    `verified` names the identifier kinds the source confirmed rather than merely reported. It
    is a fact the connector asserts and never something inferred here: inferring it would make
    stage one's strength a guess.
    """

    record: SourceRef
    name: NormalisedName
    identifiers: Mapping[IdentifierKind, str] = MappingProxyType({})
    fields: Mapping[Feature, str] = MappingProxyType({})
    verified: frozenset[IdentifierKind] = frozenset()

    def __post_init__(self) -> None:
        for kind, digest in self.identifiers.items():
            if not _DIGEST_RE.match(digest):
                msg = (
                    f"the {kind.value} identifier is not a sha256 digest. The cascade compares "
                    "digests so that no value is ever in scope where a reason string is built; "
                    "a raw value here would join on plaintext and would reach a review item"
                )
                raise ResolutionError(msg)
        for feature in self.fields:
            if feature not in FIELD_FEATURES:
                msg = (
                    f"{feature.value!r} is not a corroborating field. A name feature carried "
                    "here would let a name corroborate itself, and an identifier carried here "
                    "would skip the blocklist that identifiers pass through"
                )
                raise ResolutionError(msg)

    def is_hard(self, kind: IdentifierKind) -> bool:
        """Whether this record's identifier of that kind may decide stage one.

        Present, and verified where the leaf asks for verification. A domain nobody confirmed
        is still compared and still scored; it simply does not decide alone.
        """
        if kind not in self.identifiers:
            return False
        return kind not in VERIFICATION_REQUIRED or kind in self.verified


# ---------------------------------------------------------------------- the comparison
@dataclass(frozen=True)
class Comparison:
    """What comparing two records found, before any stage has looked at it.

    Deliberately inert. It carries what agreed, what was comparable and disagreed, the observed
    similarity and the strongest hard identifier both records carry, and it draws no
    conclusion: the stages are the conclusion, and separating them is what makes it possible to
    test that stage one returns before the scorer runs.

    There is no count of anything and no candidate on it, so nothing built from a `Comparison`
    can report how many records were considered.
    """

    agreed: frozenset[Feature]
    #: Features both records could be compared on that did not agree.
    disagreed: frozenset[Feature]
    #: The trigram similarity of the two match keys, or None when either has no usable key.
    similarity: float | None
    #: The strongest hard identifier both records carry, or None when they share none.
    hard_kind: IdentifierKind | None
    #: Whether that identifier agreed. Meaningless, and False, when `hard_kind` is None.
    hard_agreed: bool


def compare(
    left: Observation, right: Observation, *, thresholds: Thresholds = DECLARED_THRESHOLDS
) -> Comparison:
    """Every comparison the two records admit, with no verdict attached.

    The name features are mutually exclusive by construction: `NAME_EXACT` is the collapsed
    forms agreeing, `NAME_STRIPPED` is the match keys agreeing when the collapsed forms did
    not, and `NAME_TRIGRAM` is similarity at or above the upper threshold. Reporting all three
    for one pair of identical names would put three terms in the sum for one fact, which is how
    an additive score double-counts and how a threshold quietly stops meaning what it meant.

    A name whose `normalise` verdict is not USABLE takes part in nothing. `match_key` is None
    for those, which is the guard that module built for exactly this call site, and a caller
    that ignored the verdict would otherwise join every too-short name to every other.
    """
    agreed: set[Feature] = set()
    disagreed: set[Feature] = set()

    for kind in IdentifierKind:
        feature = Feature(kind.value)
        if kind not in left.identifiers or kind not in right.identifiers:
            continue
        if left.identifiers[kind] == right.identifiers[kind]:
            agreed.add(feature)
        else:
            disagreed.add(feature)

    for feature in sorted(FIELD_FEATURES, key=lambda one: one.value):
        if feature not in left.fields or feature not in right.fields:
            continue
        if left.fields[feature] == right.fields[feature]:
            agreed.add(feature)
        else:
            disagreed.add(feature)

    left_key = left.name.match_key
    right_key = right.name.match_key
    similarity: float | None = None
    if left_key is not None and right_key is not None:
        similarity = trigram_similarity(left_key, right_key)
        if left.name.collapsed == right.name.collapsed:
            agreed.add(Feature.NAME_EXACT)
        elif left_key == right_key:
            agreed.add(Feature.NAME_STRIPPED)
        elif similarity >= thresholds.upper:
            agreed.add(Feature.NAME_TRIGRAM)
        else:
            disagreed.add(Feature.NAME_TRIGRAM)
        if phonetic_agrees(left_key, right_key):
            agreed.add(Feature.NAME_PHONETIC)
        else:
            disagreed.add(Feature.NAME_PHONETIC)

    shared_hard = [kind for kind in HARD_IDENTIFIERS if left.is_hard(kind) and right.is_hard(kind)]
    hard_kind = min(shared_hard, key=priority_of) if shared_hard else None
    hard_agreed = hard_kind is not None and Feature(hard_kind.value) in agreed
    return Comparison(
        agreed=frozenset(agreed),
        disagreed=frozenset(disagreed),
        similarity=similarity,
        hard_kind=hard_kind,
        hard_agreed=hard_agreed,
    )


# ------------------------------------------------------------ corroboration (M14.3.2)
@dataclass(frozen=True)
class CorroboratedName:
    """A name agreement with a second, non-name field agreeing beside it.

    **There is no way to build one out of a name alone**, and that is the whole of M14.3.2's
    guard. `corroborant` is refused when it is a name feature, so "the names agree and the
    trigrams also agree" cannot be expressed, and `name` is refused when it is not one, so the
    two slots cannot be filled the other way round to sneak past. See
    `STAGE_TWO_CANNOT_BE_REACHED_BY_A_NAME_ALONE`.
    """

    name: Feature
    corroborant: Feature

    def __post_init__(self) -> None:
        if self.name not in NAME_FEATURES:
            msg = (
                f"{self.name.value!r} is not a name feature, so this is not a name agreement "
                "and stage two is not the stage that admits it"
            )
            raise ResolutionError(msg)
        if self.corroborant in NAME_FEATURES:
            msg = (
                f"{self.corroborant.value!r} is a name feature and cannot corroborate a name. "
                "Two name features agreeing is one fact reported twice, and admitting it here "
                "makes stage two into 'the names agree', which is the promotion M14.3.2 exists "
                "to prevent"
            )
            raise ResolutionError(msg)


def corroboration_for(comparison: Comparison) -> CorroboratedName | None:
    """The strongest corroborated name agreement in this comparison, or None (M14.3.2).

    Ordered so that two runs over the same comparison produce the same answer: the exact name
    before the stripped one, and the corroborating features in `Feature` declaration order.
    Order matters because the corroborant reaches a reviewer in the audit and an answer that
    varied between runs would read as two different pieces of evidence.
    """
    for name in (Feature.NAME_EXACT, Feature.NAME_STRIPPED):
        if name not in comparison.agreed:
            continue
        for corroborant in Feature:
            if corroborant in NAME_FEATURES or corroborant not in comparison.agreed:
                continue
            return CorroboratedName(name=name, corroborant=corroborant)
    return None


# ------------------------------------------------------- the additive score (M14.3.6)
def score(agreed: frozenset[Feature], *, weights: WeightTable = DECLARED_WEIGHTS) -> float:
    """The sum of the weights of the features that agreed.

    One weight per agreeing feature, added. A feature that disagreed contributes nothing rather
    than a negative, and that is honesty rather than design: how much a disagreement should
    cost is exactly the quantity a calibration measures, and inventing one here would put a
    fitted-looking number in a table that has been fitted to nothing. See
    `THE_WEIGHTS_ARE_DECLARED_AND_NOTHING_HAS_CALIBRATED_THEM`.
    """
    return sum(weights.weight_for(feature) for feature in agreed)


def evidence_for(
    comparison: Comparison, *, weights: WeightTable = DECLARED_WEIGHTS
) -> tuple[Evidence, ...]:
    """Every comparison as a line a reviewer can read, strongest first.

    `guardrails.Evidence` rather than a local type, so there is one thing a reviewer is shown
    and one rule about what may be on it: a field name and a weight, and nowhere to put a
    value. A disagreement is carried at weight nought, which `guardrails.strength_of` renders
    as AGAINST, because a reviewer who sees only the agreements is being shown half the
    evidence and will merge more than they should.
    """
    lines = [
        Evidence(field=feature.value, weight=weights.weight_for(feature))
        for feature in sorted(comparison.agreed, key=lambda one: one.value)
    ]
    lines.extend(
        Evidence(field=feature.value, weight=0.0)
        for feature in sorted(comparison.disagreed, key=lambda one: one.value)
    )
    return tuple(lines)


#: How each feature is compared in SQL. Exhaustive over `Feature` by `cascade_gaps`.
#:
#: Written as data rather than assembled in a loop, for the reason `guardrails.PLAIN_LANGUAGE`
#: is: the property that matters is that every feature has an expression and that every
#: expression is a comparison rather than a call, and both are visible here and would be buried
#: in a builder.
#:
#: **The four name predicates are mutually exclusive, and the guards are the whole of why.**
#: `compare` reports at most one name feature for a pair, because reporting three for one fact
#: is how an additive score double-counts. The first version of this table was four bare
#: equalities, which report three for a pair of identical names: `name_collapsed` agrees,
#: `name_key` agrees because it is derived from it, and the similarity of two equal keys is
#: one. The rendered expression therefore scored six where `score` scored four, on the pairs
#: that match most often. A key that differs implies a collapsed form that differs, so the
#: trigram term needs only the one guard, and the stripped term needs the other one.
#:
#: `l.name_key IS NOT NULL` stands for `normalise.NormalisedName.match_key` being None, which
#: is every verdict that is not USABLE. `compare` evaluates no name feature at all for such a
#: pair, and the two guarded terms would otherwise agree on the collapsed form of two names
#: neither of which may be matched on.
#:
#: `l` and `r` are the two sides of the self join. None of these columns exists: no migration
#: in this repository declares them, and the phonetic one assumes a text array materialised at
#: write time, which is the point `WHAT_WOULD_BREAK_THE_SQL_SHAPE` makes.
SQL_PREDICATES: Mapping[Feature, str] = MappingProxyType(
    {
        Feature.UEN: "l.uen_hash = r.uen_hash",
        Feature.TAX_ID: "l.tax_id_hash = r.tax_id_hash",
        Feature.DOMAIN: "l.domain_hash = r.domain_hash",
        Feature.PHONE: "l.phone_hash = r.phone_hash",
        Feature.EMAIL: "l.email_hash = r.email_hash",
        Feature.NAME_EXACT: (
            "l.name_key IS NOT NULL AND r.name_key IS NOT NULL "
            "AND l.name_collapsed = r.name_collapsed"
        ),
        Feature.NAME_STRIPPED: "l.name_collapsed <> r.name_collapsed AND l.name_key = r.name_key",
        Feature.NAME_TRIGRAM: (
            "l.name_key <> r.name_key AND similarity(l.name_key, r.name_key) >= :upper"
        ),
        Feature.NAME_PHONETIC: (
            "l.name_key IS NOT NULL AND r.name_key IS NOT NULL AND l.name_dm && r.name_dm"
        ),
        Feature.COUNTRY: "l.country_key = r.country_key",
        Feature.POSTCODE: "l.postcode_key = r.postcode_key",
    }
)


#: What each weight binds under in the rendered expression: this prefix and the feature's
#: machine name. Declared here rather than in `brain.resolution.query`, because the renderer
#: below writes the placeholder and that module binds it, and a prefix declared on both sides
#: is a statement that fails on a missing parameter the first time the two disagree.
WEIGHT_PARAM_PREFIX: Final = "w_"


def sql_score_expression() -> str:
    """The additive score as one SQL expression, with every weight bound rather than written in.

    One scoring rule and not two: the terms come from `SQL_PREDICATES`, which `cascade_gaps`
    holds exhaustive over `Feature`, and each term's weight arrives as a parameter that
    `brain.resolution.query.weight_parameters` binds from the same `WeightTable` `score` sums.
    A caller pastes this into a SELECT over a self join and gets one number per candidate pair
    with no round trip, which is what M14.3.6 means by millisecond online cost.

    **Bound rather than rendered, and that is not a matter of style.** A weight written into the
    text makes every re-calibration a different statement: prepared statements and plan caches
    turn over, and a figure a job fitted has become part of the query rather than an input to
    it. M14.4.4 schedules that job weekly, so the difference is a new argument list against a
    new query, every week. The weight table's version is not rendered here for the same reason;
    `query.ScoreQuery` carries it as a field, where it can be written onto a link.

    Every term is `CASE WHEN <comparison> THEN <bound weight> ELSE 0 END`, and the terms are
    added. There is no function call, no subquery and no window in any of them except pg_trgm's
    `similarity`, which is an operator with an index behind it rather than a computation. See
    `WHAT_WOULD_BREAK_THE_SQL_SHAPE`, and note that no migration here creates the columns this
    names.

    The name terms carry guards so that the total this renders is the total `score` sums over
    `compare`'s agreements rather than a larger one. See `SQL_PREDICATES`.
    """
    terms = [
        f"  CASE WHEN {SQL_PREDICATES[feature]} "
        f"THEN :{WEIGHT_PARAM_PREFIX}{feature.value} ELSE 0 END"
        for feature in Feature
    ]
    return "\n+ ".join(terms)


# ------------------------------------------------------------------- the cascade itself
@dataclass(frozen=True)
class CascadeResult:
    """What the cascade decided about one pair, and the evidence it decided on.

    `confidence` is None for anything that is not a match, so a caller cannot write a link out
    of a review item by reading a field that happened to hold a number. There is no total score
    on the type either: the per-feature evidence is here, which is where evidence belongs, and a
    total is the thing a reviewer would threshold on, on a scale nothing has calibrated. That is
    `guardrails.ReviewItem`'s rule applied one layer earlier.

    No count of candidates and no other candidate is named. This is an answer about two records.
    """

    decision: Decision
    stage: Stage
    left: SourceRef
    right: SourceRef
    evidence: tuple[Evidence, ...]
    reason: str
    #: What goes in `canonical.Link.confidence`, or None when nothing should be linked.
    confidence: float | None = None

    def __post_init__(self) -> None:
        if (self.confidence is not None) is not (self.decision is Decision.MATCHED):
            msg = (
                "confidence and the decision have to agree. A confidence on a refusal is a "
                "number a caller will write into a link, and a match with no confidence is a "
                "link with nothing to put in the column canonical.Link requires"
            )
            raise ResolutionError(msg)

    def review_item(self, item_id: str) -> ReviewItem:
        """This pair as something a person can be asked about (M14.3.4).

        Refuses for anything that is not `TO_REVIEW`, because a queue holding decided pairs is
        a queue nobody finishes, and a reviewer shown a decided pair will assume the cascade
        wanted their opinion about it.

        **Nothing here filters by reach.** `guardrails.review_queue` holds that filter and
        holds it as a conjunction over both halves; a second copy here would be a second place
        for it to be subtly wrong, and the wrong copy is the one in production.
        """
        if self.decision is not Decision.TO_REVIEW:
            msg = (
                f"this pair was decided at stage {self.stage.value}, so there is nothing to "
                "review; a queue of decided pairs teaches its reviewers to approve everything"
            )
            raise ResolutionError(msg)
        return ReviewItem(item_id=item_id, left=self.left, right=self.right, evidence=self.evidence)


def cascade(
    left: Observation,
    right: Observation,
    *,
    thresholds: Thresholds = DECLARED_THRESHOLDS,
    weights: WeightTable = DECLARED_WEIGHTS,
) -> CascadeResult:
    """Four stages in order, and the first one that can answer does (M14.3.1 to M14.3.4).

    Stage one is a hard identifier and it is an identity: it returns, and nothing below it is
    evaluated on that path. A hard identifier that *disagrees* also returns, refusing, because
    the strongest identifier both records carry saying they are two companies is not something
    a name similarity may overturn. See `A_HARD_IDENTIFIER_IS_AN_IDENTITY_AND_NOT_A_SCORE`.

    Stage two is a normalised name with a second field agreeing beside it, carried as a
    `CorroboratedName` so that a name alone is not expressible. A pair whose names are equal
    and which nothing corroborates goes to a person rather than falling into stage three, for
    the reason `A_SIMILARITY_IS_A_MEASUREMENT_AND_EQUALITY_IS_NOT_ONE` gives: without that
    branch stage three merges everything stage two refused, and M14.3.2's guard decides
    nothing. Stage three is the trigram similarity against two thresholds, over pairs whose
    keys differ, and stage four is the band between them. A pair whose
    names cannot be measured at all reaches stage four only when something else agreed:
    queueing every unmeasurable pair would make the review queue the whole estate, and queueing
    none of them would throw away `normalise.A_SHORT_NAME_IS_NOT_A_BAD_NAME`.

    The additive score is computed for the evidence and never for the decision. It is available
    to a caller through `score`, it is what `sql_score_expression` renders, and it decides
    nothing here, which is the property that keeps six weak agreements from outvoting a
    register number.
    """
    comparison = compare(left, right, thresholds=thresholds)
    evidence = evidence_for(comparison, weights=weights)

    if comparison.hard_kind is not None:
        kind = comparison.hard_kind
        if comparison.hard_agreed:
            return CascadeResult(
                decision=Decision.MATCHED,
                stage=Stage.HARD_IDENTIFIER,
                left=left.record,
                right=right.record,
                evidence=evidence,
                confidence=DECLARED_CONFIDENCE[Stage.HARD_IDENTIFIER],
                reason=(
                    f"both records carry the same {kind.value}, which is the strongest hard "
                    "identifier they share; that is an identity rather than a score"
                ),
            )
        return CascadeResult(
            decision=Decision.NOT_MATCHED,
            stage=Stage.HARD_IDENTIFIER,
            left=left.record,
            right=right.record,
            evidence=evidence,
            reason=(
                f"both records carry a {kind.value} and the two disagree; that is the "
                "strongest hard identifier they share and a weaker one cannot overturn it"
            ),
        )

    corroborated = corroboration_for(comparison)
    if corroborated is not None:
        return CascadeResult(
            decision=Decision.MATCHED,
            stage=Stage.CORROBORATED_NAME,
            left=left.record,
            right=right.record,
            evidence=evidence,
            confidence=DECLARED_CONFIDENCE[Stage.CORROBORATED_NAME],
            reason=(
                f"{corroborated.name.value} agreed and {corroborated.corroborant.value} "
                "agreed with it, so the name is not carrying this on its own"
            ),
        )

    if comparison.agreed & NAME_EQUALITY_FEATURES:
        return CascadeResult(
            decision=Decision.TO_REVIEW,
            stage=Stage.HUMAN_REVIEW,
            left=left.record,
            right=right.record,
            evidence=evidence,
            reason=(
                "the names are equal and nothing else agreed; stage two is the stage that "
                "admits a name agreement and it asks for a second field, and the similarity "
                "of two equal keys is equality rather than a measurement"
            ),
        )

    if comparison.similarity is None:
        if comparison.agreed:
            return CascadeResult(
                decision=Decision.TO_REVIEW,
                stage=Stage.HUMAN_REVIEW,
                left=left.record,
                right=right.record,
                evidence=evidence,
                reason=(
                    "one of the two names cannot be matched on, so there is no similarity to "
                    "threshold, and something else agreed; a person decides this one"
                ),
            )
        return CascadeResult(
            decision=Decision.NOT_MATCHED,
            stage=Stage.SIMILARITY,
            left=left.record,
            right=right.record,
            evidence=evidence,
            reason=(
                "one of the two names cannot be matched on and nothing else agreed, so there "
                "is no evidence here for a person to weigh"
            ),
        )

    if comparison.similarity >= thresholds.upper:
        return CascadeResult(
            decision=Decision.MATCHED,
            stage=Stage.SIMILARITY,
            left=left.record,
            right=right.record,
            evidence=evidence,
            confidence=DECLARED_CONFIDENCE[Stage.SIMILARITY],
            reason=(
                f"the two match keys are {comparison.similarity:.2f} similar, at or above the "
                f"upper threshold of {thresholds.upper}"
            ),
        )
    if thresholds.band_holds(comparison.similarity):
        return CascadeResult(
            decision=Decision.TO_REVIEW,
            stage=Stage.HUMAN_REVIEW,
            left=left.record,
            right=right.record,
            evidence=evidence,
            reason=(
                f"the two match keys are {comparison.similarity:.2f} similar, between the "
                f"thresholds of {thresholds.lower} and {thresholds.upper}; that band is a "
                "person rather than a decision"
            ),
        )
    return CascadeResult(
        decision=Decision.NOT_MATCHED,
        stage=Stage.SIMILARITY,
        left=left.record,
        right=right.record,
        evidence=evidence,
        reason=(
            f"the two match keys are {comparison.similarity:.2f} similar, below the lower "
            f"threshold of {thresholds.lower}"
        ),
    )


# ------------------------------------------------------------------------- the gaps
def cascade_gaps(
    weights: WeightTable = DECLARED_WEIGHTS,
    thresholds: Thresholds = DECLARED_THRESHOLDS,
    predicates: Mapping[Feature, str] = SQL_PREDICATES,
    confidence: Mapping[Stage, float] = DECLARED_CONFIDENCE,
) -> tuple[str, ...]:
    """Every place the tables in this module disagree with each other or with what they claim.

    Every table is a parameter, for the reason `guardrails.guardrail_gaps` takes its caps as
    one: a detector that only fires when the tables disagree returns nothing on a healthy tree
    whether or not it is still doing anything, and a mutation run in that package found exactly
    that. The parameters are how a test hands it tables that do disagree.

    `confidence` was a module constant read from inside this function until a test tried to
    exercise the check below and found there was no way to. That is the same defect one
    parameter down, and it is worth naming rather than quietly fixing: a check nothing can make
    fire is a check nothing has proved is still connected.

    The fourth check is the one worth having. It holds the confidence table against the
    thresholds rather than against itself: a link the cascade makes on similarity must be
    believed more than the figure below which it refuses to make one, and a stage-two link must
    be believed more than a stage-three one, because the stages are ordered by strength and a
    confidence that inverted them would tell a reviewer the opposite of the truth.
    """
    gaps: list[str] = []

    for feature in Feature:
        if feature not in weights.weights:
            gaps.append(
                f"{feature.value} has no weight, so it contributes nothing to the score and "
                "cannot be told apart from a feature that never agreed"
            )
        if feature not in predicates:
            gaps.append(
                f"{feature.value} has no SQL predicate, so the rendered expression scores it "
                "at nothing while the Python scorer scores it at its weight"
            )

    for kind in IdentifierKind:
        if kind.value not in {feature.value for feature in Feature}:
            gaps.append(
                f"{kind.value} is an identifier kind with no feature, so the cascade cannot "
                "compare it and stage one cannot decide on it"
            )

    email_rank = priority_of(IdentifierKind.EMAIL)
    for kind in HARD_IDENTIFIERS:
        if priority_of(kind) >= email_rank:
            gaps.append(
                f"{kind.value} decides stage one and does not outrank email in the identifier "
                "priority order, so the cascade merges on an identifier guardrails calls the "
                "weakest available"
            )

    ordered = (Stage.HARD_IDENTIFIER, Stage.CORROBORATED_NAME, Stage.SIMILARITY)
    for stronger, weaker in itertools.pairwise(ordered):
        if confidence[stronger] <= confidence[weaker]:
            gaps.append(
                f"a match at stage {stronger.value} is not believed more than one at stage "
                f"{weaker.value}, which inverts the order the stages are in"
            )
    if confidence[Stage.SIMILARITY] <= thresholds.lower:
        gaps.append(
            "a similarity match is believed no more than the threshold below which the "
            "cascade refuses to make one, so the confidence says less than the refusal does"
        )

    missing_letters = sorted(
        letter for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if letter not in _DM_LOOKUP
    )
    if missing_letters:
        gaps.append(
            f"the phonetic table has no entry for {', '.join(missing_letters)}, so a name "
            "containing one is coded with that letter silently skipped"
        )
    return tuple(gaps)
