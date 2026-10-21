"""The install checks for stored workflows, each passing on PostgreSQL at head and failing with the
product broken.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M17.6.1, M17.6.2, M17.6.3, M17.6.4, M17.6.6, M17.6.7, M17.7.7
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

MODULE = "brain.ops.acceptance_checks_workflow"
CONFIG = "a_workflow_is_saved_in_versions_and_run_by_an_assigned_agent"
RUN = "a_workflow_runs_through_the_gate_and_one_trace_is_kept"
WRITTEN = (
    "ops.workflow_version",
    "agent.workflow_assignment",
    "ops.workflow_run",
    "ops.workflow_step_run",
    "ops.evaluation_candidate",
    "ops.outbox_event",
)


def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Delete this and a check can lose a leaf with the Install page showing the same rows, and the
    leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (CONFIG, ("M17.6.1", "M17.7.7")),
        (RUN, ("M17.6.2", "M17.6.3", "M17.6.4", "M17.6.6", "M17.6.7")),
    ]
    assert checks_in(MODULE) == [CONFIG, RUN]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_workflow") as url:
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
    """**The module as the worker runs it.** Both pass and no workflow, run, candidate or event is
    left. Delete this and a check that can never pass on a real schema, or that leaves rows in
    tables nothing can delete from, reaches the owner's install."""
    before = _counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 2
    assert _counts(install) == before


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_workflow_run_by_an_agent_never_assigned_it_fails_the_configuration_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The assignment read as always there. Delete this and M17.7.7 closes on a refusal that
    refuses nothing."""
    from brain import workflow_routes
    from brain.ops import acceptance_checks_workflow as module

    async def everything(self: Any, agent_id: str) -> tuple[str, ...]:
        listed = await workflow_routes.StoredWorkflows.listing(self)
        return (*[one.workflow_id for one in listed], "no-such-workflow")

    monkeypatch.setattr(workflow_routes.StoredWorkflows, "assigned", everything)
    assert _failed(install, CONFIG) in {
        module.AN_UNASSIGNED_RUN_STARTED,
        module.THE_REFUSALS_DIFFER,
        module.NOT_ASSIGNED,
    }


@pytest.mark.needs_db
def test_a_trace_that_is_not_kept_fails_the_run_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run's write removed. Delete this and M17.6.8 closes on a trace nothing keeps."""
    from brain.ops import acceptance_checks_workflow as module
    from brain.ops import workflow_store

    async def nothing(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(workflow_store, "keep_run", nothing)
    assert _failed(install, RUN) in {
        module.THE_TRACE_WAS_NOT_KEPT,
        module.NO_SIGNAL_WAS_SENT,
        module.NO_CANDIDATE_WAS_OPENED,
    }


@pytest.mark.needs_db
def test_a_mask_that_does_not_hold_fails_the_run_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The step's outputs taken from anything the record holds, masked or not. Delete this and the
    workflow's door is believed to hold the gate's mask without anybody having looked."""
    from brain.ops import acceptance_checks_workflow as module
    from brain.orchestration import workflow_run

    def always(step: Any, result: Any) -> dict[str, object]:
        return {out.name: "x" for out in step.outputs}

    monkeypatch.setattr(workflow_run, "_outputs_of", always)
    assert _failed(install, RUN) == module.THE_MASK_DID_NOT_HOLD


@pytest.mark.needs_db
def test_a_candidate_that_is_never_opened_fails_the_run_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repeats read as never. Delete this and M17.6.7 closes on a failure nobody is shown."""
    from brain.ops import acceptance_checks_workflow as module
    from brain.ops import workflow_store

    monkeypatch.setattr(workflow_store, "repeats", lambda *_a, **_k: False)
    assert _failed(install, RUN) == module.NO_CANDIDATE_WAS_OPENED
