"""The install checks for what a migration leans on, each passing on PostgreSQL at head and failing
with the product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M37.2.2.3, M37.2.3.1, M37.2.3.2, M37.2.3.3, M37.3.2.4, M37.5.1.2, M37.5.1.4
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

MODULE = "brain.ops.acceptance_checks_migration_rebuild"
REBUILT = "an_agent_is_rebuilt_from_a_template_with_a_ceiling_and_at_shadow"
SKILL = "a_skill_added_from_outside_runs_only_after_its_review"
ADOPTION = "adoption_counts_the_person_and_leaves_the_machines_out"
CONTROLS = "every_scheduled_control_is_listed_and_has_a_caller"
WRITTEN = (
    "agent.template_version",
    "agent.template_instance",
    "agent.agent",
    "agent.skill",
    "ops.question_asked",
)


def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Delete this and a check can lose a leaf with the Install page showing the same rows, and the
    leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (REBUILT, ("M37.2.3.1", "M37.2.3.2", "M37.2.3.3")),
        (SKILL, ("M37.2.2.3",)),
        (ADOPTION, ("M37.3.2.4",)),
        (CONTROLS, ("M37.5.1.2", "M37.5.1.4")),
    ]
    assert checks_in(MODULE) == [REBUILT, SKILL, ADOPTION, CONTROLS]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_migration_rebuild") as url:
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
    # The names are this module's constants, never input.
    both.update({one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in WRITTEN})  # noqa: S608
    return both


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All four pass and no agent, template version, skill
    or question is left. Delete this and a check that can never pass on a real schema, or that
    leaves an agent on the owner's install, reaches it."""
    before = _counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 4
    assert _counts(install) == before


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_an_agent_that_starts_above_shadow_fails_the_rebuild_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The install route reporting a leash rung above Shadow. Delete this and M37.2.3.3 closes on
    a rebuilt agent that kept the autonomy its old system gave it."""
    from brain import agent_lifecycle_routes
    from brain.ops import acceptance_checks_migration_rebuild as module

    real = agent_lifecycle_routes.leash_view

    def raised(leash: Any) -> Any:
        return [one.model_copy(update={"rung": "draft"}) for one in real(leash)]

    monkeypatch.setattr(agent_lifecycle_routes, "leash_view", raised)
    assert _failed(install, REBUILT) == module.NOT_AT_SHADOW


@pytest.mark.needs_db
def test_a_run_that_is_not_narrowed_by_the_ceiling_fails_the_rebuild_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one wrapper over the intersection returning the caller's own reach. Delete this and
    M37.2.3.2 closes on an agent whose ceiling narrows nothing."""
    from brain.ops import acceptance_checks_migration_rebuild as module
    from brain.ops import automation

    monkeypatch.setattr(automation, "flow_reach", lambda caller, _ceiling: caller)
    assert _failed(install, REBUILT) == module.THE_CEILING_DID_NOT_NARROW


@pytest.mark.needs_db
def test_a_skill_executable_before_its_review_fails_the_skill_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A skill that counts as executable straight away. Delete this and M37.2.2.3 closes on a
    library that trusts a skill because it came from somewhere that trusted it."""
    from brain.ops import acceptance_checks_migration_rebuild as module
    from brain.tools.skills import ImportedSkill

    monkeypatch.setattr(ImportedSkill, "is_executable", lambda _self: True)
    assert _failed(install, SKILL) == module.AN_IMPORT_WAS_TRUSTED


@pytest.mark.needs_db
def test_machine_traffic_counted_as_a_person_fails_the_adoption_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every question counted as a person's. Delete this and M37.3.2.4 closes on an adoption
    figure a nightly job can raise."""
    from brain import adoption
    from brain.ops import acceptance_checks_migration_rebuild as module

    monkeypatch.setattr(adoption, "is_automated", lambda *_a, **_k: False)
    assert _failed(install, ADOPTION) == module.A_MACHINE_WAS_COUNTED


@pytest.mark.needs_db
def test_a_job_the_screen_does_not_list_fails_the_controls_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Jobs route listing one control fewer than the scheduler runs. Delete this and
    M37.5.1.2 closes on a safety control nobody can see being scheduled."""
    from brain import jobs_routes
    from brain.ops import acceptance_checks_migration_rebuild as module
    from brain.ops.schedule import schedulable

    monkeypatch.setattr(jobs_routes, "schedulable", lambda *a, **k: schedulable(*a, **k)[:-1])
    assert _failed(install, CONTROLS) == module.A_JOB_WAS_NOT_LISTED
