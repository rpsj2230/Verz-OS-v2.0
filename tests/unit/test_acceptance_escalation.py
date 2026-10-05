"""Install checks for escalation and sensitive topics: passing at head, and failing as they should.

The pure half holds the module to its leaves. The database half runs both checks as the worker
would, with the hosted profile and every provider's key in a vault the test answers for: they
pass, leave nothing and ask no provider. Then each is shown failing with the product broken the way
it would plausibly break: a handoff that carries what the asker could not see, an answer path that
hands nothing on, an expiry that marks nothing, and a sensitive question that reaches the model.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M8.4.1
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, counts
from tests.unit.test_acceptance_models import Providers, laddered, live_ladder

MODULE = "brain.ops.acceptance_escalation"
ESCALATED = "an_escalated_question_reaches_its_person_and_times_out"
SENSITIVE = "a_sensitive_question_is_routed_before_any_agent_answers"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_per_flow_for_its_leaves() -> None:
    """The escalation check claims the three escalation leaves and the proof leaf; the sensitive
    check claims the proof leaf alone. Delete this and a check can start claiming a leaf it never
    exercises, which closes that leaf on a check that says nothing about it."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (ESCALATED, ("M8.3.1", "M8.3.2", "M8.3.4", "M8.4.1")),
        (SENSITIVE, ("M8.4.1",)),
    ]


def test_the_check_s_queue_is_one_a_skill_may_name_and_its_deadline_one_a_skill_may_set() -> None:
    """Delete this and the check's own skill can be refused by the parser, so the check fails on
    every install for a reason that is the check's."""
    from brain.ops.acceptance_escalation import QUEUE, WITHIN_HOURS
    from brain.tools.skills import ESCALATION_QUEUE_RE, MAX_ESCALATION_HOURS

    assert ESCALATION_QUEUE_RE.match(QUEUE)
    assert 1 <= WITHIN_HOURS <= MAX_ESCALATION_HOURS


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_escalation") as url:
        laddered(url)
        yield url


@pytest.fixture
def vaulted(monkeypatch: pytest.MonkeyPatch) -> Providers:
    """The hosted profile and the vault the answer checks use, and the install offline."""
    from tests.unit.test_acceptance import INSTALL
    from tests.unit.test_acceptance_answers import vault_the_providers
    from tests.unit.test_acceptance_ingest import offline_install

    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)
    offline_install(monkeypatch)
    return vault_the_providers(monkeypatch)


def run_checks(url: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from(
        {
            "BRAIN_DATABASE_URL": url,
            "BRAIN_VAULT_ADDRESS": "https://vault.acceptance.invalid",
            "BRAIN_VAULT_TOKEN": "test-token-not-a-token",
        }
    )
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


@pytest.mark.needs_db
def test_both_checks_pass_on_an_install_and_leave_nothing(install: str, vaulted: Providers) -> None:
    """**The checks as the worker runs them.** Both pass; nothing either wrote is left, the ladder,
    the webhook channel and the queue's person included; and no provider was asked. Delete this
    and a check that can never pass on a real schema, or one that commits a handoff, reaches the
    owner's server first."""
    before, ladder = counts(install), live_ladder(install)
    assert run_checks(install) == {ESCALATED: (PASSED, ""), SENSITIVE: (PASSED, "")}
    assert counts(install) == before and live_ladder(install) == ladder
    assert vaulted.sent == []


def _failed(url: str, name: str) -> str:
    outcome, reason = run_checks(url)[name]
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_handoff_carrying_what_the_asker_could_not_see_fails(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The handoff's text built with the abstention's reason in it. Delete this and M8.4.1 closes
    with a handoff that tells the named person a refusal from an absence."""
    from brain.gate.escalating import handoff_text

    def telling(**kw: Any) -> str:
        return handoff_text(**kw) + " (not_entitled)"

    # By name, because `brain.escalation_routes` sends with the name it imported.
    monkeypatch.setattr("brain.escalation_routes.handoff_text", telling)
    assert "carried something the member could not see" in _failed(install, ESCALATED)


@pytest.mark.needs_db
def test_an_answer_path_that_hands_nothing_on_fails(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`escalated` answering unchanged. Delete this and M8.3.1 closes with a skill's declaration
    that nothing ever acts on."""
    from brain import escalation_routes

    async def unchanged(request: Any, answered: Any, **kw: Any) -> Any:
        return answered

    monkeypatch.setattr(escalation_routes, "escalated", unchanged)
    assert "did not say it was handed to a person" in _failed(install, ESCALATED)


@pytest.mark.needs_db
def test_an_expiry_that_marks_nothing_fails(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker's expiry marking nothing. Delete this and M8.3.4 closes with a deadline nothing
    enforces, so an asker waits for ever."""
    from brain.ops import escalation_store

    async def idle(session: Any, *, now: Any) -> int:
        return 0

    monkeypatch.setattr(escalation_store, "expire_overdue", idle)
    assert "did not say nobody picked their question up" in _failed(install, ESCALATED)


@pytest.mark.needs_db
def test_a_sensitive_question_that_reaches_the_model_fails(
    install: str, vaulted: Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The interception recognising nothing, so the question takes the ordinary path. Delete this
    and M8.4.1 closes on an install where a harassment report is answered by a model."""
    from brain import api_routes

    async def nowhere(request: Any, reach: Any, question: str) -> None:
        return None

    monkeypatch.setattr(api_routes, "referred", nowhere)
    assert "reached a model before it was routed" in _failed(install, SENSITIVE)
