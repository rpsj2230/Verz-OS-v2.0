"""The candidate scan: one statement, weights bound to it, and both halves of every pair
filtered before anything is scored.

`tests/unit/test_cascade.py` proves the rendered expression sums to what the Python scorer
sums. These are about the statement built around it, and two of them carry the leaf.

**The weights are data.** The whole of M14.3.6's "plain SQL" is that scoring N candidates costs
one statement rather than N, and the whole of M14.4.4's weekly re-fit surviving that is that a
new weight table is a new argument list rather than a new statement. Both are one assertion:
the SQL text is identical under two different weight tables.

**Both halves or the pair is not there.** A reader who reaches one record and not the other
must not learn that the other exists. The filter is a conjunction over the two aliases inside
the statement, so the refusal is a row that was never produced rather than a row removed from a
result somebody could have counted.

The arithmetic is evaluated in SQLite, for the reason `test_cascade` gives: the parser is then
not this file's opinion about what the expression means. What SQLite cannot stand in for is
named where it is rewritten.

Task ids: M14.3.6
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from typing import Any

import pytest

from brain.core.scope import Clause, Op, Scope
from brain.core.scope_sql import ColumnLayout
from brain.resolution.canonical import IdentifierKind, ResolutionError, SourceRef
from brain.resolution.cascade import (
    DECLARED_THRESHOLDS,
    DECLARED_WEIGHTS,
    WEIGHT_PARAM_PREFIX,
    Feature,
    Observation,
    WeightTable,
    compare,
    phonetic_codes,
    score,
)
from brain.resolution.normalise import normalise_name
from brain.resolution.query import (
    LEFT_PARAM_PREFIX,
    RECORD_KEY_COLUMNS,
    RIGHT_PARAM_PREFIX,
    score_query,
    weight_parameters,
)

TABLE = "er.candidate"

#: A weight table with every figure the same and none of them the declared ones, so a statement
#: that differed between two tables would differ under this one.
FLAT_WEIGHTS = WeightTable(
    version="flat-for-a-test",
    weights=dict.fromkeys(Feature, 2.5),
    calibration_ref="em-2026-09-07",
)

#: The columns the rendered expression names, in the order the harness inserts them.
COMPARISON_COLUMNS = (
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

#: PostgreSQL's array overlap, which SQLite has no parser for. Rewritten into a registered
#: function, and the rewrite is asserted to have found something so a predicate that stops
#: using the operator fails loudly rather than evaluating as absent.
_ARRAY_OVERLAP = "l.name_dm && r.name_dm"
_OVERLAP_CALL = "overlaps(l.name_dm, r.name_dm)"

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def observation(
    name: str,
    *,
    source: str = "hubspot",
    record: str = "1",
    identifiers: Mapping[IdentifierKind, str] | None = None,
    fields: Mapping[Feature, str] | None = None,
) -> Observation:
    return Observation(
        record=SourceRef(source=source, entity="company", source_id=record),
        name=normalise_name(name),
        identifiers=dict(identifiers or {}),
        fields=dict(fields or {}),
    )


def _row(record: Observation) -> list[str | None]:
    """One observation as the columns the statement names.

    `name_dm` is the phonetic code set materialised at write time, which is what
    `cascade.WHAT_WOULD_BREAK_THE_SQL_SHAPE` says the phonetic term assumes.
    """
    key = record.name.match_key
    return [
        record.record.source,
        record.record.entity,
        record.record.source_id,
        record.identifiers.get(IdentifierKind.UEN),
        record.identifiers.get(IdentifierKind.TAX_ID),
        record.identifiers.get(IdentifierKind.DOMAIN),
        record.identifiers.get(IdentifierKind.PHONE),
        record.identifiers.get(IdentifierKind.EMAIL),
        record.name.collapsed,
        key,
        " ".join(sorted(phonetic_codes(key))) if key is not None else None,
        record.fields.get(Feature.COUNTRY),
        record.fields.get(Feature.POSTCODE),
    ]


def _similarity(left: str | None, right: str | None) -> float | None:
    from brain.resolution.cascade import trigram_similarity

    if left is None or right is None:
        return None
    return trigram_similarity(left, right)


def _overlaps(left: str | None, right: str | None) -> bool | None:
    if left is None or right is None:
        return None
    return bool(set(left.split()) & set(right.split()))


def run(records: list[Observation], *, sql: str, params: Mapping[str, Any]) -> list[Any]:
    """Execute the statement over these records and hand back the rows.

    The table is created under a name SQLite can hold, because `er.candidate` would be read as
    a database qualifier there. That substitution is the only difference between what runs here
    and what the caller would send.
    """
    runnable = sql.replace(_ARRAY_OVERLAP, _OVERLAP_CALL)
    assert runnable != sql, "the phonetic predicate no longer uses the array operator"
    runnable = runnable.replace(TABLE, "candidate")

    connection = sqlite3.connect(":memory:")
    try:
        connection.create_function("similarity", 2, _similarity)
        connection.create_function("overlaps", 2, _overlaps)
        columns = ", ".join(f"{one} TEXT" for one in (*RECORD_KEY_COLUMNS, *COMPARISON_COLUMNS))
        connection.execute(f"CREATE TABLE candidate ({columns})")
        placeholders = ", ".join("?" * (len(RECORD_KEY_COLUMNS) + len(COMPARISON_COLUMNS)))
        for record in records:
            connection.execute(
                f"INSERT INTO candidate VALUES ({placeholders})",  # noqa: S608
                _row(record),
            )
        return connection.execute(runnable, dict(params)).fetchall()
    finally:
        connection.close()


ANYWHERE = Scope.unrestricted()


# ------------------------------------------------- the weights are data, not code (M14.3.6)
def test_the_statement_is_one_text_under_every_weight_table() -> None:
    """**The leaf's load-bearing property.** Additive scoring in plain SQL means the weights
    are an input to the query and not part of it.

    A weight rendered into the text makes every re-calibration a different statement:
    prepared statements and plan caches turn over, and the figure a job fitted has become code.
    M14.4.4 schedules that fit weekly, so this is the difference between a new argument list and
    a new query, every week.

    Two tables sharing no figure at all, so a renderer that interpolated anything would produce
    two different texts. The parameters have to differ, or the test would be satisfied by a
    builder that ignored the weights completely.

    Delete this and the next convenient edit writes the weights back into the expression, which
    reads as simpler and is what makes the calibration a deployment."""
    declared = score_query(table=TABLE, scope=ANYWHERE, weights=DECLARED_WEIGHTS)
    flat = score_query(table=TABLE, scope=ANYWHERE, weights=FLAT_WEIGHTS)

    assert declared.sql == flat.sql
    assert declared.params != flat.params
    assert declared.weight_version != flat.weight_version
    assert declared.calibrated is False
    assert flat.calibrated is True


def test_every_weight_the_statement_names_is_one_the_binder_binds() -> None:
    """The renderer writes the placeholder and the binder fills it, and they are two functions
    in two modules.

    A missing parameter is a loud failure at execution, which is the safe direction, but only
    on the day somebody executes it: nothing in this repository does. So the coupling is
    checked here, by reading the placeholders out of the rendered statement and comparing them
    with the keys the binder produces, rather than by trusting one prefix constant used twice.

    Delete this and a feature added to the vocabulary is rendered into the expression and never
    bound, and the whole statement fails the first time it is run against a real database."""
    built = score_query(table=TABLE, scope=ANYWHERE)
    named = set(re.findall(rf":({WEIGHT_PARAM_PREFIX}[a-z_]+)", built.sql))

    assert named == set(weight_parameters())
    assert len(named) == len(Feature)


def test_the_database_computes_the_same_total_the_python_scorer_does() -> None:
    """The statement is only worth having if it agrees with the rule it renders.

    `test_cascade` proves the expression agrees with `score`; this proves the statement built
    around it does, which is a different claim: a WHERE clause that filtered the join wrongly,
    or a self join that paired a record with itself, would leave the expression correct and the
    answer wrong.

    Evaluated rather than read, so the parser is not this file's opinion about what the SQL
    means. Run under both weight tables, because a builder that bound the wrong argument list
    would agree with the Python scorer under the declared weights and not under any other.

    Delete this and the statement can drift from the expression it embeds."""
    left = observation(
        "Acme Trading Pte Ltd",
        identifiers={IdentifierKind.UEN: DIGEST_A},
        fields={Feature.COUNTRY: "sg"},
    )
    right = observation(
        "Acme Trading Limited",
        record="2",
        identifiers={IdentifierKind.UEN: DIGEST_A, IdentifierKind.EMAIL: DIGEST_B},
        fields={Feature.COUNTRY: "sg"},
    )

    for weights in (DECLARED_WEIGHTS, FLAT_WEIGHTS):
        built = score_query(table=TABLE, scope=ANYWHERE, weights=weights)
        rows = run([left, right], sql=built.sql, params=built.params)

        assert len(rows) == 1
        expected = score(compare(left, right).agreed, weights=weights)
        assert rows[0][-1] == pytest.approx(expected)
    assert score(compare(left, right).agreed) > 0.0, "the pair has to score something"


# --------------------------------------------------------- both halves or nothing (M14.6.4)
def test_a_pair_the_reader_reaches_only_one_half_of_is_not_in_the_result() -> None:
    """**A candidate pair is a statement about two records**, so a reader who reaches one of
    them learns from the row that the other exists and resembles it.

    The filter is therefore compiled once per side and conjoined inside the statement. Not
    applied to the results, because a filter applied afterwards is a filter somebody can count
    what it removed, and a count of removed candidates is a count of records the reader may not
    see.

    The sibling is the pair both sides of which the reader reaches, which has to come back:
    a conjunction that returned nothing at all would pass the refusal half on its own.

    Delete this and the scan returns pairs whose far side the reader was never granted."""
    mine = observation("Acme Trading", source="hubspot", record="1")
    theirs = observation("Acme Trading", source="freshdesk", record="2")

    only_hubspot = Scope(clauses=(Clause(field="source", op=Op.EQ, value="hubspot"),))
    built = score_query(table=TABLE, scope=only_hubspot)
    assert run([mine, theirs], sql=built.sql, params=built.params) == []

    second_hubspot = observation("Acme Trading", source="hubspot", record="2")
    rows = run([mine, second_hubspot], sql=built.sql, params=built.params)
    assert len(rows) == 1


def test_the_filter_binds_each_side_under_its_own_parameters() -> None:
    """`CompiledPredicate.and_` refuses to merge two fragments sharing a parameter name, and
    that refusal is what stops one side's value being bound into the other's placeholder.

    It only works if the two compilations use different prefixes, which is asserted here on the
    rendered fragment rather than on the two constants: comparing the constants with each other
    would pass with both of them unused.

    Delete this and the two halves can be compiled under one prefix, which either raises on
    every call or, worse, quietly filters both sides by one side's value."""
    narrow = Scope(clauses=(Clause(field="source", op=Op.EQ, value="hubspot"),))
    built = score_query(table=TABLE, scope=narrow)

    assert f"l.source = :{LEFT_PARAM_PREFIX}0" in built.sql
    assert f"r.source = :{RIGHT_PARAM_PREFIX}0" in built.sql
    assert built.params[f"{LEFT_PARAM_PREFIX}0"] == "hubspot"
    assert built.params[f"{RIGHT_PARAM_PREFIX}0"] == "hubspot"


def test_an_impossible_scope_says_it_is_impossible_rather_than_looking_empty() -> None:
    """An empty result set and a reader entitled to nothing look identical, and they mean
    opposite things: "there are no candidates" is a statement about the estate.

    `CompiledPredicate` carries the flag for exactly this and it is carried through rather than
    dropped, so a caller can tell the two apart without being able to tell anybody else.

    The sibling is the ordinary scope, whose flag is False, so the field is not simply always
    set.

    Delete this and a narrow principal is shown a confident emptiness."""
    contradiction = Scope(
        clauses=(
            Clause(field="source", op=Op.EQ, value="hubspot"),
            Clause(field="source", op=Op.EQ, value="freshdesk"),
        )
    )
    built = score_query(table=TABLE, scope=contradiction)

    assert built.certainly_empty is True
    assert "FALSE" in built.sql
    assert score_query(table=TABLE, scope=ANYWHERE).certainly_empty is False


# ------------------------------------------------------------ the shape of the statement
def test_the_scan_is_one_statement_with_no_round_trip_and_no_subquery() -> None:
    """What the millisecond claim actually rests on: one statement for N candidate pairs.

    A subquery per term, or a second statement, would each turn the scoring into something that
    scales with the candidate set in round trips rather than in rows. The trigram term uses
    pg_trgm's operator, which is an operator with an index behind it rather than a computation,
    and it is the only call in the whole expression.

    Delete this and a term arrives that needs a lookup, which is invisible in a diff and is the
    difference between one query and one query per pair."""
    built = score_query(table=TABLE, scope=ANYWHERE)

    assert ";" not in built.sql
    assert built.sql.upper().count("SELECT") == 1
    assert "UNION" not in built.sql.upper()
    assert "ORDER BY" not in built.sql.upper()


def test_a_record_is_never_compared_with_itself_and_a_pair_appears_once() -> None:
    """A record compared with itself agrees on every feature and scores the maximum, which is
    the single most convincing wrong answer this statement can produce.

    The join is a row comparison over the three key columns, which is strict, so the reflexive
    pair is excluded and each unordered pair is produced once rather than twice. Written as a
    row comparison rather than as three ORs because that spelling is where a parenthesis gets
    dropped.

    Delete this and one duplicated record in the projection becomes a perfect match with
    itself, at the top of any list sorted by score."""
    alone = observation("Acme Trading", record="1")
    built = score_query(table=TABLE, scope=ANYWHERE)

    assert run([alone], sql=built.sql, params=built.params) == []

    other = observation("Acme Trading", record="2")
    assert len(run([alone, other], sql=built.sql, params=built.params)) == 1


def test_a_table_name_that_could_close_a_quote_is_refused() -> None:
    """An identifier cannot be parameterised, so it is constrained rather than quoted: a name
    that cannot contain a quote cannot close one. That is `scope_sql.IDENT_RE`'s own reasoning
    applied to the one identifier this module accepts from a caller.

    The sibling admits a bare name and a schema-qualified one, because refusing everything
    would satisfy the refusal half on its own.

    Delete this and the only caller-supplied identifier in the module is interpolated
    unchecked."""
    for bad in ("er.candidate; DROP TABLE er.link", "ER.Candidate", "er candidate", ""):
        with pytest.raises(ResolutionError, match="table"):
            score_query(table=bad, scope=ANYWHERE)

    assert score_query(table="candidate", scope=ANYWHERE).sql
    assert score_query(table="er.candidate", scope=ANYWHERE).sql


def test_the_scan_reads_a_promoted_column_when_the_layout_says_it_is_one() -> None:
    """The layout is `compile_where`'s and is passed through rather than reimplemented, which
    is what lets the reach filter use an index instead of a jsonb lookup.

    It matters for this surface in particular: a scan over every pair of records is exactly
    where a predicate that cannot use an index turns into a scan, which is
    `ColumnLayout`'s own argument.

    Delete this and the layout can be dropped from the signature, and every reach filter on
    this statement becomes a jsonb extraction."""
    narrow = Scope(clauses=(Clause(field="department", op=Op.EQ, value="maintenance"),))

    promoted = score_query(
        table=TABLE, scope=narrow, layout=ColumnLayout(promoted=frozenset({"department"}))
    )
    assert "l.department = " in promoted.sql

    default = score_query(table=TABLE, scope=narrow)
    assert "l.row_data ->> 'department'" in default.sql


def test_the_threshold_is_bound_and_not_written_into_the_comparison() -> None:
    """The trigram threshold is the other figure M14.3.5's calibration would set, and it is
    data for the same reason the weights are.

    Asserted through the statement rather than by reading `SQL_PREDICATES`, so a term that
    stopped using the placeholder fails here rather than passing on the constant's own text.

    Delete this and a re-calibrated threshold is a new statement, which puts the whole
    prepared-statement argument back where it started."""
    built = score_query(table=TABLE, scope=ANYWHERE, thresholds=DECLARED_THRESHOLDS)

    assert ":upper" in built.sql
    assert built.params["upper"] == DECLARED_THRESHOLDS.upper
    assert str(DECLARED_THRESHOLDS.upper) not in built.sql
