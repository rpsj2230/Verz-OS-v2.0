"""Who may connect a source, what is wrong with a connection, and what a person is told.

`brain.ops.connector_admin` is the permission decision on the Connectors screen's writes, so the
first tests here are the scopes a grant can carry: over everything, over one source, over a
department, lapsed, and absent. Each refusal has a sibling that is admitted.

Task ids: M42.6.5
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest

from brain.connectors.registry import INSTALL_AUTHORITY
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.ops.connectable import CONNECTABLE
from brain.ops.connector_admin import (
    CONNECTING_A_SOURCE,
    KEY_FIELD,
    KEY_SENTENCES,
    SOURCE_FIELD,
    TOLD,
    VAULT_SAYS,
    WHAT_CONNECTING_A_SOURCE_STARTS,
    connection_problems,
    key_problems,
    may_connect_source,
)
from brain.ops.credentials import VaultState, problems_with

#: Far outside any plausible wall clock, and a lapse far before it. See `CLAUDE.md`.
NOW: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
LAPSED: Final = datetime(2019, 1, 1, tzinfo=UTC)


def reach(*grants: Grant, not_after: datetime | None = None) -> EntitlementSet:
    return EntitlementSet(principal_id="u_reader", grants=grants, not_after=not_after)


def over(scope: Scope) -> Grant:
    return Grant(capability=INSTALL_AUTHORITY, scope=scope)


def one_clause(field: str, value: str) -> Scope:
    return Scope(clauses=(Clause(field=field, op=Op.EQ, value=value),))


# ------------------------------------------------------------------------ who may


def test_the_install_authority_over_everything_connects_every_source() -> None:
    """The positive case. Delete this and a judgement refusing everybody passes every refusal."""
    holder = reach(over(Scope.unrestricted()))

    assert all(may_connect_source(holder, name, NOW) for name in CONNECTABLE)


def test_a_grant_over_one_source_connects_that_source_and_no_other() -> None:
    """`A_GRANT_NARROWED_TO_ONE_SOURCE_CONNECTS_THAT_SOURCE`. Delete this and the scope can be
    ignored, so a grant written for one source writes every source's key."""
    holder = reach(over(one_clause(SOURCE_FIELD, "xero")))

    assert may_connect_source(holder, "xero", NOW) is True
    assert may_connect_source(holder, "hubspot", NOW) is False
    assert may_connect_source(holder, "xero_other", NOW) is False


def test_a_grant_narrowed_by_anything_but_the_source_connects_nothing() -> None:
    """A source has no department, and a missing field satisfies no clause. Delete this and a
    department administrator holding the install authority over their department writes keys for
    systems the whole company reads."""
    holder = reach(over(one_clause("department", "finance")))

    assert not any(may_connect_source(holder, name, NOW) for name in CONNECTABLE)


def test_a_lapsed_grant_a_different_capability_and_no_grant_connect_nothing() -> None:
    """The instant is the request's, so a contractor's lapsed grant still on file refuses. Delete
    this and `now` can be dropped from the call, or the capability respelled."""
    lapsed = reach(over(Scope.unrestricted()), not_after=LAPSED)
    reader = reach(Grant(capability=Capability(value="read:connector"), scope=Scope.unrestricted()))

    assert may_connect_source(lapsed, "xero", NOW) is False
    assert may_connect_source(lapsed, "xero", LAPSED.replace(year=2018)) is True
    assert may_connect_source(reader, "xero", NOW) is False
    assert may_connect_source(reach(), "xero", NOW) is False


@pytest.mark.parametrize("name", ["", "Xero", "xero/../providers", "providers/anthropic", "x y"])
def test_a_name_that_is_not_one_slot_segment_is_refused_even_to_the_widest_grant(name: str) -> None:
    """The name becomes a vault path, so a name that is not one lower-case segment is refused
    before any scope is asked. Delete this and a disconnect path could be walked into another
    slot's name by what it was sent."""
    assert may_connect_source(reach(over(Scope.unrestricted())), name, NOW) is False


# ------------------------------------------------------------------ what is wrong


def test_a_source_the_console_cannot_connect_is_one_problem_and_nothing_else_is_judged() -> None:
    """Delete this and an unknown source reaches `settings_problems` with nothing to judge by."""
    found = connection_problems("freshdesk", {"domain": "x"}, "")

    assert [(one.field, one.code) for one in found] == [(SOURCE_FIELD, "not_connectable")]


def test_the_settings_and_the_key_are_judged_together_in_field_order() -> None:
    """Delete this and a bad key is only reported once the settings are right, which is a form
    filled in twice. The positive sibling is a connection with nothing wrong."""
    both = connection_problems("xero", {}, "")
    clean = connection_problems("xero", {"tenant_id": "11111111"}, "a-key-in-one-piece")

    assert [(one.field, one.code) for one in both] == [("tenant_id", "blank"), (KEY_FIELD, "blank")]
    assert clean == ()


@pytest.mark.parametrize(
    ("value", "code"), [("", "blank"), ("a" * 1001, "too_long"), ("one two", "not_one_piece")]
)
def test_a_key_is_judged_by_the_one_judgement_and_told_in_a_source_key_s_words(
    value: str, code: str
) -> None:
    """The codes are `problems_with`'s own, so there is one rule for what a key is, and every code
    it can give has a sentence about a source's key rather than a provider's. Delete this and a
    source's key is refused with "paste the key from your provider account"."""
    assert [one.code for one in problems_with(value)] == [code]
    [told] = key_problems(value)
    assert (told.field, told.code, told.message) == (KEY_FIELD, code, KEY_SENTENCES[code])
    assert "provider" not in told.message


# ------------------------------------------------------------------ what is said


def test_every_vault_state_has_a_sentence_for_a_write_and_for_the_screen() -> None:
    """Total over `VaultState`, read off the enumeration. Delete this and a state added there
    reaches a `KeyError` inside a request."""
    for state in VaultState:
        assert TOLD[state]
    assert all(VAULT_SAYS[state] for state in VaultState if state is not VaultState.READY)
    assert VAULT_SAYS[VaultState.READY] == ""


def test_the_confirmation_says_what_connecting_starts_and_that_no_question_is_answered_yet() -> (
    None
):
    """The words a person agrees to include what connecting starts, the worker reading the source,
    and what it still does not, answering a question from it. Delete this and the confirmation can
    be shortened to the write alone, or to the read alone, which reads as the source being usable
    in an answer the moment it is connected."""
    assert WHAT_CONNECTING_A_SOURCE_STARTS in CONNECTING_A_SOURCE
    assert "worker" in WHAT_CONNECTING_A_SOURCE_STARTS
    assert "No question is answered" in WHAT_CONNECTING_A_SOURCE_STARTS
