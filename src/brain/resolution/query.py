"""The additive score as a statement the database evaluates, with the weights bound to it
rather than written into it.

`brain.resolution.cascade` owns the scoring rule: one weight per feature, one comparison per
weight, and a total that is a sum. `sql_score_expression` renders that rule as SQL and this is
what wraps it into something a caller can execute, which is the half M14.3.6 asks for and the
half the cascade deliberately does not have, because a module that built a statement would be a
module that knew a table name.

**The weights are parameters, and that is the whole difference between data and code.** A
rendered expression carrying `THEN 4.0` is a different statement for every weight table: the
text changes when the weekly calibration lands, every prepared statement and every plan cache
is invalidated with it, and the weight has become part of the query rather than an input to it.
Bound as `:w_domain`, the text is one text under every weight table the system will ever hold,
and re-calibration is a different argument list on the same prepared statement. That is what
makes the millisecond claim survive M14.4's schedule. See
`A_WEIGHT_IN_THE_QUERY_TEXT_IS_A_STATEMENT_PER_CALIBRATION`.

**The reach predicate is compiled by `brain.core.scope_sql.compile_where` and not by anything
here.** That function is one of exactly four names `tests/invariants/test_single_implementation`
holds to a single definition, and the reasons are its own: LIKE escaping, the difference between
an IN over a tuple and an IN over a string, and the gap between an empty predicate and an
impossible one. A scoring query is precisely where a second copy would be written, because the
scoring half already renders SQL and adding twenty lines of WHERE feels like the same job. See
`THE_REACH_FILTER_IS_COMPILED_ONCE_AND_NOT_HERE`.

**It is compiled twice, once per side, and the two are conjoined.** A candidate pair is a
statement about two records, so a reader who reaches one of them and not the other must not see
the pair at all: not scored low, not returned with the far side blank, not returned. That is
`guardrails.BOTH_HALVES_OR_THE_ITEM_IS_NOT_THERE` expressed where the rows are, and it is a
conjunction over two aliases rather than a filter applied afterwards, because a filter applied
afterwards is a filter somebody can count what it removed. See
`BOTH_SIDES_OR_THE_PAIR_IS_NOT_IN_THE_RESULT`.

**An impossible scope compiles to FALSE and says so on the result.** `CompiledPredicate`
carries `certainly_empty` for exactly this, and it is carried through rather than dropped: a
caller that cannot tell "you may see nothing" from "there is nothing here" will render the
second, which is a statement about the estate made to somebody entitled to no part of it.

**What the millisecond claim is and is not.** It is that scoring N candidate pairs costs one
statement rather than N: no round trip per pair, no per-pair Python, and nothing fitted loaded
into the request process. It is not a claim about the join that produces the candidates. There
is no blocking pass in this repository, `calibration.OFFLINE_TOOLING` records that as the
largest gap in M14.4, and an unblocked self join is every record against every other however
cheap each term is. See `THE_COST_CLAIM_IS_ABOUT_THE_SCORING_AND_NOT_ABOUT_THE_JOIN`.

**None of these columns exists.** `cascade.SQL_PREDICATES` says so about the comparison columns
and the same is true of the key columns here: no migration in this repository creates a table
this statement could run against, no pg_trgm extension is installed, and nothing has executed
it against PostgreSQL. What has been executed is the arithmetic, in SQLite, against the Python
scorer, which is what makes the agreement between the two halves a measurement rather than a
reading. See `NOTHING_HAS_RUN_THIS_AGAINST_POSTGRES`.

Rejected: rendering the whole thing in `cascade`. That module states, in its own scope note,
that nothing in it opens a connection or knows a table, and a statement needs a table name. The
split is the same one `brain.ops.limits` and `brain.ops.limit_store` draw, for the same reason:
the rule is testable without a server precisely because it does not know about one.

Rejected: an ORDER BY on the score with a LIMIT, which is how a candidate scan is usually
written. Ordering by evidence strength is what `guardrails.review_queue` refuses for the queue,
and a bound on the scan belongs to the candidate generation that decides which pairs are
compared at all. Adding one here would put a bound on a scan whose shape nothing has decided.

Scope: domain logic. Nothing here opens a connection, reads a clock or binds a parameter to a
driver. It emits a statement and its arguments as data, exactly as `scope_sql` does.

Task ids: M14.3.6
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Final

from brain.core.scope import Scope
from brain.core.scope_sql import ColumnLayout, CompiledPredicate, compile_where
from brain.resolution.canonical import ResolutionError
from brain.resolution.cascade import (
    DECLARED_THRESHOLDS,
    DECLARED_WEIGHTS,
    WEIGHT_PARAM_PREFIX,
    Feature,
    Thresholds,
    WeightTable,
    sql_score_expression,
)

# ------------------------------------------------------------------ written-down reasons
#: Why a weight is bound and never rendered.
A_WEIGHT_IN_THE_QUERY_TEXT_IS_A_STATEMENT_PER_CALIBRATION: Final = (
    "A CASE WHEN carrying THEN 4.0 is a different statement from one carrying THEN 4.3, so a "
    "weight written into the text makes every re-calibration a new query: prepared statements "
    "are invalidated, plan caches turn over, and the figure a calibration job fitted has "
    "become part of the code it was supposed to be an input to. Bound as a parameter the text "
    "is one text for every weight table the system will ever hold, and the weekly job M14.4.4 "
    "schedules changes an argument list rather than a statement. This is also what makes the "
    "two halves comparable: the same expression is evaluated under the declared weights and "
    "under a fitted export, so a test can hold the SQL total against the Python total under "
    "both without the text moving underneath it."
)

#: Why the WHERE clause is not built here.
THE_REACH_FILTER_IS_COMPILED_ONCE_AND_NOT_HERE: Final = (
    "brain.core.scope_sql.compile_where is one of the names held to a single definition, and "
    "the reasons are its own: a prefix containing an underscore narrows in Python and widens "
    "in SQL unless the LIKE escape is right, an IN over a string becomes an IN over its "
    "characters, and an empty predicate and an impossible one compile to opposite meanings. A "
    "scoring query is exactly where the second copy gets written, because this file already "
    "renders SQL and a WHERE clause looks like the same job. It is not the same job. The "
    "scoring half decides what a pair is worth and the filter decides whether the reader may "
    "know the pair exists, and only one of those is a permission."
)

#: Why the filter is a conjunction over two aliases.
BOTH_SIDES_OR_THE_PAIR_IS_NOT_IN_THE_RESULT: Final = (
    "A candidate pair is a statement about two records. A reader who reaches one of them "
    "learns, from the existence of the row, that the other one exists and is similar enough "
    "to be a candidate, which is a disclosure about a record they were not granted. So the "
    "predicate is compiled once per side and conjoined, and the conjunction is inside the "
    "statement rather than applied to its results: a filter applied afterwards is a filter "
    "somebody can count what it removed, and a count of removed candidates is a count of "
    "records the reader may not see. This is guardrails.BOTH_HALVES_OR_THE_ITEM_IS_NOT_THERE "
    "expressed where the rows are, and it is the same rule rather than a second one because "
    "the queue filter runs on ReviewItems and this runs on rows that have not become items."
)

#: What the leaf's cost phrase covers.
THE_COST_CLAIM_IS_ABOUT_THE_SCORING_AND_NOT_ABOUT_THE_JOIN: Final = (
    "M14.3.6 asks for millisecond online cost and this delivers one part of it: scoring N "
    "candidate pairs is one statement rather than N, with no per-pair round trip, no per-pair "
    "Python and nothing fitted loaded into the request process. It says nothing about how the "
    "N candidates were chosen. There is no blocking pass in this repository, "
    "calibration.OFFLINE_TOOLING records that as the largest gap in M14.4, and an unblocked "
    "self join is every record against every other regardless of how cheap each term is. "
    "Claiming the cost of the scoring is honest; claiming the cost of the query would not be."
)

#: The gap this module does not close, kept as a constant so it has to be deleted.
NOTHING_HAS_RUN_THIS_AGAINST_POSTGRES: Final = (
    "No migration in this repository creates a table with these columns, the pg_trgm extension "
    "is not installed by anything here, and no deployment has executed this statement. What "
    "has been executed is the arithmetic: the rendered expression is evaluated in SQLite "
    "against the Python scorer, over pairs chosen to hit every branch, which is what makes the "
    "agreement between the two halves a measurement rather than a reading. The parts that "
    "SQLite cannot stand in for are the trigram operator's index and the array overlap, and "
    "both are named where the test rewrites them."
)


# ------------------------------------------------------------------------ the vocabulary
#: The three columns that name a record, spelled as `proj.record` and `er.link` spell them.
#:
#: Written as the same three names rather than a synthetic row id, for the reason
#: `brain.tables.resolution` gives about its own copy: this triple exists to join to
#: `proj.record`, and a join whose columns are named differently on the two sides is a join
#: somebody eventually writes wrong. They are also `canonical.SourceRef`'s three fields, which
#: is what lets a returned row become a `SourceRef` without a mapping table in between.
RECORD_KEY_COLUMNS: Final[tuple[str, ...]] = ("source", "entity", "source_id")

#: The alias each side of the self join carries. `cascade.SQL_PREDICATES` is written against
#: exactly these two letters, so they are constants here rather than parameters: a caller
#: choosing its own aliases would produce a WHERE clause that referred to tables the score
#: expression did not.
LEFT_ALIAS: Final = "l"
RIGHT_ALIAS: Final = "r"

#: The parameter prefix each half of the reach filter binds under. Distinct, because
#: `CompiledPredicate.and_` refuses to merge two fragments that share a parameter name, and
#: that refusal is the guard against one side's value being bound into the other's placeholder.
LEFT_PARAM_PREFIX: Final = "lreach"
RIGHT_PARAM_PREFIX: Final = "rreach"

#: What the upper trigram threshold binds under. Named by `cascade.SQL_PREDICATES` itself,
#: which is why it is read from there rather than declared twice.
THRESHOLD_PARAM: Final = "upper"

#: A table this statement may be built over: a bare name or a schema-qualified one. Identifiers
#: cannot be parameterised, so they are constrained rather than quoted, which is the reasoning
#: `scope_sql.IDENT_RE` gives for its own.
_TABLE_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,62}(?:\.[a-z][a-z0-9_]{0,62})?$")


def weight_parameters(weights: WeightTable = DECLARED_WEIGHTS) -> dict[str, float]:
    """Every weight as a bound parameter, keyed the way the rendered expression names it.

    Built from `Feature` rather than from the table's own keys, so a table that somehow held a
    key the vocabulary does not have would bind nothing for it and the statement would fail on
    a missing parameter rather than score it at whatever the driver defaults to.
    `WeightTable.weight_for` refuses a feature it has no weight for, which is the same refusal
    one layer down.
    """
    return {f"{WEIGHT_PARAM_PREFIX}{one.value}": weights.weight_for(one) for one in Feature}


@dataclass(frozen=True)
class ScoreQuery:
    """One statement, its arguments, and the two facts the statement cannot carry.

    `weight_version` and `calibrated` are here rather than in a SQL comment on purpose. A
    comment naming the weight table would make the text differ between two tables, which is the
    property this whole module exists to remove; carried as fields they travel with the result
    and can be written onto a link, which is where `canonical.Link` wants them.

    `certainly_empty` is `CompiledPredicate`'s flag, carried through rather than dropped: a
    caller that cannot tell an impossible scope from an empty table will render the second, and
    "there are no candidates" said to somebody entitled to no part of the estate is a statement
    about the estate.

    There is no field here for how many rows were filtered out, and there must not be one.
    """

    sql: str
    params: Mapping[str, Any]
    weight_version: str
    calibrated: bool
    certainly_empty: bool = False


def _reach_predicate(scope: Scope, layout: ColumnLayout) -> CompiledPredicate:
    """The reach filter for both sides of the join, conjoined.

    Two compilations of one scope against two aliases, combined with `CompiledPredicate.and_`
    so the parameter-collision refusal in that method is what guarantees the two halves cannot
    bind into each other. See `BOTH_SIDES_OR_THE_PAIR_IS_NOT_IN_THE_RESULT`.
    """
    left = compile_where(scope, replace(layout, alias=LEFT_ALIAS), param_prefix=LEFT_PARAM_PREFIX)
    right = compile_where(
        scope, replace(layout, alias=RIGHT_ALIAS), param_prefix=RIGHT_PARAM_PREFIX
    )
    return left.and_(right)


def score_query(
    *,
    table: str,
    scope: Scope,
    weights: WeightTable = DECLARED_WEIGHTS,
    thresholds: Thresholds = DECLARED_THRESHOLDS,
    layout: ColumnLayout | None = None,
) -> ScoreQuery:
    """The candidate scan: every visible pair with its additive score (M14.3.6).

    One statement. The score is `cascade.sql_score_expression`, which renders the same weight
    table `cascade.score` sums, so there is one scoring rule and this module does not hold a
    second copy of it. The filter is `compile_where`, compiled once per side, for the same
    reason in the permission direction.

    `table` is required and has no default. A default would be a table name this repository
    does not create, written where a reader would take it for one that exists; the columns are
    already invented and saying so once is enough. See `NOTHING_HAS_RUN_THIS_AGAINST_POSTGRES`.

    The join condition is a row comparison over the three key columns, which yields each
    unordered pair exactly once and never a record against itself. Written as a row comparison
    rather than as three ORs because the three-OR spelling is where somebody eventually drops a
    parenthesis and turns a strict ordering into one that admits the reflexive pair, and a
    record compared against itself agrees on every feature and scores the maximum.
    """
    if not _TABLE_RE.match(table):
        msg = (
            f"{table!r} is not a table this statement may be built over. An identifier cannot "
            "be parameterised, so it is constrained rather than quoted: a name that cannot "
            "contain a quote cannot close one"
        )
        raise ResolutionError(msg)

    columns = layout if layout is not None else ColumnLayout(promoted=frozenset(RECORD_KEY_COLUMNS))
    reach = _reach_predicate(scope, columns)

    left_key = ", ".join(f"{LEFT_ALIAS}.{one}" for one in RECORD_KEY_COLUMNS)
    right_key = ", ".join(f"{RIGHT_ALIAS}.{one}" for one in RECORD_KEY_COLUMNS)
    selected = ", ".join(
        f"{LEFT_ALIAS}.{one} AS left_{one}, {RIGHT_ALIAS}.{one} AS right_{one}"
        for one in RECORD_KEY_COLUMNS
    )
    sql = (
        f"SELECT {selected},\n"
        f"{sql_score_expression()} AS match_weight\n"
        f"FROM {table} {LEFT_ALIAS} JOIN {table} {RIGHT_ALIAS}\n"
        f"  ON ({left_key}) < ({right_key})\n"
        f"WHERE {reach.where}"
    )
    params: dict[str, Any] = {
        **weight_parameters(weights),
        THRESHOLD_PARAM: thresholds.upper,
        **reach.params,
    }
    return ScoreQuery(
        sql=sql,
        params=params,
        weight_version=weights.version,
        calibrated=weights.calibrated,
        certainly_empty=reach.certainly_empty,
    )
