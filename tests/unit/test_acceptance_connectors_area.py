"""The Connectors area's check: not run until a person has recorded every requirement, passing
once they have, and failing while a newest check is a failure.

The database half runs the module as the worker would, over a register of its own written for the
test, so the outcome never depends on the shipped register's rows.

Task ids: M11.8.13
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_checks_connectors_area import (
    AREA,
    CHECK_ORDER,
    SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK,
    THIS_RELEASE_CARRIES_NO_REGISTER,
)
from brain.requirement_check_routes import CHECKED_BY, NewCheck, StoredRequirementChecks
from brain.settings import settings_from
from brain.tables.requirement_check import CheckOutcome
from tests.unit.test_acceptance import at_head, checks_in
from tests.unit.test_acceptance_operations_console import _sessions

MODULE = "brain.ops.acceptance_checks_connectors_area"
NAME = "every_connectors_requirement_is_shown_working_by_a_person"

#: A register of the test's own: two connectors requirements and one of another area.
ROWS = (
    ("TEST-C-1", "Connectors"),
    ("TEST-C-2", "Connectors"),
    ("TEST-T-1", "Tools"),
)


def test_the_check_names_only_the_leaf_the_screen_asks_the_area_for() -> None:
    """Held against the Requirement checks screen's own map, which the module does not import.
    Delete this and the area can be renamed on the screen while this check keeps looking for a
    name the register no longer carries, and the leaf then says not run for ever."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {NAME: ("M11.8.13",)}
    assert checks_in(MODULE) == [NAME]
    assert CHECKED_BY[AREA] == "M11.8.13"


def test_the_module_sits_in_the_range_this_package_was_given_and_its_sentences_fit() -> None:
    """The coordinator gave this package the keys 1200 to 1299, and a reason is stored whole.
    Delete this and a key outside the range collides with another package's, or a reason is cut
    short on the Install page."""
    assert 1200 <= CHECK_ORDER <= 1299
    assert len(THIS_RELEASE_CARRIES_NO_REGISTER) <= REASON_CHARS
    assert len(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK) <= REASON_CHARS


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_connectors_area") as url:
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
                        "leaves": ["M11.8.13"],
                        "proof": ["M11.8.13"],
                        "decision": None,
                    }
                    for one, area in ROWS
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(screen, "DOCS", tmp_path)


def run_area(url: str) -> tuple[str, str]:
    from brain.db import normalise_database_url

    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings_from({"BRAIN_DATABASE_URL": url}),
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    [one] = results
    return one.outcome, one.reason


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
def test_the_check_says_not_run_until_a_person_has_recorded_every_requirement(
    install: str, register: None
) -> None:
    """No recorded check, then one of two recorded as passed: both say not run, in the one
    sentence about it. A requirement of another area recorded as passed changes nothing. Delete
    this and a leaf asking a person to demonstrate every requirement closes on the first one a
    person passes."""
    assert run_area(install) == (NOT_RUN, SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)
    record(install, "TEST-C-1", CheckOutcome.PASSED)
    record(install, "TEST-T-1", CheckOutcome.PASSED)
    assert run_area(install) == (NOT_RUN, SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)


@pytest.mark.needs_db
def test_the_check_passes_when_every_requirement_has_a_newest_pass(
    install: str, register: None
) -> None:
    """Both requirements passed. Delete this and the check is satisfied by a function that never
    passes, which no leaf can then close on."""
    record(install, "TEST-C-1", CheckOutcome.PASSED)
    record(install, "TEST-C-2", CheckOutcome.PASSED)
    assert run_area(install) == (PASSED, "")


@pytest.mark.needs_db
def test_a_failing_newest_check_fails_the_area_until_a_person_passes_it_again(
    install: str, register: None
) -> None:
    """A failure recorded after a pass fails the check, in a sentence naming no requirement, and a
    later pass makes it pass without the failure being edited away. Delete this and a requirement
    somebody saw break stays counted as demonstrated by the pass before it."""
    record(install, "TEST-C-2", CheckOutcome.FAILED)
    outcome, reason = run_area(install)
    assert outcome == FAILED and "TEST-C" not in reason
    record(install, "TEST-C-2", CheckOutcome.PASSED)
    assert run_area(install) == (PASSED, "")


@pytest.mark.needs_db
def test_a_release_with_no_connectors_requirements_says_so(
    install: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty register directory. Delete this and a release carrying no register passes or
    fails the leaf instead of saying it cannot be asked."""
    from brain import requirement_check_routes as screen

    monkeypatch.setattr(screen, "DOCS", tmp_path)
    assert run_area(install) == (NOT_RUN, THIS_RELEASE_CARRIES_NO_REGISTER)
