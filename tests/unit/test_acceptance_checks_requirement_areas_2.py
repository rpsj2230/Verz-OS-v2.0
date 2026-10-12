"""The install checks for five more areas' "demonstrated on an install by a person" leaves.

Held against the Requirement checks screen's own map, and run as the worker would over a register
of the test's own: not run while a requirement has no recorded check, failed when the newest check
is a failure, passed only when every requirement of the area has a newest pass.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M13.8.12, M13.8.14, M14.8.2, M16.7.11, M16.7.9
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_checks_requirement_areas_2 import (
    AREAS,
    SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK,
    THIS_RELEASE_CARRIES_NO_REGISTER,
)
from brain.requirement_check_routes import CHECKED_BY, NewCheck, StoredRequirementChecks
from brain.settings import settings_from
from brain.tables.requirement_check import CheckOutcome
from tests.unit.test_acceptance import at_head, checks_in
from tests.unit.test_acceptance_operations_console import _sessions

MODULE = "brain.ops.acceptance_checks_requirement_areas_2"
AGENTS = "every_agents_requirement_is_shown_working_by_a_person"
HARNESS = "every_harness_requirement_is_shown_working_by_a_person"
ENTITY = "every_entity_resolution_requirement_is_shown_working_by_a_person"
MEMORY = "every_memory_requirement_is_shown_working_by_a_person"
LEARNING = "every_learning_requirement_is_shown_working_by_a_person"

#: A register of the test's own, so the outcome never depends on the shipped register's rows.
ROWS = (("TEST-A-1", "Agents"), ("TEST-A-2", "Agents"), ("TEST-M-1", "Memory"))


def test_the_module_declares_one_check_for_each_of_the_five_leaves() -> None:
    """One check per leaf, each naming only its own. Delete this and one check can name two
    leaves, so one area's failure holds another area's leaf open, or a leaf is lost."""
    assert {one.name: one.leaves for one in registered((MODULE,))} == {
        AGENTS: ("M13.8.12",),
        HARNESS: ("M13.8.14",),
        ENTITY: ("M14.8.2",),
        MEMORY: ("M16.7.11",),
        LEARNING: ("M16.7.9",),
    }
    assert sorted(checks_in(MODULE)) == sorted([AGENTS, HARNESS, ENTITY, MEMORY, LEARNING])


def test_the_five_areas_are_the_five_the_screen_names_for_these_leaves() -> None:
    """Held against the screen's own map, which the module does not import. Delete this and an
    area can be renamed on the screen while this check looks for a name the register no longer
    carries, and the leaf says not run for ever."""
    assert {area: CHECKED_BY[area] for area in AREAS} == AREAS
    assert len(AREAS) == 5


def test_the_module_sits_in_the_range_this_package_was_given() -> None:
    """The coordinator gave this package the keys 800 to 899. Delete this and a key outside the
    range is not noticed until two modules collide."""
    from brain.ops import acceptance_checks_requirement_areas_2 as module

    assert 800 <= module.CHECK_ORDER <= 899


def test_the_sentences_a_check_may_end_with_fit_the_result() -> None:
    """Stored whole. Delete this and why a check was not run is cut short on the Install page."""
    assert len(THIS_RELEASE_CARRIES_NO_REGISTER) <= REASON_CHARS
    assert len(SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK) <= REASON_CHARS


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_req_areas_2") as url:
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
                        "leaves": ["M13.8.12"],
                        "proof": ["M13.8.12"],
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
    """With nothing recorded, the two areas the test's register holds say not run in the one
    sentence about it and the three it does not hold say so in the other; one of two agents
    requirements passed still says not run. Delete this and a leaf asking a person to demonstrate
    every requirement closes on the first one a person passes."""
    first = run_areas(install)
    assert first[AGENTS] == (NOT_RUN, SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)
    assert first[MEMORY] == (NOT_RUN, SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)
    for absent in (HARNESS, ENTITY, LEARNING):
        assert first[absent] == (NOT_RUN, THIS_RELEASE_CARRIES_NO_REGISTER)
    record(install, "TEST-A-1", CheckOutcome.PASSED)
    assert run_areas(install)[AGENTS] == (NOT_RUN, SOME_REQUIREMENT_HAS_NO_RECORDED_CHECK)


@pytest.mark.needs_db
def test_an_area_passes_only_when_every_requirement_has_a_newest_pass_and_a_failure_fails_it(
    install: str, register: None
) -> None:
    """Both agents requirements passed: that check passes and memory, unchecked, does not. A
    failure after a pass fails it in words naming no requirement, and a later pass restores it.
    Delete this and the check is satisfied by a function that never passes, or one that forgets
    a requirement somebody saw break."""
    record(install, "TEST-A-1", CheckOutcome.PASSED)
    record(install, "TEST-A-2", CheckOutcome.PASSED)
    results = run_areas(install)
    assert results[AGENTS] == (PASSED, "")
    assert results[MEMORY][0] == NOT_RUN
    record(install, "TEST-A-1", CheckOutcome.FAILED)
    outcome, reason = run_areas(install)[AGENTS]
    assert outcome == FAILED
    assert "TEST-A-1" not in reason
    record(install, "TEST-A-1", CheckOutcome.PASSED)
    assert run_areas(install)[AGENTS] == (PASSED, "")
