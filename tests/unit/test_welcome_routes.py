"""The welcome route serves the three starter questions for the caller's own department only.

Task ids: M26.1.4
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from brain.core.entitlement import EntitlementSet, Grant
from brain.core.scope import Scope
from brain.identity.lifecycle import STARTER_PACK, WELCOME_QUESTIONS
from brain.welcome_routes import (
    WELCOME_FROM_DATA_PATH,
    WELCOME_PATH,
    WelcomeView,
    router,
    welcome,
    welcome_from_data,
)

#: Far from any wall clock, so no grant here can lapse while the suite runs.
NOW = datetime(2999, 1, 1, tzinfo=UTC)


def asked(department: str | None, reach: EntitlementSet) -> Any:
    principal = SimpleNamespace(primary_department=department)
    return SimpleNamespace(caller=SimpleNamespace(principal=principal), reach=reach, now=NOW)


def starter_in(department: str) -> EntitlementSet:
    return EntitlementSet(
        principal_id="p_new",
        grants=tuple(
            Grant(capability=one, scope=Scope.department(department))
            for one in STARTER_PACK.capabilities
        ),
    )


def test_a_joiner_with_the_starter_pack_is_offered_three_questions_naming_their_department() -> (
    None
):
    """The questions come from the joiner's pack and department. Delete this and the Ask page
    can go on suggesting nothing while the route returns an empty list for everybody."""
    told = asyncio.run(welcome(asked("finance", starter_in("finance"))))
    assert len(told.questions) == WELCOME_QUESTIONS
    assert all("finance" in one for one in told.questions)


def test_a_joiner_holding_the_pack_in_another_department_is_offered_nothing() -> None:
    """A pack over another department does not admit this one, so no question is offered, and
    the answer is the one a person with no pack gets. Delete this and a suggestion can name a
    department the person cannot read."""
    told = asyncio.run(welcome(asked("finance", starter_in("engineering"))))
    assert told.questions == []
    nobody = asyncio.run(welcome(asked("finance", EntitlementSet(principal_id="p_new", grants=()))))
    assert nobody == told


def test_a_person_with_no_department_or_a_department_that_is_not_a_slug_is_offered_nothing() -> (
    None
):
    """Neither can have a question scoped to them. Delete this and either raises a 500 on the
    first screen a new person sees."""
    reach = starter_in("finance")
    assert asyncio.run(welcome(asked(None, reach))).questions == []
    assert asyncio.run(welcome(asked("Not A Slug!", reach))).questions == []


def test_the_route_is_one_read_and_carries_no_count() -> None:
    """One GET at the declared path whose answer holds the questions and nothing else. Delete
    this and a count of what was withheld can be added beside the list."""
    assert [(one.path, sorted(one.methods)) for one in router.routes] == [  # type: ignore[attr-defined]
        (f"/api/v1{WELCOME_PATH}", ["GET"]),
        (f"/api/v1{WELCOME_FROM_DATA_PATH}", ["GET"]),
    ]
    assert set(WelcomeView.model_fields) == {"questions"}


class _Untouched:
    """A request that fails the test if the route reads anything from it."""

    @property
    def app(self) -> Any:
        raise AssertionError("the route read the application before it knew the department")


def test_a_department_that_is_not_a_slug_is_offered_no_question_from_data_and_nothing_is_read() -> (
    None
):
    """A person with no department, or one that is not a slug, is answered with an empty list
    before the switch, the connections or the index are read, the same answer as one who may ask
    none of them. Delete this and either reads the database for a department no question can be
    scoped to, or raises on the first screen a new person sees."""
    reach = starter_in("finance")
    for department in (None, "", "Not A Slug!"):
        told = asyncio.run(welcome_from_data(_Untouched(), asked(department, reach)))  # type: ignore[arg-type]
        assert told.questions == []
