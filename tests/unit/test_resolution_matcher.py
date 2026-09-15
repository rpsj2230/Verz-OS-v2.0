"""The record matcher's decisions, held to the cascade they are derived from.

Everything here runs without Splink or DuckDB, which is the reason `brain.resolution.matcher`
is a module of its own: `docs/needs-rupash.md` item 55 put both packages in an image this suite
never runs in. The assertions are therefore about the cascade on one side and the settings,
rows and files on the other, and wherever a figure could be compared with itself it is compared
with the cascade, `calibration.weight_of` or `brain.ops.wiring` instead.

Task ids: M14.4.1
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from brain.ops.wiring import component
from brain.resolution import matcher
from brain.resolution.calibration import weight_of
from brain.resolution.canonical import IdentifierKind, ResolutionError, SourceRef, identifier_hash
from brain.resolution.cascade import (
    DECLARED_THRESHOLDS,
    DECLARED_WEIGHTS,
    SQL_PREDICATES,
    Feature,
    Observation,
    WeightTable,
    compare,
    phonetic_codes,
    trigram_similarity,
)
from brain.resolution.guardrails import Strength
from brain.resolution.normalise import MIN_KEY_CHARS, normalise_name

PEPPER = "a-test-pepper-and-not-a-secret"


def _observation(name: str, source_id: str, **identifiers: str) -> Observation:
    return Observation(
        record=SourceRef(source="crm", entity="company", source_id=source_id),
        name=normalise_name(name),
        identifiers={
            IdentifierKind(kind): identifier_hash(IdentifierKind(kind), value, pepper=PEPPER)
            for kind, value in identifiers.items()
        },
        fields={Feature.COUNTRY: "sg"},
    )


def _row(weight: float = 1.0, **levels: tuple[int, float]) -> dict[str, Any]:
    """A predicted row as Splink returns it: every group incomparable unless named."""
    row: dict[str, Any] = {
        "match_weight": weight,
        "source_l": "crm",
        "entity_l": "company",
        "source_id_l": "7",
        "source_r": "billing",
        "entity_r": "company",
        "source_id_r": "3",
    }
    for group in matcher.COMPARISON_GROUPS:
        gamma, bf = levels.get(matcher.group_name(group), (-1, 1.0))
        row[f"gamma_{matcher.group_name(group)}"] = gamma
        row[f"bf_{matcher.group_name(group)}"] = bf
    return row


# ------------------------------------------------------------------ the derived settings
def test_every_comparison_condition_is_a_cascade_predicate_with_its_sides_renamed() -> None:
    """**The leaf's own constraint: no second copy of the matching arithmetic.** Every level
    Splink evaluates is `cascade.SQL_PREDICATES` for that feature, with `l.x` spelled `x_l` and
    the threshold bound from `DECLARED_THRESHOLDS`, and nothing of the self-join spelling or an
    unbound placeholder survives into a condition DuckDB would run.

    Delete this and the settings can carry a hand-written condition that agrees with the cascade
    on the day it is written and on no day after."""
    settings = matcher.settings()
    conditions: dict[str, str] = {}
    for comparison in settings["comparisons"]:
        for level in comparison["comparison_levels"]:
            if level.get("is_null_level") or level["sql_condition"] == "ELSE":
                continue
            conditions[level["label_for_charts"]] = level["sql_condition"]

    assert set(conditions) == {feature.value for feature in Feature}
    for feature in Feature:
        condition = conditions[feature.value]
        renamed = re.sub(r"\b([lr])\.([a-z_]+)\b", r"\2_\1", SQL_PREDICATES[feature])
        assert condition == renamed.replace(":upper", repr(DECLARED_THRESHOLDS.upper))
        assert not re.search(r"\b[lr]\.", condition), condition
        assert ":" not in condition, condition
    assert conditions["name_trigram"].endswith(
        f"similarity(name_key_l, name_key_r) >= {DECLARED_THRESHOLDS.upper}"
    )


def test_a_placeholder_no_threshold_supplies_is_refused_and_a_known_one_is_bound() -> None:
    """Splink passes an unbound `:name` to DuckDB as text, which fails on the first pair or is
    read as something else. So an unknown placeholder is refused while the settings are built,
    and the sibling proves the known ones are still bound rather than everything refused.

    Delete this and a predicate gaining a second threshold ships a condition that cannot run."""
    with pytest.raises(ResolutionError, match=":ceiling"):
        matcher.duckdb_condition("similarity(l.name_key, r.name_key) >= :ceiling")

    bound = matcher.duckdb_condition("similarity(l.name_key, r.name_key) < :lower")
    assert bound == f"similarity(name_key_l, name_key_r) < {DECLARED_THRESHOLDS.lower}"


def test_the_one_function_the_conditions_call_is_the_cascades_own_similarity() -> None:
    """pg_trgm's `similarity` is not a DuckDB function, and DuckDB's similarity functions are
    different measures. Registering `cascade.trigram_similarity` under that name is what lets the
    predicate run unchanged, and a predicate calling anything else is refused before the export
    is opened, because otherwise it fails after the training has already run.

    Delete this and the registered function can drift to a DuckDB built-in with the same name
    and a different answer."""
    assert matcher.unregistered_calls() == ()
    assert matcher.REGISTERED_FUNCTIONS["similarity"] is trigram_similarity

    edited = dict(SQL_PREDICATES)
    edited[Feature.NAME_TRIGRAM] = "levenshtein(l.name_key, r.name_key) < 2"
    assert matcher.unregistered_calls(MappingProxyType(edited)) == ("levenshtein",)
    with pytest.raises(ResolutionError, match="levenshtein"):
        matcher.settings(predicates=MappingProxyType(edited))


def test_the_groups_score_every_cascade_feature_exactly_once() -> None:
    """A feature in no group is evidence the cascade uses and the matcher never scores; a
    feature in two is one agreement counted twice. Both are refused, and the declared groups
    have neither.

    Delete this and a feature added to the cascade is silently missing from every trained model."""
    assert matcher.group_gaps() == ()

    without_postcode = matcher.COMPARISON_GROUPS[:-1]
    assert any(
        "postcode is in no comparison group" in one for one in matcher.group_gaps(without_postcode)
    )
    with pytest.raises(ResolutionError, match="postcode"):
        matcher.settings(groups=without_postcode)

    doubled = (*matcher.COMPARISON_GROUPS, (Feature.UEN,))
    assert any("uen is in 2 comparison groups" in one for one in matcher.group_gaps(doubled))
    assert any("empty" in one for one in matcher.group_gaps((*matcher.COMPARISON_GROUPS, ())))


def test_no_two_features_of_one_group_agree_on_the_same_pair() -> None:
    """Splink's levels are a CASE, so a group can only ever report one of its features. That is
    right only if `cascade.compare` never reports two of them together, and this asks
    `compare` rather than trusting the comment that says so.

    The positive half: across the pairs, each of the three name features does agree at least
    once, so the property is not satisfied by pairs that agree on nothing.

    Delete this and a group can be widened to features that co-occur, and the matcher scores
    one fact at a single level while the cascade scores it twice."""
    names = [
        ("Northwind Trading Pte Ltd", "Northwind Trading Pte Ltd"),
        ("Northwind Trading Pte Ltd", "Northwind Trading"),
        ("Northwind Trading", "Northwind Tradings"),
        ("Northwind Trading", "Kestrel Analytics"),
        ("Blue Harbour Logistics", "BLUE HARBOUR LOGISTICS"),
    ]
    seen: set[Feature] = set()
    for index, (left, right) in enumerate(names):
        agreed = compare(
            _observation(left, f"{index}a", domain="a.example"),
            _observation(right, f"{index}b", domain="a.example"),
        ).agreed
        seen |= agreed
        for group in matcher.COMPARISON_GROUPS:
            assert len(agreed & set(group)) <= 1, (left, right, sorted(agreed & set(group)))

    assert {Feature.NAME_EXACT, Feature.NAME_STRIPPED, Feature.NAME_TRIGRAM} <= seen


def test_an_untrained_model_scores_every_agreement_at_its_declared_weight() -> None:
    """The starting model is the cascade's. Each agreeing level starts at the m and u whose
    `calibration.weight_of` is that feature's declared weight, and each comparison's levels sum
    to one on both sides, so a `--declared-only` run is comparable with `cascade.score`.

    Asserted against `DECLARED_WEIGHTS` and `weight_of`, neither of which this module defines.

    Delete this and the starting values can be Splink's defaults, which is a different model
    from the one the cascade documents, used whenever training is skipped."""
    for group in matcher.COMPARISON_GROUPS:
        levels = matcher.starting_probabilities(group)
        assert len(levels) == len(group) + 1
        for feature, (m, u) in zip(group, levels, strict=False):
            assert math.isclose(weight_of(m, u), DECLARED_WEIGHTS.weight_for(feature), abs_tol=1e-9)
        assert math.isclose(sum(m for m, _ in levels), 1.0)
        assert math.isclose(sum(u for _, u in levels), 1.0)


def test_declared_weights_that_leave_no_room_for_a_disagreement_are_refused() -> None:
    """A weight below nought starts u above m, and three of them in one group can start the
    unmatch probabilities past one between them, so the else level would begin at or below
    nought among non-matches.

    Asserted at the boundary rather than far from it, because a mutation run found the first
    version of this test used weights of minus twenty: the remainder was then so far below
    nought that a guard refusing only below minus one still refused it. So the three name
    features are given the weight that starts each u at 0.34, leaving the else level minus 0.02,
    which must be refused; and the sibling starts each at 0.33, leaving 0.01, which must not.

    Delete this and such a table starts Splink at a model where disagreeing is impossible."""
    names = matcher.COMPARISON_GROUPS[5]
    m_each = 0.9 / len(names)

    def table(u_each: float) -> WeightTable:
        weights = dict(DECLARED_WEIGHTS.weights)
        weights.update(dict.fromkeys(names, math.log2(m_each / u_each)))
        return WeightTable(version="a-test-table", weights=MappingProxyType(weights))

    with pytest.raises(ResolutionError, match="impossible"):
        matcher.starting_probabilities(names, weights=table(0.34))

    levels = matcher.starting_probabilities(names, weights=table(0.33))
    assert math.isclose(levels[-1][1], 0.01, abs_tol=1e-9)


def test_every_group_is_trained_by_some_pass_and_one_pass_would_leave_names_untrained() -> None:
    """A pass cannot estimate a comparison its own rule reads, because every pair it admits
    agrees there by construction. The declared rules leave every group free in at least one.

    The refusal sibling is the single pass somebody would write first, blocked on the name key:
    it trains the identifiers and never the two name groups.

    Delete this and a model reported as trained keeps its declared name weights for ever."""
    assert matcher.untrainable_groups() == ()

    assert matcher.untrainable_groups(rules=("l.name_key = r.name_key",)) == (
        "name_exact",
        "name_phonetic",
    )


def test_blocking_admits_pairs_only_on_export_columns_and_names_by_a_whole_prefix() -> None:
    """A blocking rule on a column the export lacks admits nothing and is silent about it. And
    the prefix rule is only a prefix for keys at least as long as it, which is why its length
    is `normalise.MIN_KEY_CHARS`: a key one shorter is not usable and never reaches a block.

    Delete this and the prefix can be lengthened past the shortest usable key, and short names
    fall out of every block."""
    rules = matcher.blocking_rules()
    assert "l.name_key = r.name_key" in rules
    assert matcher.NAME_PREFIX_CHARS == MIN_KEY_CHARS
    assert normalise_name("A" * MIN_KEY_CHARS).match_key is not None
    assert normalise_name("A" * (MIN_KEY_CHARS - 1)).match_key is None

    with pytest.raises(ResolutionError, match="region_key"):
        matcher.blocking_rules(("name_key", "region_key"))


# ----------------------------------------------------------------------- the export's rows
def test_an_export_row_carries_exactly_the_columns_the_cascade_compares() -> None:
    """A row is built from an `Observation`, so the refusals upstream stay made: identifiers are
    digests, and a name that may not be matched on has no key and no phonetic codes, and so
    takes part in no comparison.

    Delete this and the export can carry a raw identifier or a key for an unusable name, and
    DuckDB joins on it."""
    usable = _observation("Northwind Trading Pte Ltd", "1", domain="northwind.example")
    row = matcher.export_row(usable, unique_id="0")

    assert set(row) == set(matcher.export_columns())
    assert row["domain_hash"] == usable.identifiers[IdentifierKind.DOMAIN]
    assert row["uen_hash"] is None
    assert row["name_key"] == usable.name.match_key
    assert row["name_dm"] == sorted(phonetic_codes(str(usable.name.match_key)))
    assert (row["source"], row["entity"], row["source_id"]) == usable.record.sort_key()

    unusable = matcher.export_row(_observation("Pte Ltd", "2"), unique_id="1")
    assert unusable["name_key"] is None
    assert unusable["name_dm"] is None


def test_an_export_row_is_refused_when_a_predicate_reads_a_column_no_row_can_fill() -> None:
    """A predicate gaining a column would otherwise be a comparison against a column every row
    lacks, scored as incomparable across the estate with every run succeeding.

    Delete this and the export and the cascade can disagree about their columns in silence."""
    edited = dict(SQL_PREDICATES)
    edited[Feature.POSTCODE] = "l.postcode_key = r.postcode_key AND l.region_key = r.region_key"

    with pytest.raises(ResolutionError, match="region_key"):
        matcher.export_row(
            _observation("Northwind Trading", "1"),
            unique_id="0",
            predicates=MappingProxyType(edited),
        )


def test_an_export_lacking_a_compared_column_is_named() -> None:
    """The check the job makes before it compares anything, with its positive half.

    Delete this and `export_schema_gaps` can return nothing for every export."""
    columns = matcher.export_columns()

    assert matcher.export_schema_gaps(columns) == ()
    assert matcher.export_schema_gaps(one for one in columns if one != "postcode_key") == (
        "postcode_key",
    )


def test_the_export_is_attached_read_only_and_a_quote_in_its_path_is_doubled() -> None:
    """The job is handed evidence and must not be able to change it; and an operator's directory
    name is a path, not an injection, so a quote in it is doubled rather than refused.

    Delete this and the attach can lose `READ_ONLY`, and Splink's working tables are written
    into the export."""
    statement = matcher.attach_statement(Path("exports") / "it's.duckdb")

    assert statement.endswith(f"AS {matcher.EXPORT_SCHEMA} (READ_ONLY)")
    assert "it''s.duckdb" in statement
    assert matcher.view_statement().split() == [
        "CREATE",
        "VIEW",
        matcher.EXPORT_TABLE,
        "AS",
        "SELECT",
        "*",
        "FROM",
        f"{matcher.EXPORT_SCHEMA}.{matcher.EXPORT_TABLE}",
    ]


def test_duckdb_is_capped_below_the_component_by_the_reserve_and_refuses_no_room() -> None:
    """The second cap. DuckDB spills past its ceiling rather than failing, so the ceiling has to
    sit below the cgroup by what Python holds outside it, and a component too small for the
    reserve is refused rather than given a ceiling of nought or less.

    Asserted against the component `brain.ops.wiring` declares, not a figure written here.

    Delete this and the ceiling can be the whole container, which DuckDB fills and the kernel
    then kills."""
    limit = component(matcher.MATCHER_COMPONENT).memory_mib
    spare = limit - matcher.MATCHER_RESERVE_MIB

    assert 0 < spare < limit
    assert matcher.duckdb_statements() == (
        f"SET memory_limit = '{spare}MiB'",
        f"SET threads = {matcher.DUCKDB_THREADS}",
    )
    with pytest.raises(ResolutionError, match="nothing left"):
        matcher.duckdb_statements(matcher.MATCHER_RESERVE_MIB)


# --------------------------------------------------------------- predictions to questions
def test_levels_are_read_from_the_top_down_and_an_impossible_value_is_refused() -> None:
    """Splink numbers non-null levels from the top down to nought. Reading them the other way
    round names the trigram level for an exact name match, which is the weakest name evidence
    reported for the strongest.

    Delete this and the mapping can be reversed with every other unit test green; only the real
    run against `cascade.compare` would say so."""
    names = matcher.COMPARISON_GROUPS[5]

    assert matcher.level_feature(names, 3) is Feature.NAME_EXACT
    assert matcher.level_feature(names, 2) is Feature.NAME_STRIPPED
    assert matcher.level_feature(names, 1) is Feature.NAME_TRIGRAM
    assert matcher.level_feature(names, 0) is None
    for impossible in (-1, 4):
        with pytest.raises(ResolutionError, match="not a level"):
            matcher.level_feature(names, impossible)


def test_a_pair_at_the_floor_is_suggested_and_one_just_below_it_is_not() -> None:
    """**The floor is the decision, and it is here rather than only in Splink's argument.** A
    pair as likely one company as two is asked about; one the model believes is two is not.

    Delete this and a job whose threshold argument was dropped suggests every pair it blocked."""
    rows = [
        _row(weight=matcher.SUGGESTION_FLOOR_WEIGHT, domain=(1, 16.0)),
        {**_row(weight=-0.001, domain=(1, 16.0)), "source_id_l": "8"},
    ]

    items = matcher.suggestions_from(rows, run_ref="export-0123456789abcdef")

    assert len(items) == 1
    assert items[0].right.source_id == "7"


def test_an_agreement_is_never_rendered_as_a_disagreement() -> None:
    """Training can measure an agreement as worth nothing, and nought renders as "did not
    agree". So an agreeing level is floored just above nought, which renders as agreed.

    Delete this and a reviewer is told two fields differ when they are identical."""
    (item,) = matcher.suggestions_from([_row(domain=(1, 0.5))], run_ref="export-0123456789abcdef")
    (line,) = item.evidence

    assert line.field == "domain"
    assert line.weight == matcher.AGREEMENT_FLOOR_WEIGHT
    assert line.strength is Strength.WEAK
    assert item.explain()[0].startswith("domain agreed")


def test_a_disagreement_is_never_rendered_as_support_and_an_incomparable_group_says_nothing() -> (
    None
):
    """The else level of the name group is the trigram disagreeing, as `cascade.compare` reports
    it, and a trained factor above one on it is capped at nought. A group either record lacks
    has no line at all, as in `cascade.evidence_for`.

    Delete this and a reviewer is shown "agreed" for a name that differs."""
    (item,) = matcher.suggestions_from(
        [_row(name_exact=(0, 4.0), domain=(1, 16.0))], run_ref="export-0123456789abcdef"
    )
    by_field = {line.field: line for line in item.evidence}

    assert set(by_field) == {"domain", "name_trigram"}
    assert by_field["name_trigram"].weight == 0.0
    assert by_field["name_trigram"].strength is Strength.AGAINST
    assert by_field["domain"].weight == math.log2(16.0)


def test_a_suggestion_names_two_records_and_its_evidence_and_nothing_to_merge_on() -> None:
    """**It suggests and never merges.** The line a file holds is the two records and the
    evidence. No total, no probability and no confidence, because each is a number a later step
    would threshold into a link without a person.

    Delete this and `match_probability` is added to the file for convenience, and the first
    script that reads it merges everything above 0.99."""
    (item,) = matcher.suggestions_from([_row(domain=(1, 16.0))], run_ref="export-0123456789abcdef")
    document = matcher.suggestion_document(item)

    assert set(document) == {"item_id", "left", "right", "evidence"}
    assert all(set(line) == {"field", "weight"} for line in document["evidence"])
    assert set(document["left"]) == {"source", "entity", "source_id"}
    text = json.dumps(document)
    for absent in ("match_weight", "match_probability", "confidence", "merge", "link"):
        assert absent not in text


def test_one_pair_has_one_id_whichever_side_splink_put_each_record_on() -> None:
    """Splink's left and right are an accident of the unique ids. The id and the order of the
    two records are not, so a reviewer's answer to a question survives the next run.

    Delete this and the same pair is asked twice under two ids."""
    forward = _row(domain=(1, 16.0))
    swapped = {
        **forward,
        **{f"{name}_l": forward[f"{name}_r"] for name in ("source", "entity", "source_id")},
        **{f"{name}_r": forward[f"{name}_l"] for name in ("source", "entity", "source_id")},
    }

    (one,) = matcher.suggestions_from([forward], run_ref="export-0123456789abcdef")
    (two,) = matcher.suggestions_from([swapped], run_ref="export-0123456789abcdef")

    assert one == two
    assert one.left.source == "billing"


def test_a_suggestions_file_is_written_once_and_a_second_run_is_refused(tmp_path: Path) -> None:
    """A file may be in front of a reviewer, so a run never replaces it. The positive half is
    the file itself: one JSON line per item, with `\\n` endings on every platform.

    Delete this and a re-run changes the questions under somebody answering them."""
    items = matcher.suggestions_from(
        [_row(domain=(1, 16.0)), {**_row(domain=(1, 16.0)), "source_id_l": "9"}],
        run_ref="export-0123456789abcdef",
    )

    written = matcher.write_suggestions(items, tmp_path, "export-0123456789abcdef")

    assert written.read_bytes().count(b"\n") == 2
    assert b"\r\n" not in written.read_bytes()
    with pytest.raises(ResolutionError, match="already exists"):
        matcher.write_suggestions(items, tmp_path, "export-0123456789abcdef")


def test_a_run_is_named_by_the_bytes_of_its_export(tmp_path: Path) -> None:
    """A reference names what was matched rather than when, so the same export resolves to the
    same file, which is how a second run on it is refused, and a different export does not.

    Delete this and the reference can become a timestamp, and every re-run writes a fresh file
    of the same questions."""
    first = tmp_path / "a.duckdb"
    second = tmp_path / "b.duckdb"
    again = tmp_path / "c.duckdb"
    first.write_bytes(b"one export")
    again.write_bytes(b"one export")
    second.write_bytes(b"another export")

    assert matcher.run_ref_for(first) == matcher.run_ref_for(again)
    assert matcher.run_ref_for(first) != matcher.run_ref_for(second)
    assert re.fullmatch(r"export-[0-9a-f]{16}", matcher.run_ref_for(first))


def test_a_group_is_incomparable_when_either_record_lacks_any_column_it_reads() -> None:
    """Splink's null level scores nought, which is `cascade.compare` evaluating nothing for a
    pair missing an input. The level has to cover every column the group reads, on both sides,
    joined by OR: joined by AND, a record with a key and no phonetic codes is compared as though
    it had both, and every such pair disagrees.

    Asserted as the whole expression, because a condition that merely mentions the columns is
    satisfied by the wrong connective.

    Delete this and the null level can narrow to one column, and incomparable pairs are scored
    as disagreements across the estate."""
    phonetic = matcher.null_condition((Feature.NAME_PHONETIC,), SQL_PREDICATES)
    names = matcher.null_condition(matcher.COMPARISON_GROUPS[5], SQL_PREDICATES)

    assert phonetic == (
        "name_dm_l IS NULL OR name_dm_r IS NULL OR name_key_l IS NULL OR name_key_r IS NULL"
    )
    assert names == (
        "name_collapsed_l IS NULL OR name_collapsed_r IS NULL OR "
        "name_key_l IS NULL OR name_key_r IS NULL"
    )


def test_an_id_is_the_same_whichever_order_the_records_are_given_in() -> None:
    """`suggestions_from` sorts the two records before it asks for an id, so the symmetry of
    `suggestion_id` itself is invisible through it. Asked directly, because the next caller may
    not sort first.

    Delete this and `suggestion_id` can depend on argument order with every other test green."""
    left = SourceRef(source="crm", entity="company", source_id="1")
    right = SourceRef(source="billing", entity="company", source_id="2")

    assert matcher.suggestion_id("export-0123456789abcdef", left, right) == matcher.suggestion_id(
        "export-0123456789abcdef", right, left
    )
    assert matcher.suggestion_id("export-0123456789abcdef", left, right) != matcher.suggestion_id(
        "export-fedcba9876543210", left, right
    )


def test_the_prior_is_estimated_from_the_hard_identifiers_and_never_from_an_email() -> None:
    """Splink scales the pairs a deterministic rule finds by the assumed recall to estimate how
    often two random records match. An email is not a hard identifier, because a shared mailbox
    identifies nobody, and a rule on it would count every pair sharing accounts@ as a match.

    Asserted against the identifier kinds rather than against the function's own output.

    Delete this and the rules can be widened to every identifier, which inflates the prior and
    with it every suggestion's weight."""
    rules = matcher.deterministic_rules()

    assert "l.email_hash = r.email_hash" not in rules
    assert {"l.uen_hash = r.uen_hash", "l.tax_id_hash = r.tax_id_hash"} <= set(rules)
    assert len(rules) == len(IdentifierKind) - 1
