"""What the routes for a connector added from the console ask, refuse and show.

`brain.custom_connector_routes` asks the authority a connection asks before anything is judged,
tells a submitter in words that they cannot approve their own, and shows a definition whole only to
a reader who may connect it. These tests drive the functions the routes call over a store that keeps
definitions in memory, so what is held is the routes' own decisions; the store's are held against a
database in `test_custom_connector_store.py`, and the whole path in the install check.

Task ids: M11.7.8
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Final, cast

import pytest

from brain.connectors.registry import INSTALL_AUTHORITY
from brain.core.entitlement import EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Clause, Op, Scope
from brain.custom_connector_routes import (
    DEFINITION_PATH,
    DEFINITIONS_PATH,
    REVIEW_PATH,
    ReviewAsked,
    deciding,
    submission,
    view_of,
)
from brain.ops.acceptance_checks_custom_connector import made_up_definition
from brain.ops.custom_connector import ReviewState
from brain.ops.custom_connector_store import (
    NOBODY_APPROVES_THEIR_OWN_DEFINITION,
    OwnDefinitionError,
    StoredCustomConnectors,
    StoredDefinition,
)
from tests.fixtures.scratch_postgres import run
from tests.unit.test_custom_connector import ENTITY, _Resolver

NAME: Final = "widgets_api"
DEPARTMENT: Final = "finance"
#: Far from any wall clock, because nothing here is about the present.
NOW: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)


def reach(principal_id: str, *, connects: str | None) -> EntitlementSet:
    """A reader holding the connect authority for `connects`, or holding nothing."""
    grants: tuple[Grant, ...] = ()
    if connects is not None:
        where = Scope(clauses=(Clause(field="connector", op=Op.EQ, value=connects),))
        grants = (Grant(capability=INSTALL_AUTHORITY, scope=where),)
    return EntitlementSet(principal_id=principal_id, grants=grants)


class _Kept:
    """`StoredCustomConnectors` in memory, refusing a self-approval as the real one does."""

    def __init__(self) -> None:
        self.kept: dict[str, StoredDefinition] = {}

    async def listed(self) -> tuple[StoredDefinition, ...]:
        return tuple(self.kept.values())

    async def submit(self, definition: Any, *, by: str, **_: Any) -> StoredDefinition:
        one = StoredDefinition(
            definition=definition,
            state=ReviewState.UNREVIEWED,
            submitted_by=by,
            submitted_at=NOW,
        )
        self.kept[definition.name] = one
        return one

    async def decide(self, name: str, *, approve: bool, by: str, **_: Any) -> StoredDefinition:
        one = self.kept[name]
        if one.submitted_by == by:
            raise OwnDefinitionError(NOBODY_APPROVES_THEIR_OWN_DEFINITION)
        state = ReviewState.APPROVED if approve else ReviewState.REJECTED
        self.kept[name] = replace(one, state=state, reviewed_by=by, reviewed_at=NOW)
        return self.kept[name]


def store() -> StoredCustomConnectors:
    # The routes call five methods of the store, and `_Kept` has the three these tests reach.
    return cast("StoredCustomConnectors", _Kept())


def submitted(kept: StoredCustomConnectors, by: EntitlementSet) -> Any:
    body = made_up_definition(NAME, ENTITY, DEPARTMENT)
    return run(lambda: submission(kept, body, reach=by, now=NOW, resolver=_Resolver()))


def test_a_caller_without_the_connect_authority_is_refused_and_one_with_it_is_kept() -> None:
    """Asked before anything is judged, for the definition's own name. Delete this and anybody
    signed in can submit a connector that reads the company's data once somebody approves it."""
    kept = store()
    with pytest.raises(Absent):
        submitted(kept, reach("u_nobody", connects=None))
    with pytest.raises(Absent):
        submitted(kept, reach("u_elsewhere", connects="another_api"))
    one = submitted(kept, reach("u_definer", connects=NAME))
    assert isinstance(one, StoredDefinition)
    assert (one.state, one.submitted_by) == (ReviewState.UNREVIEWED, "u_definer")


def test_a_submitter_is_told_in_words_that_they_cannot_approve_their_own() -> None:
    """A 422 with `own_definition` and the reason, and a second person's approval beside it.
    Delete this and a refused self-approval reads as the console's one refusal, a fault, or the
    approval goes through."""
    kept = store()
    definer = reach("u_definer", connects=NAME)
    submitted(kept, definer)
    asked = ReviewAsked(approve=True, revision=1)
    own = run(lambda: deciding(kept, NAME, asked, reach=definer, now=NOW))
    assert isinstance(own, tuple)
    assert [(one.code, one.message) for one in own] == [
        ("own_definition", NOBODY_APPROVES_THEIR_OWN_DEFINITION)
    ]
    second = run(lambda: deciding(kept, NAME, asked, reach=reach("u_rev", connects=NAME), now=NOW))
    assert isinstance(second, StoredDefinition)
    assert (second.state, second.reviewed_by) == (ReviewState.APPROVED, "u_rev")


def test_a_definition_is_shown_whole_only_to_a_reader_who_may_connect_it() -> None:
    """The document is what a reviewer approves, so it is shown to the people who may, and the
    review button only to one who did not submit it. Delete this and a reader of the Connectors
    screen reads every pasted specification, or a submitter is offered their own approval."""
    kept = store()
    one = submitted(kept, reach("u_definer", connects=NAME))
    assert view_of(one, reach("u_reader", connects=None), NOW).document is None
    theirs = view_of(one, reach("u_definer", connects=NAME), NOW)
    assert theirs.document is not None
    assert theirs.reviewable is False
    other = view_of(one, reach("u_rev", connects=NAME), NOW)
    assert (other.reviewable, other.offered) == (True, False)


def test_the_router_answers_each_path_and_the_application_mounts_it() -> None:
    """Delete this and a router written and never mounted is the console's submit form posting to
    an address that answers 404."""
    from brain.api import API_PREFIX
    from brain.routers import ROUTERS

    mounted = {
        (getattr(route, "path", ""), method)
        for router in ROUTERS
        for route in router.routes
        for method in getattr(route, "methods", ())
    }
    for path, method in (
        (DEFINITIONS_PATH, "GET"),
        (DEFINITIONS_PATH, "POST"),
        (DEFINITION_PATH, "POST"),
        (REVIEW_PATH, "POST"),
    ):
        assert (API_PREFIX + path, method) in mounted
