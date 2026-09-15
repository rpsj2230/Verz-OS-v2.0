"""Everything the record matcher decides, in a module that can be tested without the matcher.

`docs/needs-rupash.md` item 55 decided on Option A: Splink and DuckDB live in an offline image
of their own, the way the models run beside the application in item 31, and never inside the
process that answers requests. That leaves the job split in two, and the split is the design.
`brain.resolution.splink_job` is the half that imports the two packages, opens the export and
calls the library. This module is every decision that job makes, written in terms of the
cascade, and it imports neither package, so the suite that gates every commit can test the job
without the image that runs it. See `THE_MATCHER_IS_AN_IMAGE_AND_ITS_DECISIONS_ARE_NOT`.

**The Splink model is derived from `brain.resolution.cascade` and never written a second
time.** Every comparison condition is `cascade.SQL_PREDICATES` rewritten from the self-join
spelling (`l.name_key`) to Splink's (`name_key_l`), the similarity threshold is bound from
`cascade.DECLARED_THRESHOLDS`, and the trigram similarity DuckDB calls is
`cascade.trigram_similarity` registered into the connection under pg_trgm's name. The export's
columns are the columns those predicates name, and a row is built from a `cascade.Observation`.
So a feature added to the cascade arrives here as a comparison, or as a refusal naming it,
rather than as a matcher quietly scoring the old vocabulary. Rejected: a Splink settings file
kept beside the cascade. It is the cheaper thing to write and it is a second copy of the
central matching rule, and the copy is the one that would run against real data. See
`THE_SETTINGS_ARE_DERIVED_FROM_THE_CASCADE_AND_NOT_WRITTEN_A_SECOND_TIME`.

**The starting model is the declared one.** Each agreeing level starts at `calibration.
INITIAL_M` and at the unmatch probability that makes `calibration.weight_of` return that
feature's declared weight, so an untrained run scores agreements exactly as `cascade.score`
does. Training then measures them. Rejected: Splink's own defaults, which would make an
untrained run a different model from the one the cascade documents, with nothing saying so.

**It suggests and it never merges (M14.4.1's own words: suggestions for a person to confirm).**
The only thing this module produces is a `guardrails.ReviewItem`, the type the review queue
already renders and filters by reach over both halves, and the file it writes holds nothing
else: no total, no probability, no link and no confidence. Nothing here imports
`brain.resolution.merge`, the job holds no connection string to this system's database, and a
test reads both off the import graph. See `THE_MATCHER_SUGGESTS_AND_NEVER_MERGES`.

**The blocking pass is here, and it is also where the matcher's recall is decided.** A pair
that no blocking rule admits is never compared, so a trigram match between two records with
different postcodes, different identifiers and different first letters is never suggested.
That is the trade every blocking pass makes and it is stated rather than implied: see
`BLOCKING_DECIDES_WHAT_IS_NEVER_COMPARED`.

Scope: offline. Nothing on the request path may import this module, and
`tests/invariants/test_no_ml_on_the_request_path.py` holds that, together with the stronger
rule that the only module under `src/brain` importing a numerical library is the job itself.

Task ids: M14.4.1
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Final

from brain.ops.wiring import component
from brain.resolution.calibration import (
    _REF_RE,
    INITIAL_M,
    MIN_REF_CHARS,
)
from brain.resolution.canonical import IdentifierKind, ResolutionError, SourceRef
from brain.resolution.cascade import (
    DECLARED_THRESHOLDS,
    DECLARED_WEIGHTS,
    HARD_IDENTIFIERS,
    SQL_PREDICATES,
    Feature,
    Observation,
    Thresholds,
    WeightTable,
    phonetic_codes,
    trigram_similarity,
)
from brain.resolution.guardrails import Evidence, ReviewItem
from brain.resolution.normalise import MIN_KEY_CHARS

# ------------------------------------------------------------------ written-down reasons
#: Why the packages and this module are in different places.
THE_MATCHER_IS_AN_IMAGE_AND_ITS_DECISIONS_ARE_NOT: Final = (
    "Item 55 put Splink and DuckDB in an offline image of their own, so the application's "
    "environment never contains them and the suite that gates a commit cannot import them. A "
    "job written as one module would therefore be a job no gate ever tests. So the module that "
    "imports the packages is kept to opening an export, registering functions and calling the "
    "library, and every decision it makes is here, importable anywhere the cascade is."
)

#: Why the Splink model is computed rather than configured.
THE_SETTINGS_ARE_DERIVED_FROM_THE_CASCADE_AND_NOT_WRITTEN_A_SECOND_TIME: Final = (
    "The comparison conditions are cascade.SQL_PREDICATES rewritten to Splink's column "
    "spelling, the similarity threshold is the declared one, and the similarity function "
    "DuckDB calls is cascade.trigram_similarity. A settings file written beside the cascade "
    "would be a second copy of the rule that decides whether two records are one company, and "
    "the copy would be the one run against real data while the tests watched the original."
)

#: Why nothing this job produces can become a merge on its own.
THE_MATCHER_SUGGESTS_AND_NEVER_MERGES: Final = (
    "A probabilistic match is a reason to ask a person, never a reason to move a pointer. The "
    "job produces guardrails.ReviewItem and nothing else, which the review queue already shows "
    "only to somebody who reaches both records, and the file it writes carries no total, no "
    "probability and no confidence for a later step to threshold into a link. It imports "
    "nothing from brain.resolution.merge and holds no connection to this system's database, "
    "so there is no call it could make to merge anything even if a line were added asking it to."
)

#: Why the floor is where it is.
A_SUGGESTION_IS_A_PAIR_MORE_LIKELY_ONE_THING_THAN_TWO: Final = (
    "Splink's match weight includes the prior, so a total of nought is a posterior probability "
    "of one half: the model thinks these records are as likely one company as two. Below that "
    "a suggestion asks a reviewer to look at a pair the model itself believes are different, "
    "and a queue of those teaches its reviewers to reject without reading. The floor selects "
    "which pairs become questions; it is never written onto one."
)

#: Why an agreement with a trained weight at or below nought is still rendered as agreeing.
AN_AGREEMENT_IS_NEVER_RENDERED_AS_A_DISAGREEMENT: Final = (
    "guardrails.strength_of renders a weight of nought or less as AGAINST, whose sentence is "
    "'did not agree'. Training can measure an agreement as evidence for nothing, and rendering "
    "that as a disagreement would tell a reviewer two fields differ when they are the same. So "
    "an agreeing level is floored just above nought, which renders as agreed and barely moving "
    "the answer, and that sentence is true of an agreement worth nothing."
)

#: The mirror of the rule above.
A_DISAGREEMENT_IS_NEVER_RENDERED_AS_SUPPORT: Final = (
    "The else level of a comparison is a disagreement, and a trained Bayes factor above one on "
    "it would render as agreed and supporting. A reviewer shown 'agreed' for a field that "
    "differs is shown the opposite of the record. So a disagreement is capped at nought, which "
    "is what cascade.evidence_for already carries a disagreement at."
)

#: What the blocking rules cost.
BLOCKING_DECIDES_WHAT_IS_NEVER_COMPARED: Final = (
    "A pair no blocking rule admits is never scored, however strongly it would have matched. "
    "The rules below admit any shared identifier, a shared postcode, and a shared name key or "
    "name prefix, so a pair of records that differ on all of those is never suggested even when "
    "their names are a trigram match. Widening the rules is how that is fixed, and every widening "
    "is paid for in pairs compared, which is the cost DuckDB is here to carry offline."
)

#: Why training has more than one pass.
EVERY_GROUP_IS_FREE_IN_SOME_TRAINING_RULE: Final = (
    "Splink cannot estimate a comparison from pairs admitted by a rule on that comparison's own "
    "columns: every such pair agrees on it by construction. So the expectation-maximisation "
    "runs once per training rule, and the rules are chosen so every comparison group is free "
    "in at least one of them. A group trained by no pass keeps its declared starting weight for "
    "ever while the report says the model was trained."
)

#: Why a run never replaces the file an earlier run wrote.
A_SUGGESTIONS_FILE_IS_NEVER_OVERWRITTEN: Final = (
    "A suggestions file may be in front of a reviewer. A second run on the same export writing "
    "over it would change the questions under somebody part way through answering them, and a "
    "run on a different export has a different reference and a different file. So the file is "
    "created exclusively and a second run on the same export is refused rather than repeated."
)

# ---------------------------------------------------------------------- the export's shape
#: The table the export holds, one row per source record.
EXPORT_TABLE: Final = "observation"

#: The name the export is attached under, read-only, in the job's working connection.
EXPORT_SCHEMA: Final = "export"

#: The columns that name a record rather than compare one, in the order they are written.
IDENTITY_COLUMNS: Final[tuple[str, ...]] = ("unique_id", "source", "entity", "source_id")

#: The export columns that hold a list rather than a string.
#:
#: `cascade.SQL_PREDICATES` compares the phonetic codes with `&&`, which is an overlap of two
#: arrays in PostgreSQL and in DuckDB alike, so the export carries them as a list of strings.
LIST_COLUMNS: Final[frozenset[str]] = frozenset({"name_dm"})

#: Functions the conditions call that DuckDB does not have, and the cascade function each is.
#:
#: `similarity` is pg_trgm's name, which is the name `cascade.SQL_PREDICATES` is written with,
#: and `cascade.trigram_similarity` is documented as that function. Registering it under that
#: name is what lets the predicate be used unchanged rather than translated into a DuckDB
#: similarity that is a different measure.
REGISTERED_FUNCTIONS: Final[Mapping[str, Callable[[str, str], float]]] = MappingProxyType(
    {"similarity": trigram_similarity}
)

#: The comparisons Splink scores, one tuple per comparison, levels in evaluation order.
#:
#: Written out rather than derived from name prefixes, for the reason `cascade.NAME_FEATURES` is
#: written out. The one group with more than one feature is the three name features
#: `cascade.compare` reports at most one of, in the order it tests them, so Splink's ordered
#: levels reproduce that exclusivity rather than scoring one fact three times. The phonetic
#: feature is its own group because `compare` evaluates it independently of the other three.
COMPARISON_GROUPS: Final[tuple[tuple[Feature, ...], ...]] = (
    (Feature.UEN,),
    (Feature.TAX_ID,),
    (Feature.DOMAIN,),
    (Feature.PHONE,),
    (Feature.EMAIL,),
    (Feature.NAME_EXACT, Feature.NAME_STRIPPED, Feature.NAME_TRIGRAM),
    (Feature.NAME_PHONETIC,),
    (Feature.COUNTRY,),
    (Feature.POSTCODE,),
)

#: A pair is suggested when its total match weight is at least this. See
#: `A_SUGGESTION_IS_A_PAIR_MORE_LIKELY_ONE_THING_THAN_TWO`.
SUGGESTION_FLOOR_WEIGHT: Final = 0.0

#: The weight an agreement is floored at. The smallest positive float, so it renders as WEAK
#: and adds nothing a reviewer could notice. See `AN_AGREEMENT_IS_NEVER_RENDERED_AS_A_DISAGREEMENT`.
AGREEMENT_FLOOR_WEIGHT: Final = math.ulp(0.0)

#: How many leading characters of a name key form a blocking key.
#:
#: `normalise.MIN_KEY_CHARS`, and the relation is the reason rather than the figure: every key
#: `NormalisedName.match_key` releases is at least that long, so every usable name has a whole
#: prefix and no short key is admitted to a block by being entirely its own prefix.
NAME_PREFIX_CHARS: Final = MIN_KEY_CHARS

#: Columns whose equality admits a pair to be compared. See
#: `BLOCKING_DECIDES_WHAT_IS_NEVER_COMPARED`.
BLOCKING_COLUMNS: Final[tuple[str, ...]] = (
    "uen_hash",
    "tax_id_hash",
    "domain_hash",
    "phone_hash",
    "email_hash",
    "name_key",
    "postcode_key",
)

#: The rules the expectation-maximisation passes are blocked on. See
#: `EVERY_GROUP_IS_FREE_IN_SOME_TRAINING_RULE`.
TRAINING_BLOCKING_RULES: Final[tuple[str, ...]] = (
    "l.name_key = r.name_key",
    "l.postcode_key = r.postcode_key",
)

#: The share of true matches the hard-identifier rules are assumed to find, which is what
#: Splink scales their count by to estimate the prior. A judgement and not a measurement: a
#: register number is on most company records a connector holds, and not on all of them.
HARD_IDENTIFIER_RECALL: Final = 0.8

#: The prior an untrained run uses: one pair in ten thousand is a match. A judgement, replaced
#: by an estimate whenever the job trains.
PRIOR_MATCH_PROBABILITY: Final = 1e-4

#: How many random pairs the unmatch probabilities are sampled from, and the seed, so two runs
#: on one export sample the same pairs.
U_SAMPLE_PAIRS: Final = 1_000_000
U_SAMPLE_SEED: Final = 14

#: The component this job runs as, in `brain.ops.wiring.COMPONENTS`.
MATCHER_COMPONENT: Final = "record-matcher"

#: Where the compose file mounts the export, and where suggestions are written. Posix paths
#: because they are paths inside a Linux container whatever machine reads this module, and
#: declared here rather than in the job so a test can hold the compose file to them without
#: importing DuckDB.
DEFAULT_EXPORT: Final = PurePosixPath("/exports/export.duckdb")
DEFAULT_SUGGESTIONS: Final = PurePosixPath("/suggestions")

#: The exit status of a run that was handed no export. Distinct from a failure, and never zero.
EXIT_NO_EXPORT: Final = 3

#: The exit status of a licence check that found a licence the application refuses.
EXIT_LICENCE_REFUSED: Final = 4

#: What the container spends outside DuckDB's own ceiling: the interpreter, pandas, numpy,
#: Splink, this package, and the predictions handed back to Python.
#:
#: **A judgement above one measurement, and the measurement is on the wrong platform.** The
#: one real run peaked at 146 MiB of working set, end to end, over a generated export of 32
#: records, on Windows. Linux has not been measured, and the predictions term grows with the
#: number of pairs suggested, which 32 records says nothing about. 384 leaves more than twice
#: the measured peak for both unknowns, and it is recorded as a judgement so nobody quotes it
#: as a figure.
MATCHER_RESERVE_MIB: Final = 384

#: DuckDB's worker threads. It sizes its pool from the host's cores rather than the cgroup's
#: share, and each thread holds buffers, so an unbounded pool is one buffer set per host core
#: inside a limit written for two.
DUCKDB_THREADS: Final = 2

_COLUMN_RE: Final = re.compile(r"\b([lr])\.([a-z][a-z0-9_]*)\b")
_PLACEHOLDER_RE: Final = re.compile(r"(?<![:\w]):([a-z_][a-z0-9_]*)\b")
_CALL_RE: Final = re.compile(r"\b([a-z_][a-z0-9_]*)\s*\(")


# ------------------------------------------------------------------ columns and conditions
def columns_of(predicate: str) -> frozenset[str]:
    """Every export column a self-join predicate reads, on either side."""
    return frozenset(match.group(2) for match in _COLUMN_RE.finditer(predicate))


def export_columns(predicates: Mapping[Feature, str] = SQL_PREDICATES) -> tuple[str, ...]:
    """The columns an export must hold: the identity columns, then every compared column."""
    compared: set[str] = set()
    for predicate in predicates.values():
        compared |= columns_of(predicate)
    return (*IDENTITY_COLUMNS, *sorted(compared - set(IDENTITY_COLUMNS)))


def duckdb_condition(predicate: str, *, thresholds: Thresholds = DECLARED_THRESHOLDS) -> str:
    """One cascade predicate as a Splink comparison condition.

    Two rewrites and nothing else. The sides become suffixes, and the thresholds the predicate
    binds become the declared figures. A placeholder this does not know is refused rather than
    left in: Splink would pass `:lower` to DuckDB as text and the comparison would fail at run
    time on the first pair, or worse, be parsed as something else.
    """
    bound = {"upper": thresholds.upper, "lower": thresholds.lower}

    def bind(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in bound:
            msg = (
                f"the predicate binds :{name}, which no declared threshold supplies; "
                f"{THE_SETTINGS_ARE_DERIVED_FROM_THE_CASCADE_AND_NOT_WRITTEN_A_SECOND_TIME}"
            )
            raise ResolutionError(msg)
        return repr(float(bound[name]))

    condition = _PLACEHOLDER_RE.sub(bind, predicate)
    return _COLUMN_RE.sub(lambda match: f"{match.group(2)}_{match.group(1)}", condition)


def unregistered_calls(
    predicates: Mapping[Feature, str] = SQL_PREDICATES,
    registered: Mapping[str, Callable[[str, str], float]] = REGISTERED_FUNCTIONS,
) -> tuple[str, ...]:
    """Functions a predicate calls that the job will not register, in name order.

    A predicate calling a PostgreSQL function DuckDB lacks fails on the first pair compared,
    after the export has been read and the training has run, so the job asks this before it
    opens anything.
    """
    called = {match.group(1) for text in predicates.values() for match in _CALL_RE.finditer(text)}
    return tuple(sorted(called - set(registered)))


def null_condition(group: Sequence[Feature], predicates: Mapping[Feature, str]) -> str:
    """The level a pair falls into when either record lacks a column the group compares.

    `cascade.compare` evaluates no feature whose inputs either record lacks, and Splink's null
    level scores nought, which is the same statement: incomparable is not a disagreement.
    """
    columns = sorted({one for feature in group for one in columns_of(predicates[feature])})
    return " OR ".join(f"{one}_l IS NULL OR {one}_r IS NULL" for one in columns)


# --------------------------------------------------------------------------- the groups
def group_gaps(
    groups: Sequence[Sequence[Feature]] = COMPARISON_GROUPS,
    predicates: Mapping[Feature, str] = SQL_PREDICATES,
) -> tuple[str, ...]:
    """Every way the groups stop covering the cascade exactly once.

    A feature in no group is a comparison Splink never scores, so a trained model silently
    lacks evidence the cascade uses. A feature in two groups is one fact scored twice, which is
    how an additive score double-counts. A feature with no predicate has no condition to run.
    """
    findings: list[str] = []
    seen: dict[Feature, int] = {}
    for group in groups:
        if not group:
            findings.append("an empty comparison group has no level to score")
        for feature in group:
            seen[feature] = seen.get(feature, 0) + 1
    findings.extend(
        f"{feature.value} is in no comparison group, so the matcher never scores it"
        for feature in Feature
        if feature not in seen
    )
    findings.extend(
        f"{feature.value} is in {count} comparison groups, so one agreement is scored {count} times"
        for feature, count in sorted(seen.items(), key=lambda item: item[0].value)
        if count > 1
    )
    findings.extend(
        f"{feature.value} has no predicate in the cascade, so it has no condition to run"
        for feature in sorted(seen, key=lambda one: one.value)
        if feature not in predicates
    )
    return tuple(findings)


def group_name(group: Sequence[Feature]) -> str:
    """The Splink output column for a group: its first feature's machine name."""
    return group[0].value


def starting_probabilities(
    group: Sequence[Feature], *, weights: WeightTable = DECLARED_WEIGHTS
) -> tuple[tuple[float, float], ...]:
    """The (m, u) each level starts at: one per feature in order, then the else level.

    Each agreeing level's m is an equal share of `calibration.INITIAL_M` and its u is the value
    that makes `calibration.weight_of(m, u)` the declared weight, so an untrained run agrees with
    `cascade.score` on every agreement. The else level takes what is left of each.

    Refuses a group whose unmatch probabilities leave nothing for the else level. That is a
    declared weight so far below nought that its u exceeds its m by the whole of the remainder,
    and a model starting there has a disagreement impossible among non-matches.
    """
    m_each = INITIAL_M / len(group)
    levels = tuple((m_each, m_each / 2.0 ** weights.weight_for(feature)) for feature in group)
    m_rest = 1.0 - sum(m for m, _ in levels)
    u_rest = 1.0 - sum(u for _, u in levels)
    if u_rest <= 0.0:
        msg = (
            f"the declared weights of {[one.value for one in group]} start the unmatch "
            "probabilities at or above one between them, so the else level would be impossible "
            "among non-matches"
        )
        raise ResolutionError(msg)
    return (*levels, (m_rest, u_rest))


def comparison_for(
    group: Sequence[Feature],
    *,
    weights: WeightTable = DECLARED_WEIGHTS,
    thresholds: Thresholds = DECLARED_THRESHOLDS,
    predicates: Mapping[Feature, str] = SQL_PREDICATES,
) -> dict[str, Any]:
    """One Splink comparison: a null level, one level per feature, then the else level."""
    probabilities = starting_probabilities(group, weights=weights)
    levels: list[dict[str, Any]] = [
        {"sql_condition": null_condition(group, predicates), "is_null_level": True}
    ]
    for feature, (m, u) in zip(group, probabilities, strict=False):
        levels.append(
            {
                "sql_condition": duckdb_condition(predicates[feature], thresholds=thresholds),
                "label_for_charts": feature.value,
                "m_probability": m,
                "u_probability": u,
            }
        )
    m_rest, u_rest = probabilities[-1]
    levels.append(
        {
            "sql_condition": "ELSE",
            "label_for_charts": "else",
            "m_probability": m_rest,
            "u_probability": u_rest,
        }
    )
    return {"output_column_name": group_name(group), "comparison_levels": levels}


def blocking_rules(columns: Sequence[str] = BLOCKING_COLUMNS) -> tuple[str, ...]:
    """The rules that admit a pair to be compared, one per column plus the name prefix."""
    known = set(export_columns())
    unknown = sorted(set(columns) - known)
    if unknown:
        msg = f"blocking column(s) {unknown} are not in the export, so the rule admits nothing"
        raise ResolutionError(msg)
    return (
        *(f"l.{one} = r.{one}" for one in columns),
        f"substr(l.name_key, 1, {NAME_PREFIX_CHARS}) = substr(r.name_key, 1, {NAME_PREFIX_CHARS})",
    )


def deterministic_rules() -> tuple[str, ...]:
    """The rules the prior is estimated from: agreement on a stage-one hard identifier."""
    return tuple(f"l.{kind.value}_hash = r.{kind.value}_hash" for kind in HARD_IDENTIFIERS)


def untrainable_groups(
    rules: Sequence[str] = TRAINING_BLOCKING_RULES,
    groups: Sequence[Sequence[Feature]] = COMPARISON_GROUPS,
    predicates: Mapping[Feature, str] = SQL_PREDICATES,
) -> tuple[str, ...]:
    """The groups no training pass can estimate, because every rule reads one of their columns.

    See `EVERY_GROUP_IS_FREE_IN_SOME_TRAINING_RULE`.
    """
    free: set[str] = set()
    for rule in rules:
        blocked_on = columns_of(rule)
        for group in groups:
            reads = {one for feature in group for one in columns_of(predicates[feature])}
            if not reads & blocked_on:
                free.add(group_name(group))
    return tuple(group_name(group) for group in groups if group_name(group) not in free)


def settings(
    *,
    groups: Sequence[Sequence[Feature]] = COMPARISON_GROUPS,
    weights: WeightTable = DECLARED_WEIGHTS,
    thresholds: Thresholds = DECLARED_THRESHOLDS,
    predicates: Mapping[Feature, str] = SQL_PREDICATES,
) -> dict[str, Any]:
    """The Splink settings document, derived entirely from the cascade.

    Refuses rather than builds when the groups do not cover the cascade exactly once, when a
    predicate calls a function the job will not register, or when some group would never be
    trained. Each of those produces a model that runs, converges and suggests, and is not the
    model the cascade describes.
    """
    problems = [
        *group_gaps(groups, predicates),
        *(
            f"a predicate calls {name}(), which DuckDB lacks and the job does not register"
            for name in unregistered_calls(predicates)
        ),
        *(
            f"no training pass can estimate {name}; {EVERY_GROUP_IS_FREE_IN_SOME_TRAINING_RULE}"
            for name in untrainable_groups(groups=groups, predicates=predicates)
        ),
    ]
    if problems:
        raise ResolutionError("; ".join(problems))
    return {
        "link_type": "dedupe_only",
        "unique_id_column_name": IDENTITY_COLUMNS[0],
        "additional_columns_to_retain": list(IDENTITY_COLUMNS[1:]),
        # True, and not for the values. Measured on the first real run: with it False, Splink
        # 4.0.17 drops the gamma columns as well as the compared values, and the gamma column
        # is the only place a pair's level can be read from. The values stay in the job's
        # in-memory predictions; `suggestion_document` writes references and evidence only.
        "retain_matching_columns": True,
        "retain_intermediate_calculation_columns": True,
        "probability_two_random_records_match": PRIOR_MATCH_PROBABILITY,
        "blocking_rules_to_generate_predictions": list(blocking_rules()),
        "comparisons": [
            comparison_for(group, weights=weights, thresholds=thresholds, predicates=predicates)
            for group in groups
        ],
    }


# ------------------------------------------------------------------ building the export
def export_row(
    observation: Observation,
    *,
    unique_id: str,
    predicates: Mapping[Feature, str] = SQL_PREDICATES,
) -> dict[str, object]:
    """One `cascade.Observation` as the row the export holds for it.

    Built from the observation rather than from a source record, so everything the cascade
    already refused upstream stays refused: identifiers are digests that passed the blocklist,
    and a name whose verdict is not usable has no key and therefore takes part in no
    comparison. Refuses when the row it builds does not have exactly the columns the cascade's
    predicates read, which is what a predicate naming a new column would otherwise become: a
    comparison against a column every row lacks, scored as incomparable for ever.
    """
    key = observation.name.match_key
    row: dict[str, object] = {
        "unique_id": unique_id,
        "source": observation.record.source,
        "entity": observation.record.entity,
        "source_id": observation.record.source_id,
        "name_collapsed": observation.name.collapsed,
        "name_key": key,
        "name_dm": None if key is None else sorted(phonetic_codes(key)),
    }
    for kind in IdentifierKind:
        row[f"{kind.value}_hash"] = observation.identifiers.get(kind)
    for feature, token in observation.fields.items():
        row[f"{feature.value}_key"] = token
    for feature in (Feature.COUNTRY, Feature.POSTCODE):
        row.setdefault(f"{feature.value}_key", None)
    expected = set(export_columns(predicates))
    if set(row) != expected:
        msg = (
            f"an export row would carry {sorted(set(row) - expected)} and lack "
            f"{sorted(expected - set(row))}; the export's columns are the cascade's"
        )
        raise ResolutionError(msg)
    return row


def export_schema_gaps(present: Iterable[str]) -> tuple[str, ...]:
    """The columns an export lacks, in order. Read before anything is compared."""
    have = set(present)
    return tuple(one for one in export_columns() if one not in have)


def run_ref_for(export: Path) -> str:
    """The reference a run on this export writes under: the digest of the file's bytes.

    A digest rather than a time, so a run names what it matched rather than when, and a second
    run on the same export resolves to the same file and is refused by
    `write_suggestions`. Held to `calibration`'s reference grammar, which is what makes it a
    name somebody can quote in a review rather than a word.
    """
    digest = hashlib.sha256()
    with export.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    ref = f"export-{digest.hexdigest()[:16]}"
    if not _REF_RE.match(ref) or len(ref) < MIN_REF_CHARS:  # pragma: no cover - by construction
        msg = f"{ref!r} is not a reference"
        raise ResolutionError(msg)
    return ref


def duckdb_statements(memory_mib: int | None = None) -> tuple[str, ...]:
    """The settings DuckDB is given before it reads a row: its memory ceiling and its threads.

    The ceiling is the component's limit less `MATCHER_RESERVE_MIB`, for the reason the parse
    worker's budget sits below its cgroup: what DuckDB caps is not all the cgroup counts. It
    spills to disk past it rather than failing, which is the behaviour wanted from an offline
    job and not available to a Python heap.
    """
    limit = component(MATCHER_COMPONENT).memory_mib if memory_mib is None else memory_mib
    spare = limit - MATCHER_RESERVE_MIB
    if spare <= 0:
        msg = (
            f"a {limit} MiB container has nothing left for DuckDB once {MATCHER_RESERVE_MIB} "
            "MiB of interpreter and imports are resident"
        )
        raise ResolutionError(msg)
    return (f"SET memory_limit = '{spare}MiB'", f"SET threads = {DUCKDB_THREADS}")


def attach_statement(export: Path) -> str:
    """Attach the export read-only, so the job cannot alter the evidence it was handed.

    DuckDB takes no bound parameter in ATTACH, so the path is quoted here, and a path holding a
    quote is doubled rather than refused: an operator's directory name is not an injection.
    """
    quoted = str(export).replace("'", "''")
    return f"ATTACH '{quoted}' AS {EXPORT_SCHEMA} (READ_ONLY)"


def view_statement() -> str:
    """A view in the working connection over the attached export's table.

    Splink finds an input table's columns by its bare name, and handed
    `export.observation` it found none and generated a SELECT with no columns in it, which
    DuckDB refused as a syntax error. Measured on the first real run rather than assumed. A
    view gives it a bare name, lives in the in-memory connection, and writes nothing to the
    export.
    """
    # Built only from the two module constants above, never from anything a caller passes.
    return f"CREATE VIEW {EXPORT_TABLE} AS SELECT * FROM {EXPORT_SCHEMA}.{EXPORT_TABLE}"  # noqa: S608


# ------------------------------------------------------------- predictions to suggestions
def level_feature(group: Sequence[Feature], gamma: int) -> Feature | None:
    """Which feature a comparison vector value is, or None for the else level.

    Splink numbers a comparison's non-null levels from the top down to nought and gives the
    null level minus one, so with one level per feature and an else level the first feature is
    `len(group)` and the else level is nought. Refuses a value outside that range, including
    minus one, which the caller skips as incomparable before asking.
    """
    if not 0 <= gamma <= len(group):
        msg = f"comparison vector value {gamma} is not a level of {group_name(group)}"
        raise ResolutionError(msg)
    return None if gamma == 0 else group[len(group) - gamma]


def evidence_from(
    row: Mapping[str, Any], groups: Sequence[Sequence[Feature]] = COMPARISON_GROUPS
) -> tuple[Evidence, ...]:
    """One predicted pair's evidence, a line per comparable group, in the cascade's terms.

    An agreeing level is the feature it is, at the log2 of its Bayes factor floored above
    nought; the else level is the group's last feature at that log2 capped at nought, which is
    the feature `cascade.compare` reports as disagreeing for the name group and the only one for
    every other group. An incomparable group contributes no line, as in `cascade.evidence_for`.
    """
    lines: list[Evidence] = []
    for group in groups:
        name = group_name(group)
        gamma = int(row[f"gamma_{name}"])
        if gamma < 0:
            continue
        weight = math.log2(float(row[f"bf_{name}"]))
        feature = level_feature(group, gamma)
        if feature is None:
            lines.append(Evidence(field=group[-1].value, weight=min(weight, 0.0)))
        else:
            lines.append(Evidence(field=feature.value, weight=max(weight, AGREEMENT_FLOOR_WEIGHT)))
    return tuple(sorted(lines, key=lambda one: one.field))


def _record(row: Mapping[str, Any], side: str) -> SourceRef:
    return SourceRef(
        source=str(row[f"source_{side}"]),
        entity=str(row[f"entity_{side}"]),
        source_id=str(row[f"source_id_{side}"]),
    )


def suggestion_id(run_ref: str, left: SourceRef, right: SourceRef) -> str:
    """A stable id for one pair in one run, the same whichever side Splink put each record on."""
    first, second = sorted((left, right), key=SourceRef.sort_key)
    material = json.dumps([run_ref, first.sort_key(), second.sort_key()])
    return f"{run_ref}:{hashlib.sha256(material.encode('utf-8')).hexdigest()[:16]}"


def suggestions_from(
    rows: Iterable[Mapping[str, Any]],
    *,
    run_ref: str,
    groups: Sequence[Sequence[Feature]] = COMPARISON_GROUPS,
) -> tuple[ReviewItem, ...]:
    """Every predicted pair at or above the floor, as a question for a person.

    The floor is applied here even though the job also passes it to Splink, because this is
    the decision and that is an optimisation: a job whose threshold argument was dropped would
    otherwise suggest every pair it blocked. Sorted by the records rather than by weight, for
    the reason `guardrails.review_queue` gives about the order of a queue.
    """
    items: list[ReviewItem] = []
    for row in rows:
        if float(row["match_weight"]) < SUGGESTION_FLOOR_WEIGHT:
            continue
        left, right = sorted((_record(row, "l"), _record(row, "r")), key=SourceRef.sort_key)
        items.append(
            ReviewItem(
                item_id=suggestion_id(run_ref, left, right),
                left=left,
                right=right,
                evidence=evidence_from(row, groups),
            )
        )
    return tuple(sorted(items, key=lambda one: (one.left.sort_key(), one.right.sort_key())))


def suggestion_document(item: ReviewItem) -> dict[str, Any]:
    """One suggestion as a line of the file: the two records and the evidence, and nothing else.

    See `THE_MATCHER_SUGGESTS_AND_NEVER_MERGES` for what is deliberately absent.
    """
    return {
        "item_id": item.item_id,
        "left": dict(zip(("source", "entity", "source_id"), item.left.sort_key(), strict=True)),
        "right": dict(zip(("source", "entity", "source_id"), item.right.sort_key(), strict=True)),
        "evidence": [{"field": one.field, "weight": one.weight} for one in item.evidence],
    }


def write_suggestions(items: Sequence[ReviewItem], directory: Path, run_ref: str) -> Path:
    """Write the suggestions as JSON lines, refusing a file an earlier run already wrote.

    See `A_SUGGESTIONS_FILE_IS_NEVER_OVERWRITTEN`. Written with `\\n` line endings whatever the
    platform, so the file a reviewer's tooling reads is the same bytes wherever it was produced.
    """
    path = directory / f"{run_ref}.jsonl"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            for item in items:
                handle.write(json.dumps(suggestion_document(item), sort_keys=True) + "\n")
    except FileExistsError as exc:
        msg = f"{path.name} already exists. {A_SUGGESTIONS_FILE_IS_NEVER_OVERWRITTEN}"
        raise ResolutionError(msg) from exc
    return path
