"""The quality install checks, each passing on PostgreSQL at head and each failing with the product
broken the way it would plausibly break.

The pure half holds the module's place and the leaves each check names. The database half runs the
module as the worker would: every check passes and nothing is left behind, then each is shown
failing with the guard it exists for removed: a flag filed outside the lead's department, a queue
given to a department reader, a candidate that changes an agent, a regression the comparison cannot
see, and an example in effect before it was promoted.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M28.3.1, M28.3.2, M28.3.3, M28.4.1, M28.5.3, M16.6.7, M16.7.14
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

MODULE = "brain.ops.acceptance_checks_quality"
FLAGS = "a_flag_becomes_a_case_that_holds_no_value"
TIERS = "readings_are_sampled_annotated_and_reported_as_two_tiers"
CANDIDATES = "a_failed_case_opens_a_candidate_and_never_changes_the_agent"
GOLDEN = "golden_scores_are_kept_by_release_and_a_regression_is_shown"
EXAMPLES = "an_approved_output_is_an_example_in_effect_only_once_promoted"

QUALITY_TABLES = (
    "ops.answer_flag",
    "ops.regression_case",
    "ops.quality_reading",
    "ops.quality_annotation",
    "ops.golden_score",
    "ops.evaluation_candidate",
    "ops.positive_example",
    "ops.tier_decision",
)


def test_the_module_declares_one_check_per_group_of_leaves() -> None:
    """Five checks, each closing its own leaves. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (FLAGS, ("M28.3.1", "M28.3.2")),
        (TIERS, ("M28.3.3",)),
        (CANDIDATES, ("M28.4.1",)),
        (GOLDEN, ("M28.5.3",)),
        (EXAMPLES, ("M16.6.7", "M16.7.14")),
    ]
    assert checks_in(MODULE) == [FLAGS, TIERS, CANDIDATES, GOLDEN, EXAMPLES]


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_quality") as url:
        yield url


def run_quality(url: str, *names: str) -> dict[str, tuple[str, str]]:
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
    both.update({one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in QUALITY_TABLES})  # noqa: S608
    return both


@pytest.mark.needs_db
def test_every_quality_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** All five pass and no flag, reading, score, candidate or
    decision is left. Delete this and a check that can never pass on a real schema, or one that
    leaves a candidate for an agent on the owner's install, reaches it."""
    before = _counts(install)
    outcomes = run_quality(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 5
    assert _counts(install) == before


def _failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_quality(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_flag_filed_in_a_department_the_lead_does_not_reach_fails_the_flags_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The department rule removed. Delete this and M28.3.1 closes on a lead who can file against
    any department's answers, which discloses that they exist."""
    from brain import quality_routes
    from brain.core.entitlement import EntitlementSet, Grant
    from brain.core.scope import Scope
    from brain.ops import feedback

    real = feedback.flag_answer

    def anyone(**kwargs: Any) -> Any:
        broad = EntitlementSet(
            principal_id=kwargs["flagger"].principal_id,
            grants=(Grant(capability=feedback.FLAG_CAPABILITY, scope=Scope.unrestricted()),),
        )
        return real(**{**kwargs, "flagger": broad})

    monkeypatch.setattr(quality_routes, "flag_answer", anyone)
    assert "do not reach" in _failed(install, FLAGS)


@pytest.mark.needs_db
def test_a_queue_given_to_a_department_reader_fails_the_tiers_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The company-wide rule removed. Delete this and M28.3.3 closes on a queue anybody with the
    flag grant may draw, which is a statement about every department's volume."""
    from brain import quality_routes

    monkeypatch.setattr(quality_routes, "_company_wide", lambda *args: True)
    assert "company-wide" in _failed(install, TIERS)


@pytest.mark.needs_db
def test_a_candidate_that_can_be_decided_twice_fails_the_candidates_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every candidate read as still pending. Delete this and M28.4.1 closes on a candidate whose
    decision can be taken again, so who decided it is whoever pressed last."""
    from dataclasses import replace

    from brain import quality_routes
    from brain.ops.quality_store import candidates as real

    async def always_pending(session: Any, **kwargs: Any) -> Any:
        return [replace(one, standing="pending") for one in await real(session, **kwargs)]

    monkeypatch.setattr(quality_routes, "candidates", always_pending)
    assert "decided twice" in _failed(install, CANDIDATES)


@pytest.mark.needs_db
def test_a_comparison_that_cannot_see_a_permission_failure_fails_the_golden_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression rule reading only the share. Delete this and M28.5.3 closes on a release
    that leaks and is called no worse."""
    from brain.ops import quality_store

    def share_only(latest: Any, previous: Any) -> bool:
        now, before = latest.quality_share, previous.quality_share
        return now is not None and before is not None and now < before

    monkeypatch.setattr(quality_store, "regressed", share_only)
    assert "regression" in _failed(install, GOLDEN)


@pytest.mark.needs_db
def test_an_example_in_effect_before_it_is_promoted_fails_the_examples_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The promotion read as optional. Delete this and M16.6.7 closes on examples that steer an
    agent the moment one person approved an output."""
    from sqlalchemy import select

    from brain.ops import quality_store
    from brain.tables.quality import PositiveExampleRow

    async def everything(session: Any, agent_id: str, *, now: Any) -> list[Any]:
        found = await session.execute(
            select(PositiveExampleRow).where(PositiveExampleRow.agent_id == agent_id)
        )
        return list(found.scalars())

    monkeypatch.setattr(quality_store, "examples_in_effect", everything)
    assert "before anybody promoted" in _failed(install, EXAMPLES)
