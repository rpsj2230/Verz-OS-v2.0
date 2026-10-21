"""The install checks for what a person pastes from the old system, each passing on PostgreSQL at
head and failing with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M37.1.2.1, M37.1.2.2, M37.1.2.3, M37.1.2.4, M37.2.2.2, M37.2.2.4, M37.2.2.5, M37.2.3.4
Task ids: M37.2.4.2, M37.2.4.3
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_migration_convert"
SKILLS = "pasted_skills_are_converted_and_nothing_is_imported"
CARRY = "a_pasted_export_is_planned_compared_and_archived"
LEARNING = "a_conclusion_is_re_derived_and_a_widening_is_refused"
AUDIENCE = "availability_is_mapped_and_never_defaulted"
WRITTEN = ("ops.setting", "ops.migration_record")


def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Delete this and a check can lose a leaf with the Install page showing the same rows."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (SKILLS, ("M37.2.2.2", "M37.2.2.4", "M37.2.2.5")),
        (CARRY, ("M37.1.2.1", "M37.1.2.2", "M37.1.2.3", "M37.1.2.4")),
        (LEARNING, ("M37.2.4.2", "M37.2.4.3")),
        (AUDIENCE, ("M37.2.3.4",)),
    ]
    assert checks_in(MODULE) == [SKILLS, CARRY, LEARNING, AUDIENCE]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_migration_convert") as url:
        yield url


def run_module(url: str, *names: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    checks = [one for one in registered((MODULE,)) if not names or one.name in names]
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=checks,
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    both.update({one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN})  # noqa: S608
    return both


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All four pass and no register, switch or setting is
    left. Delete this and a check that can never pass on a real schema, or that leaves a register
    on the owner's install, reaches it."""
    before = _counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 4
    assert _counts(install) == before


@pytest.mark.needs_db
def test_a_conversion_open_to_anybody_fails_the_skills_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The authority check removed. Delete this and a department-scoped holder converts skills."""
    from brain import migration_convert_routes as routes
    from brain.ops import acceptance_checks_migration_convert as module

    monkeypatch.setattr(routes, "may_run_a_migration", lambda *_: True)
    assert _failed(install, SKILLS) == module.THE_ROUTES_WERE_OPEN_TO_ANYBODY


@pytest.mark.needs_db
def test_a_conversion_that_ignores_the_switch_fails_the_skills_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch read as always on. Delete this and the routes work on an install that did not
    turn a migration on."""
    from brain import migration_convert_routes as routes
    from brain.ops import acceptance_checks_migration_convert as module

    async def always(_session: Any) -> None:
        return None

    monkeypatch.setattr(routes, "_switched_on", always)
    assert _failed(install, SKILLS) == module.THE_ROUTES_IGNORED_THE_SWITCH


@pytest.mark.needs_db
def test_a_preamble_that_is_kept_fails_the_skills_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The conversion removed. Delete this and a description written at a router is offered
    unchanged."""
    from brain.migration import skills
    from brain.ops import acceptance_checks_migration_convert as module

    monkeypatch.setattr(skills, "proposed_description", lambda foreign: foreign.description)
    assert _failed(install, SKILLS) == module.A_ROUTER_PREAMBLE_WAS_KEPT


@pytest.mark.needs_db
def test_vectors_that_are_not_named_as_discarded_fail_the_carry_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Delete this and a vector shipped with an export is carried without anybody saying so."""
    from brain.migration import carry
    from brain.ops import acceptance_checks_migration_convert as module

    monkeypatch.setattr(carry, "carried_vectors", lambda _exports: ())
    assert _failed(install, CARRY) == module.A_VECTOR_WAS_KEPT


@pytest.mark.needs_db
def test_a_widening_that_is_derived_fails_the_learning_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal of a conclusion that changes who may see what removed. Delete this and one
    carries across."""
    from brain.migration import learning
    from brain.ops import acceptance_checks_migration_convert as module

    monkeypatch.setattr(learning, "CHANGES_WHAT_ANYBODY_MAY_SEE", frozenset())
    reason = _failed(install, LEARNING)
    assert reason in (module.A_WIDENING_WAS_DERIVED, module.A_PREFERENCE_WAS_REFUSED)


@pytest.mark.needs_db
def test_an_availability_given_a_default_fails_the_audience_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unmapped level defaulted to the narrowest. Delete this and a typo in a mapping becomes
    an agent nobody can see."""
    from brain.agents.model import AgentAudience
    from brain.knowledge.visibility import Visibility
    from brain.migration import rebuild
    from brain.ops import acceptance_checks_migration_convert as module

    def defaulted(foreign: Any, *, mapping: Any, owner_id: str, department: str = "") -> Any:
        level = mapping.get(foreign.availability, Visibility.PERSONAL)
        return AgentAudience(level=level, owner_id=owner_id, department=department)

    monkeypatch.setattr(rebuild, "audience_for", defaulted)
    assert _failed(install, AUDIENCE) == module.AN_UNMAPPED_LEVEL_WAS_DEFAULTED
