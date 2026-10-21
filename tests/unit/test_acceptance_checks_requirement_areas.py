"""The install checks for five areas' "demonstrated on an install by a person" leaves, passing on
PostgreSQL once people have recorded their checks and refusing to pass before.

The pure half holds the module against the screen it reads: the five areas are the five the screen
names for these leaves, and the key sits in the range this package was given. The database half
runs the module as the worker would, over a register of its own written for the test, and shows
each outcome: not run while a requirement has no recorded check, failed when the newest check is a
failure, passed only when every requirement of the area has a newest pass, and a later pass
superseding an earlier failure without the earlier row being edited.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M1.8.8, M2.3.2, M5.6.5, M24.3.6, M27.15.12
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_checks_requirement_areas import (
    AREAS,
    SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK,
    THIS_RELEASE_CARRIES_NO_REGISTER,
)
from brain.requirement_check_routes import CHECKED_BY, NewCheck, StoredRequirementChecks
from brain.settings import settings_from
from brain.tables.requirement_check import CheckOutcome
from tests.unit.test_acceptance import at_head, checks_in
from tests.unit.test_acceptance_operations_console import _sessions

MODULE = "brain.ops.acceptance_checks_requirement_areas"
PERMISSIONS = "every_permissions_requirement_is_shown_working_by_a_person"
DEPARTMENTS = "every_departments_requirement_is_shown_working_by_a_person"
MODELS = "every_models_requirement_is_shown_working_by_a_person"
OBSERVABILITY = "every_observability_requirement_is_shown_working_by_a_person"
CONSOLE = "every_console_requirement_is_shown_working_by_a_person"

#: A register of the test's own, so the outcome never depends on the shipped register's rows.
ROWS = (
    ("TEST-P-1", "Permissions"),
    ("TEST-P-2", "Permissions"),
    ("TEST-M-1", "Models"),
    ("TEST-C-1", "Console"),
)


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_for_each_of_the_five_leaves() -> None:
    """One check per leaf, each naming only its own. Delete this and one check can name two
    leaves, so one area's failure holds another area's leaf open, or lose a leaf the page shows."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        PERMISSIONS: ("M1.8.8",),
        DEPARTMENTS: ("M2.3.2",),
        MODELS: ("M5.6.5",),
        OBSERVABILITY: ("M24.3.6",),
        CONSOLE: ("M27.15.12",),
    }
    assert sorted(checks_in(MODULE)) == sorted(
        [PERMISSIONS, DEPARTMENTS, MODELS, OBSERVABILITY, CONSOLE]
    )


def test_the_five_areas_are_the_five_the_screen_names_for_these_leaves() -> None:
    """Held against the Requirement checks screen's own map, which the module does not import.
    Delete this and an area can be renamed on the screen while this check keeps looking for a
    name the register no longer carries, and the leaf then says not run for ever."""
    assert {area: CHECKED_BY[area] for area in AREAS} == AREAS
    assert set(AREAS) == {"Permissions", "Departments", "Models", "Observability", "Console"}


def test_the_module_sits_in_the_range_this_package_was_given() -> None:
    """The coordinator gave this package the keys 600 to 699, so two packages cannot share one.
    Delete this and a key outside the range is not noticed until two modules collide."""
    from brain.ops import acceptance_checks_requirement_areas as module

    assert 600 <= module.CHECK_ORDER <= 699


def test_the_sentences_a_check_may_end_with_fit_the_result() -> None:
    """Stored whole. Delete this and why the check was not run is cut short on the Install page."""
    assert len(THIS_RELEASE_CARRIES_NO_REGISTER) <= REASON_CHARS
    assert len(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK) <= REASON_CHARS


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    """A database at head, as the application leaves it. Nothing is furnished for these checks."""
    with at_head("brain_acceptance_req_areas") as url:
        yield url


@pytest.fixture
def register(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The test's own register in the place the screen reads it from."""
    from brain import requirement_check_routes as screen
    from brain.requirements import REGISTER_IN_DOCS

    path = tmp_path / REGISTER_IN_DOCS
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "requirements": [
                    {
                        "id": one,
                        "source": "test",
                        "area": area,
                        "requirement": "A requirement written for this test.",
                        "leaves": ["M1.8.8"],
                        "proof": ["M1.8.8"],
                        "decision": None,
                    }
                    for one, area in ROWS
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(screen, "DOCS", tmp_path)


def run_areas(url: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def record(url: str, requirement: str, outcome: CheckOutcome) -> None:
    store = StoredRequirementChecks(_sessions(url))
    asyncio.run(
        store.record(
            NewCheck(
                requirement_id=requirement,
                outcome=outcome,
                checked_by="acceptance.test.person",
                release_commit=None,
                note="Walked it on a scratch database for the test.",
            )
        )
    )


@pytest.mark.needs_db
def test_the_checks_say_not_run_until_a_person_has_recorded_every_requirement(
    install: str, register: None
) -> None:
    """With no recorded check, the two areas the test's register holds say not run in the one
    sentence about it, and the two it does not hold say so in the other. Then one of two
    permissions requirements recorded as passed still says not run. Delete this and a leaf
    asking a person to demonstrate every requirement closes on the first one a person passes."""
    first = run_areas(install)
    assert first[PERMISSIONS] == (NOT_RUN, SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)
    assert first[MODELS] == (NOT_RUN, SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)
    assert first[DEPARTMENTS] == (NOT_RUN, THIS_RELEASE_CARRIES_NO_REGISTER)
    assert first[OBSERVABILITY] == (NOT_RUN, THIS_RELEASE_CARRIES_NO_REGISTER)
    assert first[CONSOLE] == (NOT_RUN, SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)
    record(install, "TEST-P-1", CheckOutcome.PASSED)
    assert run_areas(install)[PERMISSIONS] == (NOT_RUN, SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)


@pytest.mark.needs_db
def test_an_area_passes_when_every_requirement_has_a_newest_pass_and_no_other_area_does(
    install: str, register: None
) -> None:
    """Both permissions requirements passed: that check passes and the models one, with its
    requirement unchecked, still says not run. Delete this and the check is satisfied by a
    function that never passes, which no leaf can then close on."""
    record(install, "TEST-P-1", CheckOutcome.PASSED)
    record(install, "TEST-P-2", CheckOutcome.PASSED)
    results = run_areas(install)
    assert results[PERMISSIONS] == (PASSED, "")
    assert results[MODELS][0] == NOT_RUN


@pytest.mark.needs_db
def test_a_failing_newest_check_fails_the_area_until_a_person_passes_it_again(
    install: str, register: None
) -> None:
    """A failure recorded after a pass fails the check, in a sentence naming no requirement, and a
    later pass makes it pass without the failure being edited away. Delete this and a requirement
    somebody saw break stays counted as demonstrated by the pass before it."""
    record(install, "TEST-P-1", CheckOutcome.PASSED)
    record(install, "TEST-P-2", CheckOutcome.PASSED)
    record(install, "TEST-P-1", CheckOutcome.FAILED)
    outcome, reason = run_areas(install)[PERMISSIONS]
    assert outcome == FAILED
    assert "TEST-P-1" not in reason
    record(install, "TEST-P-1", CheckOutcome.PASSED)
    assert run_areas(install)[PERMISSIONS] == (PASSED, "")


@pytest.mark.needs_db
def test_the_console_area_passes_on_its_own_requirements_and_fails_on_a_failing_one(
    install: str, register: None
) -> None:
    """The console's one requirement, passed by a person, passes the console's check and leaves
    the models one, whose requirement nobody has recorded, waiting; a failure recorded after it
    fails the console's check alone.
    Delete this and the console's leaf is either never reachable or is held by another area."""
    record(install, "TEST-C-1", CheckOutcome.PASSED)
    results = run_areas(install)
    assert results[CONSOLE] == (PASSED, "")
    assert results[MODELS][0] == NOT_RUN
    record(install, "TEST-C-1", CheckOutcome.FAILED)
    outcome, reason = run_areas(install)[CONSOLE]
    assert outcome == FAILED
    assert "TEST-C-1" not in reason
