"""The document plane: where the permission predicate sits, and what the indexes promise.

Three things are asserted here and they fail in three different ways.

**The order of the filter and the limit fails invisibly, and it is the leaf everything else
serves.** Ranking first and filtering afterwards produces no error, no exception and no bug
report. It produces a thin answer for the people with the narrowest permissions, which is
the population least able to tell that something is wrong, and the thinness is itself the
disclosure: an asker who gets almost nothing back has learnt that plenty exists and none of
it is theirs. `test_a_narrow_scope_callers_page_is_full_rather_than_near_empty` writes the
wrong order out inline so the two can be read side by side.

**The table fails silently.** The declaration in `brain.knowledge.search` and the migration
are two hand-written descriptions of one database and nothing but a test compares them,
which is the arrangement every other migration in this repository has and the reason each
has a test for it.

**The second wall fails only when it is needed.** A policy is exercised by no ordinary
request, because the query already carries the predicate. What is checked here is that the
policy exists, that it says the same thing the query says, and that the check constraint the
policy's `string_to_array` depends on is really there. Whether PostgreSQL admits and refuses
the rows it is written to needs a server, and that is CI's job rather than this file's.

Task ids: M15.2.1, M15.2.2, M15.2.3, M15.2.4, M15.2.5, M15.2.6, M15.2.7
"""

from __future__ import annotations

import importlib.util
import io
import re
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import CheckConstraint, create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateColumn, CreateIndex, CreateTable
from sqlalchemy.sql import ClauseElement

from brain.core.department import SLUG_RE
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.db import metadata
from brain.install import BY_NAME
from brain.knowledge.embed_policy import QWEN3_EMBEDDING_DIMENSIONS
from brain.knowledge.item import KnowledgeState
from brain.knowledge.search import (  # the two private helpers below are guards, see their tests
    CANDIDATE_DEPTH,
    CHUNK,
    CJK_LEXICAL_INDEX,
    CJK_REGCONFIG_SQL,
    CJK_TSVECTOR,
    DEPARTMENTS_SETTING,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_CHARS,
    INDEXABLE_DIMENSION_CEILING,
    INDEXES,
    ITERATIVE_SCAN,
    KNOWLEDGE_READ,
    LANGUAGE_TAG_CHARS,
    MAX_CANDIDATE_DEPTH,
    PRINCIPAL_SETTING,
    REGCONFIG_SQL,
    RETRIEVABLE_STATE_VALUES,
    SEARCH_CONFIG,
    SLUG_SQL_PATTERN,
    TEXT_FIELDS_THE_DATABASE_CANNOT_FILL,
    WIDTH_SETTING,
    Reach,
    SearchError,
    Vector,
    _posix_pattern,
    chunk_text_fields,
    cjk_lexical_query,
    declared_dimensions,
    hybrid,
    iterative_scan_statements,
    lexical_legs,
    lexical_query,
    reach_for,
    reach_predicate,
    session_settings,
    top_within_reach,
    vector_query,
    width_change_refusal,
)
from brain.knowledge.visibility import Visibility
from brain.ops.migration_policy import check_file

REPO = Path(__file__).resolve().parents[2]
MIGRATION = REPO / "migrations" / "versions" / "0009_search.py"

#: A PostgreSQL dialect to render against. Taken from an engine rather than from
#: `postgresql.dialect()` because that constructor is untyped and mypy runs strict here.
#: Creating an engine performs no I/O; nothing below ever connects it.
POSTGRES = create_engine("postgresql+psycopg://", poolclass=NullPool).dialect

#: Ten departments, so the corpus below is one part in ten reachable by the narrow caller.
#: Ten rather than two, because the failure this file is about is a matter of proportion: a
#: caller who reaches half of everything gets a nearly full page even when the filter runs
#: in the wrong place, and the test would pass for the wrong reason.
DEPARTMENTS = (
    "web",
    "sales",
    "finance",
    "hr",
    "legal",
    "operations",
    "design",
    "data",
    "support",
    "delivery",
)

NARROW = Reach(principal_id="p_ada", departments=("web",))
WIDE = Reach(principal_id="p_root", departments=DEPARTMENTS)

#: The identity a corpus holds, in the `name@revision:dimensions` form the column
#: stores. Named in every vector query now that the model is a conjunct.
A_MODEL = "bge-m3@1.0:1536"

AN_EMBEDDING = [0.01] * EMBEDDING_DIMENSIONS


def a_corpus(size: int = 1000) -> tuple[dict[str, object], ...]:
    """Rows already in descending relevance order, one department in ten being Web.

    A list rather than a database, because the property under test is the order of two
    operations and not the behaviour of an index. Every row is department-visible and
    published, so nothing but the department decides who reaches it and the test cannot
    accidentally pass because of the draft rule or the state filter.
    """
    return tuple(
        {
            "chunk_id": f"doc_{index:04d}.0000",
            "state": KnowledgeState.PUBLISHED.value,
            "owner_id": "p_someone",
            "deleted_at": None,
            "visibility": Visibility.DEPARTMENT.value,
            "department": DEPARTMENTS[index % len(DEPARTMENTS)],
        }
        for index in range(size)
    )


def a_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "chunk_id": "doc_0001.0000",
        "state": KnowledgeState.PUBLISHED.value,
        "owner_id": "p_someone",
        "deleted_at": None,
        "visibility": Visibility.DEPARTMENT.value,
        "department": "web",
    }
    row.update(overrides)
    return row


def entitled(scope: Scope, principal_id: str = "p_ada") -> EntitlementSet:
    return EntitlementSet(
        principal_id=principal_id,
        grants=(Grant(capability=KNOWLEDGE_READ, scope=scope),),
    )


def squash(text: str) -> str:
    """Collapse whitespace, so a statement wrapped across lines still compares."""
    return " ".join(text.split())


def bare_predicate(reach: Reach) -> ClauseElement:
    """A SELECT carrying nothing but the reach predicate, so it can be read on its own.

    The two legs both conjoin the same thing, and reading it without a `ts_rank_cd` or a
    distance operator wrapped round it is what makes an assertion about the predicate an
    assertion about the predicate.
    """
    return sa.select(sa.literal_column("1")).where(reach_predicate(reach))


def rendered_sql(statement: ClauseElement) -> str:
    """The statement as PostgreSQL would receive it, with the expanding IN spelled out."""
    compiled = statement.compile(dialect=POSTGRES, compile_kwargs={"render_postcompile": True})
    return squash(str(compiled))


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("m0009", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rendered(direction: str) -> str:
    """The SQL the migration emits, rendered without a database.

    Alembic's `--sql` mode driven in-process. It matters that the tests read this rather than
    the file's text: a statement sitting in a constant that `upgrade` never executes would
    pass a source-text search and build nothing.
    """
    buffer = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": buffer, "target_metadata": metadata},
    )
    with Operations.context(context):
        getattr(migration(), direction)()
    return buffer.getvalue()


def model_checks() -> dict[str, str]:
    return {
        str(c.name): str(c.sqltext) for c in CHUNK.constraints if isinstance(c, CheckConstraint)
    }


# ============================================== the leaf: a narrow caller's page (M15.2.4)
def test_a_narrow_scope_callers_page_is_full_rather_than_near_empty() -> None:
    """**This is the leaf everything else in this module serves, and it is worth reading the
    two orders side by side.**

    `top_within_reach` filters and then takes, so Ada gets fifty Web chunks. The three lines
    below it are the other order, written out here rather than imported, because the whole
    test is the difference between them: rank first and Ada gets five, because forty-five of
    her results were crowded out of the candidate set by documents she may not see.

    Five results is bad retrieval. What makes it a disclosure is that Ada can count them.
    Everybody else gets fifty, she gets five, and the difference is the number of things she
    is not allowed to know exist. The platform's rule is that DENIED and ABSENT are
    indistinguishable, and post-filtering breaks it twice over: by the emptiness and by the
    count.

    Delete this test and the post-filter is a one-line simplification that no other
    assertion in this repository would notice."""
    corpus = a_corpus()

    inside = top_within_reach(corpus, reach=NARROW, depth=CANDIDATE_DEPTH)

    # The wrong order. Take the top fifty by relevance, then drop what Ada may not read.
    ranked_first = corpus[:CANDIDATE_DEPTH]
    then_filtered = tuple(str(r["chunk_id"]) for r in ranked_first if NARROW.admits(r))

    assert len(inside) == CANDIDATE_DEPTH
    assert len(then_filtered) == 5
    assert set(then_filtered) < set(inside)


def test_the_size_of_a_page_says_nothing_about_who_asked_for_it() -> None:
    """The second half of the disclosure, stated on its own because it is the half that
    survives somebody "fixing" the first by fetching more candidates. A wider candidate set
    makes the narrow caller's page fuller and leaves the count different, and a count that
    varies with the asker's permissions is a permission model readable from the outside.

    With the filter inside the query both callers get a full page, so the size of the result
    carries nothing.

    Delete this and over-fetching looks like a complete fix."""
    corpus = a_corpus()
    assert len(top_within_reach(corpus, reach=NARROW)) == len(top_within_reach(corpus, reach=WIDE))


def test_a_caller_who_reaches_nothing_still_gets_an_ordinary_empty_page() -> None:
    """The positive case's opposite, and the one that keeps the test above honest. A function
    that returned a full page for everybody would pass every assertion so far. Somebody whose
    reach genuinely admits nothing gets nothing, and it is an ordinary empty tuple rather
    than an error, because an error would be a different observable outcome for a person
    with no access than for a person whose search matched nothing."""
    stranger = Reach(principal_id="p_new")
    assert top_within_reach(a_corpus(), reach=stranger) == ()


# ================================================ the predicate is inside the query (M15.2.6)
def test_the_scope_predicate_is_inside_the_query_and_never_applied_to_its_results() -> None:
    """The same claim as the leaf above, asserted where it actually runs. The department test
    appears between `WHERE` and `LIMIT` of a single statement: there is no outer query over a
    limited subquery, which is what post-filtering would look like once somebody wrote it in
    SQL rather than in Python.

    Delete this and the predicate can be lifted into an enclosing SELECT, which reads in a
    diff as a tidy-up and returns the narrow caller five rows."""
    sql = rendered_sql(lexical_query("client sla", reach=NARROW))
    assert sql.count("SELECT") == 1, sql
    where = sql.index(" WHERE ")
    limit = sql.index(" LIMIT ")
    assert where < sql.index("chunk.department") < limit


def test_both_legs_carry_exactly_the_same_reach_predicate() -> None:
    """Two queries and one permission rule. A predicate that drifted between the legs would
    make what a person can see depend on which retriever found it, so a document would be
    reachable by its wording and not by its meaning, or the other way round.

    Delete this and the vector leg's `WHERE` can be simplified during a performance
    investigation without the lexical leg's tests noticing."""
    standalone = rendered_sql(bare_predicate(NARROW))
    predicate = standalone.split(" WHERE ", 1)[1]
    assert predicate in rendered_sql(lexical_query("client sla", reach=NARROW))
    assert predicate in rendered_sql(vector_query(AN_EMBEDDING, reach=NARROW, model=A_MODEL))


def test_every_visibility_level_has_a_branch_in_the_predicate() -> None:
    """The disjunction is the enumeration of `Visibility` and nothing else. A level with no
    branch matches nothing, so every document at it becomes invisible to everybody, which
    fails closed and is therefore never reported: the documents are simply never found.

    `_level_branch` matches on the enum with `assert_never`, so a fourth level is a mypy
    failure as well. This is the runtime half, and it is what catches a branch that is
    present but tests the wrong string."""
    compiled = lexical_query("q", reach=NARROW).compile(dialect=POSTGRES)
    branched = {value for key, value in compiled.params.items() if key.startswith("visibility")}
    assert branched == {level.value for level in Visibility}


def test_a_caller_who_reaches_no_department_gets_false_and_not_a_missing_branch() -> None:
    """`brain.core.department.CrossDepartmentPlan` makes the same distinction with `None`
    rather than an unrestricted scope, and calls a filter list that reduces to no WHERE
    clause the most expensive bug available in this design. This is that bug in its other
    form: an empty department list has to compile to `false`, not to a branch that was left
    out, because a left-out branch inside an OR admits everything the other branches do not.

    Delete this and the personal-only caller reads the whole company's department
    documents."""
    sql = rendered_sql(bare_predicate(NARROW))
    without = rendered_sql(bare_predicate(Reach(principal_id="p_new")))
    assert "chunk.department" in sql
    assert "false" in without
    assert "chunk.department" not in without


def test_a_grant_that_cannot_be_reduced_to_departments_is_refused_not_trimmed() -> None:
    """**A widening that would have shipped.** A grant reading `department = web AND
    owner_id = p_bob` admits Web, so reducing it to the department list `("web",)` builds a
    query returning every Web document rather than Bob's. The dropped clause was the one
    doing the narrowing, and the query that results returns more rows, which reads as better
    recall.

    Refused rather than reduced, for the reason `brain.core.redaction.redact` refuses an
    opaque request it cannot honour: a caller who asked for one thing and silently received
    a wider one never checks.

    Delete this and the reduction looks like ordinary intersection arithmetic."""
    narrowing = Scope(
        clauses=(
            Clause(field="department", op=Op.EQ, value="web"),
            Clause(field="owner_id", op=Op.EQ, value="p_bob"),
        )
    )
    with pytest.raises(SearchError, match="reads as better recall"):
        reach_for(entitled(narrowing), departments=DEPARTMENTS)


def test_a_prefix_over_departments_is_refused_with_the_rest() -> None:
    """The one that looks harmless. `department LIKE 'web%'` is a real predicate, and a list
    of names could stand in for it only by enumerating whichever departments existed on the
    day the query ran, so the reduction would change meaning when a department is created.

    Delete this and a prefix grant silently means "the departments that happened to exist at
    request time", which is a permission that moves on its own."""
    prefixed = Scope(clauses=(Clause(field="department", op=Op.PREFIX, value="web"),))
    with pytest.raises(SearchError, match="membership of department"):
        reach_for(entitled(prefixed), departments=DEPARTMENTS)


def test_a_grant_that_is_a_department_membership_is_admitted() -> None:
    """The sibling every refusal needs. Three shapes have to keep working: one department,
    several, and the unrestricted grant a super admin holds, which reaches every department
    precisely because it never mentions the field.

    Delete this and the guard above is satisfied by a function that refuses everything, and
    the document plane answers nobody."""
    one = reach_for(entitled(Scope.department("web")), departments=DEPARTMENTS)
    several = reach_for(
        entitled(Scope(clauses=(Clause(field="department", op=Op.IN, value=("web", "sales")),))),
        departments=DEPARTMENTS,
    )
    everything = reach_for(entitled(Scope()), departments=DEPARTMENTS)
    assert one is not None and one.departments == ("web",)
    assert several is not None and several.departments == ("web", "sales")
    assert everything is not None and everything.departments == DEPARTMENTS


def test_a_caller_holding_no_read_of_the_knowledge_plane_produces_no_reach_at_all() -> None:
    """None rather than a `Reach` with an empty department list, and the difference is what
    a caller does next: there is no query to build. `EntitlementSet.scope_for` already
    returns None for an expired principal, so expiry arrives here as absence rather than as a
    second check somebody has to remember.

    Delete this and an ungranted caller gets a query that runs and returns the company's
    handbook."""
    assert reach_for(EntitlementSet(principal_id="p_ada"), departments=DEPARTMENTS) is None
    other = EntitlementSet(
        principal_id="p_ada",
        grants=(Grant(capability=Capability(value="read:client"), scope=Scope()),),
    )
    assert reach_for(other, departments=DEPARTMENTS) is None


# ================================================= what the predicate excludes as well
def test_a_draft_is_reachable_only_by_the_person_who_owns_it() -> None:
    """`KnowledgeState.DRAFT` says so: written, not yet vouched for, retrievable only by its
    owner. Without this conjunct a department-visible draft answers questions for the whole
    department in its author's name, and the badge beside the answer would say unverified,
    which nobody reads as "this is somebody's unfinished note".

    Delete this and an upload becomes a publication the moment it lands."""
    mine = a_row(state=KnowledgeState.DRAFT.value, owner_id="p_ada")
    theirs = a_row(state=KnowledgeState.DRAFT.value, owner_id="p_bob")
    assert NARROW.admits(mine)
    assert not NARROW.admits(theirs)
    # And the same rule is in the SQL, not only in the Python evaluator.
    sql = rendered_sql(bare_predicate(NARROW))
    assert "chunk.state != " in sql


@pytest.mark.parametrize("state", sorted(set(KnowledgeState) - {KnowledgeState.DRAFT}))
def test_only_the_retrievable_states_are_reachable(state: KnowledgeState) -> None:
    """A superseded document must stop answering beside the version that replaced it, and an
    archived one must not answer at all. `chunk_document` refuses to *build* chunks for
    either, and this refuses to *read* the chunks of a document superseded after they were
    built, which is the ordinary case: version two arrives months after version one was
    indexed.

    Delete this and the company keeps quoting the price list it replaced."""
    row = a_row(state=state.value)
    assert NARROW.admits(row) is (state in {KnowledgeState.PUBLISHED})
    assert state.value in RETRIEVABLE_STATE_VALUES or not NARROW.admits(row)


def test_the_query_filters_the_unretrievable_states_and_not_only_the_evaluator() -> None:
    """**Found by mutation.** The test above pins `Reach.admits` and left the SQL conjunct
    unguarded, so deleting `state.in_(...)` from `reach_predicate` was a survivor: every
    assertion in this file still passed while the query returned the chunks of superseded and
    archived documents. The SQL is the half that runs against the whole table, and the Python
    evaluator is only its statement in a form that can be tested here.

    The values are compared against the same frozenset the evaluator reads, so a list widened
    to include `superseded` fails as loudly as a list removed.

    Delete this and the replaced price list answers again, beside the one that replaced
    it."""
    statement = bare_predicate(NARROW)
    assert "know.chunk.state IN (" in rendered_sql(statement)
    bound = statement.compile(dialect=POSTGRES).params.values()
    assert list(RETRIEVABLE_STATE_VALUES) in list(bound)


def test_a_retired_chunk_is_never_reachable() -> None:
    """Re-chunking a document retires its old chunks, and the old spans point a few
    characters off after a re-parse. A retired chunk that stayed reachable would produce a
    citation that resolves to the wrong sentence, which is the worst kind of wrong:
    followable, specific, and about a different paragraph."""
    assert NARROW.admits(a_row())
    assert not NARROW.admits(a_row(deleted_at="2026-09-06T09:00:00+00:00"))


def test_a_company_document_is_reached_by_a_caller_with_the_narrowest_department() -> None:
    """**The rejected alternative, asserted.** Applying the caller's departmental grant to
    every branch would be the tidy thing to do and would hide the staff handbook from
    everybody whose grant is departmental, which is everybody. The document is readable by
    design, is never found, and the answer is merely thin with nothing saying why.

    Delete this and the tidy version ships, and the symptom is that company knowledge stops
    being retrievable while every permission test passes.

    **The second assertion was found by mutation.** With only the first, narrowing the
    company branch in `_level_branch` was a survivor: the Python evaluator still admitted the
    handbook, the SQL no longer did, and nothing here reported the difference. The department
    test belongs in exactly one branch of the disjunction, so a second copy of it means a
    second branch has acquired one."""
    assert NARROW.admits(a_row(visibility=Visibility.COMPANY.value, department=None))
    sql = rendered_sql(bare_predicate(NARROW))
    assert sql.count("chunk.department") == 1


def test_a_personal_document_is_reached_only_by_its_owner() -> None:
    """The narrowest level, from both sides. A personal document reachable by a colleague is
    the failure `brain.knowledge.visibility.scope_for` refuses at the other end, where a
    personal scope built without an owner becomes the unrestricted one."""
    mine = a_row(visibility=Visibility.PERSONAL.value, owner_id="p_ada", department=None)
    theirs = a_row(visibility=Visibility.PERSONAL.value, owner_id="p_bob", department=None)
    assert NARROW.admits(mine)
    assert not NARROW.admits(theirs)


def test_a_department_document_outside_the_callers_departments_is_not_reached() -> None:
    """The department branch doing its job, which every other assertion here assumes."""
    assert NARROW.admits(a_row(department="web"))
    assert not NARROW.admits(a_row(department="finance"))


# ========================================================== the two legs (M15.2.1, M15.2.2)
def test_the_lexical_leg_asks_with_the_configuration_the_index_was_built_with() -> None:
    """A GIN index built over `to_tsvector('english', ...)` is never used by a query asking
    with `simple`, and the symptom is not an error: it is a sequential scan returning the
    right answer slowly, which nothing fails on and which is diagnosed months later.

    Both come from `SEARCH_CONFIG`, so this is what says the single constant really does
    reach both places."""
    assert f"'{SEARCH_CONFIG}'" == REGCONFIG_SQL
    sql = rendered_sql(lexical_query("client sla", reach=NARROW))
    assert f"websearch_to_tsquery({REGCONFIG_SQL}" in sql
    generated = str(CreateTable(CHUNK).compile(dialect=POSTGRES))
    assert f"to_tsvector({REGCONFIG_SQL}," in generated


def test_the_lexical_leg_uses_the_parser_that_does_not_raise_on_a_persons_punctuation() -> None:
    """`to_tsquery` raises a syntax error on ordinary punctuation, so "what is the client's
    SLA?" would return a 500 from an apostrophe. `websearch_to_tsquery` parses what a person
    types and never raises, and unlike `plainto_tsquery` it keeps quoted phrases and a
    leading minus.

    Delete this and the swap to `to_tsquery` looks like using the more capable function."""
    sql = rendered_sql(lexical_query('"service level" -draft', reach=NARROW))
    assert "websearch_to_tsquery" in sql
    assert "plainto_tsquery" not in sql
    assert re.search(r"(?<!websearch_)to_tsquery", sql) is None


def test_the_search_column_is_weighted_rather_than_flat() -> None:
    """With every field at weight A, `ts_rank_cd` cannot tell a chunk that is *about* a term
    from one that mentions it once in a paragraph, and a title is the closest thing to a
    statement of aboutness a chunk carries.

    `coalesce` on every input is the other half and it is the one that fails silently:
    concatenating a tsvector with NULL yields NULL, so one chunk with no section heading
    would have an empty search column and be invisible while looking indexed."""
    generated = str(CreateTable(CHUNK).compile(dialect=POSTGRES))
    for column, weight in (("title", "A"), ("section", "B"), ("body", "C")):
        assert f"coalesce({column}, '')), '{weight}')" in generated
    assert "GENERATED ALWAYS AS" in generated
    assert "STORED" in generated


# --------------------------------------------------- the guards on the DDL helpers
def test_a_vector_column_of_no_width_is_refused() -> None:
    """A width of zero renders `VECTOR(0)`, which PostgreSQL refuses at migration time with a
    message about the type rather than about the column, and a negative one renders something
    that is not a type at all.

    Found by a mutation audit over every condition in this module: the guard was written,
    correct, and reachable by nothing.

    Delete this and the branch is unreachable again, and the failure moves from an import in
    a test run to a migration on a client's server."""
    with pytest.raises(SearchError, match="is not a vector width"):
        Vector(0)


def test_a_pattern_that_still_carries_a_colon_after_conversion_is_refused() -> None:
    """**The guard on the guard, and the reason it exists shipped once.**

    `CheckConstraint` wraps its argument in `sqlalchemy.text`, which reads `:name` as a bind
    parameter. A `(?:` in a Python pattern therefore rendered as the word NULL inside the
    constraint: it looked like a regex, it was a different regex, and nothing about the model
    or the migration said so. The conversion removes the non-capturing groups; this refuses a
    colon that survived by any other route, such as a character class or a literal.

    Delete this and the one thing standing between another colon and another silently wrong
    constraint is unreachable, which is what it was until this test."""
    with pytest.raises(SearchError, match="still carries a colon"):
        _posix_pattern("^[a-z]+:[0-9]+$")


def test_a_pattern_carrying_a_construct_postgres_does_not_have_is_refused() -> None:
    """The second half of the same guard. A lookahead or a named group is Python-only, so a
    constraint built from one is refused by PostgreSQL when the migration runs, which is the
    worst moment to find out: the deploy has already started.

    Written with a lookahead rather than another non-capturing group, because the conversion
    removes those and this has to survive it.

    Delete this and only the colon half is watched, and the pattern that reaches a client's
    database is the one nobody could run here."""
    with pytest.raises(SearchError, match="does not have"):
        _posix_pattern("^(?=[a-z])[a-z0-9]+$")


def test_a_pattern_the_conversion_can_handle_comes_back_without_its_colons() -> None:
    """The positive case for both refusals, and the property the conversion exists for: a
    non-capturing group becomes an ordinary one, which matches identically and carries no
    colon.

    Delete this and `_posix_pattern` can be tightened until it refuses the patterns this
    module actually uses, and the failure is at import."""
    assert _posix_pattern("^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$") == "^[a-z][a-z0-9]*(_[a-z0-9]+)*$"


# ------------------------------------------------- the Han leg (M35.1.2.1, M35.1.2.3)
#: A Chinese phrase and the two-character term inside it, which is the case the whole leg
#: exists for. Written as escapes rather than as characters so this file stays readable in a
#: terminal that cannot render them, and so a copy through a lossy clipboard cannot silently
#: change the test.
A_HAN_PHRASE = "\u5ba2\u6237\u670d\u52a1\u6761\u6b3e"
A_HAN_TERM = "\u6761\u6b3e"


def test_a_two_character_term_shares_a_token_with_the_phrase_that_contains_it() -> None:
    """**The failure the column exists for, stated as the property that fixes it.**

    PostgreSQL's parser has no Chinese dictionary, so a run of Han characters is one token and
    a query for a term inside a longer phrase matches nothing. Overlapping bigrams give every
    adjacent pair its own token, so any term of two characters or more shares a token with the
    text containing it.

    Asserted as an intersection of the two token sets rather than as a literal list of
    bigrams, because a list here is the tokeniser's output written down twice and would agree
    with it for every segmentation it could produce.

    Delete this and the column can be filled with the whole phrase, which indexes and matches
    nothing a person would type."""
    indexed = set(chunk_text_fields(A_HAN_PHRASE)["cjk"].split())
    asked = set(chunk_text_fields(A_HAN_TERM)["cjk"].split())

    assert asked
    assert asked <= indexed


def test_the_han_leg_asks_with_the_configuration_its_column_was_built_with() -> None:
    """The same argument as the English leg one file-section above, and it matters more here:
    `english` would stem a bigram against a stop list written for another language and would
    do it differently at index time and query time depending on what the pair looked like.

    Both halves are read from `CJK_REGCONFIG_SQL`, so this says the one constant reaches both
    places rather than saying two literals agree.

    Delete this and the index and the query can drift to different configurations, and the
    symptom is a Chinese query that returns nothing while the index sits there looking used."""
    assert CJK_REGCONFIG_SQL in CJK_TSVECTOR
    sql = rendered_sql(cjk_lexical_query(A_HAN_TERM, reach=NARROW))

    assert f"websearch_to_tsquery({CJK_REGCONFIG_SQL}" in sql
    generated = str(CreateTable(CHUNK).compile(dialect=POSTGRES))
    assert f"to_tsvector({CJK_REGCONFIG_SQL}, coalesce(cjk, ''))" in generated


def test_the_han_query_is_segmented_by_the_same_function_that_segmented_the_text() -> None:
    """A bigram index asked with a whole phrase matches nothing, which is the same failure the
    column was added to fix arriving from the query side.

    The bound parameter is compared against what `chunk_text_fields` would have written for
    the same text, so the two sides are asserted to agree rather than both asserted against a
    literal.

    Delete this and the query side can pass the raw question, and every Chinese search returns
    nothing at all."""
    compiled = cjk_lexical_query(A_HAN_PHRASE, reach=NARROW).compile(dialect=POSTGRES)
    expected = chunk_text_fields(A_HAN_PHRASE)["cjk"]

    assert expected in compiled.params.values()
    assert A_HAN_PHRASE not in compiled.params.values()


def test_the_han_leg_reaches_only_the_callers_rows() -> None:
    """The reach predicate is conjoined into the same `WHERE` the `LIMIT` applies to, exactly
    as the English leg does. A second leg is a second place to leave the predicate out, and
    leaving it out returns other people's rows ranked by relevance.

    Delete this and the newest search path is the one with no permission check in it."""
    sql = rendered_sql(cjk_lexical_query(A_HAN_TERM, reach=NARROW))

    assert "owner_id" in sql
    assert "LIMIT" in sql
    assert sql.count("SELECT") == 1


def test_the_han_index_is_partial_on_the_same_predicate_as_the_english_one() -> None:
    """A retired chunk in a GIN index is postings nobody may read, and re-chunking a document
    retires a document's worth at once.

    Delete this and the second index is the one that keeps the postings of every deleted
    chunk, which is a disclosure risk the first index does not have."""
    rendered_index = str(CreateIndex(CJK_LEXICAL_INDEX).compile(dialect=POSTGRES))

    assert "USING gin" in rendered_index
    assert "WHERE deleted_at IS NULL" in rendered_index


def test_a_question_is_asked_of_every_script_it_contains() -> None:
    """**A mixed question is not a majority vote.** "SLA \u6761\u6b3e" is two words in two
    scripts and the answer may be in a document holding either, so running one leg on the
    strength of a character count discards half the question.

    Delete this and a question with three Latin words and one Chinese term asks only the
    English leg, and the Chinese term is silently dropped."""
    assert lexical_legs(f"SLA {A_HAN_TERM}") == ("tsv", "tsv_cjk")
    assert lexical_legs("service level") == ("tsv",)
    assert lexical_legs(A_HAN_TERM) == ("tsv_cjk",)


def test_a_question_with_no_letters_at_all_still_asks_the_english_leg() -> None:
    """A number or a reference is neither script, and answering "no legs" would make the
    search return nothing for a question somebody typed.

    Delete this and asking for an invoice number returns an empty result rather than a
    lexical match."""
    assert lexical_legs("2026") == ("tsv",)
    assert lexical_legs("") == ("tsv",)


def test_a_chunk_with_too_little_text_records_no_language_rather_than_english() -> None:
    """**M35.1.2.3, and the nullable column is the load-bearing part.** A detector that always
    answers turns "we could not tell" into "English", which is a claim nothing downstream can
    distinguish from a measurement. A row saying unknown can be improved later; one saying
    English will not be looked at again.

    Delete this and the obvious tidy-up is a default of `en`, and every two-word chunk in the
    corpus becomes a confident English row."""
    assert chunk_text_fields("OK")["language"] is None
    assert (
        chunk_text_fields("a chunk with plenty of English words in it to be sure")["language"]
        == "en"
    )


def test_every_column_the_database_cannot_fill_is_filled_by_the_one_builder() -> None:
    """`cjk` is the only column on this table the database cannot compute, so it is the only
    one with a second place to forget it, and `chunk_text_fields` is that place made single.

    The declared list and the builder's keys are compared, and the list is written out in the
    module rather than derived from the builder, so the two can disagree. Derived, this test
    would move both sides together and be green for every list either could hold.

    Delete this and a column can be added to the declared list with nothing filling it, or
    filled by the builder without being declared, and either way a chunk is written that is
    invisible to a Chinese query while looking indexed."""
    built = chunk_text_fields("a chunk with plenty of English words in it to be sure")

    assert set(TEXT_FIELDS_THE_DATABASE_CANNOT_FILL) == set(built)


def test_the_language_column_is_wide_enough_for_every_tag_the_detector_produces() -> None:
    """Anchored against `brain.locale.SCRIPT_LANGUAGE` rather than against a number written
    here, so a third language whose tag does not fit fails this instead of being truncated
    into a fourth language nobody declared.

    Delete this and adding a locale silently starts writing truncated tags, which read as
    real ones."""
    from brain.locale import SCRIPT_LANGUAGE

    assert max(len(tag) for tag in SCRIPT_LANGUAGE.values()) <= LANGUAGE_TAG_CHARS


def test_the_vector_leg_orders_by_distance_and_limits_in_the_same_statement() -> None:
    """The nearest-neighbour ordering has to be the statement's own `ORDER BY ... LIMIT` or
    the index is not used at all: pgvector reaches an HNSW index through exactly that shape,
    and any wrapping turns it into a sequential scan with a sort, which returns the right
    answer and cannot be told apart from a correct query by its output."""
    sql = rendered_sql(vector_query(AN_EMBEDDING, reach=NARROW, model=A_MODEL))
    assert sql.count("SELECT") == 1
    assert " ORDER BY (know.chunk.embedding <=> " in sql
    assert sql.index(" ORDER BY ") < sql.index(" LIMIT ")


def test_the_vector_leg_excludes_rows_that_have_not_been_embedded_yet() -> None:
    """A NULL distance orders last in PostgreSQL rather than being dropped, so without this a
    corpus with fewer embedded chunks than the depth returns unembedded chunks at the tail
    with no distance at all, and fusion would rank them as though a retriever had chosen
    them."""
    assert "know.chunk.embedding IS NOT NULL" in rendered_sql(
        vector_query(AN_EMBEDDING, reach=NARROW, model=A_MODEL)
    )


def test_an_embedding_of_the_wrong_width_is_refused_before_the_server_sees_it() -> None:
    """The dimension is part of the column type, so a model swapped underneath this produces
    a server-side error naming two integers and no column. Refusing here names the model and
    the column, which is the difference between a five-minute diagnosis and an afternoon.

    Delete this and the first symptom of an embedding model change is an insert failing in
    production."""
    with pytest.raises(SearchError, match="the column's width is the model's"):
        vector_query([0.1] * (EMBEDDING_DIMENSIONS - 1), reach=NARROW, model=A_MODEL)


def test_the_stored_vector_is_narrow_enough_that_an_index_can_be_built_on_it() -> None:
    """pgvector stores up to 16,000 dimensions and indexes at most 2,000. The asymmetry is
    the trap: the column is created, the rows are inserted, and `CREATE INDEX` is what fails,
    by which point there is a corpus to re-embed.

    The second assertion held the declaration to `0009`'s copy of it until 2026-09-10, when
    the width became `INSTALL_EMBEDDING_DIMENSIONS` and `0027` became what sets the column.
    `0009` still describes the column it built, which is why the comparison moved rather than
    being deleted: the migration that decides the width today is the one that has to agree.

    Delete this and raising the dimension to a larger model's native width looks like a
    quality improvement right up to the migration."""
    assert EMBEDDING_DIMENSIONS <= INDEXABLE_DIMENSION_CEILING
    assert width_migration().EMBEDDING_DIMENSIONS == EMBEDDING_DIMENSIONS


def test_the_width_is_whatever_the_install_declared_rather_than_a_number_in_this_module() -> None:
    """**The half of item 34 that is not about 1024.** A column width compiled into the
    product makes a client whose embedding model is a different size a fork of this
    repository, and the fork is the failure that reports nothing: both copies pass their own
    tests and only one of them gets the next fix.

    Asserted at a width that is nobody's real model, so a reading that returned the default
    whatever it was handed would fail here rather than agreeing with itself.

    Delete this and `declared_dimensions` can go back to returning a constant, with every
    other test in this file green because they all resolve through it."""
    assert declared_dimensions({WIDTH_SETTING: "768"}) == 768
    assert declared_dimensions({WIDTH_SETTING: str(INDEXABLE_DIMENSION_CEILING)}) == (
        INDEXABLE_DIMENSION_CEILING
    )


def test_the_default_width_is_the_one_the_model_this_product_serves_produces() -> None:
    """Where 1024 comes from, asserted against the three things outside the declaration that
    decide it rather than against itself.

    A test reading `BY_NAME[WIDTH_SETTING].default` and comparing it to 1024 written here
    would compare a constant with a copy of itself and stay green at every value the setting
    could hold, which is the failure `CLAUDE.md` records three separate authors making in one
    afternoon. So the default is held to `brain.knowledge.embed_policy`'s record of the model
    card figure, to the pgvector ceiling it has to sit under, and to the width the column
    object actually ends up declaring when nothing is set.

    Delete this and the shipped default can drift from the model this product serves, whose
    only symptom is that every embedding job fails at the insert on a fresh install."""
    default = BY_NAME[WIDTH_SETTING].default

    assert int(default) == QWEN3_EMBEDDING_DIMENSIONS
    assert int(default) <= INDEXABLE_DIMENSION_CEILING
    assert declared_dimensions({}) == int(default)
    # `get_col_spec` is pgvector's, and mypy sees the column's type as the generic
    # `TypeEngine`. Cast at the library boundary: proving the structural match would be
    # work for no property, and the assertion itself is what pins the rendered width.
    assert cast("Any", CHUNK.c.embedding.type).get_col_spec() == f"VECTOR({default})"


def test_a_width_pgvector_will_store_and_refuse_to_index_is_refused_when_it_is_read() -> None:
    """The value is refused rather than the index, and the order is the whole point.

    pgvector stores a vector of up to 16,000 dimensions and indexes one of at most 2,000, so a
    width between the two produces a column that accepts every row and an index that cannot be
    built. Nothing says so until `CREATE INDEX`, which is after the corpus exists, and the
    repair at that point is a migration plus a re-embed rather than an edit to one line of an
    environment file.

    Delete this and a client can be told to set a width their model produces and this system
    cannot index, and the failure arrives at the worst possible moment."""
    with pytest.raises(SearchError, match="cannot carry an HNSW or IVFFlat index"):
        declared_dimensions({WIDTH_SETTING: str(INDEXABLE_DIMENSION_CEILING + 1)})


@pytest.mark.parametrize("supplied", ["0", "-1", "1024 dimensions", "1e3", "1024.0", ""])
def test_a_width_that_is_not_a_usable_number_of_dimensions_is_refused(supplied: str) -> None:
    """Every way this setting is filled in wrongly by hand, refused where it is read.

    The empty string is in the list and is the one that is not a refusal: an unset variable
    and a variable set to nothing are the same thing to `brain.install.value_of`, and both
    mean the default. The rest reach SQLAlchemy as a column type otherwise, and the message
    then names a Python type rather than the variable somebody just edited.

    Delete this and a mistyped width is discovered from a DDL error during an install."""
    if not supplied:
        assert declared_dimensions({WIDTH_SETTING: supplied}) == EMBEDDING_DIMENSIONS
        return
    with pytest.raises(SearchError, match=WIDTH_SETTING):
        declared_dimensions({WIDTH_SETTING: supplied})


def test_values_are_bound_into_the_query_and_never_rendered_into_it() -> None:
    """The department, the principal and the question are all somebody else's strings. They
    appear in the parameter dictionary and nowhere in the statement, which is the property
    rather than the habit: `brain.core.scope_sql` validates identifiers precisely because
    they cannot be parameterised, and everything that can be, is."""
    compiled = lexical_query("client sla", reach=NARROW).compile(dialect=POSTGRES)
    assert "client sla" in compiled.params.values()
    assert "web" in compiled.params.values()
    assert "p_ada" in compiled.params.values()
    assert "client sla" not in str(compiled)
    assert "p_ada" not in str(compiled)


@pytest.mark.parametrize("depth", [0, -1, MAX_CANDIDATE_DEPTH + 1])
def test_a_candidate_depth_outside_the_bounds_is_refused(depth: int) -> None:
    """A depth of zero asks for no candidates and returns an empty page that reads as an
    empty knowledge base. A depth without a ceiling is a request parameter, and a large
    enough one turns each leg into a scan with a sort on top for rows nothing ever shows."""
    with pytest.raises(SearchError):
        lexical_query("q", reach=NARROW, depth=depth)


# ============================================ iterative scan, not an index per scope (M15.2.3)
def test_iterative_scan_is_enabled_rather_than_a_partial_index_per_scope() -> None:
    """**The decision this leaf asks for, asserted as a shape.** One vector index, narrowed
    only by liveness, plus iterative scan at query time. A per-scope index would show up here
    as a `WHERE department = ...` on the index itself, and would need one index per
    department and one per person, each maintained on every insert, with onboarding becoming
    a DDL change.

    Delete this and the first person to meet the filtered-ANN problem adds a partial index
    for the one department that complained, which works and does not compose."""
    vectors = [
        index for index in INDEXES if index.dialect_options["postgresql"].get("using") == "hnsw"
    ]
    assert len(vectors) == 1
    predicate = str(vectors[0].dialect_options["postgresql"]["where"])
    assert predicate == "deleted_at IS NULL"
    for scoped in ("department", "owner_id", "visibility"):
        assert scoped not in predicate
    assert dict(ITERATIVE_SCAN)["hnsw.iterative_scan"] == "relaxed_order"
    assert int(dict(ITERATIVE_SCAN)["hnsw.max_scan_tuples"]) > 0


def test_the_scan_bound_is_set_alongside_iterative_scan_and_not_left_open() -> None:
    """Iterative scan without a bound is a sequential scan for a caller narrow enough, which
    is precisely the caller this whole module exists for. The bound is what keeps the cost
    of the safe behaviour finite, and reaching it returns fewer rows rather than wrong ones.

    Delete this and the bound can be dropped as an unnecessary constraint on recall."""
    names = [name for name, _value in ITERATIVE_SCAN]
    assert names == ["hnsw.iterative_scan", "hnsw.max_scan_tuples"]
    statements = iterative_scan_statements()
    assert len(statements) == len(ITERATIVE_SCAN)
    for statement, (name, value) in zip(statements, ITERATIVE_SCAN, strict=True):
        compiled = statement.compile(dialect=POSTGRES)
        assert compiled.params == {"name": name, "value": value}


# ============================================================ the second wall (M15.2.7)
def test_a_session_setting_binds_its_value_rather_than_building_a_statement_out_of_it() -> None:
    """`SET LOCAL x = :v` is a syntax error, because `SET` takes no bind parameters at all,
    and that is why code reaching for it ends up interpolating. `set_config(name, value,
    true)` is an ordinary function call and does take them, so nothing here builds SQL out of
    a principal id.

    `true` is `is_local`. PgBouncer runs in transaction mode, so a session-lifetime `SET` can
    land on a connection handed to somebody else afterwards, which is the same class of trap
    0005 records and that made `pg_advisory_lock` unusable in `brain.migrate`."""
    statements = session_settings(NARROW)
    compiled = [statement.compile(dialect=POSTGRES) for statement in statements]
    assert [c.params for c in compiled] == [
        {"name": PRINCIPAL_SETTING, "value": "p_ada"},
        {"name": DEPARTMENTS_SETTING, "value": "web"},
    ]
    for one in compiled:
        assert "SET LOCAL" not in str(one)
        assert "p_ada" not in str(one)
        assert ", true)" in str(one)


def test_the_migration_enables_row_level_security() -> None:
    """A policy on a table without row-level security enabled is a policy PostgreSQL never
    consults, and `sweep_rls` fails the build on a table in a named schema without it. The
    two statements are separate and forgetting the first is silent.

    Asserted on the rendered upgrade rather than on the constant, for the reason `rendered`
    exists: a statement in a tuple that `upgrade` never executes builds nothing."""
    up = squash(rendered("upgrade"))
    assert "ALTER TABLE know.chunk ENABLE ROW LEVEL SECURITY" in up
    assert "CREATE POLICY chunk_within_reach ON know.chunk FOR ALL TO brain_app" in up
    assert "WITH CHECK (true)" in up


def test_the_policy_repeats_the_reach_the_query_already_carries() -> None:
    """**Why both walls.** The predicate in the query is right today and is written by
    whoever wrote the query; the policy is what holds when a future query is not, which is
    the one added during an incident or by a backfill next year. A policy that checked only
    liveness would be the thing every other table has, which is not a second wall for reach
    at all.

    Every level, both settings, the draft rule and the retrievable states, taken from the
    same constants the query is built from.

    Delete this and the policy can be simplified to `deleted_at IS NULL` and every other
    test here still passes."""
    up = squash(rendered("upgrade"))
    policy = up[up.index("CREATE POLICY chunk_within_reach") : up.index("WITH CHECK")]
    for level in Visibility:
        assert f"visibility = '{level.value}'" in policy
    assert f"current_setting('{PRINCIPAL_SETTING}', true)" in policy
    assert f"current_setting('{DEPARTMENTS_SETTING}', true)" in policy
    assert "state <> 'draft' OR owner_id = current_setting" in policy
    listed = ", ".join(f"'{state}'" for state in RETRIEVABLE_STATE_VALUES)
    assert f"state IN ({listed})" in policy
    assert "deleted_at IS NULL" in policy


def test_the_check_constraint_is_what_makes_the_policys_comma_split_sound() -> None:
    """The policy splits `app.departments` on a comma. That is only safe because the column
    it is compared against cannot hold one, which the slug constraint enforces. The two are
    written in different files and neither says the other exists, so this is the line between
    them.

    Delete this and widening the department column's grammar becomes a way to smuggle a
    second department past the second wall."""
    up = squash(rendered("upgrade"))
    assert f"string_to_array(current_setting('{DEPARTMENTS_SETTING}', true), ',')" in up
    assert SLUG_RE.match("web")
    assert not SLUG_RE.match("web,finance")
    assert re.match(SLUG_SQL_PATTERN, "web")
    assert not re.match(SLUG_SQL_PATTERN, "web,finance")
    assert "," not in model_checks()["ck_chunk_department_is_a_slug"]


def test_a_department_name_outside_the_slug_grammar_is_refused_by_the_reach() -> None:
    """The same rule at the other end. A reach carrying `web,finance` would set one session
    setting that the policy splits into two departments, so the second wall would admit a
    department nobody granted. The column's constraint cannot catch that, because the value
    never reaches a column."""
    with pytest.raises(SearchError, match="split into departments nobody granted"):
        Reach(principal_id="p_ada", departments=("web,finance",))


def test_a_reach_without_a_principal_is_refused() -> None:
    """An empty principal compares `owner_id` against an empty string, which no chunk carries
    because of the `owned` constraint. Every personal document and every draft would then be
    unreachable by anybody, including its own author, and the symptom is a knowledge layer
    that has quietly lost half its rows."""
    with pytest.raises(SearchError, match="reach needs the principal"):
        Reach(principal_id="   ")


def test_a_reach_cannot_name_one_department_twice() -> None:
    """A duplicate would lengthen the session setting for no reason and would make
    `membership_scope` and the setting disagree about the list's length, which is the kind of
    difference that turns into a comparison somebody writes later."""
    with pytest.raises(SearchError, match="reaches a department twice"):
        Reach(principal_id="p_ada", departments=("web", "web"))


# ==================================================== the table and the migration (0009)
def test_the_migration_follows_the_one_before_it() -> None:
    """A revision that does not chain is a migration Alembic never runs, and the symptom is a
    table missing in production while every test passes."""
    module = migration()
    assert module.revision == "0009"
    assert module.down_revision == "0008"


def _columns_added_later() -> tuple[str, ...]:
    """Columns that a migration after 0009 added to this table.

    Read from the migrations themselves rather than listed here, so adding a column is one
    file to edit. A migration that adds one declares `ADDS_COLUMNS`; one that does not touch
    columns declares nothing and is skipped.
    """
    return _declared_by_later_migrations("ADDS_COLUMNS")


def _columns_altered_later() -> tuple[str, ...]:
    """Columns `0009` created and a later migration changed the type of.

    The sibling of the tuple above and read the same way. A column here is one that `0009`
    genuinely built, so it is not missing from that migration's DDL; what has moved on is its
    declaration, which now describes what the later migration left rather than what `0009`
    made. `0027` is the only one, and it is the vector width becoming an install setting.
    """
    return _declared_by_later_migrations("ALTERS_COLUMNS")


def _declared_by_later_migrations(attribute: str) -> tuple[str, ...]:
    """Every column named by `attribute` across the migrations, in revision order.

    Read from the migrations themselves rather than listed here, so adding or altering a
    column is one file to edit. A migration that touches none declares nothing and is skipped.
    """
    found: list[str] = []
    versions = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    for path in sorted(versions.glob("*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:  # pragma: no cover - every file has both
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        found.extend(getattr(module, attribute, ()))
    return tuple(found)


def test_the_migration_builds_the_table_the_declaration_declares() -> None:
    """The migration copies the declaration rather than importing it, so the copy needs
    something comparing it or it rots without saying so.

    Compared column by column rather than on one rendered string, because 0009 built this
    table and a later migration added `embedding_model`: the model now describes the database
    and 0009 describes history, so holding one whole DDL against the other fails for being
    accurate. The columns a later migration added are read from that migration's own
    `ADDS_COLUMNS`, so adding another is one file to edit and not two.

    A column a later migration *altered* is the second case and is exempted the same way, by
    that migration's `ALTERS_COLUMNS`. `embedding` is the one: 0009 built it as `VECTOR(1536)`
    and 0027 sets it to whatever this install declared, so its declaration is 0027's business
    and the test that holds the two together is the one below. Skipping it here rather than
    asserting it is absent, because 0009 does build the column and the difference is only its
    type.

    Delete this and the migration and the declaration drift apart at the first edit, silently,
    because nothing else compares them."""
    assert migration().TABLES == ("know.chunk",)

    built = squash(rendered("upgrade"))
    added = set(_columns_added_later())
    altered = set(_columns_altered_later())

    for column in CHUNK.columns:
        if column.name in added:
            assert column.name not in built, (
                f"{column.name} is declared by a later migration and 0009 should not build it"
            )
            continue
        if column.name in altered:
            continue
        # One column's rendered definition, which carries its type, width and nullability.
        rendered_column = squash(str(CreateColumn(column).compile(dialect=POSTGRES)))
        assert rendered_column in built, f"0009 does not build {column.name} as declared"

    assert added, "no later migration adds a column; this test is comparing nothing extra"
    assert altered, "no later migration alters a column; the exemption above covers nothing"


def test_the_migration_builds_every_index_the_declaration_declares() -> None:
    """An index that exists only in the declaration is an index that is never built, and here
    that is not a performance matter: without the HNSW index there is no approximate search
    at all, so iterative scan has nothing to iterate and every vector query is a full scan
    that returns the right answer at the wrong cost."""
    up = squash(rendered("upgrade"))
    assert [index.name for index in INDEXES] == [
        "ix_chunk_tsv",
        "ix_chunk_embedding",
        "ix_chunk_reach",
        "ix_chunk_document",
    ]
    for index in INDEXES:
        assert squash(str(CreateIndex(index).compile(dialect=POSTGRES))) in up, index.name


def test_the_closed_vocabularies_are_written_from_the_enums_themselves() -> None:
    """A hand-typed list is a second copy of an enum and stops matching it the first time
    somebody adds a member, and the failure is a row the database refuses in production after
    passing every test that only exercised the Python side. 0007 exists because exactly that
    happened to the channel vocabulary."""
    checks = model_checks()
    assert checks["ck_chunk_visibility"] == "visibility IN ('company', 'department', 'personal')"
    assert checks["ck_chunk_state"] == ("state IN ('archived', 'draft', 'published', 'superseded')")
    assert checks["ck_chunk_visibility"] == migration().VISIBILITY_IN
    assert checks["ck_chunk_state"] == migration().STATE_IN


def test_a_department_visible_chunk_has_to_name_its_department() -> None:
    """It would match no branch of the reach predicate, so it would be invisible to
    everybody including its own team. That fails closed, which is the safe direction and
    exactly why nobody would ever notice it: the document is simply never an answer."""
    assert model_checks()["ck_chunk_a_department_chunk_names_its_department"] == (
        "visibility <> 'department' OR department IS NOT NULL"
    )


def test_the_rendered_pattern_survived_sqlalchemys_bind_parameter_parser() -> None:
    """**Found by rendering the DDL rather than by reading the code.** `CheckConstraint`
    wraps its argument in `sqlalchemy.text`, which reads `:name` as a bind parameter, and
    `SLUG_PATTERN` contains `(?:_[a-z0-9]+)`. The colon was taken for a parameter, bound to
    nothing, and rendered as the word NULL, so the constraint that would have shipped read
    `(?NULL[a-z0-9]+)`. It looks like a regex and it is a different regex.

    Asserted on the meaning rather than on the text, in the same form
    `test_the_pattern_handed_to_postgresql_carries_no_python_only_construct` uses: the
    rendered pattern must accept and reject exactly what the Python one does."""
    rendered_pattern = model_checks()["ck_chunk_department_is_a_slug"]
    assert "NULL[" not in rendered_pattern
    stripped = rendered_pattern.split("~ '", 1)[1].rstrip("'")
    for good in ("web", "client_ops", "operations"):
        assert re.match(stripped, good) and SLUG_RE.match(good)
    for bad in ("Web", "web-ops", "1web", "web,finance"):
        assert not re.match(stripped, bad) and not SLUG_RE.match(bad)


def test_the_migration_grants_no_delete_and_hands_the_fast_lane_nothing() -> None:
    """A retired chunk is `deleted_at`, as everywhere but 0006: "what did this document say
    before it was replaced" is asked after a wrong answer, not before one. The fast lane
    answers from the local projection without a model and has no business in the document
    plane, so 0008's grant to it has no counterpart here."""
    grants = migration().GRANTS
    assert grants == ("GRANT SELECT, INSERT, UPDATE ON know.chunk TO brain_app",)
    assert all("DELETE" not in statement for statement in grants)
    assert "brain_fastlane" not in squash(rendered("upgrade"))


def test_the_downgrade_drops_what_the_upgrade_built() -> None:
    """A migration with no way back is a deploy with no way back. `know` is not dropped: 0001
    created all nine schemas and 0001's downgrade owns them."""
    down = squash(rendered("downgrade"))
    assert "DROP TABLE know.chunk" in down
    assert "DROP SCHEMA" not in down


def test_the_migration_satisfies_the_migration_policy() -> None:
    """The mechanical rules: a downgrade that exists and does something, no unreviewed
    autogeneration markers, no schema and data change in one file."""
    assert check_file(MIGRATION) == []


def test_the_migration_changes_no_data() -> None:
    """Schema and data in one migration cannot be rolled back independently: the schema half
    reverses and the data half usually cannot. This one creates a table and nothing else."""
    emitted = squash(rendered("upgrade")).upper()
    for statement in ("INSERT INTO", "DELETE FROM"):
        assert statement not in emitted


def test_nothing_the_migration_runs_needs_a_superuser() -> None:
    """0001 creates `brain_app` NOBYPASSRLS and that is the whole reason it exists. A
    migration that quietly required more would make every policy written here decoration, and
    the tests would still pass because they would run as the same role."""
    emitted = (rendered("upgrade") + rendered("downgrade")).upper()
    for forbidden in ("SUPERUSER", "BYPASSRLS", "SET ROLE", "SECURITY DEFINER"):
        assert forbidden not in emitted


def test_the_search_table_is_registered_where_autogenerate_will_look_for_it() -> None:
    """This test asserted the opposite for the length of one build, and the inversion is the
    point rather than an embarrassment.

    The table was declared on a private registry while it was being written, because
    `brain.tables` asserts that its tuple names every table on `Base.metadata` and only
    those, and registering one without also listing it there turns a real guard into a
    failing build. Keeping it private made that a decision somebody had to take rather than
    something that happened.

    The decision has been taken: it is listed in `TABLES_IN_DEPENDENCY_ORDER` and the
    inventory test names it. What made it worth taking is concrete. `alembic revision
    --autogenerate` compares the database against `Base.metadata`, so a table absent from it
    reads as one the code no longer wants, and the proposal would have been to drop
    `know.chunk` and everything in it.

    Delete this and the table can drift back off the shared registry, which nothing else
    would notice until an autogenerated migration offered to delete the search index."""
    from brain import tables

    assert "know.chunk" in metadata.tables
    assert CHUNK.metadata is metadata
    assert "know.chunk" in tables.TABLES_IN_DEPENDENCY_ORDER


# ================================================================= fusion at the edge
def test_a_fused_page_is_drawn_from_two_lists_that_are_already_in_reach() -> None:
    """The last place the leaf could be undone. Both inputs came from queries carrying the
    reach predicate, so the fused page is in reach by construction and there is no filtering
    step here to add. A filter at this point would be the post-filter the module is written
    against, moved one layer later, with exactly the same two disclosures.

    Delete this and `hybrid` grows a `reach` argument, which reads as defence in depth."""
    lexical = tuple(f"doc_{i:04d}.0000" for i in range(20))
    vector = tuple(f"doc_{i:04d}.0000" for i in range(10, 30))
    page = hybrid(lexical=lexical, vector=vector, limit=10)
    assert len(page) == 10
    assert {item.ref for item in page} <= set(lexical) | set(vector)
    assert page[0].corroborated
    with pytest.raises(SearchError, match="asks for no results"):
        hybrid(lexical=lexical, vector=vector, limit=0)


# --------------------------- the model a vector came from, as a conjunct not a convention
def test_the_vector_leg_names_the_model_in_its_where_clause() -> None:
    """**The failure this closes has no symptom.** Changing the embedding model invalidates
    every stored vector, and old and new sit in one column under one index: every distance
    between them is a number rather than an error, so results come back confident and wrong
    and retrieval degrades instead of breaking.

    `corpus_identity` refuses a mixed corpus and can only refuse rows a caller hands it. In
    the WHERE clause the statement itself cannot span a model change, which is the same
    argument the scope predicate makes one line above it: a rule a caller has to remember is
    a rule that holds until the second caller.

    Delete this and the conjunct is a one-line simplification that no other assertion here
    would notice, because every test corpus holds one model."""
    sql = rendered_sql(vector_query(AN_EMBEDDING, reach=NARROW, model=A_MODEL))

    assert "embedding_model" in sql
    assert sql.count("SELECT") == 1, "the model must be conjoined, not applied to a subquery"


def test_the_model_is_bound_rather_than_written_into_the_statement() -> None:
    """It arrives from a corpus check, and a value reaching SQL as text is a value somebody
    eventually builds with a format string. Every other value in this statement is bound and
    this one is no different."""
    statement = vector_query(AN_EMBEDDING, reach=NARROW, model=A_MODEL)
    compiled = statement.compile(dialect=POSTGRES)

    assert A_MODEL not in str(compiled), "the model was pasted into the statement"
    assert A_MODEL in compiled.params.values()


def test_the_migrations_column_width_matches_the_declarations() -> None:
    """Two statements of one width, in two files. The migration says so in its own docstring
    and this is what makes that sentence true rather than a hope.

    Delete this and widening the declaration leaves a database column that silently truncates
    a longer model name, which reads as a model that does not match anything."""
    assert migration_module_0010().MODEL_CHARS == EMBEDDING_MODEL_CHARS


def migration_module_0010() -> ModuleType:
    """The column-adding migration, loaded the way `migration()` loads the table-building one."""
    import importlib.util

    path = (
        Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0010_embedding_model.py"
    )
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ================================ the width belongs to the install (0027, item 34)

WIDTH_MIGRATION = REPO / "migrations" / "versions" / "0027_embedding_width.py"


def width_migration() -> ModuleType:
    """The migration that sets the vector column to the width this install declared."""
    spec = importlib.util.spec_from_file_location("m0027", WIDTH_MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def width_rendered(direction: str) -> str:
    """What 0027 emits, rendered without a database, the way `rendered` does it for 0009.

    Read from the rendered SQL rather than from the file for the reason that function gives:
    a statement sitting in a constant that `upgrade` never executes passes a source-text
    search and does nothing at all, which is exactly the shape this migration's refusal would
    fail in.
    """
    buffer = io.StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": buffer, "target_metadata": metadata},
    )
    with Operations.context(context):
        getattr(width_migration(), direction)()
    return buffer.getvalue()


def test_the_width_migration_follows_the_one_before_it() -> None:
    """A revision that does not chain is a migration Alembic never runs, and here the symptom
    is a corpus column at the width a hosted model wanted while the served model produces
    another, which is the state item 34 was opened about."""
    module = width_migration()

    assert module.revision == "0027"
    assert module.down_revision == "0026"


def test_the_width_migration_sets_the_column_to_the_width_this_install_declared() -> None:
    """The end of item 34: the column is what `INSTALL_EMBEDDING_DIMENSIONS` says, and this is
    the migration that makes that sentence true of a database rather than of a Python object.

    Compared against the column's own rendered specification rather than against the number,
    so the declaration and the database are held together by the same string PostgreSQL is
    given.

    Delete this and the migration can be edited to a literal that agrees with the declaration
    on this machine and with nothing on a client's, which is the copy that goes stale."""
    emitted = squash(width_rendered("upgrade"))
    declared = cast("Any", CHUNK.c.embedding.type).get_col_spec()

    assert f"ALTER TABLE know.chunk ALTER COLUMN embedding TYPE {declared}" in emitted


def test_the_width_migration_refuses_to_move_a_column_that_already_holds_vectors() -> None:
    """**The guard that makes a configurable width safe rather than merely convenient.** A
    stored vector belongs to the model that produced it, so altering the column does not
    convert the corpus, it invalidates it. A setting that can be changed quietly is one
    somebody will change quietly, and what is lost is every embedding the company has paid
    for.

    Asserted in both directions, because a rollback is the direction nobody rehearses, and
    before the alteration in each, because a refusal after the rewrite is a message about
    something that has already happened.

    Delete this and the width becomes an environment variable somebody edits on a Friday."""
    for direction in ("upgrade", "downgrade"):
        emitted = width_rendered(direction)
        refusal = emitted.index("RAISE EXCEPTION")
        alteration = emitted.index("ALTER COLUMN embedding TYPE")

        assert "IF EXISTS (SELECT 1 FROM know.chunk WHERE embedding IS NOT NULL)" in emitted
        assert refusal < alteration, f"the {direction} alters the column before it refuses"


def test_the_refusal_asks_about_the_column_the_vectors_are_actually_in() -> None:
    """The statement is rendered from the table object rather than spelled, so a renamed table
    or column cannot leave a guard that asks a question about something that is not there.

    A `DO` block naming a table that does not exist raises rather than passing quietly, so
    this is not the failure that direction usually takes. What it would cost is worse in a
    subtler way: the refusal would fire on every install, including the empty ones, and the
    migration would become one nobody can apply.

    Delete this and the guard can be written against a column name that was right once."""
    statement = width_change_refusal(EMBEDDING_DIMENSIONS)

    assert f"{CHUNK.schema}.{CHUNK.name}" in statement
    assert f"{CHUNK.c.embedding.name} IS NOT NULL" in statement
    # Two, and they are the ones around the message. A third is an apostrophe somebody wrote
    # into the prose, which ends the quoted string early and leaves PostgreSQL parsing the
    # rest of the sentence as SQL.
    assert statement.count("'") == 2
    assert "%" not in statement, "RAISE reads a percent sign as a placeholder"


def test_the_downgrade_puts_back_the_width_the_creating_migration_built() -> None:
    """A downgrade is for the release before this one, and that release read a hardcoded 1536.
    Putting back this install's declared width instead would leave the previous release
    refusing every insert against a column it thinks it knows the size of.

    The figure is held to 0009's own constant rather than to the literal in 0027, because a
    number written in one file about another file is the copy this repository keeps finding
    rotted.

    Delete this and a rollback lands on a column width that matches neither release."""
    built_by_0009 = migration().EMBEDDING_DIMENSIONS

    assert built_by_0009 == width_migration().WIDTH_BEFORE_THIS
    assert f"ALTER TABLE know.chunk ALTER COLUMN embedding TYPE VECTOR({built_by_0009})" in squash(
        width_rendered("downgrade")
    )


def test_the_width_migration_satisfies_the_migration_policy() -> None:
    """The mechanical rules: a downgrade that exists and does something, no unreviewed
    autogeneration markers, no schema and data change in one file. This migration is the one
    most likely to look like the third, because its guard reads a table."""
    assert check_file(WIDTH_MIGRATION) == []


def test_the_width_migration_changes_no_data() -> None:
    """The guard reads the corpus and must never write to it. A migration that cleared the
    column to make its own alteration possible would be a data loss written as a convenience,
    and it would pass every other test in this file."""
    emitted = squash(width_rendered("upgrade") + width_rendered("downgrade")).upper()

    for statement in ("INSERT INTO", "DELETE FROM", "UPDATE KNOW.CHUNK", "TRUNCATE"):
        assert statement not in emitted


def test_the_width_migration_creates_no_table_and_declares_none() -> None:
    """`tests/unit/test_tables.py` compares the migrations that create tables against the
    package tuple end to end. A migration that altered a column and declared a `TABLES` slice
    anyway would be counted as creating one, and the end-to-end equality would fail with a
    table named twice.

    Delete this and the next migration to alter something copies a `TABLES` line from the one
    above it, which is how that comparison acquires a duplicate."""
    module = width_migration()

    assert not hasattr(module, "TABLES")
    assert module.ALTERS_COLUMNS == ("embedding",)
