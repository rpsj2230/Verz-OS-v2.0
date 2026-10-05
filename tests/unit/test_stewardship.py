"""Which stewarded things a grant somebody made to themselves reaches, and who is told of it.

`brain.identity.stewardship` in isolation: capabilities that touch, scopes that admit, a source
reached by reaching any of its records, and the notice list a steward is given. Every refusal
has a sibling proving the thing it refuses still works.

Task ids: M7.7.2
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from brain.core.entitlement import Capability
from brain.core.scope import Clause, Op, Scope
from brain.identity.stewardship import (
    NOTICE_WINDOW,
    SelfGrant,
    Stewarded,
    StewardedKind,
    admits,
    notices_for,
    reaches,
    touches,
)

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)

READ_KNOWLEDGE: Final = Capability(value="read:knowledge")
READ_TICKETS: Final = Capability(value="read:ticket.*")


def cap(value: str) -> Capability:
    return Capability(value=value)


def document(steward: str, *, department: str = "web", object_id: str = "d1") -> Stewarded:
    return Stewarded(
        kind=StewardedKind.DOCUMENT,
        object_id=object_id,
        label=f"document {object_id}",
        steward_id=steward,
        row={"document_id": object_id, "visibility": "department", "department": department},
        reached_by=(READ_KNOWLEDGE,),
    )


def source(steward: str, *, name: str = "freshdesk") -> Stewarded:
    return Stewarded(
        kind=StewardedKind.SOURCE,
        object_id=name,
        label=name,
        steward_id=steward,
        row={"connector": name},
        reached_by=(READ_TICKETS,),
        partial=True,
    )


def grant(
    principal: str,
    *capabilities: str,
    scope: Scope | None = None,
    at: datetime = LONG_AGO,
    grant_id: str = "g1",
) -> SelfGrant:
    return SelfGrant(
        grant_id=grant_id,
        principal_id=principal,
        capabilities=tuple(cap(one) for one in capabilities),
        scope=scope or Scope.unrestricted(),
        at=at,
    )


# ------------------------------------------------------------------------------ touches
@pytest.mark.parametrize(
    "granted",
    ["read:knowledge", "read:knowledge.*", "read:knowledge.document", "read:knowledge.a.b"],
)
def test_a_grant_on_the_capability_its_wildcard_or_one_of_its_fields_touches_it(
    granted: str,
) -> None:
    """The positive half: the capability itself, its wildcard, and a field under it are all
    somebody reading the thing. Delete this and a field-level self-grant, the narrow-looking
    one a person would make to stay unnoticed, is told to nobody."""
    assert touches(cap(granted), READ_KNOWLEDGE)


@pytest.mark.parametrize("granted", ["read:knowledgebase", "write:knowledge", "read:client.*"])
def test_a_grant_on_a_neighbouring_name_does_not_touch_it(granted: str) -> None:
    """The sibling: a capability that merely starts with the same letters, or another verb, is
    not a read of the thing. Delete this and `touches` can answer yes for everything, which the
    positive test above would not notice."""
    assert not touches(cap(granted), READ_KNOWLEDGE)


def test_a_wildcard_base_is_touched_by_a_field_under_it() -> None:
    """A thing reached through `read:ticket.*` is touched by a grant of one ticket field. Delete
    this and a source's steward misses the grant of `read:ticket.subject`."""
    assert touches(cap("read:ticket.subject"), READ_TICKETS)
    assert not touches(cap("read:tickets"), READ_TICKETS)


# ------------------------------------------------------------------------------- admits
def test_a_documents_scope_is_judged_by_the_scope_rule_every_read_uses() -> None:
    """A department-scoped grant admits the document in that department and not the one in
    another. Delete this and a steward is told of grants that cannot read their document."""
    web = Scope.department("web")
    assert admits(web, document("u_s", department="web"))
    assert not admits(web, document("u_s", department="finance"))


def test_a_clause_on_a_field_a_document_does_not_carry_admits_nothing() -> None:
    """`Scope.matches` refuses a missing field, and a document is not partial, so a clause on
    `owner_id` against a row without one admits nothing. Delete this and the strict half of
    `admits` could read a document as partial."""
    only_mine = Scope(clauses=(Clause(field="owner_id", op=Op.EQ, value="u_x"),))
    assert not admits(only_mine, document("u_s"))


def test_a_source_is_reached_by_a_grant_scoped_to_part_of_its_records() -> None:
    """`A_SOURCE_IS_REACHED_BY_REACHING_ANY_OF_ITS_RECORDS`: a department clause, which the
    source's row cannot carry, still reaches some of its records. Delete this and a
    department-scoped grant of `read:ticket.*` passes unseen by the person who stewards the
    tickets."""
    assert admits(Scope.department("support"), source("u_s"))


def test_a_source_is_not_reached_by_a_grant_pinned_to_another_source() -> None:
    """The sibling: a clause on the field the source's row does carry is still judged. Delete
    this and every grant scoped to one source is told to every source's steward."""
    elsewhere = Scope(clauses=(Clause(field="connector", op=Op.EQ, value="hubspot"),))
    assert not admits(elsewhere, source("u_s", name="freshdesk"))
    assert admits(elsewhere, source("u_s", name="hubspot"))


# ------------------------------------------------------------------------------ reaches
def test_a_grant_reaches_a_thing_only_when_both_the_capability_and_the_scope_do() -> None:
    """Both halves are needed. Delete this and `reaches` can be either half alone."""
    thing = document("u_s", department="web")
    assert reaches(grant("u_x", "read:knowledge.*", scope=Scope.department("web")), thing)
    assert not reaches(grant("u_x", "read:client.*", scope=Scope.department("web")), thing)
    assert not reaches(grant("u_x", "read:knowledge.*", scope=Scope.department("hr")), thing)


# ---------------------------------------------------------------------------- notices_for
def test_a_steward_is_told_of_a_grant_somebody_else_made_that_reaches_their_thing() -> None:
    """The positive case the whole leaf exists for. Delete this and `notices_for` can return
    nothing for every steward."""
    told = notices_for("u_s", [grant("u_x", "read:knowledge.*")], [document("u_s")])
    assert [(one.grant.principal_id, [t.object_id for t in one.reached]) for one in told] == [
        ("u_x", ["d1"])
    ]


def test_a_steward_is_not_told_of_their_own_grant() -> None:
    """`A_STEWARD_IS_NOT_TOLD_OF_THEIR_OWN_GRANT`. Delete this and a steward's list fills with
    the grants they made themselves, burying the one somebody else made."""
    assert notices_for("u_s", [grant("u_s", "read:knowledge.*")], [document("u_s")]) == ()


def test_a_notice_names_only_the_things_its_reader_stewards() -> None:
    """`A_NOTICE_NAMES_ONLY_WHAT_ITS_READER_STEWARDS`: one grant reaching two stewards' documents
    is told to each with their own document only, and a person who stewards nothing it reaches
    is told nothing. Delete this and a notice discloses another steward's document, which the
    reader may not be able to see."""
    things = [document("u_s", object_id="mine"), document("u_t", object_id="theirs")]
    wide = [grant("u_x", "read:knowledge.*")]

    [told] = notices_for("u_s", wide, things)
    assert [one.object_id for one in told.reached] == ["mine"]
    [other] = notices_for("u_t", wide, things)
    assert [one.object_id for one in other.reached] == ["theirs"]
    assert notices_for("u_nobody", wide, things) == ()


def test_notices_are_newest_first() -> None:
    """Delete this and the grant made this morning can sit under ninety days of older ones."""
    older = grant("u_x", "read:knowledge.*", at=LONG_AGO, grant_id="g_old")
    newer = grant("u_y", "read:knowledge.*", at=LONG_AGO + timedelta(days=1), grant_id="g_new")
    told = notices_for("u_s", [older, newer], [document("u_s")])
    assert [one.grant.grant_id for one in told] == ["g_new", "g_old"]


def test_the_notice_window_is_a_quarter() -> None:
    """The access review's own interval, so every self-grant since the last review is on the
    list when the next one runs. Delete this and the window can shrink to a day, after which a
    steward who reads their list weekly misses most of what they were meant to be told."""
    assert timedelta(days=89) < NOTICE_WINDOW <= timedelta(days=92)


def test_a_stewarded_thing_names_itself_its_steward_and_what_reaches_it() -> None:
    """Delete this and a thing with no steward, or reached by no capability, is judged: the
    first is told to nobody and the second is reached by nothing, both silently."""
    with pytest.raises(ValueError, match="names itself and its steward"):
        document("")
    with pytest.raises(ValueError, match="names no capability"):
        Stewarded(
            kind=StewardedKind.AGENT,
            object_id="a1",
            label="an agent",
            steward_id="u_s",
            row={},
            reached_by=(),
        )
