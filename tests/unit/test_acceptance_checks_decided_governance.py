"""The install checks for the governance decisions answered on 2026-10-12 and 2026-10-13: each
passing on PostgreSQL at head and leaving nothing, and each failing with the product broken.

The database half runs the module as the worker would. Then each check is shown failing where the
product is broken the way it would plausibly break: the count of redacted requests sent to a reader
who may not see them all, the leash ceiling removed, the steward allowed to switch channels, a
department's administrator unable to stop their own agent or able to stop another's, the widget
offered to an agent that reads more, and the builder's links dropped.

Task ids: M33.4.1.3, M33.2.2.4, M39.8.1, M33.8.3, M13.7.3, M13.7.4, M13.9.1, M20.1.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_decided_governance"
COUNT = "redacted_requests_are_counted_for_a_reader_who_may_see_them_all"
RUNG = "a_rung_cannot_pass_the_rung_the_agent_was_published_at"
ROLE = "a_steward_changes_no_channel_or_connector_and_the_role_is_named"
STOP = "a_department_admin_stops_one_agent_of_their_own_department"
WIDGET = "the_widget_is_offered_only_to_an_agent_reading_public_knowledge"
LINKS = "the_builder_links_the_parts_of_an_agent_it_does_not_hold"


def test_the_module_declares_one_check_per_decision() -> None:
    """Six checks, each closing its own leaves. Delete this and a check can lose a leaf with the
    page showing the same rows, and the leaf closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (COUNT, ("M33.4.1.3",)),
        (RUNG, ("M33.2.2.4",)),
        (ROLE, ("M39.8.1", "M33.8.3")),
        (STOP, ("M13.7.3",)),
        (WIDGET, ("M13.7.4",)),
        (LINKS, ("M20.1.1", "M13.9.1")),
    ]


def test_the_checks_are_listed_in_their_page_order_inside_the_assigned_range() -> None:
    """Delete this and a check can drop out of the module with the page listing one fewer row, or
    the module's order can wander out of the range it was assigned and collide with another's."""
    from brain.ops.acceptance_checks_decided_governance import CHECK_ORDER

    assert checks_in(MODULE) == [COUNT, RUNG, ROLE, STOP, WIDGET, LINKS]
    assert 1400 <= CHECK_ORDER <= 1499


@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_decided_governance") as url:
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


@pytest.mark.needs_db
def test_every_decided_governance_check_passes_on_an_install_and_leaves_nothing(
    install: str,
) -> None:
    """**The module as the worker runs it.** All six pass and nothing a check wrote is left.
    Delete this and a check that can never pass on a real schema reaches the owner's server."""
    before = counts(install)
    outcomes = run_module(install)
    assert outcomes == dict.fromkeys(outcomes, (PASSED, "")), outcomes
    assert len(outcomes) == 6
    assert counts(install) == before


def failed(url: str, name: str) -> str:
    [(outcome, reason)] = run_module(url, name).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_count_sent_to_a_reader_who_may_not_see_it_all_fails_the_count_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reach test answering yes for everybody. Delete this and M33.4.1.3 closes on a figure
    over requests a narrower auditor cannot see."""
    from brain import audit_statistics_routes

    monkeypatch.setattr(audit_statistics_routes, "covers_everybody", lambda reach, now: True)
    assert "covers less was sent a count" in failed(install, COUNT)


@pytest.mark.needs_db
def test_a_leash_with_no_ceiling_fails_the_rung_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The published rung read as the top of the ladder. Delete this and M33.2.2.4 closes on a
    leash that can be raised past what two approvers signed for."""
    from brain import agent_leash_routes
    from brain.gate.injection import AutonomyTier

    monkeypatch.setattr(
        agent_leash_routes, "published_rung", lambda *_arguments: AutonomyTier.AUTONOMOUS
    )
    assert "above the rung the agent was published at" in failed(install, RUNG)


@pytest.mark.needs_db
def test_a_steward_allowed_to_switch_channels_fails_the_role_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The channel switch allowed to the agent's steward again. Delete this and M39.8.1 closes on
    a rule the owner decided against."""
    from brain import agent_lifecycle_routes

    monkeypatch.setattr(agent_lifecycle_routes, "may_change_channels", lambda record, asked: True)
    assert "steward switched its channels" in failed(install, ROLE)


@pytest.mark.needs_db
def test_a_department_administrator_who_cannot_stop_their_agent_fails_the_stop_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The agent's department never looked up. Delete this and M13.7.3 closes on a department's
    administrator who still has to ask the company's."""
    from brain import halt_routes

    async def nobody(request: object, scope: object, target: object) -> str:
        return ""

    monkeypatch.setattr(halt_routes, "_agent_department_of", nobody)
    assert failed(install, STOP)


@pytest.mark.needs_db
def test_a_widget_offered_to_every_agent_fails_the_widget_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The public-knowledge question answering yes. Delete this and M13.7.4 closes on a widget
    that can be put in front of visitors on an agent that reads company data."""
    from brain import agent_lifecycle_routes

    monkeypatch.setattr(
        agent_lifecycle_routes, "ceiling_holds_only_public_knowledge", lambda record, policy: True
    )
    assert "reading more than public" in failed(install, WIDGET)


@pytest.mark.needs_db
def test_a_builder_that_drops_its_links_fails_the_links_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The links emptied. Delete this and M20.1.1 closes on a builder with nothing pointing at
    where workflows, memory and channels are set."""
    from brain import agent_builder_routes

    monkeypatch.setattr(agent_builder_routes, "SET_ELSEWHERE", ())
    assert "did not name where each part" in failed(install, LINKS)
