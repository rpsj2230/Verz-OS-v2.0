"""Predicate evaluation, SQL rendering, and the capability grammar.

Task ids: M0.2.2, M0.2.3
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope


# ------------------------------------------------------------- evaluation
def test_any_matches_anything_including_an_empty_row() -> None:
    c = Clause(field="department", op=Op.ANY)
    assert c.matches({})
    assert c.matches({"department": "maintenance"})


def test_in_matches_membership_only() -> None:
    c = Clause(field="department", op=Op.IN, value=("maintenance", "web"))
    assert c.matches({"department": "web"})
    assert not c.matches({"department": "sales"})


def test_prefix_matches_the_start_of_a_value() -> None:
    """Used for hierarchical scopes like `web.projects` under `web`."""
    c = Clause(field="scope_path", op=Op.PREFIX, value="web.")
    assert c.matches({"scope_path": "web.projects"})
    assert not c.matches({"scope_path": "sales.pipeline"})


def test_values_are_compared_as_strings() -> None:
    """Rows arrive from jsonb, where a number may surface as either. Comparing as strings
    keeps a client id matching whether it came back as 4471 or "4471"."""
    c = Clause(field="client_id", op=Op.EQ, value="4471")
    assert c.matches({"client_id": 4471})


def test_field_names_must_be_lowercase_identifiers() -> None:
    """The field name reaches SQL as a jsonb key, so it is constrained rather than quoted."""
    for bad in ("Department", "department name", "department;drop", ""):
        with pytest.raises(ValidationError):
            Clause(field=bad, op=Op.EQ, value="x")


# ---------------------------------------------------------------- to_sql
def test_any_renders_as_true() -> None:
    sql, params = Clause(field="department", op=Op.ANY).to_sql("p")
    assert sql == "TRUE"
    assert params == {}


def test_in_renders_as_a_parameterised_array() -> None:
    sql, params = Clause(field="department", op=Op.IN, value=("a", "b")).to_sql("p")
    assert "= ANY(:p)" in sql
    assert params == {"p": ["a", "b"]}


def test_prefix_renders_as_like_with_the_wildcard_in_the_parameter() -> None:
    """The `%` goes in the value, never in the SQL string - otherwise a value containing
    `%` would change the shape of the query."""
    sql, params = Clause(field="scope_path", op=Op.PREFIX, value="web.").to_sql("p")
    assert "LIKE :p" in sql
    assert params == {"p": "web.%"}


def test_multiple_clauses_render_as_a_conjunction_with_distinct_parameters() -> None:
    s = Scope(
        clauses=(
            Clause(field="department", op=Op.EQ, value="maintenance"),
            Clause(field="tier", op=Op.EQ, value="managed"),
        )
    )
    sql, params = s.to_sql()
    assert sql.count("AND") == 1
    assert len(params) == 2


def test_a_custom_parameter_prefix_avoids_collisions() -> None:
    _, params = Scope.department("maintenance").to_sql("caller")
    assert list(params) == ["caller0"]


# -------------------------------------------------------- is_unrestricted
def test_empty_scope_is_unrestricted() -> None:
    assert Scope.unrestricted().is_unrestricted()


def test_a_scope_of_only_any_clauses_is_unrestricted() -> None:
    assert Scope(clauses=(Clause(field="department", op=Op.ANY),)).is_unrestricted()


def test_a_scope_with_a_real_clause_is_restricted() -> None:
    assert not Scope.department("maintenance").is_unrestricted()


# ------------------------------------------------------------- capability
def test_capability_grammar_accepts_the_real_shapes() -> None:
    for good in (
        "read:client",
        "read:client.name",
        "read:client.hours_remaining",
        "read:client.*",
        "write:ticket.status",
        "invoke:agent",
        "approve:envelope",
        "admin:grant",
    ):
        assert Capability(value=good).value == good


def test_capability_grammar_rejects_malformed_strings() -> None:
    for bad in ("read", "read:", ":client", "Read:client", "read:Client", "read client"):
        with pytest.raises(ValidationError):
            Capability(value=bad)


def test_unknown_verbs_are_rejected() -> None:
    """A typo like `reed:client.name` would otherwise create a capability nobody holds and
    nothing grants - a permanently silent refusal that looks like missing data."""
    with pytest.raises(ValidationError, match="unknown verb"):
        Capability(value="reed:client.name")


def test_verb_and_noun_are_readable_off_the_capability() -> None:
    c = Capability(value="read:client.hours_remaining")
    assert c.verb == "read"
    assert c.noun == "client"


def test_verb_and_noun_work_without_a_field() -> None:
    c = Capability(value="invoke:agent")
    assert c.verb == "invoke"
    assert c.noun == "agent"


def test_a_wildcard_does_not_cross_the_entity_boundary() -> None:
    """`read:client.*` must not reach `read:client_secret.value`."""
    assert not Capability(value="read:client.*").covers(Capability(value="read:client_secret.x"))


def test_a_narrower_capability_does_not_cover_a_wider_one() -> None:
    assert not Capability(value="read:client.name").covers(Capability(value="read:client.*"))


# ------------------------------------------- the two evaluators must admit the same rows
def test_a_prefix_wildcard_is_neutralised_before_it_reaches_like() -> None:
    """SQL LIKE reads `%` and `_`; `str.startswith` does not. Unescaped, a scope written
    to reach `web_` also reaches `webXnorth`, so a grant meant for one team reaches every
    team whose name differs by one character.

    Found by the agent building M2, reported rather than worked around, and fixed here at
    the type rather than downstream, so no caller can render an unescaped pattern.
    """
    sql, params = Clause(field="d", op=Op.PREFIX, value="web_").to_sql("p")
    assert "ESCAPE" in sql
    assert params["p"] == r"web\_%"


def test_a_percent_in_a_prefix_cannot_match_everything() -> None:
    """`web%` unescaped is "anything starting with web", which is what the author wrote,
    and `%` alone would be every row in the table."""
    _, params = Clause(field="d", op=Op.PREFIX, value="%").to_sql("p")
    assert params["p"] == r"\%%"


def test_a_backslash_is_escaped_before_the_wildcards_are() -> None:
    """Order matters: escape the escape character last and it would escape the escapes.

    `chr(92)` rather than a literal, because this exact test was first written with one
    backslash too few and passed a backspace character instead, which proves nothing.
    """
    backslash = chr(92)
    _, params = Clause(field="d", op=Op.PREFIX, value=f"a{backslash}b").to_sql("p")
    assert params["p"] == f"a{backslash}{backslash}b%"


def test_a_membership_clause_cannot_hold_a_bare_string() -> None:
    """`matches` requires a tuple and admits nothing; `to_sql` called `list("abc")` and
    admitted three values nobody wrote. The SQL side was the wider one."""
    with pytest.raises(ValidationError, match="needs a tuple"):
        Clause(field="d", op=Op.IN, value="abc")


def test_a_prefix_clause_cannot_hold_a_non_string() -> None:
    """`matches` admits nothing; `to_sql` rendered `str(None)` into `LIKE 'None%'`, which
    matches any row whose value happens to start with "None"."""
    with pytest.raises(ValidationError, match="needs a string"):
        Clause(field="d", op=Op.PREFIX, value=None)


def test_the_shapes_that_merely_match_nothing_are_still_allowed() -> None:
    """Narrow on purpose. An empty IN and an EQ against None match nothing in Python and
    nothing in SQL, so the evaluators agree and both fail closed. Refusing them here would
    be authoring-time sanity, which is a different job and a different layer."""
    assert Clause(field="d", op=Op.IN, value=()).matches({"d": "x"}) is False
    assert Clause(field="d", op=Op.EQ, value=None).matches({"d": "x"}) is False


# --------------------------------------------- the instant the invariant is evaluated at
#: Two instants far enough from any wall clock that this file can never become
#: time-dependent. That is the whole point of choosing them: the defect these tests exist
#: for was found by a fixture that expired at noon, so a fixture that could expire again
#: would be repeating the mistake rather than testing it.
LONG_AGO = datetime(2019, 1, 1, tzinfo=UTC)
LONG_AFTER = datetime(2999, 1, 1, tzinfo=UTC)

READ = Capability(value="read:client.name")


def _holder(not_after: datetime | None) -> EntitlementSet:
    """Somebody holding one capability everywhere, until a date."""
    return EntitlementSet(
        principal_id="p_holder",
        grants=(Grant(capability=READ, scope=Scope.unrestricted()),),
        not_after=not_after,
    )


def test_an_intersection_judges_the_right_hand_side_at_the_instant_it_is_given() -> None:
    """**`EntitlementSet.intersect` evaluates the right-hand side's expiry, and until
    2026-09-08 it did so against the process clock.**

    The left-hand side's expiry is not evaluated inside `intersect` at all: it is carried
    out on `not_after` and asked later by whoever calls `scope_for` on the result. The
    right-hand side's has to be asked here, because a ceiling that has run out admits
    nothing, and that one call had no instant to use.

    Here the right-hand side lapsed in 2020 and the question is being asked about 2019, so
    it had not lapsed then and the capability survives the intersection. A version reading
    the wall clock answers empty.

    Delete this and the one implementation of the platform's invariant goes back to reading
    a clock nobody handed it."""
    lapsed_in_2020 = _holder(datetime(2020, 1, 1, tzinfo=UTC))

    asking_about_2019 = _holder(None).intersect(lapsed_in_2020, LONG_AGO)

    assert asking_about_2019.scope_for(READ, LONG_AGO) is not None


def test_an_intersection_at_an_instant_after_the_right_hand_side_lapsed_admits_nothing() -> None:
    """The other direction, and the one that matters. The failure was permissive: a reader
    whose access had lapsed by the instant being reasoned about was admitted, because the
    process clock had not reached it yet.

    Four surfaces ask "may this reader be told this" as `requirement(thing).intersect(reader)`,
    which puts the real principal on the right, so this is the side their expiry was on.

    Delete this and an evaluation for a future instant admits a reader who has already gone."""
    lapses_in_2999 = _holder(LONG_AFTER)

    asking_about_3000 = _holder(None).intersect(lapses_in_2999, datetime(3000, 1, 1, tzinfo=UTC))

    assert asking_about_3000.scope_for(READ, datetime(3000, 1, 1, tzinfo=UTC)) is None
    # And the sibling: the same pair asked about an instant inside the window still holds.
    assert _holder(None).intersect(lapses_in_2999, LONG_AGO).scope_for(READ, LONG_AGO) is not None


def test_an_intersection_with_no_instant_still_answers() -> None:
    """`now` is optional, because five call sites have no instant to give and inventing one
    for them would be worse than the wall clock. Omitting it must therefore keep working
    rather than raise or return empty.

    Neither side expires here, so this asserts the default path and says nothing about which
    clock it reads.

    Delete this and making `now` required looks free."""
    both_open = _holder(None).intersect(_holder(None))

    assert both_open.scope_for(READ, LONG_AGO) is not None


def test_an_intersection_carries_the_tighter_of_the_two_time_bounds() -> None:
    """**Nothing tested this and a mutation found it: replacing the minimum with the
    left-hand side's own bound survived every test file that mentions `not_after`.**

    The comment beside the line has said since it was written that an agent ceiling with its
    own expiry, a time-boxed automation say, must not outlive either side of the
    intersection. It was a comment and not a check.

    Asserted both ways round, because a version that always takes the left-hand side and one
    that always takes the right each pass one of the two orders. And with neither side bound,
    because a version that invents a bound when there is none would refuse work nobody
    limited.

    Delete this and a run can outlive the ceiling that authorised it, which is the one
    direction an intersection is not allowed to move in."""
    until_2030 = _holder(datetime(2030, 1, 1, tzinfo=UTC))
    until_2025 = _holder(datetime(2025, 1, 1, tzinfo=UTC))

    assert until_2030.intersect(until_2025, LONG_AGO).not_after == datetime(2025, 1, 1, tzinfo=UTC)
    assert until_2025.intersect(until_2030, LONG_AGO).not_after == datetime(2025, 1, 1, tzinfo=UTC)
    assert _holder(None).intersect(_holder(None), LONG_AGO).not_after is None
