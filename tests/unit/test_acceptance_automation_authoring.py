"""The install checks for New automation, each passing on PostgreSQL at head and each failing with
the product broken the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: every check
passes and leaves nothing. Then each is shown failing: a row read back with nothing of what the
person wrote, a run on the template's cadence instead of the writer's, a person without the read
the task needs being run anyway, a trigger nothing fires being run, one being offered a start, an
agent read without its attachments, a list of usable tools that is the agent's own list, and an
instruction automation that can be started.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M39.9.2.1, M39.9.2.2, M39.9.2.3, M39.9.2.4, M39.9.2.5, M17.4.1, M17.4.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, REASON_CHARS, registered
from brain.ops.acceptance_checks_automation_authoring import (
    A_KIND_RAN,
    A_REACH_WAS_INVENTED,
    A_TOOL_OUT_OF_REACH_WAS_USABLE,
    AN_INSTRUCTION_COULD_BE_STARTED,
    CHECK_ORDER,
    IT_DID_NOT_READ_BACK,
    THE_AGENT_READ_ITS_MANIFEST,
    THE_CADENCE_WAS_THE_TEMPLATES,
)
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_automation_authoring"
WRITES = "a_person_writes_changes_and_runs_an_automation_as_themselves"
KINDS = "each_kind_of_trigger_is_saved_and_a_webhook_is_refused"
USES = "an_automation_names_only_what_the_agents_ceiling_lets_a_run_use"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Three checks, each closing its own leaves. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (WRITES, ("M39.9.2.1", "M39.9.2.2", "M39.9.2.4", "M39.9.2.5", "M17.4.2")),
        (KINDS, ("M17.4.1", "M39.9.2.2")),
        (USES, ("M39.9.2.3",)),
    ]


def test_the_checks_are_listed_in_their_page_order_inside_this_modules_range() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row, or
    this module can stand where another agent's range starts."""
    assert checks_in(MODULE) == [WRITES, KINDS, USES]
    assert 1600 <= CHECK_ORDER <= 1699


def test_the_sentences_a_check_may_end_with_fit_the_result() -> None:
    """Stored whole. Delete this and why a check failed is cut short on the Install page."""
    for sentence in (
        A_KIND_RAN,
        A_REACH_WAS_INVENTED,
        IT_DID_NOT_READ_BACK,
        A_TOOL_OUT_OF_REACH_WAS_USABLE,
        AN_INSTRUCTION_COULD_BE_STARTED,
        THE_AGENT_READ_ITS_MANIFEST,
    ):
        assert len(sentence) <= REASON_CHARS


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_automation_authoring") as url:
        yield url


def run_checks(url: str, *names: str) -> dict[str, tuple[str, str]]:
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


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_checks(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_every_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** Every one passes and nothing a check wrote is left: no
    automation, no run, no schedule row. Delete this and a check that can never pass on a real
    schema, or one that leaves an automation behind, reaches the owner's server."""
    from tests.fixtures.scratch_postgres import sql

    before = counts(install)
    outcomes = run_checks(install)

    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 3
    assert counts(install) == before
    assert sql(install, "SELECT count(*) FROM agent.automation") == [(0,)]


@pytest.mark.needs_db
def test_an_automation_read_back_without_what_was_written_fails_the_first_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store that reads an authored row back as an installed one. Delete this and M39.9.2.1
    closes on a screen that shows a person's automation with none of their words."""
    from brain.ops import automation_run_store

    monkeypatch.setattr(automation_run_store, "_authored_of", lambda row: None)

    assert _failed(install, WRITES) != ""


@pytest.mark.needs_db
def test_a_run_on_the_templates_cadence_fails_the_first_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker asking the template list for a cadence the person changed. Delete this and
    M39.9.2.1 closes on an automation that runs when the product says, not when its writer did."""
    from brain.console.automation_gallery import template_by_id
    from brain.ops import automation_run_store

    real = automation_run_store._cadence_of

    def templates_own(row: Any) -> Any:
        template = template_by_id("unanswered_questions")
        return real(row) if template is None or row.template_id != "authored" else template.cadence

    monkeypatch.setattr(automation_run_store, "_cadence_of", templates_own)

    assert THE_CADENCE_WAS_THE_TEMPLATES in _failed(install, WRITES)


@pytest.mark.needs_db
def test_a_run_that_ignores_the_writers_reach_fails_the_first_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reach test at a run answering yes for everybody. Delete this and M39.9.2.5 closes on an
    automation that runs at a reach its writer does not hold."""
    from brain.console.agent_automations import automation_reach
    from brain.ops import automation_run, automation_run_store

    real = automation_run.admitted_run

    def always(automation: Any, **kwargs: Any) -> Any:
        admitted = real(automation, **kwargs)
        if admitted is not automation_run.PausedBecause.OWNER_LOST_REACH:
            return admitted
        declaration = automation_run.task_declaration(automation.task)
        assert declaration is not None
        return automation_run.Admitted(
            reach=automation_reach(kwargs["owner_entitlements"], kwargs["agent"]),
            declaration=declaration,
        )

    monkeypatch.setattr(automation_run_store, "admitted_run", always)

    assert A_REACH_WAS_INVENTED in _failed(install, WRITES)


@pytest.mark.needs_db
def test_a_clock_that_claims_an_automation_a_change_starts_fails_the_second_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker's clock treating a row a change starts as one it may run. Delete this and M17.4.1
    closes on a listener the clock claims as a schedule with no cadence and refuses on its first
    minute."""
    from sqlalchemy import true

    from brain.ops import automation_run_store

    monkeypatch.setattr(automation_run_store, "_started_by_the_clock", lambda: true())

    assert A_KIND_RAN in _failed(install, KINDS)


@pytest.mark.needs_db
def test_an_agent_read_without_its_attachments_fails_the_third_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The routes' agent reader handing back the manifest's tools alone. Delete this and M39.9.2.3
    closes on an agent whose detached tool can still be named on a new automation."""
    from brain import automation_gallery_routes
    from brain.agent_routes import one_agent, record_of

    async def manifest_only(self: Any, agent_id: str) -> Any:
        async with self._sessions() as session:
            row = (await session.execute(one_agent(agent_id))).scalar_one_or_none()
        return None if row is None else record_of(row)

    monkeypatch.setattr(automation_gallery_routes.StoredAgentRecords, "agent", manifest_only)

    assert THE_AGENT_READ_ITS_MANIFEST in _failed(install, USES)


@pytest.mark.needs_db
def test_a_list_of_usable_tools_that_is_the_agents_own_list_fails_the_third_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The projection replaced by a copy of the agent's list. Delete this and M39.9.2.3 closes on
    a form that offers a write above the ceiling."""
    from brain.console import automation_authoring

    monkeypatch.setattr(
        automation_authoring,
        "usable_tools",
        lambda agent, registry, reach, *, now: agent.authority.allowed_tools,
    )

    assert A_TOOL_OUT_OF_REACH_WAS_USABLE in _failed(install, USES)


@pytest.mark.needs_db
def test_an_instruction_that_can_be_started_fails_the_third_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The start's own question answering that nothing stops it. Delete this and M39.9.2.3 closes
    on a card that says it cannot be started while a second person starts it."""
    from brain.console import automation_schedule

    monkeypatch.setattr(automation_schedule, "cannot_start_because", lambda one, agent, now: None)

    assert AN_INSTRUCTION_COULD_BE_STARTED in _failed(install, USES)
